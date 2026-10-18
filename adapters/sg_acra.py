"""
🇸🇬 Singapore ACRA (Accounting and Corporate Regulatory Authority)
data.gov.sg 的开放数据集，CKAN datastore_search API。

无需 API key，每月更新一次，每次按字母分卷（A-Z + Others）。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from normalizers import build_unified_record


# data.gov.sg CKAN collection 2（ACRA 业务实体）的 resource_id
# MVP 第一版统一用 Others 卷兜底——它覆盖所有字母分卷合起来的全集，
# 缺点是每次查询会扫全表（较慢），优点是零维护、不会因字母分卷错路由。
# 后续优化：从 https://api-production.data.gov.sg/v2/public/api/collections/2/metadata
# 动态拉取 27 个字母分卷的 resource_id，按公司名首字母精确路由。
_OTHERS_RESOURCE_ID = "d_124a9bd407c7a25f8335b93b86e50fdd"

_BASE = "https://data.gov.sg/api/action/datastore_search"


class SGAcraAdapter:
    country = "SG"
    region = None
    data_source = "SG ACRA data.gov.sg"
    last_verified = "2026-10-14"  # 官方注明的更新日期

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=15.0)

    # ── 用公司名搜索 ──────────────────────────────────────────
    def search_by_name(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        resource_id = _OTHERS_RESOURCE_ID
        params = {
            "resource_id": resource_id,
            "q": name,          # CKAN 全文包含搜索
            "limit": limit,
        }
        resp = self._client.get(_BASE, params=params)
        resp.raise_for_status()
        data = resp.json()
        results: list[dict[str, Any]] = []
        for row in data.get("result", {}).get("records", []):
            results.append(self._normalize(row))
        return results

    # ── 用 UEN 精确查询 ───────────────────────────────────────
    def get_by_number(self, uen: str) -> dict[str, Any] | None:
        # UEN 是唯一主键，理论上全表唯一；但数据集按字母分卷，
        # 所以要在 "Others" 卷里精确过滤（Others 包含非字母开头的实体）
        params = {
            "resource_id": _OTHERS_RESOURCE_ID,
            "filters": json.dumps({"uen": uen}),
            "limit": 1,
        }
        resp = self._client.get(_BASE, params=params)
        resp.raise_for_status()
        data = resp.json()
        records = data.get("result", {}).get("records", [])
        if not records:
            return None
        return self._normalize(records[0])

    # ── 把 ACRA 原始行翻译成统一 schema ──────────────────────
    def _normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        return build_unified_record(
            country=self.country,
            region=self.region,
            registration_number=row.get("uen"),
            entity_name=row.get("entity_name"),
            raw_status=row.get("entity_status_description"),
            raw_entity_type=row.get("entity_type_description"),
            filing_date=row.get("registration_incorporation_date"),
            dissolution_date=None,
            registered_agent=None,  # ACRA 不收集 RA
            address_parts={
                "block": row.get("block"),
                "street_name": row.get("street_name"),
                "level_no": row.get("level_no"),
                "unit_no": row.get("unit_no"),
                "building_name": row.get("building_name"),
                "postal_code": row.get("postal_code"),
                "country": "Singapore",
            },
            industry_code=row.get("primary_ssic_code"),
            industry_description=row.get("primary_ssic_description"),
            officers_count=_int_or_none(row.get("no_of_officers")),
            data_source=self.data_source,
            last_verified=self.last_verified,
            raw=row,
        )

    def close(self) -> None:
        self._client.close()


def _int_or_none(v: Any) -> int | None:
    if v is None or str(v).strip() in ("na", ""):
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None
