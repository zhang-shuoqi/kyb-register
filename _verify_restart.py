from pathlib import Path
import time

d = Path(r"d:\S.Q\kyb-mcp-server\data")
print("UK log tail:")
lines = (d / "download_uk.log").read_text().strip().split("\n")
for l in lines[-4:]:
    print("  " + l)
au_log = d / "download_au.log"
print("AU log exists:", au_log.exists())
if au_log.exists():
    for l in au_log.read_text().strip().split("\n")[-3:]:
        print("  " + l)
au = d / "asic_companies.csv"
if au.exists():
    mt = time.strftime("%H:%M:%S", time.localtime(au.stat().st_mtime))
    print(f"AU csv: {au.stat().st_size/1024/1024:.1f} MB @ {mt}")
