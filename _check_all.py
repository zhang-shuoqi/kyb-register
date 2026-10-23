"""Full pipeline progress check."""
import time
from pathlib import Path

d = Path(r"d:\S.Q\kyb-mcp-server\data")
now = time.time()


def age(p):
    return (now - p.stat().st_mtime) / 60


print(f"now: {time.strftime('%H:%M:%S')}")
print()
print("=== flags ===")
for f in ["done_uk.flag", "done_au.flag", "done_sg.flag", "done_fl.flag"]:
    print(f"  {f}: {(d / f).exists()}")

print()
print("=== UK (done) ===")
uk_parts = sorted((d / "uk_snapshot").glob("part*.zip"))
total = sum(p.stat().st_size for p in uk_parts)
print(f"  7 parts, {total/1024/1024:.0f} MB on disk")

print()
print("=== AU (6 segments) ===")
au_main = d / "asic_companies.csv"
print(f"  prefix: {au_main.stat().st_size/1024/1024:.1f} MB (age {age(au_main):.0f} min)")
segs = sorted((d / "au_segs").glob("auseg_*.part"))
st = sum(p.stat().st_size for p in segs)
newest = max(age(p) for p in segs) if segs else 999
print(f"  {len(segs)} segs, {st/1024/1024:.1f} MB, oldest write {newest:.0f} min ago")
print(f"  total: {(au_main.stat().st_size + st)/1024/1024:.1f} / 381.8 MB ({(au_main.stat().st_size+st)/400376724*100:.0f}%)")

print()
print("=== SG (27 shards) ===")
shards = sorted((d / "sg_shards").glob("shard_*.csv"))
st = sum(p.stat().st_size for p in shards)
newest = max(age(p) for p in shards) if shards else 999
done_cnt = 0
prog = d / "sg_progress_par.json"
if prog.exists():
    import json
    pj = json.loads(prog.read_text())
    done_cnt = sum(1 for v in pj.values() if v.get("done"))
print(f"  {len(shards)} shards started, {done_cnt} complete, {st/1024/1024:.1f} MB, oldest write {newest:.0f} min ago")

print()
print("=== FL (4 segments) ===")
segs = sorted((d / "sunbiz_quarterly" / "segs").glob("seg_*.part"))
st = sum(p.stat().st_size for p in segs)
prefix = (d / "sunbiz_quarterly" / "cordata.zip").stat().st_size
newest = max(age(p) for p in segs) if segs else 999
print(f"  prefix {prefix/1024/1024:.0f} MB + {len(segs)} segs {st/1024/1024:.1f} MB, oldest write {newest:.0f} min ago")
print(f"  total: {(prefix+st)/1024/1024:.0f} / 1710 MB ({(prefix+st)/1710*1024/1024*100:.0f}%)")

print()
print("=== keepalive ===")
ka = d / "keepalive.log"
if ka.exists():
    lines = ka.read_text().strip().split("\n")
    print(f"  last entry: {lines[-1]}")
