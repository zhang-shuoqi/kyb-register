# -*- coding: utf-8 -*-
"""FL 重灌准备：摘 FTS 触发器 + 分批删除 us_fl 行。"""
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"d:\S.Q\kyb-mcp-server\data\kyb.db"

conn = sqlite3.connect(DB, isolation_level=None)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA cache_size=-65536")

print("dropping fts triggers ...", flush=True)
for t in ("company_fts_ai", "company_fts_ad", "company_fts_au"):
    conn.execute(f"DROP TRIGGER IF EXISTS {t}")

n0 = conn.execute("SELECT COUNT(*) FROM company WHERE jurisdiction='us_fl'").fetchone()[0]
print(f"deleting us_fl rows: {n0:,} (batched 500k)", flush=True)
t0 = time.time()
deleted = 0
while True:
    cur = conn.execute(
        "DELETE FROM company WHERE rowid IN "
        "(SELECT rowid FROM company WHERE jurisdiction='us_fl' LIMIT 500000)")
    k = cur.rowcount
    deleted += k
    print(f"  deleted {deleted:,}/{n0:,}  {time.time()-t0:.0f}s", flush=True)
    if k == 0:
        break
print(f"DELETE done: {deleted:,} rows in {time.time()-t0:.0f}s", flush=True)
left = conn.execute("SELECT COUNT(*) FROM company WHERE jurisdiction='us_fl'").fetchone()[0]
print(f"remaining us_fl: {left}", flush=True)
conn.close()
