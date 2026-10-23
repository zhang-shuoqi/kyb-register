"""Kill AU+FL downloaders, wipe AU, restart both with supervisors."""
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


# 1. kill AU + FL downloaders (loop)
for attempt in range(4):
    r = ps_run("""
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*_dl_au_par*' -or $_.CommandLine -like '*_dl_cor_par*' } |
  ForEach-Object { taskkill /F /T /PID $_.ProcessId; Write-Output ("killed " + $_.ProcessId) }
""")
    out = (r.stdout or "").strip()
    print(f"kill round {attempt+1}: {out or '(none left)'}")
    if "killed" not in out:
        break
    time.sleep(2)

# 2. wipe AU artifacts
d = ROOT / "data"
for attempt in range(3):
    try:
        for p in (d / "au_segs").glob("auseg_*.part"):
            p.unlink()
        (d / "asic_companies.csv").unlink(missing_ok=True)
        (d / "download_au.log").unlink(missing_ok=True)
        print("AU artifacts wiped")
        break
    except PermissionError:
        print("locked, retry 3s")
        time.sleep(3)

# 3. restart AU (with startup lock inside) + supervisor
r1 = ps_run(f"""
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = '{EXE} "{ROOT}\\_supervise.py" "{ROOT}\\_dl_au_par.py" "{ROOT}\\data\\done_au.flag"' }} |
  Select-Object -ExpandProperty ReturnValue
""")
print("AU supervisor restart return:", (r1.stdout or "").strip())

# 4. restart FL with supervisor (it had none — that's why it died silently)
r2 = ps_run(f"""
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = '{EXE} "{ROOT}\\_supervise.py" "{ROOT}\\_dl_cor_par.py" "{ROOT}\\data\\done_fl.flag"' }} |
  Select-Object -ExpandProperty ReturnValue
""")
print("FL supervisor restart return:", (r2.stdout or "").strip())

time.sleep(30)
# 5. verify both
au_log = d / "download_au.log"
if au_log.exists():
    for l in au_log.read_text().strip().split("\n")[-2:]:
        print("  AU:", l[:100])
segs = sorted((d / "au_segs").glob("auseg_*.part"))
st = sum(p.stat().st_size for p in segs)
print(f"AU progress: {st/1024/1024:.1f} MB in segments")
fl_log = d / "download_cor.log"
if fl_log.exists():
    for l in fl_log.read_text(encoding="utf-8", errors="replace").strip().split("\n")[-2:]:
        print("  FL:", l[:100])
