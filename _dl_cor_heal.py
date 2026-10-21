"""Self-healing SFTP downloader: auto-reconnect + resume until file complete.
Runs as an independent process (Start-Process), survives session close.
Log: data/download_cor.log
"""
import paramiko
import time
from pathlib import Path

OUT = Path(__file__).parent / "data" / "sunbiz_quarterly" / "cordata.zip"
LOG = Path(__file__).parent / "data" / "download_cor.log"
REMOTE = "doc/Quarterly/Cor/cordata.zip"
HOST, USER, PASS = "sftp.floridados.gov", "Public", "PubAccess1845!"


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


attempt = 0
t_start = time.time()
while True:
    attempt += 1
    try:
        transport = paramiko.Transport((HOST, 22))
        transport.connect(username=USER, password=PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)
        total = sftp.stat(REMOTE).st_size
        resume = OUT.stat().st_size if OUT.exists() else 0

        if resume >= total:
            log(f"✅ COMPLETE: {total/1024/1024:.0f} MB after {attempt} attempts, {time.time()-t_start:.0f}s total")
            sftp.close(); transport.close()
            break

        log(f"attempt {attempt}: {resume/1024/1024:.0f}/{total/1024/1024:.0f} MB, resuming...")
        with sftp.open(REMOTE, "rb") as rf:
            rf.seek(resume)
            with open(OUT, "ab") as lf:
                while True:
                    chunk = rf.read(1024 * 512)
                    if not chunk:
                        break
                    lf.write(chunk)
        sftp.close(); transport.close()
        # 循环回去检查是否完成
    except Exception as e:
        log(f"⚠ attempt {attempt} failed: {type(e).__name__}: {e}; retry in 15s")
        time.sleep(15)
    finally:
        try:
            sftp.close(); transport.close()
        except Exception:
            pass
