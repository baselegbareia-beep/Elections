"""Election day & night fetcher: official CEC files -> live/*.json for the dashboard.

Runs on GitHub Actions (.github/workflows/live.yml, one pass per loop iteration) or on any laptop:

    python3 pipeline/live_fetch.py --out live --loop 60 --publish   # poll every 60 s and publish (laptop)
    python3 pipeline/live_fetch.py --out live --once                # one pass
    python3 pipeline/live_fetch.py --out /tmp/l --once --results-file data/official/k25_expb.csv --as K25
                                                                    # dry run on a past election
    python3 pipeline/live_fetch.py --out /tmp/d --once --drill --minutes 15
                                                                    # rehearsal: 2022 revealed over 15 minutes

Inputs
  * Results: the CEC ballot file (expb.csv) at the URL in pipeline/live_config.json. On election
    night it grows as polling stations are counted; double envelopes come last. Outside a drill
    or --results-file nothing is fetched or published before election day 22:00 Israel time;
    until then the URL is only probed (HTTP code in status.results_probe) every ~10 minutes.
  * Turnout during the day: the CEC national hourly figures and, if the CEC publishes them as
    announced (ruling of 16.8.2026), per-station turnout. National figures are typed into
    live_input/turnout.json (the CEC releases them as statements, not files) or scraped when a
    URL is configured.
  * Exit polls: live_input/exit_polls.json, published only after polls close (22:00).

Outputs (next to the page on GitHub Pages; the JSON contract is in the lead's ARCH_V2 notes)
  live/results.json   counted totals + projection frame (pipeline/live_model.make_frame);
                      updated_he is the time the CEC file last changed, not the time of the check
  live/turnout.json   national hourly series, sector turnout from per-station data
  live/exit_polls.json, live/status.json, live/history.json (projection over the night)
  live/state.json     persisted state keyed by source: last accepted sha256, stations, last valid
                      inputs and config, probe times. State from another source is ignored.

Every download is checked: an empty body, HTML or JSON instead of CSV (maintenance page, WAF,
rate limit) is rejected, a file without the expected columns or without a single counted station
is rejected, rows with more voters than eligible voters are dropped and counted, a file whose
station count shrank is rejected, an unchanged file (same SHA-256) is skipped, and the SHA-256 of
each accepted file is recorded. Each pass prints one JSON line (the status plus "changed": the
files written or removed), which the workflow uses to decide whether to commit.
"""
import argparse
import collections
import csv
import datetime as dt
import glob
import hashlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_model as LM  # noqa: E402
from build_data import load_election, read_expb  # noqa: E402

ROOT = LM.ROOT
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live"
try:
    from zoneinfo import ZoneInfo
    IL = ZoneInfo("Asia/Jerusalem")
except Exception:                                   # a runner without tz data: IST (UTC+2) from 25.10.2026
    IL = dt.timezone(dt.timedelta(hours=2))
AGREEMENTS_2026 = [("Likud", "Religious Zionism"), ("Yashar", "The Democrats"), ("Together", "Yisrael Beiteinu"),
                   ("Ra'am", "Joint List")]
STATE = "state.json"
DRILL_URL = "https://media25.bechirot.gov.il/files/expb.csv"
DEFAULT_CFG = {"election_day": "2026-10-27", "results_url": "https://media26.bechirot.gov.il/files/expb.csv"}
PROBE_EVERY = 600       # seconds between probes of the results URL before 22:00
HEARTBEAT = 300         # status.json is rewritten at least this often even when nothing changed
HOUR_RE = re.compile(r"^\d{2}:\d{2}$")


def now_il():
    return dt.datetime.now(dt.timezone.utc).astimezone(IL)


def he_time(t):
    return t.strftime("%H:%M") + (" (" + t.strftime("%d.%m") + ")" if t.date() != now_il().date() else "")


def closing(election_day):
    return dt.datetime.combine(election_day, dt.time(22, 0), IL)


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if "maintenance" in r.geturl():
            raise IOError(f"redirected to {r.geturl()}")
        data = r.read()
    head = data[:200].lstrip(b"\xef\xbb\xbf \t\r\n").lower()     # the 2022 file starts with a UTF-8 BOM
    if not head:
        raise IOError("empty body")
    if head[:1] in (b"<", b"{", b"["):
        raise IOError("got an HTML or JSON page instead of a data file")
    return data


