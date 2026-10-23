"""FL cordata.zip FULL audit (runs under Python 3.10 + zipfile_deflate64).
Single streaming pass over 10 inner files (~18.7 GB decoded, ~13M lines):
  - CRC: ZipExtFile validates at EOF (BadZipFile on mismatch)
  - line length == 1440
  - doc-number + name parse
  - status / entity-type distributions
  - filing-date sanity
  - global doc-number uniqueness
"""
import io
import re
import sys
import time
import zipfile_deflate64 as zipfile
from collections import Counter

Z = r"d:\S.Q\kyb-mcp-server\data\sunbiz_quarterly\cordata.zip"
DOC_RE = re.compile(r"^(?:[A-Z]\d{10,11}|[A-Z]?\d{5,6})")

issues = []
n_lines = 0
n_badlen = 0
n_docfail = 0
doc_fail_samples = []
status = Counter()
etype = Counter()
n_date_checked = 0
n_date_bad = 0
bad_date_samples = []
docs = set()
n_dup_docs = 0
active_samples = []
t0 = time.time()

with zipfile.ZipFile(Z) as z:
    names = sorted(z.namelist())
    for name in names:
        f_badlen = 0
        with z.open(name) as f:
            tf = io.TextIOWrapper(f, encoding="latin-1")
            for line in tf:
                n_lines += 1
                line = line.rstrip("\r\n")
                if len(line) != 1440:
                    n_badlen += 1
                    f_badlen += 1
                    continue
                head = line[:180]
                m = DOC_RE.match(head)
                if not m:
                    n_docfail += 1
                    if len(doc_fail_samples) < 3:
                        doc_fail_samples.append(line[:60])
                    continue
                doc = m.group(0)
                if doc in docs:
                    n_dup_docs += 1
                else:
                    docs.add(doc)
                status[line[204]] += 1
                etype[line[205:209]] += 1
                if line[204] == "A" and line[480:489].strip() and len(active_samples) < 3:
                    active_samples.append((doc, head[m.end():m.end()+60].rstrip(), doc, line[480:489], line[472:480]))
                if n_lines % 5000 == 0:
                    d = line[472:480]
                    n_date_checked += 1
                    if d and d != "00000000" and not (len(d) == 8 and d.isdigit()):
                        n_date_bad += 1
                        if len(bad_date_samples) < 3:
                            bad_date_samples.append((n_lines, line[460:500]))
        # reaching here without BadZipFile == CRC OK for this member
        print(f"{name}: rows so far {n_lines:,} (badlen this file {f_badlen}) "
              f"[{time.time()-t0:.0f}s]", flush=True)

elapsed = time.time() - t0
print()
print("=== FL cordata.zip audit summary ===")
print(f"total lines:        {n_lines:,}")
print(f"bad-length lines:   {n_badlen:,}  {'PASS' if n_badlen == 0 else 'FAIL'}")
print(f"doc-parse failures: {n_docfail:,}  ({n_docfail/max(n_lines,1)*100:.3f}%)  {'PASS' if n_docfail/max(n_lines,1) < 0.001 else 'WARN'}")
for s in doc_fail_samples:
    print(f"    sample: {s!r}")
print(f"global dup docs:    {n_dup_docs:,}  {'PASS' if n_dup_docs == 0 else 'WARN'}")
print(f"unique docs:        {len(docs):,}")
print(f"date bad (sampled): {n_date_bad}/{n_date_checked}  {'PASS' if n_date_bad == 0 else 'FAIL'}")
for ln, seg in bad_date_samples:
    print(f"    bad-date line {ln} [460:500]: {seg!r}")
print()
print("active samples for cross-check:")
for doc, name, _d, fei, regdate in active_samples:
    print(f"  doc={doc}  fei={fei}  filing={regdate}  name={name!r}")
print()
print("status distribution [204]:")
for k, v in status.most_common(15):
    print(f"  {v:>10,}  {k!r}")
print("entity type distribution [205:209] (top 15):")
for k, v in etype.most_common(15):
    print(f"  {v:>10,}  {k!r}")
print(f"\nelapsed: {elapsed:.0f}s")
if n_badlen == 0 and n_date_bad == 0:
    print("STRUCTURAL AUDIT: PASS")
else:
    print("STRUCTURAL AUDIT: ISSUES FOUND")
    issues.append("structure")
