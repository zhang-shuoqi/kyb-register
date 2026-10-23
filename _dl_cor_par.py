"""FL cordata.zip — PARALLEL segment downloader (4 SFTP connections).
Keeps existing prefix, downloads remainder in 4 segments, merges, verifies.
done flag: data/done_fl.flag

v2 (2026-10-23):
  + StallWatchdog — SFTP reads hang forever when the channel half-dies
    (observed twice tonight: fast start, then zero progress, no exception).
    Watchdog force-closes the transport after STALL_SECS without progress,
    which unblocks the stuck recv(); the retry loop reconnects and resumes
    from the on-disk segment size (content-safe).
  + single-instance lock (same pattern as _dl_au_par.py) — prevents
    multi-writer corruption.
  + banner/connect timeouts on Transport.
"""
import paramiko
import threading
import time
from pathlib import Path

BASE = Path(__file__).parent / "data"
ZIP = BASE / "sunbiz_quarterly" / "cordata.zip"
LOG = BASE / "download_cor.log"
FLAG = BASE / "done_fl.flag"
SEGDIR = BASE / "sunbiz_quarterly" / "segs"
HOST, USER, PASS = "sftp.floridados.gov", "Public", "PubAccess1845!"
REMOTE = "doc/Quarterly/Cor/cordata.zip"
NSEG = 4
STALL_SECS = 90
LOCK = threading.Lock()


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOCK:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


class StallWatchdog:
    """Force-close the transport if no progress for STALL_SECS seconds.
    Closing the socket unblocks a recv() stuck in the reader thread."""

    def __init__(self, transport, tag):
        self.transport = transport
        self.tag = tag
        self.lock = threading.Lock()
        self.timer = None
        self.finished = False

    def kick(self):
        with self.lock:
            if self.finished:
                return
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(STALL_SECS, self._fire)
            self.timer.daemon = True
            self.timer.start()

    def _fire(self):
        if self.finished:
            return
        log(f"watchdog[{self.tag}]: no progress {STALL_SECS}s — force-closing transport")
        try:
            self.transport.close()
        except Exception:
            pass

    def cancel(self):
        with self.lock:
            self.finished = True
            if self.timer:
                self.timer.cancel()


def fetch_total():
    transport = paramiko.Transport((HOST, 22))
    wd = StallWatchdog(transport, "stat")
    wd.kick()
    try:
        transport.connect(username=USER, password=PASS)
        s = paramiko.SFTPClient.from_transport(transport)
        total = s.stat(REMOTE).st_size
        s.close()
        return total
    finally:
        wd.cancel()
        try:
            transport.close()
        except Exception:
            pass


def download_seg(idx, start, end):
    """Download [start, end) into seg_{idx}.part with resume."""
    seg = SEGDIR / f"seg_{idx}.part"
    while True:
        have = seg.stat().st_size if seg.exists() else 0
        need = end - start
        if have >= need:
            log(f"seg{idx} complete ({have/1024/1024:.0f} MB)")
            return
        transport = None
        wd = None
        try:
            transport = paramiko.Transport((HOST, 22))
            wd = StallWatchdog(transport, f"seg{idx}")
            wd.kick()
            transport.connect(username=USER, password=PASS)
            sftp = paramiko.SFTPClient.from_transport(transport)
            with sftp.open(REMOTE, "rb") as rf:
                rf.seek(start + have)
                remaining = need - have
                with open(seg, "ab") as f:
                    done = have
                    last_log = done
                    while remaining > 0:
                        chunk = rf.read(min(512 * 1024, remaining))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                        done += len(chunk)
                        wd.kick()
                        if done - last_log >= 30 * 1024 * 1024:
                            log(f"  seg{idx}: {done/1024/1024:.0f} MB")
                            last_log = done
            sftp.close()
        except Exception as e:
            log(f"⚠ seg{idx}: {type(e).__name__}; retry in 15s")
            time.sleep(15)
        finally:
            if wd:
                wd.cancel()
            if transport is not None:
                try:
                    transport.close()
                except Exception:
                    pass


def already_running():
    """Return True if another _dl_cor_par.py instance is alive (besides self)."""
    import os
    import subprocess as sp
    my_pid = os.getpid()
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          f"Where-Object {{ $_.CommandLine -like '*python.exe*\"*_dl_cor_par.py\"*' -and $_.ProcessId -ne {my_pid} -and $_.CommandLine -notlike '*_supervise.py*' }} | "
          "Measure-Object | Select-Object -ExpandProperty Count")
    try:
        r = sp.run(["powershell.exe", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True, timeout=30)
        return int(r.stdout.strip() or "0") > 0
    except Exception:
        return False  # fail-open (never block download because check failed)


def main():
    SEGDIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    total = fetch_total()
    prefix = ZIP.stat().st_size if ZIP.exists() else 0
    log(f"total={total/1024/1024:.0f} MB, prefix={prefix/1024/1024:.0f} MB")
    if prefix >= total:
        log("already complete")
        FLAG.write_text("ok")
        return
    remaining = total - prefix
    seg_size = remaining // NSEG
    segs = []
    for i in range(NSEG):
        start = prefix + i * seg_size
        end = total if i == NSEG - 1 else prefix + (i + 1) * seg_size
        segs.append((i, start, end))

    threads = []
    for idx, start, end in segs:
        t = threading.Thread(target=download_seg, args=(idx, start, end), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    # verify segments
    for idx, start, end in segs:
        seg = SEGDIR / f"seg_{idx}.part"
        if seg.stat().st_size != end - start:
            log(f"❌ seg{idx} size mismatch, rerun script")
            return

    # merge: prefix + segs -> new zip
    log("merging prefix + 4 segments...")
    tmp = ZIP.with_suffix(".zip.new")
    with open(ZIP, "rb") as pf, open(tmp, "wb") as out:
        while True:
            chunk = pf.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
        for idx, start, end in segs:
            with open(SEGDIR / f"seg_{idx}.part", "rb") as sf:
                while True:
                    chunk = sf.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
    if tmp.stat().st_size == total:
        tmp.replace(ZIP)
        log(f"🎉 FL COMPLETE: {total/1024/1024:.0f} MB in {time.time()-t0:.0f}s")
        FLAG.write_text("ok")
        for idx in range(NSEG):
            (SEGDIR / f"seg_{idx}.part").unlink(missing_ok=True)
    else:
        log(f"❌ merged size {tmp.stat().st_size} != {total}")


if __name__ == "__main__":
    if already_running():
        log("⛔ another _dl_cor_par.py instance is already running — exit")
    else:
        main()
