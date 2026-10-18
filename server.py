"""
kyb-mcp-server — Global Business Registration Verification MCP Server

面向 AI agent 的 KYB 企业注册数据查询插件。
统一接口，多 GEO 适配器，零成本开放数据源。

Usage:
    python server.py                # 以 stdio 模式运行（MCP 客户端自动启动）
    python server.py --transport sse # 以 SSE 模式运行（远程部署）
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from fastmcp import FastMCP

from adapters.sg_acra import SGAcraAdapter
from adapters.au_asic import AUAsicAdapter
from adapters.us_fl_sunbiz import USFlSunbizAdapter
from adapters.uk_companies_house import UKCompaniesHouseAdapter


# ── 初始化 MCP server ─────────────────────────────────────────
mcp = FastMCP(
    name="kyb-register",
    description=(
        "Global business registration verification for AI agents. "
        "Query official government registers across multiple jurisdictions "
        "for company status, filing dates, registered agents, and addresses."
    ),
    version="0.1.0",
)

# ── 适配器注册表（country → adapter 实例） ─────────────────────
_adapters: dict[str, Any] = {}


def _init_adapter(country: str) -> Any:
    """按需初始化 adapter（延迟加载，避免启动时全部连上外部 API）。"""
    if country in _adapters:
        return _adapters[country]

    if country == "SG":
        _adapters[country] = SGAcraAdapter()
    elif country == "AU":
        _adapters[country] = AUAsicAdapter()
    elif country == "US-FL":
        _adapters[country] = USFlSunbizAdapter()
    elif country == "UK":
        _adapters[country] = UKCompaniesHouseAdapter()
    else:
        raise ValueError(
            f"Unsupported country: {country}. "
            f"Supported: {', '.join(_SUPPORTED_COUNTRIES)}"
        )
    return _adapters[country]


_SUPPORTED_COUNTRIES = ["SG", "AU", "US-FL", "UK"]


# ── Tool 1: query_registration（统一入口） ────────────────────
@mcp.tool()
def query_registration(
    country: str,
    query: str,
    query_type: str = "name",
    limit: int = 20,
) -> dict[str, Any]:
    """Query a business entity registration record from an official government register.

    Use this tool to verify whether a company is legally registered, check its
    current status, filing date, registered agent, and principal address.
    Data is sourced directly from government open data portals — no third-party aggregator.

    Args:
        country: Jurisdiction code. One of "SG" (Singapore), "AU" (Australia),
            "US-FL" (USA Florida), "UK" (United Kingdom).
        query: The company name OR registration number (UEN for SG, ACN for AU,
            DocNumber for US-FL, company_number for UK).
        query_type: How to interpret `query`. "name" (default) does fuzzy search
            across the register; "number" does exact lookup by registration ID.
        limit: Maximum results when query_type is "name". Default 20, max 100.

    Returns:
        A unified JSON object (or list of objects) with these fields:
        - country, region, registration_number, entity_name
        - entity_type (normalized enum: Corporation, LLC, LP, Partnership, ...)
        - status (normalized enum: Active, Inactive, Dissolved, Merged, Liquidation, Unknown)
        - filing_date, dissolution_date, registered_agent, principal_address
        - industry_code, industry_description, officers_count
        - data_source (exact government source), last_verified (update date)
        - raw (original fields from the source, for advanced use)

    When to call:
        - Verify a counterparty's legal existence before signing a contract
        - Check if a supplier is currently in Good Standing
        - Find the registered agent or official address for service of process
        - Cross-reference a company registration number against official records

    Do NOT call when:
        - You need identity verification of a natural person (use IDV tools instead)
        - You need sanctions screening (use OpenSanctions MCP instead)
        - You need real-time UBO/beneficial ownership tracing
    """
    country = country.strip().upper()
    query = query.strip()
    query_type = query_type.strip().lower()

    if country not in _SUPPORTED_COUNTRIES:
        return {
            "error": f"Unsupported country '{country}'",
            "supported_countries": _SUPPORTED_COUNTRIES,
        }

    if not query:
        return {"error": "query is required"}

    adapter = _init_adapter(country)

    if query_type == "number":
        result = adapter.get_by_number(query)
        if result is None:
            return {"found": False, "country": country, "query": query}
        return {"found": True, "country": country, "result": result}

    # default: search by name
    limit = max(1, min(int(limit), 100))
    results = adapter.search_by_name(query, limit=limit)
    return {
        "found": len(results) > 0,
        "country": country,
        "query": query,
        "count": len(results),
        "results": results,
    }


# ── Tool 2: list_supported_countries（让 agent 知道能查什么） ──
@mcp.tool()
def list_supported_countries() -> dict[str, Any]:
    """Return all jurisdictions this server can query, with data source info.

    Call this first if you are unsure which country code to use, or to confirm
    data freshness and coverage before running a query.
    """
    return {
        "countries": [
            {
                "code": "SG",
                "name": "Singapore",
                "source": "ACRA via data.gov.sg",
                "records": "~1.5M",
                "update_frequency": "Monthly",
                "auth_required": False,
            },
            {
                "code": "AU",
                "name": "Australia",
                "source": "ASIC via data.gov.au",
                "records": "~3.7M",
                "update_frequency": "Weekly",
                "auth_required": False,
            },
            {
                "code": "US-FL",
                "name": "United States (Florida)",
                "source": "Sunbiz SFTP",
                "records": "~1.3M",
                "update_frequency": "Quarterly full + daily delta",
                "auth_required": False,
            },
            {
                "code": "UK",
                "name": "United Kingdom",
                "source": "Companies House API",
                "records": "~5.5M",
                "update_frequency": "Near real-time",
                "auth_required": True,
                "how_to_get_key": "https://developer.company-information.service.gov.uk/manage-applications",
            },
        ],
        "usage_hint": "Use the 'code' field as the country parameter in query_registration.",
    }


# ── 入口 ──────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="kyb-register MCP server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.transport == "stdio":
        # 默认 stdio：MCP 客户端（Claude Desktop / Trae / Cline）自动 spawn 这个进程
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
