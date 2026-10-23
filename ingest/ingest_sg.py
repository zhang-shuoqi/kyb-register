# -*- coding: utf-8 -*-
"""SG ACRA 快照 -> kyb.db

源：data/sg_shards/shard_00-26.csv（54 列，utf-8-sig，'na' 为空值占位）
锚点（2026-10-23 实测）：日期已 ISO；uen 列无 'na' 行；
        456,457 行为下载翻页重叠产生的完全重复行（_id+54列全同），
        预期由 UNIQUE(jurisdiction, company_number) 去重 -> 唯一实体 1,938,343。
        former_entity_name1-15 -> previous_name（无日期列，changed_at=''）。

用法：python ingest_sg.py [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys

sys.path.insert(0, r"d:\S.Q\kyb-mcp-server\ingest")
from common import (BATCH, EXPECTED_UNIQUE, INSERT_COMPANY, INSERT_PREV, Progress,
                    SG_SHARDS_GLOB, connect, dump_json, file_date, init_schema,
                    norm_date_iso, norm_name, norm_number, out_safe, stats)

out_safe()


def v(s: str) -> str:
    """SG 空值占位 'na' -> ''。"""
    t = (s or "").strip()
    return "" if t.lower() == "na" else t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    files = sorted(glob.glob(SG_SHARDS_GLOB))
    print(f"SG ingest: {len(files)} shards -> limit={args.limit or 'ALL'}")
    if not files:
        print("FATAL: no shards found")
        sys.exit(2)
    retrieved = file_date(files[0]) or "2026-10-22"

    conn = connect()
    init_schema(conn)

    prog = Progress("SG")
    n_company = 0
    n_prev = 0
    n_conflict = 0
    n_na_uen = 0
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

    header: list[str] | None = None
    idx_i_name = idx_i_status = idx_i_type = idx_i_reg = -1
    idx_i_addr = list(range(-1, -1))
    idx_i_prev = list(range(-1, -1))

    stop = False
    for path in files:
        if stop:
            break
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            h = [c.strip() for c in next(reader)]
            if header is None:
                header = h
                idx_i_name = header.index("entity_name")
                idx_i_status = header.index("entity_status_description")
                idx_i_type = header.index("entity_type_description")
                idx_i_reg = header.index("registration_incorporation_date")
                idx_i_addr = [header.index(c) for c in
                              ("block", "street_name", "level_no", "unit_no",
                               "building_name", "postal_code")]
                idx_i_prev = [header.index(f"former_entity_name{k}") for k in range(1, 16)]
                idx_ssic = header.index("primary_ssic_code")
                print(f"header ok: 54 cols expected={len(h)}")
            for row in reader:
                prog.tick()
                uen = norm_number(row[1])
                if not uen or uen.lower() == "NA":
                    n_na_uen += 1
                    continue
                name = norm_name(row[idx_i_name])
                if not name:
                    print(f"WARN empty name uen={uen}")
                    continue
                filing = norm_date_iso(row[idx_i_reg])
                if not filing and row[idx_i_reg].strip():
                    bad_dates += 1
                addr = ", ".join(v(row[i]) for i in idx_i_addr)
                buf.append((
                    "sg", uen, name,
                    v(row[idx_i_status]),
                    v(row[idx_i_type]),
                    v(row[idx_ssic]),
                    filing, "", addr,
                    "",  # SG bulk 无注册代理人字段
                    f"https://www.bizfile.gov.sg/ (UEN {uen})",
                    retrieved,
                    dump_json(dict(zip(header, row))),
                ))
                for pi in idx_i_prev:
                    former = norm_name(v(row[pi]))
                    if former:
                        prev_buf.append(("sg", uen, former, "", "sg_former_col"))
                if len(buf) >= BATCH:
                    flush()
                if args.limit and prog.n >= args.limit:
                    stop = True
                    break
    flush()
    prog.done()
    stats(conn, "SG", prog.n, n_company, n_conflict,
          {"previous_name rows": f"{n_prev:,}",
           "na/empty uen skipped": str(n_na_uen),
           "bad reg dates": str(bad_dates),
           "expected unique": f"{EXPECTED_UNIQUE['sg']:,}"})
    conn.close()


if __name__ == "__main__":
    main()
