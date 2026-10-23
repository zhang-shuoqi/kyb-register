# -*- coding: utf-8 -*-
"""AU ASIC 快照 -> kyb.db

源：data/asic_companies.csv（15 列，Tab 分隔，utf-8-sig）
锚点（2026-10-23 实测）：ACN 9位含前导零；日期 DD/MM/YYYY；
        同 ACN 多行 = 曾用名行（Current Name Indicator='Y' 为现名行），
        曾用名行的 Company Name 是曾用名本体，Current Name Start Date 是现名生效日。
        ABN 列可为占位 '0'，不入主表列（raw 留底）。

用法：python ingest_au.py [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import sys

sys.path.insert(0, r"d:\S.Q\kyb-mcp-server\ingest")
from common import (AU_CSV, BATCH, INSERT_COMPANY, INSERT_PREV, Progress,
                    connect, dump_json, file_date, init_schema, norm_date_dmy,
                    norm_name, norm_number, out_safe, stats)

out_safe()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print(f"AU ingest -> limit={args.limit or 'ALL'}")
    retrieved = file_date(AU_CSV) or "2026-10-22"

    conn = connect()
    init_schema(conn)

    prog = Progress("AU")
    n_company = 0
    n_prev = 0
    n_conflict = 0
    n_empty_acn = 0
    bad_dates = 0
    prev_buf: list[tuple] = []
    buf: list[tuple] = []

    def flush() -> None:
        nonlocal n_company, n_prev, n_conflict
        if buf:
            n = len(buf)
            c0 = conn.total_changes
            conn.executemany(INSERT_COMPANY, buf)
            got = conn.total_changes - c0
            n_company += got
            n_conflict += n - got
            buf.clear()
        if prev_buf:
            c0 = conn.total_changes
            conn.executemany(INSERT_PREV, prev_buf)
            n_prev += conn.total_changes - c0
            prev_buf.clear()
        conn.commit()

    with open(AU_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = [c.strip() for c in next(reader)]
        idx = {h: i for i, h in enumerate(header)}
        need = ["Company Name", "ACN", "Type", "Class", "Sub Class", "Status",
                "Date of Registration", "Date of Deregistration",
                "Current Name Indicator", "Current Name Start Date"]
        missing = [c for c in need if c not in idx]
        if missing:
            print(f"FATAL header missing: {missing}")
            sys.exit(2)
        i_name = idx["Company Name"]
        i_acn = idx["ACN"]
        i_type = idx["Type"]
        i_cls = idx["Class"]
        i_sub = idx["Sub Class"]
        i_status = idx["Status"]
        i_dor = idx["Date of Registration"]
        i_dod = idx["Date of Deregistration"]
        i_ind = idx["Current Name Indicator"]
        i_cnsd = idx["Current Name Start Date"]
        for row in reader:
            prog.tick()
            acn = norm_number(row[i_acn], pad=9)
            if not acn:
                n_empty_acn += 1
                continue
            name = norm_name(row[i_name])
            if not name:
                print(f"WARN empty name acn={acn}")
                continue
            if row[i_ind].strip().upper() == "Y":
                filing = norm_date_dmy(row[i_dor])
                diss = norm_date_dmy(row[i_dod])
                if not filing and row[i_dor].strip():
                    bad_dates += 1
                cls = row[i_cls].strip()
                sub = row[i_sub].strip()
                buf.append((
                    "au", acn, name,
                    row[i_status].strip(),
                    row[i_type].strip(),
                    f"{cls}/{sub}" if cls and sub else (cls or sub),
                    filing, diss, "",  # AU CSV 无地址列
                    "",
                    f"https://abr.business.gov.au/ (ACN {acn})",
                    retrieved,
                    dump_json(dict(zip(header, row))),
                ))
                if len(buf) >= BATCH:
                    flush()
            else:
                prev_buf.append(("au", acn, name,
                                 norm_date_dmy(row[i_cnsd]), "au_prev_row"))
                if len(prev_buf) >= BATCH:
                    flush()
            if args.limit and prog.n >= args.limit:
                break
    flush()
    prog.done()

    # 曾用名行对应的 ACN 是否都有主表行（无 'Y' 行的 ACN 会被漏掉，必须量化）
    missing_main = conn.execute(
        "SELECT COUNT(*) FROM previous_name p WHERE p.jurisdiction='au' AND src='au_prev_row'"
        " AND NOT EXISTS (SELECT 1 FROM company c WHERE c.jurisdiction='au'"
        " AND c.company_number=p.company_number)").fetchone()[0]
    stats(conn, "AU", prog.n, n_company, n_conflict,
          {"previous_name rows": f"{n_prev:,}",
           "empty acn skipped": str(n_empty_acn),
           "bad reg dates": str(bad_dates),
           "prev rows w/o main company (must be 0)": f"{missing_main:,}"})
    conn.close()


if __name__ == "__main__":
    main()
