"""Precisely locate field boundaries in Genfile."""
import zipfile
import re
from collections import Counter

z = zipfile.ZipFile(r"d:\S.Q\kyb-mcp-server\data\sunbiz_quarterly\Genfile.zip")
lines = []
with z.open(z.namelist()[0]) as f:
    for i, raw in enumerate(f):
        lines.append(raw.decode("latin-1").rstrip("\r\n"))
        if i >= 500:
            break

# 严格日期锚点（MMDDYYYY，月/日合法）
date_re = re.compile(r"(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{4}")
pos_counter = Counter()
for l in lines:
    m = date_re.search(l, 150)  # 从 150 列之后找（跳过名称区）
    if m:
        pos_counter[m.start()] += 1
print("=== filing date position candidates ===")
for pos, cnt in pos_counter.most_common(4):
    print(f"  col {pos}: {cnt}/{len(lines)}")

# 取第一行的精确切片（以日期位置为准）
l = lines[0]
dpos = date_re.search(l, 150).start()
print(f"\nline1 date at col {dpos}")
print(f"  [{dpos-3}:{dpos}]   {l[dpos-3:dpos]!r}  <- status code before date?")
print(f"  [{dpos}:{dpos+8}]  {l[dpos:dpos+8]!r}  <- filing date")
print(f"  [{dpos+8}:{dpos+16}] {l[dpos+8:dpos+16]!r}  <- diss date?")
print(f"  [{dpos+16}:{dpos+24}] {l[dpos+16:dpos+24]!r}")
print(f"  [{dpos+24}:{dpos+33}] {l[dpos+24:dpos+33]!r}  <- FEI/EIN?")
print(f"  [{dpos+33}:{dpos+35}] {l[dpos+33:dpos+35]!r}  <- state?")
print(f"  [{dpos+35}:{dpos+95}] {l[dpos+35:dpos+95].strip()!r}  <- addr1")
print(f"  [{dpos+95}:{dpos+125}] {l[dpos+95:dpos+125].strip()!r}  <- city")
print(f"  [{dpos+125}:{dpos+133}] {l[dpos+125:dpos+133].strip()!r}  <- state+zip")

# 名称区精确边界：找名称结束的位置（第一个连续 10 空格）
name_end_re = re.compile(r"  {10,}")
m = name_end_re.search(l, 13)
print(f"\nname area: [13:{m.start()}] = {l[13:m.start()]!r}")
print(f"name field width guess: {m.start()-13}")

# 759 行后半部分（agent/officer 区域）切片
print("\n=== tail slices (line1, cols 400-759) ===")
for a, b, tag in [(400, 460, "officer?"), (460, 520, "?"), (520, 580, "?"), (580, 640, "?"), (640, 700, "?"), (700, 759, "?")]:
    seg = l[a:b]
    if seg.strip():
        print(f"  [{a}:{b}] {seg.strip()!r}")

# 前缀类型分布
print("\n=== entity type prefix (first 3 chars) distribution ===")
print(Counter(l[:3] for l in lines).most_common(5))
print("=== status char (col 12) distribution ===")
print(Counter(l[12] for l in lines).most_common(8))
