"""AU ASIC CSV downloader (self-healing, resumable). 381.8 MB.
Output: data/asic_companies.csv — done flag: data/done_au.flag
"""
import time
import urllib.request
from pathlib import Path

URL = (
    "https://data.gov.au/data/dataset/7b8656f9-606d-4337-af29-66b89b2eeefb/"
    "resource/5c3914e6-413e-4a2c-b890-bf8efe3eabf2/download"
)
OUT = Path(__file__).parent / "data" / "asic_companies.csv"
LOG = Path(__file__).parent / "data" / "download_au.log"
FLAG = Path(__file__).parent / "data" / "done_au.flag"


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


OUT.parent.mkdir(parents=True, exist_ok=True)
t0 = time.time()
while True:
    resume = OUT.stat().st_size if OUT.exists() else 0
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "kyb-register/0.1"})
        if resume:
            req.add_header("Range", f"bytes={resume}-")
        with urllib.request.urlopen(req, timeout=60) as r:
            ranged = (r.status == 206)
            if resume and not ranged:
                log(f"server ignored Range (200), restart from 0")
                resume = 0
            total = r.headers.get("Content-Length")
            total = int(total) + (resume if ranged else 0) if total else None
            mode = "ab" if (resume and ranged) else "wb"
            done = resume if ranged else 0
            last_log = done
            with open(OUT, mode) as f:
                while True:
                    chunk = r.read(512 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if done - last_log >= 20 * 1024 * 1024:
                        log(f"  {done/1024/1024:.0f} MB ({(done-resume)/1024/1024/max(time.time()-t0,1):.2f} MB/s)")
                        last_log = done
        size = OUT.stat().st_size
        if total and size >= total:
            log(f"✅ AU COMPLETE: {size/1024/1024:.1f} MB in {time.time()-t0:.0f}s")
            FLAG.write_text("ok")
            break
        if total is None:
            log(f"✅ AU COMPLETE (no CL): {size/1024/1024:.1f} MB in {time.time()-t0:.0f}s")
            FLAG.write_text("ok")
            break
        log(f"⚠ short: {size} < {total}; resuming")
    except Exception as e:
        log(f"⚠ {type(e).__name__}: {e}; retry in 15s")
        time.sleep(15)