def probe(url, timeout=20):
    """HTTP status of url without downloading it: HEAD, or a one-byte GET where HEAD is refused."""
    for method, headers in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
        req = urllib.request.Request(url, headers={"User-Agent": UA, **headers}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, ""
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in (403, 405):
                continue
            return exc.code, ""
        except Exception as exc:
            return 0, f"{exc.__class__.__name__}: {exc}"[:120]
    return 0, ""


DRILL = False
CHANGED = []            # files written or removed in this pass (the workflow commits only then)


def _strip(o):
    """The object without its timestamps, to tell a real change from a re-stamp."""
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if k not in ("updated_at", "updated_he", "checked_he")}
    if isinstance(o, list):
        return [_strip(x) for x in o]
    return o


def write_json(out, name, obj, heartbeat=None):
    """Write out/name unless it already holds the same content (timestamps aside). heartbeat:
    rewrite anyway when the stored updated_at is older than that many seconds, so a quiet feed
    still shows it is alive. Returns True when the file was written."""
    if DRILL and isinstance(obj, dict):
        obj = {**obj, "drill": True}
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, name)
    if os.path.exists(p):
        try:
            old = json.load(open(p, encoding="utf-8"))
            age = time.time() - os.path.getmtime(p)
            if heartbeat is not None and isinstance(old, dict) and old.get("updated_at"):
                age = (now_il() - dt.datetime.fromisoformat(old["updated_at"])).total_seconds()
            if _strip(old) == _strip(obj) and (heartbeat is None or age < heartbeat):
                return False
        except Exception:
            pass
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)
    CHANGED.append(name)
    return True


def remove_json(out, name):
    p = os.path.join(out, name)
    if os.path.exists(p):
        os.remove(p)
        CHANGED.append(name)
        return True
    return False


