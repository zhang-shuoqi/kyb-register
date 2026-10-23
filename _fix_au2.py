"""One-shot AU fix: kill ALL instances, wipe, patch downloader with startup lock, restart ONCE."""
import subprocess
import time
from pathlib import Path

ROOT = Path(r"d:\S.Q\kyb-mcp-server")


def ps_run(ps_text):
    Path(ROOT / "_tmp.ps1").write_text(ps_text)
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(ROOT / "_tmp.ps1")],
        capture_output=True, text=True)


# 1. kill ALL AU instances (loop until none)
for attempt in range(5):
    r = ps_run("""
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*_dl_au*' } |
  ForEach-Object { Write-Output ("killing " + $_.ProcessId); Stop-Process -Id $_.Id -Force }
""")
    out = (r.stdout or "").strip()
    print(f"kill round {attempt+1}: {out or '(none left)'}")
    if not out:
        break
    time.sleep(2)

# also taskkill any zombies
r = ps_run("""
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*_dl_au*' } |
  ForEach-Object { taskkill /F /T /PID $_.ProcessId }
""")
print("taskkill sweep:", (r.stdout or "").strip() or "(nothing)")

# 2. wipe
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

# 3. patch _dl_au_par.py with startup lock
au_file = ROOT / "_dl_au_par.py"
src = au_file.read_text(encoding="utf-8")
if "already_running" not in src:
    lock_code = '''
def already_running():
    """Return True if another _dl_au_par.py instance is alive (besides self)."""
    import subprocess as sp
    ps = ("Get-CimInstance Win32_Process -Filter \\"Name='python.exe'\\" | "
          "Where-Object { $_.CommandLine -like '*_dl_au_par.py*' -and $_.ProcessId -ne $PID } | "
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
'''
    # replace the trailing __main__ block
    old_block = 'if __name__ == "__main__":\n    main()\n'
    if old_block in src:
        src = src.replace(old_block, lock_code)
    else:
        src = src.rstrip() + "\n" + lock_code
    au_file.write_text(src, encoding="utf-8")
    print("startup-lock patched into _dl_au_par.py")
else:
    print("lock already present")

# 4. restart ONCE
r = ps_run(f"""
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = 'C:\\Users\\31720\\AppData\\Local\\Python\\bin\\python.exe "d:\\S.Q\\kyb-mcp-server\\_dl_au_par.py"' }} |
  Select-Object -ExpandProperty ReturnValue
""")
print("restart return:", (r.stdout or "").strip())

# 5. check FL health (log tail)
fl_log = d / "download_cor.log"
if fl_log.exists():
    lines = fl_log.read_text(encoding="utf-8", errors="replace").strip().split("\n")
    print("FL log tail:", lines[-1][:100])
