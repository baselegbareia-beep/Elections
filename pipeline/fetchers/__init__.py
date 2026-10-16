"""Fetchers: one script per source that only GitHub's runners reach (gov.il, bechirot.gov.il, cbs.gov.il,
data.gov.il answer the build container with 403).

The shared contract, for every pipeline/fetchers/<name>.py:

    python3 pipeline/fetchers/<name>.py --out DIR

* standard library only (a runner's own Python 3.9 or later, nothing installed);
* writes the raw files it fetched under DIR (e.g. DIR/files/<name>), plus DIR/summary.json and DIR/summary.md:
  what was asked, what answered, what was saved and what it says;
* never raises on a single bad URL (refused, 403, 404, a timeout, an unreadable body): it is recorded in the
  summary and the fetcher goes on;
* exits 0 unless the script itself crashed.

.github/workflows/fetch.yml runs one fetcher by name, on a request {"workflow": "fetch", "what": "<name>"} pushed
to ops-control (docs/ELECTION_DAY.md, "בקשות דרך ops-control") or on Run workflow, and pushes DIR to the ops-reports
branch as reports/fetch/<name>/<YYYYMMDD-HHMM>/ and reports/fetch/<name>/latest/. The fetcher runs without a token.
A name is lower-case letters, digits and _ and does not start with _ (so this file is never one).
"""
