#!/usr/bin/env python3
"""Smoke test of the election-day feed (pipeline/live_fetch.py), self-contained:

    python3 pipeline/test_live.py

Runs single passes into a temporary folder and checks the JSON contract with the page:
  1. a 2022 dry run on 30% of data/official/k25_expb.csv publishes a valid results.json;
     a lenient read tolerates one inconsistent row and a non-numeric column (OPS-8);
     an unknown 2026 layout: a numeric non-list column, a short total column, the yod spellings
     סמל יישוב / שם יישוב, a '-' in the first row, and the live_config overrides (WF-1);
  2. header-only, BOM+HTML and JSON bodies from the results URL are rejected, no results.json (OPS-2);
     an election_day or eligible that does not parse falls back and is reported (WF-2);
  3. an unchanged file (same SHA-256) is not republished (OPS-9); a changed projection_paused /
     envelopes_expected re-renders it without moving the data time (DOC-3); a file that lost up to 2% of its
     counted stations is accepted without a history point that steps back, one that lost more is rejected (R8);
  4. 2026 mode on a synthetic file with the 2026 ballot letters projects the 2026 lists;
     a counted register above the configured one is reported and shown as 99% (LM-B);
  5. before 22:00 on election day nothing is fetched (a probe only), after 22:00 it is;
     the switches act on the cached file while the CEC file is rejected (DOC-3), and after a run hand-off,
     without the cached file, the pause acts on the published results.json and the rest is reported (R4);
  6. a broken live_input/turnout.json keeps the last good figures and reports the error (OPS-10);
     a typo in an hour or a figure is reported, not dropped silently (DOC-7);
     exit polls appear only after 22:00 and disappear when the input is removed (OPS-14); a poll without
     a §16ה(ב)–(ג) disclosure item is reported (PAGE-F1);
     the 2022-vote-weighted lean is omitted during voting hours;
  6b. per-station releases: live_config column_aliases reach the reader, a semicolon file, a percentage
     column instead of voters, and blank / '-' / 0 figures left out of the national turnout (arab_turnout's rule);
  7. a drill is marked, and a real run discards its files (OPS-3);
  8. the Actions-mode publisher's reset cycle survives another writer on live-data (OPS-1), and the
     laptop takes live_input/ and live_config.json from origin/main every pass (DOC-2);
  8c. branch mode (the owner's Pages setting): site/live/ is committed to main and nothing else, the
     operator's commits on main are kept, a push rejected by a concurrent writer is redone (no rebase);
  8d. the cadence (publish_every_min) and the first results / exit polls at once, also after a failed push;
     a change in timestamps alone (the heartbeat, the probe's time, state.json) waits 30 minutes, 60 from noon
     the day after (R3, WF-9), also at --flush (R2); the Pages build request against a mock API (POST
     /pages/builds, skipped when the push started a build; retried after a failure), the Actions-mode dispatch
     of pages.yml, and the Pages-source auto-detection;
  8e. seeding a run (never from a drill; the cadence carries over, R2; a drill refused over the real files and
     into the poll ban, WF-2), the reset to the placeholder, and one end-to-end pass of live_fetch.py --publish;
     status.json carries heartbeat_s (the quiet gap) and publish_mode;
  9. pipeline/live_config.json still holds the 7,340,000 placeholder after 25.10 (LM-B);
 10. the Arab-society section in turnout.json during voting hours: "arab" and "arab_history" (one entry
     per release, the last 8, with "localities" and "kinds") through a stand-in pipeline/arab_turnout.py,
     a failure keeps the last section, a failed station fetch keeps the last release; the release time:
     sectors_time labels only the release it was set for (a stale one is reported), a new release waits up to
     10 minutes for its time while the polls are open (R1), a release first seen after 22:00 is 22:00, seen_he
     does not change at midnight (R5), another day's releases leave arab_history; then, if both are present, the real
     module on pipeline/make_demo_turnout.py's 14:00 release (its --check unit checks too, and
     site/data/arab_day_demo.json left alone) and on a release with blank figures (the same national turnout);
 11. the workflows: bash -n on every run: block, the daily poll-ban guard on dates around the ban, the
     daily job split (polls-data.js read without a token; the poll-table check on good and broken tables),
     the daily rebuild request retried and red when it keeps failing, build_polls.py reading polls-data.js as
     data only (WF-1), official-data.yml's split (no write token where polls-data.js is read), live.yml's
     year, minutes and drill guard, its reset going red when not published, and the push filters (site/live/**
     starts no workflow);
 11b. the operator's requests on the ops-control branch (ops/request.json, the stand-in for Run workflow and
     Cancel run): the request step of live.yml, discover.yml, net-check.yml, daily.yml and fetch.yml run on sample
     requests (each goes on only for its own, its fields checked as the dispatch inputs; a bad request is red; a fetch
     request without a fetcher's name in `what` is red), fetch.yml's guard (the name again, the file on the commit),
     its run step (the fetcher's output cannot issue workflow commands; a crash is noted, the files still pushed; one
     stopped at the limit, with no summary, gets one listing its files; the limit well inside the job's) and
     its push to ops-reports run against a scratch origin (reports/fetch/<what>/<stamp>/ and latest/, latest replaced,
     the rest of the branch kept, a rejected push redone, nothing else written), the two steps' GNU `timeout -k` and
     `base64 -w0` stood in for (with a note) where this shell has not got them (macOS), a drill
     request through live.yml's guard into the poll ban and a daily request through the ban guard, the groups and
     write targets (main, ops-reports; never the triggering branch), a run from ops-control taking live_input/
     from main, and the "restart" request that ends a running loop, only for a request the requested run will
     take (the same request check, then its guard's drill rule), and only once that run's request job has
     finished (the loop run whole against a stand-in for the runs API), or 3 minutes on; the runbook's request
     command, also when the forced push is refused; and 11b again as the drill's smoke test runs it, in a checkout
     whose ops/request.json is the drill request;
 11c. the 2026 lists: pipeline/reference/lists_2026.json against build_polls (ids, letters), polls_2026.json's
     parties, live_fetch.AGREEMENTS_2026 and live_model.BASE_MAP['K26']; pipeline/fetchers/cec_lists.py against a
     local stand-in for gov.il (the content-pages API, a roster page with other letters, an agreements page, a PDF,
     404 / 500 / refused URLs): exit 0, the summary's comparison, the files stored; then with gov.il answering 403,
     against a stand-in for www.bechirot.gov.il (a home page without links whose scripts name the site's API, robots.txt,
     a sitemap, a Hebrew address, a PDF, an XLSX, a DOCX, a page about the 25th Knesset dated 2026, redirects on the site,
     off it and to itself, JSON nested 5000 deep) and for the Wayback Machine (availability, CDX, raw snapshots): the
     crawl's choices and its gap between requests (redirects too), letters and agreements confirmed by live pages and
     files or by archive snapshots (marked as such), never by a page off the site or about an earlier Knesset,
     lists_2026.json never written, --reread; the crawl's bounds on a 100-page site (a sitemap index of 3000), a 429
     from the archive, the deadline, the site's menus asked once and every page's block; a dripped body cut at the
     deadline, a gzip body unpacked to MAX_FILE at most;
 11d. the fetchers' clock (pipeline/fetchers/__init__.py): cbs.py, cec_lists.py and poll_filings.py each with a
     --deadline at least 3 minutes inside fetch.yml's limit, and with --deadline 0 nothing asked, both summaries
     written, exit 0 (a fetcher without one is noted); cbs.py against a stand-in for census.cbs.gov.il (Jerusalem
     first, the areas that matter in every city before the rest, a cut search asked again one digit longer, the
     deadline stopping part 4 with its city files and a partial summary written) and on a sample catalogue listing
     (taken by name pattern, any case, a subfolder; GEO_MAX files at most; every file not taken named in summary.md).
The drill in live.yml and the daily poll update run this first, with HEALTH_GATE=1: then the checks of the
repository's own state (site/live/status.json and ops/request.json are main's placeholders) are skipped: a run that a
push to ops-control started has the request itself checked out. Runtime about four minutes."""
import contextlib
import datetime as dt
import glob
import html
import http.server
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import urllib.parse
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_fetch as LF  # noqa: E402
from build_data import read_expb  # noqa: E402

ROOT = LF.ROOT
K25 = os.path.join(ROOT, "data", "official", "k25_expb.csv")
TMP = tempfile.mkdtemp(prefix="kalpi26-test-")
IL = LF.IL
DAY = dt.date(2026, 10, 27)
EVENING = dt.datetime(2026, 10, 27, 19, 30, tzinfo=IL)      # polls open
NIGHT = dt.datetime(2026, 10, 27, 22, 30, tzinfo=IL)        # polls closed
LETTERS_2026 = ["מחל", "דרך", "רק", "אמת", "ל", "שס", "ג", "ב", "ט", "ודם", "עם", "ך", "די", "כן", "זך"]
failures = []


def check(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        failures.append(what)


def run(*args, now=None):
    """One pass of live_fetch.main at a (mocked) time; returns the printed status line."""
    buf = io.StringIO()
    real_now = LF.now_il
    if now is not None:
        LF.now_il = lambda: now
    try:
        with contextlib.redirect_stdout(buf):
            LF.main(["--once", *args])
    finally:
        LF.now_il = real_now
    return json.loads(buf.getvalue().strip().splitlines()[-1])


def load(out, name):
    p = os.path.join(out, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))
    return path


# ---------------------------------------------------------------- fixtures
def subset_k25():
    """30% of the 2022 stations (every row with index % 10 < 3), UTF-8 with BOM like the original."""
    lines = open(K25, encoding="utf-8-sig").read().splitlines()
    keep = [lines[0]] + [ln for i, ln in enumerate(lines[1:]) if i % 10 < 3]
    return write(os.path.join(TMP, "k25_30.csv"), "﻿" + "\n".join(keep) + "\n")


def odd_k25(src):
    """The subset with one inconsistent row and an extra non-numeric column."""
    lines = open(src, encoding="utf-8-sig").read().splitlines()
    hdr = lines[0].split(",")
    i_valid = hdr.index("כשרים")
    out = [",".join(hdr + ["שעת עדכון"])]
    for n, ln in enumerate(lines[1:]):
        cells = ln.split(",")
        if n == 7:
            cells[i_valid] = str(int(cells[i_valid]) + 1)       # party votes no longer add up
        out.append(",".join(cells + ["22:31"]))
    return write(os.path.join(TMP, "k25_odd.csv"), "﻿" + "\n".join(out) + "\n")


def variant(src, name, header=None, extra=None, cell=None):
    """The subset with a renamed header (header: {old: new}), an extra column (extra: (name, fn(cells, hdr)))
    or one cell changed (cell: (row index, column, value)). UTF-8 with BOM like the original."""
    lines = open(src, encoding="utf-8-sig").read().splitlines()
    hdr = lines[0].split(",")
    out_hdr = [(header or {}).get(h, h) for h in hdr] + ([extra[0]] if extra else [])
    out = [",".join(out_hdr)]
    for n, ln in enumerate(lines[1:]):
        cells = ln.split(",")
        if cell and n == cell[0]:
            cells[hdr.index(cell[1])] = cell[2]
        if extra:
            cells.append(str(extra[1](cells, hdr)))
        out.append(",".join(cells))
    return write(os.path.join(TMP, name), "﻿" + "\n".join(out) + "\n")


def synthetic_k26(src):
    """2022 votes re-lettered as 2026 lists (the test file the CEC would publish in 2026)."""
    lines = open(src, encoding="utf-8-sig").read().splitlines()
    hdr = lines[0].split(",")
    i_valid = hdr.index("כשרים")
    meta = hdr[:i_valid + 1]
    parties = hdr[i_valid + 1:]
    idx = {p: i_valid + 1 + k for k, p in enumerate(parties)}
    rng = random.Random(2026)
    out = [",".join(meta + LETTERS_2026)]
    for ln in lines[1:]:
        c = ln.split(",")
        v = {p: int(float(c[idx[p]] or 0)) for p in parties}
        kn = v.get("כן", 0)
        d = {"מחל": v.get("מחל", 0), "דרך": round(kn * 0.6), "רק": v.get("פה", 0), "אמת": v.get("אמת", 0) + v.get("מרצ", 0),
             "ל": v.get("ל", 0), "שס": v.get("שס", 0), "ג": v.get("ג", 0), "ב": v.get("ט", 0) // 2,
             "ט": v.get("ט", 0) - v.get("ט", 0) // 2, "ודם": v.get("ום", 0) + v.get("ד", 0), "עם": v.get("עם", 0),
             "כן": kn - round(kn * 0.6)}
        left = int(float(c[i_valid] or 0)) - sum(d.values())     # the small 2022 lists feed the new ones
        a = rng.randint(0, max(0, left))
        b = rng.randint(0, max(0, left - a))
        d.update({"ך": a, "די": b, "זך": left - a - b})
        out.append(",".join(c[:i_valid + 1] + [str(d[p]) for p in LETTERS_2026]))
    return write(os.path.join(TMP, "k26.csv"), "﻿" + "\n".join(out) + "\n")


class Server(http.server.BaseHTTPRequestHandler):
    bodies, hits = {}, []

    def _send(self, head_only=False):
        body = self.bodies.get(self.path, b"nope")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def do_GET(self):
        self.hits.append(("GET", self.path))
        self._send()

    def do_HEAD(self):
        self.hits.append(("HEAD", self.path))
        self._send(head_only=True)

    def log_message(self, *a):
        pass


def serve(bodies):
    Server.bodies = bodies
    srv = http.server.HTTPServer(("127.0.0.1", 0), Server)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def cfg_file(name, **kw):
    base = {"election_day": "2026-10-27", "eligible": 7340000, "projection_paused": False, "envelopes_expected": None}
    return write(os.path.join(TMP, name), {**base, **kw})


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def station_release(src, f, name, seed=0):
    """A per-station turnout release built from the 2022 file: voters = 2022 final voters x f (with a
    little station noise), header like the CEC's ballot file (סמל ישוב, שם ישוב, קלפי, בזב, מצביעים)."""
    lines = open(src, encoding="utf-8-sig").read().splitlines()
    hdr = lines[0].split(",")
    ix = [hdr.index(c) for c in ("סמל ישוב", "שם ישוב", "קלפי", "בזב", "מצביעים")]
    rng = random.Random(seed)
    out = ["סמל ישוב,שם ישוב,קלפי,בזב,מצביעים"]
    for ln in lines[1:]:
        c = ln.split(",")
        if c[ix[0]].strip() in ("9999", "99999"):
            continue
        v = round(int(float(c[ix[4]] or 0)) * f * rng.uniform(0.9, 1.1))
        out.append(",".join([c[ix[0]], c[ix[1]], c[ix[2]], c[ix[3]], str(v)]))
    return write(os.path.join(TMP, name), "﻿" + "\n".join(out) + "\n")


def rework_release(src, name, header=None, delim=",", cells=None):
    """A per-station release (station_release's layout) rewritten: another header (a list), another delimiter,
    or each data row's cells through cells(i, [code, name, kalpi, elig, voters]) -> list."""
    lines = open(src, encoding="utf-8-sig").read().splitlines()
    out = [delim.join(header or lines[0].split(","))]
    for i, ln in enumerate(lines[1:]):
        c = ln.split(",")
        out.append(delim.join(cells(i, c) if cells else c))
    return write(os.path.join(TMP, name), "﻿" + "\n".join(out) + "\n")


def drop_rows(src, name, every):
    """The subset without every `every`-th data row (a results file that lost stations)."""
    lines = open(src, encoding="utf-8-sig").read().splitlines()
    keep = [lines[0]] + [ln for i, ln in enumerate(lines[1:]) if i % every != every - 1]
    return write(os.path.join(TMP, name), "\ufeff" + "\n".join(keep) + "\n")


def blank_some(i, c):
    """Every 5th station without a figure yet, every 50th written '-', every 97th with 0 voters."""
    v = "" if i % 5 == 0 else "-" if i % 50 == 1 else "0" if i % 97 == 2 else c[4]
    return c[:4] + [v]


