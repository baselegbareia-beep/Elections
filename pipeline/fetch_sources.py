"""Download every input of the data build, official sources first.

For each election the official CEC ballot file is tried first:
    https://media2X.bechirot.gov.il/files/expb.csv  ->  data/raw/official/k2X_expb.csv
If the CEC host cannot be reached (it is blocked from some cloud networks),
the normalised public mirror of the same files is used instead and every file
is checked against the mirror's published SHA-256 manifest. build_data.py
prefers data/raw/official/* whenever it exists, and both paths reconcile to
the official national totals.

Every download is recorded in data/raw/fetch_log.json (url, bytes, sha256).

Run: python3 pipeline/fetch_sources.py [--out data/raw]
"""
import argparse
import csv
import hashlib
import io
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELECTIONS = ["K21", "K22", "K23", "K24", "K25"]
OFFICIAL = "https://media{n}.bechirot.gov.il/files/expb.csv"
MIRROR = "https://raw.githubusercontent.com/Yoavfried/israel-election-map/main/public-data/v1/"
MIRROR_FILES = ["manifest.csv", "metadata/parties.csv", "metadata/elections.csv",
                "geographies/localities_2022.zip", "geographies/custom_geographies.zip"] + \
               [f"ballots/{e.lower()}.csv" for e in ELECTIONS]
MANDATES = "https://raw.githubusercontent.com/Yoavfried/israel-election-map/main/data/manual/election_mandates.csv"
POLLS_2026 = "https://raw.githubusercontent.com/amitlev/israel-polls-2026/main/docs/polls-data.js"
SES = "https://raw.githubusercontent.com/harelc/elections-vote-transfer/master/site/data/socioeconomic_clusters.json"


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "kalpi26-data-pipeline"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def save(path, data, url, log):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    log.append({"url": url, "path": os.path.relpath(path, ROOT), "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest()})


def main(out):
    log = []
    official_ok = 0
    for e in ELECTIONS:
        url = OFFICIAL.format(n=e[1:])
        try:
            data = get(url)
            save(os.path.join(out, "official", f"{e.lower()}_expb.csv"), data, url, log)
            official_ok += 1
            print(f"{e}: official file {len(data):,} bytes")
        except Exception as exc:  # network policy, DNS, 4xx/5xx
            print(f"{e}: official source unavailable ({exc.__class__.__name__}); using the mirror")

    mirror_dir = os.path.join(out, "mirror")
    manifest = None
    for rel in MIRROR_FILES:
        data = get(MIRROR + rel)
        if rel == "manifest.csv":
            manifest = {r["path"]: r["sha256"] for r in csv.DictReader(io.StringIO(data.decode("utf-8-sig")))}
        elif manifest and rel in manifest and hashlib.sha256(data).hexdigest() != manifest[rel]:
            raise SystemExit(f"checksum mismatch for {rel}")
        save(os.path.join(mirror_dir, rel), data, MIRROR + rel, log)
    save(os.path.join(out, "election_mandates.csv"), get(MANDATES), MANDATES, log)
    save(os.path.join(out, "polls-data.js"), get(POLLS_2026), POLLS_2026, log)
    save(os.path.join(out, "socioeconomic_clusters.json"), get(SES), SES, log)

    with open(os.path.join(out, "fetch_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    print(f"done: {official_ok}/{len(ELECTIONS)} official ballot files, {len(log)} files logged")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "raw"))
    main(ap.parse_args().out)
