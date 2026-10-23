"""SG ACRA full snapshot puller v2 — 27 letter shards via datastore_search.
Self-healing + resumable. Progress: data/sg_progress.json
"""
import csv
import io
import json
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data" / "sg_full.csv"
PROG = Path(__file__).parent / "data" / "sg_progress.json"
LOG = Path(__file__).parent / "data" / "download_sg.log"

SHARDS = [
    "d_8575e84912df3c28995b8e6e0e05205a", "d_3a3807c023c61ddfba947dc069eb53f2",
    "d_c0650f23e94c42e7a20921f4c5b75c24", "d_acbc938ec77af18f94cecc4a7c9ec720",
    "d_124a9bd407c7a25f8335b93b86e50fdd", "d_4526d47d6714d3b052eed4a30b8b1ed6",
    "d_b58303c68e9cf0d2ae93b73ffdbfbfa1", "d_fa2ed456cf2b8597bb7e064b08fc3c7c",
    "d_85518d970b8178975850457f60f1e738", "d_478f45a9c541cbe679ca55d1cd2b970b",
    "d_5573b0db0575db32190a2ad27919a7aa", "d_a2141adf93ec2a3c2ec2837b78d6d46e",
    "d_9af9317c646a1c881bb5591c91817cc6", "d_67e99e6eabc4aad9b5d48663b579746a",
    "d_5c4ef48b025fdfbc80056401f06e3df9", "d_300ddc8da4e8f7bdc1bfc62d0d99e2e7",
    "d_181005ca270b45408b4cdfc954980ca2", "d_4130f1d9d365d9f1633536e959f62bb7",
    "d_2b8c54b2a490d2fa36b925289e5d9572", "d_df7d2d661c0c11a7c367c9ee4bf896c1",
    "d_72f37e5c5d192951ddc5513c2b134482", "d_0cc5f52a1f298b916f317800251057f3",
    "d_e97e8e7fc55b85a38babf66b0fa46b73", "d_af2042c77ffaf0db5d75561ce9ef5688",
    "d_1cd970d8351b42be4a308d628a6dd9d3", "d_31af23fdb79119ed185c256f03cb5773",
    "d_4e3db8955fdcda6f9944097bef3d2724",
]
LIMIT = 1000
API = "https://data.gov.sg/api/action/datastore_search?resource_id={rid}&limit={limit}&offset={offset}"


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_progress():
    if PROG.exists():
        return json.loads(PROG.read_text())
    return {}


def save_progress(p):
    PROG.write_text(json.dumps(p))


def fetch(rid, offset):
    url = API.format(rid=rid, limit=LIMIT, offset=offset)
    req = urllib.request.Request(url, headers={"User-Agent": "kyb-register/0.1"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def main():
    t0 = time.time()
    prog = load_progress()  # {rid: {"offset": N, "done": bool, "header_written": bool}}
    wfile = open(DATA, "a", encoding="utf-8", newline="")
    writer = None
    first_ever = DATA.stat().st_size == 0 if DATA.exists() else True
    grand_total = 0

    for idx, rid in enumerate(SHARDS):
        if rid not in prog:
            prog[rid] = {"offset": 0, "done": False}
        st = prog[rid]  # 引用 prog 内的 dict，修改会真实落盘
        if st.get("done"):
            grand_total += st.get("rows", 0)
            continue
        offset = st.get("offset", 0)
        rows_this = 0
        log(f"shard {idx+1}/27 ({rid[:12]}...) from offset {offset}")
        while not st.get("done"):
            try:
                j = fetch(rid, offset)
            except Exception as e:
                log(f"⚠ {rid[:12]}: {type(e).__name__}; retry in 20s")
                time.sleep(20)
                continue
            records = j["result"]["records"]
            if not writer and records:
                writer = csv.DictWriter(wfile, fieldnames=list(records[0].keys()))
                if first_ever:
                    writer.writeheader()
                    first_ever = False
            if records and writer:
                writer.writerows(records)
                wfile.flush()
            got = len(records)
            offset += got
            rows_this += got
            st["offset"] = offset
            st["rows"] = st.get("rows", 0) + got
            save_progress(prog)
            total = j["result"].get("total", 0)
            if offset >= total or got < LIMIT:
                st["done"] = True
                save_progress(prog)
                log(f"  ✅ shard done: {st['rows']} rows (total={total})")
                grand_total += st["rows"]
                break
            if offset % 20000 < LIMIT:
                log(f"  {offset}/{total} rows")

    wfile.close()
    log(f"🎉 ALL SHARDS COMPLETE: {grand_total} rows in {time.time()-t0:.0f}s")
    Path(__file__).parent.joinpath("data", "done_sg.flag").write_text("ok")


if __name__ == "__main__":
    main()
