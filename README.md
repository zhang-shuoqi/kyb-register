# kyb-register

> Global business registration verification for AI agents — unified MCP server built on official government open data.

## What this is

A single MCP tool that lets any AI agent query business registry records across **multiple jurisdictions** through a **unified interface**. Data is sourced directly from government open-data portals — no third-party aggregator, no API keys required (except UK Companies House, which is free to register).

Built with a **GEO adapter architecture**: each jurisdiction gets a small adapter that normalizes its quirks into one consistent output schema. Adding a new country is one new file, no changes to existing code.

## Supported jurisdictions

| Code | Jurisdiction | Source | Records | Auth |
|------|-------------|--------|---------|------|
| `SG` | Singapore | ACRA via data.gov.sg | ~1.5M | None |
| `AU` | Australia | ASIC via data.gov.au | ~3.7M | None |
| `US-FL` | USA (Florida) | Sunbiz SFTP | ~1.3M | None (public creds) |
| `UK` | United Kingdom | Companies House API | ~5.5M | Free key (1 min) |

Total coverage: **~12M+ entities**.

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.10+.

## Usage

### In Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kyb-register": {
      "command": "python",
      "args": ["path/to/server.py"],
      "env": {
        "CH_API_KEY": "your_free_companies_house_key"
      }
    }
  }
}
```

### In any MCP client (stdio)

```bash
python server.py
```

### SSE mode (remote deployment)

```bash
python server.py --transport sse --host 0.0.0.0 --port 8000
```

### UK Companies House API key (free)

Register at [developer.company-information.service.gov.uk/manage-applications](https://developer.company-information.service.gov.uk/manage-applications) — takes 1 minute. No credit card required.

## Tools

### `query_registration`

Query a business entity record from an official government register.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `country` | string | Jurisdiction code: `SG`, `AU`, `US-FL`, `UK` |
| `query` | string | Company name OR registration number |
| `query_type` | string | `name` (fuzzy search) or `number` (exact lookup). Default: `name` |
| `limit` | int | Max results for name search. Default 20, max 100 |

**Example agent prompts:**

- "Is Tesla registered in the UK?"
- "查一下 Singapore Airlines 在新加坡的注册状态"
- "Get the registered agent for Apple Inc in Florida"

**Unified response schema:**

```json
{
  "found": true,
  "country": "SG",
  "query": "Singapore Airlines",
  "count": 3,
  "results": [
    {
      "country": "SG",
      "region": null,
      "registration_number": "01234567X",
      "entity_name": "SINGAPORE AIRLINES LIMITED",
      "entity_type": "Corporation",
      "status": "Active",
      "filing_date": "1972-10-28",
      "dissolution_date": null,
      "registered_agent": null,
      "principal_address": "1 Scotts Road, Singapore 228208",
      "industry_code": "51101",
      "industry_description": "PASSENGER AIR TRANSPORT NSC",
      "officers_count": null,
      "data_source": "SG ACRA data.gov.sg",
      "last_verified": "2026-10-14",
      "raw": { /* original fields from the source */ }
    }
  ]
}
```

Status enum: `Active`, `Inactive`, `Dissolved`, `Merged`, `Liquidation`, `Unknown`

### `list_supported_countries`

Returns all queryable jurisdictions with data-source info, record count, and update frequency. Call this first if unsure which `country` code to use.

## Architecture

```
server.py              ← FastMCP app, exposes 2 tools
normalizers.py         ← Unified schema + cross-GEO status/type mapping
adapters/
  sg_acra.py          ← Singapore ACRA (CKAN JSON API)
  au_asic.py          ← Australia ASIC (CSV download + local scan)
  us_fl_sunbiz.py     ← US Florida Sunbiz (SFTP quarterly snapshots)
  uk_companies_house.py ← UK Companies House (REST API, free key)
```

Each adapter implements two methods:

```python
search_by_name(name: str, limit: int) -> list[dict]
get_by_number(number: str) -> dict | None
```

Raw source data flows through `normalizers.build_unified_record()` which translates country-specific fields into the unified schema before returning to the agent.

## Why this exists

Most agent projects need some form of KYB (Know Your Business) verification — confirming a counterparty exists, is active, and hasn't been dissolved. The data is public in every jurisdiction, but each country exposes it differently (API vs CSV vs SFTP, different field names, different status vocabularies).

This server does the tedious work once, so agent developers can call one tool instead of integrating with N government APIs.

## License

MIT
