"""UK data cross-validation: CSV vs live Companies House API."""
import csv
import io
import zipfile
from pathlib import Path
from dotenv import load_dotenv
import os
import urllib.request
import base64
import json

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
KEY = os.environ.get("CH_API_KEY", "")
d = ROOT / "data" / "uk_snapshot"

# 1. find 3 well-known companies in CSV
samples = []
with zipfile.ZipFile(d / "part1_7.zip") as z:
    with z.open("BasicCompanyData-2026-10-01-part1_7.csv") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
        reader.fieldnames = [fn.strip() for fn in reader.fieldnames]
        for row in reader:
            n = row["CompanyName"].strip()
            if any(k in n for k in ("TESCO", "ROLLS-ROYCE", "GLAXO")) and len(samples) < 3:
                samples.append(row)
            if len(samples) >= 3:
                break

print(f"found {len(samples)} samples in CSV")

# 2. cross-check each against live API
auth = base64.b64encode((KEY + ":").encode()).decode()
for row in samples:
    num = row["CompanyNumber"].strip()
    req = urllib.request.Request(
        f"https://api.company-information.service.gov.uk/company/{num}",
        headers={"Authorization": f"Basic {auth}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            api = json.loads(r.read())
        csv_status = row["CompanyStatus"].strip()
        api_status = api.get("company_status", "?")
        csv_name = row["CompanyName"].strip()
        api_name = api.get("company_name", "?")
        match_status = "MATCH" if csv_status == api_status else "DIFF"
        match_name = "MATCH" if csv_name.upper() == api_name.upper() else "DIFF"
        print(f"\n{num}: {csv_name}")
        print(f"  name   : CSV={csv_name} | API={api_name} -> {match_name}")
        print(f"  status : CSV={csv_status} | API={api_status} -> {match_status}")
        print(f"  API URL: https://find-and-update.company-information.service.gov.uk/company/{num}")
    except Exception as e:
        print(f"{num}: API check failed: {e}")
