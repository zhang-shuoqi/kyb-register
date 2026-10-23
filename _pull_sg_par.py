"""SG ACRA puller — PARALLEL (5 workers, one shard each, independent shard files).
Merge at the end. done flag: data/done_sg.flag
"""
import csv
import json
import queue
import threading
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data"
PROG = DATA / "sg_progress.json"
LOG = DATA / "download_sg.log"
FLAG = DATA / "done_sg.flag"
SHARD_DIR = DATA / "sg_shards"
LIMIT = 1000
WORKERS = 10
API = "https://data.gov.sg/api/action/datastore_search?resource_id={rid}&limit={limit}&offset={offset}"

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
LOGLOCK = threading.Lock()


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOGLOCK:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def load_prog():
    p = DATA / "sg_progress_par.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def save_prog(prog):
    (DATA / "sg_progress_par.json").write_text(json.dumps(prog))


def fetch(rid, offset):
    url = API.format(rid=rid, limit=LIMIT, offset=offset)
    req = urllib.request.Request(url, headers={"User-Agent": "kyb-register/0.1"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def worker(q):
    while True:
        try:
            idx, rid = q.get_nowait()
        except queue.Empty:
            return
        shard_file = SHARD_DIR / f"shard_{idx:02d}.csv"
        prog = load_prog()
        st = prog.get(rid, {})
        if st.get("done") and shard_file.exists():
            q.task_done()
            continue
        offset = st.get("offset", 0)
        header_written = shard_file.exists() and shard_file.stat().st_size > 0
        rows = 0
        log(f"W: shard {idx} start at offset {offset}")
        while True:
            try:
                j = fetch(rid, offset)
            except Exception as e:
                log(f"⚠ shard {idx}: {type(e).__name__}; retry in 15s")
                time.sleep(15)
                continue
            records = j["result"]["records"]
            with open(shard_file, "a", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
                if not header_written:
                    w.writeheader()
                    header_written = True
                w.writerows(records)
            got = len(records)
            offset += got
            rows += got
            prog = load_prog()
            prog[rid] = {"offset": offset, "done": offset >= j["result"].get("total", 0) or got < LIMIT}
            save_prog(prog)
            if prog[rid]["done"]:
                log(f"✅ shard {idx}: {offset} rows")
                break
        q.task_done()


def main():
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    q = queue.Queue()
    for i, rid in enumerate(SHARDS):
        q.put((i, rid))
    threads = [threading.Thread(target=worker, args=(q,), daemon=True) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # merge
    log("merging 27 shards -> sg_full.csv")
    with open(DATA / "sg_full.csv", "w", encoding="utf-8", newline="") as out:
        header = None
        for i in range(len(SHARDS)):
            sf = SHARD_DIR / f"shard_{i:02d}.csv"
            with open(sf, "r", encoding="utf-8", newline="") as f:
                rd = csv.reader(f)
                h = next(rd)
                if header is None:
                    header = h
                    out.write(",".join(h) + "\n")
                for row in rd:
                    out.write(",".join(row) + "\n")
    log(f"🎉 ALL DONE: merged in {time.time()-t0:.0f}s")
    FLAG.write_text("ok")


if __name__ == "__main__":
    main()
