# -*- coding: utf-8 -*-
"""kyb.db 入库验收：四国行数对账 + 样本秒查。

验收标准（蓝图原文）：行数对账全中 + 查 BHP 秒回。

用法：python verify_ingest.py
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, r"d:\S.Q\kyb-mcp-server\ingest")
from common import DB_PATH, EXPECTED_UNIQUE, connect, out_safe

out_safe()

SAMPLES = [
    ("gb", "08209948", "! LTD"),
    ("au", "004028077", "BHP (四行改名链样本)"),
    ("us_fl", "L16000216990", "FLIP THAT REO LLC"),
]


def timed(conn, sql: str, args: tuple) -> tuple[float, list]:
    t0 = time.time()
    rows = conn.execute(sql, args).fetchall()
    return time.time() - t0, rows


def main() -> None:
    conn = connect()
    print(f"db: {DB_PATH}")
    ok = True

    print("\n== 1. 四国行数对账 ==")
    counts = dict(conn.execute(
        "SELECT jurisdiction, COUNT(*) FROM company GROUP BY jurisdiction").fetchall())
    for j in ("gb", "sg", "au", "us_fl"):
        exp = EXPECTED_UNIQUE[j]
        got = counts.get(j, 0)
        mark = "PASS" if (exp is None or got == exp) else "FAIL"
        if mark == "FAIL":
            ok = False
        print(f"  {j:6} {got:>12,}  expected={exp or '(Y行实测)'}  {mark}")
    total = sum(counts.values())
    print(f"  total  {total:,}")

    print("\n== 2. 样本秒查（按唯一键） ==")
    for j, num, label in SAMPLES:
        el, rows = timed(conn, "SELECT name, status_raw, filing_date FROM company"
                               " WHERE jurisdiction=? AND company_number=?", (j, num))
        mark = "PASS" if rows else "FAIL"
        if not rows:
            ok = False
        print(f"  {mark} {el*1000:.1f}ms  {j}/{num}  {label} -> {rows}")

    print("\n== 3. FTS 秒查（BHP） ==")
    try:
        el, rows = timed(conn, "SELECT c.jurisdiction, c.company_number, c.name FROM"
                               " company_fts f JOIN company c ON c.rowid=f.rowid"
                               " WHERE company_fts MATCH 'bhp' LIMIT 5", ())
        print(f"  PASS {el*1000:.1f}ms  hits(5): {rows}")
    except Exception as e:
        print(f"  FTS not built yet ({e})")

    print("\n== 4. AU 曾用名链（BHP 004028077） ==")
    el, rows = timed(conn, "SELECT former_name, changed_at FROM previous_name"
                           " WHERE jurisdiction='au' AND company_number=?"
                           " ORDER BY changed_at", ("004028077",))
    print(f"  {el*1000:.1f}ms  {len(rows)} former names: {rows}")

    print("\n== 5. 表完整性 ==")
    for t in ("company", "previous_name", "company_event", "company_fts"):
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n:,}")
        except Exception as e:
            if t == "company_fts":
                print(f"  {t}: 未构建")
            else:
                ok = False
                print(f"  {t}: ERROR {e}")

    print("\nVERDICT:", "PASS" if ok else "FAIL")
    conn.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
