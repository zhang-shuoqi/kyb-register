"""AU cross-validation v3: SearchByABN.aspx accepts ACN too.
Samples: 3 mid-file rows + BHP + Telstra (world-known real ACNs)."""
import csv
import re
import urllib.request

CSV = r"d:\S.Q\kyb-mcp-server\data\asic_companies.csv"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

SAMPLES = [
    ("129486611", "BULLZIE PTY LTD"),
    ("618039946", "D AND D CO PTY LIMITED"),
    ("659187069", "GT JOHNSON GROUP PTY LTD"),
    ("004028077", "BHP"),
    ("051775556", "TELSTRA"),
]


def read_local(acn: str):
    rows = []
    with open(CSV, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if (row.get("ACN") or "").strip() == acn:
                rows.append(row)
    return rows


def strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", html))


n_match = 0
n_total = 0
for acn, hint in SAMPLES:
    local = read_local(acn)
    if not local:
        print(f"[{acn}] ({hint}) not in local CSV!")
        continue
    cur = local[-1]
    print(f"[{acn}] LOCAL: name={cur['Company Name']!r} status={cur['Status']!r} "
          f"reg={cur['Date of Registration']!r} dereg={cur['Date of Deregistration']!r} abn={cur['ABN']!r}")

    abn_for_query = cur["ABN"] if cur["ABN"].strip() not in ("", "0") else acn
    url = f"https://abr.business.gov.au/SearchByABN.aspx?SearchText={abn_for_query}"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    FETCH FAIL: {type(e).__name__}: {e}")
        continue
    text = strip_tags(html)
    found = {}
    for label in ["Entity name", "ABN", "ABN status", "Entity type", "Goods & Services Tax", "Main business location"]:
        m = re.search(re.escape(label) + r"\s*:?\s*(?:\|\s*)+([^|]{2,90}?)\s*(?:\||$)", text)
        if m:
            found[label] = m.group(1).strip()
    n_total += 1
    if found:
        for k, v in found.items():
            print(f"    REMOTE {k}: {v!r}")
        remote_name = (found.get("Entity name") or "").upper()
        local_name = cur["Company Name"].strip().upper()
        if remote_name and (remote_name == local_name or remote_name in local_name or local_name in remote_name):
            n_match += 1
            print(f"    VERDICT: NAME MATCH")
        else:
            print(f"    VERDICT: name differs (remote={remote_name!r} vs local={local_name!r}) — inspect")
    else:
        idx = text.upper().find(cur["Company Name"].split()[0].upper())
        print(f"    (no labelled fields) snippet: ...{text[max(0, idx-150):idx+250] if idx >= 0 else text[:400]}...")
    print()

print(f"FIELD-LEVEL CROSS-VALIDATION: {n_match}/{n_total} name-matched via ABN Lookup")
