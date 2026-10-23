"""UK CH snapshot downloader (python, self-healing, resumable).
7 parts x ~70MB. Log: data/download_uk.log
"""
import time
import urllib.request
from pathlib import Path

DIR = Path(__file__).parent / "data" / "uk_snapshot"
LOG = Path(__file__).parent / "data" / "download_uk.log"
BASE = "https://download.companieshouse.gov.uk/BasicCompanyData-2026-10-01-part{0}_7.zip"


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


DIR.mkdir(parents=True, exist_ok=True)
t0 = time.time()

for i in range(1, 8):
    url = BASE.format(i)
    out = DIR / f"part{i}_7.zip"
    while True:
        resume = out.stat().st_size if out.exists() else 0
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kyb-register/0.1"})
            if resume:
                req.add_header("Range", f"bytes={resume}-")
            with urllib.request.urlopen(req, timeout=60) as r:
                # 206 = Range 生效（续传）；200 = 服务器不支持 Range，必须从头重写
                ranged = (r.status == 206)
                if resume and not ranged:
                    log(f"  part{i}: server ignored Range (200), restarting from 0")
                    resume = 0
                total = r.headers.get("Content-Length")
                total = int(total) + (resume if ranged else 0) if total else None
                mode = "ab" if (resume and ranged) else "wb"
                done = resume if ranged else 0
                last_log = done
                with open(out, mode) as f:
                    while True:
                        chunk = r.read(512 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if done - last_log >= 20 * 1024 * 1024:
                            log(f"  part{i}: {done/1024/1024:.0f} MB")
                            last_log = done
            size = out.stat().st_size
            if total and size >= total:
                log(f"✅ part{i} complete: {size/1024/1024:.1f} MB ({time.time()-t0:.0f}s)")
                break
            elif total is None:
                # 服务器没给 Content-Length：读完即完成（chunk 循环已到 EOF）
                log(f"✅ part{i} complete (no CL): {size/1024/1024:.1f} MB ({time.time()-t0:.0f}s)")
                break
            else:
                log(f"⚠ part{i} short: {size} < {total}; resuming")
        except Exception as e:
            log(f"⚠ part{i}: {type(e).__name__}: {e}; retry in 15s")
            time.sleep(15)

log("ALL 7 PARTS COMPLETE")
Path(__file__).parent.joinpath("data", "done_uk.flag").write_text("ok")
