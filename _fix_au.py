"""Wipe corrupted AU artifacts, restart clean AU parallel download."""
import subprocess
import time
from pathlib import Path

# 1. kill AU processes via ps1 script file (avoid inline quote hell)
ps = r"""
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*_dl_au*' } |
  ForEach-Object { Write-Output ("killed " + $_.ProcessId); Stop-Process -Id $_.Id -Force }
"""
Path(r"d:\S.Q\kyb-mcp-server\_kill_au.ps1").write_text(ps)
r = subprocess.run(
    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
     "-File", r"d:\S.Q\kyb-mcp-server\_kill_au.ps1"],
    capture_output=True, text=True)
print("kill:", (r.stdout or "").strip() or "(none running)")

# 1.5 second kill round (kill all until none left)
for attempt in range(3):
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", r"d:\S.Q\kyb-mcp-server\_kill_au.ps1"],
        capture_output=True, text=True)
    out = (r.stdout or "").strip()
    print(f"kill round {attempt+1}: {out or '(none left)'}")
    if not out:
        break
    time.sleep(2)

# 2. wipe corrupted artifacts (retry on locked files)
d = Path(r"d:\S.Q\kyb-mcp-server\data")
for attempt in range(3):
    try:
        for p in (d / "au_segs").glob("auseg_*.part"):
            p.unlink()
        (d / "asic_companies.csv").unlink(missing_ok=True)
        (d / "download_au.log").unlink(missing_ok=True)
        print("AU artifacts wiped")
        break
    except PermissionError as e:
        print(f"still locked ({e.filename}), retry in 3s")
        time.sleep(3)

# 3. restart clean parallel AU
cmd = r'C:\Users\31720\AppData\Local\Python\bin\python.exe "d:\S.Q\kyb-mcp-server\_dl_au_par.py"'
r2 = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command",
     f"Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = '{cmd}' }} | Select-Object -ExpandProperty ReturnValue"],
    capture_output=True, text=True)
print("restart return:", r2.stdout.strip())

# 4. status of FL + SG
time.sleep(5)
segs = sorted((d / "sunbiz_quarterly" / "segs").glob("seg_*.part"))
st = sum(p.stat().st_size for p in segs)
prefix = (d / "sunbiz_quarterly" / "cordata.zip").stat().st_size
pct = (prefix + st) / (1710 * 1024 * 1024) * 100
print(f"FL: {(prefix + st)/1024/1024:.0f} / 1710 MB ({pct:.0f}%)")
shards = sorted((d / "sg_shards").glob("shard_*.csv"))
st = sum(p.stat().st_size for p in shards)
print(f"SG: {len(shards)} shards, {st/1024/1024:.1f} MB (flag=True)")
