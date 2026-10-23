"""Morning full status check."""
import time
from pathlib import Path

d = Path(r"d:\S.Q\kyb-mcp-server\data")
now = time.time()

print(f"now: {time.strftime('%H:%M:%S')}\n")

flags = {f: (d / f).exists() for f in ["done_uk.flag", "done_sg.flag", "done_au.flag", "done_fl.flag"]}
for f, v in flags.items():
    print(f"{'✅' if v else '⏳'} {f}: {v}")

print()
au_log = d / "download_au.log"
if au_log.exists():
    lines = au_log.read_text().strip().split("\n")
    print("AU log tail:")
    for l in lines[-4:]:
        print("  " + l[:110])
segs = sorted((d / "au_segs").glob("auseg_*.part"))
st = sum(p.stat().st_size for p in segs)
prefix = (d / "asic_companies.csv").stat().st_size if (d / "asic_companies.csv").exists() else 0
if segs or prefix:
    newest = min((now - p.stat().st_mtime) / 60 for p in segs) if segs else 99
    print(f"  total: {(prefix + st)/1024/1024:.0f} / 381.8 MB, newest write {newest:.1f} min ago")

print()
fl_log = d / "download_cor.log"
if fl_log.exists():
    lines = fl_log.read_text(encoding="utf-8", errors="replace").strip().split("\n")
    print("FL log tail:")
    for l in lines[-2:]:
        print("  " + l[:110])
segs = sorted((d / "sunbiz_quarterly" / "segs").glob("seg_*.part"))
st = sum(p.stat().st_size for p in segs)
prefix = (d / "sunbiz_quarterly" / "cordata.zip").stat().st_size
if segs or prefix:
    newest = min((now - p.stat().st_mtime) / 60 for p in segs) if segs else 99
    print(f"  total: {(prefix + st)/1024/1024:.0f} / 1710 MB, newest write {newest:.1f} min ago")
