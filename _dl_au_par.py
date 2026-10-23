"""AU ASIC CSV — PARALLEL (6 HTTP connections, prefix + segments + merge).
Resumes: keeps existing prefix (data/asic_companies.csv), splits remainder.
done flag: data/done_au.flag
"""
import threading
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data"
OUT = DATA / "asic_companies.csv"
LOG = DATA / "download_au.log"
FLAG = DATA / "done_au.flag"
SEGDIR = DATA / "au_segs"
URL = (
    "https://data.gov.au/data/dataset/7b8656f9-606d-4337-af29-66b89b2eeefb/"
    "resource/5c3914e6-413e-4a2c-b890-bf8efe3eabf2/download"
)
NSEG = 6
LOCK = threading.Lock()


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOCK:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def get_total():
    req = urllib.request.Request(URL, method="HEAD", headers={"User-Agent": "kyb-register/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])


def download_seg(idx, start, end):
    seg = SEGDIR / f"auseg_{idx}.part"
    while True:
        have = seg.stat().st_size if seg.exists() else 0
        need = end - start
        if have >= need:
            log(f"auseg{idx} complete ({have/1024/1024:.0f} MB)")
            return
        try:
            req = urllib.request.Request(
                URL, headers={"User-Agent": "kyb-register/0.1", "Range": f"bytes={start + have}-"}
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                ranged = r.status == 206
                if not ranged:
                    # server ignored Range (200 full-file) — writing it would corrupt
                    # the segment with out-of-slice bytes. Discard and retry.
                    log(f"auseg{idx}: server ignored Range (200), discard & retry")
                    time.sleep(5)
                    continue
                mode = "ab"
                done = have
                remaining = need - done
                last_log = done
                with open(seg, mode) as f:
                    while remaining > 0:
                        chunk = r.read(min(512 * 1024, remaining))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                        done += len(chunk)
                        if done - last_log >= 30 * 1024 * 1024:
                            log(f"  auseg{idx}: {done/1024/1024:.0f} MB")
                            last_log = done
        except Exception as e:
            log(f"⚠ auseg{idx}: {type(e).__name__}; retry in 15s")
            time.sleep(15)


def main():
    SEGDIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    total = get_total()
    prefix = OUT.stat().st_size if OUT.exists() else 0
    log(f"AU total={total/1024/1024:.1f} MB, prefix={prefix/1024/1024:.1f} MB, {NSEG} segments")
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

    for idx, start, end in segs:
        seg = SEGDIR / f"auseg_{idx}.part"
        if seg.stat().st_size != end - start:
            log(f"❌ auseg{idx} size mismatch, rerun")
            return

    log("merging prefix + 6 segments...")
    tmp = OUT.with_suffix(".csv.new")
    with open(tmp, "wb") as out:
        if prefix > 0 and OUT.exists():
            with open(OUT, "rb") as pf:
                while True:
                    chunk = pf.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
        else:
            log("  (no prefix — segments contain the whole file)")
            # rename seg_0 as the base? simpler: copy segs in order
        for idx, start, end in segs:
            with open(SEGDIR / f"auseg_{idx}.part", "rb") as sf:
                while True:
                    chunk = sf.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
    if tmp.stat().st_size == total:
        tmp.replace(OUT)
        log(f"🎉 AU COMPLETE: {total/1024/1024:.1f} MB in {time.time()-t0:.0f}s")
        FLAG.write_text("ok")
        for idx in range(NSEG):
            (SEGDIR / f"auseg_{idx}.part").unlink(missing_ok=True)
    else:
        log(f"❌ merged size {tmp.stat().st_size} != {total}")



def already_running():
    """Return True if another _dl_au_par.py instance is alive (besides self)."""
    import os
    import subprocess as sp
    my_pid = os.getpid()
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          f"Where-Object {{ $_.CommandLine -like '*python.exe*\"*_dl_au_par.py\"*' -and $_.ProcessId -ne {my_pid} -and $_.CommandLine -notlike '*_supervise.py*' }} | "
          "Measure-Object | Select-Object -ExpandProperty Count")
    try:
        r = sp.run(["powershell.exe", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True, timeout=30)
        return int(r.stdout.strip() or "0") > 0
    except Exception:
        return False  # fail-open (never block download because check failed)


if __name__ == "__main__":
    if already_running():
        log("⛔ another _dl_au_par.py instance is already running — exit")
        raise SystemExit(0)
    main()
