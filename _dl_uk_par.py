"""UK CH snapshot downloader — PARALLEL (7 threads, one per part).
Self-healing per-thread (Range-206 aware). done flag on all parts complete.
Log: data/download_uk.log
"""
import threading
import time
import urllib.request
from pathlib import Path

DIR = Path(__file__).parent / "data" / "uk_snapshot"
LOG = Path(__file__).parent / "data" / "download_uk.log"
FLAG = Path(__file__).parent / "data" / "done_uk.flag"
BASE = "https://download.companieshouse.gov.uk/BasicCompanyData-2026-10-01-part{0}_7.zip"
LOCK = threading.Lock()

# exact byte sizes observed on 2026-10-22 (CRC-verified complete) — skip if local >= these
DONE_SIZES = {1: 73166493, 2: 73760929, 3: 73610038, 4: 73772663, 5: 73531039, 6: 73591961, 7: 52565573}


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOCK:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def download_part(i):
    url = BASE.format(i)
    out = DIR / f"part{i}_7.zip"
    if i in DONE_SIZES and out.exists() and out.stat().st_size >= DONE_SIZES[i]:
        log(f"⏭ part{i} already complete ({out.stat().st_size/1024/1024:.1f} MB), skip")
        return
    while True:
        resume = out.stat().st_size if out.exists() else 0
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kyb-register/0.1"})
            if resume:
                req.add_header("Range", f"bytes={resume}-")
            with urllib.request.urlopen(req, timeout=60) as r:
                ranged = (r.status == 206)
                if resume and not ranged:
                    log(f"  part{i}: server ignored Range (200), restart from 0")
                    resume = 0
                total = r.headers.get("Content-Length")
                total = int(total) + (resume if ranged else 0) if total else None
                mode = "ab" if (resume and ranged) else "wb"
                done = resume if ranged else 0
                with open(out, mode) as f:
                    while True:
                        chunk = r.read(512 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
            size = out.stat().st_size
            if total and size >= total:
                log(f"✅ part{i} complete: {size/1024/1024:.1f} MB")
                return
            if total is None:
                log(f"✅ part{i} complete (no CL): {size/1024/1024:.1f} MB")
                return
            log(f"⚠ part{i} short: {size} < {total}; resuming")
        except Exception as e:
            log(f"⚠ part{i}: {type(e).__name__}; retry in 15s")
            time.sleep(15)


def main():
    DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    threads = []
    for i in range(1, 8):
        t = threading.Thread(target=download_part, args=(i,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(1)  # stagger starts
    for t in threads:
        t.join()
    log(f"🎉 ALL 7 PARTS COMPLETE in {time.time()-t0:.0f}s")
    FLAG.write_text("ok")


if __name__ == "__main__":
    main()