def read_json(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def read_input(inputs, name):
    """A manual input file, or None when it does not exist (a JSON error raises)."""
    p = os.path.join(inputs, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def discard_drill_output(out):
    """A real run never starts from a rehearsal's files (OPS-3)."""
    st = read_json(os.path.join(out, "status.json"), {})
    if not DRILL and isinstance(st, dict) and st.get("drill"):
        for p in glob.glob(os.path.join(out, "*.json")):
            remove_json(out, os.path.basename(p))
        return True
    return False


# ------------------------------------------------------------------ setup
class Election2026:
    """2026 lists, the 2022 baseline and the projector, built once."""

    def __init__(self, cfg, as_election=None):
        self.cfg = cfg
        core = json.load(open(os.path.join(ROOT, "site", "data", "core.json"), encoding="utf-8"))
        src = os.path.join(ROOT, "data", "raw", "mirror")
        self.dry = as_election            # replay a past election through the same code (testing)
        if self.dry:
            base_e = {"K25": "K24", "K24": "K23"}[self.dry]
            import registry as R
            el = next(e for e in core["elections"] if e["id"] == self.dry)
            fam = {p["id"]: p["family"] for p in el["parties"]}
            self.meta = {p: {"name": next(x["name"] for x in el["parties"] if x["id"] == p), "letters": p,
                             "color": R.FAMILIES[fam.get(p, "other")]["color"],
                             "dark": R.FAMILIES[fam.get(p, "other")]["dark"],
                             "bloc": "coal" if v[2] == "nb" else "arab" if v[2] == "arab" else "opp"}
                         for p, v in R.PARTIES[self.dry].items()}
            mapping = LM.BASE_MAP[self.dry]
            agreements = LM.AGREEMENTS[self.dry]
            prior = LM.final_poll_prior(self.dry)
        else:
            base_e = "K25"
            polls = json.load(open(os.path.join(ROOT, "site", "data", "polls_2026.json"), encoding="utf-8"))
            self.meta = {p["letters"]: {"name": p["name"], "letters": p["letters"], "color": p["color"],
                                        "dark": p["dark"], "bloc": p["bloc"], "id": p["id"]} for p in polls["parties"]}
            to_letter = {p["id"]: p["letters"] for p in polls["parties"]}
            mapping = {to_letter[k]: v for k, v in LM.BASE_MAP["K26"].items() if k in to_letter}
            agreements = [(to_letter[a], to_letter[b]) for a, b in AGREEMENTS_2026]
            prior = {to_letter[k]: v for k, v in poll_prior(polls).items()}
        (_, base_rows), self.base_source = load_election(src, base_e)
        self.B = LM.Baseline(base_e, base_rows, core)
        # the ballot file's eligible voters per station add up to the whole register (envelope voters
        # are registered at their home station), so register growth scales every locality
        base_elig = sum(L["elig"] for L in self.B.loc.values())
        if self.dry:
            (_, cur_rows), _ = load_election(src, self.dry)
            self.eligible = sum(r["elig"] for r in cur_rows if not r["env"] and r["code"] is not None)
        else:
            self.eligible = cfg.get("eligible") or round(base_elig * 1.081)
        self.g = self.eligible / base_elig
        self.lists = list(self.meta)
        camp = {j: m["bloc"] for j, m in self.meta.items()}
        self.proj = LM.Projector(self.B, self.lists, mapping, self.g, agreements, prior=prior, camp=camp)
        # station -> sector for turnout during the day (2022 classification of each station)
        b25 = json.load(open(os.path.join(ROOT, "site", "data", "ballots_K25.json"), encoding="utf-8"))
        locsec = {l["code"]: l["sector"] for l in core["localities"]}
        self.station_sector = {}
        self.sector_final = collections.defaultdict(lambda: [0, 0])
        # 2022 per station: final voters and votes by bloc, for turnout pace and the lean-weighted signal
        el25 = next(e for e in core["elections"] if e["id"] == "K25")
        bloc25 = {p["id"]: ("coal" if p["bloc"] == "nb" else "arab" if p["bloc"] == "arab" else "opp") for p in el25["parties"]}
        cols = b25["cols"]
        self.station22 = {}
        for row in b25["rows"]:
            code, kalpi, sc, elig, voters = row[0], str(row[1]), row[2], row[3], row[4]
            sec = station_sector(locsec.get(code, "jewish"), sc)
            self.station_sector[(code, kalpi)] = sec
            self.sector_final[sec][0] += elig
            self.sector_final[sec][1] += voters
            bv = collections.Counter()
            for c, v in zip(cols, row[6:]):
                bv[bloc25.get(c, "opp")] += v
            self.station22[(code, kalpi)] = (voters, dict(bv), sec)


def station_sector(loc_sector, code):
    if loc_sector == "arab":
        return "arab"
    if loc_sector == "druze":
        return "druze"
    if code % 10 == 1:
        return "mixed"       # Arab station in a mixed city or Jewish locality
    if code >= 10:
        return "haredi"
    return "jewish"


def poll_prior(polls):
    """The 2026 prior: national vote shares exactly as the page's own estimate (core.js
    voteSharesFromAverage; LM-4), keyed by list id, plus the small lists under LM.OTHER ("_other")."""
    return LM.poll_shares(polls)


# ------------------------------------------------------------------ results
def results_pass(E, data, out, source_url, history, state):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        tf.write(data)
        path = tf.name
    checks = {}
    try:
        cols, rows = read_expb(path, strict=False, checks=checks)      # OPS-8: odd rows do not block the feed
    finally:
        os.unlink(path)
    # The CEC file was briefly empty during the 2020 and 2021 counts. Rows only ever get added,
    # so an empty or shrunken file is rejected and the last good results stay published.
    n_counted = sum(1 for r in rows if r["voters"])
    if n_counted == 0:
        raise IOError("no counted stations in the file yet; nothing to publish")
    if n_counted < 0.98 * state.get("rows", 0):
        raise IOError(f"results file shrank from {state['rows']} to {n_counted} counted stations; keeping the last good snapshot")
    keep = set(E.lists)
    counted, env, dropped = {}, None, 0
    for r in rows:
        if r["elig"] and r["voters"] > r["elig"] * 1.02 and not r["env"]:
            dropped += 1                       # impossible row: more voters than eligible
            continue
        if not r["voters"]:
            continue                           # station listed but not yet counted
        if r["env"] or r["code"] is None:
            env = env or LM.new_unit()
            LM.add_row(env, r, keep)
        else:
            LM.add_row(counted.setdefault(r["code"], LM.new_unit()), r, keep)
    unknown = [c for c in cols if c not in keep]
    E.proj.env_override = E.cfg.get("envelopes_expected") or None
    frame = LM.make_frame(E.proj, counted, env if (env and env["valid"]) else None, E.meta, n_boot=200)
    if E.cfg.get("projection_paused"):
        frame["paused"] = E.cfg.get("pause_reason") or "התחזית הושהתה על ידי המפעיל."
    # what came in since the last accepted file: stations by sector and their vote by camp
    stations = {(r["code"], r["kalpi"]) for r in rows if r["voters"] and not r["env"] and r["code"] is not None}
    prev = {tuple(k.rsplit(":", 1)) for k in state.get("stations", [])}
    prev = {(int(c), k) for c, k in prev}
    new = stations - prev if prev else set()
    if new:
        by_sec, camp_v = collections.Counter(), collections.Counter()
        for r in rows:
            k = (r["code"], r["kalpi"])
            if k in new:
                by_sec[E.station_sector.get(k) or E.station_sector.get((r["code"], r["kalpi"].split(".")[0]), "jewish")] += 1
                for j, v in r["votes"].items():
                    camp_v[E.meta.get(j, {}).get("bloc", "opp")] += v
        tv = sum(camp_v.values()) or 1
        frame["batch"] = {"stations": len(new), "by_sector": dict(by_sec),
                          "blocs": {b: round(v / tv, 3) for b, v in camp_v.items()}}
    t = now_il()                               # the file changed: this is the data time
    history.append({"t": t.strftime("%H:%M"), "counted": frame["counted"]["share"],
                    "coal": frame["blocs"]["coal"]["seats"], "coal_lo": frame["blocs"]["coal"]["lo"],
                    "coal_hi": frame["blocs"]["coal"]["hi"], "p61": frame["blocs"]["coal"]["p61"]})
    acc = replay_accuracy()
    sha = hashlib.sha256(data).hexdigest()
    write_json(out, "results.json", {
        "election": E.dry or "K26", "updated_at": t.isoformat(), "updated_he": he_time(t),
        "source_url": source_url, "source_label": "ועדת הבחירות המרכזית · expb.csv",
        "frame": frame, "accuracy": acc["accuracy"], "accuracy_real": acc["accuracy_real"],
        "history": history[-240:],
        "checks": {"rows": len(rows), "counted_stations": n_counted, "dropped_impossible": dropped,
                   "unknown_lists": unknown, "bad_rows": checks.get("bad_rows", 0),
                   "ignored_columns": checks.get("ignored_columns", []), "sha256": sha},
    })
    write_json(out, "history.json", history[-240:])
    state.update({"rows": n_counted, "sha256": sha, "at": t.isoformat(), "data_he": he_time(t),
                  "counted": frame["counted"]["share"],
                  "stations": sorted(f"{c}:{k}" for c, k in stations)})
    return frame


def replay_accuracy():
    """The backtests shown next to the live projection: simulated orders and the real 2021 order."""
    d = read_json(os.path.join(ROOT, "site", "data", "replay_night.json"), {}) or {}
    return {"accuracy": d.get("accuracy"), "accuracy_real": d.get("accuracy_real")}


def drill_data(a, state, out):
    """Rehearsal input: the 2022 ballot file (media25 through fetch(), else data/official), revealed
    progressively over the drill so the page shows a count in progress."""
    cache = os.path.join(out, ".drill_source.csv")
    if a.results_file:
        raw = open(a.results_file, "rb").read()
        state["drill_source"] = a.results_file
    elif os.path.exists(cache):
        raw = open(cache, "rb").read()
    else:
        try:
            raw = fetch(a.drill_url)
            state["drill_source"] = a.drill_url
        except Exception as exc:
            raw = open(os.path.join(ROOT, "data", "official", "k25_expb.csv"), "rb").read()
            state["drill_source"] = f"data/official/k25_expb.csv ({exc.__class__.__name__}: {exc})"[:160]
        with open(cache, "wb") as f:
            f.write(raw)
    start = state.setdefault("drill_start", time.time())
    f = a.drill_fraction if a.drill_fraction is not None else (time.time() - start) / max(60.0, a.minutes * 60)
    f = min(1.0, max(0.0, f))
    state["drill_fraction"] = round(f, 3)
    return reveal(raw, f)


def reveal(raw, f):
    """The ballot file with the stations counted by fraction f of the night. Localities open in a
    fixed random order (bigger ones a little later) and are counted over the next quarter of the
    night; the double envelopes (סמל ישוב 9999) come in over the last 3%, as they do in reality."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1255")
    lines = text.splitlines()
    header = [h.strip() for h in lines[0].split(",")]
    ic = header.index("סמל ישוב")
    by_loc, env = collections.defaultdict(list), []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        code = ln.split(",")[ic].strip() if ln.count(",") >= ic else ""
        (env if code in ("9999", "99999") else by_loc[code]).append(ln)
    rng = random.Random(26)
    big = max((len(v) for v in by_loc.values()), default=1)
    order = sorted(by_loc, key=lambda c: rng.random() + 0.4 * len(by_loc[c]) / big)
    out = []
    for i, c in enumerate(order):
        start = 0.72 * i / max(1, len(order))                # the last locality opens at 72% and is done by 97%
        done = min(1.0, max(0.0, (f - start) / 0.25))
        boxes = list(by_loc[c])
        rng.shuffle(boxes)
        out += boxes[:round(done * len(boxes))]
    if f > 0.97:
        out += env[:round(min(1.0, (f - 0.97) / 0.03) * len(env))]
    return ("﻿" + "\n".join([lines[0]] + out) + "\n").encode("utf-8")


def results_step(E, a, cfg, state, history, out, status):
    """Decide whether to fetch, fetch, and publish when the file changed."""
    source = a.results_file or cfg.get("results_url") or DEFAULT_CFG["results_url"]
    src_key = [E.dry or "K26", "drill" if DRILL else source]
    if state.get("source") != src_key:            # OPS-11: state of another source or election is ignored
        for k in ("sha256", "rows", "stations", "at", "data_he", "counted", "drill_start", "drill_fraction"):
            state.pop(k, None)
        state["source"] = src_key
    election_day = dt.date.fromisoformat(cfg.get("election_day", DEFAULT_CFG["election_day"]))
    if DRILL:
        data = drill_data(a, state, out)
        status["drill_fraction"] = state.get("drill_fraction")
        status["drill_source"] = state.get("drill_source")
        maybe_probe(cfg.get("results_url") or DEFAULT_CFG["results_url"], state, status)   # does this runner reach media26?
    elif a.results_file:
        data = open(a.results_file, "rb").read()
    elif now_il() < closing(election_day):
        # OPS-2: nothing from the CEC is fetched or shown while the polls are open; a probe only
        status["results_state"] = "before-22"
        maybe_probe(cfg.get("results_url") or DEFAULT_CFG["results_url"], state, status)
        return
    else:
        data = fetch(source)
    sha = hashlib.sha256(data).hexdigest()
    if sha == state.get("sha256") and os.path.exists(os.path.join(out, "results.json")):
        status["results"] = {"counted": state.get("counted"), "sha256": sha}     # OPS-9: unchanged file
    else:
        frame = results_pass(E, data, out, source, history, state)
        status["results"] = {"counted": frame["counted"]["share"], "sha256": sha}
    status["results_state"] = "ok"
    status["data_he"] = state.get("data_he")


def maybe_probe(url, state, status):
    last = state.get("probe") or {}
    if time.time() - last.get("ts", 0) >= PROBE_EVERY:
        code, note = probe(url)
        last = {"http": code, "at_he": he_time(now_il()), "ts": time.time()}
        if note:
            last["error"] = note
        state["probe"] = last
    status["results_probe"] = {k: v for k, v in last.items() if k != "ts"}


# ------------------------------------------------------------------ turnout
def turnout_pass(E, cfg, out, state, status, inputs):
    try:
        manual = read_input(inputs, "turnout.json")
        if manual is not None and not isinstance(manual, dict):
            raise ValueError("turnout.json must be a JSON object")
        manual = state["turnout_input"] = manual or {}
    except Exception as exc:                      # OPS-10: a typo keeps the last valid figures on the page
        status["errors"].append(f"turnout: {exc.__class__.__name__}: {exc}"[:200])
        manual = state.get("turnout_input")
        if manual is None:
            old = read_json(os.path.join(out, "turnout.json"), {}) or {}
            manual = {k: old[k] for k in ("national", "released", "source", "source_url", "claims") if k in old}
    national = {}
    for h, v in (manual.get("national") or {}).items():       # "10:00".."22:00", and "19:00" in 2022
        if HOUR_RE.match(str(h)) and isinstance(v, (int, float)) and 0 <= v <= 100:
            national[h] = v
    # Third-party turnout estimates may be survey-based, i.e. election polls under §16ה(ח):
    # they are published only after the polls close.
    election_day = dt.date.fromisoformat(E.cfg.get("election_day", DEFAULT_CFG["election_day"]))
    closed = now_il() >= closing(election_day)
    doc = {"updated_at": now_il().isoformat(), "updated_he": he_time(now_il()), "national": national,
           "eligible": E.eligible, "claims": manual.get("claims", []) if closed else [],
           "source": str(manual.get("source", "") or "")}
    for k in ("released", "source_url"):          # when the CEC released each figure, and where
        if manual.get(k):
            doc[k] = manual[k]
    url = cfg.get("station_turnout_url")
    if url:
        try:
            data = fetch(url)
            st = station_turnout(E, data)
            if st["sectors"]:
                doc.update({"sectors": st["sectors"], "stations_national": st["national"],
                            "sectors_time": manual.get("sectors_time", "") or now_il().strftime("%H:%M"),
                            "sectors_coverage": st["coverage"], "sectors_excluded": st["excluded"],
                            "sectors_sha256": hashlib.sha256(data).hexdigest()})
                # the 2022-vote-weighted pace is an open question for the CEC legal adviser: not during voting
                if closed or cfg.get("lean_during_voting"):
                    doc["lean"] = st["lean"]
        except Exception as exc:
            doc["station_error"] = f"{exc.__class__.__name__}: {exc}"[:200]
    write_json(out, "turnout.json", doc)
    return doc


def station_turnout(E, data):
    """Per-station turnout release -> turnout by sector and by 2022 vote.

    The CEC format is not known in advance, so columns are found by their Hebrew names (as in
    expb.csv: סמל ישוב, קלפי, בזב, מצביעים). For every sector:
      turnout  = voters so far / eligible, over the stations in the release;
      ratio    = that turnout / the national turnout of the same release;
      pace     = voters so far / the same stations' final voters in 2022.
    The lean-weighted signal weights each station's pace by its 2022 votes for each bloc: are the
    stations that voted for the Netanyahu bloc, the Jewish opposition or the Arab lists in 2022
    turning out faster or slower than then? Stations that cannot be matched to 2022 or whose pace
    is implausible (>2.0, usually a renumbered station) are left out of pace and counted."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1255", "replace")
    rd = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(rd)]

    def col(*names):
        return next((header.index(n) for n in names if n in header), None)
    ic, ik = col("סמל ישוב", "סמל יישוב"), col("קלפי", "מספר קלפי")
    ie, iv = col("בזב", "בעלי זכות בחירה"), col("מצביעים", "הצביעו")
    if None in (ic, ik, iv):
        raise ValueError(f"unknown columns: {header[:12]}")
    agg = collections.defaultdict(lambda: {"elig": 0, "voters": 0, "stations": 0, "now": 0, "then": 0})
    lean = collections.defaultdict(lambda: [0.0, 0.0])           # bloc -> [Σ pace×votes22, Σ votes22]
    nat = {"elig": 0, "voters": 0}
    excluded = collections.Counter()
    for rec in rd:
        try:
            code, kalpi, voters = int(rec[ic]), rec[ik].strip(), int(float(rec[iv] or 0))
        except (ValueError, IndexError):
            excluded["unreadable"] += 1
            continue
        elig = int(float(rec[ie] or 0)) if ie is not None else 0
        if elig and voters > elig * 1.02:
            excluded["more voters than eligible"] += 1
            continue
        key = (code, kalpi) if (code, kalpi) in E.station22 else (code, kalpi.split(".")[0])
        sec = E.station_sector.get(key, "jewish")
        a = agg[sec]
        if elig:
            a["elig"] += elig
            a["voters"] += voters
            nat["elig"] += elig
            nat["voters"] += voters
        a["stations"] += 1
        s22 = E.station22.get(key)
        if not s22 or not s22[0]:
            excluded["no 2022 match"] += 1
            continue
        pace = voters / s22[0]
        if pace > 2.0:
            excluded["implausible pace"] += 1
            continue
        a["now"] += voters
        a["then"] += s22[0]
        for b, v in s22[1].items():
            lean[b][0] += pace * v
            lean[b][1] += v
    nt = nat["voters"] / nat["elig"] if nat["elig"] else None
    out = {}
    for k, a in agg.items():
        fe, fv = E.sector_final[k]
        t = a["voters"] / a["elig"] if a["elig"] else None
        out[k] = {"turnout": round(t, 4) if t is not None else None,
                  "ratio": round(t / nt, 3) if (t is not None and nt) else None,
                  "pace": round(a["now"] / a["then"], 3) if a["then"] else None,
                  "coverage": round(a["then"] / fv, 3) if fv else None,
                  "final_2022": round(fv / fe, 4) if fe else None, "stations": a["stations"]}
    signal = {b: round(x / w, 3) for b, (x, w) in lean.items() if w}
    total22 = sum(v[1] for v in E.sector_final.values())
    return {"sectors": out, "lean": signal, "national": round(nt, 4) if nt else None,
            "coverage": round(sum(a["then"] for a in agg.values()) / total22, 3) if total22 else 0,
            "excluded": dict(excluded)}