class Api(http.server.BaseHTTPRequestHandler):
    """A stand-in for the GitHub REST API: the Pages source, the latest Pages build, build requests and
    workflow dispatches. latest = "tip" answers with the commit at the tip of origin's main (the push
    started a build), anything else with an older commit."""
    calls, origin, latest, build_code, build_type = [], "", "old", 201, "legacy"

    def _json(self, code, obj=None):
        body = json.dumps(obj).encode() if obj is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.calls.append(("GET", self.path, self.headers.get("Authorization"), None))
        if self.path.endswith("/pages/builds/latest"):
            tip = sh(["git", "rev-parse", "main"], self.origin) if self.latest == "tip" else "0" * 40
            return self._json(200, {"status": "built", "commit": tip})
        if self.path.endswith("/pages"):
            return self._json(200, {"build_type": self.build_type, "source": {"branch": "main", "path": "/"}})
        self._json(404, {"message": "Not Found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode() if n else ""
        self.calls.append(("POST", self.path, self.headers.get("Authorization"), body))
        if self.path.endswith("/pages/builds"):
            return self._json(self.build_code, {"status": "queued"} if self.build_code == 201 else {"message": "boom"})
        if self.path.endswith("/actions/workflows/pages.yml/dispatches"):
            return self._json(204)
        self._json(404, {"message": "Not Found"})

    def log_message(self, *a):
        pass


class RunsApi(Api):
    """A stand-in for the workflow-runs API that live.yml's loop asks after a restart request (requested_run_ready):
    GET /repos/o/r/actions/runs, filtered by event, branch and head_sha as GitHub filters them, and
    /repos/o/r/actions/runs/{id}/jobs. runs: the run objects; jobs: {run id: [(status, conclusion), ...]}, one state
    per call, the last one repeating; code: a status other than 200 fails every call."""
    runs, jobs, code, calls = [], {}, 200, []

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        self.calls.append((url.path, q, self.headers.get("Authorization")))
        m = re.fullmatch(r"/repos/o/r/actions/runs(?:/(\d+)/jobs)?", url.path)
        if self.code != 200 or not m or (m.group(1) and int(m.group(1)) not in self.jobs):
            return self._json(self.code if self.code != 200 else 404, {"message": "boom" if self.code != 200 else "Not Found"})
        if m.group(1):
            states = self.jobs[int(m.group(1))]
            status, conclusion = states.pop(0) if len(states) > 1 else states[0]
            return self._json(200, {"total_count": 2, "jobs": [{"name": "request", "status": status, "conclusion": conclusion},
                                                               {"name": "feed", "status": "queued", "conclusion": None}]})
        runs = [r for r in self.runs if all(q.get(k, r[f]) == r[f] for k, f in (("event", "event"), ("branch", "head_branch"),
                                                                                 ("head_sha", "head_sha")))]
        self._json(200, {"total_count": len(runs), "workflow_runs": runs})


def load_yaml(path):
    """A workflow file as a dict: PyYAML when installed, else Ruby's YAML (on GitHub's runners), else None."""
    def norm(d):   # YAML 1.1 reads the workflow key `on:` as a boolean (PyYAML: True; JSON via Ruby: "true")
        if isinstance(d, dict) and "on" not in d:
            for k in (True, "true"):
                if k in d:
                    d["on"] = d.pop(k)
        return d
    try:
        import yaml
        return norm(yaml.safe_load(open(path, encoding="utf-8")))
    except ImportError:
        pass
    if shutil.which("ruby"):
        r = subprocess.run(["ruby", "-ryaml", "-rjson", "-e", "puts JSON.dump(YAML.load_file(ARGV[0]))", path],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return norm(json.loads(r.stdout))
    return None


def workflow_steps(doc):
    """(job, step) pairs of a parsed workflow."""
    for job, j in (doc.get("jobs") or {}).items():
        for st in j.get("steps") or []:
            yield job, st


def push_paths(doc):
    on = doc.get("on", doc.get(True)) or {}             # YAML 1.1 reads the key `on` as true
    push = on.get("push") if isinstance(on, dict) else None
    return None if push is None else (push or {}).get("paths")


def path_filter(patterns, path):
    """GitHub's push `paths` filter: the last pattern that matches decides; '!' excludes."""
    import fnmatch
    hit = False
    for p in patterns:
        neg = p.startswith("!")
        if fnmatch.fnmatchcase(path, p.lstrip("!").replace("**", "*")):
            hit = not neg
    return hit


def run_block(script, env, cwd):
    """A workflow run: block under bash -e with the given environment (GITHUB_OUTPUT and friends set, in the
    scratch folder: cwd may be the repository)."""
    out_file = os.path.join(TMP, "gh_output")
    open(out_file, "w").close()
    env_file = os.path.join(TMP, "gh_env")
    open(env_file, "w").close()
    full = {**os.environ, "GITHUB_OUTPUT": out_file, "GITHUB_STEP_SUMMARY": os.path.join(TMP, "gh_summary"),
            "GITHUB_ENV": env_file, **env}
    r = subprocess.run(["bash", "-e", "-c", script], cwd=cwd, env=full, capture_output=True, text=True)
    outputs = dict(ln.split("=", 1) for ln in (open(out_file).read() + open(env_file).read()).splitlines() if "=" in ln)
    return r.returncode, outputs, r.stdout + r.stderr


# the workflows a push of ops/request.json to ops-control starts: (the name a request gives it, the fields it takes)
OPS_REQUESTS = {"live.yml": ("live", "drill reset minutes runner restart"), "discover.yml": ("discover", "mode urls runner"),
                "net-check.yml": ("net-check", ""), "daily.yml": ("daily", ""), "fetch.yml": ("fetch", "what")}
# ops/request.json on main: a request for no workflow. The samples and the scratch origin below use this constant, not
# the checkout's file: a run that a push to ops-control started (the drill's smoke test) has the request checked out
OPS_PLACEHOLDER = {"workflow": "none", "id": "init"}


def ops_placeholder(root):
    """The repository's state (WF-4): ops/request.json in the checkout at `root` is main's placeholder."""
    try:
        req = json.load(open(os.path.join(root, "ops", "request.json"), encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, repr(exc)
    return isinstance(req, dict) and req.get("workflow") == "none", req


def ops_control_in_request_checkout(docs, body):
    """11b as the drill's smoke test runs it: HEALTH_GATE=1, in a checkout of ops-control whose ops/request.json is
    the request `body` (a scratch copy of what 11b reads: docs/, ops/, pipeline/discover.py). Returns the failures
    (taken off the list: the caller reports them in one check), the output and the scratch checkout."""
    global ROOT
    root, wtmp = os.path.join(TMP, "ops_checkout"), os.path.join(TMP, "wf_checkout")
    os.makedirs(wtmp)
    for d in ("docs", "ops"):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(root, d))
    os.makedirs(os.path.join(root, "pipeline"))
    shutil.copy(os.path.join(ROOT, "pipeline", "discover.py"), os.path.join(root, "pipeline"))
    write(os.path.join(root, "ops", "request.json"), body)
    saved, gate, before, buf = ROOT, os.environ.get("HEALTH_GATE"), len(failures), io.StringIO()
    ROOT, os.environ["HEALTH_GATE"] = root, "1"
    try:
        with contextlib.redirect_stdout(buf):
            ops_control(docs, wtmp)
    finally:
        ROOT = saved
        if gate is None:
            os.environ.pop("HEALTH_GATE", None)
        else:
            os.environ["HEALTH_GATE"] = gate
    new = failures[before:]
    del failures[before:]
    return new, buf.getvalue(), root


def tail(log, n):
    """The end of a step's output on one line, for a check's message."""
    return " | ".join(log.strip().splitlines())[-n:]


def gnu_stand_ins(dest):
    """fetch.yml's run and push steps use GNU `timeout -k` and `base64 -w0` (ubuntu runners have both). Where this
    shell has not got them (macOS, a BSD: live.yml's drill may run this file on a self-hosted Mac), portable stand-ins
    go into dest, first on PATH for those two steps only, and a note says so. Returns the names stood in for."""
    names = []
    r = subprocess.run(["bash", "-c", "timeout -k 1 5 true"], capture_output=True)
    if r.returncode != 0:
        write(os.path.join(dest, "timeout"), f"""#!{sys.executable}
# a stand-in for GNU timeout [-k KILL] [-s SIG] DURATION COMMAND...: its exit codes (124 when the time ran out)
import subprocess, sys
a, kill = sys.argv[1:], None
while a and a[0].startswith("-") and a[0] != "--":
    o = a.pop(0)
    if o in ("-k", "-s"):
        v = a.pop(0)
        kill = v if o == "-k" else kill
    elif o.startswith("--kill-after="):
        kill = o.split("=", 1)[1]
a = a[1:] if a and a[0] == "--" else a
secs = lambda s: float(s.rstrip("smhd")) * {{"m": 60, "h": 3600, "d": 86400}}.get(s[-1:], 1)
p = subprocess.Popen(a[1:])
try:
    rc = p.wait(timeout=secs(a[0]))
    sys.exit(rc if rc >= 0 else 128 - rc)
except subprocess.TimeoutExpired:
    p.terminate()
    try:
        p.wait(timeout=secs(kill) if kill else None)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        sys.exit(137)
    sys.exit(124)
""")
        names.append("timeout")
    r = subprocess.run(["bash", "-c", "printf x | base64 -w0"], capture_output=True, text=True)
    if r.returncode != 0 or r.stdout != "eA==":
        write(os.path.join(dest, "base64"), f"#!{sys.executable}\n# a stand-in for GNU base64 -w0 (encode, no line breaks)\n"
              "import base64, sys\nsys.stdout.write(base64.b64encode(sys.stdin.buffer.read()).decode())\n")
        names.append("base64 -w0")
    for n in names:
        os.chmod(os.path.join(dest, n.split()[0]), 0o755)
    if names:
        print(f"  note: no GNU {' or '.join(names)} in this shell: fetch.yml's run and push steps run here with portable "
              f"stand-ins ({dest}); the runners have the real ones")
    return names


def fetch_yml(doc, wtmp):
    """11b, fetch.yml: the shared runner path for pipeline/fetchers/<what>.py. Its jobs and groups, the guard on
    sample names, the run step on stand-in fetchers (one stopped at the limit), and the push to ops-reports against
    a scratch origin; the GNU tools of the two steps stood in for where this shell lacks them."""
    on = doc.get("on", doc.get(True)) or {}
    inp = ((on.get("workflow_dispatch") or {}).get("inputs") or {}).get("what") or {}
    jobs = doc.get("jobs") or {}
    job = jobs.get("fetch") or {}
    conc, fif = job.get("concurrency") or {}, str(job.get("if", ""))
    check("schedule" not in on and inp.get("required") is True and inp.get("type") == "string"
          and doc.get("permissions") == {"contents": "read"} and job.get("permissions") == {"contents": "write"}
          and (jobs.get("request") or {}).get("if") == "github.event_name == 'push'" and job.get("needs") == "request"
          and "!cancelled()" in fif and "needs.request.outputs.run == 'true'" in fif
          and "&& format('fetch-{0}', needs.request.outputs.what || github.event.inputs.what) ||" in str(conc.get("group"))
          and "fetch-skipped-" in str(conc.get("group")) and conc.get("cancel-in-progress") is False,
          f"fetch.yml: no schedule; dispatch with a required `what`; read-only but the fetch job (contents: write); the fetch "
          f"job only for a fetch request, one group per fetcher (a skipped job in a group of its own): {fif} {conc}")
    st = {s_.get("id"): s_ for s_ in job.get("steps") or [] if s_.get("id")}
    co = (job.get("steps") or [{}])[0]
    guard, run_st, pub = st.get("guard") or {}, st.get("run") or {}, st.get("publish") or {}
    token_steps = [s_.get("id") or s_.get("name") for s_ in job.get("steps") or [] if "github.token" in json.dumps(s_)]
    check(str(co.get("uses", "")).startswith("actions/checkout") and (co.get("with") or {}).get("persist-credentials") is False
          and token_steps == ["publish"] and "GH_TOKEN" not in json.dumps(run_st)
          and (guard.get("env") or {}).get("WHAT") == "${{ needs.request.outputs.what || github.event.inputs.what }}"
          and (run_st.get("env") or {}).get("OUT") == (pub.get("env") or {}).get("OUT"),
          f"fetch.yml: a checkout without stored credentials, the token only in the push step ({token_steps}), the name from "
          "the request or the dispatch input")
    pushes = re.findall(r"\bgit(?:auth)?\b[^\n]*?\spush\s[^\n;]*", pub.get("run", ""))
    check(pushes and all("HEAD:refs/heads/ops-reports" in p_ for p_ in pushes) and "ops-reports" in pub.get("run", ""),
          f"fetch.yml: pushes to ops-reports only: {pushes}")

    # the guard: a fetcher's name, and the file on this commit
    gdir = os.path.join(wtmp, "fetch_guard")
    for n in ("cec_lists.py", "__init__.py", "_private.py"):
        write(os.path.join(gdir, "pipeline", "fetchers", n), "")
    for what, code in (("cec_lists", 0), ("cbs_2026", 1), ("__init__", 1), ("_private", 1), ("../cec_lists", 1),
                       ("cec lists", 1), ("cec_lists\nx", 1), ("", 1), ("CEC_LISTS", 1), ("a" * 41, 1)):
        rc, outs, log = run_block(guard.get("run", "false"), {"WHAT": what}, gdir)
        check(rc == code and (code or (outs.get("what") == what and re.fullmatch(r"\d{8}-\d{4}", outs.get("stamp", "")))),
              f"fetch.yml guard, what={what!r}: exit {rc} (want {code}) {outs} {tail(log, 90)}")

    # the run step: what a fetcher prints cannot issue workflow commands; a crash is noted and the step goes on; a
    # fetcher stopped at the limit (timeout's 124) without a summary of its own gets one listing its files
    tools = os.path.join(wtmp, "fetch_tools")
    os.makedirs(tools, exist_ok=True)
    gnu_stand_ins(tools)
    tools_path = tools + os.pathsep + os.environ.get("PATH", "")
    write(os.path.join(gdir, "pipeline", "fetchers", "stub_ok.py"),
          "import os, sys\nout = sys.argv[sys.argv.index('--out') + 1]\nos.makedirs(os.path.join(out, 'files'), exist_ok=True)\n"
          "open(os.path.join(out, 'summary.md'), 'w').write('stub summary\\n')\nprint('::error::from a page')\n")
    write(os.path.join(gdir, "pipeline", "fetchers", "stub_crash.py"), "raise SystemExit(3)\n")
    write(os.path.join(gdir, "pipeline", "fetchers", "stub_stopped.py"),
          "import os, sys\nout = sys.argv[sys.argv.index('--out') + 1]\nos.makedirs(os.path.join(out, 'files'), exist_ok=True)\n"
          "open(os.path.join(out, 'files', 'partial.html'), 'w').write('<p>half</p>')\nraise SystemExit(124)\n")
    summ = os.path.join(TMP, "gh_summary")
    for what, rc_want in (("stub_ok", "0"), ("stub_crash", "3"), ("stub_stopped", "124")):
        out = os.path.join(wtmp, "fetch_out_" + what)
        open(summ, "w").close()
        rc, outs, log = run_block(run_st.get("run", "false"), {"WHAT": what, "STAMP": "20261016-1200", "OUT": out,
                                                               "PATH": tools_path}, gdir)
        stop = re.search(r"^::stop-commands::(\w+)$", log, re.M)
        guarded = bool(stop) and (what != "stub_ok" or (log.index(stop.group(0)) < log.index("::error::from a page")
                                                        < log.index(f"::{stop.group(1)}::")))
        said = open(summ).read()
        own = open(os.path.join(out, "summary.md")).read() if os.path.exists(os.path.join(out, "summary.md")) else ""
        check(rc == 0 and outs.get("rc") == rc_want and guarded
              and (what != "stub_ok" or "## Fetch stub_ok, 20261016-1200" in said and "stub summary" in said)
              and (what != "stub_stopped" or ("stopped at fetch.yml's limit" in log and "- files/partial.html" in own
                                              and "stopped at fetch.yml's limit" in said and "summary.md" not in own.split("by then:")[-1])),
              f"fetch.yml run step, {what}: exit {rc}, rc={outs.get('rc')} (want {rc_want}), the fetcher's output between "
              f"stop-commands and its resume: {guarded}; its summary {own[:120]!r}")
    lim = re.search(r"^\s*timeout -k (\d+) (\d+) python3 \"pipeline/fetchers/\$WHAT\.py\" --out \"\$OUT\"", run_st.get("run", ""), re.M)
    check(lim and int(lim.group(1)) + int(lim.group(2)) <= 60 * int(job.get("timeout-minutes") or 0) - 180,
          f"fetch.yml: the fetcher is stopped (and killed soon after) at least 3 minutes before the job's own limit, the "
          f"push's time: {lim and lim.group(0).strip()[:40]}, timeout-minutes {job.get('timeout-minutes')}")

    # the push: a scratch origin whose ops-reports already holds a discover report
    origin, clone, other = (os.path.join(wtmp, n) for n in ("fetch_origin.git", "fetch_clone", "fetch_other"))
    sh(["git", "init", "-q", "--bare", "-b", "main", origin], wtmp)
    sh(["git", "clone", "-q", origin, other], wtmp)
    for k, v in (("user.email", "op@example.com"), ("user.name", "operator")):
        sh(["git", "config", k, v], other)
    write(os.path.join(other, "README.md"), "main\n")
    sh(["git", "add", "-A"], other)
    sh(["git", "commit", "-q", "-m", "main"], other)
    sh(["git", "push", "-q", "origin", "HEAD:main"], other)
    sh(["git", "checkout", "-q", "--orphan", "rep"], other)
    sh(["git", "rm", "-rfq", "."], other)
    write(os.path.join(other, "reports", "latest.md"), "discover report\n")
    sh(["git", "add", "-A"], other)
    sh(["git", "commit", "-q", "-m", "discover"], other)
    sh(["git", "push", "-q", "origin", "HEAD:ops-reports"], other)
    sh(["git", "clone", "-q", "--depth", "1", "file://" + origin, clone], wtmp)
    main0 = sh(["git", "rev-parse", "refs/heads/main"], origin)
    stub = os.path.join(wtmp, "fetch_stub")
    write(os.path.join(stub, "sleep"), "#!/bin/sh\nexit 0\n")
    os.chmod(os.path.join(stub, "sleep"), 0o755)

    def publish(out_files, stamp, what="cec_lists"):
        out = os.path.join(wtmp, f"fetch_pub_{stamp}_{len(out_files)}")
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        for n, body in out_files.items():
            write(os.path.join(out, n), body)
        return run_block(pub.get("run", "false"), {"WHAT": what, "STAMP": stamp, "OUT": out, "GH_TOKEN": "test-token",
                                                   "RUNNER_TEMP": os.path.join(wtmp, "fetch_rt"),
                                                   "PATH": stub + os.pathsep + tools_path}, clone)

    def tree():
        return set(sh(["git", "ls-tree", "-r", "--name-only", "refs/heads/ops-reports"], origin).split())
    os.makedirs(os.path.join(wtmp, "fetch_rt"), exist_ok=True)
    d = "reports/fetch/cec_lists/"
    rc, _, log = publish({"summary.json": "{}", "summary.md": "one\n", "files/a.html": "<p>a</p>"}, "20261016-1200")
    t1 = tree()
    check(rc == 0 and {"reports/latest.md", d + "20261016-1200/summary.json", d + "20261016-1200/files/a.html",
                       d + "latest/summary.md", d + "latest/files/a.html"} <= t1
          and sh(["git", "rev-parse", "refs/heads/main"], origin) == main0,
          f"fetch.yml push: reports/fetch/<what>/<stamp>/ and latest/ on ops-reports, its other reports kept, main untouched: "
          f"exit {rc} {sorted(t1)[:6]} {tail(log, 120)}")
    rc, _, log = publish({"summary.json": '{"n": 2}', "summary.md": "two\n"}, "20261016-1300")
    t2 = tree()
    check(rc == 0 and d + "latest/files/a.html" not in t2 and d + "20261016-1200/files/a.html" in t2
          and d + "20261016-1300/summary.json" in t2 and "reports/latest.md" in t2,
          f"fetch.yml push, a second run: latest/ replaced (a file the run did not write is gone), the first run's folder kept: "
          f"exit {rc} {tail(log, 100)}")
    head = sh(["git", "rev-parse", "refs/heads/ops-reports"], origin)
    rc, _, log = publish({"summary.json": '{"n": 2}', "summary.md": "two\n"}, "20261016-1300")
    check(rc == 0 and "already has these files" in log and sh(["git", "rev-parse", "refs/heads/ops-reports"], origin) == head,
          f"fetch.yml push, the same files again: no commit: exit {rc} {tail(log, 80)}")
    hook = os.path.join(origin, "hooks", "pre-receive")       # the first push is refused (a writer in between)
    write(hook, '#!/bin/sh\nif [ ! -f "$GIT_DIR/refused-once" ]; then touch "$GIT_DIR/refused-once"; echo refused >&2; exit 1; fi\n')
    os.chmod(hook, 0o755)
    rc, _, log = publish({"summary.json": '{"n": 3}', "summary.md": "three\n"}, "20261016-1400")
    os.remove(hook)
    check(rc == 0 and "push rejected (1)" in log and d + "20261016-1400/summary.json" in tree(),
          f"fetch.yml push, refused once: done again from the tip: exit {rc} {tail(log, 120)}")
    for files, stamp, what, why in (({}, "20261016-1500", "cec_lists", "nothing written"),
                                    ({"summary.md": "x"}, "", "cec_lists", "no stamp"),
                                    ({"summary.md": "x"}, "20261016-1500", "", "no name")):
        rc, _, log = publish(files, stamp, what)
        check(rc == 1, f"fetch.yml push, {why}: red (exit {rc}) {tail(log, 80)}")


def ops_control(docs, wtmp):
    """11b. The operator's requests (docs/ELECTION_DAY.md, "בקשות דרך ops-control"): the session's token can push but
    not dispatch or cancel, so a push of ops/request.json to the ops-control branch stands in for Run workflow. Every
    one of the five workflows reads it in the same step and goes on only when the request names it, its fields
    checked as the dispatch inputs are (the step itself, run here on sample requests); the request's outputs reach
    live.yml's drill guard and daily.yml's poll-ban guard; the working jobs keep their concurrency groups, and a
    request for another workflow can never take a group's pending slot; everything is written to main or
    ops-reports, never to the triggering branch; a run that ops-control started reads live_input/ and
    live_config.json from main; and a later {"restart": true} request ends a running loop (the stand-in for Cancel),
    once the run it started has finished its request job (so that its feed job is pending in the group)."""
    print("11b. ops-control: the request step in the five workflows, its guards, groups, write targets and restart; fetch.yml")
    steps = {}
    for wf, (name, fields) in OPS_REQUESTS.items():
        doc = docs[wf]
        on = doc.get("on", doc.get(True)) or {}
        check(on.get("push") == {"branches": ["ops-control"], "paths": ["ops/request.json"]} and "workflow_dispatch" in on,
              f"{wf}: started by a push of ops/request.json to ops-control (only), and by dispatch: {on.get('push')}")
        found = [(job, s_) for job, s_ in workflow_steps(doc) if s_.get("id") == "request"]
        job, st = found[0] if len(found) == 1 else ("", {})
        env = st.get("env") or {}
        check(len(found) == 1 and env.get("WORKFLOW") == name and str(env.get("FIELDS") or "") == fields,
              f"{wf}: one request step, WORKFLOW={env.get('WORKFLOW')!r} FIELDS={env.get('FIELDS')!r} (want {name!r}, {fields!r})")
        jsteps = ((doc.get("jobs") or {}).get(job) or {}).get("steps") or []
        co = jsteps[0] if jsteps else {}
        check(len(jsteps) > 1 and jsteps[1] is st and str(co.get("uses", "")).startswith("actions/checkout")
              and (co.get("with") or {}).get("sparse-checkout") == "ops" and (co.get("with") or {}).get("persist-credentials") is False
              and ((doc["jobs"][job].get("permissions") or doc.get("permissions")) == {"contents": "read"}),
              f"{wf}: the request is read first, from a checkout of ops/ without stored credentials, in a read-only job ({job})")
        steps[wf] = st
    def commands(block):                           # the block without its comment lines
        return "\n".join(ln for ln in (block or "").splitlines() if not ln.strip().startswith("#"))
    check(len({st.get("run") for wf, st in steps.items() if wf != "fetch.yml"}) == 1
          and len({commands(st.get("run")) for st in steps.values()}) == 1
          and all(st.get("run", "").rstrip().endswith("\npython3 ops/check_request.py ops/request.json") for st in steps.values()),
          "the request step is the same block in live.yml, discover.yml, net-check.yml and daily.yml, the same commands in "
          "fetch.yml, and runs ops/check_request.py")
    for wf in ("pages.yml", "official-data.yml"):
        on = docs[wf].get("on", docs[wf].get(True)) or {}
        check((on.get("push") or {}).get("branches") == ["main"], f"{wf}: pushes to main only (a request starts nothing else)")
    # the checkout's ops/request.json is the repository's state (WF-4): main's placeholder. A run that a push to
    # ops-control started has the request itself checked out (the drill's smoke test, HEALTH_GATE): nothing else in
    # 11b reads it
    if os.environ.get("HEALTH_GATE"):
        print("  skip the checkout's ops/request.json (HEALTH_GATE: a run from ops-control has the request checked out)")
    else:
        ok, req = ops_placeholder(ROOT)
        check(ok, f"ops/request.json on main names no workflow: {req}")

    # the step on sample requests: {workflow file: (exit code, outputs)}; a workflow not named: exit 0 and run=false
    rdir = os.path.join(wtmp, "ops_request")
    os.makedirs(os.path.join(rdir, "ops"), exist_ok=True)
    shutil.copy(os.path.join(ROOT, "ops", "check_request.py"), os.path.join(rdir, "ops"))
    red = {wf: (1, {}) for wf in OPS_REQUESTS}
    cases = [
        (json.dumps(OPS_PLACEHOLDER), {}),
        ('{"workflow": "live", "drill": true, "minutes": 15, "id": "drill-1"}', {"live.yml": (0, {"drill": "true", "minutes": "15"})}),
        ('{"workflow": "live", "reset": true, "id": "r"}', {"live.yml": (0, {"reset": "true"})}),
        ('{"workflow": "live", "minutes": 345, "runner": "ubuntu-latest", "id": "x"}',
         {"live.yml": (0, {"minutes": "345", "runner": "ubuntu-latest"})}),
        ('{"workflow": "live", "restart": true, "minutes": "0345", "runner": "self-hosted"}',
         {"live.yml": (0, {"restart": "true", "minutes": "345", "runner": "self-hosted"})}),
        ('{"workflow": "live", "drill": false, "reset": false}', {"live.yml": (0, {"drill": "false", "reset": "false"})}),
        ('{"workflow": "discover", "id": 7}', {"discover.yml": (0, {})}),
        ('{"workflow": "discover", "mode": "full", "urls": ["https://a.gov.il/x.csv", "https://b.gov.il/"], "runner": "ubuntu-latest"}',
         {"discover.yml": (0, {"mode": "full", "urls": "https://a.gov.il/x.csv https://b.gov.il/", "runner": "ubuntu-latest"})}),
        ('{"workflow": "discover", "mode": "quick", "urls": "https://a.gov.il/1  https://a.gov.il/2"}',
         {"discover.yml": (0, {"mode": "quick", "urls": "https://a.gov.il/1 https://a.gov.il/2"})}),
        ('{"workflow": "net-check", "id": "n1"}', {"net-check.yml": (0, {})}),
        ('{"workflow": "daily", "id": "p1"}', {"daily.yml": (0, {})}),
        ('{"workflow": "fetch", "what": "cec_lists", "id": "f1"}', {"fetch.yml": (0, {"what": "cec_lists"})}),
        ('{"workflow": "fetch", "what": "cbs_2026"}', {"fetch.yml": (0, {"what": "cbs_2026"})}),
        # a fetch names its fetcher: pipeline/fetchers/<what>.py, never a path, an option or a private module
        ('{"workflow": "fetch", "id": "f2"}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": "../live_fetch"}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": "cec_lists.py"}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": "CEC"}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": "__init__"}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": "-h"}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": ""}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": "cec_lists\\nrun=true"}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": ["cec_lists"]}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": 7}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": "' + "a" * 41 + '"}', {"fetch.yml": (1, {})}),
        ('{"workflow": "fetch", "what": "cec_lists", "urls": "https://a.gov.il/"}', {"fetch.yml": (1, {})}),
        ('{"workflow": "live", "what": "cec_lists"}', {"live.yml": (1, {})}),
        ('{"workflow": "discover", "what": "cec_lists"}', {"discover.yml": (1, {})}),
        # red in the workflow it names (a bad field, as Run workflow would refuse it), quiet in the others
        ('{"workflow": "live", "drill": "true"}', {"live.yml": (1, {})}),
        ('{"workflow": "live", "minutes": "4o"}', {"live.yml": (1, {})}),
        ('{"workflow": "live", "minutes": 15.5}', {"live.yml": (1, {})}),
        ('{"workflow": "live", "minutes": -5}', {"live.yml": (1, {})}),
        ('{"workflow": "live", "minute": 15}', {"live.yml": (1, {})}),
        ('{"workflow": "live", "runner": "self-hosted\\nrun=true"}', {"live.yml": (1, {})}),
        # a label no runner has would wait for one, holding the group: only GitHub's servers or the computer in Israel
        ('{"workflow": "live", "runner": "ubuntu-lates"}', {"live.yml": (1, {})}),
        ('{"workflow": "discover", "runner": "self hosted"}', {"discover.yml": (1, {})}),
        ('{"workflow": "live", "mode": "full"}', {"live.yml": (1, {})}),
        ('{"workflow": "discover", "mode": "fast"}', {"discover.yml": (1, {})}),
        ('{"workflow": "discover", "urls": "https://a.gov.il/x\\nrun=true"}', {"discover.yml": (1, {})}),
        ('{"workflow": "discover", "urls": "ftp://a.gov.il/x"}', {"discover.yml": (1, {})}),
        ('{"workflow": "discover", "drill": true}', {"discover.yml": (1, {})}),
        ('{"workflow": "daily", "drill": true}', {"daily.yml": (1, {})}),
        ('{"workflow": "net-check", "runner": "self-hosted"}', {"net-check.yml": (1, {})}),
        # no request at all: red everywhere
        ('{"workflow": "lve"}', red), ('{"drill": true}', red), ('not json', red), ('["live"]', red), (None, red),
    ]
    req_path = os.path.join(rdir, "ops", "request.json")
    for body, want in cases:
        if body is None:
            if os.path.exists(req_path):
                os.remove(req_path)
        else:
            write(req_path, body)
        for wf, st in steps.items():
            code, outs_want = want.get(wf, (0, None))
            outs_want = {"run": "false"} if outs_want is None else ({"run": "true", **outs_want} if code == 0 else {})
            rc, outs, log = run_block(st["run"], {**st["env"], "GITHUB_EVENT_NAME": "push"}, rdir)
            check(rc == code and (outs == outs_want if code == 0 else outs.get("run") != "true"),
                  f"request {str(body)[:70]} in {wf}: exit {rc}, {outs} (want {code}, {outs_want}) {log.strip()[-90:]}")
    for wf, st in steps.items():                   # schedule and dispatch: nothing is read, the run goes on
        rc, outs, _ = run_block(st["run"], {**st["env"], "GITHUB_EVENT_NAME": "schedule"}, rdir)
        check(rc == 0 and outs == {"run": "true"}, f"{wf}: a scheduled run passes the request step: {rc} {outs}")

    # the working jobs: run only for their own request, its fields mapped onto the dispatch inputs, same groups
    for wf in OPS_REQUESTS:
        check(not docs[wf].get("concurrency"), f"{wf}: no workflow-level group (a request for another workflow would take its pending slot)")
    jl = docs["live.yml"]["jobs"]
    feed, fenv = jl.get("feed") or {}, (jl.get("feed") or {}).get("env") or {}
    fif, fconc = str(feed.get("if", "")), feed.get("concurrency") or {}
    check(jl.get("request", {}).get("if") == "github.event_name == 'push'" and feed.get("needs") == "request"
          and "!cancelled()" in fif and "needs.request.outputs.run == 'true'" in fif and "vars.LIVE_FEED_OFF" in fif,
          f"live.yml: the request job only on a push; the feed after it, for a live request or as before: {fif}")
    check("needs.request.outputs.drill == 'true'" in fenv.get("DRILL", "") and "inputs.drill == true" in fenv.get("DRILL", "")
          and "needs.request.outputs.reset == 'true'" in fenv.get("RESET", "") and "inputs.reset == true" in fenv.get("RESET", "")
          and "needs.request.outputs.minutes" in fenv.get("MINUTES", "") and "inputs.minutes" in fenv.get("MINUTES", "")
          and str(feed.get("runs-on", "")).startswith("${{ needs.request.outputs.runner || inputs.runner || vars.LIVE_RUNNER"),
          f"live.yml: the request's drill, reset, minutes and runner in place of the dispatch inputs: {fenv} {feed.get('runs-on')}")
    check("&& 'live-feed' ||" in str(fconc.get("group")) and "needs.request.outputs.run == 'true'" in str(fconc.get("group"))
          and fconc.get("cancel-in-progress") is False, f"live.yml: the feed job in live-feed (a skipped job in a group of its own): {fconc}")
    jd = docs["discover.yml"]["jobs"]
    disc = jd.get("discover") or {}
    denv = next((s_.get("env") or {} for s_ in disc.get("steps") or [] if "discover.py" in (s_.get("run") or "")), {})
    check(jd.get("request", {}).get("if") == "github.event_name == 'push'" and disc.get("needs") == "request"
          and "needs.request.outputs.run == 'true'" in str(disc.get("if")) and "!cancelled()" in str(disc.get("if"))
          and "&& 'discover' ||" in str((disc.get("concurrency") or {}).get("group"))
          and str(disc.get("runs-on", "")).startswith("${{ needs.request.outputs.runner || github.event.inputs.runner")
          and denv.get("MODE", "").startswith("${{ needs.request.outputs.mode || github.event.inputs.mode")
          and denv.get("URLS", "").startswith("${{ needs.request.outputs.urls || github.event.inputs.urls"),
          f"discover.yml: the scan runs for its own request, mode / urls / runner from it, in the discover group: {disc.get('if')} {denv}")
    dj = docs["daily.yml"]["jobs"]
    dguard = next((s_ for s_ in dj["guard"]["steps"] if s_.get("id") == "guard"), {})
    check(dguard.get("if") == "steps.request.outputs.run == 'true'" and "github.event_name" in json.dumps(dguard.get("env"))
          and "&& 'daily-polls' ||" in str((dj["commit"].get("concurrency") or {}).get("group")),
          "daily.yml: the poll-ban guard runs for a daily request (event push, refused like a manual run); the push in daily-polls")
    nprobe = next((s_ for s_ in docs["net-check.yml"]["jobs"]["net-check"]["steps"] if "curl" in (s_.get("run") or "")), {})
    check(nprobe.get("if") == "steps.request.outputs.run == 'true'", "net-check.yml: the probes run for a net-check request only")
    fetch_yml(docs["fetch.yml"], wtmp)

    # a drill request reaches live.yml's guard as the dispatch input does: refused into the poll ban
    lguard = next((s_["run"] for s_ in feed.get("steps") or [] if s_.get("id") == "guard"), "")
    for body, when, code in (('{"workflow": "live", "drill": true, "minutes": 40}', dt.datetime(2026, 10, 23, 22, 0, tzinfo=IL), 0),
                             ('{"workflow": "live", "drill": true, "minutes": 40}', dt.datetime(2026, 10, 23, 23, 10, tzinfo=IL), 1),
                             ('{"workflow": "live", "drill": true}', dt.datetime(2026, 10, 27, 12, 0, tzinfo=IL), 1),
                             ('{"workflow": "live", "drill": true, "reset": true}', dt.datetime(2026, 10, 27, 23, 0, tzinfo=IL), 0),
                             ('{"workflow": "live", "minutes": 345}', dt.datetime(2026, 10, 27, 19, 30, tzinfo=IL), 0)):
        write(req_path, body)
        _, outs, _ = run_block(steps["live.yml"]["run"], {**steps["live.yml"]["env"], "GITHUB_EVENT_NAME": "push"}, rdir)
        rc, gouts, log = run_block(lguard, {"NOW_S": str(int(when.timestamp())), "GITHUB_EVENT_NAME": "push",
                                            "DRILL": str(outs.get("drill") == "true").lower(), "RESET": str(outs.get("reset") == "true").lower(),
                                            "MINUTES": outs.get("minutes", "")}, rdir)
        check(rc == code and (code or gouts.get("MINUTES") == (outs.get("minutes") or "345")),
              f"request {body} at {when:%d.%m %H:%M} through live.yml's guard: exit {rc} (want {code}) {gouts.get('MINUTES')} {log.strip()[-80:]}")

    # writes: main (live.yml: the Pages branch; daily.yml: BRANCH) and ops-reports, never the triggering branch
    for wf in ("live.yml", "daily.yml", "discover.yml", "fetch.yml"):
        refs = [s_.get("name") or s_.get("id") for _, s_ in workflow_steps(docs[wf])
                if re.search(r"GITHUB_REF\b|GITHUB_REF_NAME|github\.ref\b|github\.ref_name|GITHUB_HEAD_REF", json.dumps(s_))]
        check(not refs, f"{wf}: no step uses the triggering ref: {refs}")
    check(fenv.get("INPUT_REF", "").startswith("${{ github.event_name == 'push' && (github.event.repository.default_branch || 'main')")
          and "DEFAULT_BRANCH" in fenv, f"live.yml: inputs from the default branch on a push: {fenv.get('INPUT_REF')}")
    pub = next((s_["run"] for s_ in feed.get("steps") or [] if "PUB_ARGS=" in (s_.get("run") or "")), "")
    check("--branch $pbranch" in pub and "--ref $DEFAULT_BRANCH" in pub and "[ \"$pbranch\" = - ] && pbranch=$DEFAULT_BRANCH" in pub,
          "live.yml: publishes to the Pages branch (else the default branch), pages.yml dispatched on the default branch")
    loop = next((s_["run"] for s_ in feed.get("steps") or [] if "while [" in (s_.get("run") or "")), "")
    check('git checkout -q --no-overlay "origin/$INPUT_REF" -- live_input pipeline/live_config.json' in loop,
          "live.yml: every pass takes live_input/ and live_config.json from origin/$INPUT_REF")
    check(all(((dj[j].get("steps") or [{}])[0].get("with") or {}).get("ref") == "${{ github.event.repository.default_branch || 'main' }}"
              for j in ("build", "commit")) and dj["commit"].get("env", {}).get("BRANCH") == "${{ github.event.repository.default_branch || 'main' }}",
          "daily.yml: builds from main and pushes to main (BRANCH)")
    check(re.search(r'add_argument\("--branch", default="ops-reports"\)', open(os.path.join(ROOT, "pipeline", "discover.py"), encoding="utf-8").read())
          and "--branch" not in json.dumps(disc.get("steps")), "discover.yml: the report goes to ops-reports (discover.py's default)")

    # the runbook's request command (docs/ELECTION_DAY.md), run as written against a scratch origin: ops-control
    # afresh from origin/main, the request with an id, a forced push
    runbook = open(os.path.join(ROOT, "docs", "ELECTION_DAY.md"), encoding="utf-8").read()
    block = re.search(r"```bash\n(REQ='[^\n]*'\ngit -C \.\./ops fetch.*?)```", runbook, re.S)
    check(block and "checkout -q -f -B ops-control origin/main" in block.group(1) and "push -qf origin ops-control" in block.group(1)
          and re.search(r"push -qf origin ops-control\s*\\?\s*\|\| \{ git -C \.\./ops push -q origin --delete ops-control "
                        r"&& git -C \.\./ops push -q origin ops-control; \}", block.group(1)),
          "docs/ELECTION_DAY.md: the request command makes ops-control from origin/main and force-pushes it "
          "(refused: deletes the branch and pushes it anew)")
    scan = re.search(r"```bash\n(REQ='[^\n]*'\ngit -C \.\./ops fetch.*?)```",
                     open(os.path.join(ROOT, "docs", "FILE_DISCOVERY.md"), encoding="utf-8").read(), re.S)
    check(block and scan and scan.group(1).split("\n", 1)[1] == block.group(1).split("\n", 1)[1]
          and '"workflow": "discover"' in scan.group(1).split("\n", 1)[0],
          "docs/FILE_DISCOVERY.md: the same request command, with a discover request")
    origin = os.path.join(wtmp, "ops_origin.git")
    sh(["git", "init", "-q", "--bare", "-b", "main", origin], wtmp)
    editor = os.path.join(wtmp, "ops_editor")             # edits to main (the operator's ../op)
    sess = os.path.join(wtmp, "ops_session")              # the session's checkout; ../ops is its request worktree
    ops_wt = os.path.join(wtmp, "ops")
    for d in (editor, sess):
        sh(["git", "clone", "-q", origin, d], wtmp)
        for k, v in (("user.email", "op@example.com"), ("user.name", "operator")):
            sh(["git", "config", k, v], d)
    write(os.path.join(editor, "live_input", "turnout.json"), '{"national": {"10:00": 15.2}}')
    write(os.path.join(editor, "pipeline", "live_config.json"), '{"github_feed": true}')
    write(os.path.join(editor, "ops", "request.json"), json.dumps(OPS_PLACEHOLDER))
    shutil.copy(os.path.join(ROOT, "ops", "check_request.py"), os.path.join(editor, "ops"))
    sh(["git", "add", "-A"], editor)
    sh(["git", "commit", "-q", "-m", "main"], editor)
    sh(["git", "push", "-q", "origin", "HEAD:main"], editor)
    sh(["bash", "-c", "git fetch -q origin main && git worktree add -q --detach ../ops origin/main"], sess)

    def request(body, stray=False):
        """One request with the runbook's command; the new ops-control tip."""
        script = re.sub(r"^REQ='[^\n]*'", lambda _: f"REQ='{body}'", block.group(1) if block else "false", count=1)
        r = subprocess.run(["bash", "-c", script], cwd=sess, capture_output=True, text=True)
        check(r.returncode == 0 and json.load(open(os.path.join(ops_wt, "ops", "request.json"))).get("id"),
              f"the runbook's request command for {body}: exit {r.returncode} {r.stderr.strip()[-120:]}")
        if stray:                                         # a stale input on the branch must not reach the feed
            write(os.path.join(ops_wt, "live_input", "turnout.json"), '{"national": {"10:00": 99}}')
            write(os.path.join(ops_wt, "live_input", "stray.json"), "{}")
            sh(["git", "add", "-A"], ops_wt)
            sh(["git", "commit", "-q", "-m", "stray inputs"], ops_wt)
            sh(["git", "push", "-q", "-f", "origin", "ops-control"], ops_wt)
        return sh(["git", "rev-parse", "HEAD"], ops_wt)

    inputs_step = next((s_["run"] for s_ in feed.get("steps") or [] if s_.get("id") == "inputs"), "")
    check(inputs_step and [s_.get("id") for s_ in feed.get("steps") or []].index("inputs") == 2,
          "live.yml: the inputs step comes right after the checkout")
    run_dir = os.path.join(wtmp, "ops_run")
    rc, outs, _ = run_block(inputs_step, {"INPUT_REF": "main"}, editor)     # no ops-control yet
    check(rc == 0 and outs.get("OPS_SEEN") == "none", f"inputs step without ops-control: OPS_SEEN={outs.get('OPS_SEEN')}")
    tip = request('{"workflow": "live", "minutes": 345, "id": "1"}', stray=True)
    sh(["git", "clone", "-q", "-b", "ops-control", origin, run_dir], wtmp)   # the checkout of the run that push started
    lost = os.path.join(wtmp, "ops_lost")                                   # one whose remote cannot be reached
    sh(["git", "clone", "-q", "-b", "ops-control", origin, lost], wtmp)
    sh(["git", "remote", "set-url", "origin", os.path.join(wtmp, "missing.git")], lost)
    sh(["git", "pull", "-q", "--ff-only", "origin", "main"], editor)        # the operator edits main meanwhile
    write(os.path.join(editor, "live_input", "turnout.json"), '{"national": {"10:00": 15.2, "12:00": 27.9}}')
    write(os.path.join(editor, "live_input", "exit_polls.json"), "{}")
    sh(["git", "add", "-A"], editor)
    sh(["git", "commit", "-q", "-m", "turnout 12:00"], editor)
    sh(["git", "push", "-q", "origin", "HEAD:main"], editor)
    rc, outs, log = run_block(inputs_step, {"INPUT_REF": "main"}, run_dir)
    got = json.load(open(os.path.join(run_dir, "live_input", "turnout.json")))
    check(rc == 0 and got == {"national": {"10:00": 15.2, "12:00": 27.9}} and not os.path.exists(os.path.join(run_dir, "live_input", "stray.json"))
          and os.path.exists(os.path.join(run_dir, "live_input", "exit_polls.json")) and outs.get("OPS_SEEN") == tip,
          f"a run from ops-control takes live_input/ from origin/main (not the branch) and notes the tip: {got} {outs} {log.strip()[-120:]}")
    rc, outs, log = run_block(inputs_step, {"INPUT_REF": "main"}, lost)
    check(rc == 0 and outs.get("OPS_SEEN") == "off" and "::warning::" in log,
          f"inputs step where git cannot reach the remote: a warning, OPS_SEEN={outs.get('OPS_SEEN')} (no restart possible)")

    # restart: a {"workflow": "live", "restart": true} pushed after the run began ends the loop; nothing else does.
    # restart_requested says whether the tip is such a request; the loop then stops once the requested run is ready
    # (requested_run_ready, the end-to-end cases below)
    m = re.search(r"^restart_requested\(\) \{\n.*?^\}\n", loop, re.S | re.M)
    body_ = loop.split("while [", 1)[-1]
    check(m and re.search(r"^requested_run_ready\(\) \{\n.*?^\}\n", loop, re.S | re.M)
          and loop.index("restart_requested()") < loop.index("while [") and loop.index("requested_run_ready()") < loop.index("while [")
          and "restart_requested; then" in body_ and "requested_run_ready; then" in body_,
          "live.yml: the loop asks restart_requested at every pass, then waits for the requested run (requested_run_ready)")
    lperm = feed.get("permissions") or docs["live.yml"].get("permissions") or {}
    check(lperm.get("actions") in ("read", "write") and "GH_TOKEN" in fenv,
          f"live.yml: the feed job's token can read the runs API (actions: {lperm.get('actions')}; GH_TOKEN in its env)")
    # ... and only for a request the requested run will carry out: the request job's own check, then the guard's
    check(m and f"FIELDS='{steps['live.yml']['env']['FIELDS']}'" in m.group(0) and "python3 ops/check_request.py " in m.group(0)
          and "GITHUB_OUTPUT=_req/out" in m.group(0),
          "live.yml: restart_requested checks the request with ops/check_request.py and the request step's FIELDS")
    _, genv, _ = run_block(lguard, {"NOW_S": str(int(EVENING.timestamp())), "GITHUB_EVENT_NAME": "push", "DRILL": "false",
                                    "RESET": "false", "MINUTES": ""}, rdir)
    drill_env = {k: genv.get(k, "") for k in ("DRILL_BAN_S", "DRILL_BACK_S")}
    check(all(v.isdigit() for v in drill_env.values()) and f"ban={drill_env['DRILL_BAN_S']} " in lguard,
          f"live.yml: the guard hands its drill rule (the poll ban) to the loop's restart check: {drill_env}")

    def restart(seen, cwd=run_dir, now=EVENING, env=None):
        rc_, outs_, log_ = run_block((m.group(0) if m else "restart_requested() { return 1; }\n")
                                     + 'if restart_requested; then echo "restart=yes"; else echo "restart=no"; fi\n'
                                     + 'echo "seen=$OPS_SEEN" >> "$GITHUB_OUTPUT"\n',
                                     {"OPS_SEEN": seen, "NOW_S": str(int(now.timestamp())), **(drill_env if env is None else env)}, cwd)
        return rc_ == 0 and "restart=yes" in log_, outs_.get("seen"), log_

    def taken(body, now):
        """Would the run this request starts carry it out, 10 minutes from now? Its request step, then its guard."""
        write(req_path, body)
        rc_, o, _ = run_block(steps["live.yml"]["run"], {**steps["live.yml"]["env"], "GITHUB_EVENT_NAME": "push"}, rdir)
        if rc_ or o.get("run") != "true":
            return False
        rc_, _, _ = run_block(lguard, {"NOW_S": str(int(now.timestamp()) + 600), "GITHUB_EVENT_NAME": "push",
                                       "DRILL": o.get("drill", "false"), "RESET": o.get("reset", "false"), "MINUTES": o.get("minutes", "")}, rdir)
        return rc_ == 0

    t_run = tip
    for body, seen, want in (('{"workflow": "live", "restart": true, "id": "2"}', "start", True),
                             (None, "same", False),
                             ('{"workflow": "live", "restart": true, "id": "3"}', "off", False),
                             ('{"workflow": "discover", "id": "4"}', "start", False),
                             ('{"workflow": "live", "minutes": 345, "id": "5"}', "start", False),
                             ('{"workflow": "live", "restart": "true", "id": "6"}', "start", False),
                             ('{"workflow": "net-check", "restart": true, "id": "7"}', "start", False),
                             ('{"workflow": "live", "restart": true, "reset": true, "id": "8"}', "none", True)):
        new_tip = request(body) if body else sh(["git", "rev-parse", "HEAD"], ops_wt)
        stop, after, _ = restart({"start": t_run, "same": new_tip, "off": "off", "none": "none"}[seen])
        check(stop == want and (seen == "off" or after == new_tip),
              f"restart check, {body or 'the request that started the run'} (seen: {seen}): restart requested={stop} (want {want}), "
              f"seen {str(after)[:8]}")

    # a restart request the requested run would refuse leaves the active run going (a warning; the tip is noted, so
    # it is not read again): a bad field or value (its request job is red), a drill into the poll ban (its guard)
    def at(d, hh, mm):
        return dt.datetime(2026, 10, d, hh, mm, tzinfo=IL)
    d40 = '{"workflow": "live", "restart": true, "drill": true, "minutes": 40}'
    last = None
    for body, now, env, want, what in (
            ('{"workflow": "live", "restart": true, "minutes": "abc"}', EVENING, None, False, "minutes not a number"),
            ('{"workflow": "live", "restart": true, "runner": "self hosted"}', EVENING, None, False, "a runner label with a space"),
            ('{"workflow": "live", "restart": true, "runner": "ubuntu-lates"}', EVENING, None, False, "a runner no one has"),
            ('{"workflow": "live", "restart": true, "bogus": 1}', EVENING, None, False, "a field live does not take"),
            ('{"workflow": "live", "restart": true, "drill": true}', at(27, 12, 0), None, False, "a drill on election day"),
            ('{"workflow": "live", "restart": true, "drill": true, "reset": true}', at(27, 23, 0), None, True, "drill and reset: a reset"),
            (d40, at(23, 22, 0), None, True, "a 40-minute drill at 23.10 22:00"),
            (None, at(23, 22, 56), None, False, "the same at 22:56 (its guard, 10 minutes on, refuses it)"),
            (None, at(23, 23, 10), None, False, "the same at 23:10"),
            (None, at(15, 12, 0), {}, False, "the guard's rule not handed on: no drill restart"),
            ('{"workflow": "live", "restart": true, "minutes": 345, "runner": "self-hosted"}', at(27, 19, 35), None, True,
             "the 19:30 handover onto the computer in Israel")):
        last = body or last
        new_tip = request(body) if body else sh(["git", "rev-parse", "HEAD"], ops_wt)
        stop, after, log = restart(t_run, now=now, env=env)
        agrees = env is not None or stop == taken(last, now)
        check(stop == want and agrees and after == new_tip and (stop or "::warning::ops-control" in log),
              f"restart check, {last} at {now:%d.%m %H:%M} ({what}): restart requested={stop} (want {want}; the requested "
              f"run's request step and guard agree: {agrees}), seen {str(after)[:8]} {' | '.join(log.strip().splitlines())[-110:]}")
    stop, _, _ = restart(t_run, lost)
    check(not stop, "restart check where git cannot reach the remote: no restart")

    # The deferred stop: the requested run takes over only if its feed job is pending in the live-feed group when the
    # active run ends, and it joins the group only once its request job has finished. So after a restart request the
    # loop goes on (its passes keep publishing) and asks the runs API at every pass: it stops once the request job of
    # the live.yml run that the push started is completed with success (then 10 s more), or 3 minutes after it saw
    # the request (a warning; an API failure counts as not finished). The loop step run whole, in the checkout of a
    # run that ops-control started, with live_fetch.py, sleep and the clock stubbed, against a stand-in for the API
    rtip = request('{"workflow": "live", "restart": true, "minutes": 345}')
    stub = os.path.join(wtmp, "loop_stub")
    clock, stub_log = os.path.join(stub, "clock"), os.path.join(stub, "log")
    write(os.path.join(stub, "python3"), '#!/bin/sh\nif [ "$1" = pipeline/live_fetch.py ]; then echo "live_fetch $*" >> "$STUB_LOG"; '
                                         f'printf "%s\\n" "$FAKE_LINE"; exit 0; fi\nexec "{sys.executable}" "$@"\n')
    write(os.path.join(stub, "sleep"), '#!/bin/sh\necho "sleep $1" >> "$STUB_LOG"\nt=$(cat "$FAKE_CLOCK")\necho $((t + $1)) > "$FAKE_CLOCK"\n')
    write(os.path.join(stub, "date"), f'#!/bin/sh\nif [ "$1" = +%s ]; then cat "$FAKE_CLOCK"; exit 0; fi\nexec "{shutil.which("date")}" "$@"\n')
    for n in ("python3", "sleep", "date"):
        os.chmod(os.path.join(stub, n), 0o755)
    api_srv = http.server.HTTPServer(("127.0.0.1", 0), RunsApi)
    threading.Thread(target=api_srv.serve_forever, daemon=True).start()
    t0 = int(EVENING.timestamp())

    def loop_run(seen, runs, jobs, code=200, minutes=10):
        """The loop step from the clock's t0 with OPS_SEEN = seen: (exit code, log, live_fetch.py passes, sleeps,
        seconds on the clock, the API's calls)."""
        RunsApi.runs, RunsApi.jobs, RunsApi.code, RunsApi.calls = runs, jobs, code, []
        write(clock, str(t0))
        write(stub_log, "")
        rc_, _, log_ = run_block(loop, {"OPS_SEEN": seen, "NOW_S": str(t0), **drill_env, "DRILL": "false", "RESET": "false",
                                        "MINUTES": str(minutes), "PUB_ARGS": "", "INPUT_REF": "main", "GH_TOKEN": "test-token",
                                        "GITHUB_REPOSITORY": "o/r", "GITHUB_API_URL": f"http://127.0.0.1:{api_srv.server_address[1]}",
                                        "FAKE_CLOCK": clock, "STUB_LOG": stub_log,
                                        "FAKE_LINE": json.dumps({"changed": False, "published": "unchanged", "errors": []}),
                                        "PATH": stub + os.pathsep + os.environ.get("PATH", "")}, run_dir)
        lines = open(stub_log).read().splitlines()
        passes = [ln for ln in lines if ln.startswith("live_fetch ")]
        return (rc_, log_, sum("--once" in ln for ln in passes) if passes and "--flush" in passes[-1] else -1,
                [int(ln.split()[1]) for ln in lines if ln.startswith("sleep ")], int(open(clock).read()) - t0, list(RunsApi.calls))

    def run_obj(i, path, sha=rtip):
        return {"id": i, "name": path, "path": f".github/workflows/{path}", "event": "push", "head_branch": "ops-control", "head_sha": sha}
    done = [("completed", "success")]
    # the same push starts the other three workflows too, whose request jobs finish at once (a request for live)
    others = [run_obj(11, "discover.yml"), run_obj(12, "net-check.yml"), run_obj(13, "daily.yml")]
    ojobs = {11: done, 12: done, 13: done}
    try:
        for what, seen, runs, jobs, code, minutes, want in (
                ("the request job finishes at the third look", t_run, others + [run_obj(21, "live.yml"), run_obj(22, "live.yml", "0" * 40)],
                 {**ojobs, 21: [("queued", None), ("in_progress", None), ("completed", "success")], 22: done}, 200, 10,
                 ("ready", 2, [45, 45, 10], 100)),
                ("finished when the loop sees the request (a path with its ref)", t_run, [run_obj(23, "live.yml@refs/heads/ops-control")] + others,
                 {**ojobs, 23: done}, 200, 10, ("ready", 0, [10], 10)),
                ("the API fails (HTTP 500)", t_run, [], {}, 500, 10, ("the runs API failed", 4, [45] * 4, 180)),
                ("the request job failed", t_run, others + [run_obj(24, "live.yml")], {**ojobs, 24: [("completed", "failure")]}, 200, 10,
                 ("completed/failure", 4, [45] * 4, 180)),
                ("no live.yml run, only the other workflows'", t_run, others, ojobs, 200, 10, ("no live.yml run", 4, [45] * 4, 180)),
                ("the jobs API fails", t_run, others + [run_obj(25, "live.yml")], ojobs, 200, 10, ("the jobs API failed", 4, [45] * 4, 180)),
                ("no restart request (the tip the run began with)", rtip, others + [run_obj(26, "live.yml")], {**ojobs, 26: done}, 200, 3,
                 ("end", 4, [45] * 4, 180))):
            rc, log, passes, sleeps, secs, calls = loop_run(seen, runs, jobs, code, minutes)
            how, n_pass, n_sleeps, n_secs = want
            said = log.count("ops-control: restart requested")
            if how == "ready":
                ok = "stopping, the requested run takes over" in log and "::warning::" not in log and said == 1
            elif how == "end":
                ok = said == 0 and not calls and "stopping" not in log
            else:
                ok = (said == 1 and "::warning::ops-control: the requested run's request job has not finished" in log
                      and f"({how}" in log)
            # one look at the runs per pass (and one more at the stop): the request's commit, live.yml's runs only
            run_calls = [c for c in calls if c[0] == "/repos/o/r/actions/runs"]
            asked = (all(c[1] == {"event": "push", "branch": "ops-control", "head_sha": rtip} for c in run_calls)
                     and all(c[2] == "Bearer test-token" for c in calls))
            job_calls = {c[0].split("/")[-2] for c in calls if c[0].endswith("/jobs")}
            right_jobs = job_calls <= {str(r["id"]) for r in runs if r["path"].split("@")[0].endswith("/live.yml") and r["head_sha"] == rtip}
            check(rc == 0 and ok and passes == n_pass and sleeps == n_sleeps and secs == n_secs
                  and (how == "end" or (len(run_calls) == n_pass + 1 and asked and right_jobs)),
                  f"restart, the loop end to end, {what}: exit {rc}, {passes} passes (want {n_pass}), sleeps {sleeps} "
                  f"(want {n_sleeps}), stopped after {secs} s (want {n_secs}), {len(run_calls)} runs-API calls, jobs asked of "
                  f"{sorted(job_calls)}; {' | '.join(ln for ln in log.splitlines() if 'ops-control' in ln)[-200:]}")
    finally:
        api_srv.shutdown()

    # the request command when the forced push is refused (a ruleset, or a token without the workflows permission for
    # main's workflow changes): it deletes ops-control and pushes it anew
    sh(["git", "config", "receive.denyNonFastForwards", "true"], origin)
    old = sh(["git", "rev-parse", "refs/heads/ops-control"], origin)
    new_tip = request('{"workflow": "net-check"}')
    remote = sh(["git", "rev-parse", "refs/heads/ops-control"], origin)
    sh(["git", "config", "--unset", "receive.denyNonFastForwards"], origin)
    check(remote == new_tip != old,
          f"the request command after a refused forced push: ops-control made anew at the request ({remote[:8]}, was {old[:8]})")


class GovilMock(http.server.BaseHTTPRequestHandler):
    """A stand-in for gov.il, www.bechirot.gov.il and the Wayback Machine (11c): routes {path or path?query: (status,
    content type, body[, extra headers])}, else dynamic(path) when set (None: 404); an extra "_drip": s sends the body
    8 bytes every s seconds. The headers of every request kept by path, and the time it came (times: [(monotonic,
    path)])."""
    routes, asked, times, dynamic = {}, {}, [], None

    def do_GET(self):
        GovilMock.asked[self.path] = dict(self.headers)
        GovilMock.times.append((time.monotonic(), self.path))
        code, ctype, body, *more = (self.routes.get(self.path) or self.routes.get(self.path.split("?")[0])
                                    or (GovilMock.dynamic and GovilMock.dynamic(self.path)) or (404, "text/html", b"<p>no</p>"))
        body = body if isinstance(body, bytes) else body.encode("utf-8")
        extra = dict(more[0]) if more else {}
        drip = extra.pop("_drip", None)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        try:
            for piece in [body[i:i + 8] for i in range(0, len(body), 8)] if drip else [body]:
                self.wfile.write(piece)
                if drip:
                    self.wfile.flush()
                    time.sleep(drip)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *a):
        pass


def pdf_rows(rows):
    """A one-page PDF whose rows (lists of cells) read back as text (11c): a simple font, a byte a character, its
    ToUnicode map giving the letters; each cell drawn left to right, so a reader may give a Hebrew row backwards
    (pdftotext does: cec_lists.orient turns it around)."""
    chars = sorted({ch for r in rows for c in r for ch in c})
    code = {ch: i + 1 for i, ch in enumerate(chars)}
    cmap = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /T def /CMapType 2 def\n"
            "1 begincodespacerange <01> <FF> endcodespacerange\n" + f"{len(chars)} beginbfchar\n"
            + "".join(f"<{code[ch]:02X}> <{ord(ch):04X}>\n" for ch in chars)
            + "endbfchar endcmap CMapName currentdict /CMap defineresource pop end end\n").encode()
    ops, y = ["BT /F1 12 Tf"], 750
    for r in rows:
        x = 60
        for c in r:
            ops.append(f"1 0 0 1 {x} {y} Tm <{''.join(f'{code[ch]:02X}' for ch in c)}> Tj")
            x += 7 * len(c) + 60
        y -= 20
    content = "\n".join(ops + ["ET"]).encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 1 /LastChar %d /Widths [%s] /ToUnicode 6 0 R >>"
            % (len(chars), b" ".join(b"600" for _ in chars)),
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(cmap), cmap)]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, o)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def xlsx_rows(rows):
    """A minimal XLSX (shared strings, one sheet) of rows (11c)."""
    strs = sorted({c for r in rows for c in r})
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{html.escape(s_)}</t></si>" for s_ in strs) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>" + "".join(
            "<row>" + "".join(f'<c t="s"><v>{strs.index(c)}</v></c>' for c in r) + "</row>" for r in rows) + "</sheetData></worksheet>")
    return buf.getvalue()


