# -*- coding: utf-8 -*-
"""终审第 D 层：源文件重解析 diff 验证。

方法：行号 % 11317 == 42 确定性采样（UK≈505行/SG≈212/AU≈393/FL≈1147），
用与 ingest_* 完全相同的锚点/规范化规则独立重解析，逐字段与库值比对。
任何 diff = 入库变换有错，一票否决。
"""
from __future__ import annotations

import csv
import glob
import io
import json
import re
import sqlite3
import sys
import zipfile

import zipfile_deflate64 as zipfile  # noqa: F401 (仅 FL 段需要 3.10 环境)

sys.path.insert(0, r"d:\S.Q\kyb-mcp-server\ingest")
from common import (AU_CSV, UK_SNAPSHOT_DIR, norm_date_dmy, norm_date_iso,
                    norm_date_mdy8, norm_name, norm_number, out_safe)

out_safe()

DB = r"d:\S.Q\kyb-mcp-server\data\kyb.db"
SAMPLE_MOD, SAMPLE_REM = 11317, 42
DOC_RE = re.compile(r"^(?:[A-Z]\d{10,11}|[A-Z]?\d{5,6})")
ADDR_COLS = ["RegAddress.AddressLine1", "RegAddress.AddressLine2",
             "RegAddress.PostTown", "RegAddress.County", "RegAddress.Country",
             "RegAddress.PostCode"]

# UK
def parse_uk(row, idx):
    num = norm_number(row[idx["CompanyNumber"]], pad=8)
    filing = norm_date_dmy(row[idx["IncorporationDate"]])
    diss = norm_date_dmy(row[idx["DissolutionDate"]])
    addr = ", ".join(row[idx[c]].strip() for c in ADDR_COLS if row[idx[c]].strip())
    return {
        "company_number": num,
        "name": norm_name(row[idx["CompanyName"]]),
        "status_raw": row[idx["CompanyStatus"]].strip(),
        "entity_type_raw": row[idx["CompanyCategory"]].strip(),
        "industry_raw": row[idx["SICCode.SicText_1"]].strip(),
        "filing_date": filing, "dissolution_date": diss,
        "address": addr, "agent": "",
        "source_url": row[idx["URI"]].strip(),
    }


# SG
def parse_sg(row, header):
    def v(s):
        t = (s or "").strip()
        return "" if t.lower() == "na" else t
    idx = {h: i for i, h in enumerate(header)}
    num = norm_number(row[1])
    addr = ", ".join(v(row[i]) for i in [idx[c] for c in
                     ("block", "street_name", "level_no", "unit_no", "building_name", "postal_code")])
    return {
        "company_number": num,
        "name": norm_name(row[idx["entity_name"]]),
        "status_raw": v(row[idx["entity_status_description"]]),
        "entity_type_raw": v(row[idx["entity_type_description"]]),
        "industry_raw": v(row[idx["primary_ssic_code"]]),
        "filing_date": norm_date_iso(row[idx["registration_incorporation_date"]]),
        "dissolution_date": "",
        "address": addr, "agent": "",
        "source_url": f"https://www.bizfile.gov.sg/ (UEN {num})",
    }


# AU
def parse_au(row, idx):
    num = norm_number(row[idx["ACN"]], pad=9)
    cls = row[idx["Class"]].strip()
    sub = row[idx["Sub Class"]].strip()
    return {
        "company_number": num,
        "name": norm_name(row[idx["Company Name"]]),
        "status_raw": row[idx["Status"]].strip(),
        "entity_type_raw": row[idx["Type"]].strip(),
        "industry_raw": f"{cls}/{sub}" if cls and sub else (cls or sub),
        "filing_date": norm_date_dmy(row[idx["Date of Registration"]]),
        "dissolution_date": norm_date_dmy(row[idx["Date of Deregistration"]]),
        "address": "", "agent": "",
        "source_url": f"https://abr.business.gov.au/ (ACN {num})",
    }


