"""Fetchers: one script per source that only GitHub's runners reach (gov.il, bechirot.gov.il, cbs.gov.il,
data.gov.il answer the build container with 403).

The shared contract, for every pipeline/fetchers/<name>.py:

    python3 pipeline/fetchers/<name>.py --out DIR

* standard library only (a runner's own Python 3.9 or later, nothing installed);
* writes the raw files it fetched under DIR (e.g. DIR/files/<name>), plus DIR/summary.json and DIR/summary.md:
  what was asked, what answered, what was saved and what it says;
* never raises on a single bad URL (refused, 403, 404, a timeout, an unreadable body): it is recorded in the
  summary and the fetcher goes on;
* finishes within 20 minutes: fetch.yml stops the fetcher at 25 (`timeout -k 30 1500`; the job itself at 30).
  A fetcher has its own clock, --deadline SECONDS (default 1200, from its start): it asks nothing after it, cuts
  a body still coming soon after (a minute at most), records what it did not ask, and writes summary.json and
  summary.md with what it has, its files already saved. A slow source then costs its own part, never the run. A
  long fetcher (cbs.py) also writes the summary as it goes, each write whole (a temporary file, then rename),
  so that even a kill leaves one; and when fetch.yml's limit stops a fetcher anyway (exit 124 or 137), the run
  step writes a stand-in summary.md listing its files when there is none, and pushes them as usual;
* exits 0 unless the script itself crashed.

.github/workflows/fetch.yml runs one fetcher by name, on a request {"workflow": "fetch", "what": "<name>"} pushed
to ops-control (docs/ELECTION_DAY.md, "בקשות דרך ops-control") or on Run workflow, and pushes DIR to the ops-reports
branch as reports/fetch/<name>/<YYYYMMDD-HHMM>/ and reports/fetch/<name>/latest/. The fetcher runs without a token.
A name is lower-case letters, digits and _ and does not start with _ (so this file is never one).
"""
