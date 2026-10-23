# -*- coding: utf-8 -*-
"""UK Companies House bulk 快照 -> kyb.db

源：data/uk_snapshot/part1_7.zip（7 个 CSV 成员，55 列，header 带前导空格须 strip）
锚点（2026-10-23 实测）：CompanyNumber 8位含前导零；日期 DD/MM/YYYY；
        PreviousName_1..10 = CONDATE + CompanyName 成对；URI 列为官方核对链接。
审计基线：5,704,711 行（part4 空行伪影已修复）。

用法：python ingest_uk.py [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile

sys.path.insert(0, r"d:\S.Q\kyb-mcp-server\ingest")
from common import (BATCH, EXPECTED_UNIQUE, INSERT_COMPANY, INSERT_PREV, Progress,
                    UK_SNAPSHOT_DIR, connect, dump_json, file_date, init_schema,
                    norm_date_dmy, norm_name, norm_number, out_safe, stats)

out_safe()

ADDR_COLS = ["RegAddress.AddressLine1", "RegAddress.AddressLine2",
             "RegAddress.PostTown", "RegAddress.County", "RegAddress.Country",
             "RegAddress.PostCode"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="仅处理前 N 行（小样测试）")
    args = ap.parse_args()

    import glob
    zips = sorted(glob.glob(UK_SNAPSHOT_DIR + r"\part*_7.zip"))
    if not zips:
        print(f"FATAL: no part*_7.zip under {UK_SNAPSHOT_DIR}")
        sys.exit(2)
    retrieved = file_date(zips[0]) or "2026-10-01"
    print(f"UK ingest -> {len(zips)} zips, retrieved_at={retrieved} limit={args.limit or 'ALL'}")

    conn = connect()
    init_schema(conn)

    prog = Progress("UK")
    n_company = 0
    n_prev = 0
    n_conflict = 0
    bad_dates: list[str] = []
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

    with zipfile.ZipFile(zips[0]) as z0:
        inner = sorted(n for n in z0.namelist() if n.lower().endswith(".csv"))
    print(f"inner csv members: {inner}")
    stop = False
    for zpath in zips:
        if stop:
            break
        with zipfile.ZipFile(zpath) as z:
            for member in (n for n in sorted(z.namelist()) if n.lower().endswith(".csv")):
                with z.open(member) as raw_f:
                    tf = io.TextIOWrapper(raw_f, encoding="utf-8-sig", newline="")
                    reader = csv.reader(tf)
                    header = [h.strip() for h in next(reader)]
                    idx = {h: i for i, h in enumerate(header)}
                    missing = [c for c in ["CompanyName", "CompanyNumber", "CompanyStatus",
                                           "CompanyCategory", "IncorporationDate",
                                           "DissolutionDate", "SICCode.SicText_1", "URI"]
                               + ADDR_COLS if c not in idx]
                    if missing:
                        print(f"FATAL header missing cols in {zpath}/{member}: {missing}")
                        sys.exit(2)
                    i_prev = [(idx[f"PreviousName_{k}.CONDATE"], idx[f"PreviousName_{k}.CompanyName"])
                              for k in range(1, 11)]
                    for row in reader:
                        prog.tick()
                        if len(row) != len(header):
                            print(f"WARN bad col count {len(row)} in {member}, skipped")
                            continue
                        number = norm_number(row[idx["CompanyNumber"]], pad=8)
                        name = norm_name(row[idx["CompanyName"]])
                        if not number or not name:
                            print(f"WARN empty number/name: {row[:2]!r}")
                            continue
                        filing = norm_date_dmy(row[idx["IncorporationDate"]])
                        diss = norm_date_dmy(row[idx["DissolutionDate"]])
                        if not filing and row[idx["IncorporationDate"]].strip():
                            if len(bad_dates) < 5:
                                bad_dates.append(row[idx["IncorporationDate"]])
                        addr = ", ".join(row[idx[c]].strip() for c in ADDR_COLS
                                         if row[idx[c]].strip())
                        buf.append((
                            "gb", number, name,
                            row[idx["CompanyStatus"]].strip(),
                            row[idx["CompanyCategory"]].strip(),
                            row[idx["SICCode.SicText_1"]].strip(),
                            filing, diss, addr,
                            "",  # UK bulk 无注册代理人字段
                            row[idx["URI"]].strip(),
                            retrieved,
                            dump_json(dict(zip(header, row))),
                        ))
                        for ci, cn in i_prev:
                            former = norm_name(row[cn]) if cn < len(row) else ""
                            if former:
                                prev_buf.append(("gb", number, former,
                                                 norm_date_dmy(row[ci]) if ci < len(row) else "",
                                                 "uk_prev_col"))
                        if len(buf) >= BATCH:
                            flush()
                        if args.limit and prog.n >= args.limit:
                            stop = True
                            break
                if stop:
                    break
    flush()
    prog.done()
    stats(conn, "UK", prog.n, n_company, n_conflict,
          {"previous_name rows": f"{n_prev:,}",
           "bad incorporation dates": str(len(bad_dates)) + (f" samples={bad_dates}" if bad_dates else ""),
           "expected": f"{EXPECTED_UNIQUE['gb']:,}"})
    conn.close()


if __name__ == "__main__":
    main()
