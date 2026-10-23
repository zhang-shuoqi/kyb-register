"""SG cross-validation: local shard data vs live data.gov.sg API (3 companies)."""
import csv
import json
import time
import urllib.request
from pathlib import Path

d = Path(r"d:\S.Q\kyb-mcp-server\data\sg_shards")
shard = sorted(d.glob("shard_*.csv"))[0]

# 1. pick 3 well-known-ish companies from local shard (Active ones, decent size names)
samples = []
with open(shard, encoding="utf-8", newline="") as f:
    reader = csv.reader(f)
    header = next(reader)
    idx = {fn: i for i, fn in enumerate(header)}
    for row in reader:
        uen = row[idx["uen"]].strip()
        name = row[idx["entity_name"]].strip()
        status = row[idx["entity_status_description"]].strip()
        reg = row[idx["registration_incorporation_date"]].strip()
        # pick recognizable names: banks/big corp hints, active, real UEN format
        if status == "Live Company" and len(name) > 6 and any(
            k in name.upper() for k in ("BANK", "TELECOM", "AIRLINE", "PROPERTY", "ENGINEERING")
        ) and uen[0].isdigit():
            samples.append({"uen": uen, "name": name, "status": status, "reg": reg})
        if len(samples) >= 3:
            break

print(f"picked {len(samples)} samples from shard_00")
for s in samples:
    print(f"  local: UEN={s['uen']} | {s['name']} | {s['status']} | reg={s['reg']}")

# 2. query live API for each UEN
print()
import urllib.parse

for s in samples:
    try:
        params = urllib.parse.urlencode(
            {
                "resource_id": "d_8575e84912df3c28995b8e6e0e05205a",
                "limit": 5,
                "filters": json.dumps({"uen": s["uen"]}),
            }
        )
        url = "https://data.gov.sg/api/action/datastore_search?" + params
        req = urllib.request.Request(url, headers={"User-Agent": "kyb-register/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read())
        recs = j["result"]["records"]
        if not recs:
            print(f"{s['uen']}: API returned 0 records — MISMATCH")
            continue
        api = recs[0]
        api_name = api.get("entity_name", "?").strip()
        api_status = api.get("entity_status_description", "?").strip()
        api_reg = str(api.get("registration_incorporation_date", "?")).strip()
        name_ok = api_name.upper() == s["name"].upper()
        status_ok = api_status == s["status"]
        reg_ok = api_reg[:10] == s["reg"][:10] or s["reg"][:10] in api_reg
        verdict = "ALL MATCH" if (name_ok and status_ok and reg_ok) else "DIFF"
        print(f"{s['uen']}: {verdict}")
        print(f"  name  : local={s['name']} | api={api_name} -> {'MATCH' if name_ok else 'DIFF'}")
        print(f"  status: local={s['status']} | api={api_status} -> {'MATCH' if status_ok else 'DIFF'}")
        print(f"  reg   : local={s['reg']} | api={api_reg} -> {'MATCH' if reg_ok else 'DIFF'}")
    except Exception as e:
        print(f"{s['uen']}: API FAIL {type(e).__name__} {str(e)[:60]}")
    time.sleep(2)
