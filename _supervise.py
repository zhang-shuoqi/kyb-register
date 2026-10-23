"""Generic supervisor: keep restarting a downloader until its done-flag appears.
Usage: python _supervise.py <script_path> <done_flag_path>
"""
import subprocess
import sys
import time
from pathlib import Path

script, flag = sys.argv[1], sys.argv[2]
name = Path(script).stem

while not Path(flag).exists():
    print(f"[{time.strftime('%H:%M:%S')}] supervising {name}", flush=True)
    subprocess.run([sys.executable, script])
    if Path(flag).exists():
        break
    print(f"[{time.strftime('%H:%M:%S')}] {name} died, restarting in 30s", flush=True)
    time.sleep(30)

print(f"[{time.strftime('%H:%M:%S')}] {name} FINISHED (flag found)", flush=True)
