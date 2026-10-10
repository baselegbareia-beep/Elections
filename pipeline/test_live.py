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
     envelopes_expected re-renders it without moving the data time (DOC-3);
  4. 2026 mode on a synthetic file with the 2026 ballot letters projects the 2026 lists;
     a counted register above the configured one is reported and shown as 99% (LM-B);
  5. before 22:00 on election day nothing is fetched (a probe only), after 22:00 it is;
     the switches act on the cached file while the CEC file is rejected (DOC-3);
  6. a broken live_input/turnout.json keeps the last good figures and reports the error (OPS-10);
     a typo in an hour or a figure is reported, not dropped silently (DOC-7);
     exit polls appear only after 22:00 and disappear when the input is removed (OPS-14);
     the 2022-vote-weighted lean is omitted during voting hours;
  7. a drill is marked, and a real run discards its files (OPS-3);
  8. the laptop publisher's reset cycle survives another writer on live-data (OPS-1), and the
     laptop takes live_input/ and live_config.json from origin/main every pass (DOC-2);
  9. pipeline/live_config.json still holds the 7,340,000 placeholder after 25.10 (LM-B).
The drill in live.yml runs this first. Runtime about one to two minutes."""
import contextlib
import datetime as dt
import glob
import http.server
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time

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
    Server.bodies["/k25_30.csv"] = good

    print("6. manual inputs: broken turnout.json, exit polls, lean during voting")
    o6 = os.path.join(TMP, "o6")
    write(os.path.join(inputs, "turnout.json"), {"national": {"10:00": 15.2, "12:00": 27.9, "19:00": 60.1}, "source": "הודעת הוועדה",
                                                 "claims": [{"time": "16:00", "source": "x", "text": "y"}]})
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
    os.remove(os.path.join(inputs, "exit_polls.json"))
    st = run("--out", o6, "--config", c6, "--as", "K25", "--inputs", inputs, now=NIGHT)
    check(st["exit_polls"] is False and load(o6, "exit_polls.json") is None and "exit_polls.json" in st["changed"], "input removed: published copy removed (OPS-14)")
    write(os.path.join(inputs, "turnout.json"), {"national": {}, "source": "", "claims": []})
    st = run("--out", o6, "--config", write(os.path.join(TMP, "broken.json"), "{ nope"), "--as", "K25", "--inputs", inputs, now=NIGHT)
    check(any(e.startswith("config:") for e in st["errors"]) and st["results_state"] in ("waiting", "ok"), f"broken config reported, pass completed: {st['errors']}")

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

    print("8. laptop publisher: reset cycle against a bare repository with a second writer")
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
    r1 = LF.publish(o1, wt=os.path.join(repo, ".live-data"), repo=repo)
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
    r2 = LF.publish(o1, wt=os.path.join(repo, ".live-data"), repo=repo)
    check(r2 == "pushed", f"publish after a foreign push: {r2}")
    sh(["git", "fetch", "-q", "origin", "live-data"], other)
    tip = json.loads(sh(["git", "show", "origin/live-data:live/status.json"], other))
    check(tip.get("writer") is None and tip.get("has_results") is True, "the laptop's files are on the tip, no rebase, no conflict")
    r3 = LF.publish(o1, wt=os.path.join(repo, ".live-data"), repo=repo)
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

    print("9. the register size in pipeline/live_config.json (LM-B)")
    cfg = json.load(open(os.path.join(ROOT, "pipeline", "live_config.json"), encoding="utf-8"))
    late = dt.date.today() >= dt.date(2026, 10, 25)
    check(not (late and cfg.get("eligible") == LF.PLACEHOLDER_ELIGIBLE),
          "eligible is still the 7,340,000 placeholder: set the CEC's official register size (docs/ELECTION_DAY.md, הכנות 3)")
    check(cfg.get("ignore_columns") == [] and cfg.get("column_aliases") == {}, "ignore_columns / column_aliases present and empty")

    srv.shutdown()
    print(f"\n{len(failures)} failure(s) in {time.time() - t0:.0f} s; scratch in {TMP}")
    for f in failures:
        print("  FAIL", f)
    if not failures:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