def docx_rows(paras, rows):
    """A minimal DOCX of paragraphs and one table (11c)."""
    def p(t):
        return f"<w:p><w:r><w:t>{html.escape(t)}</w:t></w:r></w:p>"
    body = "".join(map(p, paras)) + "<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in r) + "</w:tr>"
                                                         for r in rows) + "</w:tbl>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                                        f"<w:body>{body}</w:body></w:document>")
    return buf.getvalue()


def wayback_mock(closest, cdx, snaps, refuse=None):
    """GovilMock.dynamic for 11c: /govil/... answers 403 (gov.il's WAF); /arch/wayback/available the closest snapshot
    {address: closest}; /wb/cdx/search/cdx the rows {url param: [header, rows...]}; /wb/web/<ts>id_/<address> the
    snapshot {address: (status, type, body)}; refuse=(status, ...) for every archive.org request instead."""
    def dyn(path):
        u = urllib.parse.urlsplit(path)
        q = urllib.parse.parse_qs(u.query)
        if path.startswith("/govil/"):
            return 403, "text/html", "<html><body>Access Denied</body></html>"
        if refuse and path.startswith(("/arch/", "/wb/")):
            return refuse
        if u.path == "/arch/wayback/available":
            c = closest.get(q.get("url", [""])[0])
            return 200, "application/json", json.dumps({"url": q.get("url", [""])[0], "archived_snapshots": {"closest": c} if c else {}})
        if u.path == "/wb/cdx/search/cdx":
            return 200, "application/json", json.dumps(cdx.get(q.get("url", [""])[0], []))
        m = re.match(r"/wb/web/(\d{14})id_/(.+)$", path)
        return snaps.get(m.group(2)) if m else None
    return dyn


