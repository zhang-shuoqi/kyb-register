"""
任务 1：AU ASIC CSV → SQLite 入库
用法：
  python import_au.py --sample     # 只导前 1000 行（验证字段名）
  python import_au.py --full      # 全量导入（370 万行，约几分钟）
  python import_au.py             # 默认 --full
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from normalizers import build_unified_record  # noqa: E402

DB_PATH = Path(__file__).parent / "data" / "kyb.db"
CSV_PATH = Path(__file__).parent / "data" / "asic_companies.csv"
SNAPSHOT_DATE = time.strftime("%Y-%m-%d")  # 本次快照日期，company_history 用

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  country TEXT NOT NULL,
  region TEXT,
  registration_number TEXT,
  entity_name TEXT,
  entity_type TEXT,
  status TEXT,
  status_raw TEXT,
  filing_date TEXT,
  dissolution_date TEXT,
  registered_agent TEXT,
  principal_address TEXT,
  industry_code TEXT,
  industry_description TEXT,
  officers_count INTEGER,
  data_source TEXT,
  last_verified TEXT,
  raw TEXT,
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(country, entity_name);
CREATE INDEX IF NOT EXISTS idx_entities_number ON entities(country, registration_number);

-- 任务 3 的变动历史表（现在建好，diff 管道从首周快照开始写入）
CREATE TABLE IF NOT EXISTS company_history (
  country TEXT NOT NULL,
  registration_number TEXT NOT NULL,
  field TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  changed_at TEXT,            -- 我们观测到差异的日期（diff 运行日）
  source_snapshot_date TEXT,  -- 数据快照所属日期
  PRIMARY KEY (country, registration_number, field, source_snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_history_number ON company_history(country, registration_number);

-- 每周快照登记（diff 管道用：记住最近一次快照日期与来源）
CREATE TABLE IF NOT EXISTS snapshots (
  country TEXT NOT NULL,
  source_snapshot_date TEXT NOT NULL,
  row_count INTEGER,
  imported_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (country, source_snapshot_date)
);
"""

COLUMNS = [
    "country", "region", "registration_number", "entity_name", "entity_type",
    "status", "status_raw", "filing_date", "dissolution_date",
    "registered_agent", "principal_address", "industry_code",
    "industry_description", "officers_count", "data_source", "last_verified",
    "raw",
]


def row_to_unified(row: dict) -> dict:
    """把 ASIC 原始行转成统一 schema dict（复用 normalizers）。"""
    from adapters.au_asic import _parse_date

    return build_unified_record(
        country="AU",
        region=None,
        registration_number=(row.get("ACN") or "").strip() or None,
        entity_name=(row.get("Current Name") or row.get("Company Name") or "").strip() or None,
        raw_status=(row.get("Status") or "").strip() or None,
        raw_entity_type=(row.get("Type") or "").strip() or None,
        filing_date=_parse_date(row.get("Date of Registration")),
        dissolution_date=_parse_date(row.get("Date of Deregistration")),
        registered_agent=None,
        address_parts={
            "state": row.get("State Registration Number"),
            "country": "Australia",
        },
        industry_code=None,
        industry_description=None,
        officers_count=None,
        data_source="AU ASIC data.gov.au",
        last_verified=SNAPSHOT_DATE,
        raw=row,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="只导前 1000 行验证字段")
    ap.add_argument("--full", action="store_true", help="全量导入")
    args = ap.parse_args()

    if not CSV_PATH.exists():
        print(f"❌ CSV 不存在: {CSV_PATH}，先跑下载")
        sys.exit(1)

    limit = 1000 if args.sample else None
    mode = "SAMPLE(1000)" if args.sample else "FULL"

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    t0 = time.time()
    batch: list[tuple] = []
    total = 0

    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            u = row_to_unified(row)
            # 样例模式：先打印第一条的字段结构再入库
            if total == 0:
                print("=== unified record keys ===")
                for k in COLUMNS:
                    v = u.get(k)
                    shown = str(v)[:60] if v is not None else None
                    print(f"  {k}: {shown}")
            batch.append(tuple(u.get(c) for c in COLUMNS))
            total += 1
            if len(batch) >= 50000:
                _insert(conn, batch)
                batch = []
                print(f"  ...{total} rows ({time.time()-t0:.0f}s)")
            if limit and total >= limit:
                break

    if batch:
        _insert(conn, batch)

    conn.execute(
        "INSERT OR REPLACE INTO snapshots (country, source_snapshot_date, row_count) VALUES (?,?,?)",
        ("AU", SNAPSHOT_DATE, total),
    )
    conn.commit()

    cnt = conn.execute("SELECT COUNT(*) FROM entities WHERE country='AU'").fetchone()[0]
    print(f"✅ done: {total} rows read, {cnt} in DB, {time.time()-t0:.0f}s, mode={mode}")
    conn.close()


def _insert(conn: sqlite3.Connection, batch: list[tuple]) -> None:
    placeholders = ",".join("?" * len(COLUMNS))
    conn.executemany(
        f"INSERT INTO entities ({','.join(COLUMNS)}) VALUES ({placeholders})",
        batch,
    )
    conn.commit()


if __name__ == "__main__":
    main()
