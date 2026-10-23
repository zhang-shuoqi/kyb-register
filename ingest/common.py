# -*- coding: utf-8 -*-
"""入库公共层：连接/规范化/进度日志。

哲学：坏了不修，坏了全量重建（源文件已本地留底）。
入库只做结构规范化（trim/大写/ISO日期/唯一键去重），翻译不进库。
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = r"d:\S.Q\kyb-mcp-server\data\kyb.db"
SCHEMA_PATH = os.path.join(BASE, "schema.sql")

# 各源文件路径
UK_SNAPSHOT_DIR = r"d:\S.Q\kyb-mcp-server\data\uk_snapshot"  # part1_7.zip ~ part7_7.zip 共 7 个
SG_SHARDS_GLOB = r"d:\S.Q\kyb-mcp-server\data\sg_shards\shard_*.csv"
AU_CSV = r"d:\S.Q\kyb-mcp-server\data\asic_companies.csv"
FL_ZIP = r"d:\S.Q\kyb-mcp-server\data\sunbiz_quarterly\cordata.zip"

# 各国检索快照日兜底值（若 mtime 不可用时使用；正常以源文件 mtime 为准）
RETRIEVED_FALLBACK = {
    "gb": "2026-10-01",
    "sg": "2026-10-22",
    "au": "2026-10-22",
    "us_fl": "2026-10-23",
}

# 预期行数（对账口径 = 唯一可入库实体数，来自四国审计+实测）
EXPECTED_UNIQUE = {
    "gb": 5_704_711,      # UK 审计行数（快照唯一）
    "sg": 1_938_342,      # 2,394,800 文件行 - 456,457 下载重叠重复 - 1 空名 UEN(53347159A)
    "au": 4_018_252,      # Current Name Indicator='Y' 行实测
    "us_fl": 12_987_600,  # 12,987,601 - 1 空名行(L13000151001)
}

BATCH = 50_000  # 每事务行数（官方 FAQ：勿逐行 commit）


def out_safe():
    """Windows GBK 控制台防炸：输出统一 UTF-8 + 替换坏字符。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def file_date(path: str) -> str:
    """源文件 mtime -> YYYY-MM-DD，作为 retrieved_at（实事求是：数据快照日）。"""
    try:
        return time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path)))
    except OSError:
        return ""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")   # 64MB，导入期少刷盘
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


# ── 规范化（只改写法，不改内容；解析失败一律返回 '' 并交给调用方计数，绝不静默编造） ──

def norm_number(s: str, pad: int | None = None) -> str:
    s = (s or "").strip().upper()
    if pad and s.isdigit() and len(s) < pad:
        s = s.rjust(pad, "0")
    return s


def norm_name(s: str) -> str:
    return " ".join((s or "").split())


def norm_date_dmy(s: str) -> str:
    """DD/MM/YYYY -> YYYY-MM-DD；非法/空 -> ''。"""
    s = (s or "").strip()
    if not s:
        return ""
    p = s.split("/")
    if len(p) == 3 and all(x.isdigit() for x in p):
        d, m, y = p
        if len(y) == 4 and 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{int(m):02d}-{int(d):02d}"
    return ""


def norm_date_mdy8(s: str) -> str:
    """MMDDYYYY(定宽8位) -> YYYY-MM-DD；'00000000'/空/非法 -> ''。"""
    s = (s or "").strip()
    if not s or s == "00000000":
        return ""
    if len(s) == 8 and s.isdigit():
        mm, dd, yyyy = s[0:2], s[2:4], s[4:8]
        if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
            return f"{yyyy}-{mm}-{dd}"
    return ""


def norm_date_iso(s: str) -> str:
    """已是 ISO 的透传校验；非法/空 -> ''。"""
    s = (s or "").strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-" and s[:4].isdigit() and s[5:7].isdigit() and s[8:10].isdigit():
        return s
    return ""


class Progress:
    def __init__(self, label: str, report_every: int = 500_000):
        self.label = label
        self.report_every = report_every
        self.n = 0
        self.t0 = time.time()
        self.last_report = 0

    def tick(self, k: int = 1) -> None:
        self.n += k
        if self.n - self.last_report >= self.report_every:
            self.last_report = self.n
            self.report()

    def report(self) -> None:
        el = time.time() - self.t0
        rate = self.n / el if el > 0 else 0
        print(f"[{self.label}] {self.n:,} rows  {rate:,.0f} rows/s  {el:.0f}s", flush=True)

    def done(self) -> None:
        el = time.time() - self.t0
        print(f"[{self.label}] DONE {self.n:,} rows in {el:.0f}s", flush=True)


INSERT_COMPANY = """
INSERT INTO company
  (jurisdiction, company_number, name, status_raw, entity_type_raw, industry_raw,
   filing_date, dissolution_date, address, agent, source_url, retrieved_at, raw)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(jurisdiction, company_number) DO NOTHING
"""

INSERT_PREV = """
INSERT INTO previous_name (jurisdiction, company_number, former_name, changed_at, src)
VALUES (?,?,?,?,?)
ON CONFLICT(jurisdiction, company_number, former_name, changed_at) DO NOTHING
"""


def stats(conn: sqlite3.Connection, label: str, total_rows: int, n_company: int,
          n_conflict: int, extra: dict | None = None) -> None:
    print(f"\n=== {label} summary ===")
    print(f"source rows     : {total_rows:,}")
    print(f"inserted company: {n_company:,}")
    print(f"conflict-skipped: {n_conflict:,}  (UNIQUE 冲突被 DO NOTHING 跳过)")
    if extra:
        for k, v in extra.items():
            print(f"{k}: {v}")


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
