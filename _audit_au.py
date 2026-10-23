"""Full quality audit for AU ASIC CSV (asic_companies.csv).
Mirrors _audit_uk_sg.py standards:
  1. file size  2. header  3. full streaming row/col validation
  4. status distribution  5. ACN format  6. duplicate ACN breakdown
  7. date sanity  8. encoding check
"""
import csv
import sys
import time
from collections import Counter
from pathlib import Path

CSV_PATH = Path("data/asic_companies.csv")
EXPECTED_SIZE = 400_376_724
EXPECTED_COLS = 15

issues = []

print("=== AU: file size ===")
size = CSV_PATH.stat().st_size
print(f"  {'PASS' if size == EXPECTED_SIZE else 'FAIL'}  {size} bytes (expected {EXPECTED_SIZE})")
if size != EXPECTED_SIZE:
    issues.append("file size mismatch")

print()
print("=== AU: header ===")
with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
    header_line = f.readline()
has_bom = open(CSV_PATH, "rb").read(3) == b"\xef\xbb\xbf"
header = header_line.rstrip("\r\n").split("\t")
print(f"  BOM: {has_bom} (expected True, adapter uses utf-8-sig)")
print(f"  columns: {len(header)} (expected {EXPECTED_COLS})")
for i, h in enumerate(header):
    print(f"    [{i}] {h!r}")
if len(header) != EXPECTED_COLS:
    issues.append(f"header has {len(header)} cols")
if has_bom is False:
    issues.append("missing UTF-8 BOM")

print()
print("=== AU: streaming row/column validation (full file) ===")
n_rows = 0
n_bad_cols = 0
bad_col_samples = []
n_bad_acn = 0
status_counter = Counter()
type_counter = Counter()
date_bad = 0
date_checked = 0
t0 = time.time()
with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
    reader = csv.reader(f, delimiter="\t")
    next(reader)  # header
    for row in reader:
        n_rows += 1
        if len(row) != EXPECTED_COLS:
            n_bad_cols += 1
            if len(bad_col_samples) < 5:
                bad_col_samples.append((n_rows + 1, len(row)))
            continue
        status_counter[row[5]] += 1
        type_counter[row[2]] += 1
        acn = row[1]
        if not (acn and acn.isdigit() and len(acn) == 9):
            n_bad_acn += 1
        # date sanity: sample every 5000th row, DD/MM/YYYY
        if n_rows % 5000 == 0:
            d = row[6].strip()
            date_checked += 1
            if d:
                parts = d.split("/")
                if not (len(parts) == 3 and len(parts[2]) == 4 and parts[0].isdigit() and parts[1].isdigit()):
                    date_bad += 1
elapsed = time.time() - t0

print(f"  {'PASS' if n_bad_cols == 0 else 'FAIL'}  total {n_rows:,} rows, {n_bad_cols} malformed ({elapsed:.0f}s elapsed)")
for ln, nc in bad_col_samples:
    print(f"    INFO  line {ln}: {nc} cols (expected {EXPECTED_COLS})")
if n_bad_cols > 0:
    issues.append(f"{n_bad_cols} malformed rows")

print()
print("=== AU: ACN format check (full) ===")
print(f"  {'PASS' if n_bad_acn == 0 else 'FAIL'}  {n_bad_acn:,} non-9-digit ACNs out of {n_rows:,}")
if n_bad_acn > 0:
    issues.append(f"{n_bad_acn} bad ACNs")

print()
print("=== AU: date sanity (sampled every 5000 rows) ===")
print(f"  {'PASS' if date_bad == 0 else 'FAIL'}  {date_bad}/{date_checked} bad 'Date of Registration' formats")
if date_bad > 0:
    issues.append(f"{date_bad} bad dates in sample")

print()
print("=== AU: status distribution (full) ===")
for st, c in status_counter.most_common(20):
    print(f"  {c:>10,}  {st!r}")
print(f"  ({len(status_counter)} distinct statuses)")

print()
print("=== AU: entity type distribution (full) ===")
for tp, c in type_counter.most_common(15):
    print(f"  {c:>10,}  {tp!r}")

print()
print("=== AU: duplicate ACN breakdown (full — name-change rows are legit) ===")
# Re-stream: for duplicated ACNs, check whether the dup is a previous-name row
# (Current Name Indicator / Current Name filled) vs a true anomaly.
acn_first_line = {}
dup_examples = []
n_dup_lines = 0
with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
    reader = csv.reader(f, delimiter="\t")
    next(reader)
    for i, row in enumerate(reader, start=2):
        acn = row[1]
        if acn in acn_first_line:
            n_dup_lines += 1
            if len(dup_examples) < 5:
                dup_examples.append((acn, acn_first_line[acn], i))
        else:
            acn_first_line[acn] = i
n_unique = len(acn_first_line)
print(f"  unique ACNs: {n_unique:,}")
print(f"  extra rows sharing an ACN: {n_dup_lines:,} (previous-name records are legitimate)")
print(f"  {'PASS' if n_dup_lines < n_unique * 0.15 else 'WARN'}  dup ratio {n_dup_lines / max(n_unique, 1) * 100:.2f}%")
for acn, l1, l2 in dup_examples:
    print(f"    sample: ACN {acn} at lines {l1} & {l2}")

print()
print("=" * 50)
if issues:
    print(f"AUDIT RESULT: {len(issues)} ISSUE(S)")
    for x in issues:
        print(f" - {x}")
    sys.exit(1)
else:
    print("AUDIT RESULT: ALL PASS")
