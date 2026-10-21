"""Download cordata.zip (1.7GB) with resume + progress log."""
import paramiko
import os
import time
from pathlib import Path

OUT = Path(__file__).parent / "data" / "sunbiz_quarterly" / "cordata.zip"
OUT.parent.mkdir(parents=True, exist_ok=True)
REMOTE = "doc/Quarterly/Cor/cordata.zip"

t0 = time.time()
transport = paramiko.Transport(("sftp.floridados.gov", 22))
transport.connect(username="Public", password="PubAccess1845!")
sftp = paramiko.SFTPClient.from_transport(transport)

total = sftp.stat(REMOTE).st_size
resume_from = OUT.stat().st_size if OUT.exists() else 0
print(f"remote size: {total/1024/1024:.0f} MB, local: {resume_from/1024/1024:.0f} MB", flush=True)

mode = "ab" if 0 < resume_from < total else "wb"
with sftp.open(REMOTE, "rb") as rf:
    if resume_from:
        rf.seek(resume_from)
    with open(OUT, mode) as lf:
        done = resume_from
        last_log = 0
        while True:
            chunk = rf.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            lf.write(chunk)
            done += len(chunk)
            if done - last_log >= 100 * 1024 * 1024:  # log every 100MB
                pct = done / total * 100
                speed = (done - resume_from) / 1024 / 1024 / (time.time() - t0)
                print(f"  {pct:.0f}% ({done/1024/1024:.0f} MB, {speed:.1f} MB/s)", flush=True)
                last_log = done

sftp.close()
transport.close()
final = OUT.stat().st_size
print(f"✅ done: {final/1024/1024:.0f} MB in {time.time()-t0:.0f}s, expected {total/1024/1024:.0f} MB", flush=True)
if final != total:
    print("❌ SIZE MISMATCH — rerun this script to resume", flush=True)
