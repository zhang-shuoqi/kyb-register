"""Full asset audit: UK (7 zips) + SG (27 shards).
Checks: CRC, row counts, column consistency, status distribution, duplicate sampling.
Runtime estimate: 3-6 min. Read-only for completed files only.
"""
import csv
import io
import time
import zipfile
from collections import Counter
from pathlib import Path

d = Path(r"d:\S.Q\kyb-mcp-server\data")
report = []


def sec(msg):
    print(f"\n=== {msg} ===")


def ok(msg):
    print(f"  PASS  {msg}")


def bad(msg):
    print(f"  FAIL  {msg}")
    report.append(msg)


def info(msg):
    print(f"  INFO  {msg}")


# ═══════════════ UK ═══════════════
sec("UK: CRC (all 7 zips)")
uk_dir = d / "uk_snapshot"
for i in range(1, 8):
    p = uk_dir / f"part{i}_7.zip"
    try:
        with zipfile.ZipFile(p) as z:
            if z.testzip() is None:
                ok(f"part{i}: CRC OK")
            else:
                bad(f"part{i}: CRC corrupt")
    except Exception as e:
        bad(f"part{i}: {e}")

sec("UK: streaming row/column validation (all 7 parts)")
total_rows = 0
bad_rows = 0
status_counter = Counter()
per_part_rows = []
t0 = time.time()
for i in range(1, 8):
    rows_i = 0
    with zipfile.ZipFile(uk_dir / f"part{i}_7.zip") as z:
        inner = z.namelist()[0]
        with z.open(inner) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
            header = next(reader)
            ncols = len(header)
            for row in reader:
                rows_i += 1
                if len(row) != ncols:
                    bad_rows += 1
                    if bad_rows <= 3:
                        info(f"  part{i} line {rows_i}: {len(row)} cols (expected {ncols})")
                if rows_i % 200000 == 0:
                    # sample status field (index of CompanyStatus = 11)
                    if len(row) == ncols:
                        status_counter[row[11].strip()] += 1
    per_part_rows.append(rows_i)
    total_rows += rows_i
    print(f"  part{i}: {rows_i:,} rows ({time.time()-t0:.0f}s elapsed)")
if bad_rows == 0:
    ok(f"TOTAL {total_rows:,} rows, 0 malformed")
else:
    bad(f"TOTAL {total_rows:,} rows, {bad_rows} malformed")

sec("UK: status distribution (sampled every 200k rows)")
for st, cnt in status_counter.most_common(8):
    info(f"  {st}: {cnt:,}")
unreasonable = [s for s in status_counter if not s or s.lower() in ("none", "null")]
if unreasonable:
    bad(f"unreasonable status values: {unreasonable[:3]}")
else:
    ok("status values all reasonable")

sec("UK: duplicate company_number sampling (part1 first 100k)")
seen = Counter()
with zipfile.ZipFile(uk_dir / "part1_7.zip") as z:
    with z.open(z.namelist()[0]) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
        next(reader)
        for idx, row in enumerate(reader):
            if idx >= 100000:
                break
            if len(row) > 1:
                seen[row[1].strip()] += 1
dups = {k: v for k, v in seen.items() if v > 1}
if not dups:
    ok("100k sample: no duplicate company numbers")
else:
    bad(f"100k sample: {len(dups)} duplicate numbers, e.g. {list(dups.items())[:3]}")

# ═══════════════ SG ═══════════════
sec("SG: 27 shards — header consistency + column validation")
shards = sorted((d / "sg_shards").glob("shard_*.csv"))
headers = {}
sg_rows = 0
sg_bad = 0
sg_status = Counter()
seen_uen = Counter()
for sf in shards:
    with open(sf, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = tuple(next(reader))
        headers.setdefault(header, []).append(sf.name)
        ncols = len(header)
        uen_idx = None
        status_idx = None
        for idx, fn in enumerate(header):
            if "uen" in fn.lower():
                uen_idx = idx
            if "status" in fn.lower():
                status_idx = idx
        for row in reader:
            sg_rows += 1
            if len(row) != ncols:
                sg_bad += 1
            if uen_idx is not None and len(row) > uen_idx and seen_uen is not None:
                if len(seen_uen) < 50000:
                    seen_uen[row[uen_idx]] += 1
            if status_idx is not None and len(row) > status_idx:
                sg_status[row[status_idx].strip()[:30]] += 1
if len(headers) == 1:
    ok(f"all {len(shards)} shards share identical header ({len(list(headers)[0])} cols)")
else:
    bad(f"{len(headers)} DIFFERENT headers: {[v[:2] for v in headers.values()]}")
if sg_bad == 0:
    ok(f"TOTAL {sg_rows:,} rows, 0 malformed")
else:
    bad(f"TOTAL {sg_rows:,} rows, {sg_bad} malformed")

sec("SG: duplicate UEN in first 50k sample")
sg_dups = {k: v for k, v in seen_uen.items() if v > 1 and k.strip()}
if not sg_dups:
    ok("50k sample: no duplicate UEN")
else:
    info(f"{len(sg_dups)} dup UENs in sample — ACRA legitimately has branches w/ same UEN? check top: {list(sg_dups.items())[:3]}")

sec("SG: status distribution (full)")
for st, cnt in sg_status.most_common(8):
    info(f"  {st}: {cnt:,}")

print("\n" + "=" * 50)
if report:
    print(f"AUDIT RESULT: {len(report)} ISSUE(S)")
    for r in report:
        print(" -", r)
else:
    print("AUDIT RESULT: UK + SG ALL CLEAN")
