"""FL cross-validation: check 3 active samples against official Sunbiz web search."""
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}

SAMPLES = [
    ("L25000020640", "MARIA DIAZ SERVICES LLC"),
    ("L19000233650", "MAURICIO NAMIAS LLC"),
    ("L15000021030", "SOUTHERN HOLDINGS 9 LLC"),
]

n_ok = 0
for doc, name in SAMPLES:
    url = ("https://search.sunbiz.org/Inquiry/CorporationSearch/SearchResults?"
           + urllib.parse.urlencode({"InquiryType": "EntityName", "searchTerm": name}))
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[{doc}] {name}: FETCH FAIL {type(e).__name__}: {e}")
        continue
    # results rows contain the document number and status text
    doc_hit = doc in html
    name_hit = name.split()[0].upper() in html.upper()
    status_hit = bool(re.search(r"Active", html, re.I))
    # try to pull the detail row snippet around our doc number
    idx = html.find(doc)
    snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html[max(0, idx-300):idx+300])) if idx >= 0 else ""
    print(f"[{doc}] {name}")
    print(f"    doc in results: {doc_hit}, name in results: {name_hit}, 'Active' in page: {status_hit}")
    if snippet:
        print(f"    snippet: {snippet.strip()[:220]}")
    if doc_hit and name_hit:
        n_ok += 1
    print()

print(f"SUNBIZ WEB CROSS-CHECK: {n_ok}/{len(SAMPLES)} verified")
