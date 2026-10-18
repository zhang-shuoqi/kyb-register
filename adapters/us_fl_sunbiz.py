"""
🇫🇷 US Florida Sunbiz SFTP
公开密码，季度全量快照 + 每日增量事件文件，Pipe 分隔 .txt。
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any

from normalizers import build_unified_record


SFTP_HOST = "sftp.floridados.gov"
SFTP_USER = "Public"
SFTP_PASS = "PubAccess1845!"

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data"
_QUARTERLY_DIR = _CACHE_DIR / "sunbiz_quarterly"


class USFlSunbizAdapter:
    country = "US"
    region = "FL"
    data_source = "US Florida Sunbiz SFTP"
    last_verified = "quarterly"

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else _QUARTERLY_DIR

    # ── 下载季度快照 ──────────────────────────────────────────
    def download_quarterly(self, force: bool = False) -> list[Path]:
        import paramiko

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # 如果已有文件且不是 force，跳过
        existing = list(self._cache_dir.glob("*.txt"))
        if existing and not force:
            print(f"[US-FL] Using cached: {existing}")
            return existing

        print(f"[US-FL] Connecting SFTP {SFTP_HOST} ...")
        transport = paramiko.Transport((SFTP_HOST, 22))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)

        files = sftp.listdir_attr("doc/Quarterly")
        paths: list[Path] = []
        for f in files:
            local = self._cache_dir / f.filename
            print(f"[US-FL] Downloading {f.filename} ({f.st_size} bytes) ...")
            sftp.get(f"doc/Quarterly/{f.filename}", str(local))
            paths.append(local)

        sftp.close()
        transport.close()
        return paths

    # ── 按公司名搜索 ──────────────────────────────────────────
    def search_by_name(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        paths = self.download_quarterly()
        needle = name.strip().upper()
        results: list[dict[str, Any]] = []

        # Sunbiz 季度文件是 Pipe 分隔，CSV 第一行通常是 header
        for p in paths:
            with open(p, "r", encoding="latin-1") as f:
                reader = csv.DictReader(f, delimiter="|")
                for row in reader:
                    legal = (row.get("LegalName") or row.get("legal_name") or "").strip().upper()
                    if needle in legal:
                        results.append(self._normalize(row))
                        if len(results) >= limit:
                            return results
        return results

    def get_by_number(self, doc_number: str) -> dict[str, Any] | None:
        paths = self.download_quarterly()
        for p in paths:
            with open(p, "r", encoding="latin-1") as f:
                reader = csv.DictReader(f, delimiter="|")
                for row in reader:
                    if (row.get("DocNumber") or row.get("doc_number") or "").strip() == doc_number.strip():
                        return self._normalize(row)
        return None

    def _normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        return build_unified_record(
            country=self.country,
            region=self.region,
            registration_number=row.get("DocNumber") or row.get("doc_number"),
            entity_name=row.get("LegalName") or row.get("legal_name"),
            raw_status=row.get("Status") or row.get("status"),
            raw_entity_type=row.get("EntityType") or row.get("entity_type"),
            filing_date=row.get("FilingDate") or row.get("filing_date"),
            dissolution_date=row.get("DissolutionDate") or row.get("dissolution_date"),
            registered_agent=row.get("RegisteredAgentName") or row.get("registered_agent"),
            address_parts={
                "address_line1": row.get("PrincipalAddress1"),
                "address_line2": row.get("PrincipalAddress2"),
                "city": row.get("PrincipalCity"),
                "state": row.get("PrincipalState"),
                "zip_code": row.get("PrincipalZip"),
            },
            industry_code=row.get("NAICS") or row.get("naics"),
            industry_description=row.get("NAICSDescription"),
            officers_count=None,
            data_source=self.data_source,
            last_verified=self.last_verified,
            raw=row,
        )