# ------------------------------------------------------------------ exit polls
def exit_polls_pass(out, election_day, state, status, inputs):
    """Publish live_input/exit_polls.json after the polls close; remove the published copy when
    the input is deleted or emptied (a retraction), and never show one before 22:00."""
    closed = now_il() >= closing(election_day)
    try:
        ep = read_input(inputs, "exit_polls.json")
        state["exit_input"] = ep
    except Exception as exc:
        status["errors"].append(f"exit polls: {exc.__class__.__name__}: {exc}"[:200])
        ep = state.get("exit_input")              # OPS-10: the last valid copy
    if ep and closed:
        write_json(out, "exit_polls.json", ep)
        return True
    remove_json(out, "exit_polls.json")           # OPS-14, and never before polls close (Elections Law)
    return False


# ------------------------------------------------------------------ publishing from a laptop
def git(*args, cwd=ROOT, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[:200]}")
    return r


def publish(out, branch="live-data", wt=None, repo=ROOT):
    """Laptop fallback when GitHub's runners cannot reach the CEC: copy out/*.json into a worktree
    of the live-data branch and push with the same reset cycle as the workflow (fetch, reset --hard
    to the remote tip, copy, commit, push; never rebase, so two writers cannot wedge each other).
    The branch holds only live/; the page is rebuilt by pages.yml (see dispatch_pages)."""
    wt = wt or os.path.join(repo, ".live-data")
    ref = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
    if not os.path.exists(os.path.join(wt, ".git")):
        shutil.rmtree(wt, ignore_errors=True)
        git("worktree", "prune", cwd=repo, check=False)     # a stale registration from a deleted folder
        if git("fetch", "-q", "origin", ref, cwd=repo, check=False).returncode == 0:
            git("worktree", "add", "-q", "--detach", wt, f"origin/{branch}", cwd=repo)
        else:                                     # first use: an orphan branch holding only live/
            git("worktree", "add", "-q", "--detach", wt, cwd=repo)
            git("checkout", "-q", "--orphan", f"{branch}-{int(time.time())}", cwd=wt)
            git("rm", "-rfq", "--cached", ".", cwd=wt)
            for name in os.listdir(wt):
                if name != ".git":
                    (shutil.rmtree if os.path.isdir(os.path.join(wt, name)) else os.remove)(os.path.join(wt, name))
            os.makedirs(os.path.join(wt, "live"))
            shutil.copy(os.path.join(repo, "site", "live", "status.json"), os.path.join(wt, "live", "status.json"))
            git("add", "-A", cwd=wt)
            git("commit", "-q", "-m", "live-data: placeholder", cwd=wt)
            git("push", "-q", "origin", f"HEAD:{branch}", cwd=wt, check=False)
            git("checkout", "-q", "--detach", cwd=wt)
    for attempt in range(5):
        if git("fetch", "-q", "origin", ref, cwd=wt, check=False).returncode == 0:
            git("reset", "-q", "--hard", f"origin/{branch}", cwd=wt)
        live = os.path.join(wt, "live")
        os.makedirs(live, exist_ok=True)
        for p in glob.glob(os.path.join(live, "*.json")):
            os.remove(p)
        for p in glob.glob(os.path.join(out, "*.json")):
            shutil.copy(p, live)
        if not git("status", "--porcelain", cwd=wt).stdout.strip():
            return "unchanged"
        git("add", "-A", "live", cwd=wt)
        git("commit", "-q", "-m", f"live {now_il().strftime('%H:%M')} (laptop)", cwd=wt)
        if git("push", "-q", "origin", f"HEAD:{branch}", cwd=wt, check=False).returncode == 0:
            return "pushed"
        time.sleep(3 + 2 * attempt)
    return "push failed"


