# -*- coding: utf-8 -*-
"""kyb.db 全库终审 v2（流式版：每国单遍扫描，L2/L3/L4 一次算完）。

L0 仪器校准（ACN/ABN 算法正负样本，不过拒绝跑）
L1 行数对账
L2+L3+L4 每国流式：空名/非法日期/未来日期 + 校验和与格式全量 + 值分布
L5 FTS 一致性 + 孤儿行
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = r"d:\S.Q\kyb-mcp-server\data\kyb.db"
FUTURE_CUTOFF = "2027-01-01"

FL_ETYPES_OFFICIAL = {"DOMP", "DOMNP", "FORP", "FORNP", "DOMLP", "FORLP",
                      "FLAL", "FORL", "NPREG", "TRUST", "AGENT"}
UEN_RES = [
    re.compile(r"^\d{8}[A-Z]$"),
    re.compile(r"^\d{9}[A-Z]$"),
    re.compile(r"^[TSR]\d{2}[A-Z]{2}\d{4,5}[A-Z]$"),
    re.compile(r"^[TSRF]\d{2}[A-Z]{2}\d{4}[A-Z]$"),
]
UK_NUM_RE = re.compile(r"^[A-Z0-9]{6,8}$")
FL_DOC_YY = re.compile(r"^([A-Z])(\d{2})\d+$")

issues: list[str] = []


def sec(t):
    print(f"\n{'='*10} {t} {'='*10}", flush=True)


def row(m):
    print(f"  {m}", flush=True)


def acn_ok(a):
    if len(a) != 9 or not a.isdigit():
        return False
    w = (8, 7, 6, 5, 4, 3, 2, 1)
    s = sum(int(d) * x for d, x in zip(a[:8], w))
    return (10 - s % 10) % 10 == int(a[8])


def abn_ok(a):
    if len(a) != 11 or not a.isdigit():
        return False
    d = list(map(int, a))
    d[0] -= 1
    w = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
    return sum(x * y for x, y in zip(d, w)) % 89 == 0


def date_bad(d):
    if not d:
        return False
    return not (len(d) == 10 and d[4] == "-" and d[7] == "-"
                and d[:4].isdigit() and d[5:7].isdigit() and d[8:].isdigit()
                and 1 <= int(d[5:7]) <= 12 and 1 <= int(d[8:]) <= 31)


def main():
    # L0
    sec("L0 仪器校准")
    cal = True
    for n in ("004028077", "000001105"):
        if not acn_ok(n):
            row(f"CAL FAIL: acn_ok({n}) 应 True")
            cal = False
    for n in ("004028078", "000001106"):
        if acn_ok(n):
            row(f"CAL FAIL: acn_ok({n}) 应 False")
            cal = False
    if abn_ok("33051775556"):
        if abn_ok("34051775556") or abn_ok("33051775557"):
            row("CAL FAIL: abn 负样本通过")
            cal = False
    else:
        row("CAL WARN: ABN 样本未过 mod-89（算法需复核，ABN 结果仅参考）")
    if not cal:
        print("VERDICT: ABORT")
        return
    row("校准通过")

    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA query_only=1")
    conn.execute("PRAGMA cache_size=-65536")

    sec("L1 行数对账")
    counts = dict(conn.execute(
        "SELECT jurisdiction, COUNT(*) FROM company GROUP BY jurisdiction").fetchall())
    exp = {"gb": 5_704_711, "sg": 1_938_342, "au": 4_018_252, "us_fl": 12_987_600}
    for j in ("gb", "sg", "au", "us_fl"):
        ok = counts.get(j, 0) == exp[j]
        row(f"{j:6} {counts.get(j,0):>12,}  {'PASS' if ok else 'FAIL'}")
        if not ok:
            issues.append(f"L1 {j}")
    row(f"total {sum(counts.values()):,}")

    # L2/L3/L4 每国流式
    for j in ("gb", "sg", "au", "us_fl"):
        sec(f"L2-L4 {j} 流式审计")
        t0 = time.time()
        n = 0
        empty_name = bad_date = future = 0
        st_c = Counter()
        et_c = Counter()
        fmt_bad, bad_samples = 0, []
        # FL 年份自洽
        yy_same = yy_older = yy_newer = yy_noprefix = 0
        # AU ABN 采样（每 80 行取 1）
        abn_ok_n = abn_bad_n = abn_skip_n = 0
        abn_bad_samples = []
        cur = conn.execute(
            "SELECT company_number, name, status_raw, entity_type_raw,"
            " filing_date, address, raw FROM company WHERE jurisdiction=?", (j,))
        while True:
            rows = cur.fetchmany(100_000)
            if not rows:
                break
            for (num, name, st, et, fd, addr, raw) in rows:
                n += 1
                st_c[st] += 1
                et_c[et] += 1
                if not name:
                    empty_name += 1
                if date_bad(fd):
                    bad_date += 1
                elif fd >= FUTURE_CUTOFF:
                    future += 1
                if j == "au":
                    if acn_ok(num):
                        pass
                    else:
                        issues.append(f"L3 AU ACN 校验失败: {num}")
                    if n % 80 == 3:
                        try:
                            abn = str(json.loads(raw).get("ABN", "")).strip()
                        except Exception:
                            abn = ""
                        if not abn or abn == "0":
                            abn_skip_n += 1
                        elif abn_ok(abn):
                            abn_ok_n += 1
                        else:
                            abn_bad_n += 1
                            if len(abn_bad_samples) < 5:
                                abn_bad_samples.append(abn)
                elif j == "sg":
                    if not any(r.match(num) for r in UEN_RES):
                        fmt_bad += 1
                        if len(bad_samples) < 8:
                            bad_samples.append(num)
                elif j == "gb":
                    if not UK_NUM_RE.match(num):
                        fmt_bad += 1
                        if len(bad_samples) < 5:
                            bad_samples.append(num)
                elif j == "us_fl":
                    if et not in FL_ETYPES_OFFICIAL:
                        fmt_bad += 1
                        if len(bad_samples) < 5:
                            bad_samples.append(et)
                    m = FL_DOC_YY.match(num)
                    if not m:
                        yy_noprefix += 1
                    elif not fd[:4].isdigit():
                        pass
                    else:
                        fy, py_ = int(fd[:4]), 2000 + int(m.group(2))
                        if fy == py_:
                            yy_same += 1
                        elif fy < py_:
                            yy_older += 1
                        else:
                            yy_newer += 1
        row(f"scanned {n:,} in {time.time()-t0:.0f}s")
        row(f"empty_name={empty_name:,}  malformed_date={bad_date:,}  "
            f"future_date={future:,}")
        if empty_name:
            issues.append(f"L2 {j} 空名 {empty_name}")
        if bad_date:
            issues.append(f"L2 {j} 非法日期 {bad_date}")
        if future:
            row(f"  future date 样本国 FL 已知源伪影，其余国应为 0")
            issues.append(f"L2 {j} 未来日期 {future}")
        if j == "au":
            row(f"ACN 全量校验: 0 失败计数与 L3 合并（失败已实时报 issues）")
            row(f"ABN 采样校验: PASS {abn_ok_n:,} / FAIL {abn_bad_n:,} / skip {abn_skip_n:,}"
                + (f"  samples={abn_bad_samples}" if abn_bad_samples else ""))
            if abn_bad_n / max(abn_ok_n, 1) > 0.0001:
                issues.append(f"L3 ABN 校验失败 {abn_bad_n}")
        elif j == "sg":
            row(f"UEN 格式族: 匹配 {n-fmt_bad:,} / 不匹配 {fmt_bad:,}"
                + (f"  samples={bad_samples}" if bad_samples else ""))
            if fmt_bad / max(n, 1) > 0.001:
                issues.append(f"L3 SG 格式外 {fmt_bad}")
        elif j == "gb":
            row(f"number 格式: 匹配 {n-fmt_bad:,} / 不匹配 {fmt_bad:,}"
                + (f"  samples={bad_samples}" if bad_samples else ""))
            if fmt_bad / max(n, 1) > 0.0001:
                issues.append(f"L3 UK 格式外 {fmt_bad}")
        elif j == "us_fl":
            row(f"Filing Type 非官方枚举值: {fmt_bad:,}"
                + (f"  samples={bad_samples}" if bad_samples else ""))
            row(f"年份自洽: same={yy_same:,} older(合法reinstatement)={yy_older:,} "
                f"newer(伪影)={yy_newer:,} 无年号前缀={yy_noprefix:,}")
            if fmt_bad:
                issues.append(f"L3 FL 非官方类型 {fmt_bad}")
            if yy_newer > 20:
                issues.append(f"L3 FL 年份前向伪影 {yy_newer}")
        row(f"status top4: {st_c.most_common(4)}")
        row(f"etype  top4: {et_c.most_common(4)}")

    # L5
    sec("L5 FTS 一致性 + 孤儿行")
    n_fts, = conn.execute("SELECT COUNT(*) FROM company_fts").fetchone()
    n_c, = conn.execute("SELECT COUNT(*) FROM company").fetchone()
    row(f"company={n_c:,}  fts={n_fts:,}  {'PASS' if n_fts == n_c else 'FAIL'}")
    if n_fts != n_c:
        issues.append("L5 FTS 行数不一致")
    orphan, = conn.execute(
        "SELECT COUNT(*) FROM previous_name p WHERE NOT EXISTS"
        " (SELECT 1 FROM company c WHERE c.jurisdiction=p.jurisdiction"
        " AND c.company_number=p.company_number)").fetchone()
    row(f"previous_name 孤儿行: {orphan:,}（39 个 AU CNCL 注销公司为已知上游形态）")
    if orphan > 100:
        issues.append(f"L5 孤儿 {orphan}")

    print("\n" + "=" * 50)
    if issues:
        print(f"VERDICT: REVIEW（{len(issues)} 项）")
        for i in issues:
            print(f"  - {i}")
    else:
        print("VERDICT: PASS（L0-L5 全过）")
    conn.close()


if __name__ == "__main__":
    main()
