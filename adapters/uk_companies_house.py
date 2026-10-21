"""
🇬🇧 UK Companies House API
需要免费 API key（developer.company-information.service.gov.uk）。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from normalizers import build_unified_record


BASE = "https://api.company-information.service.gov.uk"


class UKCompaniesHouseAdapter:
    country = "UK"
    region = None
    data_source = "UK Companies House API"
    last_verified = "near real-time"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("CH_API_KEY")
        if not self._api_key:
            raise ValueError(
                "UK Companies House API key required. "
                "Set env var CH_API_KEY or pass api_key parameter. "
                "Free key: https://developer.company-information.service.gov.uk/manage-applications"
            )
        self._client = httpx.Client(timeout=15.0, auth=httpx.BasicAuth(self._api_key, ""))

    def search_by_name(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        resp = self._client.get(
            f"{BASE}/search/companies",
            params={"q": name, "items_per_page": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[dict[str, Any]] = []
        for item in data.get("items", []):
            results.append(self._normalize_search_item(item))
        return results

    def get_by_number(self, company_number: str) -> dict[str, Any] | None:
        resp = self._client.get(f"{BASE}/company/{company_number}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return self._normalize_detail(data)

    def _normalize_search_item(self, item: dict[str, Any]) -> dict[str, Any]:
        roa = item.get("registered_office_address") or {}
        return build_unified_record(
            country=self.country,
            region=self.region,
            registration_number=item.get("company_number"),
            entity_name=item.get("title"),  # search result 里公司名叫 title
            raw_status=item.get("company_status"),
            raw_entity_type=item.get("company_type"),
            filing_date=item.get("date_of_creation"),
            dissolution_date=item.get("date_of_cessation"),
            registered_agent=None,
            address_parts={
                "address_line1": roa.get("address_line_1"),
                "address_line2": roa.get("address_line_2"),
                "city": roa.get("locality"),
                "state": roa.get("region"),
                "postal_code": roa.get("postal_code"),
                "country": roa.get("country"),
            },
            industry_code=(item.get("sic_codes") or [None])[0],
            industry_description=None,
            officers_count=None,
            data_source=self.data_source,
            last_verified=self.last_verified,
            raw=item,
        )

    def _normalize_detail(self, data: dict[str, Any]) -> dict[str, Any]:
        roa = data.get("registered_office_address") or {}
        return build_unified_record(
            country=self.country,
            region=self.region,
            registration_number=data.get("company_number"),
            entity_name=data.get("company_name"),
            raw_status=data.get("company_status"),
            raw_entity_type=data.get("company_type"),
            filing_date=data.get("date_of_creation"),
            dissolution_date=data.get("date_of_cessation"),
            registered_agent=None,
            address_parts={
                "address_line1": roa.get("address_line_1"),
                "address_line2": roa.get("address_line_2"),
                "city": roa.get("locality"),
                "state": roa.get("region"),
                "postal_code": roa.get("postal_code"),
                "country": roa.get("country"),
            },
            industry_code=(data.get("sic_codes") or [None])[0],
            industry_description=None,
            officers_count=None,
            data_source=self.data_source,
            last_verified=self.last_verified,
            raw=data,
        )

    def close(self) -> None:
        self._client.close()