_dispatch = {"last": 0.0, "warned": False}


def dispatch_pages(ref="main", min_gap=50, repo=ROOT, pending=None):
    """Ask GitHub to rebuild the page (pages.yml, workflow_dispatch) at most once per min_gap
    seconds: with gh when it is installed and logged in, else through the REST API with $GH_TOKEN."""
    if time.time() - _dispatch["last"] < min_gap:
        return "deferred"
    _dispatch["last"] = time.time()
    if shutil.which("gh"):
        r = subprocess.run(["gh", "workflow", "run", "pages.yml", "--ref", ref], cwd=repo, capture_output=True, text=True)
        if r.returncode == 0:
            return "gh"
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    slug = os.environ.get("GITHUB_REPOSITORY") or origin_repo(repo)
    if token and slug:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{slug}/actions/workflows/pages.yml/dispatches",
            data=json.dumps({"ref": ref}).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "User-Agent": UA, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return f"rest {r.status}"
        except urllib.error.HTTPError as exc:
            return f"rest failed {exc.code}"
        except Exception as exc:
            return f"rest failed {exc.__class__.__name__}"
    if not _dispatch["warned"]:
        _dispatch["warned"] = True
        print("warning: the page will not be rebuilt: install gh and run `gh auth login`, or set GH_TOKEN", file=sys.stderr)
    return "no dispatcher"


