# -*- coding: utf-8 -*-
"""FL Sunbiz cordata -> kyb.db

!!! 必须在 Python 3.10 + zipfile_deflate64 下运行：py -V:3.10 ingest_fl.py !!!

源：data/sunbiz_quarterly/cordata.zip（10 个内层文件，Deflate64，latin-1，1440 定宽）
锚点（2026-10-23 官方 file-structure 页实锤 + 1299 万行全量审计）：
  https://dos.fl.gov/sunbiz/other-services/data-downloads/corporate-data-file/file-structure/
  1-based 起始/长度 -> 0-based 切片：
  [0:12]   Corporation Number（变长，DOC_RE 解析；8 条已知格式变体走 fallback）
  [12:204] Corporation Name
  [204]    Status（A/I）
  [205:220] Filing Type（15字符：FLAL/FORL/DOMP/DOMNP/FORP/FORNP/DOMLP/FORLP/NPREG/TRUST/AGENT）
  [220:262] Address 1   [262:304] Address 2
  [304:332] City        [332:334] State  [334:344] Zip（含 ZIP+4）
  [472:480] File Date MMDDYYYY（'00000000'=空）
  [544:586] Registered Agent Name
  [480:494] FEI、[495:503] Last Transaction Date 等不入主表，原文在 raw。
  旧笔记 [462:470]"注册日期"实为官方 Mail Zip 字段（[460:470]），已废弃。

用法：py -V:3.10 ingest_fl.py [--limit N]
"""
from __future__ import annotations

import argparse
import io
import re
import sys

sys.path.insert(0, r"C:\Users\31720\AppData\Local\Python\pythoncore-3.10-64\Lib\site-packages")
sys.path.insert(0, r"d:\S.Q\kyb-mcp-server\ingest")
import zipfile_deflate64 as zipfile  # noqa: E402  (整包替换 API，支持 Deflate64)

from common import (BATCH, FL_ZIP, INSERT_COMPANY, Progress,  # noqa: E402
                    connect, dump_json, file_date, init_schema,
                    norm_date_mdy8, out_safe, stats)

out_safe()

DOC_RE = re.compile(r"^(?:[A-Z]\d{10,11}|[A-Z]?\d{5,6})")


def seg(line: str, a: int, b: int) -> str:
    return line[a:b].strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print(f"FL ingest -> limit={args.limit or 'ALL'}")
    print(f"python={sys.version.split()[0]} exe={sys.executable}")
    retrieved = file_date(FL_ZIP) or "2026-10-23"

    conn = connect()
    init_schema(conn)

    prog = Progress("FL", report_every=1_000_000)
    n_company = 0
    n_conflict = 0
    n_badlen = 0
    n_docfail = 0
    docfail_samples: list[str] = []
    n_bad_date = 0
    buf: list[tuple] = []

    def flush() -> None:
        nonlocal n_company, n_conflict
        if buf:
            n = len(buf)
            c0 = conn.total_changes
            conn.executemany(INSERT_COMPANY, buf)
            got = conn.total_changes - c0
            n_company += got
            n_conflict += n - got
            buf.clear()
        conn.commit()

    with zipfile.ZipFile(FL_ZIP) as z:
        names = sorted(z.namelist())
        print(f"members: {names}")
        for name in names:
            with z.open(name) as f:
                tf = io.TextIOWrapper(f, encoding="latin-1")
                for line in tf:
                    prog.tick()
                    line = line.rstrip("\r\n")
                    if len(line) != 1440:
                        n_badlen += 1
                        continue
                    m = DOC_RE.match(line)
                    if m:
                        number = m.group(0)
                        name_s = " ".join(line[m.end():204].split())
                    else:
                        # 8 条已知格式变体（单数字/小写前缀）兜底：不丢行，粗糙解析+原文在 raw
                        n_docfail += 1
                        if len(docfail_samples) < 5:
                            docfail_samples.append(line[:60])
                        number = line[:12].strip().upper()
                        name_s = " ".join(line[12:204].split())
                    if not number or not name_s:
                        print(f"WARN empty doc/name at row {prog.n}: {line[:60]!r}")
                        continue
                    filing = norm_date_mdy8(line[472:480])
                    if not filing and seg(line, 472, 480) not in ("", "00000000"):
                        n_bad_date += 1
                    addr = ", ".join(x for x in (
                        seg(line, 220, 262), seg(line, 262, 304),
                        seg(line, 304, 332),
                        (seg(line, 332, 334) + " " + seg(line, 334, 344)).strip(),
                    ) if x)
                    agent_name = seg(line, 544, 586)
                    buf.append((
                        "us_fl", number, name_s,
                        line[204],
                        seg(line, 205, 220),
                        "",  # FL 无行业码字段
                        filing, "", addr,
                        agent_name,
                        f"https://search.sunbiz.org/ (Document {number})",
                        retrieved,
                        dump_json({"doc": number, "name": name_s, "status": line[204],
                                   "etype": seg(line, 205, 220), "filing_date": filing,
                                   "line": line}),
                    ))
                    if len(buf) >= BATCH:
                        flush()
                    if args.limit and prog.n >= args.limit:
                        break
            if args.limit and prog.n >= args.limit:
                break
    flush()
    prog.done()
    stats(conn, "FL", prog.n, n_company, n_conflict,
          {"bad-length lines (skipped)": f"{n_badlen:,}",
           "doc-parse fallback rows": f"{n_docfail:,}" + (f" samples={docfail_samples}" if docfail_samples else ""),
           "bad filing dates": str(n_bad_date),
           "expected": f"{12_987_601:,}"})
    conn.close()


if __name__ == "__main__":
    main()