# FL（官方锚点）
def parse_fl(line):
    def seg(a, b):
        return line[a:b].strip()
    m = DOC_RE.match(line)
    if m:
        num = m.group(0)
        name = " ".join(line[m.end():204].split())
    else:
        num = line[:12].strip().upper()
        name = " ".join(line[12:204].split())
    return {
        "company_number": num,
        "name": name,
        "status_raw": line[204],
        "entity_type_raw": seg(205, 220),
        "industry_raw": "",
        "filing_date": norm_date_mdy8(line[472:480]),
        "dissolution_date": "",
        "address": ", ".join(x for x in (seg(220, 262), seg(262, 304), seg(304, 332),
                              (seg(332, 334) + " " + seg(334, 344)).strip()) if x),
        "agent": seg(544, 586),
        "source_url": f"https://search.sunbiz.org/ (Document {num})",
    }


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA query_only=1")
    total = checked = mismatch = 0
    mmsgs = []

    def compare(jur, key, fields):
        nonlocal checked, mismatch
        checked += 1
        dbrow = conn.execute(
            "SELECT company_number, name, status_raw, entity_type_raw, industry_raw,"
            " filing_date, dissolution_date, address, agent, source_url FROM company"
            " WHERE jurisdiction=? AND company_number=?", (jur, key)).fetchone()
        if dbrow is None:
            mismatch += 1
            if len(mmsgs) < 10:
                mmsgs.append(f"{jur}/{key}: 库中无此行（或空名被跳过）")
            return
        dbvals = dict(zip(["company_number", "name", "status_raw", "entity_type_raw",
                           "industry_raw", "filing_date", "dissolution_date",
                           "address", "agent", "source_url"], dbrow))
        for k, v in fields.items():
            if dbvals[k] != v:
                mismatch += 1
                if len(mmsgs) < 10:
                    mmsgs.append(f"{jur}/{key} field={k}: db={dbvals[k]!r} != src={v!r}")
                return

    # UK
    import glob as _g
    for zp in sorted(_g.glob(UK_SNAPSHOT_DIR + r"\part*_7.zip")):
        with zipfile.ZipFile(zp) as z:
            for member in (n for n in sorted(z.namelist()) if n.lower().endswith(".csv")):
                with z.open(member) as rf:
                    tf = io.TextIOWrapper(rf, encoding="utf-8-sig", newline="")
                    r = csv.reader(tf)
                    header = [h.strip() for h in next(r)]
                    idx = {h: i for i, h in enumerate(header)}
                    for i, row in enumerate(r):
                        if i % SAMPLE_MOD != SAMPLE_REM or len(row) != len(header):
                            continue
                        total += 1
                        f = parse_uk(row, idx)
                        if f["company_number"] and f["name"]:
                            compare("gb", f["company_number"], f)
    print(f"UK sampled {total} checked {checked} mismatch {mismatch}", flush=True)

    # SG
    uk_done = (total, checked, mismatch)
    for p in sorted(glob.glob(r"d:\S.Q\kyb-mcp-server\data\sg_shards\shard_*.csv")):
        with open(p, encoding="utf-8-sig", newline="") as f:
            r = csv.reader(f)
            header = [c.strip() for c in next(r)]
            for i, row in enumerate(r):
                if i % SAMPLE_MOD != SAMPLE_REM:
                    continue
                total += 1
                d = parse_sg(row, header)
                if d["company_number"] and d["name"]:
                    compare("sg", d["company_number"], d)
    print(f"SG cumulative: sampled {total} checked {checked} mismatch {mismatch}", flush=True)

    # AU（只采现名行 Y，与主表口径一致）
    au_start = (total, checked, mismatch)
    with open(AU_CSV, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f, delimiter="\t")
        header = [c.strip() for c in next(r)]
        idx = {h: i for i, h in enumerate(header)}
        for i, row in enumerate(r):
            if i % SAMPLE_MOD != SAMPLE_REM:
                continue
            total += 1
            if row[idx["Current Name Indicator"]].strip().upper() != "Y":
                continue
            d = parse_au(row, idx)
            if d["company_number"] and d["name"]:
                compare("au", d["company_number"], d)
    print(f"AU cumulative: sampled {total} checked {checked} mismatch {mismatch}", flush=True)

    # FL
    from common import FL_ZIP
    with zipfile.ZipFile(FL_ZIP) as z:
        stop = False
        for name in sorted(z.namelist()):
            if stop:
                break
            with z.open(name) as f:
                tf = io.TextIOWrapper(f, encoding="latin-1")
                i = 0
                for line in tf:
                    if i % SAMPLE_MOD == SAMPLE_REM:
                        line = line.rstrip("\r\n")
                        if len(line) == 1440:
                            total += 1
                            d = parse_fl(line)
                            if d["company_number"] and d["name"]:
                                compare("us_fl", d["company_number"], d)
                    i += 1
    print(f"FL cumulative: sampled {total} checked {checked} mismatch {mismatch}", flush=True)

    print(f"\n=== DIFF VERDICT: {'PASS' if mismatch == 0 else 'FAIL'} ===")
    print(f"sampled rows: {total:,} / field-compared: {checked:,} / mismatches: {mismatch:,}")
    for m in mmsgs:
        print(f"  {m}")
    conn.close()


if __name__ == "__main__":
    main()