def origin_repo(repo=ROOT):
    r = git("remote", "get-url", "origin", cwd=repo, check=False)
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?$", r.stdout.strip())
    return m.group(1) if m else ""


# ------------------------------------------------------------------ main
def load_config(path, state, errors):
    """The config, or the last valid copy when it does not parse (OPS-10)."""
    try:
        cfg = json.load(open(path, encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("not a JSON object")
        state["config"] = cfg
        return cfg
    except Exception as exc:
        errors.append(f"config: {exc.__class__.__name__}: {exc}"[:200])
        return state.get("config") or dict(DEFAULT_CFG)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "live"))
    ap.add_argument("--config", default=os.path.join(ROOT, "pipeline", "live_config.json"))
    ap.add_argument("--inputs", default=os.path.join(ROOT, "live_input"), help="folder of the manual inputs")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=60, help="seconds between passes")
    ap.add_argument("--minutes", type=float, default=345, help="stop after this many minutes (a drill reveals 2022 over them)")
    ap.add_argument("--results-file", default="", help="read results from a local file (testing)")
    ap.add_argument("--as", dest="as_election", default=None, help="treat the file as this past election")
    ap.add_argument("--drill", action="store_true", help="rehearsal on the 2022 file, revealed progressively; every output is marked")
    ap.add_argument("--drill-url", default=DRILL_URL)
    ap.add_argument("--drill-fraction", type=float, default=None, help="drill: reveal this share of 2022 instead of following the clock")
    ap.add_argument("--publish", action="store_true", help="push live/*.json to the live-data branch and redeploy after every pass (laptop mode)")
    ap.add_argument("--ref", default="main", help="branch of pages.yml to dispatch with --publish")
    a = ap.parse_args(argv)
    global DRILL
    DRILL = a.drill
    if DRILL and not a.as_election:
        a.as_election = "K25"
    os.makedirs(a.out, exist_ok=True)
    state = read_json(os.path.join(a.out, STATE), {}) or {}
    boot_errors = []
    cfg = load_config(a.config, state, boot_errors)
    E = Election2026(cfg, a.as_election)
    hist_path = os.path.join(a.out, "history.json")
    history = read_json(hist_path, []) if os.path.exists(hist_path) else []
    start = time.time()
    while True:
        CHANGED.clear()
        t = now_il()
        status = {"updated_at": t.isoformat(), "updated_he": he_time(t), "checked_he": he_time(t),
                  "election": E.dry or "K26", "phase": "pre", "has_results": False, "has_turnout": False,
                  "exit_polls": False, "results_state": "waiting", "errors": []}
        if os.environ.get("PAGES_SOURCE"):
            status["pages_source"] = os.environ["PAGES_SOURCE"]
        if DRILL:
            status["drill"] = True
        cfg = E.cfg = load_config(a.config, state, status["errors"])
        election_day = dt.date.fromisoformat(cfg.get("election_day", DEFAULT_CFG["election_day"]))
        if discard_drill_output(a.out):
            status["errors"].append("discarded the files of a rehearsal")
            history = []
        try:
            td = turnout_pass(E, cfg, a.out, state, status, a.inputs)
            status["has_turnout"] = bool(td.get("national") or td.get("sectors"))
        except Exception as exc:
            status["errors"].append(f"turnout: {exc.__class__.__name__}: {exc}"[:200])
            old = read_json(os.path.join(a.out, "turnout.json"), {}) or {}
            status["has_turnout"] = bool(old.get("national") or old.get("sectors"))
        try:
            results_step(E, a, cfg, state, history, a.out, status)
        except Exception as exc:
            status["results_state"] = "waiting"
            status["errors"].append(f"results: {exc.__class__.__name__}: {exc}"[:200])
        status["has_results"] = os.path.exists(os.path.join(a.out, "results.json"))
        if status["has_results"] and status.get("results") is None:
            status["data_he"] = state.get("data_he")
        try:
            status["exit_polls"] = exit_polls_pass(a.out, election_day, state, status, a.inputs)
        except Exception as exc:
            status["errors"].append(f"exit polls: {exc}"[:200])
        status["phase"] = ("night" if status["has_results"] or t >= closing(election_day)
                           else "day" if t.date() == election_day else "pre")
        write_json(a.out, STATE, state)
        write_json(a.out, "status.json", status, heartbeat=HEARTBEAT)
        if a.publish and CHANGED:
            try:
                status["published"] = publish(a.out)
                if status["published"] == "pushed":
                    status["dispatched"] = dispatch_pages(a.ref)
            except Exception as exc:
                status["errors"].append(f"publish: {exc}"[:200])
        print(json.dumps({**status, "changed": list(CHANGED)}, ensure_ascii=False), flush=True)
        if a.once or (time.time() - start) / 60 > a.minutes:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
