"""
跨 GEO 的统一 schema 与映射工具。

所有 adapter 返回的原始数据都经过这里翻译成统一格式，
MCP server 对外只暴露这一种 schema。
"""

from __future__ import annotations

from typing import Any


# ── 统一状态枚举 ────────────────────────────────────────────────
# 每个 GEO adapter 提供 raw status → 这里统一成这六个值之一。

UNIFIED_STATUSES = [
    "Active",          # 正常运营
    "Inactive",        # 不活跃
    "Dissolved",       # 已解散 / 已注销
    "Merged",          # 已合并
    "Liquidation",     # 清算中
    "Unknown",         # 无法映射
]

STATUS_ALIASES: dict[str, str] = {
    # 通用
    "active": "Active",
    "live": "Active",
    "in operation": "Active",
    "current": "Active",
    "registered": "Active",
    "regd": "Active",
    "good standing": "Active",
    # SG ACRA
    "dormant": "Inactive",
    "terminated": "Dissolved",
    "ceased registration": "Dissolved",
    "cancelled": "Dissolved",
    "struck off": "Dissolved",
    # AU ASIC
    "dereg": "Dissolved",
    # UK Companies House
    "dissolved": "Dissolved",
    "liquidation": "Liquidation",
    "merged": "Merged",
    "administration": "Liquidation",
    # FL Sunbiz
    "inactive": "Inactive",
}

# ── 统一实体类型枚举 ──────────────────────────────────────────────

UNIFIED_ENTITY_TYPES = [
    "Corporation",
    "LLC",
    "LP",
    "LLP",
    "Sole Proprietorship",
    "Partnership",
    "Foreign Entity",
    "Other",
]

ENTITY_TYPE_ALIASES: dict[str, str] = {
    # SG ACRA
    "sole proprietorship": "Sole Proprietorship",
    "sole proprietorship/ partnership": "Partnership",
    "partnership": "Partnership",
    "private company limited by shares": "Corporation",
    "public company limited by shares": "Corporation",
    "company limited by guarantee": "Corporation",
    # AU ASIC
    "apty": "Corporation",       # Proprietary Company
    "pub": "Corporation",        # Public Company
    "ptyl": "Corporation",       # Proprietary Limited
    # UK Companies House
    "ltd": "Corporation",
    "plc": "Corporation",
    "llp": "LLP",
    "lp": "LP",
    "overseas": "Foreign Entity",
    # FL Sunbiz
    "profit corporation": "Corporation",
    "foreign profit corporation": "Foreign Entity",
    "limited liability company": "LLC",
    "foreign limited liability company": "Foreign Entity",
    "limited partnership": "LP",
    "foreign limited partnership": "Foreign Entity",
    # 通用缩写（数据供应商经常用缩写）
    "llc": "LLC",
    "ltd": "Corporation",
    "inc": "Corporation",
    "corp": "Corporation",
    "llp": "LLP",
    "lp": "LP",
}


def normalize_status(raw: str | None) -> str:
    """把任意 GEO 的原始状态值翻译成统一枚举。"""
    if not raw:
        return "Unknown"
    key = raw.strip().lower()
    return STATUS_ALIASES.get(key, "Unknown")


def normalize_entity_type(raw: str | None) -> str:
    if not raw:
        return "Other"
    key = raw.strip().lower()
    return ENTITY_TYPE_ALIASES.get(key, "Other")


def normalize_address(parts: dict[str, Any]) -> str | None:
    """把分散的地址字段拼成一个可读字符串。

    接受的 key 会被按顺序拼接（非空才加入）。
    不认识的 key 直接忽略。
    """
    order = [
        "block",
        "building_name",
        "street_name",
        "level_no",
        "unit_no",
        "principal_address",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "region",
        "postal_code",
        "zip_code",
        "country",
    ]
    pieces = []
    for k in order:
        v = parts.get(k)
        if v and str(v).strip() not in ("na", "n/a", "", "none"):
            pieces.append(str(v).strip())
    return ", ".join(pieces) if pieces else None


def build_unified_record(
    *,
    country: str,
    region: str | None,
    registration_number: str | None,
    entity_name: str | None,
    raw_status: str | None,
    raw_entity_type: str | None,
    filing_date: str | None,
    dissolution_date: str | None,
    registered_agent: str | None,
    address_parts: dict[str, Any] | None,
    industry_code: str | None,
    industry_description: str | None,
    officers_count: int | None,
    data_source: str,
    last_verified: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    """组装最终的统一输出记录。"""
    return {
        "country": country,
        "region": region,
        "registration_number": registration_number,
        "entity_name": entity_name,
        "entity_type": normalize_entity_type(raw_entity_type),
        "status": normalize_status(raw_status),
        "filing_date": filing_date,
        "dissolution_date": dissolution_date,
        "registered_agent": registered_agent,
        "principal_address": normalize_address(address_parts or {}),
        "industry_code": industry_code,
        "industry_description": industry_description,
        "officers_count": officers_count,
        "data_source": data_source,
        "last_verified": last_verified,
        "raw": raw,
    }