def lists_2026():
    """11c. The 2026 lists: the reference file against the code, then pipeline/fetchers/cec_lists.py offline."""
    print("11c. the 2026 lists: pipeline/reference/lists_2026.json against the code; pipeline/fetchers/cec_lists.py offline")
    import build_polls as BP
    ref_path = os.path.join(ROOT, "pipeline", "reference", "lists_2026.json")
    ref = json.load(open(ref_path, encoding="utf-8"))
    lists = ref.get("lists") or []
    letters = [e.get("letters") for e in lists]
    modelled = [e for e in lists if e.get("id")]
    by_id = {e["id"]: e for e in modelled}
    check(len(lists) == 38 and len(set(letters)) == 38 and all(isinstance(x, str) and re.fullmatch("[א-ת]{1,4}", x) for x in letters)
          and len({e.get("cec_key") for e in lists}) == 38,
          f"lists_2026.json: 38 lists, each with its own letters and CEC page: {len(lists)} lists, {len(set(letters))} letters")
    check(len(modelled) == len(by_id) and set(by_id) == set(BP.PARTIES_2026)
          and all(by_id[k]["letters"] == BP.LETTERS_2026[k] for k in by_id),
          f"lists_2026.json: the modelled lists are build_polls.PARTIES_2026, with build_polls.LETTERS_2026: "
          f"{sorted(k for k in by_id if by_id[k]['letters'] != BP.LETTERS_2026.get(k))}")
    check(all(by_id[k].get("leader") == BP.PARTIES_2026[k][1] for k in by_id),
          f"lists_2026.json: the leaders are build_polls': {[k for k in by_id if by_id[k].get('leader') != BP.PARTIES_2026[k][1]]}")
    polls = json.load(open(os.path.join(ROOT, "site", "data", "polls_2026.json"), encoding="utf-8"))
    parties = [{"id": k, "name": v[0], "leader": v[1], "bloc": v[2], "color": v[3], "dark": v[4], "letters": BP.LETTERS_2026.get(k, "")}
               for k, v in BP.PARTIES_2026.items()]
    check(polls.get("parties") == parties, "site/data/polls_2026.json: its parties are build_polls' (names, leaders, letters)")
    ag = ref.get("agreements") or []
    pairs_ref = {frozenset(a.get("ids") or []) for a in ag}
    pairs_code = {frozenset(p_) for p_ in LF.AGREEMENTS_2026}
    in_two = [k for k in by_id if sum(k in p_ for p_ in LF.AGREEMENTS_2026) > 1]
    check(pairs_ref == pairs_code and len(pairs_code) == len(LF.AGREEMENTS_2026) and all(len(p_) == 2 for p_ in pairs_code)
          and not in_two and all(set(p_) <= set(BP.PARTIES_2026) for p_ in pairs_code),
          f"live_fetch.AGREEMENTS_2026 is lists_2026.json's agreements, each list in one at most: "
          f"{sorted(map(sorted, pairs_code ^ pairs_ref))} {in_two}")
    partner = {}
    for a in ag:
        x, y = a.get("lists") or ["", ""]
        partner[x], partner[y] = y, x
    check(all({by_id[i]["letters"] for i in a["ids"]} == set(a["lists"]) and a.get("sources") for a in ag)
          and all(e.get("agreement") == partner.get(e["letters"]) for e in modelled)
          and not {n.get("id") for n in ref.get("no_agreement") or []} & {i for a in ag for i in a["ids"]},
          "lists_2026.json: each agreement's letters are its lists', with sources; every modelled list names its partner (or none)")
    check(set(LF.LM.BASE_MAP["K26"]) == set(BP.PARTIES_2026), f"live_model.BASE_MAP['K26'] maps exactly the modelled lists: "
          f"{sorted(set(LF.LM.BASE_MAP['K26']) ^ set(BP.PARTIES_2026))}")
    urls = [s_ for s_ in re.findall(r'"(https?://[^"]*)"', open(ref_path, encoding="utf-8").read())]
    check(urls and all(u.startswith("https://") and " " not in u for u in urls)
          and all(e["letter_sources"] for e in lists if e["verified"]["letters"])
          and all(isinstance(v, bool) for e in lists for v in e["verified"].values()),
          f"lists_2026.json: every source an https address ({len(urls)}), verified letters with their sources, flags true or false")
    # the page has its own copy of the agreements (site/src/js/core.js): the same pairs as the feed
    core = open(os.path.join(ROOT, "site", "src", "js", "core.js"), encoding="utf-8").read()
    m = re.search(r"const AGREEMENTS_2026 = (\[.*?\]);", core)
    page = {frozenset(a or b for a, b in re.findall(r""""([^"]*)"|'([^']*)'""", p_)) for p_ in re.findall(r"\[([^\[\]]+)\]", m.group(1))} if m else set()
    check(page == pairs_code, f"site/src/js/core.js AGREEMENTS_2026 is live_fetch.AGREEMENTS_2026 (the page lacks "
          f"{sorted(map(sorted, pairs_code - page))}, has {sorted(map(sorted, page - pairs_code))} beyond it)")
    # the Arabic version keys its dictionaries by the Hebrew UI strings: every key still used in site/src/js
    p_ = __import__("check_i18n").problems()
    check(not p_, f"pipeline/check_i18n.py: the Arabic dictionaries match the Hebrew sources {p_[:5]}")

    # the fetcher against a stand-in for gov.il: client-config.js, the content-pages API, files, a catalogue
    srv = http.server.HTTPServer(("127.0.0.1", 0), GovilMock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    api = "/api/api/content-pages/"
    lk, ya, bw = (next(e for e in lists if e.get("id") == i) for i in ("Likud", "Yashar", "National Unity"))
    res_ = next(e for e in lists if e.get("id") == "Reservists")
    page_json = lambda title, html_: json.dumps({"contentHead": {"title": title}, "contentMain": {"htmlContents": [{"sectionData": html_}]}},
                                                ensure_ascii=False)
    GovilMock.asked, GovilMock.times, GovilMock.dynamic = {}, [], None
    GovilMock.routes = {
        "/govil/ContentpageWebApi/client-config.js": (200, "application/javascript",
                                                     "window['govilRunConfig'] = {\"contentPageWebApi\": \"https://api.example.gov.il/content\", "
                                                     "\"clientId\": \"cid-test\"};"),
        api + "candidates-lists-26?culture=he": (200, "application/json", page_json(
            "רשימות המועמדים לכנסת ה-26", '<p>הרשימות שאושרו</p><a href="/BlobFolder/guide/candidates-lists-26/he/Approved%20Voting%20Slips.pdf">'
            'פתקי ההצבעה</a> <a href="/he/pages/heskem-26">הודעה על הסכמי עודפים</a> <a href="https://elsewhere.example.com/x.pdf">הסכמי עודפים (עותק)</a>'
            f'<a href="?chapterIndex=2">פרק 2</a><a href="/he/pages/{lk["cec_key"]}">הליכוד</a><a href="/he/pages/new-party_list39">חדשה</a>')),
        api + "candidates-lists-26?culture=he&chapterIndex=2": (200, "application/json", page_json(
            "רשימות", f"<table><tr><td>{lk['letters']}</td><td>{lk['official_name']}</td></tr></table>")),
        api + "heskem-26?culture=he": (200, "application/json", page_json("הסכמי עודפים", (
            "<h2>הסכמי עודפים בין רשימות המועמדים</h2><table>"
            "<tr><td>הליכוד בהנהגת בנימין נתניהו לראשות הממשלה</td><td>הציונות הדתית בראשות בצלאל סמוטריץ' וזהות</td></tr>"
            "<tr><td>ש\"ס</td><td>יהדות התורה</td></tr>"
            f"<tr><td>{bw['official_name']}</td><td>{res_['official_name']}</td></tr></table>"))),
        api + lk["cec_key"] + "?culture=he": (200, "application/json", page_json(lk["official_name"], f"<p>אותיות הרשימה: {lk['letters']}</p>")),
        api + ya["cec_key"] + "?culture=he": (200, "application/json", page_json(ya["official_name"], "<p>אותיות הרשימה: דרכ</p>")),
        api + bw["cec_key"] + "?culture=he": (500, "text/html", "<p>error</p>"),
        "/govil/BlobFolder/guide/candidates-lists-26/he/Approved%20Voting%20Slips.pdf": (200, "application/pdf", b"%PDF-1.4 slips"),
        "/govil/he/pages/candidates-lists-26": (200, "text/html", "<html><head><title>gov.il</title></head><body><app-root></app-root></body></html>"),
        "/data/api/3/action/package_search": (200, "application/json", json.dumps({"result": {"results": [
            {"title": "הסכמי עודפים לכנסת ה-26", "resources": [{"name": "odafim", "url": "https://data.gov.il/dataset/o/odafim.csv"}]}]}},
            ensure_ascii=False)),
        "/data/dataset/o/odafim.csv": (200, "text/csv", "a,b\n"),
    }
    out = os.path.join(TMP, "cec_lists_out")
    base = f"http://127.0.0.1:{port}"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "pipeline", "fetchers", "cec_lists.py"), "--out", out, "--timeout", "5",
                        "--rewrite", f"https://www.gov.il={base}/govil", "--rewrite", f"https://api.example.gov.il/content={base}/api",
                        "--rewrite", f"https://data.gov.il={base}/data", "--rewrite", "https://votes26.bechirot.gov.il=http://127.0.0.1:9",
                        "--only-rewritten"], capture_output=True, text=True, timeout=180)
    srv.shutdown()
    s = load(out, "summary.json") or {}
    rows = {e["cec_key"]: e for e in s.get("lists") or []}
    seen = {e["url"]: e for e in s.get("urls") or []}
    a_ = s.get("agreements") or {}
    check(r.returncode == 0 and os.path.exists(os.path.join(out, "summary.md")) and len(rows) == 38,
          f"cec_lists.py offline: exit {r.returncode}, summary.json and summary.md written {r.stderr.strip()[-200:]}")
    asked = {k.lower(): v for k, v in (GovilMock.asked.get(api + lk["cec_key"] + "?culture=he") or {}).items()}
    check(s.get("client_id_found") and s.get("content_api") == "https://api.example.gov.il/content/api/content-pages"
          and asked.get("x-client-id") == "cid-test" and asked.get("origin") == "https://www.gov.il",
          f"cec_lists.py: the content-pages API and client id from client-config.js, asked with gov.il's Origin: {s.get('content_api')} {asked}")
    check((rows.get(lk["cec_key"]) or {}).get("letters_match") is True and (rows.get(ya["cec_key"]) or {}).get("letters_match") is False
          and (rows.get(bw["cec_key"]) or {}).get("status") == 500 and (rows.get(bw["cec_key"]) or {}).get("letters_match") is None,
          f"cec_lists.py: a roster page with the reference letters, one with others (flagged), one that failed (500): "
          f"{[(k, rows.get(k, {}).get('letters_match'), rows.get(k, {}).get('status')) for k in (lk['cec_key'], ya['cec_key'], bw['cec_key'])]}")
    check(sorted(["מחל", "ט"]) in a_.get("expected_seen", []) and sorted(["שס", "ג"]) in a_.get("expected_seen", [])
          and any(set(p_) == {bw["letters"], res_["letters"]} for p_ in a_.get("not_expected", [])) and len(a_.get("expected_not_seen", [])) == 3,
          f"cec_lists.py: the agreements page read (two expected pairs seen, one not expected, three not seen): {a_.get('expected_seen')} "
          f"{a_.get('not_expected')} {a_.get('expected_not_seen')}")
    ix = s.get("index") or {}
    check(ix.get("roster_pages_linked") == 2 and ix.get("not_in_reference") == ["new-party_list39"]
          and len(ix.get("not_linked", [])) == 36 and (seen.get("https://api.example.gov.il/content/api/content-pages/"
                                                          "new-party_list39?culture=he") or {}).get("status") == 404,
          f"cec_lists.py: a roster page the lists page links to that the reference lacks is reported and asked for: {ix}")
    slips = seen.get(ref["cec"]["approved_slips_pdf"]) or {}
    linked_out = seen.get("https://elsewhere.example.com/x.pdf")
    refused = seen.get("https://votes26.bechirot.gov.il/") or {}
    csv_ = seen.get("https://data.gov.il/dataset/o/odafim.csv") or {}
    check(str(slips.get("saved", "")).endswith(".pdf") and os.path.exists(os.path.join(out, slips.get("saved", "-")))
          and csv_.get("saved") and "refused" in str(refused.get("error", "")).lower()
          and str((linked_out or {}).get("error", "")).startswith("not fetched: not a gov.il address")
          and all(e.get("error", "").startswith("not fetched") for u, e in seen.items() if u.startswith("https://bechirot.gov.il")),
          f"cec_lists.py: the slips PDF and a data.gov.il resource stored, a refused host and the hosts not rewritten recorded, "
          f"no link off gov.il followed: {slips.get('saved')} {csv_.get('saved')} {refused.get('error')}")
    conf = s.get("confirmation") or {}
    st_l = {r["letters"]: r for r in conf.get("letters") or []}
    st_a = {frozenset(r["lists"]): r["status"] for r in conf.get("agreements") or []}
    check((st_l.get("מחל") or {}).get("status") == "live" and (st_l.get("דרך") or {}).get("other_letters") == ["דרכ"]
          and st_a.get(frozenset(["מחל", "ט"])) == "live" and st_a.get(frozenset(["רק", "ל"])) == "not confirmed"
          and "## Confirmed by the CEC's own pages and files" in open(os.path.join(out, "summary.md"), encoding="utf-8").read(),
          f"cec_lists.py: the confirmations on top of summary.md (the lists page's row and roster page for מחל, other "
          f"letters for דרך, the agreements page): {conf.get('counts')}")
    cec_lists_site(ref, ref_path, lists)


