"""Restart AU only (supervisor handles the lock check now)."""
import subprocess
import time
from pathlib import Path

ROOT = Path(r"d:\S.Q\kyb-mcp-server")
EXE = r"C:\Users\31720\AppData\Local\Python\bin\python.exe"


def ps_run(text):
    (ROOT / "_tmp.ps1").write_text(text)
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(ROOT / "_tmp.ps1")],
        capture_output=True, text=True)


# ensure no AU downloader or supervisor is running
for attempt in range(3):
    r = ps_run("""
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*_dl_au_par*' -or ($_.CommandLine -like '*_supervise.py*' -and $_.CommandLine -like '*done_au.flag*') } |
  ForEach-Object { taskkill /F /T /PID $_.ProcessId; Write-Output ("killed " + $_.ProcessId) }
""")
    out = (r.stdout or "").strip()
    print(f"kill round {attempt+1}: {out or '(none left)'}")
    if "killed" not in out:
        break
    time.sleep(2)

# start AU supervisor (which starts the downloader; downloader checks for peers)
r = ps_run(f"""
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = '{EXE} "{ROOT}\\_supervise.py" "{ROOT}\\_dl_au_par.py" "{ROOT}\\data\\done_au.flag"' }} |
  Select-Object -ExpandProperty ReturnValue
""")
print("AU supervisor return:", (r.stdout or "").strip())
time.sleep(45)

d = ROOT / "data"
au_log = d / "download_au.log"
if au_log.exists():
    for l in au_log.read_text().strip().split("\n")[-2:]:
        print("  AU:", l[:110])
segs = sorted((d / "au_segs").glob("auseg_*.part"))
st = sum(p.stat().st_size for p in segs)
newest = min((time.time() - p.stat().st_mtime) / 60 for p in segs) if segs else 99
print(f"AU progress: {st/1024/1024:.1f} MB in segs, newest write {newest:.1f} min ago")
