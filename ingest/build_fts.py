# -*- coding: utf-8 -*-
"""FTS5 全文索引构建：四国插完后跑一次。

先插数后建索引（省体积：external content 表 + columnsize=0，社区实测可省约一半）。
完成后挂触发器，供未来每周 diff 增量更新时自动同步索引。

用法：python build_fts.py
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, r"d:\S.Q\kyb-mcp-server\ingest")
from common import connect, out_safe

out_safe()

DDL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS company_fts USING fts5(
  name,
  content='company',
  content_rowid='rowid',
  columnsize=0
);
"""

DDL_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS company_fts_ai AFTER INSERT ON company BEGIN
  INSERT INTO company_fts(rowid, name) VALUES (new.rowid, new.name);
END;
CREATE TRIGGER IF NOT EXISTS company_fts_ad AFTER DELETE ON company BEGIN
  INSERT INTO company_fts(company_fts, rowid, name) VALUES ('delete', old.rowid, old.name);
END;
CREATE TRIGGER IF NOT EXISTS company_fts_au AFTER UPDATE ON company BEGIN
  INSERT INTO company_fts(company_fts, rowid, name) VALUES ('delete', old.rowid, old.name);
  INSERT INTO company_fts(rowid, name) VALUES (new.rowid, new.name);
END;
"""


def main() -> None:
    conn = connect()
    t0 = time.time()
    print("creating fts table ...")
    conn.executescript(DDL_FTS)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM company").fetchone()[0]
    print(f"company rows: {n:,}; rebuilding fts index (single pass) ...")
    conn.execute("INSERT INTO company_fts(company_fts) VALUES('rebuild')")
    conn.commit()
    print(f"rebuild done in {time.time()-t0:.0f}s; creating triggers ...")
    conn.executescript(DDL_TRIGGERS)
    conn.commit()
    # 抽查：FTS 可命中
    probe = conn.execute("SELECT COUNT(*) FROM company_fts WHERE company_fts MATCH 'bhp'").fetchone()[0]
    print(f"fts probe 'bhp' hits: {probe:,}")
    print(f"TOTAL {time.time()-t0:.0f}s")
    conn.close()


if __name__ == "__main__":
    main()
