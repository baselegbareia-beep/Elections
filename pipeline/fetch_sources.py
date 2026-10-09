"""Download every input of the data build, official sources first.

For each election the official CEC ballot file is tried first:
    https://media2X.bechirot.gov.il/files/expb.csv  ->  data/raw/official/k2X_expb.csv
If the CEC host cannot be reached (it is blocked from some cloud networks),
the normalised public mirror of the same files is used instead and every file
is checked against the mirror's published SHA-256 manifest. build_data.py
(official_path) looks for each election's official file in this order: the
committed copy in data/official/ (stored by .github/workflows/official-data.yml
with its SHA-256 in data/official/fetch_log.json), then a fresh download in
data/raw/official/, then the mirror. So a committed copy takes precedence over
a new download; compare the SHA-256 in the two logs to see whether the CEC file
changed. Both paths reconcile to the official national totals.

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
SNAPSHOTS_K24 = "https://github.com/sapir/israel-votes24-data"


# The CEC hosts sit behind a WAF that rejects unknown clients; a browser-like UA is accepted.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-pipeline"


def get(url, timeout=60, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if "maintenance" in r.geturl():
                    raise IOError(f"redirected to {r.geturl()}")
                return r.read()
        except Exception:
            if i == tries - 1:
                raise


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

    # Snapshots of the official 2021 ballot file taken during election night (git history, one
    # commit per change). The final snapshot is identical to the official file row for row.
    snap = os.path.join(out, "snapshots", "votes24")
    if not os.path.exists(snap):
        import subprocess
        subprocess.run(["git", "clone", "-q", SNAPSHOTS_K24, snap], check=False)
    log.append({"url": SNAPSHOTS_K24, "path": os.path.relpath(snap, ROOT), "bytes": None, "sha256": None})

    with open(os.path.join(out, "fetch_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    print(f"done: {official_ok}/{len(ELECTIONS)} official ballot files, {len(log)} files logged")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "raw"))
    main(ap.parse_args().out)
