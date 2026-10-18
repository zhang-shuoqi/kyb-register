"""
🇦🇺 Australia ASIC (Australian Securities and Investments Commission)
data.gov.au 的公开 CSV，每周更新一次。

下载 URL 固定，是 Tab 分隔的 15 列表，约 370 万行。
MVP 第一版：从 CSV 本地文件查询（先下载、入库）。
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any

import httpx

from normalizers import build_unified_record


CSV_URL = (
    "https://data.gov.au/data/dataset/7b8656f9-606d-4337-af29-66b89b2eeefb/"
    "resource/5c3914e6-413e-4a2c-b890-bf8efe3eabf2/download"
)

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data"
_CACHE_FILE = _CACHE_DIR / "asic_companies.csv"


class AUAsicAdapter:
    country = "AU"
    region = None
    data_source = "AU ASIC data.gov.au"
    last_verified = "weekly"

    def __init__(self, cache_path: str | Path | None = None) -> None:
        self._cache_path = Path(cache_path) if cache_path else _CACHE_FILE
        self._client = httpx.Client(timeout=60.0)

    # ── 下载并缓存 CSV ────────────────────────────────────────
    def download_csv(self, force: bool = False) -> Path:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self._cache_path.exists() and not force:
            print(f"[AU ASIC] Using cached: {self._cache_path}")
            return self._cache_path

        print(f"[AU ASIC] Downloading 3.7M rows from {CSV_URL} ...")
        resp = self._client.get(CSV_URL, follow_redirects=True)
        resp.raise_for_status()
        self._cache_path.write_bytes(resp.content)
        print(f"[AU ASIC] Saved: {self._cache_path} ({len(resp.content)} bytes)")
        return self._cache_path

    # ── 用公司名搜索（线性扫描 CSV） ──────────────────────────
    # MVP 第一版先用简单字符串匹配，数据量大时再考虑 SQLite 索引。
    def search_by_name(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        csv_path = self.download_csv()
        needle = name.strip().upper()
        results: list[dict[str, Any]] = []

        # ASIC CSV 是 Tab 分隔，UTF-8 with BOM
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                company_name = (row.get("Company Name") or "").strip().upper()
                if needle in company_name:
                    results.append(self._normalize(row))
                    if len(results) >= limit:
                        break
        return results

    # ── 用 ACN 精确查询 ───────────────────────────────────────
    def get_by_number(self, acn: str) -> dict[str, Any] | None:
        csv_path = self.download_csv()
        needle = acn.strip()
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                if (row.get("ACN") or "").strip() == needle:
                    return self._normalize(row)
        return None

    # ── 把 ASIC 原始行翻译成统一 schema ──────────────────────
    def _normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        # ASIC 的 "Registered Office Address" 字段可能在原始 CSV 里存在，
        # 但我们手头拿到的 15 列里没它，所以用 State Registration Number 作为辅助。
        return build_unified_record(
            country=self.country,
            region=None,
            registration_number=row.get("ACN"),
            entity_name=row.get("Current Name") or row.get("Company Name"),
            raw_status=row.get("Status"),
            raw_entity_type=row.get("Type"),
            filing_date=_parse_date(row.get("Date of Registration")),
            dissolution_date=_parse_date(row.get("Date of Deregistration")),
            registered_agent=None,  # ASIC CSV 不提供
            address_parts={
                "city": row.get("State Registration Number"),  # 辅助字段
                "country": "Australia",
            },
            industry_code=None,  # ASIC CSV 不含
            industry_description=None,
            officers_count=None,
            data_source=self.data_source,
            last_verified=self.last_verified,
            raw=row,
        )

    def close(self) -> None:
        self._client.close()


def _parse_date(s: str | None) -> str | None:
    """ASIC 日期是 'DD/MM/YYYY' 格式，转成 ISO 'YYYY-MM-DD'。"""
    if not s or not s.strip():
        return None
    try:
        d, m, y = s.strip().split("/")
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    except ValueError:
        return s.strip()
