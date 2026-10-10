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
     Cancel run): the request step of live.yml, discover.yml, net-check.yml and daily.yml run on sample requests
     (each goes on only for its own, its fields checked as the dispatch inputs; a bad request is red), a drill
     request through live.yml's guard into the poll ban and a daily request through the ban guard, the groups and
     write targets (main, ops-reports; never the triggering branch), a run from ops-control taking live_input/
     from main, and the "restart" request that ends a running loop, only for a request the requested run will
     take (the same request check, then its guard's drill rule); the runbook's request command, also when the
     forced push is refused; and 11b again as the drill's smoke test runs it, in a checkout whose
     ops/request.json is the drill request.
The drill in live.yml and the daily poll update run this first, with HEALTH_GATE=1: then the checks of the
repository's own state (site/live/status.json and ops/request.json are main's placeholders) are skipped: a run that a
push to ops-control started has the request itself checked out. Runtime about four minutes."""
import contextlib
import datetime as dt
import glob
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


def load_yaml(path):
    """A workflow file as a dict: PyYAML when installed, else Ruby's YAML (on GitHub's runners), else None."""
    try:
        import yaml
        return yaml.safe_load(open(path, encoding="utf-8"))
    except ImportError:
        pass
    if shutil.which("ruby"):
        r = subprocess.run(["ruby", "-ryaml", "-rjson", "-e", "puts JSON.dump(YAML.load_file(ARGV[0]))", path],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout)
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
                "net-check.yml": ("net-check", ""), "daily.yml": ("daily", "")}
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


def ops_control(docs, wtmp):
    """11b. The operator's requests (docs/ELECTION_DAY.md, "בקשות דרך ops-control"): the session's token can push but
    not dispatch or cancel, so a push of ops/request.json to the ops-control branch stands in for Run workflow. Every
    one of the four workflows reads it in the same step and goes on only when the request names it, its fields
    checked as the dispatch inputs are (the step itself, run here on sample requests); the request's outputs reach
    live.yml's drill guard and daily.yml's poll-ban guard; the working jobs keep their concurrency groups, and a
    request for another workflow can never take a group's pending slot; everything is written to main or
    ops-reports, never to the triggering branch; a run that ops-control started reads live_input/ and
    live_config.json from main; and a later {"restart": true} request ends a running loop (the stand-in for Cancel)."""
    print("11b. ops-control: the request step in the four workflows, its guards, groups, write targets and restart")
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
    check(len({st.get("run") for st in steps.values()}) == 1
          and all(st.get("run", "").rstrip().endswith("\npython3 ops/check_request.py ops/request.json") for st in steps.values()),
          "the request step is the same block in the four workflows, and runs ops/check_request.py")
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
    for wf in ("live.yml", "daily.yml", "discover.yml"):
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

    # restart: a {"workflow": "live", "restart": true} pushed after the run began ends the loop; nothing else does
    m = re.search(r"^restart_requested\(\) \{\n.*?^\}\n", loop, re.S | re.M)
    check(m and loop.index("restart_requested()") < loop.index("while [") and re.search(r"if restart_requested; then\n.*?break", loop, re.S),
          "live.yml: the loop asks restart_requested at every pass and stops")
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
              f"restart check, {body or 'the request that started the run'} (seen: {seen}): restart={stop} (want {want}), seen {str(after)[:8]}")

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
              f"restart check, {last} at {now:%d.%m %H:%M} ({what}): restart={stop} (want {want}; the requested run's "
              f"request step and guard agree: {agrees}), seen {str(after)[:8]} {' | '.join(log.strip().splitlines())[-110:]}")
    stop, _, _ = restart(t_run, lost)
    check(not stop, "restart check where git cannot reach the remote: no restart")

    # the request command when the forced push is refused (a ruleset, or a token without the workflows permission for
    # main's workflow changes): it deletes ops-control and pushes it anew
    sh(["git", "config", "receive.denyNonFastForwards", "true"], origin)
    old = sh(["git", "rev-parse", "refs/heads/ops-control"], origin)
    new_tip = request('{"workflow": "net-check"}')
    remote = sh(["git", "rev-parse", "refs/heads/ops-control"], origin)
    sh(["git", "config", "--unset", "receive.denyNonFastForwards"], origin)
    check(remote == new_tip != old,
          f"the request command after a refused forced push: ops-control made anew at the request ({remote[:8]}, was {old[:8]})")


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

    srv.shutdown()
    print(f"\n{len(failures)} failure(s) in {time.time() - t0:.0f} s; scratch in {TMP}")
    for f in failures:
        print("  FAIL", f)
    if not failures:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