def cec_lists_site(ref, ref_path, lists):
    """11c, the CEC's own site and the Wayback Machine, with www.gov.il answering 403 to everything (as its WAF answers
    GitHub's runners): a stand-in for www.bechirot.gov.il whose home page has no links, only the elements its scripts
    fill from the site's API (the addresses found in the scripts), with robots.txt, a sitemap, a page under a Hebrew
    address, a PDF, an XLSX and a DOCX, redirects; and for archive.org (the availability API, the CDX index, raw
    snapshots). Then --reread, the bounds (a site of 100 pages and 200 files, a sitemap index), a 429 from the archive,
    the deadline, the site's header, footer and share bar against the API budget; in-process, a dripped body and a gzip
    one."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("cec_lists_11c", os.path.join(ROOT, "pipeline", "fetchers", "cec_lists.py"))
    C = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(C)
    pdf_ok = bool(C.pdf_reader())
    if not pdf_ok:
        print("  note: neither pdftotext nor pypdf here: the PDFs below are stored, not read, and so not counted")
    ref_before = (open(ref_path, "rb").read(), os.path.getmtime(ref_path))
    by = {e.get("id"): e for e in lists if e.get("id")}
    A, slips = C.API_FALLBACK, ref["cec"]["approved_slips_pdf"]
    heb = lambda s_: "/" + urllib.parse.quote(s_) + "/"                                    # noqa: E731
    ag_slug, notices_slug = heb("הסכמי-עודפים"), heb("ילקוט-הפרסומים")
    lists_api, res_api, ag_api = (f"{A}/{n}?culture=he" for n in ("candidates-lists-26", by["Reservists"]["cec_key"],
                                                                     "surplus-agreements-knesset26"))
    blob_pdf = "https://www.gov.il/BlobFolder/guide/candidates-lists-26/he/surplus-agreements.pdf"
    page_json = lambda title, html_: json.dumps({"contentHead": {"title": title}, "contentMain": {"htmlContents": [  # noqa: E731
        {"sectionData": html_}]}}, ensure_ascii=False)
    row = lambda *cells: "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"     # noqa: E731
    home = ('<!DOCTYPE HTML><html lang="he" dir="rtl"><head><title>ועדת הבחירות המרכזית- דף הבית</title>'
            '<script type="text/javascript" src="/ruxitagentjs_ICA15789.js"></script><link rel="stylesheet" href="/css/MiniSite.min.css"/>'
            '</head><body><header id="PageHeader" navigation="2" logo="2" currentPageId="22714" htmlLangAttribute="he" siteRootUrl="/">'
            '</header><main><div id="Banner-118be830" component-id="118be830" component-query="22569" component-currentPageId="22714" '
            'component-type="BannersWithLinks" class="mst-banner"></div><div id="ContentShow-4d108e53" component-id="4d108e53" '
            'component-currentPageId="22714" component-query="22578" component-type="Boxes"></div></main>'
            '<footer id="PageFooter" currentPageId="22714" publicationDate="06/01/2025 13:06"></footer>'
            '<script src="/bootstrap/js/bootstrap.bundle.min.js"></script><script src="/dist/Header.bundle.js?v=248baca6"></script>'
            '<script src="/dist/ContentShow.bundle.js?v=248baca6"></script></body></html>')
    menu = [{"Title": "הבחירות לכנסת ה-26", "Url": "/elections-26/"}, {"Title": "אודות הוועדה", "Url": "/about/"},
            {"Title": "תוצאות הבחירות לכנסת ה-25", "Url": "/results/"}, {"Title": "רשימות המועמדים (פנימי)", "Url": "/private/candidates-26/"},
            {"Title": "רשימות המועמדים", "Link": {"Url": "/elections-26/candidates/", "Target": ""}}]
    boxes = [{"title": "לחצו כאן", "url": ag_slug}, {"title": "רשימות המועמדים (אתר אחר)", "url": "https://elsewhere.example.com/lists"}]
    site = {
        "/": (200, "text/html", home),
        "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /private/\nSitemap: https://www.bechirot.gov.il/sitemap.xml\n"),
        "/sitemap.xml": (200, "application/xml", '<?xml version="1.0"?><urlset><url><loc>https://www.bechirot.gov.il/about/</loc></url>'
                         f"<url><loc>https://www.bechirot.gov.il{notices_slug}</loc></url></urlset>"),
        "/dist/Header.bundle.js": (200, "application/javascript", 'function m(e){return fetch("/umbraco/api/MiniSiteApi/GetMenu?'
                                   'currentPageId="+e.currentPageId+"&culture=he").then(function(r){return r.json()})}'),
        "/dist/ContentShow.bundle.js": (200, "application/javascript", 'var a=function(t){return axios.get("/umbraco/api/ContentShow/'
                                        'GetItems",{params:{query:t.query,currentPageId:t.currentPageId}})};'),
        "/umbraco/api/MiniSiteApi/GetMenu?currentPageId=22714&culture=he": (200, "application/json", json.dumps(menu, ensure_ascii=False)),
        "/umbraco/api/ContentShow/GetItems?query=22578&currentPageId=22714": (200, "application/json", json.dumps(boxes, ensure_ascii=False)),
        "/umbraco/api/Carousel/GetLinks?query=176858&currentPageId=22714": (200, "application/json", json.dumps(
            [{"letters": "אמת", "listName": by["The Democrats"]["official_name"], "knesset": "הכנסת ה-26"}], ensure_ascii=False)),
        "/elections-26/": (200, "text/html", '<h1>הבחירות לכנסת ה-26</h1><a href="/elections-26/candidates/">רשימות המועמדים</a>'),
        "/elections-26/candidates/": (200, "text/html", (
            "<h1>רשימות המועמדים לכנסת ה-26</h1><table>" + row("מחל", by["Likud"]["official_name"]) + row("שס", by["Shas"]["official_name"])
            + row("דרכ", by["Yashar"]["official_name"]) + row("בד", "ביחד נצליח") + '</table><a href="/media/a1/slips.pdf">פתקי ההצבעה</a>'
            '<a href="/media/a2/lists.xlsx">קובץ להורדה</a><a href="/media/a3/photo.jpg">תמונה</a>'
            '<a href="/elections-26/moved">רשימות המועמדים - עדכון</a><a href="/elections-26/away/">הודעות הוועדה</a>'
            '<a href="/elections-26/loop/">רשימות המועמדים - קישור ישן</a><a href="/results/knesset-lists/">רשימות המועמדים (ארכיון)</a>')),
        # a redirect on the site (followed, in the site's turn), one off it (not followed), one to itself
        "/elections-26/moved": (301, "text/html", "", {"Location": "/bech/elections-26/moved/"}),
        "/elections-26/moved/": (200, "text/html", "<h1>רשימות המועמדים לכנסת ה-26: עדכון</h1><table>"
                                 + row("ך", by["Amcha Yisrael"]["official_name"]) + "</table>"),
        "/elections-26/away/": (302, "text/html", "", {"Location": "/evil/page"}),
        "/elections-26/loop/": (302, "text/html", "", {"Location": "/bech/elections-26/loop/"}),
        # the 25th Knesset's lists, updated in 2026: not about the 26th
        "/results/knesset-lists/": (200, "text/html", "<h1>רשימות המועמדים והתוצאות - הבחירות לכנסת ה-25</h1><p>עודכן 3 בינואר 2026</p>"
                                    "<p>הסכמי עודפים</p><table>" + row("ב", by["Otzma Yehudit"]["official_name"])
                                    + row(by["Otzma Yehudit"]["official_name"], by["Haredi Public"]["official_name"]) + "</table>"),
        "/notices/deep-26/": (200, "application/json", "[" * 5000 + "]" * 5000),
        ag_slug: (200, "text/html", "<h1>הסכמי עודפים לבחירות לכנסת ה-26</h1><table>"
                  + row(by["Together"]["official_name"], by["Yisrael Beiteinu"]["official_name"]) + "</table>"),
        notices_slug: (200, "text/html", '<h1>ילקוט הפרסומים: הודעות הוועדה לכנסת ה-26</h1><a href="/media/n1/notice.docx">הודעה על '
                       'רשימות המועמדים</a><a href="https://www.gov.il/he/pages/surplus-agreements-knesset26">הסכמי העודפים באתר gov.il</a>'
                       '<a href="/notices/deep-26/">הודעות נוספות</a>'),
        "/notices/heskem-yashar-26/": (200, "text/html", "<h1>הודעה על הסכם עודפים</h1><p>הבחירות לכנסת ה-26</p><table>"
                                       + row(by["The Democrats"]["official_name"], by["Yashar"]["official_name"]) + "</table>"),
        "/media/a1/slips.pdf": (200, "application/pdf", pdf_rows([["פתקי ההצבעה לכנסת ה-26"], ["רק", by["Together"]["official_name"]]])),
        "/media/a2/lists.xlsx": (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 xlsx_rows([["אותיות", "שם הרשימה"], ["ל", by["Yisrael Beiteinu"]["official_name"]]])),
        "/media/n1/notice.docx": (200, "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                  docx_rows(["הודעה על רשימות המועמדים לכנסת ה-26"], [["כן", by["National Unity"]["official_name"]]])),
        "/private/candidates-26/": (200, "text/html", "<p>רשימות המועמדים לכנסת ה-26</p>"),
        "/about/": (200, "text/html", "<p>אודות</p>"), "/results/": (200, "text/html", "<p>תוצאות</p>"),
    }
    closest = {lists_api: {"available": True, "status": "200", "timestamp": "20261005120000"},
               res_api: {"available": True, "status": "200", "timestamp": "20261003000000"},
               ag_api: {"available": True, "status": "200", "timestamp": "20261014000000"},
               slips: {"available": True, "status": "403", "timestamp": "20261001000000"}}
    cdx = {"www.bechirot.gov.il/": [["original", "timestamp", "statuscode", "mimetype"],
                                    ["https://www.bechirot.gov.il/notices/heskem-yashar-26/", "20261012000000", "200", "text/html"],
                                    ["https://www.bechirot.gov.il/css/MiniSite.min.css", "20261012000000", "200", "text/css"],
                                    ["http://www.bechirot.gov.il:80/umbraco/api/Carousel/GetLinks?query=176858&currentPageId=22714",
                                     "20261012000000", "200", "application/json"]],
           "www.gov.il/BlobFolder/guide/candidates-lists-26/": [["original", "timestamp", "statuscode", "mimetype"],
                                                                [blob_pdf, "20261015000000", "200", "application/pdf"]],
           slips: [["timestamp", "original", "statuscode"], ["20260930000000", slips, "200"]]}
    snaps = {lists_api: (200, "application/json", page_json("רשימות המועמדים לכנסת ה-26", "<table>" + row("ג", by["UTJ"]["official_name"]) + "</table>")),
             res_api: (200, "application/json", page_json(by["Reservists"]["official_name"], "<p>אותיות הרשימה: די</p>")),
             ag_api: (200, "application/json", page_json("הסכמי עודפים", "<table>" + row('ש"ס', "יהדות התורה") + "</table>")),
             slips: (200, "application/pdf", b"%PDF-1.4 not a PDF after all"),
             blob_pdf: (200, "application/pdf", pdf_rows([["הסכמי עודפים לבחירות לכנסת ה-26"],
                                                          [by["Ra'am"]["official_name"], by["Joint List"]["official_name"]]]))}
    srv = http.server.HTTPServer(("127.0.0.1", 0), GovilMock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    rewrite = ["--rewrite", f"https://www.gov.il={base}/govil", "--rewrite", f"https://www.bechirot.gov.il={base}/bech",
               "--rewrite", f"https://archive.org={base}/arch", "--rewrite", f"https://web.archive.org={base}/wb"]

    def fetch(name, routes, dyn, *extra, timeout=180):
        GovilMock.routes, GovilMock.dynamic, GovilMock.asked, GovilMock.times = routes, dyn, {}, []
        out = os.path.join(TMP, name)
        t = time.time()
        r = subprocess.run([sys.executable, os.path.join(ROOT, "pipeline", "fetchers", "cec_lists.py"), "--out", out, "--timeout", "5",
                            *rewrite, "--only-rewritten", *extra], capture_output=True, text=True, timeout=timeout)
        md = os.path.join(out, "summary.md")
        return r, load(out, "summary.json") or {}, open(md, encoding="utf-8").read() if os.path.exists(md) else "", time.time() - t, out

    def gaps(prefixes):
        ts = [t for t, p in GovilMock.times if p.startswith(prefixes)]
        return min((b - a for a, b in zip(ts, ts[1:])), default=None), len(ts)

    try:
        evil = (200, "text/html", "<h1>רשימות המועמדים לכנסת ה-26</h1><p>הסכמי עודפים</p><table>" + row("זך", by["Haredi Public"]["official_name"])
                + row(by["Likud"]["official_name"], by["Religious Zionism"]["official_name"]) + "</table>")
        r, s, md, secs, out_b = fetch("cec_lists_site", {**{"/bech" + k: v for k, v in site.items()}, "/evil/page": evil},
                                      wayback_mock(closest, cdx, snaps), "--polite", "0.15", "--archive-gap", "0.08")
        asked = set(GovilMock.asked)
        site_gap, n_site = gaps(("/bech/",))
        arch_gap, n_arch = gaps(("/arch/", "/wb/"))
        cr, ar = s.get("crawl") or {}, s.get("archive") or {}
        conf = s.get("confirmation") or {}
        st_l = {x["letters"]: x for x in conf.get("letters") or []}
        st_a = {frozenset(x["lists"]): x for x in conf.get("agreements") or []}
        check(r.returncode == 0 and md and "/bech/umbraco/api/MiniSiteApi/GetMenu?currentPageId=22714&culture=he" in asked
              and "/bech/umbraco/api/ContentShow/GetItems?query=22578&currentPageId=22714" in asked
              and "/bech/umbraco/api/Carousel/GetLinks?query=176858&currentPageId=22714" in asked
              and {"/bech/dist/Header.bundle.js?v=248baca6", "/bech/dist/ContentShow.bundle.js?v=248baca6"} <= asked
              and not any("ruxit" in p_ or "bootstrap" in p_ or p_.endswith((".css", ".jpg")) for p_ in asked)
              and {"/bech/elections-26/candidates/", "/bech" + ag_slug, "/bech" + notices_slug, "/bech/notices/heskem-yashar-26/",
                   "/bech/media/a1/slips.pdf", "/bech/media/a2/lists.xlsx", "/bech/media/n1/notice.docx"} <= asked,
              f"cec_lists.py, www.bechirot.gov.il: the API addresses read in the site's scripts asked with the attributes of the "
              f"elements they fill (and one from the archive's index), the pages and files about the lists and agreements "
              f"(a Hebrew address, the sitemap, the index) followed, no tracking script, style sheet or image asked: exit "
              f"{r.returncode}, {len(asked)} paths, API found {[x.get('address') for x in cr.get('api_found') or []]} "
              f"{r.stderr.strip()[-200:]}")
        check(not ({"/bech/about/", "/bech/results/", "/bech/private/candidates-26/"} & asked)
              and "https://elsewhere.example.com/lists" in (cr.get("elsewhere") or [])
              and not any(e["url"].startswith("https://elsewhere") for e in s.get("urls") or [])
              and any(x.get("why") == "disallowed by robots.txt" for x in cr.get("not_asked") or []),
              f"cec_lists.py, the crawl: not a page about none of the topics, about the 25th Knesset only, or disallowed by "
              f"robots.txt; a link elsewhere listed, not fetched: {sorted(p_ for p_ in asked if p_.startswith('/bech/'))[:30]}")
        check(site_gap is not None and site_gap >= 0.15 * 0.8 and arch_gap is not None and arch_gap >= 0.08 * 0.8,
              f"cec_lists.py: one request to the site every --polite seconds, to archive.org every --archive-gap: the "
              f"shortest gaps {site_gap and round(site_gap, 3)} s over {n_site} and {arch_gap and round(arch_gap, 3)} s over {n_arch}")
        want_l = {"מחל": "live", "שס": "live", "ל": "live", "כן": "live", "ג": "archive snapshot", "די": "archive snapshot",
                  "רק": "live" if pdf_ok else "not confirmed", "אמת": "live", "דרך": "not confirmed", "ט": "not confirmed",
                  "ך": "live", "בד": "live", "ב": "not confirmed", "זך": "not confirmed"}
        got_l = {k: (st_l.get(k) or {}).get("status") for k in want_l}
        kinds = {k: [(x["url"], x["kind"]) for x in (st_l.get(k) or {}).get("confirmed_by") or []] for k in ("ג", "די", "ל", "כן", "אמת")}
        check(got_l == want_l and (st_l.get("דרך") or {}).get("other_letters") == ["דרכ"]
              and kinds["ג"] == [(lists_api, "archive snapshot 20261005120000")] and kinds["די"] == [(res_api, "archive snapshot 20261003000000")]
              and kinds["ל"] == [("https://www.bechirot.gov.il/media/a2/lists.xlsx", "live file")]
              and kinds["כן"] == [("https://www.bechirot.gov.il/media/n1/notice.docx", "live file")]
              and kinds["אמת"] == [("https://www.bechirot.gov.il/umbraco/api/Carousel/GetLinks?query=176858&currentPageId=22714", "live page")]
              and sum(1 for x in st_l.values() if x["status"] != "not confirmed") == sum(1 for v in want_l.values() if v != "not confirmed"),
              f"cec_lists.py: letters confirmed by the site's pages, an API answer's JSON row, its XLSX, DOCX{' and PDF' if pdf_ok else ''} "
              f"(live), by archive snapshots of the lists page and a roster page (their gov.il addresses, marked as snapshots), "
              f"other letters flagged: {got_l} {kinds}")
        want_a = {frozenset(["רק", "ל"]): "live", frozenset(["דרך", "אמת"]): "live", frozenset(["שס", "ג"]): "archive snapshot",
                  frozenset(["עם", "ודם"]): "archive snapshot" if pdf_ok else "not confirmed", frozenset(["מחל", "ט"]): "not confirmed"}
        got_a = {k: (st_a.get(k) or {}).get("status") for k in want_a}
        a_src = [(x["url"], x["kind"]) for x in (st_a.get(frozenset(["שס", "ג"])) or {}).get("confirmed_by") or []]
        check(got_a == want_a and a_src == [(ag_api, "archive snapshot 20261014000000")]
              and not conf.get("not_expected") and "archive snapshot 20261014000000" in md
              and not any(x["kind"].startswith("live") for v in st_a.values() for x in v["confirmed_by"] if "web.archive.org" in x["url"]),
              f"cec_lists.py: agreements confirmed by the site's pages (one under a Hebrew address, one found in the archive's "
              f"index), by archive snapshots (a gov.il page the site links to, {'a PDF in the lists page folder' if pdf_ok else 'its PDF not read here'}), "
              f"one not confirmed: { {'+'.join(sorted(k)): v for k, v in got_a.items()} } {a_src}")
        rows_ = {x["address"]: x for x in ar.get("rows") or []}
        slip_row = rows_.get(slips) or {}
        check(ar.get("lookups", 0) >= 40 and ar.get("snapshots") == 5 and "index has a 200 of 20260930000000" in str(slip_row.get("result"))
              and slip_row.get("snapshot") == 200 and str(slip_row.get("read", "")).startswith("not read")
              and (rows_.get(f"{A}/{by['Likud']['cec_key']}?culture=he") or {}).get("result") == "no snapshot"
              and not ar.get("stopped"),
              f"cec_lists.py, the archive: every gov.il address that answered 403 looked up, a closest snapshot that is not a 200 "
              f"replaced by the index's latest 200, a PDF that does not read recorded: {ar.get('lookups')} lookups, "
              f"{ar.get('snapshots')} snapshots, the slips {slip_row}")
        by_url = {e["url"]: e for e in s.get("urls") or []}
        moved, away, loop = (by_url.get(f"{C.BECHIROT}/elections-26/{p_}") or {} for p_ in ("moved", "away/", "loop/"))
        n_loop = sum(1 for _, p_ in GovilMock.times if p_ == "/bech/elections-26/loop/")
        n_pages = sum(1 for _, p_ in GovilMock.times if p_.startswith("/bech/") and not p_.startswith(("/bech/media/", "/bech/dist/")))
        check("/evil/page" not in asked and away.get("status") == 302 and "/evil/page" in str(away.get("redirect_refused"))
              and "not followed" in str(away.get("error")) and "/bech/elections-26/moved/" in asked and moved.get("hops") == 1
              and [(x["url"], x["kind"]) for x in (st_l.get("ך") or {}).get("confirmed_by") or []] == [(C.BECHIROT + "/elections-26/moved", "live page")]
              and n_loop == 1 + loop.get("hops", 0) <= 1 + C.MAX_HOPS and "a loop" in str(loop.get("error"))
              and (cr.get("count") or {}).get("page") == n_pages and "not followed" in md,
              f"cec_lists.py, the crawl's redirects: one on the site followed (in the site's turn, counted), one off it not "
              f"(its body not read, its lists not confirmed), one to itself stopped; every request counted: {away.get('error')} "
              f"{moved.get('hops')} hops, {n_loop} requests of the loop ({loop.get('error')}), {n_pages} pages asked, "
              f"{(cr.get('count') or {}).get('page')} counted")
        k25 = by_url.get(C.BECHIROT + "/results/knesset-lists/") or {}
        deep = by_url.get(C.BECHIROT + "/notices/deep-26/") or {}
        L_ = {k: st_l.get(k) or {} for k in ("ב", "בד", "רק")}
        check(k25.get("status") == 200 and k25.get("k26") is False and L_["ב"].get("status") == "not confirmed"
              and L_["בד"].get("confirmed_by") and L_["רק"].get("other_letters") == [] and deep.get("status") == 200 and deep.get("read"),
              f"cec_lists.py: a page about the 25th Knesset dated 2026 is not about the 26th; the row 'בד | ביחד נצליח' "
              f"confirms בד and is not read as other letters for ביחד (רק); a JSON answer nested 5000 deep read: "
              f"{k25.get('k26')} {L_['רק'].get('other_letters')} {deep.get('read')}")
        check(open(ref_path, "rb").read() == ref_before[0] and os.path.getmtime(ref_path) == ref_before[1]
              and "never written" in md,
              "cec_lists.py: lists_2026.json read, never written")
    finally:
        srv.shutdown()
    # --reread: the same files read again, nothing asked (the stand-in is down)
    out_rr = os.path.join(TMP, "cec_lists_reread")
    r2 = subprocess.run([sys.executable, os.path.join(ROOT, "pipeline", "fetchers", "cec_lists.py"), "--reread", out_b, "--out", out_rr],
                        capture_output=True, text=True, timeout=120)
    s2 = load(out_rr, "summary.json") or {}
    same = lambda a_, b_: [(x["letters"], x["status"]) for x in (a_.get("confirmation") or {}).get("letters") or []] == \
        [(x["letters"], x["status"]) for x in (b_.get("confirmation") or {}).get("letters") or []]                # noqa: E731
    check(r2.returncode == 0 and s2.get("reread_from") == out_b and same(s, s2) and s2.get("requests") == s.get("requests")
          and (s2.get("confirmation") or {}).get("agreements") == (s.get("confirmation") or {}).get("agreements")
          and "Read again" in open(os.path.join(out_rr, "summary.md"), encoding="utf-8").read(),
          f"cec_lists.py --reread: the stored files read again, the same comparison, nothing asked: exit {r2.returncode} "
          f"{(s2.get('confirmation') or {}).get('counts')} {r2.stderr.strip()[-160:]}")
    t = [C.orient(["2026 תוריחבל תסנכל", "םע | םדו"]), C.orient(["הסכמי עודפים לכנסת ה-26", "עם | ודם"])]
    check(t == [["לכנסת לבחירות 2026", "ודם | עם"], ["הסכמי עודפים לכנסת ה-26", "עם | ודם"]],
          f"cec_lists.orient: a PDF's lines that came out backwards turned around (digits kept), the others left: {t}")

    # the bounds: a site of 100 pages about the notices, two files each, and links elsewhere; the archive answering 429
    big = {"/bech/": (200, "text/html", "<h1>הבחירות לכנסת ה-26</h1>" + "".join(f'<a href="/elections-26/n{i}/">הודעה {i}</a>' for i in range(100)))}
    for i in range(100):
        big[f"/bech/elections-26/n{i}/"] = (200, "text/html", f'<h1>הודעה {i} לכנסת ה-26</h1><a href="/media/n{i}/a.pdf">קובץ</a>'
                                            f'<a href="/media/n{i}/b.xlsx">קובץ</a><a href="https://evil.example.com/{i}">הודעה</a>')
        big[f"/bech/media/n{i}/a.pdf"] = (200, "application/pdf", b"%PDF-1.4 x")
        big[f"/bech/media/n{i}/b.xlsx"] = (200, "application/vnd.ms-excel", b"PK\x03\x04 not a zip")
    # a sitemap index of 3000 sitemaps (and itself): MAX_SITEMAPS of them asked, the pages still
    big["/bech/sitemap.xml"] = (200, "application/xml", '<?xml version="1.0"?><sitemapindex>' + "".join(
        f"<sitemap><loc>{C.BECHIROT}/sm/{i}.xml</loc></sitemap>" for i in range(3000)) + f"<sitemap><loc>{C.BECHIROT}/sitemap.xml</loc>"
        "</sitemap></sitemapindex>")
    srv = http.server.HTTPServer(("127.0.0.1", 0), GovilMock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    rewrite = ["--rewrite", f"https://www.gov.il={base}/govil", "--rewrite", f"https://www.bechirot.gov.il={base}/bech",
               "--rewrite", f"https://archive.org={base}/arch", "--rewrite", f"https://web.archive.org={base}/wb"]
    try:
        r, s, md, secs, _ = fetch("cec_lists_bounds", big, wayback_mock({}, {}, {}, refuse=(429, "text/plain", "Too Many Requests")),
                                  "--polite", "0.01", "--archive-gap", "0.01")
        asked = [p_ for _, p_ in GovilMock.times]
        cr, ar = s.get("crawl") or {}, s.get("archive") or {}
        pages_ = [p_ for p_ in asked if p_.startswith("/bech/") and not p_.startswith("/bech/media/")]
        files_ = [p_ for p_ in asked if p_.startswith("/bech/media/")]
        check(r.returncode == 0 and len(pages_) == C.MAX_PAGES and len(files_) == C.MAX_FILES
              and (cr.get("count") or {}).get("page") == C.MAX_PAGES and (cr.get("count") or {}).get("file") == C.MAX_FILES
              and cr.get("not_asked_n", 0) > 100 and any("over the limit" in x["why"] for x in cr.get("not_asked") or [])
              and len(cr.get("elsewhere") or []) > 10 and not any("evil" in e["url"] for e in s.get("urls") or []),
              f"cec_lists.py, the crawl's bounds: {C.MAX_PAGES} pages and {C.MAX_FILES} files at most (robots.txt and the sitemap "
              f"among the pages), the rest named as not asked, nothing off the site: {len(pages_)} pages, {len(files_)} files, "
              f"{cr.get('not_asked_n')} not asked, exit {r.returncode} {r.stderr.strip()[-160:]}")
        maps = [p_ for p_ in pages_ if p_.startswith(("/bech/sm/", "/bech/sitemap.xml"))]
        notices = [p_ for p_ in pages_ if p_.startswith("/bech/elections-26/n")]
        check(len(maps) == (cr.get("count") or {}).get("sitemap") == C.MAX_SITEMAPS and len(notices) >= C.MAX_PAGES - C.MAX_SITEMAPS - 6
              and any("MAX_SITEMAPS" in x["why"] for x in cr.get("not_asked") or []),
              f"cec_lists.py, the crawl's bounds: a sitemap index of 3000 asks {C.MAX_SITEMAPS} sitemaps, the pages still asked: "
              f"{len(maps)} sitemaps, {len(notices)} pages")
        check(sum(1 for p_ in asked if p_.startswith(("/arch/", "/wb/"))) == 1 and "429" in str(ar.get("stopped"))
              and ar.get("lookups") == 0 and "429" in md,
              f"cec_lists.py, the archive answering 429: nothing more asked of it, said in summary.md: {ar.get('stopped')}")
        # the deadline: one request every 0.25 s and 3 s to go
        r, s, md, secs, _ = fetch("cec_lists_deadline", big, wayback_mock({}, {}, {}), "--polite", "0.25", "--archive-gap", "0.01",
                                  "--deadline", "3")
        n_site = sum(1 for _, p_ in GovilMock.times if p_.startswith("/bech/"))
        cr = s.get("crawl") or {}
        check(r.returncode == 0 and "deadline" in str(cr.get("stopped")) and 2 <= n_site <= 3 / 0.25 + 2 and secs < 3 + 15
              and "Stopped at the deadline" in md and s.get("skipped_past_deadline", 0) > 0,
              f"cec_lists.py, the crawl at the deadline: stopped, the summary written with what came: {n_site} requests to the "
              f"site in {secs:.1f} s, {cr.get('stopped')}")
        # a page's content is in its blocks' API answers: a home page whose block links 14 pages, every page with the
        # site's header, footer and share bar (the same menus on every page: asked once) and a block of its own (asked
        # for every page, within MAX_API), about the 26th Knesset as its page is
        chrome = '<header id="PageHeader" navigation="2" currentPageId="{p}" htmlLangAttribute="he"></header>' \
                 '<div id="ContentShow-c{p}" component-id="c{p}" component-query="{q}" component-currentPageId="{p}" ' \
                 'component-type="Boxes"></div><div id="PageShare" currentPageId="{p}"></div><footer id="PageFooter" ' \
                 'currentPageId="{p}"></footer><script src="/dist/Header.bundle.js?v=1"></script><script src="/dist/Footer.bundle.js?v=1">' \
                 '</script><script src="/dist/Share.bundle.js?v=1"></script><script src="/dist/ContentShow.bundle.js?v=1"></script>'
        rows14 = lists[:14]
        cs = {"/bech/": (200, "text/html", "<title>ועדת הבחירות המרכזית לכנסת ה-26</title>" + chrome.format(p=1000, q=5000)),
              "/bech/umbraco/api/ContentShow/GetItems?query=5000&currentPageId=1000": (200, "application/json", json.dumps(
                  [{"Title": f"רשימות המועמדים {i}", "Url": f"/elections-26/p{i}/"} for i in range(14)], ensure_ascii=False))}
        for name, call in (("Header", "MiniSiteApi/GetMenu?currentPageId="), ("Footer", "MiniSiteApi/GetFooter?currentPageId="),
                           ("Share", "MiniSiteApi/GetShare?currentPageId=")):
            cs[f"/bech/dist/{name}.bundle.js"] = (200, "application/javascript", f'fetch("/umbraco/api/{call}"+e.currentPageId)')
        cs["/bech/dist/ContentShow.bundle.js"] = (200, "application/javascript", 'axios.get("/umbraco/api/ContentShow/GetItems",'
                                                  '{params:{query:t.query,currentPageId:t.currentPageId}})')
        for i, e in enumerate(rows14):
            cs[f"/bech/elections-26/p{i}/"] = (200, "text/html", f"<title>רשימות המועמדים לכנסת ה-26: {i}</title>"
                                               + chrome.format(p=1001 + i, q=5001 + i))
            cs[f"/bech/umbraco/api/ContentShow/GetItems?query={5001 + i}&currentPageId={1001 + i}"] = (
                200, "application/json", json.dumps([{"letters": e["letters"], "listName": e["official_name"]}], ensure_ascii=False))
        r, s, md, secs, _ = fetch("cec_lists_chrome", cs, wayback_mock({}, {}, {}), "--polite", "0.01", "--archive-gap", "0.01")
        asked = [p_ for _, p_ in GovilMock.times]
        cr = s.get("crawl") or {}
        st_l = {x["letters"]: x for x in (s.get("confirmation") or {}).get("letters") or []}
        menus = {k: sum(1 for p_ in asked if f"/{k}?" in p_) for k in ("GetMenu", "GetFooter", "GetShare")}
        blocks = sum(1 for p_ in asked if "/ContentShow/GetItems?" in p_)
        live = [e["letters"] for e in rows14 if (st_l.get(e["letters"]) or {}).get("status") == "live"]
        check(r.returncode == 0 and menus == {"GetMenu": 1, "GetFooter": 1, "GetShare": 1} and blocks == 15
              and len(live) == 14 and (cr.get("count") or {}).get("api", 99) <= C.MAX_API,
              f"cec_lists.py, the site's API: the header, footer and share bar asked once, every page's block (its content) "
              f"asked and read: {menus}, {blocks} blocks, {len(live)} of 14 lists confirmed by them, API {(cr.get('count') or {}).get('api')}")
    finally:
        srv.shutdown()

    # in-process: a body dripped 8 bytes at a time is cut GRACE after the deadline (read(64 KB) would wait for it all);
    # a gzip body unpacks to MAX_FILE at most; a JSON answer nested too deep is read as text, not a crash
    import gzip
    bomb = gzip.compress(b"\0" * (C.MAX_FILE + 5_000_000))
    GovilMock.routes, GovilMock.dynamic = {"/drip": (200, "text/html", b"<p>" + b"x" * 2000, {"_drip": 0.02}),
                                           "/bomb": (200, "text/html", bomb, {"Content-Encoding": "gzip"})}, None
    srv = http.server.HTTPServer(("127.0.0.1", 0), GovilMock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    grace, C.GRACE = C.GRACE, 0.6
    try:
        rw = [("https://www.bechirot.gov.il", f"http://127.0.0.1:{srv.server_address[1]}")]
        t = time.monotonic()
        drip, _ = C.Fetcher(os.path.join(TMP, "cec_lists_drip"), rw, deadline=0.3).get(C.BECHIROT + "/drip")
        t_drip = time.monotonic() - t
        bomb_e, bomb_b = C.Fetcher(os.path.join(TMP, "cec_lists_bomb"), rw).get(C.BECHIROT + "/bomb")
    finally:
        C.GRACE = grace
        srv.shutdown()
    nested = [C.read_any({"url": "x"}, b"[" * n + b"]" * n)[3] for n in (5000, 200_000)]
    check("cut at the deadline" in str(drip.get("error")) and t_drip < 3 and bomb_b is None and "unpacked" in str(bomb_e.get("error"))
          and len(C.decode_body(bomb, "gzip")) == C.MAX_FILE + 1 and nested == ["html", "html"],
          f"cec_lists.py: a dripped body cut at the deadline ({t_drip:.1f} s: {drip.get('error')}), a gzip body unpacked to "
          f"MAX_FILE at most ({bomb_e.get('error')}), JSON nested 5000 and 200000 deep read as text {nested}")
    k = [C.k26_of(t_) for t_ in ("רשימות המועמדים - הבחירות לכנסת ה-25\nעודכן 3 בינואר 2026", "עודכן 3 בינואר 2026",
                                 "הבחירות לכנסת ה-26 (בכנסת ה-25: ...)")]
    check(k == [False, True, True], f"cec_lists.k26_of: the year 2026 alone not about the 26th Knesset where an earlier one is named: {k}")


class CensusMock(http.server.BaseHTTPRequestHandler):
    """A stand-in for census.cbs.gov.il (11d): /search?search=<term> answers the htmx partial with the areas whose
    label starts with the term (and, for a term without a number, the locality's own item first), 100 at most in
    label order, as the real search caps it; /csv?...&ID=<id> a zip of one CSV. The ids asked for a dashboard are
    kept in order; every answer waits `delay` seconds."""
    areas, asked, delay = {}, [], 0.0

    def do_GET(self):
        time.sleep(CensusMock.delay)
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/search":
            term = q.get("search", [""])[0]
            items = sorted((lab, aid) for aid, lab in CensusMock.areas.items() if "אזור" in lab and lab.startswith(term))
            if not re.search(r"\d", term):
                items = [(lab, aid) for aid, lab in CensusMock.areas.items() if lab == term.split(" אזור")[0]] + items
            body = "<ul>" + "".join(f'<li data-id="{aid}" data-search="{html.escape(lab)}" data-type="area">{html.escape(lab)}</li>'
                                    for lab, aid in items[:100]) + "</ul>"
            body, ctype = body.encode("utf-8"), "text/html"
        else:
            CensusMock.asked.append(q.get("ID", [""])[0])
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("religion.csv", "religion,share\nמוסלמים,12.5\n")
            body, ctype = buf.getvalue(), "application/zip"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def fetchers_budget():
    """11d. The fetchers' clock (pipeline/fetchers/__init__.py): each one's --deadline well inside fetch.yml's limit,
    and kept: with --deadline 0 a fetcher asks nothing, writes summary.json and summary.md and exits 0. Then cbs.py
    against stand-ins: the cities in priority order, Jerusalem first, the areas that matter before the rest, the
    search asked again where its answer is cut, part 4 stopped at the deadline with its files and a partial summary
    written; the geographic catalogue taken by name pattern (case, subfolders), bounded, every file left named."""
    print("11d. the fetchers' clock: --deadline inside fetch.yml's limit, and kept; cbs.py's census order and catalogue")
    import importlib.util
    fdir = os.path.join(ROOT, "pipeline", "fetchers")
    m = re.search(r"timeout -k (\d+) (\d+) python3", open(os.path.join(ROOT, ".github", "workflows", "fetch.yml"), encoding="utf-8").read())
    limit = int(m.group(2)) if m else 0
    mods = {}
    for name, extra in (("cbs", []), ("cec_lists", ["--only-rewritten"]), ("poll_filings", ["--only-rewritten", "--no-curl"])):
        spec = importlib.util.spec_from_file_location(f"fetcher_{name}", os.path.join(fdir, name + ".py"))
        mods[name] = mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        check(limit and mod.DEADLINE + mod.GRACE + 180 <= limit,
              f"{name}.py: its deadline ({mod.DEADLINE} s, a body cut {mod.GRACE} s on) at least 3 minutes inside fetch.yml's "
              f"limit ({limit} s)")
        out = os.path.join(TMP, f"deadline0_{name}")
        t = time.time()
        r = subprocess.run([sys.executable, os.path.join(fdir, name + ".py"), "--out", out, "--deadline", "0", *extra],
                           capture_output=True, text=True, timeout=120)
        s, md = load(out, "summary.json") or {}, os.path.join(out, "summary.md")
        md = open(md, encoding="utf-8").read() if os.path.exists(md) else ""
        if name == "cbs":
            kept = (s.get("census_dashboards") or {}).get("stopped") == "the deadline (--deadline)" and s.get("past_deadline") is True \
                and all("past the deadline" in str(i.get("error")) for i in s.get("items") or [] if not i["name"].startswith("census/"))
        elif name == "cec_lists":
            kept = s.get("requests") == 0 and s.get("skipped_past_deadline", 0) > 30 and "Stopped at the deadline" in md
        else:
            kept = s.get("requests", 0) > 30 and s.get("not_fetched_past_deadline") == s.get("requests") \
                and all(str(x.get("error")).startswith("not fetched") for x in s.get("rows") or []) and "Stopped at the deadline" in md
        check(r.returncode == 0 and md and kept and time.time() - t < 60,
              f"{name}.py --deadline 0: nothing asked, summary.json and summary.md written, exit {r.returncode} in "
              f"{time.time() - t:.1f} s {r.stderr.strip()[-160:]}")
    for p in sorted(glob.glob(os.path.join(fdir, "[a-z]*.py"))):
        n = os.path.basename(p)[:-3]
        if n not in mods and "--deadline" not in open(p, encoding="utf-8").read():
            print(f"  note: pipeline/fetchers/{n}.py takes no --deadline: fetch.yml's limit is its only clock, and a run "
                  "stopped there has no summary of its own (pipeline/fetchers/__init__.py)")

    C = mods["cbs"]
    check(list(C.CENSUS_CITIES) == [3000, 4000, 5000, 7600, 8500, 7000, 1061, 1063, 8000],
          f"cbs.py: the census cities in priority order, Jerusalem first: {list(C.CENSUS_CITIES)}")
    prio, err = C.census_priority()
    check(not err and len(prio.get(3000, ())) >= 10 and all(prio.get(c) for c in (4000, 5000, 7000, 7600, 8500)),
          f"cbs.py: the areas that matter, from cbs_mixed_areas.json and cbs_validation.json: "
          f"{ {c: len(v) for c, v in prio.items()} } {err}")
    srv = http.server.HTTPServer(("127.0.0.1", 0), CensusMock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    C.CENSUS_SEARCH, C.CENSUS_CSV_API, C.POLITE = base + "/search?search=", base + "/csv?dashboardId={dash}&ID={aid}", 0
    jer = list(range(111, 200)) + list(range(1001, 1061)) + list(range(2001, 2021))    # "1" answers 149: cut at 100
    CensusMock.areas = {"3000-loc": "ירושלים", **{f"3000-{n}": f"ירושלים אזור סטטיסטי {n}" for n in jer},
                        "4000-loc": "חיפה", **{f"4000-{n}": f"חיפה אזור סטטיסטי {n}" for n in range(11, 41)}}
    CensusMock.asked, CensusMock.delay = [], 0.0
    f = C.Fetcher(os.path.join(TMP, "cbs_census"), deadline=120)
    turns, said = [], io.StringIO()          # what the fetcher prints is its log, not this test's
    with contextlib.redirect_stdout(said):
        st = C.part_census_dashboards(f, {3000: {199, 1005, 2003, 9999}, 4000: {15}}, lambda s_: turns.append(dict(s_)))
    j = load(os.path.join(f.out, "census"), "religion_3000.json") or {}
    check(st.get("stopped") is None and CensusMock.asked[:6] == ["3000-loc", "3000-199", "3000-1005", "3000-2003", "4000-loc", "4000-15"]
          and len(CensusMock.asked) == 2 + len(jer) + 30 and len(set(CensusMock.asked)) == len(CensusMock.asked)
          and j.get("areas_found") == len(jer) and sum(1 for a in j.get("areas") or [] if "csv" in a) == len(jer) + 1
          and len(turns) == 2 * len(C.CENSUS_CITIES) and st.get("searched") == [str(c) for c in C.CENSUS_CITIES],
          f"cbs.py part 4: every city's locality and priority areas first (Jerusalem's, then Haifa's), then the rest; the "
          f"search asked again one digit longer where it was cut ({j.get('areas_found')} of {len(jer)} areas found, "
          f"{j.get('searches')} searches); the files and the summary after each city: {CensusMock.asked[:6]} {st}")
    CensusMock.asked, CensusMock.delay = [], 0.006         # the whole part would take 290 answers, 1.7 s at least
    f = C.Fetcher(os.path.join(TMP, "cbs_census_late"), deadline=1.0)
    with contextlib.redirect_stdout(said):
        st = C.part_census_dashboards(f, {3000: {199}}, lambda s_: C.write_summary(f, "t0", s_, "during part 4 (census)"))
    md = open(os.path.join(f.out, "summary.md"), encoding="utf-8").read()
    check("deadline" in str(st.get("stopped")) and 0 < len(CensusMock.asked) < len(jer)
          and (load(os.path.join(f.out, "census"), "religion_3000.json") or {}).get("areas") and "**Partial:**" in md
          and "(passed:" in md and not glob.glob(os.path.join(f.out, "**", "*.tmp"), recursive=True),
          f"cbs.py part 4 at the deadline: stopped, what it had written (the city files, a partial summary): {st}")
    srv.shutdown()

    # the geographic catalogue: by name pattern, any case, one level of subfolders; GEO_MAX files at most; the rest named
    g = C.Fetcher(os.path.join(TMP, "cbs_geo"))
    cat, sub = C.GEO_CATALOG, C.GEO_CATALOG + "/קלפיות 2026"

    def item(n, size=1_000_000, mod="2023-01-01T00:00:00Z", folder=cat):
        return {"Name": n, "ServerRelativeUrl": f"{folder}/{n}", "Length": str(size), "TimeLastModified": mod}
    listings = {
        ("Files", cat): [item("kalpi_April2019_stat2011.xlsx"), item("Kalpi_March2021_Stat2011.XLSX"),
                         item("מפתח מעבר אס 2011 לאס 2022.xlsx"), item("kalpi_October2026_stat2022.xlsx", mod="2026-10-01T00:00:00Z"),
                         item("kalpi_huge_2026.xlsx", 50 * 2 ** 20), item("population_2024.xlsx"), item("map.png"),
                         item("statisticalareas_demography2022.gdb.zip", 30 * 2 ** 20),
                         item("statisticalareas_demography2019.gdb.zip", 20 * 2 ** 20)]
        + [item(f"kalpi_extra{i:02d}_stat2011.xlsx", mod=f"2020-01-{i % 28 + 1:02d}T{i % 24:02d}:00:00Z") for i in range(45)],
        ("Folders", cat): [{"Name": "Forms", "ServerRelativeUrl": cat + "/Forms"}, {"Name": "קלפיות 2026", "ServerRelativeUrl": sub}],
        ("Files", sub): [item("ballot_stations_2026.xlsx", mod="2026-09-01T00:00:00Z", folder=sub)],
    }
    g.listing = lambda name, folder, what="Files": listings.get((what, folder))
    g.get = lambda url, headers=None, timeout=120, tries=3: (200, b"PK\x03\x04" + b"0" * 200_000, {})
    with contextlib.redirect_stdout(said):
        C.part_geo_catalog(g)
        C.write_summary(g, "t0", None)
    taken = {i["name"] for i in g.items if i.get("ok")}
    left = {x["name"]: x["why"] for x in g.not_taken}
    md = open(os.path.join(g.out, "summary.md"), encoding="utf-8").read()
    check({"k21_kalpi_to_stat2011.xlsx", "k24_kalpi_to_stat2011.xlsx", "stat2011_to_stat2022.xlsx", "kalpi_October2026_stat2022.xlsx",
           "ballot_stations_2026.xlsx", "statisticalareas_demography2022.gdb.zip"} <= taken
          and len(taken - {"statisticalareas_demography2022.gdb.zip"}) == C.GEO_MAX
          and sum(1 for w in left.values() if w.startswith("beyond the first")) == 50 - C.GEO_MAX
          and "size cap" in left.get("kalpi_huge_2026.xlsx", "") and "GEO_TAKE" in left.get("population_2024.xlsx", "")
          and "map.png" in left and "older" in left.get("statisticalareas_demography2019.gdb.zip", "") and "Forms/" not in left
          and "listed, not taken" in md and "population_2024.xlsx" in md,
          f"cbs.py geographic catalogue: taken by pattern (any case, a subfolder), the known names renamed, {C.GEO_MAX} files "
          f"at most, every listed file not taken named in summary.md: {len(taken)} taken {sorted(taken)[:5]} {sorted(left.items())[:4]}")
    check(C.ascii_name("קובץ א.xlsx") != C.ascii_name("קובץ ב.xlsx") and C.ascii_name("קובץ א.xlsx").endswith(".xlsx")
          and C.ascii_name("bycode2024.xlsx") == "bycode2024.xlsx",
          f"cbs.py: two Hebrew names never meet as ASCII file names: {C.ascii_name('קובץ א.xlsx')} {C.ascii_name('קובץ ב.xlsx')}")


# ---------------------------------------------------------------- tests
def main():
    t0 = time.time()
    for v in ("no_proxy", "NO_PROXY"):           # the test server is local
        os.environ[v] = "127.0.0.1,localhost"
    k25_30 = subset_k25()
    inputs = os.path.join(TMP, "inputs")
    os.makedirs(inputs)

    print("1. 2022 dry run on a 30% subset")
    o1 = os.path.join(TMP, "o1")
    st = run("--out", o1, "--results-file", k25_30, "--as", "K25", "--inputs", inputs, now=NIGHT)
    res = load(o1, "results.json")
    check(res is not None and st["results_state"] == "ok" and st["has_results"], "results.json published, results_state ok")
    check(0.25 < res["frame"]["counted"]["share"] < 0.35, f"counted share {res['frame']['counted']['share']} is about 30%")
    for k in ("updated_he", "accuracy", "accuracy_real", "history", "source_url", "frame", "checks"):
        check(k in res, f"results.json has {k}")
    check(isinstance(res.get("accuracy_real"), list) and len(res["accuracy_real"]) > 0, "accuracy_real passed through from the replay (PROV-6)")
    check(res["checks"].get("bad_rows") == 0 and res["checks"].get("ignored_columns") == [], "checks.bad_rows / ignored_columns present")
    check(res["updated_he"] == st.get("data_he") and st.get("checked_he"), "results.updated_he is the data time, status has data_he and checked_he")
    for k in ("updated_at", "updated_he", "phase", "has_results", "has_turnout", "exit_polls", "results_state", "errors"):
        check(k in st, f"status has {k}")
    check(st["phase"] == "night" and st["election"] == "K25", "phase night, election K25")
    check(set(st["changed"]) >= {"results.json", "status.json", "state.json"}, f"changed lists the written files: {st['changed']}")
    check(len(res["frame"]["lists"]) >= 10 and all(l["seats_counted"] >= 0 for l in res["frame"]["lists"]), "frame lists present with counted seats")
    stt = load(o1, "state.json")
    check(stt and stt.get("source") == ["K25", k25_30] and stt.get("sha256") == res["checks"]["sha256"], "state.json keyed by source with the accepted sha (OPS-11)")

    print("1b. lenient read: one inconsistent row and a non-numeric column")
    o1b = os.path.join(TMP, "o1b")
    st = run("--out", o1b, "--results-file", odd_k25(k25_30), "--as", "K25", "--inputs", inputs, now=NIGHT)
    res = load(o1b, "results.json")
    check(st["results_state"] == "ok" and res is not None, "file accepted")
    check(res and res["checks"]["bad_rows"] == 1 and res["checks"]["ignored_columns"] == ["שעת עדכון"], f"checks: {res and res['checks']}")

    print("1c. an unknown 2026 layout (WF-1): the lenient reader on variants of the subset")
    _, base_rows = read_expb(k25_30)
    i_v = lambda cells, hdr: cells[hdr.index("כשרים")]   # noqa: E731
    pct = lambda cells, hdr: round(100 * int(cells[hdr.index("מצביעים")]) / max(1, int(cells[hdr.index("בזב")])), 1)   # noqa: E731
    cases = {
        "num_col": (variant(k25_30, "num_col.csv", extra=("אחוז הצבעה", pct)), ["אחוז הצבעה"], 0),
        "num_col_short": (variant(k25_30, "num_short.csv", extra=("סהכ", i_v)), ["סהכ"], 0),
        "yod": (variant(k25_30, "yod.csv", header={"סמל ישוב": "סמל יישוב", "שם ישוב": "שם יישוב"}), [], 0),
        "dash_first": (variant(k25_30, "dash.csv", cell=(0, "מחל", "-")), [], 1),
    }
    for name, (path, ignored, bad) in cases.items():
        ck = {}
        try:
            cols, rows = read_expb(path, strict=False, checks=ck)
            ok = ck == {"bad_rows": bad, "ignored_columns": ignored} and len(rows) == len(base_rows) - bad and len(cols) == len(_)
            check(ok, f"{name}: accepted, checks={ck}, {len(rows)} rows, {len(cols)} lists")
        except Exception as exc:
            check(False, f"{name}: rejected: {exc}")
    weird = variant(k25_30, "weird.csv", header={"קלפי": "מס' קלפי"}, extra=("זמן", lambda c, h: "22:31"))
    try:
        read_expb(weird, strict=False)
        check(False, "weird: a renamed קלפי should be rejected without an alias")
    except ValueError as exc:
        check("missing columns" in str(exc), f"weird: rejected without an alias ({str(exc)[-60:]})")
    ck = {}
    cols, rows = read_expb(weird, strict=False, checks=ck, ignore_columns=["זמן"], column_aliases={"מס' קלפי": "קלפי"})
    check(ck == {"bad_rows": 0, "ignored_columns": ["זמן"]} and len(rows) == len(base_rows), f"weird: accepted with the overrides, checks={ck}")
    o1c = os.path.join(TMP, "o1c")
    c1c = write(os.path.join(TMP, "c1c.json"), {"election_day": "2026-10-27", "ignore_columns": ["זמן"], "column_aliases": {"מס' קלפי": "קלפי"}})
    st = run("--out", o1c, "--config", c1c, "--results-file", weird, "--as", "K25", "--inputs", inputs, now=NIGHT)
    res = load(o1c, "results.json")
    check(st["results_state"] == "ok" and res and res["checks"]["ignored_columns"] == ["זמן"], f"weird: the live_config overrides reach the reader; errors={st['errors']}")

    print("2. bad bodies from the results URL are rejected")
    hdr = open(k25_30, encoding="utf-8-sig").read().splitlines()[0]
    srv, base = serve({
        "/hdr.csv": ("﻿" + hdr + "\n").encode("utf-8"),
        "/bom.html": b"\xef\xbb\xbf<!DOCTYPE html><html><body>blocked</body></html>",
        "/err.json": b'{"error":"rate limited"}',
        "/empty.csv": b"",
        "/k25_30.csv": open(k25_30, "rb").read(),
        "/k26.csv": b"",
    })
    for path, why in (("/hdr.csv", "no counted stations"), ("/bom.html", "HTML or JSON"), ("/err.json", "HTML or JSON"), ("/empty.csv", "empty body")):
        o = os.path.join(TMP, "o2" + path.replace("/", "_").replace(".", "_"))
        st = run("--out", o, "--config", cfg_file("c2.json", results_url=base + path), "--as", "K25", "--inputs", inputs, now=NIGHT)
        err = " ".join(st["errors"])
        check(st["results_state"] == "waiting" and load(o, "results.json") is None and why in err, f"{path}: rejected ({why}); errors={err[:80]}")

    print("2b. a config whose election_day or eligible does not parse falls back and is reported (WF-2)")
    o2b = os.path.join(TMP, "o2b")
    c2b = write(os.path.join(TMP, "c2b.json"), {"election_day": "27.10.2026", "eligible": "7.3M", "results_url": base + "/k25_30.csv"})
    st = run("--out", o2b, "--config", c2b, "--inputs", inputs, now=NIGHT)
    err = " ".join(st["errors"])
    check("config: election_day" in err and "config: eligible" in err, f"both reported: {err[:160]}")
    check(st["results_state"] == "ok" and st["phase"] == "night", "the pass completed with the default election day")
    check(st.get("heartbeat_s") == LF.HEARTBEAT, "status carries heartbeat_s (PAGE-1)")

    print("3. unchanged file is not republished")
    before = open(os.path.join(o1, "results.json"), "rb").read()
    st = run("--out", o1, "--results-file", k25_30, "--as", "K25", "--inputs", inputs, now=NIGHT)
    after = open(os.path.join(o1, "results.json"), "rb").read()
    check(before == after and st["results_state"] == "ok" and "results.json" not in st["changed"], f"results.json untouched, changed={st['changed']}")
    check(len(load(o1, "history.json")) == 1, "history has one entry")

    print("3b. a changed switch re-renders the same file without moving the data time (DOC-3)")
    res0 = json.loads(before)
    later = NIGHT + dt.timedelta(minutes=50)      # still 27.10: updated_he carries a date only after midnight
    c3 = cfg_file("c3.json", projection_paused=True, pause_reason="בדיקה")
    st = run("--out", o1, "--config", c3, "--results-file", k25_30, "--as", "K25", "--inputs", inputs, now=later)
    res = load(o1, "results.json")
    check(res["frame"].get("paused") == "בדיקה" and "results.json" in st["changed"], f"paused published, changed={st['changed']}")
    check(res["updated_at"] == res0["updated_at"] and st.get("data_he") == res0["updated_he"] and len(load(o1, "history.json")) == 1,
          "data time and history unchanged")
    check(res["frame"].get("batch") == res0["frame"].get("batch"), "the last batch stays")
    st = run("--out", o1, "--config", c3, "--results-file", k25_30, "--as", "K25", "--inputs", inputs, now=later)
    check("results.json" not in st["changed"], "same switches again: nothing rewritten")
    st = run("--out", o1, "--config", cfg_file("c3b.json", envelopes_expected=500000), "--results-file", k25_30, "--as", "K25", "--inputs", inputs, now=later)
    res = load(o1, "results.json")
    check("paused" not in res["frame"] and res["frame"]["counted"]["env_override"] == 500000 and res["updated_at"] == res0["updated_at"],
          "unpaused with an envelope total, data time still unchanged")

    print("3c. a file that lost a few counted stations: up to 2% accepted (a CEC correction), more rejected (R8)")
    o3c = os.path.join(TMP, "o3c")
    Server.bodies["/shrink.csv"] = open(k25_30, "rb").read()
    c3c = cfg_file("c3c.json", results_url=base + "/shrink.csv")
    st = run("--out", o3c, "--config", c3c, "--as", "K25", "--inputs", inputs, now=NIGHT)
    full = load(o3c, "results.json")["frame"]["counted"]["share"]
    Server.bodies["/shrink.csv"] = open(drop_rows(k25_30, "k25_99.csv", 100), "rb").read()
    st = run("--out", o3c, "--config", c3c, "--as", "K25", "--inputs", inputs, now=NIGHT + dt.timedelta(minutes=5))
    res = load(o3c, "results.json")
    check(st["results_state"] == "ok" and res["frame"]["counted"]["share"] < full and len(load(o3c, "history.json")) == 1,
          f"1% fewer stations: accepted, the count steps back ({full} -> {res['frame']['counted']['share']}), "
          f"no history point that steps back; errors={st['errors']}")
    Server.bodies["/shrink.csv"] = open(drop_rows(k25_30, "k25_95.csv", 20), "rb").read()
    st = run("--out", o3c, "--config", c3c, "--as", "K25", "--inputs", inputs, now=NIGHT + dt.timedelta(minutes=10))
    check(st["results_state"] == "waiting" and any("shrank" in e for e in st["errors"])
          and load(o3c, "results.json")["checks"]["sha256"] == res["checks"]["sha256"],
          f"5% fewer: rejected, the last good file stays: {st['errors']}")

    print("4. 2026 mode on a synthetic 2026-lettered file")
    o4 = os.path.join(TMP, "o4")
    st = run("--out", o4, "--results-file", synthetic_k26(k25_30), "--inputs", inputs, now=NIGHT)
    res = load(o4, "results.json")
    check(res is not None and res["election"] == "K26" and st["results_state"] == "ok", f"K26 results published; errors={st['errors']}")
    ids = [l["id"] for l in res["frame"]["lists"]] if res else []
    check(set(ids) <= set(LETTERS_2026) and len(ids) >= 12, f"frame lists are 2026 lists: {ids}")
    check(res and res["checks"]["unknown_lists"] == [], "every column maps to a 2026 list")
    check(res and sum(l["seats"] for l in res["frame"]["lists"]) == 120, "projected seats add up to 120")

    print("4b. the register guard (LM-B): more eligible voters counted than configured")
    o4b = os.path.join(TMP, "o4b")
    st = run("--out", o4b, "--config", cfg_file("c4b.json", eligible=1500000), "--results-file", os.path.join(TMP, "k26.csv"), "--inputs", inputs, now=NIGHT)
    res = load(o4b, "results.json")
    check(res and res["frame"]["counted"]["share"] == LF.REGISTER_SLACK, f"share reads {res and res['frame']['counted']['share']}, not 'all counted'")
    check(any(e.startswith("register exceeded") for e in st["errors"]), f"error reported: {st['errors']}")
    st = run("--out", o4b, "--config", cfg_file("c4b2.json", eligible=7400000), "--results-file", os.path.join(TMP, "k26.csv"), "--inputs", inputs, now=NIGHT)
    res = load(o4b, "results.json")
    check(res["frame"]["counted"]["share"] < 0.5 and not any(e.startswith("register") for e in st["errors"]),
          f"eligible corrected without a restart: share {res['frame']['counted']['share']}, errors={st['errors']}")
    st = run("--out", o4b, "--config", cfg_file("c4b3.json", eligible=LF.PLACEHOLDER_ELIGIBLE), "--results-file", os.path.join(TMP, "k26.csv"), "--inputs", inputs, now=NIGHT)
    check(any("7,340,000" in e for e in st["errors"]), f"the placeholder register is reported from 25.10: {st['errors']}")

    print("5. the 22:00 gate: no fetch before, fetch after")
    o5 = os.path.join(TMP, "o5")
    c5 = cfg_file("c5.json", results_url=base + "/k25_30.csv")
    Server.hits.clear()
    st = run("--out", o5, "--config", c5, "--as", "K25", "--inputs", inputs, now=EVENING)
    gets = [h for h in Server.hits if h[0] == "GET"]
    check(st["results_state"] == "before-22" and not gets and load(o5, "results.json") is None, f"19:30: results_state before-22, GET requests: {gets}")
    check(st.get("results_probe", {}).get("http") == 200, f"probe reported: {st.get('results_probe')}")
    check(st["phase"] == "day", "phase day")
    st = run("--out", o5, "--config", c5, "--as", "K25", "--inputs", inputs, now=NIGHT)
    check(st["results_state"] == "ok" and load(o5, "results.json") is not None, "22:30: fetched and published")

    print("5b. the switches act on the cached file while the CEC file is rejected (DOC-3)")
    good = Server.bodies["/k25_30.csv"]
    Server.bodies["/k25_30.csv"] = Server.bodies["/bom.html"]   # the same URL now answers with a maintenance page
    c5b = cfg_file("c5b.json", results_url=base + "/k25_30.csv", projection_paused=True, pause_reason="הקובץ לא עקבי")
    st = run("--out", o5, "--config", c5b, "--as", "K25", "--inputs", inputs, now=NIGHT)
    res = load(o5, "results.json")
    check(st["results_state"] == "waiting" and res["frame"].get("paused") == "הקובץ לא עקבי" and "results.json" in st["changed"],
          f"rejected fetch, paused published from the cache; errors={st['errors']}")
    check(os.path.exists(os.path.join(o5, LF.RESULTS_CACHE)) and not glob.glob(os.path.join(o5, "*.csv")), "the cache is a dotfile, not a published file")
    # a run hand-off: the next run is seeded from the published files only, so it has no cached CEC file (R4)
    o5h = os.path.join(TMP, "o5h")
    os.makedirs(o5h)
    for p in glob.glob(os.path.join(o5, "*.json")):
        shutil.copy(p, o5h)
    res0 = load(o5h, "results.json")
    st = run("--out", o5h, "--config", cfg_file("c5h.json", results_url=base + "/k25_30.csv"), "--as", "K25", "--inputs", inputs, now=NIGHT)
    res = load(o5h, "results.json")
    check(st["results_state"] == "waiting" and "paused" not in res["frame"] and res["updated_at"] == res0["updated_at"]
          and res["frame"]["counted"] == res0["frame"]["counted"] and not any("not applied" in e for e in st["errors"]),
          f"hand-off, file still rejected: the pause lifted on the published results.json, data time kept; errors={st['errors']}")
    c5h2 = cfg_file("c5h2.json", results_url=base + "/k25_30.csv", envelopes_expected=500000)
    st = run("--out", o5h, "--config", c5h2, "--as", "K25", "--inputs", inputs, now=NIGHT)
    check(any("not applied yet" in e for e in st["errors"]) and load(o5h, "results.json")["frame"]["counted"].get("env_override") != 500000,
          f"hand-off: envelopes_expected cannot act without the file, and says so: {st['errors']}")
    Server.bodies["/k25_30.csv"] = good
    st = run("--out", o5h, "--config", c5h2, "--as", "K25", "--inputs", inputs, now=NIGHT + dt.timedelta(minutes=3))
    res = load(o5h, "results.json")
    check(st["results_state"] == "ok" and res["frame"]["counted"].get("env_override") == 500000 and res["updated_at"] == res0["updated_at"]
          and not any("not applied" in e for e in st["errors"]),
          f"the file readable again (unchanged): envelopes_expected acts, the data time stays: {st['errors']}")

    print("6. manual inputs: broken turnout.json, exit polls, lean during voting")
    o6 = os.path.join(TMP, "o6")
    write(os.path.join(inputs, "turnout.json"), {"national": {"10:00": 15.2, "12:00": 27.9, "19:00": 60.1}, "source": "הודעת הוועדה",
                                                 "claims": [{"time": "16:00", "source": "x", "text": "y"}], "sectors_time": "19:30"})
    c6 = cfg_file("c6.json", results_url=base + "/nothing", station_turnout_url=base + "/k25_30.csv")
    st = run("--out", o6, "--config", c6, "--as", "K25", "--inputs", inputs, now=EVENING)
    T = load(o6, "turnout.json")
    check(st["has_turnout"] and T["national"].get("19:00") == 60.1, "turnout published, the 19:00 key accepted")
    check(T.get("sectors") and "lean" not in T and T["claims"] == [], "sector turnout published; lean and claims withheld during voting")
    write(os.path.join(inputs, "turnout.json"), '{"national": {"10:00": 15.2, "12:00": 27.9,}')
    st = run("--out", o6, "--config", c6, "--as", "K25", "--inputs", inputs, now=EVENING)
    T = load(o6, "turnout.json")
    check(st["has_turnout"] and T["national"].get("12:00") == 27.9, "broken turnout.json: last good figures kept")
    check(any(e.startswith("turnout:") for e in st["errors"]), f"error reported: {st['errors']}")
    write(os.path.join(inputs, "turnout.json"), {"national": {"10:00": "15.2", "1200": 27.9, "14:00": 38.4, "16:00": True}})
    st = run("--out", o6, "--config", c6, "--as", "K25", "--inputs", inputs, now=EVENING)
    T = load(o6, "turnout.json")
    err = next((e for e in st["errors"] if e.startswith("turnout: ignored")), "")
    check(list(T["national"]) == ["14:00"] and all(s in err for s in ('10:00: "15.2"', "1200: 27.9", "16:00: true")), f"typos reported, not dropped silently (DOC-7): {err}")
    write(os.path.join(inputs, "turnout.json"), {"national": {"10:00": 15.2}})
    write(os.path.join(inputs, "exit_polls.json"), {"polls": [{"outlet": "כאן 11", "time": "22:00", "seats": {"מחל": 25}}]})
    st = run("--out", o6, "--config", c6, "--as", "K25", "--inputs", inputs, now=EVENING)
    check(st["exit_polls"] is False and load(o6, "exit_polls.json") is None, "exit polls not published before 22:00")
    st = run("--out", o6, "--config", cfg_file("c6b.json", results_url=base + "/nothing", station_turnout_url=base + "/k25_30.csv", lean_during_voting=True),
             "--as", "K25", "--inputs", inputs, now=NIGHT)
    T = load(o6, "turnout.json")
    check(st["exit_polls"] is True and load(o6, "exit_polls.json")["polls"][0]["outlet"] == "כאן 11", "exit polls published after 22:00")
    check("lean" in T, "lean published after 22:00")
    gap = next((e for e in st["errors"] if e.startswith("exit polls: disclosure")), "")
    check("כאן 11: commissioner, pollster, date, population, n_invited, n, moe, questions" in gap,
          f"an exit poll without its §16ה(ב)–(ג) disclosure items is reported: {gap}")
    full_poll = {"outlet": "כאן 11", "pollster": "קנטאר", "commissioner": "כאן 11", "date": "27.10", "time": "22:00",
                 "seats": {"מחל": 25}, "population": "לא פורסם", "n_invited": "לא פורסם", "n": 1650, "moe": 2.4, "questions": "לא פורסם"}
    write(os.path.join(inputs, "exit_polls.json"), {"polls": [full_poll]})
    st = run("--out", o6, "--config", c6, "--as", "K25", "--inputs", inputs, now=NIGHT)
    check(st["exit_polls"] is True and not any(e.startswith("exit polls") for e in st["errors"]),
          f"every item given, 'לא פורסם' included: nothing reported: {st['errors']}")
    os.remove(os.path.join(inputs, "exit_polls.json"))
    st = run("--out", o6, "--config", c6, "--as", "K25", "--inputs", inputs, now=NIGHT)
    check(st["exit_polls"] is False and load(o6, "exit_polls.json") is None and "exit_polls.json" in st["changed"], "input removed: published copy removed (OPS-14)")
    write(os.path.join(inputs, "turnout.json"), {"national": {}, "source": "", "claims": []})
    st = run("--out", o6, "--config", write(os.path.join(TMP, "broken.json"), "{ nope"), "--as", "K25", "--inputs", inputs, now=NIGHT)
    check(any(e.startswith("config:") for e in st["errors"]) and st["results_state"] in ("waiting", "ok"), f"broken config reported, pass completed: {st['errors']}")

    print("6b. per-station releases: column_aliases, another delimiter, a percentage column, blank figures")
    rel = station_release(k25_30, 0.3, "rel30.csv", seed=3)
    rows0, _ = LF.station_rows(open(rel, "rb").read())
    alias = {"locality": "סמל ישוב", "box": "קלפי", "registered": "בזב", "voted": "מצביעים"}
    ren = rework_release(rel, "rel_renamed.csv", header=["locality", "name", "box", "registered", "voted"])
    try:
        LF.station_rows(open(ren, "rb").read())
        check(False, "renamed headers without column_aliases should be refused")
    except ValueError as exc:
        check("unknown columns" in str(exc), f"renamed headers without column_aliases: refused ({str(exc)[:60]})")
    check(LF.station_rows(open(ren, "rb").read(), alias)[0] == rows0, "the same release under other names, read with column_aliases")
    check(LF.station_rows(open(rework_release(rel, "rel_semi.csv", delim=";"), "rb").read())[0] == rows0, "a semicolon-separated release")
    pct = rework_release(rel, "rel_pct.csv", header=["סמל יישוב", "שם יישוב", "מספר קלפי", "בעלי זכות בחירה", "אחוז הצבעה"],
                         cells=lambda i, c: c[:4] + [f"{100 * int(c[4]) / int(c[3]):.2f}%" if int(c[3] or 0) else ""])
    rows, _ = LF.station_rows(open(pct, "rb").read())
    check(len(rows) == len(rows0) and all(a["code"] == b["code"] and a["kalpi"] == b["kalpi"] and a["elig"] == b["elig"]
                                          and (a["voters"] is None if not b["elig"] else abs(a["voters"] - b["voters"]) <= 1)
                                          for a, b in zip(rows, rows0)), "a turnout percentage instead of voters: voters = % x eligible")
    Server.bodies["/rel_renamed.csv"] = open(ren, "rb").read()
    o6b = os.path.join(TMP, "o6b")
    write(os.path.join(inputs, "turnout.json"), {"national": {}, "sectors_time": "19:30"})
    st = run("--out", o6b, "--config", cfg_file("c6b1.json", results_url=base + "/nothing", station_turnout_url=base + "/rel_renamed.csv",
                                                 column_aliases=alias), "--as", "K25", "--inputs", inputs, now=EVENING)
    T = load(o6b, "turnout.json")
    check(T.get("sectors") and "station_error" not in T, f"live_config column_aliases reach the feed's per-station reader: {T.get('station_error')}")
    blank = rework_release(rel, "rel_blank.csv", cells=blank_some)
    Server.bodies["/rel_blank.csv"] = open(blank, "rb").read()
    write(os.path.join(inputs, "turnout.json"), {"national": {}, "sectors_time": "19:20"})
    st = run("--out", o6b, "--config", cfg_file("c6b2.json", results_url=base + "/nothing", station_turnout_url=base + "/rel_blank.csv"),
             "--as", "K25", "--inputs", inputs, now=EVENING)
    T = load(o6b, "turnout.json")
    rows, _ = LF.station_rows(open(blank, "rb").read())
    rep = [r for r in rows if r["voters"] and r["elig"]]
    want = round(sum(r["voters"] for r in rep) / sum(r["elig"] for r in rep), 4)
    n_none, n_zero = sum(r["voters"] is None for r in rows), sum(r["voters"] == 0 for r in rows)
    ex = T.get("sectors_excluded") or {}
    check(n_none and n_zero and T.get("stations_national") == want and ex.get("no figure") == n_none and ex.get("zero voters") == n_zero,
          f"blank, '-' and 0 figures are not reported yet: out of the national turnout {T.get('stations_national')} (want {want}), "
          f"excluded {ex}")
    check(set(ex) <= set(LF.EXCLUDED_KEYS), f"sectors_excluded uses only the documented keys (the page's labels): {sorted(ex)}")
    write(os.path.join(inputs, "turnout.json"), {"national": {}, "source": "", "claims": []})

    print("7. drill is marked and discarded by a real run")
    o7 = os.path.join(TMP, "o7")
    st = run("--out", o7, "--drill", "--results-file", K25, "--drill-fraction", "0.5", "--inputs", inputs, now=EVENING)
    res = load(o7, "results.json")
    check(st.get("drill") is True and res and res.get("drill") is True and 0.2 < res["frame"]["counted"]["share"] < 0.8,
          f"drill output marked, {res and res['frame']['counted']['share']} counted at fraction 0.5")
    st = run("--out", o7, "--drill", "--results-file", K25, "--drill-fraction", "1.0", "--inputs", inputs, now=EVENING)
    res = load(o7, "results.json")
    check(res and res["frame"]["counted"]["share"] >= 0.99 and res["frame"]["counted"]["envelopes"], "fraction 1.0: everything counted, envelopes included")
    st = run("--out", o7, "--results-file", k25_30, "--as", "K25", "--inputs", inputs, now=NIGHT)
    res = load(o7, "results.json")
    check(not st.get("drill") and res and not res.get("drill") and len(load(o7, "history.json")) == 1, "real run discarded the drill files (OPS-3)")
    real_now = LF.now_il

    def refused(when, minutes, start=None):
        LF.now_il = lambda: when
        try:
            return LF.drill_refused({"election_day": "2026-10-27"}, minutes, start)
        finally:
            LF.now_il = real_now
    il = lambda d, hh, mm: dt.datetime(2026, d // 100, d % 100, hh, mm, tzinfo=IL)   # noqa: E731  (MMDD)
    for when, minutes, start, want in ((il(1023, 22, 0), 40, None, False), (il(1023, 23, 10), 40, None, True),
                                       (il(1023, 23, 30), 40, il(1023, 22, 50).timestamp(), False),
                                       (il(1028, 9, 0), 40, None, True), (il(1105, 23, 0), 40, None, True),
                                       (il(1106, 0, 0), 40, None, False), (il(1015, 12, 0), 40, None, False)):
        why = refused(when, minutes, start)
        check(bool(why) == want, f"drill with --publish at {when:%d.%m %H:%M}, {minutes} min"
                                 f"{' (begun ' + dt.datetime.fromtimestamp(start, IL).strftime('%H:%M') + ')' if start else ''}: "
                                 f"{'refused' if why else 'allowed'} (WF-2)")
    try:
        run("--out", os.path.join(TMP, "o7r"), "--drill", "--publish", "--minutes", "40", "--inputs", inputs, now=il(1023, 23, 10))
        check(False, "live_fetch.py --drill --publish at 23.10 23:10 for 40 minutes should be refused")
    except SystemExit as exc:
        check("refused" in str(exc) and not os.path.exists(os.path.join(TMP, "o7r", "results.json")),
              f"live_fetch.py --drill --publish into the ban: refused before any pass ({str(exc)[:80]})")
    LF.DRILL = False                              # the refused main() left its drill flag set (a process runs main once)

    print("8. Actions-mode publisher (live-data): reset cycle against a bare repository with a second writer")
    origin = os.path.join(TMP, "origin.git")
    sh(["git", "init", "-q", "--bare", "-b", "main", origin], TMP)
    repo = os.path.join(TMP, "repo")
    sh(["git", "clone", "-q", origin, repo], TMP)
    for r in (repo,):
        sh(["git", "config", "user.email", "t@example.com"], r)
        sh(["git", "config", "user.name", "test"], r)
    os.makedirs(os.path.join(repo, "site", "live"))
    shutil.copy(os.path.join(ROOT, "site", "live", "status.json"), os.path.join(repo, "site", "live", "status.json"))
    sh(["git", "add", "-A"], repo)
    sh(["git", "commit", "-q", "-m", "code"], repo)
    sh(["git", "push", "-q", "origin", "HEAD:main"], repo)
    r1, _ = LF.publish(o1, "actions", wt=os.path.join(repo, ".live-data"), repo=repo)
    check(r1 == "pushed", f"first publish creates live-data: {r1}")
    files = sh(["git", "ls-tree", "--name-only", "origin/live-data", "live/"], repo).split()
    check("live/results.json" in files and "live/status.json" in files, f"live-data holds {files}")
    # another writer (the workflow) commits with the same reset cycle
    other = os.path.join(TMP, "other")
    sh(["git", "clone", "-q", "-b", "live-data", origin, other], TMP)
    sh(["git", "config", "user.email", "w@example.com"], other)
    sh(["git", "config", "user.name", "workflow"], other)
    write(os.path.join(other, "live", "status.json"), {"phase": "night", "writer": "workflow"})
    sh(["git", "commit", "-qam", "workflow"], other)
    sh(["git", "push", "-q", "origin", "HEAD:live-data"], other)
    r2, _ = LF.publish(o1, "actions", wt=os.path.join(repo, ".live-data"), repo=repo)
    check(r2 == "pushed", f"publish after a foreign push: {r2}")
    sh(["git", "fetch", "-q", "origin", "live-data"], other)
    tip = json.loads(sh(["git", "show", "origin/live-data:live/status.json"], other))
    check(tip.get("writer") is None and tip.get("has_results") is True, "the laptop's files are on the tip, no rebase, no conflict")
    r3, _ = LF.publish(o1, "actions", wt=os.path.join(repo, ".live-data"), repo=repo)
    check(r3 == "unchanged", f"nothing new: {r3}")
    check(len(sh(["git", "rev-list", "origin/live-data"], other).split()) == 4, "four commits on live-data (placeholder, laptop, workflow, laptop)")

    print("8b. laptop mode takes live_input/ and live_config.json from origin/main every pass (DOC-2)")
    editor = os.path.join(TMP, "editor")                 # the operator editing on GitHub
    sh(["git", "clone", "-q", "-b", "main", origin, editor], TMP)
    sh(["git", "config", "user.email", "e@example.com"], editor)
    sh(["git", "config", "user.name", "editor"], editor)
    write(os.path.join(editor, "live_input", "turnout.json"), {"national": {"10:00": 15.2}})
    write(os.path.join(editor, "pipeline", "live_config.json"), {"election_day": "2026-10-27", "projection_paused": True})
    sh(["git", "add", "-A"], editor)
    sh(["git", "commit", "-q", "-m", "inputs"], editor)
    sh(["git", "push", "-q", "origin", "HEAD:main"], editor)
    write(os.path.join(repo, "live_input", "turnout.json"), {"national": {"10:00": 99}})   # a stale local copy
    LF.refresh_inputs("main", repo=repo)
    check(load(os.path.join(repo, "live_input"), "turnout.json") == {"national": {"10:00": 15.2}}
          and load(os.path.join(repo, "pipeline"), "live_config.json").get("projection_paused") is True, "both files taken from origin/main")
    sh(["git", "rm", "-q", "live_input/turnout.json"], editor)
    sh(["git", "commit", "-q", "-m", "retract"], editor)
    sh(["git", "push", "-q", "origin", "HEAD:main"], editor)
    LF.refresh_inputs("main", repo=repo)
    check(not os.path.exists(os.path.join(repo, "live_input", "turnout.json")), "a file deleted on GitHub disappears locally (OPS-14)")

    print("8c. branch mode: site/live/ on main, the operator's commits kept, a rejected push redone")
    wt = os.path.join(repo, ".live-main")
    ob = os.path.join(TMP, "ob")
    shutil.copytree(o1, ob)
    op_tip = sh(["git", "rev-parse", "origin/main"], editor)           # main after the editor's pushes (8b)
    r, sha = LF.publish(ob, "branch", wt=wt, repo=repo)
    sh(["git", "fetch", "-q", "origin"], editor)
    changed = sh(["git", "show", "--name-only", "--format=", "origin/main"], editor).split()
    check(r == "pushed" and sha == sh(["git", "rev-parse", "origin/main"], editor), f"pushed to main: {r}")
    check(changed and all(f.startswith("site/live/") for f in changed) and "site/live/results.json" in changed,
          f"the commit touches site/live/ only: {changed}")
    check(sh(["git", "merge-base", "--is-ancestor", op_tip, "origin/main"], editor) == "", "the editor's commits are its ancestors (no rebase, nothing lost)")
    check(sh(["git", "log", "-1", "--format=%s", "origin/main"], editor).startswith("live "), "commit message 'live HH:MM'")
    # the operator pushes turnout to main (pull --rebase first: the feed commits there) while the feed's data changes
    sh(["git", "pull", "-q", "--rebase", "origin", "main"], editor)
    write(os.path.join(editor, "live_input", "turnout.json"), {"national": {"10:00": 15.2, "12:00": 27.9}})
    sh(["git", "add", "-A"], editor)
    sh(["git", "commit", "-q", "-m", "turnout 12:00"], editor)
    sh(["git", "push", "-q", "origin", "HEAD:main"], editor)
    op_tip = sh(["git", "rev-parse", "HEAD"], editor)
    write(os.path.join(ob, "status.json"), {**load(ob, "status.json"), "phase": "day"})
    real_git, raced = LF.git, []

    def racing_git(*args, **kw):                   # another writer pushes to main just before the feed's first push
        if args[:1] == ("push",) and not raced:
            raced.append(1)
            write(os.path.join(editor, "live_input", "turnout.json"), {"national": {"10:00": 15.2, "12:00": 27.9, "14:00": 38.4}})
            sh(["git", "commit", "-qam", "turnout 14:00"], editor)
            sh(["git", "push", "-q", "origin", "HEAD:main"], editor)
        return real_git(*args, **kw)
    LF.git = racing_git
    try:
        r, sha = LF.publish(ob, "branch", wt=wt, repo=repo)
    finally:
        LF.git = real_git
    sh(["git", "fetch", "-q", "origin"], editor)
    tip_turnout = json.loads(sh(["git", "show", "origin/main:live_input/turnout.json"], editor))
    check(r == "pushed" and raced and "14:00" in tip_turnout["national"], f"rejected push redone on the new tip: {r}")
    check(json.loads(sh(["git", "show", "origin/main:site/live/status.json"], editor)).get("phase") == "day",
          "the feed's new status is on main")
    parents = sh(["git", "log", "--format=%s", "-3", "origin/main"], editor).splitlines()
    check(parents[1:] == ["turnout 14:00", "turnout 12:00"], f"linear history, the operator's commits kept: {parents}")
    check(LF.publish(ob, "branch", wt=wt, repo=repo)[0] == "unchanged", "nothing new: unchanged")

    print("8d. cadence and the Pages build request (mock API)")
    api_srv = http.server.HTTPServer(("127.0.0.1", 0), Api)
    threading.Thread(target=api_srv.serve_forever, daemon=True).start()
    Api.origin = origin
    saved_env = {k: os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_API_URL", "LIVE_BUILD_WAIT")}
    os.environ.update({"GH_TOKEN": "test-token", "GITHUB_REPOSITORY": "o/r", "LIVE_BUILD_WAIT": "0",
                       "GITHUB_API_URL": f"http://127.0.0.1:{api_srv.server_address[1]}"})
    os.environ.pop("GITHUB_TOKEN", None)
    try:
        oc = os.path.join(TMP, "oc")
        os.makedirs(oc)
        for n in ("status.json", "turnout.json", "state.json"):
            shutil.copy(os.path.join(ob, n), oc)
        write(os.path.join(oc, "status.json"), {**load(oc, "status.json"), "phase": "day", "has_results": False})
        for n in ("results.json", "history.json"):           # the day: no results on main yet
            sh(["git", "rm", "-q", f"site/live/{n}"], wt)
        sh(["git", "commit", "-q", "-m", "day"], wt)
        sh(["git", "push", "-q", "origin", "HEAD:main"], wt)
        T0 = 1_800_000_000.0
        Api.calls.clear()
        Api.latest = "old"
        LF.CHANGED[:] = ["status.json"]
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0)
        posts = [c for c in Api.calls if c[0] == "POST"]
        check(res.get("published") == "pushed" and "requested" in res.get("build", ""), f"first pass: published and a build requested: {res}")
        check([c[1] for c in Api.calls] == ["/repos/o/r/pages/builds/latest", "/repos/o/r/pages/builds"]
              and posts[0][2] == "Bearer test-token", f"GET latest, then POST /pages/builds with the token: {Api.calls}")
        tip = sh(["git", "ls-remote", origin, "refs/heads/main"], TMP).split()[0]
        write(os.path.join(oc, "status.json"), {**load(oc, "status.json"), "updated_he": "10:05", "x": 1})
        LF.CHANGED[:] = ["status.json"]
        Api.calls.clear()
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 60)
        check(res.get("published") == "held" and 410 <= res.get("next_publish_s", 0) <= 420 and not Api.calls
              and sh(["git", "ls-remote", origin, "refs/heads/main"], TMP).split()[0] == tip, f"a change 1 minute later is held: {res}")
        LF.CHANGED[:] = []
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 200)
        check(res.get("published") == "held", f"still held without a new change: {res}")
        shutil.copy(os.path.join(ob, "results.json"), oc)    # the first results file (22:00)
        LF.CHANGED[:] = ["results.json"]
        Api.latest = "tip"                                  # this time the push itself started a build
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 240)
        check(res.get("published", "").startswith("pushed (results.json: first") and "started by the push" in res.get("build", "")
              and not [c for c in Api.calls if c[0] == "POST"], f"the first results go out at once, no second build: {res}")
        write(os.path.join(oc, "status.json"), {**load(oc, "status.json"), "x": 2})
        LF.CHANGED[:] = ["status.json"]
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 300)
        check(res.get("published") == "held", f"then the cadence again: {res}")
        write(os.path.join(oc, "exit_polls.json"), {"polls": [{"outlet": "כאן 11", "seats": {"מחל": 25}}]})
        LF.CHANGED[:] = ["exit_polls.json"]
        Api.latest, Api.build_code = "old", 500
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 320)
        check(res.get("published", "").startswith("pushed (exit_polls.json: first") and "failed (500)" in res.get("build", ""),
              f"the first exit polls at once; a failed build request is reported: {res}")
        LF.CHANGED[:] = []
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 340)
        check("build" not in res, f"no retry within {LF.BUILD_GAP} s: {res}")
        Api.build_code = 201
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 380)
        check("requested" in res.get("build", ""), f"retried after {LF.BUILD_GAP} s: {res}")
        write(os.path.join(oc, "status.json"), {**load(oc, "status.json"), "x": 3})
        LF.CHANGED[:] = ["status.json"]
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 320 + 470)
        check(res.get("published") == "held", f"7 min 50 s after the last publish: held ({res})")
        LF.CHANGED[:] = []
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 320 + 480)
        check(res.get("published") == "pushed", f"8 minutes after the last publish: published ({res})")
        # a first exit-polls file whose push is rejected every time is retried at the next pass, not after the cadence
        sh(["git", "rm", "-q", "site/live/exit_polls.json"], wt)
        sh(["git", "commit", "-q", "-m", "retracted"], wt)
        sh(["git", "push", "-q", "origin", "HEAD:main"], wt)
        LF.CHANGED[:] = ["exit_polls.json"]
        real_sleep = time.sleep

        def refusing_git(*args, **kw):
            if args[:1] == ("push",):
                return subprocess.CompletedProcess(args, 1, "", "rejected")
            return real_git(*args, **kw)
        LF.git, time.sleep = refusing_git, (lambda s: None)
        try:
            res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 850)
        finally:
            LF.git, time.sleep = real_git, real_sleep
        check(res.get("published") == "push failed" and not os.path.exists(os.path.join(wt, "site", "live", "exit_polls.json")),
              f"every push rejected: 'push failed', the worktree back at the published tip ({res.get('published')})")
        LF.CHANGED[:] = []
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 860)
        check(res.get("published", "").startswith("pushed (exit_polls.json: first"),
              f"the next pass, 1 minute after the last publish: the first exit polls go out at once ({res.get('published')})")
        res = LF.publish_step(oc, "branch", 5, wt, "main", repo=repo, now=T0 + 1000, now_publish=True)
        check("published" not in res, f"--flush with nothing pending does nothing: {res}")
        # Actions mode: live-data every changed pass, pages.yml dispatched
        Api.calls.clear()
        LF.CHANGED[:] = ["status.json"]
        res = LF.publish_step(oc, "actions", 8, os.path.join(repo, ".live-data"), "live-data", repo=repo, now=T0 + 2000)
        disp = [c for c in Api.calls if c[0] == "POST"]
        check(res.get("published", "").startswith("pushed") and "dispatched" in res.get("build", "")
              and disp and disp[0][1] == "/repos/o/r/actions/workflows/pages.yml/dispatches" and json.loads(disp[0][3]) == {"ref": "main"},
              f"Actions mode: live-data pushed, pages.yml dispatched on main: {res}")
        check(LF.pages_source(repo) == ("legacy", "main"), "the Pages source read from the API: legacy, main")
        Api.build_type = "workflow"
        a = types.SimpleNamespace(mode="auto", branch=None, wt=None, repo=repo)
        check(LF.publish_target(a, [])[:2] == ("actions", "live-data"), "auto: GitHub Actions -> the live-data path")
        Api.build_type = "legacy"
        check(LF.publish_target(a, [])[:2] == ("branch", "main"), "auto: Deploy from a branch -> site/live/ on main")

        # timestamps alone (the status heartbeat, the probe's time, state.json) wait quiet_every minutes (R3)
        def tip():
            return sh(["git", "ls-remote", origin, "refs/heads/main"], TMP).split()[0]

        def stamp(probe_at, extra=None):
            st_ = {**load(oc, "status.json"), "updated_at": f"2026-10-27T10:{probe_at[-2:]}:00+02:00", "updated_he": probe_at,
                   "checked_he": probe_at, "results_probe": {"http": 404, "at_he": probe_at}, **(extra or {})}
            write(os.path.join(oc, "status.json"), st_)
            write(os.path.join(oc, "state.json"), {**load(oc, "state.json"), "probe": {"http": 404, "at_he": probe_at, "ts": T0}})
            LF.CHANGED[:] = ["status.json", "state.json"]
        T1 = T0 + 2000
        LF.CHANGED[:] = ["status.json"]
        before = tip()
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T1)
        check(res.get("published") == "unchanged" and tip() == before, f"nothing differs from what is published: unchanged, no push ({res})")
        stamp("10:00", {"errors": ["results: HTTP Error 404"]})
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T1 + 480)
        check(res.get("published") == "pushed", f"a new error is news: published at the cadence ({res.get('published')})")
        T2 = T1 + 480
        stamp("10:10")
        before = tip()
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T2 + 600)
        check(res.get("published") == "held (timestamps only)" and res.get("next_publish_s") == 1200 and tip() == before,
              f"10 minutes later, timestamps and the probe's time only: held for {LF.QUIET_EVERY} minutes ({res})")
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T2 + 1799)
        check(res.get("published") == "held (timestamps only)", f"still held at 29:59 ({res.get('published')})")
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T2 + 1800)
        check(res.get("published") == "pushed" and tip() != before, f"published {LF.QUIET_EVERY} minutes after the last ({res.get('published')})")
        T3 = T2 + 1800
        stamp("10:45")
        before = tip()
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T3 + 60, now_publish=True)
        check(res.get("published") == "held (timestamps only)" and tip() == before,
              f"--flush at the end of a run: timestamps alone are not pushed (the next run takes them up, R2): {res.get('published')}")
        stamp("10:46", {"errors": []})
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T3 + 120)
        check(res.get("published") == "held" and res.get("next_publish_s") == 360, f"news 2 minutes after a publish: the 8-minute cadence ({res})")
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T3 + 130, now_publish=True)
        check(res.get("published") == "pushed" and tip() != before, f"--flush publishes held news at once ({res.get('published')})")
        check(LF.quiet_every(8, NIGHT, DAY) == 30 and LF.quiet_every(20, NIGHT, DAY) == 40
              and LF.quiet_every(8, dt.datetime(2026, 10, 28, 11, 59, tzinfo=IL), DAY) == 30
              and LF.quiet_every(8, dt.datetime(2026, 10, 28, 12, 0, tzinfo=IL), DAY) == LF.QUIET_AFTER == 60,
              "quiet_every: 30 minutes (twice the cadence when longer), 60 from 28.10 12:00 (WF-9)")

        print("8e. seeding a run, the reset, and one pass of live_fetch.py --publish")
        os_ = os.path.join(TMP, "os")
        res = LF.seed(os_, "branch", wt, "main", repo)
        check(set(res["seeded"]) >= {"status.json", "results.json", "exit_polls.json"} and load(os_, "results.json") is not None,
              f"seeded from main's site/live/: {res}")
        pub = load(os_, LF.PUB) or {}
        last_live = int(sh(["git", "log", "-1", "--format=%ct", "--grep=^live ", "--", "site/live"], wt))
        check(pub.get("dirty") is False and pub.get("last") == last_live > 0,
              f"the seeded run carries the cadence over: last publish = the newest 'live' commit ({pub})")
        write(os.path.join(os_, "status.json"), {**load(os_, "status.json"), "updated_he": "11:11", "checked_he": "11:11"})
        LF.CHANGED[:] = ["status.json"]
        before = tip()
        res = LF.publish_step(os_, "branch", 8, wt, "main", repo=repo)
        check(res.get("published", "").startswith("held") and tip() == before,
              f"a new run's first pass does not publish at once (R2): {res.get('published')}")
        write(os.path.join(oc, "status.json"), {**load(oc, "status.json"), "drill": True})
        LF.CHANGED[:] = ["status.json"]
        LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 5000)
        res = LF.seed(os.path.join(TMP, "os2"), "branch", wt, "main", repo)
        check(res["seeded"] == [] and "rehearsal" in res.get("note", ""), f"a drill on main is not seeded: {res}")
        LF.CHANGED[:] = []
        LF.reset_out(oc)
        res = LF.publish_step(oc, "branch", 8, wt, "main", repo=repo, now=T0 + 5010, now_publish=True)
        sh(["git", "fetch", "-q", "origin"], wt)
        files = sh(["git", "ls-tree", "--name-only", "origin/main", "site/live/"], wt).split()
        ph = json.loads(sh(["git", "show", "origin/main:site/live/status.json"], wt))
        check(res.get("published") == "pushed" and files == ["site/live/status.json"] and ph == LF.PLACEHOLDER,
              f"reset: only the placeholder status left on main ({files})")
        check("requested" in res.get("build", ""), f"a one-shot publish asks for the build at once, 10 s after the last one: {res}")
        if os.environ.get("HEALTH_GATE"):     # daily.yml / the drill: the code's health, not the repository's state (WF-4)
            print("  skip the repository's site/live/status.json (HEALTH_GATE)")
        else:
            check(json.load(open(os.path.join(ROOT, "site", "live", "status.json"), encoding="utf-8")) == LF.PLACEHOLDER,
                  "site/live/status.json in the repository is the placeholder of live_fetch.PLACEHOLDER")
        res = LF.seed(os.path.join(TMP, "os3"), "branch", wt, "main", repo, drill=True)
        check(res.get("seeded") == ["status.json"], f"a drill may start over the placeholder: {res}")
        oe = os.path.join(TMP, "oe")
        LF.seed(oe, "branch", wt, "main", repo)
        args = ["--out", oe, "--publish", "--no-refresh", "--mode", "branch", "--branch", "main", "--wt", wt, "--repo", repo,
                "--results-file", k25_30, "--as", "K25", "--inputs", inputs, "--config", cfg_file("ce.json", publish_every_min=6)]
        Api.calls.clear()
        st = run(*args, now=NIGHT)
        sh(["git", "fetch", "-q", "origin"], wt)
        on_main = json.loads(sh(["git", "show", "origin/main:site/live/results.json"], wt))
        check(st.get("published", "").startswith("pushed (results.json: first") and on_main["checks"]["counted_stations"] > 0,
              f"one pass with --publish: results on main at once: {st.get('published')} / {st.get('build')}")
        check(st.get("heartbeat_s") == 1800 and st.get("publish_mode") == "branch" and load(oe, "status.json").get("heartbeat_s") == 1800,
              f"status: heartbeat_s = the longest gap of a healthy feed (30 min with a 6-minute cadence), publish_mode branch: "
              f"{st.get('heartbeat_s')}, {st.get('publish_mode')}")
        st = run(*args, now=NIGHT + dt.timedelta(minutes=1))
        check("published" not in st and st["changed"] == [], f"the same file a minute later: nothing to publish ({st.get('published')}, {st['changed']})")
        try:
            LF.seed(os.path.join(TMP, "os4"), "branch", wt, "main", repo, drill=True)
            check(False, "a drill over the real night's files on main should be refused")
        except SystemExit as exc:
            check("real election" in str(exc), f"a drill is refused while main holds the real night's files (WF-2): {str(exc)[:90]}")
        os.environ.update({"PUBLISH_MODE": "branch", "PAGES_SOURCE": "legacy"})
        st = run("--out", os.path.join(TMP, "oh"), "--results-file", k25_30, "--as", "K25", "--inputs", inputs, now=NIGHT)
        check(st.get("heartbeat_s") == 60 * LF.QUIET_EVERY and st.get("publish_mode") == "branch" and "pages_source" not in st,
              f"the probe pass reports the workflow's mode; legacy is not flagged in branch mode: {st.get('heartbeat_s')}")
        os.environ["PAGES_SOURCE"] = "error"
        st = run("--out", os.path.join(TMP, "oh"), "--results-file", k25_30, "--as", "K25", "--inputs", inputs, now=NIGHT)
        check(st.get("pages_source") == "error", "a failed Pages-source check is reported")
        os.environ.pop("PUBLISH_MODE")
        os.environ.pop("PAGES_SOURCE")
        st = run("--out", os.path.join(TMP, "oh"), "--results-file", k25_30, "--as", "K25", "--inputs", inputs, now=NIGHT)
        check(st.get("heartbeat_s") == LF.HEARTBEAT and "publish_mode" not in st, "without a publisher: heartbeat_s is the re-stamp interval")
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        api_srv.shutdown()

    print("9. the register size in pipeline/live_config.json (LM-B)")
    cfg = json.load(open(os.path.join(ROOT, "pipeline", "live_config.json"), encoding="utf-8"))
    late = dt.date.today() >= dt.date(2026, 10, 25)
    check(not (late and cfg.get("eligible") == LF.PLACEHOLDER_ELIGIBLE),
          "eligible is still the 7,340,000 placeholder: set the CEC's official register size (docs/ELECTION_DAY.md, הכנות 2)")
    check(cfg.get("ignore_columns") == [] and cfg.get("column_aliases") == {}, "ignore_columns / column_aliases present and empty")

    print("10. the Arab-society section in turnout.json (during voting hours)")
    seen = []

    def fake_section(rows, base, national_turnout=None, released=None):   # a stand-in with the contract's shape
        rows = list(rows)
        seen.append({"rows": rows, "base": base, "national": national_turnout, "released": released})
        ar = [r for r in rows if r["code"] in ARAB_CODES and r["voters"]]
        v, e = sum(r["voters"] for r in ar), sum(r["elig"] or 0 for r in ar)
        t = round(v / e, 4) if e else None
        grp = {"voters": v, "elig": e, "turnout": t, "pace": 0.5, "localities": 2}
        return {"released": released, "localities": [{"key": "1", "voters": v, "elig": e, "turnout": t, "pace": 0.5, "stations": 3, "coverage": 1.0},
                                                     {"key": "2", "voters": 9, "elig": 30, "turnout": 0.3, "pace": 0.61234, "stations": 1, "coverage": 1.0}],
                "groups": {"raam": grp, "joint": grp, "other": grp}, "regions": {"negev": grp, "triangle": grp},
                "kinds": {"arab": grp, "druze": {**grp, "turnout": 0.31234}},
                "total": {**grp, "ratio_to_national": 0.8, "projected_final": {"lo": 0.4, "mid": 0.5, "hi": 0.6}}}
    real_at, real_err, real_base = LF.AT, LF.AT_ERR, LF.ARAB_BASE
    core = json.load(open(os.path.join(ROOT, "site", "data", "core.json"), encoding="utf-8"))
    ARAB_CODES = {loc["code"] for loc in core["localities"] if loc.get("sector") == "arab"}
    LF.AT, LF.AT_ERR = types.SimpleNamespace(arab_section=fake_section), ""
    LF.ARAB_BASE = write(os.path.join(TMP, "arab_base.json"), {"localities": [], "note": "stand-in"})
    LF._arab_base.clear()
    Server.bodies.update({f"/st{i}.csv": open(station_release(k25_30, 0.2 + 0.05 * i, f"st{i}.csv", seed=i), "rb").read()
                                           for i in range(10)})
    o10 = os.path.join(TMP, "o10")
    write(os.path.join(inputs, "turnout.json"), {"national": {"10:00": 15.2}})

    def day_pass(path, minutes):
        """One pass; no sectors_time here, so a new release is held (R1) and goes out at the pass after the hold."""
        when = dt.datetime(2026, 10, 27, 10, 0, tzinfo=IL) + dt.timedelta(minutes=minutes)
        args = ("--out", o10, "--config", cfg_file("c10.json", results_url=base + "/nothing", station_turnout_url=base + path),
                "--as", "K25", "--inputs", inputs)
        st = run(*args, now=when)
        if any("held for sectors_time" in e for e in st["errors"]):
            st = run(*args, now=when + dt.timedelta(minutes=LF.HOLD_FOR_TIME))
        return st
    try:
        st = day_pass("/st0.csv", 0)
        T = load(o10, "turnout.json")
        ok_rows = seen and seen[-1]["rows"] and set(seen[-1]["rows"][0]) == {"code", "kalpi", "elig", "voters"}
        check(st["phase"] == "day" and T.get("arab") and T["arab"]["total"]["ratio_to_national"] == 0.8 and ok_rows,
              f"10:00, polls open: turnout.json has the section; rows reach arab_section as code/kalpi/elig/voters; errors={st['errors']}")
        check(seen[-1]["national"] == T.get("stations_national") and seen[-1]["released"] == T.get("sectors_time") == "10:00"
              and seen[-1]["base"] == {"localities": [], "note": "stand-in"}, "national turnout of the same release, its time and the 2022 base passed in")
        h = T.get("arab_history") or []
        check(len(h) == 1 and set(h[0]) == {"released", "total", "groups", "regions", "kinds", "localities"}
              and set(h[0]["total"]) == {"turnout", "pace"} and set(h[0]["groups"]) == {"raam", "joint", "other"},
              f"arab_history: one compact entry: {str(h[:1])[:300]}")
        check(h and h[0]["localities"] == {"1": [T["arab"]["localities"][0]["turnout"], 0.5], "2": [0.3, 0.612]}
              and h[0]["kinds"]["druze"] == {"turnout": 0.3123, "pace": 0.5},
              f"the entry carries every locality as [turnout, pace] and the kinds, rounded (change column, Druze panel): "
              f"{h and h[0]['localities']}, {h and h[0]['kinds'].get('druze')}")
        check("lean" not in T, "the bloc lean stays withheld during voting")
        st = day_pass("/st0.csv", 15)
        check("turnout.json" not in st["changed"] and len(load(o10, "turnout.json")["arab_history"]) == 1,
              f"the same release 15 minutes later: nothing rewritten (its time stays 10:00): {st['changed']}")
        st = day_pass("/st1.csv", 240)
        T = load(o10, "turnout.json")
        check([x["released"] for x in T["arab_history"]] == ["10:00", "14:00"] and T["sectors_time"] == "14:00",
              f"a new release at 14:00: a second entry: {[x['released'] for x in T['arab_history']]}")
        for i in range(2, 10):
            day_pass(f"/st{i}.csv", 240 + 10 * i)
        T = load(o10, "turnout.json")
        check(len(T["arab_history"]) == LF.ARAB_HISTORY and T["arab_history"][0]["released"] == "14:20" and T["arab_history"][-1]["released"] == "15:30",
              f"ten releases: the last {LF.ARAB_HISTORY} kept: {[x['released'] for x in T['arab_history']]}")
        day_pass("/nothing", 400)
        T2 = load(o10, "turnout.json")
        check(T2.get("station_error") and T2.get("arab") == T["arab"] and T2.get("sectors") == T["sectors"],
              f"a failed station fetch keeps the last release on the page: {T2.get('station_error')}")
        LF.AT = types.SimpleNamespace(arab_section=lambda *a, **k: 1 / 0)
        st = day_pass("/st0.csv", 420)
        T2 = load(o10, "turnout.json")
        check(any(e.startswith("arab: ZeroDivisionError") for e in st["errors"]) and T2.get("arab") == T["arab"] and T2.get("sectors"),
              f"a failing section is reported and the last one kept; sectors unaffected: {st['errors']}")

        # the release time: sectors_time names only the release it was set for
        LF.AT = types.SimpleNamespace(arab_section=fake_section)
        o10s = os.path.join(TMP, "o10s")

        def rel_pass(out, path, when, sectors_time=None):
            write(os.path.join(inputs, "turnout.json"), {"national": {"10:00": 15.2}, **({"sectors_time": sectors_time} if sectors_time else {})})
            st = run("--out", out, "--config", cfg_file("c10s.json", results_url=base + "/nothing", station_turnout_url=base + path),
                     "--as", "K25", "--inputs", inputs, now=when)
            T = load(out, "turnout.json")
            errs = [e for e in st["errors"] if "sectors_time" in e]
            return T, [x["released"] for x in T.get("arab_history") or []], errs

        def at(d, hh, mm):
            return dt.datetime(2026, 10, d, hh, mm, tzinfo=IL)
        def held(errs):
            return any("held for sectors_time" in e for e in errs)
        T, rels, errs = rel_pass(o10s, "/st0.csv", at(27, 10, 40))
        check("sectors" not in T and "arab" not in T and rels == [] and held(errs),
              f"a new release without sectors_time while the polls are open: held, not published under 10:40 (R1): {errs}")
        T, rels, errs = rel_pass(o10s, "/st0.csv", at(27, 10, 45), "10:00")
        check(T["sectors_time"] == T["arab"]["released"] == "10:00" and rels == ["10:00"] and not errs and T["arab"].get("seen_he") == "10:40",
              f"sectors_time 10:00 pushed during the hold: published with it, first seen 10:40 kept as seen_he: {rels} {errs}")
        T, rels, errs = rel_pass(o10s, "/st1.csv", at(27, 14, 45), "10:00")
        check(T["sectors_time"] == "10:00" and rels == ["10:00"] and any("earlier" in e for e in errs) and held(errs),
              f"the next release with sectors_time unchanged: held, the page keeps the 10:00 release, both reported: {rels} {errs}")
        T, rels, errs = rel_pass(o10s, "/st1.csv", at(27, 14, 55), "14:00")
        check(T["sectors_time"] == T["arab"]["released"] == "14:00" and rels == ["10:00", "14:00"] and not errs,
              f"sectors_time 14:00 for it: relabelled in place: {rels} {errs}")
        T, rels, errs = rel_pass(o10s, "/st1.csv", at(27, 15, 0), "18:00")
        check(T["sectors_time"] == "14:00" and rels == ["10:00", "14:00"] and errs and "waits" in errs[0],
              f"sectors_time 18:00 typed ahead of its file: the 14:00 release keeps its time, reported: {rels} {errs}")
        T, rels, errs = rel_pass(o10s, "/st2.csv", at(27, 18, 40), "18:00")
        check(T["sectors_time"] == "18:00" and rels == ["10:00", "14:00", "18:00"] and not errs,
              f"its file arrives at 18:40: labelled 18:00: {rels} {errs}")
        T, rels, errs = rel_pass(o10s, "/st3.csv", at(27, 22, 40))
        check(T["sectors_time"] == T["arab"]["released"] == "22:00" and T["arab"].get("seen_he") == "22:40" and rels[-1] == "22:00",
              f"sectors_time removed, a release first seen at 22:40: labelled 22:00, seen_he 22:40: {rels}")
        T, rels, errs = rel_pass(o10s, "/st4.csv", at(27, 23, 10))
        check(rels == ["10:00", "14:00", "18:00", "22:00"] and T["sectors_sha256"] == LF.hashlib.sha256(Server.bodies["/st4.csv"]).hexdigest(),
              f"a corrected file after 22:00 replaces the 22:00 entry: {rels}")
        check(all("sha" not in x for x in T["arab_history"]), "the history's file keys stay in state.json, not in turnout.json")
        st = run("--out", o10s, "--config", cfg_file("c10s.json", results_url=base + "/nothing", station_turnout_url=base + "/st4.csv"),
                 "--as", "K25", "--inputs", inputs, now=at(28, 0, 10))
        check("turnout.json" not in st["changed"], f"midnight: the same release, turnout.json not rewritten (R5): {st['changed']}")
        T, rels, errs = rel_pass(o10s, "/st5.csv", at(28, 0, 30))
        check(T["arab"].get("seen_he") == "00:30 (28.10)" and rels[-1] == "22:00",
              f"a release first seen 28.10 00:30: labelled 22:00, seen_he with its date: {T['arab'].get('seen_he')}")
        o10h = os.path.join(TMP, "o10h")
        T, rels, errs = rel_pass(o10h, "/st6.csv", at(27, 11, 0))
        T, rels, errs = rel_pass(o10h, "/st6.csv", at(27, 11, 9))
        check(rels == [] and held(errs), f"no sectors_time yet 9 minutes after the release was first seen: still held: {errs}")
        T, rels, errs = rel_pass(o10h, "/st6.csv", at(27, 11, LF.HOLD_FOR_TIME))
        check(rels == ["11:00"] and T["sectors_time"] == "11:00" and not errs,
              f"after {LF.HOLD_FOR_TIME} minutes without one: published, labelled with the time first seen: {rels} {errs}")
        o10d = os.path.join(TMP, "o10d")
        rel_pass(o10d, "/st5.csv", at(26, 15, 0))
        T, rels, errs = rel_pass(o10d, "/st5.csv", at(26, 15, 10))
        rel_pass(o10d, "/st6.csv", at(27, 10, 30))
        T, rels, errs = rel_pass(o10d, "/st6.csv", at(27, 10, 40))
        check(rels == ["10:30"], f"a test release on 26.10 does not stay in the 27.10 history: {rels}")
        rel_pass(o10d, "/st6.csv", at(27, 10, 45), "10:00")
        T, rels, errs = rel_pass(o10d, "/st7.csv", at(27, 10, 50), "10:00")       # a corrected 10:00 file
        rel_pass(o10d, "/st7.csv", at(27, 10, 55))                                 # sectors_time removed ...
        T, rels, errs = rel_pass(o10d, "/st7.csv", at(27, 11, 0), "10:00")       # ... and set again
        check(rels == ["10:00"] and T["sectors_time"] == "10:00" and not errs
              and T["sectors_sha256"] == LF.hashlib.sha256(Server.bodies["/st7.csv"]).hexdigest(),
              f"a corrected file relabelled with the earlier file's time replaces it, the time appears once: {rels} {errs}")
        LF.AT = None
        o10b = os.path.join(TMP, "o10b")
        for when in (EVENING, EVENING + dt.timedelta(minutes=LF.HOLD_FOR_TIME)):       # held first: no sectors_time for it
            run("--out", o10b, "--config", cfg_file("c10b.json", results_url=base + "/nothing", station_turnout_url=base + "/st0.csv"),
                "--as", "K25", "--inputs", inputs, now=when)
        T = load(o10b, "turnout.json")
        check(T.get("sectors") and "arab" not in T, "without pipeline/arab_turnout.py: no section, the rest as before")
    finally:
        LF.AT, LF.AT_ERR, LF.ARAB_BASE = real_at, real_err, real_base
        LF._arab_base.clear()
    real_mod = os.path.join(ROOT, "pipeline", "arab_turnout.py")
    if LF.AT is None or not os.path.exists(LF.ARAB_BASE):
        print(f"  skip the real section: {'pipeline/arab_turnout.py' if LF.AT is None else 'site/data/arab_day_2022.json'} not here"
              + (f" ({LF.AT_ERR})" if LF.AT_ERR else ""))
        check(not (os.path.exists(real_mod) and LF.AT is None), f"pipeline/arab_turnout.py, when present, imports: {LF.AT_ERR or 'not present'}")
    else:
        csv_path, how = os.path.join(TMP, "demo_release.csv"), "synthetic (2022 voters x 0.45)"
        demo = os.path.join(ROOT, "pipeline", "make_demo_turnout.py")
        demo_json = os.path.join(ROOT, "site", "data", "arab_day_demo.json")
        before = open(demo_json, "rb").read() if os.path.exists(demo_json) else None
        if os.path.exists(demo):
            r = subprocess.run([sys.executable, demo, "--check"], capture_output=True, text=True, cwd=ROOT)
            last = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1]
            check(r.returncode == 0, f"pipeline/make_demo_turnout.py --check (the arab_turnout unit checks): {last}")
            # its CLI: --csv is a folder of turnout_HHMM.csv files; --out keeps site/data/arab_day_demo.json untouched
            cdir = os.path.join(TMP, "demo_csv")
            r = subprocess.run([sys.executable, demo, "--out", os.path.join(TMP, "demo.json"), "--csv", cdir],
                               capture_output=True, text=True, cwd=ROOT)
            got = sorted(glob.glob(os.path.join(cdir, "*.csv"))) if os.path.isdir(cdir) else [cdir] if os.path.isfile(cdir) else []
            pick = next((p for p in got if os.path.basename(p) == "turnout_1400.csv"), got[-1] if got else None)
            if r.returncode == 0 and pick:
                shutil.copy(pick, csv_path)
                how = f"pipeline/make_demo_turnout.py --csv ({os.path.basename(pick)})"
            check(r.returncode == 0 and pick, f"make_demo_turnout.py --out <tmp> --csv <folder> wrote {[os.path.basename(p) for p in got]}: "
                                              f"{(r.stderr or '').strip()[-200:]}")
            check(before is None or open(demo_json, "rb").read() == before, "site/data/arab_day_demo.json left alone by the test")
        if not os.path.exists(csv_path):
            shutil.copy(station_release(k25_30, 0.45, "demo45.csv"), csv_path)
        Server.bodies["/demo.csv"] = open(csv_path, "rb").read()
        o10c = os.path.join(TMP, "o10c")
        write(os.path.join(inputs, "turnout.json"), {"national": {"10:00": 15.2, "12:00": 27.9, "14:00": 38.4}, "sectors_time": "14:00"})
        st = run("--out", o10c, "--config", cfg_file("c10c.json", results_url=base + "/nothing", station_turnout_url=base + "/demo.csv"),
                 "--as", "K25", "--inputs", inputs, now=dt.datetime(2026, 10, 27, 14, 40, tzinfo=IL))
        T = load(o10c, "turnout.json") or {}
        A = T.get("arab") or {}
        tot = A.get("total") or {}
        check(set(A) >= {"released", "localities", "groups", "regions", "kinds", "total"} and tot.get("turnout") is not None
              and A.get("released") == "14:00" and set((tot.get("projected_final") or {})) >= {"lo", "mid", "hi"}
              and set(A["groups"]) <= {"raam", "joint", "other"},
              f"the real section on a {how} release, labelled 14:00 by sectors_time: total turnout {tot.get('turnout')}, "
              f"pace {tot.get('pace')}; errors={st['errors']}")
        h = (T.get("arab_history") or [{}])[-1]
        locs = {x["key"]: [x["turnout"], x["pace"]] for x in A.get("localities") or []}
        check(set(h) >= {"released", "as_of", "national", "total", "groups", "regions", "kinds", "localities"}
              and "projected_final" in h.get("total", {}) and h.get("localities") == locs and len(locs) > 100
              and h["kinds"] == {k: {"turnout": v["turnout"], "pace": v["pace"]} for k, v in A["kinds"].items()}
              and len(json.dumps(h, ensure_ascii=False, separators=(",", ":"))) < 8000,
              f"the history entry: arab_turnout.history_entry plus {len(h.get('localities') or {})} localities and the kinds, "
              f"{len(json.dumps(h, separators=(',', ':')))} bytes")
        # blank figures: the national turnout handed to the section is the one it computes itself from the same rows
        blank = rework_release(csv_path, "demo_blank.csv", cells=blank_some)
        Server.bodies["/demo_blank.csv"] = open(blank, "rb").read()
        for when in (dt.datetime(2026, 10, 27, 14, 50, tzinfo=IL), dt.datetime(2026, 10, 27, 15, 0, tzinfo=IL)):   # held, then out
            st = run("--out", o10c, "--config", cfg_file("c10c2.json", results_url=base + "/nothing", station_turnout_url=base + "/demo_blank.csv"),
                     "--as", "K25", "--inputs", inputs, now=when)
        T = load(o10c, "turnout.json") or {}
        B = T.get("arab") or {}
        own = real_at.arab_section(real_at.read_station_csv(open(blank, "rb").read()), real_at.load_base(), released="14:00")
        check(B.get("national") is not None and B.get("national") == T.get("stations_national") == own["national"]
              and abs((B.get("total") or {}).get("ratio_to_national", 9) - own["total"]["ratio_to_national"]) <= 0.002,
              f"blank / '-' / 0 figures: the feed's national {T.get('stations_national')} = the section's {B.get('national')} = "
              f"arab_turnout's own {own['national']}")
        check(B.get("released") == "14:50" and any("earlier" in e for e in st["errors"]),
              f"a new file with sectors_time 14:00 still in place is not labelled 14:00 again: {B.get('released')}")

        def keys(o):
            return set(o) | set().union(*(keys(v) for v in o.values())) if isinstance(o, dict) else \
                set().union(*(keys(v) for v in o)) if isinstance(o, list) else set()
        bad = {k for k in keys(A) if any(w in k for w in ("seat", "threshold", "vote_share", "raam22", "joint22"))}
        check(not bad, f"no party votes, seats or threshold figures in the section: {sorted(bad)}")

    print("11. the workflows: bash -n, the daily poll-ban guard and job split, the live reset, the push filters")
    wf_dir = os.path.join(ROOT, ".github", "workflows")
    docs = {os.path.basename(p): load_yaml(p) for p in sorted(glob.glob(os.path.join(wf_dir, "*.yml")))}
    if any(d is None for d in docs.values()):
        print("  skip: no YAML reader here (PyYAML or ruby)")
    else:
        wtmp = os.path.join(TMP, "wf")
        os.makedirs(wtmp)
        n = 0
        for name, doc in docs.items():
            for job, stp in workflow_steps(doc):
                if "run" not in stp:
                    continue
                script = re.sub(r"\$\{\{[^}]*\}\}", "X", stp["run"])
                r = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
                n += 1
                check(r.returncode == 0, f"bash -n {name} / {job} / {stp.get('name') or stp['run'][:30]!r}: {r.stderr.strip()[:200]}")
        print(f"  ({n} run blocks parsed)")
        daily = docs.get("daily.yml") or {}
        guard = next((s["run"] for _, s in workflow_steps(daily) if s.get("id") == "guard"), "")
        push = next((s["run"] for _, s in workflow_steps(daily) if s.get("id") == "push"), "")
        push_guard = push.split("# (end of the ban guard)")[0] if "# (end of the ban guard)" in push else ""
        check(guard and push_guard, "daily.yml has the guard step and the push-time guard")
        cases = [  # (Israel time, event, exit code, go)
            ("202610101200", "schedule", 0, "true"), ("202610231941", "schedule", 0, "true"),
            ("202610232329", "workflow_dispatch", 0, "true"), ("202610232330", "workflow_dispatch", 1, "false"),
            ("202610232359", "schedule", 0, "false"), ("202610240000", "schedule", 0, "false"),
            ("202610240000", "workflow_dispatch", 1, "false"), ("202610261200", "workflow_dispatch", 1, "false"),
            ("202610272159", "workflow_dispatch", 1, "false"), ("202610272200", "workflow_dispatch", 0, "true"),
            ("202610272200", "schedule", 0, "false"), ("202610091200", "schedule", 0, "false"),
            ("202710150723", "schedule", 0, "false"),
            # a request on ops-control (event push) is refused like a manual run
            ("202610151200", "push", 0, "true"), ("202610232330", "push", 1, "false"), ("202610261200", "push", 1, "false"),
            ("202610272200", "push", 0, "true"),
        ]
        for now_il, event, code, go in cases:
            rc, outs, log = run_block(guard, {"NOW_IL": now_il, "EVENT": event}, wtmp)
            check(rc == code and outs.get("go") == go, f"daily guard {now_il[6:8]}.{now_il[4:6]}.{now_il[:4]} {now_il[8:10]}:{now_il[10:]} "
                                                        f"{event}: exit {rc}, go={outs.get('go')} (want {code}, {go})")
        for now_il, code in (("202610231200", 0), ("202610232329", 0), ("202610232331", 1), ("202610240001", 1),
                             ("202610272159", 1), ("202610280900", 0)):
            rc, _, _ = run_block(push_guard, {"NOW_IL": now_il}, wtmp)
            check(rc == code, f"push-time guard at {now_il}: exit {rc} (want {code})")
        on_daily = daily.get("on", daily.get(True)) or {}
        check(set(on_daily) == {"schedule", "workflow_dispatch", "push"}
              and on_daily.get("push") == {"branches": ["ops-control"], "paths": ["ops/request.json"]},
              f"daily.yml: schedule, dispatch, and pushes of ops/request.json to ops-control only: {on_daily.get('push')}")
        crons = [c["cron"] for c in on_daily.get("schedule", [])]
        check(crons and all(c.split()[0] not in ("0", "30") and c.split()[3] == "10" for c in crons), f"daily crons off the hour, in October: {crons}")
        for wf in ("pages.yml", "official-data.yml", "daily.yml", "net-check.yml", "live.yml"):
            pats = push_paths(docs[wf])
            fires = pats is not None and path_filter(pats, "site/live/status.json")
            check(not fires, f"{wf}: a commit to site/live/ starts no run")
        check(path_filter(push_paths(docs["pages.yml"]), "site/src/js/live.js"), "pages.yml still runs for site/src changes")
        live_perm = docs["live.yml"].get("permissions") or {}
        check(live_perm.get("pages") == "write" and live_perm.get("contents") == "write", f"live.yml permissions: {live_perm}")
        feed_env = ((docs["live.yml"].get("jobs") or {}).get("feed") or {}).get("env") or {}
        check("vars.LIVE_BUILD_WAIT" in str(feed_env.get("LIVE_BUILD_WAIT")), f"live.yml: LIVE_BUILD_WAIT from a repository variable: {feed_env.get('LIVE_BUILD_WAIT')}")

        # daily.yml: the third-party polls-data.js is read in a job with nothing to steal; the job that writes never reads it
        jobs = daily.get("jobs") or {}

        def has_token(job):
            text = json.dumps(job)
            return any(w in text for w in ("github.token", "secrets.", "GH_TOKEN", "GITHUB_TOKEN"))

        def checkout(job):
            return next((s for s in job.get("steps") or [] if str(s.get("uses", "")).startswith("actions/checkout")), {})
        runs_js = re.compile(r"pipeline/build_polls\.py\s+--src|polls-data\.js|\bnode\b")   # running it, not naming the module
        js_jobs = [j for j, d in jobs.items() if any(re.search(r"pipeline/build_polls\.py\s+--src", s.get("run") or "")
                                                     for s in d.get("steps") or [])]
        bj = jobs[js_jobs[0]] if len(js_jobs) == 1 else {}
        check(len(js_jobs) == 1 and bj.get("permissions") == {"contents": "read"} and not has_token(bj)
              and (checkout(bj).get("with") or {}).get("persist-credentials") is False
              and any(str(s.get("uses", "")).startswith("actions/upload-artifact") for s in bj.get("steps") or []),
              f"daily.yml: polls-data.js is read in one job ({js_jobs}) with contents: read, no token, no stored git credentials, "
              "and leaves it as an artifact")
        writers = [j for j, d in jobs.items() if any(v == "write" for v in (d.get("permissions") or {}).values())]
        cj = jobs[writers[0]] if len(writers) == 1 else {}
        steps = cj.get("steps") or []
        ids = [s.get("id") for s in steps]
        runs = " ".join(s.get("run") or "" for s in cj.get("steps") or [])
        check(len(writers) == 1 and writers != js_jobs and not runs_js.search(runs)
              and all(v != "write" for v in (daily.get("permissions") or {}).values()),
              f"daily.yml: one job writes ({writers}), and it never reads polls-data.js; the workflow default is read-only")
        check([s.get("id") for s in steps if "GH_TOKEN" in (s.get("env") or {})] == ["push", "pages"] and "GH_TOKEN" not in (cj.get("env") or {})
              and (checkout(cj).get("with") or {}).get("persist-credentials") is False
              and all(k in ids for k in ("validate", "build", "health", "push"))
              and ids.index("validate") < ids.index("build") < ids.index("health") < ids.index("push"),
              f"daily.yml: the token only in the push and build-request steps; validate, build, health check, push in that order: {ids}")
        val = next((s["run"] for s in steps if s.get("id") == "validate"), "")
        good = json.load(open(os.path.join(ROOT, "site", "data", "polls_2026.json"), encoding="utf-8"))

        def broken(fn):
            d = json.loads(json.dumps(good))
            fn(d)
            return d
        tables = {
            "the committed polls_2026.json": (good, 0),
            "seats adding up to 121": (broken(lambda d: d["polls"][0]["seats"].update(Likud=d["polls"][0]["seats"]["Likud"] + 1)), 1),
            "markup in a pollster name": (broken(lambda d: d["polls"][1].update(pollster="x</script><script>alert(1)</script>")), 1),
            "an extra field": (broken(lambda d: d["polls"][2].update(evil=1)), 1),
            "a changed party": (broken(lambda d: d["parties"][0].update(color="red")), 1),
            "a javascript: filing link": (broken(lambda d: d["polls"][3].update(filing="javascript:alert(1)")), 1),
            "n as text": (broken(lambda d: d["polls"][4].update(n="500")), 1),
            "no polls": (broken(lambda d: d.update(polls=[])), 1),
            "NaN": ('{"parties": NaN, "polls": [], "dropped": [], "source": ""}', 1),
        }
        for what, (table, code) in tables.items():
            p = write(os.path.join(TMP, "wf", "polls_check.json"), table if isinstance(table, str) else json.dumps(table, ensure_ascii=False))
            rc, _, log = run_block(val, {"POLLS": p}, ROOT)
            check(rc == code, f"daily poll-table check, {what}: exit {rc} (want {code}) {log.strip().splitlines()[-1][:120] if log.strip() else ''}")

        # live.yml: a reset that was not published, or whose rebuild request failed, makes the run red
        live_run = next((s["run"] for _, s in workflow_steps(docs["live.yml"]) if "--reset-live" in (s.get("run") or "")), "")
        stub = os.path.join(TMP, "stub")
        os.makedirs(stub, exist_ok=True)
        write(os.path.join(stub, "python3"), '#!/bin/sh\nif [ "$1" = pipeline/live_fetch.py ]; then printf "%s\\n" "$FAKE_LINE"; exit 0; fi\n'
                                             f'exec "{sys.executable}" "$@"\n')
        os.chmod(os.path.join(stub, "python3"), 0o755)
        for line, code in ((json.dumps({"published": "pushed", "build": "Pages build requested (queued)"}), 0),
                           (json.dumps({"build": None}), 0),
                           (json.dumps({"published": "push failed"}), 1),
                           (json.dumps({"published": "pushed", "build": "Pages build request failed (500)"}), 1),
                           ("Traceback (most recent call last):", 1)):
            rc, _, log = run_block(live_run, {"RESET": "true", "PUB_ARGS": "", "FAKE_LINE": line,
                                              "PATH": stub + os.pathsep + os.environ.get("PATH", "")}, wtmp)
            check(rc == code, f"live.yml reset, {line[:60]}: exit {rc} (want {code})")

        # daily.yml: the rebuild request is retried, and the run goes red when all three fail (WF-7)
        pages_run = next((s_["run"] for _, s_ in workflow_steps(daily) if s_.get("id") == "pages"), "")
        for line, code in ((json.dumps({"ok": True, "build": "Pages build requested (queued)"}), 0),
                           (json.dumps({"ok": False, "build": "Pages build request failed (500)"}), 1), ("boom", 1)):
            rc, outs, log = run_block(pages_run, {"SHA": "0" * 40, "FAKE_LINE": line, "RETRY_WAIT": "0",
                                                  "PATH": stub + os.pathsep + os.environ.get("PATH", "")}, wtmp)
            tries = sum(1 for ln in log.splitlines() if ln.strip() == line)
            check(rc == code and (code == 0 or tries == 3), f"daily.yml rebuild request, {line[:50]}: exit {rc} (want {code}), {tries} tries")

        # live.yml: the year, the minutes and the drill guard (WF-2, WF-8)
        live_guard = next((s_["run"] for _, s_ in workflow_steps(docs["live.yml"]) if s_.get("id") == "guard"), "")
        feed_steps = (docs["live.yml"].get("jobs") or {}).get("feed", {}).get("steps") or []
        check(live_guard and feed_steps and feed_steps[0].get("id") == "guard"
              and all("steps.guard.outputs.off != 'true'" in str(s_.get("if", "")) for s_ in feed_steps[1:]),
              "live.yml: the guard step comes first and every later step is skipped outside 2026")

        def epoch(y, mo, d, hh, mm):
            return str(int(dt.datetime(y, mo, d, hh, mm, tzinfo=IL).timestamp()))
        for when, event, drill, minutes, reset, code, want in (
                (epoch(2026, 10, 23, 22, 0), "workflow_dispatch", "true", "40", "false", 0, {"MINUTES": "40"}),
                (epoch(2026, 10, 23, 23, 10), "workflow_dispatch", "true", "40", "false", 1, {}),
                (epoch(2026, 10, 23, 23, 30), "workflow_dispatch", "true", "", "false", 1, {}),
                (epoch(2026, 10, 25, 12, 0), "workflow_dispatch", "true", "40", "false", 1, {}),
                (epoch(2026, 10, 27, 23, 0), "workflow_dispatch", "true", "40", "false", 1, {}),
                (epoch(2026, 11, 5, 23, 0), "workflow_dispatch", "true", "40", "false", 1, {}),
                (epoch(2026, 11, 6, 0, 0), "workflow_dispatch", "true", "40", "false", 0, {}),
                (epoch(2026, 10, 27, 23, 0), "workflow_dispatch", "true", "", "true", 0, {}),
                (epoch(2026, 10, 27, 8, 7), "schedule", "false", "", "false", 0, {"MINUTES": "345"}),
                (epoch(2026, 10, 30, 8, 7), "schedule", "false", "", "false", 0, {"MINUTES": "20"}),
                (epoch(2027, 10, 27, 8, 7), "schedule", "false", "", "false", 0, {"off": "true"}),
                (epoch(2026, 10, 15, 12, 0), "workflow_dispatch", "false", "4o", "false", 1, {}),
                (epoch(2026, 10, 15, 12, 0), "workflow_dispatch", "true", "040", "false", 0, {"MINUTES": "40"})):
            rc, outs, log = run_block(live_guard, {"NOW_S": when, "GITHUB_EVENT_NAME": event, "DRILL": drill, "MINUTES": minutes,
                                                   "RESET": reset}, wtmp)
            t = dt.datetime.fromtimestamp(int(when), IL)
            check(rc == code and all(outs.get(k) == v for k, v in want.items()),
                  f"live.yml guard {t:%d.%m.%Y %H:%M} {event} drill={drill} reset={reset} minutes={minutes!r}: exit {rc} (want {code}), "
                  f"{ {k: outs.get(k) for k in want} }")

        # WF-1: polls-data.js is a third party's file: build_polls.py reads it as data, and no job that can write runs it
        import build_polls as BP
        check(not hasattr(BP, "subprocess"), "build_polls.py runs nothing (no subprocess, no node)")
        js_ok = write(os.path.join(TMP, "wf", "polls_ok.js"), '/* x */\nwindow.BASE_POLLS_DATA = [{"date": "2026-10-01", "Likud": 30}];\n'
                                                            'window.GOVIL_TOPICAL_DATA = [];\n')
        check(BP.load_js(js_ok) == [{"date": "2026-10-01", "Likud": 30}], "load_js: the JSON array assigned to BASE_POLLS_DATA")
        for what, body in (("code", 'window.BASE_POLLS_DATA = (function(){ require("child_process").execSync("id"); return []; })();'),
                           ("a NaN", 'window.BASE_POLLS_DATA = [{"Likud": NaN}];'),
                           ("no assignment", 'var polls = [];'),
                           ("not records", 'window.BASE_POLLS_DATA = [1, 2];')):
            try:
                BP.load_js(write(os.path.join(TMP, "wf", "polls_bad.js"), body))
                check(False, f"load_js should refuse {what}")
            except ValueError as exc:
                check("BASE_POLLS_DATA" in str(exc), f"load_js refuses {what}: {str(exc)[-70:]}")
        od = docs["official-data.yml"]
        ojobs = od.get("jobs") or {}
        o_js = [j for j, d in ojobs.items() if any("build_polls.py" in (s_.get("run") or "") for s_ in d.get("steps") or [])]
        o_writers = [j for j, d in ojobs.items() if any(v == "write" for v in (d.get("permissions") or {}).values())]
        ob_ = ojobs[o_js[0]] if len(o_js) == 1 else {}
        check(len(o_js) == 1 and ob_.get("permissions") == {"contents": "read"} and not has_token(ob_)
              and (checkout(ob_).get("with") or {}).get("persist-credentials") is False
              and all(v != "write" for v in (od.get("permissions") or {}).values()),
              f"official-data.yml: polls-data.js is read in one job ({o_js}) with contents: read, no token, no stored git credentials")
        ow = ojobs[o_writers[0]] if len(o_writers) == 1 else {}
        check(len(o_writers) == 1 and o_writers != o_js and not runs_js.search(" ".join(s_.get("run") or "" for s_ in ow.get("steps") or []))
              and str(ow.get("if", "")).find("workflow_dispatch") >= 0
              and (checkout(ow).get("with") or {}).get("persist-credentials") is False,
              f"official-data.yml: the one job that writes ({o_writers}) runs on manual runs only and never reads polls-data.js")
        check(((od.get("defaults") or {}).get("run") or {}).get("shell") == "bash",
              "official-data.yml: run steps under bash -eo pipefail (a failed rebuild piped into tee fails, WF-10)")
        check(not any(re.search(r"\bnode\b", s_.get("run") or "") for wf in ("daily.yml", "official-data.yml")
                      for _, s_ in workflow_steps(docs[wf])), "no workflow runs node on polls-data.js")
        ops_control(docs, wtmp)
        # the drill's smoke test runs this file with HEALTH_GATE=1 in a checkout of ops-control, where
        # ops/request.json is the drill request itself: 11b passes there too (only the repository-state check, which
        # would catch it, is skipped)
        drill = '{"workflow": "live", "drill": true, "minutes": 40, "id": "20261020-120000"}'
        new, out, root = ops_control_in_request_checkout(docs, drill)
        check(not new and "skip the checkout's ops/request.json" in out and not ops_placeholder(root)[0],
              f"11b in a checkout of the request {drill} with HEALTH_GATE=1 (the drill's smoke test): {len(new)} failure(s) {new[:3]}")
    lists_2026()
    fetchers_budget()

    srv.shutdown()
    print(f"\n{len(failures)} failure(s) in {time.time() - t0:.0f} s; scratch in {TMP}")
    for f in failures:
        print("  FAIL", f)
    if not failures:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
