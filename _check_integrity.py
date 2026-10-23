"""Integrity check: zips (header magic) + SG CSV (row/column consistency)."""
import csv
import zipfile
from pathlib import Path

DATA = Path(__file__).parent / "data"
issues = []

# 1. 下载中的 zip：头部魔数检查（PK\x03\x04 = 合法 zip 开头）
print("=== zip header magic check ===")
for z in [DATA / "sunbiz_quarterly" / "cordata.zip",
          DATA / "sunbiz_quarterly" / "Genfile.zip",
          DATA / "uk_snapshot" / "part1_7.zip"]:
    if not z.exists():
        print(f"  [SKIP] {z.name}: not found")
        continue
    with open(z, "rb") as f:
        head = f.read(4)
    ok = head == b"PK\x03\x04"
    size_mb = z.stat().st_size / 1024 / 1024
    mark = "OK " if ok else "BAD"
    print(f"  [{mark}] {z.name}: starts with {head!r}, {size_mb:.1f} MB")
    if not ok:
        issues.append(f"{z.name}: bad magic {head!r}")

# 2. Genfile.zip：完整 CRC 校验（已完成的文件）
print("\n=== Genfile.zip full CRC test ===")
try:
    with zipfile.ZipFile(DATA / "sunbiz_quarterly" / "Genfile.zip") as z:
        bad = z.testzip()
        n = len(z.namelist())
        print(f"  {'OK' if bad is None else 'CORRUPT: ' + bad} — {n} file(s) inside")
        if bad:
            issues.append(f"Genfile.zip corrupt entry: {bad}")
except Exception as e:
    print(f"  FAIL: {e}")
    issues.append(f"Genfile.zip: {e}")

# 3. SG sg_full.csv：行数 + 每行列数一致性 + 内容抽查
print("\n=== sg_full.csv structural check ===")
csvf = DATA / "sg_full.csv"
if csvf.exists():
    with open(csvf, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        ncols = len(header)
        rows = 0
        bad_cols = 0
        last_row = None
        for row in reader:
            rows += 1
            if len(row) != ncols:
                bad_cols += 1
            last_row = row
    print(f"  header columns: {ncols}")
    print(f"  data rows: {rows}")
    print(f"  rows with wrong column count: {bad_cols}")
    print(f"  sample last row: {[str(c)[:30] for c in (last_row or [])][:6]}")
    if bad_cols:
        issues.append(f"sg_full.csv: {bad_cols} malformed rows")
    if rows == 0:
        issues.append("sg_full.csv: zero rows")
else:
    print("  [SKIP] not found")

# 4. sunbiz 文本文件编码检查（latin-1 可读性）
print("\n=== FLRreadme.txt read check ===")
try:
    txt = (DATA / "sunbiz_quarterly" / "FLRreadme.txt").read_text(encoding="latin-1")
    print(f"  OK, {len(txt)} chars, starts: {txt[:40]!r}")
except Exception as e:
    print(f"  FAIL: {e}")
    issues.append(f"FLRreadme.txt: {e}")

# 5. 进度文件 JSON 合法性
print("\n=== progress files ===")
for p in [DATA / "sg_progress.json"]:
    if p.exists():
        try:
            import json
            json.loads(p.read_text())
            print(f"  OK {p.name}")
        except Exception as e:
            print(f"  CORRUPT {p.name}: {e}")
            issues.append(f"{p.name}: {e}")
    else:
        print(f"  [absent] {p.name}")

print("\n" + "=" * 40)
if issues:
    print(f"❌ {len(issues)} ISSUE(S):")
    for i in issues:
        print("  -", i)
else:
    print("✅ ALL CHECKS PASSED — no corruption detected")
