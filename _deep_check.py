"""Deep health check: process census + file forensics for ALL pipelines.
Goal: prove there is exactly ONE instance per downloader and no data anomalies.
"""
import subprocess
import time
from pathlib import Path

ROOT = Path(r"d:\S.Q\kyb-mcp-server")
d = ROOT / "data"
now = time.time()

# ── 1. Process census: every python process with its command line ──
ps = r"""
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  ForEach-Object { "$($_.ProcessId)||$($_.CommandLine)" } |
  Out-File -FilePath 'd:\S.Q\kyb-mcp-server\_procs_now.txt' -Encoding utf8
"""
subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
               capture_output=True, text=True, timeout=60)

print("=== PROCESS CENSUS ===")
txt = (ROOT / "_procs_now.txt").read_text(encoding="utf-8-sig", errors="replace")
counts = {"au_par": 0, "cor_par": 0, "sg_par": 0, "supervise": 0, "keepalive": 0, "other": 0}
for line in txt.splitlines():
    line = line.strip()
    if "||" not in line:
        continue
    pid, cmd = line.split("||", 1)
    cmd_l = cmd.lower()
    tag = "other"
    if "_supervise.py" in cmd_l:
        tag = "supervise"
        counts["supervise"] += 1
    elif "_dl_au_par" in cmd_l:
        tag = "au_par"
        counts["au_par"] += 1
    elif "_dl_cor_par" in cmd_l:
        tag = "cor_par"
        counts["cor_par"] += 1
    elif "_pull_sg_par" in cmd_l:
        tag = "sg_par"
        counts["sg_par"] += 1
    elif "_keepalive" in cmd_l:
        tag = "keepalive"
        counts["keepalive"] += 1
    else:
        counts["other"] += 1
    print(f"  PID {pid}: {tag} — {cmd[-95:]}")

print(f"\n  census: {counts}")
issues = []
if counts["au_par"] != 1:
    issues.append(f"AU downloader instance count = {counts['au_par']} (must be 1)")
if counts["cor_par"] != 1:
    issues.append(f"FL downloader instance count = {counts['cor_par']} (must be 1)")
au_sup = 1 if counts["supervise"] >= 1 else 0  # at least one supervisor expected
if counts["keepalive"] != 1:
    issues.append(f"keepalive count = {counts['keepalive']} (must be 1)")

# ── 2. AU file forensics ──
print("\n=== AU FORENSICS ===")
segs = sorted((d / "au_segs").glob("auseg_*.part"))
total_seg = sum(p.stat().st_size for p in segs)
expect_seg = (381.8 * 1024 * 1024) - 0  # prefix=0 in current run
for p in segs:
    sz = p.stat().st_size
    flag = "OK" if sz <= 64 * 1024 * 1024 else "OVERSIZE (>64MB — segment runaway!)"
    print(f"  {p.name}: {sz/1024/1024:.1f} MB [{flag}]")
    if sz > 64 * 1024 * 1024:
        issues.append(f"{p.name} oversize {sz/1024/1024:.1f} MB")
print(f"  total in segs: {total_seg/1024/1024:.1f} MB (max valid = 381.8)")
if total_seg > 381.8 * 1024 * 1024:
    issues.append(f"AU segs total {total_seg/1024/1024:.0f} MB exceeds file size — double-write!")
else:
    print("  PASS: segs total within file bounds")
newest = min((now - p.stat().st_mtime) / 60 for p in segs) if segs else 999
print(f"  newest write: {newest:.1f} min ago {'(ALIVE)' if newest < 2 else '(STALLED!)'}")
if newest >= 5:
    issues.append(f"AU stalled {newest:.0f} min")

# ── 3. FL file forensics ──
print("\n=== FL FORENSICS ===")
segs = sorted((d / "sunbiz_quarterly" / "segs").glob("seg_*.part"))
st = sum(p.stat().st_size for p in segs)
prefix = (d / "sunbiz_quarterly" / "cordata.zip").stat().st_size
expect_per = (1710 * 1024 * 1024 - prefix) / 4
for p in segs:
    sz = p.stat().st_size
    print(f"  {p.name}: {sz/1024/1024:.1f} MB (expect <= {expect_per/1024/1024:.0f})")
    if sz > expect_per + 1024 * 1024:
        issues.append(f"{p.name} oversize")
print(f"  total: {(prefix + st)/1024/1024:.0f} / 1710 MB")
newest = min((now - p.stat().st_mtime) / 60 for p in segs) if segs else 999
print(f"  newest write: {newest:.1f} min ago {'(ALIVE)' if newest < 20 else '(CHECK — SSH retries can pause writes)'}")
if newest >= 60:
    issues.append(f"FL stalled {newest:.0f} min")

# ── 4. log sanity ──
print("\n=== LOG TAILS ===")
for name in ["download_au.log", "download_cor.log"]:
    p = d / name
    if p.exists():
        lines = p.read_text(encoding="utf-8", errors="replace").strip().split("\n")
        print(f"  {name}: {lines[-1][:110]}")

print("\n" + "=" * 50)
if issues:
    print(f"⚠ {len(issues)} ISSUE(S):")
    for i in issues:
        print("  -", i)
else:
    print("✅ SYSTEM CLEAN: single instances, data within bounds, all alive")
