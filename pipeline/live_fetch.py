"""Election day & night fetcher: official CEC files -> live/*.json for the dashboard.

Runs on GitHub Actions (.github/workflows/live.yml, one pass per loop iteration) or on any laptop:

    python3 pipeline/live_fetch.py --out live --loop 60 --publish   # laptop: poll every 60 s and publish until
                                                                    # stopped (Ctrl-C); --minutes N stops after N
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
    URL is configured. A per-station release also feeds the Arab-society section
    (pipeline/arab_turnout.py, when present): turnout by locality, by the list that led there in
    2022 (Ra'am / Joint List) and by region, published during voting hours too.
  * Exit polls: live_input/exit_polls.json, published only after polls close (22:00).

Outputs (next to the page; the JSON contract is in the lead's ARCH_V2/V3 notes)
  live/results.json   counted totals + projection frame (pipeline/live_model.make_frame);
                      updated_he is the time the CEC file last changed, not the time of the check
  live/turnout.json   national hourly series, sector turnout from per-station data, "arab" and
                      "arab_history" (one entry per per-station release, the last 8, with every
                      locality's and kind's turnout and pace); a release's time is sectors_time from
                      live_input/turnout.json for the file it was set for, else when first seen; while
                      the polls are open a new release waits up to 10 minutes for its sectors_time
  live/exit_polls.json, live/status.json, live/history.json (projection over the night)
  live/state.json     persisted state keyed by source: last accepted sha256, stations, last valid
                      inputs and config, probe times. State from another source is ignored.

Publishing (--publish; the workflow and the laptop share the code, see publish_step): branch mode
(Pages "Deploy from a branch", the owner's setting) commits the files to site/live/ on main and asks
Pages for a build, at most once every publish_every_min minutes (live_config.json, default 8; the
first results and the first exit polls at once), and a feed with nothing new but its timestamps at
most every 30 minutes (60 from noon the day after the election); Actions mode commits them to the
live-data branch and dispatches pages.yml.

Every download is checked: an empty body, HTML or JSON instead of CSV (maintenance page, WAF,
rate limit) is rejected, a file without the expected columns or without a single counted station
is rejected, rows with more voters than eligible voters are dropped and counted, a file whose count
of counted stations shrank by more than 2% is rejected (a smaller shrink is a CEC correction and is
accepted), an unchanged file (same SHA-256) is skipped, and the SHA-256 of
each accepted file is recorded. Each pass prints one JSON line (the status plus "changed": the
files written or removed, and what was published), which the workflow logs.
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
from build_data import HEADER_ALIASES, load_election, read_expb  # noqa: E402

ROOT = LM.ROOT
try:                                    # the Arab-society election-day section; optional: absent = skipped
    import arab_turnout as AT           # noqa: E402
    AT_ERR = ""
except Exception as _exc:               # a broken module is reported in status.errors, the feed runs on
    AT = None
    AT_ERR = "" if isinstance(_exc, ModuleNotFoundError) and _exc.name == "arab_turnout" else f"{_exc.__class__.__name__}: {_exc}"
ARAB_BASE = os.path.join(ROOT, "site", "data", "arab_day_2022.json")
ARAB_HISTORY = 8                        # turnout.json arab_history: one entry per per-station release, the last 8
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
QUIET_EVERY = 30        # minutes: branch mode publishes a feed with nothing new but timestamps at most this often
QUIET_AFTER = 60        # minutes: the same from noon the day after the election (the regular count is over)
HOLD_FOR_TIME = 10      # minutes a new per-station release waits for its sectors_time while the polls are open
SHRINK_OK = 0.98        # a results file may lose up to 2% of its counted stations (a CEC correction), not more
HOUR_RE = re.compile(r"^\d{2}:\d{2}$")
PLACEHOLDER_ELIGIBLE = 7340000   # the pre-election estimate in live_config.json; the CEC's official figure replaces it (LM-B)
REGISTER_SLACK = 0.99            # while the counted register exceeds the configured one, the share reads this, not "all counted"
RESULTS_CACHE = ".results_last.csv"   # the last accepted CEC file, re-rendered when an operator switch changes (DOC-3)
PAUSED_HE = "התחזית הושהתה על ידי המפעיל."   # frame.paused when pause_reason is empty


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
    return check_body(data)


def check_body(data):
    """data, unless it is empty or an HTML/JSON page (maintenance, WAF, rate limit) instead of a data file."""
    head = data[:200].lstrip(b"\xef\xbb\xbf \t\r\n").lower()     # the 2022 file starts with a UTF-8 BOM
    if not head:
        raise IOError("empty body")
    if head[:1] in (b"<", b"{", b"["):
        raise IOError("got an HTML or JSON page instead of a data file")
    return data


def read_source(url):
    """A data file from a URL, or from a path in the repository (a copy the operator committed, e.g.
    live_input/stations.csv, when the CEC's file cannot be read directly)."""
    if re.match(r"https?://", url):
        return fetch(url)
    with open(os.path.join(ROOT, url), "rb") as f:
        return check_body(f.read())


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
            prior = {to_letter.get(k, k): v for k, v in poll_prior(polls).items()}   # '_other' stays as OTHER
        (_, base_rows), self.base_source = load_election(src, base_e)
        self.B = LM.Baseline(base_e, base_rows, core)
        # the ballot file's eligible voters per station add up to the whole register (envelope voters
        # are registered at their home station), so register growth scales every locality
        self.base_elig = sum(L["elig"] for L in self.B.loc.values())
        if self.dry:
            (_, cur_rows), _ = load_election(src, self.dry)
            self.eligible = sum(r["elig"] for r in cur_rows if not r["env"] and r["code"] is not None)
        else:
            self.eligible = cfg.get("eligible") or round(self.base_elig * 1.081)
        self.g = self.eligible / self.base_elig
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

    def set_register(self, cfg):
        """The register size from the config, re-read every pass so an edit of `eligible` acts at the next pass."""
        if not self.dry:
            self.eligible = cfg.get("eligible") or round(self.base_elig * 1.081)
        self.g = self.proj.g = self.eligible / self.base_elig


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
def results_pass(E, data, out, source_url, history, state, errors, restamp=True):
    """Publish results.json from the file `data`. restamp=False re-renders a file already accepted
    (an operator switch changed, DOC-3): the data time and the history stay as they were."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        tf.write(data)
        path = tf.name
    checks = {}
    try:   # OPS-8: odd rows do not block the feed; WF-1: live_config.json can drop or rename columns on the night
        cols, rows = read_expb(path, strict=False, checks=checks, ignore_columns=E.cfg.get("ignore_columns") or (),
                               column_aliases=E.cfg.get("column_aliases") or None)
    finally:
        os.unlink(path)
    # The CEC file was briefly empty during the 2020 and 2021 counts. Rows only ever get added, so an empty
    # file, or one with more than 2% fewer counted stations than the last accepted one, is rejected and the
    # last good results stay published; a smaller shrink is the CEC correcting a few stations and is accepted
    # (the count on the page then steps back a little; the history line does not, below)
    n_counted = sum(1 for r in rows if r["voters"])
    if n_counted == 0:
        raise IOError("no counted stations in the file yet; nothing to publish")
    if n_counted < SHRINK_OK * state.get("rows", 0):
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
    # LM-B: the CEC file never lists the whole register, so a configured `eligible` that is too small is noticed only
    # here: once more eligible voters are counted than configured, the page would say "all boxes counted" and the
    # projection would drop the boxes still out. Scale the register for this pass so the share reads 0.99, and shout.
    counted_elig = sum(C["elig"] for C in counted.values())
    E.proj.g = E.g
    if counted_elig > E.eligible:
        E.proj.g = counted_elig / (REGISTER_SLACK * E.base_elig)
        errors.append(f"register exceeded: {counted_elig:,} eligible voters counted > eligible {E.eligible:,} in "
                      "live_config.json; set the CEC's official figure (the count is shown as 99% until then)")
    frame = LM.make_frame(E.proj, counted, env if (env and env["valid"]) else None, E.meta, n_boot=200)
    if E.cfg.get("projection_paused"):
        frame["paused"] = E.cfg.get("pause_reason") or PAUSED_HE
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
    elif not restamp:                              # same file again: the last batch stays on the page
        old = read_json(os.path.join(out, "results.json"), {}) or {}
        if (old.get("frame") or {}).get("batch"):
            frame["batch"] = old["frame"]["batch"]
    if restamp or not state.get("at"):
        t = now_il()                           # the file changed: this is the data time
        # a corrected file with a few stations fewer (SHRINK_OK) adds no point that steps back in the history
        if not (history and frame["counted"]["share"] < (history[-1].get("counted") or 0)):
            history.append({"t": t.strftime("%H:%M"), "counted": frame["counted"]["share"],
                            "coal": frame["blocs"]["coal"]["seats"], "coal_lo": frame["blocs"]["coal"]["lo"],
                            "coal_hi": frame["blocs"]["coal"]["hi"], "p61": frame["blocs"]["coal"]["p61"]})
    else:
        t = dt.datetime.fromisoformat(state["at"])   # same file, a switch changed: the data time stays
    acc = replay_accuracy()
    sha = hashlib.sha256(data).hexdigest()
    with open(os.path.join(out, RESULTS_CACHE), "wb") as f:   # for a switch change while the file is unavailable
        f.write(data)
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
        for k in ("sha256", "rows", "stations", "at", "data_he", "counted", "drill_start", "drill_fraction", "switches"):
            state.pop(k, None)
        state["source"] = src_key
        if os.path.exists(os.path.join(out, RESULTS_CACHE)):
            os.remove(os.path.join(out, RESULTS_CACHE))
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
    sw = switches(cfg)
    if sha == state.get("sha256") and os.path.exists(os.path.join(out, "results.json")):
        status["results"] = {"counted": state.get("counted"), "sha256": sha}     # OPS-9: unchanged file
        if state.get("switches") != sw:           # DOC-3: a switch changed: same file again, data time unchanged
            results_pass(E, data, out, source, history, state, status["errors"], restamp=False)
    else:
        frame = results_pass(E, data, out, source, history, state, status["errors"])
        status["results"] = {"counted": frame["counted"]["share"], "sha256": sha}
    state["switches"] = sw
    status["results_state"] = "ok"
    status["data_he"] = state.get("data_he")


def switches(cfg):
    """The config keys that act on an already published file (DOC-3; eligible for LM-B)."""
    return [bool(cfg.get("projection_paused")), cfg.get("pause_reason") or "", cfg.get("envelopes_expected") or None,
            cfg.get("eligible")]


def switches_pass(E, cfg, out, history, state, status):
    """DOC-3: projection_paused / pause_reason / envelopes_expected act on the last accepted file even
    while the CEC file cannot be fetched or is being rejected (the case the switch is for). A run that took
    over from another (the workflow chains runs) has no copy of that file (RESULTS_CACHE is not published):
    then the pause acts on the published results.json itself, and envelopes_expected / eligible, which need
    the file, are reported until it is read again (R4)."""
    sw, cache, res_p = switches(cfg), os.path.join(out, RESULTS_CACHE), os.path.join(out, "results.json")
    if state.get("switches") == sw or not os.path.exists(res_p):
        return
    if not os.path.exists(cache):
        old = state.get("switches")
        try:
            doc = read_json(res_p)
            want = (cfg.get("pause_reason") or PAUSED_HE) if sw[0] else None
            if doc["frame"].get("paused") != want:
                if want:
                    doc["frame"]["paused"] = want
                else:
                    doc["frame"].pop("paused", None)
                write_json(out, "results.json", doc)          # the data time and the history stay as they were
        except Exception as exc:
            status["errors"].append(f"switches: {exc.__class__.__name__}: {exc}"[:200])
            return
        if old and list(old[2:]) != sw[2:]:
            status["errors"].append("switches: envelopes_expected / eligible not applied yet: this run has no copy of the "
                                    "last accepted CEC file; they act when the file is next read")
            sw = sw[:2] + list(old[2:])                       # still due: the next read of the file re-renders it
        state["switches"] = sw
        return
    try:
        results_pass(E, open(cache, "rb").read(), out, (state.get("source") or ["", ""])[1], history, state,
                     status["errors"], restamp=False)
        state["switches"] = sw
    except Exception as exc:
        status["errors"].append(f"switches: {exc.__class__.__name__}: {exc}"[:200])


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
    # Third-party turnout estimates may be survey-based, i.e. election polls under §16ה(ח):
    # they are published only after the polls close, and not even cached in the published state before.
    election_day = dt.date.fromisoformat(E.cfg.get("election_day", DEFAULT_CFG["election_day"]))
    closed = now_il() >= closing(election_day)
    try:
        manual = read_input(inputs, "turnout.json")
        if manual is not None and not isinstance(manual, dict):
            raise ValueError("turnout.json must be a JSON object")
        manual = manual or {}
        state["turnout_input"] = manual if closed else {k: v for k, v in manual.items() if k != "claims"}
    except Exception as exc:                      # OPS-10: a typo keeps the last valid figures on the page
        status["errors"].append(f"turnout: {exc.__class__.__name__}: {exc}"[:200])
        manual = state.get("turnout_input")
        if manual is None:
            old = read_json(os.path.join(out, "turnout.json"), {}) or {}
            manual = {k: old[k] for k in ("national", "released", "source", "source_url", "claims") if k in old}
    national, nat, ignored = {}, manual.get("national") or {}, []
    if not isinstance(nat, dict):
        status["errors"].append('turnout: "national" must be an object like {"10:00": 15.2}')
        nat = {}
    for h, v in nat.items():                      # "10:00".."22:00", and "19:00" in 2022
        if HOUR_RE.match(str(h)) and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100:
            national[h] = v
        else:
            ignored.append(f"{h}: {json.dumps(v, ensure_ascii=False)}")
    if ignored:                                   # DOC-7: a phone typo must not vanish silently
        status["errors"].append(f"turnout: ignored {', '.join(ignored)} (the key must be HH:MM, the value a number 0-100)"[:200])
    doc = {"updated_at": now_il().isoformat(), "updated_he": he_time(now_il()), "national": national,
           "eligible": E.eligible, "claims": manual.get("claims", []) if closed else [],
           "source": str(manual.get("source", "") or "")}
    for k in ("released", "source_url"):          # when the CEC released each figure, and where
        if manual.get(k):
            doc[k] = manual[k]
    url = cfg.get("station_turnout_url")
    if url:
        old = read_json(os.path.join(out, "turnout.json"), {}) or {}
        lean_ok = closed or cfg.get("lean_during_voting")
        try:
            data = read_source(url)
            sha = hashlib.sha256(data).hexdigest()
            released = release_time(manual, state, sha, election_day, status["errors"])
            rows, excluded = station_rows(data, cfg.get("column_aliases") or None)
            if held_for_time(state, sha, closed):
                # R1: the page keeps the last release until this one has its CEC time (or the hold ends)
                status["errors"].append(f"turnout: per-station release seen {state.get('station_seen')} held for sectors_time "
                                        f"(up to {HOLD_FOR_TIME} minutes): set the CEC's time for it in live_input/turnout.json")
                doc.update({k: old[k] for k in STATION_KEYS if k in old})
                if lean_ok and "lean" in old:
                    doc["lean"] = old["lean"]
                write_json(out, "turnout.json", doc)
                return doc
            st = station_turnout(E, rows, excluded)
            if st["sectors"]:
                doc.update({"sectors": st["sectors"], "stations_national": st["national"], "sectors_time": released,
                            "sectors_coverage": st["coverage"], "sectors_excluded": st["excluded"], "sectors_sha256": sha})
                # the 2022-vote-weighted pace is an open question for the CEC legal adviser: not during voting
                if lean_ok:
                    doc["lean"] = st["lean"]
            # the national turnout of the same rows under the same rule (blank = not reported), see station_turnout
            arab_pass(rows, st["national"], released, sha, doc, old, state, status["errors"])
        except Exception as exc:
            doc["station_error"] = f"{exc.__class__.__name__}: {exc}"[:200]
            # the CEC file comes and goes: the last release read stays on the page
            doc.update({k: old[k] for k in STATION_KEYS if k in old})
            if lean_ok and "lean" in old:
                doc["lean"] = old["lean"]
    write_json(out, "turnout.json", doc)
    return doc


STATION_KEYS = ("sectors", "stations_national", "sectors_time", "sectors_coverage", "sectors_excluded",
                "sectors_sha256", "arab", "arab_history")
# turnout.json "sectors_excluded" {key: stations}: the per-station rows left out, by reason. The keys are part of the
# contract with the page, which shows each in Hebrew. Out of every sum: "no figure" (blank or '-': not reported yet),
# "zero voters" (0: not reported yet), "unreadable", "more voters than eligible". In the turnout but out of the pace:
# "no 2022 match" and "implausible pace" (more than twice the station's 2022 voters, usually a renumbered station).
EXCLUDED_KEYS = ("no figure", "zero voters", "unreadable", "more voters than eligible", "no 2022 match", "implausible pace")
SECTORS_FIT = (10, 180)   # minutes: a sectors_time fits a release first seen up to 10 minutes before it to 3 hours after


def _minutes(hhmm):
    h, m = str(hhmm).split(":")[:2]
    return int(h) * 60 + int(m)


def release_time(manual, state, sha, election_day, errors):
    """The time a per-station release refers to, 'HH:MM': the "released" of the sector turnout and of the Arab
    section (arab_turnout projects from it, so it should be the CEC's cutoff, not the download time).
    A new release (a new SHA-256) is stamped once, when first seen; one first seen after the polls close is
    stamped 22:00, the latest time its figures can refer to. The operator's sectors_time (live_input/turnout.json,
    the cutoff the CEC states) replaces the stamp, but only for the release it was set for: it binds to the
    release it fits (first seen from 10 minutes before it to 3 hours after it) and never labels a later one.
    A sectors_time left over from an earlier release is reported and the stamp is used; one that fits no release
    yet (typed ahead of its file) is reported, the current release keeps the time it had, and it binds when the
    file arrives. A new release of another day than the last one (a test file before election day) starts
    arab_history afresh."""
    now = now_il()
    if state.get("station_sha") != sha:
        closed = now >= closing(election_day)
        day = (election_day if closed else now.date()).isoformat()
        if state.get("station_day") != day:
            state["arab_history"] = []
        state.update(station_sha=sha, station_seen="22:00" if closed else now.strftime("%H:%M"), station_day=day,
                     station_seen_at=now.isoformat())
    seen = state.get("station_seen") or now.strftime("%H:%M")
    s = manual.get("sectors_time")
    if s is None or str(s).strip() == "":
        state.pop("sectors_bind", None)
        return seen
    bind = state.get("sectors_bind") or {}
    mine = bind.get("time") if bind.get("sha") == sha else None    # the time this release was given, if any
    s = str(s).strip()
    if not HOUR_RE.match(s):
        errors.append(f"turnout: sectors_time {json.dumps(s, ensure_ascii=False)} is not HH:MM; the per-station release "
                      f"is labelled {mine or seen}"[:200])
        return mine or seen
    if s == bind.get("time"):
        if mine:
            return s
        errors.append(f"turnout: sectors_time {s} was set for an earlier per-station release; this one is labelled {seen}, "
                      "when it was first seen: set the CEC's time for it, or remove sectors_time"[:200])
        return seen
    if -SECTORS_FIT[0] <= _minutes(seen) - _minutes(s) <= SECTORS_FIT[1]:
        state["sectors_bind"] = {"time": s, "sha": sha}      # a new time for this release (or a corrected one)
        return s
    errors.append(f"turnout: sectors_time {s} does not fit the per-station release first seen at {seen} (it can be up to "
                  f"3 hours earlier, not later); it waits for the next release, this one stays {mine or seen}"[:200])
    return mine or seen


def held_for_time(state, sha, closed):
    """R1: while the polls are open, a new per-station release that has no sectors_time bound to it yet (release_time)
    is held back for HOLD_FOR_TIME minutes after it was first seen: the page keeps the last release meanwhile. Its
    figures are read against the 2022 curve at the release's time (the Arab section's same-hour comparison, on_track,
    the final-turnout range), so a release labelled with the time it was first seen, until the operator's time
    arrives a publish later, shows wrong figures in between. A time typed before the file arrives binds at once (no
    hold); after the hold the release goes out labelled with the time it was first seen, as before."""
    if closed or (state.get("sectors_bind") or {}).get("sha") == sha or not state.get("station_seen_at"):
        return False
    seen_at = dt.datetime.fromisoformat(state["station_seen_at"])
    return now_il() - seen_at < dt.timedelta(minutes=HOLD_FOR_TIME)


# per-station turnout headers read without an alias, by role (the names arab_turnout.read_station_csv takes);
# build_data.HEADER_ALIASES and live_config.json column_aliases map other spellings onto them
STATION_COLS = {"code": ("סמל ישוב", "סמל יישוב", "קוד ישוב", "קוד יישוב"),
                "kalpi": ("קלפי", "מספר קלפי", "מס' קלפי", "מס קלפי", "סמל קלפי"),
                "elig": ("בזב", 'בז"ב', "בעלי זכות בחירה", "בעלי זכות"),
                "voters": ("מצביעים", "הצביעו", "מספר מצביעים", "מצביעים עד כה"),
                "pct": ("אחוז הצבעה", "שיעור הצבעה", "אחוז")}


def _cell(rec, i):
    """A number cell: None when blank or '-' (not reported yet), else the number; ValueError if unreadable."""
    s = rec[i].strip() if i is not None else ""
    return None if s in ("", "-") else float(s.rstrip("%"))


def station_rows(data, column_aliases=None):
    """A per-station turnout release -> rows [{"code", "kalpi", "elig" (None without a בזב column), "voters"}]
    and a count of the rows left out, by reason. The CEC format is not known in advance, so columns are
    found by their Hebrew names (as in expb.csv: סמל ישוב, קלפי, בזב, מצביעים, and the variants in
    STATION_COLS), after build_data.HEADER_ALIASES and live_config.json column_aliases ({"their name":
    "expected name"}); the delimiter is a comma, semicolon, tab or '|', whichever the header uses; a file with
    a turnout percentage and no voter count gives voters = percentage x eligible. A blank or '-' voters cell
    is a station not reported yet: voters None (not 0), as arab_turnout reads it."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1255", "replace")
    text = text.lstrip("\ufeff")
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    delim = max(",;\t|", key=first.count)
    rd = csv.reader(io.StringIO(text), delimiter=delim if first.count(delim) else ",")
    aliases = {**HEADER_ALIASES, **(column_aliases or {})}
    header = [aliases.get(h.strip(), h.strip()) for h in next((r for r in rd if any(c.strip() for c in r)), [])]

    def col(role):
        return next((header.index(n) for n in STATION_COLS[role] if n in header), None)
    ic, ik, ie, iv, ip = (col(k) for k in ("code", "kalpi", "elig", "voters", "pct"))
    if ic is None or ik is None or (iv is None and (ip is None or ie is None)):
        raise ValueError(f"unknown columns: {header[:12]}")
    rows, excluded = [], collections.Counter()
    for rec in rd:
        if not any(c.strip() for c in rec):
            continue
        try:
            code, kalpi = int(float(rec[ic])), rec[ik].strip()
            e = _cell(rec, ie)
            elig = int(e) if e is not None else None
            if iv is not None:
                v = _cell(rec, iv)
                voters = int(v) if v is not None else None
            else:                                  # a turnout percentage only
                p = _cell(rec, ip)
                voters = round(p / 100 * elig) if (p is not None and elig) else None
        except (ValueError, IndexError):
            excluded["unreadable"] += 1
            continue
        if elig and voters and voters > elig * 1.02:
            excluded["more voters than eligible"] += 1
            continue
        rows.append({"code": code, "kalpi": kalpi, "elig": elig, "voters": voters})
    return rows, excluded


def station_turnout(E, rows, excluded=None):
    """Per-station turnout rows (station_rows) -> turnout by sector and by 2022 vote. For every sector:
      turnout  = voters so far / eligible, over the stations in the release;
      ratio    = that turnout / the national turnout of the same release;
      pace     = voters so far / the same stations' final voters in 2022.
    The lean-weighted signal weights each station's pace by its 2022 votes for each bloc: are the
    stations that voted for the Netanyahu bloc, the Jewish opposition or the Arab lists in 2022
    turning out faster or slower than then? Stations that cannot be matched to 2022 or whose pace
    is implausible (>2.0, usually a renumbered station) are left out of pace and counted.
    A station with a blank figure or 0 voters has not reported yet: it is left out of every sum, the national
    turnout's numerator and denominator included (arab_turnout's rule, so the "national" returned here is
    the figure arab_section computes from the same rows), and counted under "no figure" / "zero voters"."""
    agg = collections.defaultdict(lambda: {"elig": 0, "voters": 0, "stations": 0, "now": 0, "then": 0})
    lean = collections.defaultdict(lambda: [0.0, 0.0])           # bloc -> [Σ pace×votes22, Σ votes22]
    nat = {"elig": 0, "voters": 0}
    excluded = collections.Counter(excluded or {})
    for r in rows:
        code, kalpi, voters, elig = r["code"], r["kalpi"], r["voters"], r["elig"] or 0
        if not voters or voters < 0:              # not reported yet (no station had 0 voters in 2022)
            excluded["no figure" if voters is None else "zero voters"] += 1
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


_arab_base = {}


def _rnd(x, n):
    return round(x, n) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def history_entry(sec, released):
    """The compact turnout.json arab_history record of one release: arab_turnout.history_entry (released, as_of,
    national, total turnout / pace / projected_final, groups and regions: turnout and pace) when the module has
    it, plus "kinds" {kind: {turnout, pace}} (the Druze panel) and "localities" {key: [turnout, pace]} (the
    page's change since the previous release), rounded as in the section (turnout 4 places, pace 3), so a reader
    who opens the page late still sees the day's earlier releases."""
    def tp(d):
        return {"turnout": _rnd((d or {}).get("turnout"), 4), "pace": _rnd((d or {}).get("pace"), 3)}
    if hasattr(AT, "history_entry"):
        entry = dict(AT.history_entry(sec))
    else:
        entry = {"released": sec.get("released"), "total": tp(sec.get("total")),
                 "groups": {k: tp(v) for k, v in (sec.get("groups") or {}).items()},
                 "regions": {k: tp(v) for k, v in (sec.get("regions") or {}).items()}}
    entry["released"] = entry.get("released") or released
    entry["kinds"] = {k: tp(v) for k, v in (sec.get("kinds") or {}).items()}
    entry["localities"] = {str(x["key"]): [_rnd(x.get("turnout"), 4), _rnd(x.get("pace"), 3)]
                           for x in sec.get("localities") or [] if isinstance(x, dict) and x.get("key") is not None}
    return entry


def arab_pass(rows, national, released, sha, doc, old, state, errors):
    """The Arab-society section (pipeline/arab_turnout.py; ARCH_V3 §2): the official per-station turnout
    by locality, by the list that led there in 2022 (Ra'am / Joint List), by region and by kind, shown
    during voting hours too. It carries no party votes, seats or threshold figures. turnout.json gets
    "arab" (this release, with "seen_he": when the feed first saw its file) and "arab_history" (one
    compact entry per release, history_entry, the last 8, kept in state with the file's SHA-256 so a
    relabelled release replaces its entry). A missing module or base file skips the section; a failure
    keeps the last one and is reported."""
    if AT is None or not os.path.exists(ARAB_BASE):
        if AT_ERR:
            errors.append(f"arab: {AT_ERR}"[:200])
        return
    try:
        if "base" not in _arab_base:
            _arab_base["base"] = json.load(open(ARAB_BASE, encoding="utf-8"))
        sec = AT.arab_section(rows, _arab_base["base"], national_turnout=national, released=released)
        entry = history_entry(sec, released)
    except Exception as exc:
        errors.append(f"arab: {exc.__class__.__name__}: {exc}"[:200])
        doc.update({k: old[k] for k in ("arab", "arab_history") if k in old})
        return
    if state.get("station_seen_at"):
        # the clock time, fixed when the file was first seen (he_time would add a date at midnight and rewrite
        # turnout.json with nothing new); a date only for a file first seen on a later day than its release's (R5)
        at = dt.datetime.fromisoformat(state["station_seen_at"]).astimezone(IL)
        later = state.get("station_day") and at.date().isoformat() != state["station_day"]
        sec["seen_he"] = at.strftime("%H:%M") + (at.strftime(" (%d.%m)") if later else "")
    entry["sha"] = sha[:12]
    hist = [h for h in state.get("arab_history") or [] if isinstance(h, dict)]
    # the same file again (relabelled by sectors_time) or another file with the same time (a corrected file):
    # this entry takes the first one's place and the others go, so a time appears once
    same = [i for i, h in enumerate(hist) if h.get("sha") == entry["sha"] or h.get("released") == entry["released"]]
    if same:
        hist[same[0]] = entry
        hist = [h for i, h in enumerate(hist) if i not in same[1:]]
    else:
        hist.append(entry)
    state["arab_history"] = hist[-ARAB_HISTORY:]
    doc["arab"] = sec
    doc["arab_history"] = [{k: v for k, v in h.items() if k != "sha"} for h in state["arab_history"]]


# ------------------------------------------------------------------ exit polls
def exit_polls_pass(out, election_day, state, status, inputs):
    """Publish live_input/exit_polls.json after the polls close; remove the published copy when
    the input is deleted or emptied (a retraction), and never show one before 22:00."""
    closed = now_il() >= closing(election_day)
    try:
        ep = read_input(inputs, "exit_polls.json")
        state["exit_input"] = ep if closed else None    # live/state.json is public: nothing before 22:00
    except Exception as exc:
        status["errors"].append(f"exit polls: {exc.__class__.__name__}: {exc}"[:200])
        ep = state.get("exit_input")              # OPS-10: the last valid copy
    if ep and closed:
        gaps = disclosure_gaps(ep)
        if gaps:
            status["errors"].append(("exit polls: disclosure items missing (§16ה(ב)–(ג): fill them from the channel's "
                                     f"disclosure or write לא פורסם): {'; '.join(gaps)}")[:300])
        write_json(out, "exit_polls.json", ep)
        return True
    remove_json(out, "exit_polls.json")           # OPS-14, and never before polls close (Elections Law)
    return False


# §16ה(ב)–(ג): what whoever publishes a poll within 24 hours of its release must give with it (live_input/README.md)
DISCLOSURE = ("commissioner", "pollster", "date", "population", "n_invited", "n", "moe", "questions")


def disclosure_gaps(ep):
    """Exit polls without one of the DISCLOSURE items (absent, empty or null; 'לא פורסם' counts as given, the page
    shows it as such): ["כאן 11: population, questions", ...]."""
    out = []
    for p in (ep.get("polls") if isinstance(ep, dict) else None) or []:
        if isinstance(p, dict):
            gap = [k for k in DISCLOSURE if p.get(k) is None or str(p.get(k)).strip() == ""]
            if gap:
                out.append(f"{p.get('outlet') or '?'}: {', '.join(gap)}")
    return out


# ------------------------------------------------------------------ publishing (the workflow and the laptop)
# Two paths, picked from the Pages build_type (ARCH_V3 §1):
#   branch   Pages "Deploy from a branch: main / (root)" (build_type legacy, the owner's setting): out/*.json ->
#            site/live/ on main, then a Pages build is requested (POST /pages/builds). Branch builds have a soft
#            limit of 10 an hour and the operator's pushes to main count too, so this happens at most once every
#            publish_every_min minutes (live_config.json, default 8); the first results.json and the first
#            exit_polls.json go out at once. A feed with nothing new but timestamps (status.json's heartbeat, the
#            probe's time, state.json) costs a build only every quiet_every minutes (30; 60 from noon the day after
#            the election), and status.heartbeat_s says so, so the page's stale note stays quiet in between (R3).
#   actions  Pages "GitHub Actions" (build_type workflow): out/*.json -> live/ on the live-data branch, then
#            pages.yml is dispatched (no build limit), after every changed pass.
# Both use the same reset cycle: fetch, reset --hard to the remote tip, copy, commit only the live folder,
# push; never rebase, so a rejected push is simply repeated and nothing can wedge. The feed owns the live
# folder alone; whatever else lands on main in between (the operator's inputs, code) is kept as it is.
TARGET = {"branch": "site/live", "actions": "live"}
PUB = ".publish.json"            # the publisher's cadence state, in the out folder (a dotfile: never published)
URGENT = ("results.json", "exit_polls.json")   # the first one of each is published at once
PUBLISH_EVERY = 8                # minutes between publishes in branch mode (live_config.json publish_every_min)
BUILD_GAP = 50                   # seconds between build requests (a failed one is retried after this)
DISPATCH_TOO = False             # branch mode with an unknown Pages source: also dispatch pages.yml (request_build)
PLACEHOLDER = {"phase": "pre", "has_results": False, "has_turnout": False, "exit_polls": False,
               "results_state": "before-22", "errors": [],
               "note": "Placeholder until election day; pipeline/live_fetch.py replaces it (site/live/ on main in "
                       "branch mode, live/ on the live-data branch in Actions mode)."}


def git(*args, cwd=ROOT, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[:200]}")
    return r


def publish_every(cfg, errors=None):
    """publish_every_min from the config: minutes between publishes in branch mode (1-60, default 8)."""
    v = cfg.get("publish_every_min")
    if v is None:
        return PUBLISH_EVERY
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 1 <= v <= 60:
        return v
    if errors is not None:
        errors.append(f"config: publish_every_min {v!r} is not a number of minutes 1-60; using {PUBLISH_EVERY}")
    return PUBLISH_EVERY


def quiet_every(every, now, election_day):
    """Minutes between branch-mode publishes when nothing but timestamps changed (R3): QUIET_EVERY, or twice the
    cadence when that is longer; from noon the day after the election, when the regular count is over and the page
    no longer warns about a stale feed, QUIET_AFTER (WF-9). status.heartbeat_s is this, in seconds."""
    q = max(QUIET_EVERY, 2 * every)
    if now >= closing(election_day) + dt.timedelta(hours=14):
        q = max(q, QUIET_AFTER)
    return q


def _quiet(o):
    """A published file without what changes on every pass: the timestamps (_strip) and the probe's time."""
    if isinstance(o, dict):
        return {k: _quiet(v) for k, v in o.items() if k not in ("updated_at", "updated_he", "checked_he", "at_he")}
    if isinstance(o, list):
        return [_quiet(x) for x in o]
    return o


def pending(out, live):
    """(news, any): the out/*.json files that differ from the published copies in live/ beyond timestamps (or were
    added or removed), and whether any file differs at all. state.json never counts as news: the page does not
    read it, and its own changes (probe times, the inputs' last valid copies) come with the files that matter."""
    names = {os.path.basename(p) for p in glob.glob(os.path.join(out, "*.json")) + glob.glob(os.path.join(live, "*.json"))}
    news, differ = [], False
    for n in sorted(names):
        a, b = os.path.join(out, n), os.path.join(live, n)
        if os.path.exists(a) and os.path.exists(b):
            with open(a, "rb") as f1, open(b, "rb") as f2:
                if f1.read() == f2.read():
                    continue
        differ = True
        both = os.path.exists(a) and os.path.exists(b)
        if n != STATE and not (both and _quiet(read_json(a, object())) == _quiet(read_json(b, object()))):
            news.append(n)                    # (a file that does not parse never equals anything)
    return news, differ


def worktree(mode, wt, branch, repo=ROOT):
    """A detached worktree of origin/<branch> at wt, created on first use; the live-data branch is created
    as an orphan holding only live/ with the placeholder status."""
    ref = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
    if os.path.exists(os.path.join(wt, ".git")):
        return
    shutil.rmtree(wt, ignore_errors=True)
    git("worktree", "prune", cwd=repo, check=False)       # a stale registration from a deleted folder (OPS-5)
    if git("fetch", "-q", "origin", ref, cwd=repo, check=False).returncode == 0:
        git("worktree", "add", "-q", "--detach", wt, f"origin/{branch}", cwd=repo)
        return
    if mode == "branch":
        raise RuntimeError(f"cannot fetch origin/{branch}")
    git("worktree", "add", "-q", "--detach", wt, cwd=repo)
    git("checkout", "-q", "--orphan", f"{branch}-{int(time.time())}", cwd=wt)
    git("rm", "-rfq", "--cached", ".", cwd=wt)
    for name in os.listdir(wt):
        if name != ".git":
            (shutil.rmtree if os.path.isdir(os.path.join(wt, name)) else os.remove)(os.path.join(wt, name))
    os.makedirs(os.path.join(wt, "live"))
    with open(os.path.join(wt, "live", "status.json"), "w", encoding="utf-8") as f:
        json.dump(PLACEHOLDER, f, ensure_ascii=False, separators=(",", ":"))
    git("add", "-A", cwd=wt)
    git("commit", "-q", "-m", "live-data: placeholder", cwd=wt)
    git("push", "-q", "origin", f"HEAD:{branch}", cwd=wt, check=False)   # someone created it first: the cycle takes theirs
    git("checkout", "-q", "--detach", cwd=wt)


def sync(wt, branch):
    """The worktree at the remote tip of branch (False when the fetch failed)."""
    if git("fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}", cwd=wt, check=False).returncode:
        return False
    git("reset", "-q", "--hard", f"origin/{branch}", cwd=wt)
    return True


def publish(out, mode="branch", wt=None, repo=ROOT, branch=None, who=""):
    """Copy out/*.json into the live folder of the target branch and push (the reset cycle above). Only
    that folder is ever committed. Returns ("pushed" | "unchanged" | "push failed", the commit at the tip)."""
    branch = branch or ("live-data" if mode == "actions" else "main")
    wt = wt or os.path.join(repo, ".live-data" if mode == "actions" else ".live-main")
    sub = TARGET[mode]
    worktree(mode, wt, branch, repo)
    for attempt in range(5):
        sync(wt, branch)
        live = os.path.join(wt, sub)
        os.makedirs(live, exist_ok=True)
        for p in glob.glob(os.path.join(live, "*.json")):
            os.remove(p)
        for p in glob.glob(os.path.join(out, "*.json")):
            shutil.copy(p, live)
        if not git("status", "--porcelain", "--", sub, cwd=wt).stdout.strip():
            return "unchanged", git("rev-parse", "HEAD", cwd=wt).stdout.strip()
        git("add", "-A", "--", sub, cwd=wt)
        git("commit", "-q", "-m", f"live {now_il().strftime('%H:%M')}{who}", cwd=wt)
        if git("push", "-q", "origin", f"HEAD:{branch}", cwd=wt, check=False).returncode == 0:
            return "pushed", git("rev-parse", "HEAD", cwd=wt).stdout.strip()
        time.sleep(3 + 2 * attempt)               # someone else pushed in between: fetch, reset and copy again
    # the worktree back to what is really published, so the next pass sees a first results / exit polls file as
    # still unpublished and retries it at once instead of waiting for the cadence
    git("reset", "-q", "--hard", f"origin/{branch}", cwd=wt, check=False)
    return "push failed", None


def api(method, path, body=None):
    """A GitHub REST call: with $GH_TOKEN / $GITHUB_TOKEN (the workflows; a laptop with a token), else through
    the gh CLI when it is logged in. Returns (HTTP status, parsed JSON or None); 0 = the call could not be made."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req = urllib.request.Request(
            os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/") + path, method=method,
            data=json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "User-Agent": UA, "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw.strip() else None)
        except urllib.error.HTTPError as exc:
            return exc.code, None
        except Exception:
            return 0, None
    if shutil.which("gh"):
        r = subprocess.run(["gh", "api", "-X", method, path.lstrip("/")] + (["--input", "-"] if body is not None else []),
                           input=json.dumps(body) if body is not None else None, capture_output=True, text=True)
        if r.returncode == 0:
            try:
                return 200, (json.loads(r.stdout) if r.stdout.strip() else None)
            except ValueError:
                return 200, None
        m = re.search(r"HTTP (\d{3})", r.stderr)
        return (int(m.group(1)) if m else 0), None
    return 0, None


def origin_repo(repo=ROOT):
    r = git("remote", "get-url", "origin", cwd=repo, check=False)
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?$", r.stdout.strip())
    return m.group(1) if m else ""


def repo_slug(repo=ROOT):
    return os.environ.get("GITHUB_REPOSITORY") or origin_repo(repo)


def pages_source(repo=ROOT):
    """(build_type, source branch) of the repository's Pages site: ("legacy", "main") for "Deploy from a
    branch", ("workflow", None) for GitHub Actions, (None, None) when it cannot be read."""
    code, d = api("GET", f"/repos/{repo_slug(repo)}/pages")
    if code != 200 or not isinstance(d, dict):
        return None, None
    return d.get("build_type"), (d.get("source") or {}).get("branch")


def request_build(mode, sha=None, ref="main", repo=ROOT):
    """Have the page rebuilt after a push. Branch mode: POST /pages/builds (pushes made with GITHUB_TOKEN
    are documented as not starting a Pages build), unless the push already started one for this commit
    (a laptop pushing with its own credentials does), so no build is spent twice. Actions mode: dispatch
    pages.yml on ref. Returns (ok, label)."""
    slug = repo_slug(repo)
    if not slug:
        return False, "no repository to ask (set GITHUB_REPOSITORY)"
    if mode == "actions":
        code, _ = api("POST", f"/repos/{slug}/actions/workflows/pages.yml/dispatches", {"ref": ref})
        return code in (200, 204), (f"pages.yml dispatched on {ref}" if code in (200, 204) else f"dispatch failed ({code})")
    ok, label = False, ""
    if sha:
        time.sleep(float(os.environ.get("LIVE_BUILD_WAIT", "15")))   # give a push-started build time to show up
        code, d = api("GET", f"/repos/{slug}/pages/builds/latest")
        if code == 200 and isinstance(d, dict) and d.get("commit") == sha:
            ok, label = True, f"Pages build started by the push ({d.get('status')})"
    if not ok:
        code, d = api("POST", f"/repos/{slug}/pages/builds")
        ok = code in (200, 201)
        label = f"Pages build requested ({(d or {}).get('status', code)})" if ok else f"Pages build request failed ({code})"
    if DISPATCH_TOO:                      # the Pages source is unknown: under Actions, pages.yml deploys main's site/live/
        d_ok, d_label = request_build("actions", ref=ref, repo=repo)
        ok, label = ok or d_ok, f"{label}; {d_label}"
    return ok, label


def publish_step(out, mode, every_min, wt, branch, ref="main", repo=ROOT, now_publish=False, who="", now=None,
                 quiet_min=None):
    """After a pass: publish out/*.json when due (above) and have the page rebuilt. In branch mode a change a reader
    sees is due every_min minutes after the last publish, one in timestamps only quiet_min minutes after it (default
    quiet_every's: 30); the first results / exit polls at once. now_publish (the end of a run, a reset, Ctrl-C)
    publishes what is held at once, except timestamps alone before quiet_min: the next run takes them up, and
    publishing them would only spend a build (R2). A failed build request is retried after BUILD_GAP seconds, up
    to five times. Returns the fields for the status line: published, next_publish_s, build."""
    now = time.time() if now is None else now
    quiet_min = max(QUIET_EVERY, 2 * every_min) if quiet_min is None else quiet_min
    pp = os.path.join(out, PUB)
    p = read_json(pp, {}) or {}
    if CHANGED:
        p["dirty"] = True
    res = {}
    try:                                          # the state is saved even when a git or API call raises
        if p.get("dirty"):
            live = os.path.join(wt, TARGET[mode])
            first = [n for n in URGENT if os.path.exists(os.path.join(out, n)) and not os.path.exists(os.path.join(live, n))]
            news, differ = pending(out, live) if os.path.isdir(live) else (["(nothing published yet)"], True)
            gap = (every_min if news else quiet_min) * 60 if mode == "branch" else 0
            wait = gap - (now - p.get("last", 0))
            if not differ:
                res["published"], p["dirty"] = "unchanged", False
            elif first or wait <= 0 or (now_publish and news):
                r, sha = publish(out, mode, wt, repo, branch, who)
                res["published"] = r + (f" ({', '.join(first)}: first, at once)" if first and r == "pushed" else "")
                if r == "pushed":
                    p.update(dirty=False, last=now, build=sha, build_fails=0)
                elif r == "unchanged":
                    p["dirty"] = False
            else:
                res["published"], res["next_publish_s"] = ("held" if news else "held (timestamps only)"), int(wait)
        # a one-shot call (the flush at the end of a run, a reset) asks at once: nothing would retry it later
        if p.get("build") and (now_publish or now - p.get("last_build", 0) >= BUILD_GAP):
            ok, res["build"] = request_build(mode, p["build"], ref, repo)
            p["last_build"] = now
            if ok:
                p.update(build=None, build_fails=0)
            else:
                p["build_fails"] = p.get("build_fails", 0) + 1
                if p["build_fails"] >= 5:      # stop asking until the next publish; the push itself may have built
                    p["build"] = None
                    res["build"] += "; five failures in a row, giving up until the next publish"
    finally:
        with open(pp, "w", encoding="utf-8") as f:
            json.dump(p, f)
    return res


def last_published(wt, mode):
    """When the live folder was last published: the time of the newest feed commit ("live HH:MM") that touched it,
    else (a shallow clone may not hold that commit) the published status's updated_at, else 0."""
    r = git("log", "-1", "--format=%ct", "--grep=^live ", "--", TARGET[mode], cwd=wt, check=False)
    if r.returncode == 0 and r.stdout.strip().isdigit():
        return int(r.stdout.strip())
    st = read_json(os.path.join(wt, TARGET[mode], "status.json"), {}) or {}
    try:
        return dt.datetime.fromisoformat(st["updated_at"]).timestamp()
    except Exception:
        return 0


def seed(out, mode, wt, branch, repo=ROOT, drill=False):
    """Start of a workflow run: the worktree of the target branch at its tip, and the out folder seeded
    from the published files (history, last good copies, state), except a rehearsal's (OPS-3): a real run
    never inherits a drill, and a new drill starts clean. The publisher's cadence carries over (R2): the
    last publish is the newest feed commit, so a new run does not publish on its first pass. A drill is
    refused while the published files are the real election's (WF-2): it would overwrite them, and its
    reset at the end would delete them."""
    worktree(mode, wt, branch, repo)
    sync(wt, branch)
    live = os.path.join(wt, TARGET[mode])
    os.makedirs(out, exist_ok=True)
    st = read_json(os.path.join(live, "status.json"), {}) or {}
    st = st if isinstance(st, dict) else {}
    if drill and not st.get("drill") and (st.get("has_results") or st.get("phase") in ("day", "night")):
        raise SystemExit(f"refused: {TARGET[mode]}/ on {branch} holds the real election's files (phase {st.get('phase')}, "
                         f"has_results {st.get('has_results')}); a drill would overwrite them and its reset delete them")
    with open(os.path.join(out, PUB), "w", encoding="utf-8") as f:
        json.dump({"dirty": False, "last": last_published(wt, mode)}, f)
    if st.get("drill"):
        return {"seeded": [], "note": "the published files are a rehearsal's: starting clean"}
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(live, "*.json")))
    for n in names:
        shutil.copy(os.path.join(live, n), out)
    return {"seeded": names}


def reset_out(out):
    """The out folder back to the placeholder status alone (after a drill, or to start over); the next
    publish removes everything else from the live folder."""
    for p in glob.glob(os.path.join(out, "*.json")):
        if os.path.basename(p) != "status.json":
            remove_json(out, os.path.basename(p))
    for name in (RESULTS_CACHE, ".drill_source.csv"):
        if os.path.exists(os.path.join(out, name)):
            os.remove(os.path.join(out, name))
    write_json(out, "status.json", PLACEHOLDER)


def refresh_inputs(ref="main", repo=ROOT):
    """Laptop mode (DOC-2): the manual inputs and the config are edited on GitHub, so before every
    pass take live_input/ and pipeline/live_config.json from origin/<ref>, as the workflow does;
    --no-overlay also removes a file deleted there (OPS-14). Local edits of those files are lost."""
    git("fetch", "-q", "origin", ref, cwd=repo)
    git("checkout", "-q", "--no-overlay", f"origin/{ref}", "--", "live_input", "pipeline/live_config.json", cwd=repo)


# ------------------------------------------------------------------ main
def load_config(path, state, errors):
    """The config, or the last valid copy when it does not parse (OPS-10); an election_day or
    eligible that does not parse falls back to the default and is reported (WF-2)."""
    try:
        cfg = json.load(open(path, encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("not a JSON object")
    except Exception as exc:
        errors.append(f"config: {exc.__class__.__name__}: {exc}"[:200])
        return state.get("config") or dict(DEFAULT_CFG)
    try:
        dt.date.fromisoformat(str(cfg.get("election_day") or ""))
    except ValueError:
        errors.append(f"config: election_day {cfg.get('election_day')!r} is not YYYY-MM-DD; using {DEFAULT_CFG['election_day']}")
        cfg["election_day"] = DEFAULT_CFG["election_day"]
    e = cfg.get("eligible")
    if e is not None and not (isinstance(e, (int, float)) and not isinstance(e, bool) and e > 0):
        errors.append(f"config: eligible {e!r} is not a number; using the 2022 register x 1.081")
        cfg["eligible"] = None
    state["config"] = cfg
    return cfg


def drill_refused(cfg, minutes, start=None):
    """WF-2: why a drill that publishes may not run now ('' when it may). A drill puts a rehearsal projection on the
    public page and its reset puts the placeholder back: not when it would still run (plus 15 minutes for the reset
    and the build) at the start of the poll ban (three days before election day, 00:00), and not from then until ten
    days after election day (6.11, after the final file), when the real night's files are on main. start: when the
    drill began (state drill_start, a Unix time), else now. live.yml's guard applies the same rule."""
    ed = dt.date.fromisoformat(cfg.get("election_day") or DEFAULT_CFG["election_day"])
    ban = dt.datetime.combine(ed - dt.timedelta(days=3), dt.time(0, 0), IL)
    back = dt.datetime.combine(ed + dt.timedelta(days=10), dt.time(0, 0), IL)
    now = now_il()
    began = dt.datetime.fromtimestamp(start, IL) if start else now
    end = max(began + dt.timedelta(minutes=minutes or 0), now) + dt.timedelta(minutes=15)
    if end >= ban and now < back:
        return (f"no drill that runs into {ban:%d.%m %H:%M} Israel time (the poll ban), nor from then until "
                f"{back:%d.%m}: the page would show a rehearsal projection, and its reset would delete the real files")
    return ""


def publish_target(a, errors):
    """(mode, branch, worktree) for --publish and the one-shot actions. --mode auto reads the Pages
    build_type: legacy -> branch (site/live/ on the branch Pages deploys), workflow -> actions (live-data);
    unknown -> branch plus a dispatch of pages.yml after each publish, which reaches the page under both
    settings (under Actions pages.yml deploys the newer of main's site/live/ and live-data), with a warning."""
    global DISPATCH_TOO
    mode, branch = a.mode, a.branch
    DISPATCH_TOO = os.environ.get("PAGES_SOURCE") == "error"      # the workflow's own check failed
    if mode == "auto":
        bt, src_branch = pages_source(a.repo)
        mode = "actions" if bt == "workflow" else "branch"
        branch = branch or src_branch
        if bt not in ("workflow", "legacy"):
            DISPATCH_TOO = True
            errors.append("publish: the Pages source could not be read (gh or GH_TOKEN with Pages access); publishing "
                          "to site/live/ on main (branch mode) and dispatching pages.yml too")
    branch = "live-data" if mode == "actions" else (branch or "main")   # --branch names the Pages branch only
    wt = os.path.abspath(a.wt or os.path.join(a.repo, ".live-main" if mode == "branch" else ".live-data"))
    return mode, branch, wt


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "live"))
    ap.add_argument("--config", default=os.path.join(ROOT, "pipeline", "live_config.json"))
    ap.add_argument("--inputs", default=os.path.join(ROOT, "live_input"), help="folder of the manual inputs")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=60, help="seconds between passes")
    ap.add_argument("--minutes", type=float, default=None,
                    help="stop after this many minutes (default: run until stopped; a drill reveals 2022 over them, default 15)")
    ap.add_argument("--results-file", default="", help="read results from a local file (testing)")
    ap.add_argument("--as", dest="as_election", default=None, help="treat the file as this past election")
    ap.add_argument("--drill", action="store_true", help="rehearsal on the 2022 file, revealed progressively; every output is marked")
    ap.add_argument("--drill-url", default=DRILL_URL)
    ap.add_argument("--drill-fraction", type=float, default=None, help="drill: reveal this share of 2022 instead of following the clock")
    ap.add_argument("--publish", action="store_true",
                    help="after every pass publish the files and have the page rebuilt (branch mode: site/live/ on main, "
                         "at most every publish_every_min minutes; actions mode: the live-data branch)")
    ap.add_argument("--mode", choices=("auto", "branch", "actions"), default="auto",
                    help="publishing path; auto = from the Pages settings (Deploy from a branch -> branch, GitHub Actions -> actions)")
    ap.add_argument("--branch", default=None, help="branch mode: the branch Pages deploys from (default: from the Pages settings, else main)")
    ap.add_argument("--wt", default=None, help="worktree of the target branch (default .live-main / .live-data in the repository)")
    ap.add_argument("--ref", default="main", help="branch to take the inputs from (laptop) and to dispatch pages.yml on (actions mode)")
    ap.add_argument("--no-refresh", action="store_true",
                    help="--publish: keep the local live_input/ and live_config.json instead of taking them from origin/<ref> every pass")
    ap.add_argument("--seed", action="store_true", help="only prepare the worktree and copy the published files into --out (not a "
                                                        "drill's); with --drill: refused while they are the real election's")
    ap.add_argument("--flush", action="store_true", help="only publish what the cadence held back, now (a change in "
                                                         "timestamps alone waits for its quiet_every gap: the next run takes it)")
    ap.add_argument("--reset-live", action="store_true", help="only put the placeholder back in the published folder and rebuild the page")
    ap.add_argument("--request-build", action="store_true", help="only have the page rebuilt (after another push to main, e.g. the daily update)")
    ap.add_argument("--repo", default=ROOT, help=argparse.SUPPRESS)   # the clone holding the worktree (tests)
    ap.add_argument("--sha", default=None, help="--request-build: the commit just pushed (skips the request when its push started a build)")
    a = ap.parse_args(argv)
    global DRILL
    DRILL = a.drill
    if DRILL and not a.as_election:
        a.as_election = "K25"
    if DRILL and a.minutes is None:
        a.minutes = 15
    os.makedirs(a.out, exist_ok=True)
    state = read_json(os.path.join(a.out, STATE), {}) or {}
    boot_errors = []
    cfg = load_config(a.config, state, boot_errors)
    if DRILL and (a.publish or a.seed):           # WF-2: never into the poll ban or over the real night's files
        why = drill_refused(cfg, a.minutes, state.get("drill_start"))
        if why:
            sys.exit(f"refused: {why}")
    who = "" if os.environ.get("GITHUB_ACTIONS") else " (laptop)"
    pub_errors = []                               # reported once, on the first pass
    if a.publish or a.seed or a.flush or a.reset_live or a.request_build:
        mode, branch, wt = publish_target(a, pub_errors)
        if a.seed or a.flush or a.reset_live or a.request_build:   # one-shot actions: no pass, no model
            if a.seed:
                res = seed(a.out, mode, wt, branch, a.repo, drill=DRILL)
            elif a.request_build:
                ok, label = request_build(mode, a.sha, a.ref, a.repo)
                res = {"ok": ok, "build": label}
            else:
                if a.reset_live:
                    reset_out(a.out)
                every = publish_every(cfg)
                res = publish_step(a.out, mode, every, wt, branch, a.ref, a.repo, now_publish=True, who=who,
                                   quiet_min=quiet_every(every, now_il(), dt.date.fromisoformat(cfg["election_day"])))
            print(json.dumps({"mode": mode, "branch": branch, **res, "errors": boot_errors + pub_errors}, ensure_ascii=False), flush=True)
            return
    else:
        mode = os.environ.get("PUBLISH_MODE") or None   # the workflow's unpublished probe pass reports it too
    E = Election2026(cfg, a.as_election)
    hist_path = os.path.join(a.out, "history.json")
    history = read_json(hist_path, []) if os.path.exists(hist_path) else []
    start = time.time()
    while True:
        CHANGED.clear()
        t = now_il()
        status = {"updated_at": t.isoformat(), "updated_he": he_time(t), "checked_he": he_time(t),
                  "election": E.dry or "K26", "phase": "pre", "has_results": False, "has_turnout": False,
                  "exit_polls": False, "results_state": "waiting", "errors": pub_errors}
        pub_errors = []
        if DRILL:
            status["drill"] = True
        if a.publish and not a.no_refresh:
            try:
                refresh_inputs(a.ref, a.repo)     # DOC-2: edits made on GitHub reach the laptop too
            except Exception as exc:
                status["errors"].append(f"refresh from origin/{a.ref}: {exc}"[:200])
        cfg = E.cfg = load_config(a.config, state, status["errors"])
        every = publish_every(cfg, status["errors"])
        election_day = dt.date.fromisoformat(cfg.get("election_day", DEFAULT_CFG["election_day"]))
        quiet = quiet_every(every, t, election_day)
        # the page's staleness threshold follows heartbeat_s (PAGE-1): in branch mode the longest gap between two
        # publishes of a healthy feed (quiet_every: when nothing but timestamps changed), so its note does not fire
        # in between; otherwise the status re-stamp interval
        status["heartbeat_s"] = round(quiet * 60) if mode == "branch" else HEARTBEAT
        if mode:
            status["publish_mode"] = mode
        src = os.environ.get("PAGES_SOURCE")
        if src and not (src == "legacy" and mode == "branch"):   # legacy is the expected source in branch mode
            status["pages_source"] = src
        E.set_register(cfg)
        if not E.dry and cfg.get("eligible") == PLACEHOLDER_ELIGIBLE and t.date() >= election_day - dt.timedelta(days=2):
            status["errors"].append("eligible in live_config.json is still the estimate 7,340,000: set the register size "
                                    "the CEC published (בעלי זכות בחירה), docs/ELECTION_DAY.md הכנות 2")
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
            switches_pass(E, cfg, a.out, history, state, status)
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
        line = {**status, "changed": list(CHANGED)}
        if a.publish:                             # every pass: a held publish or a failed build request may be due
            try:
                line.update(publish_step(a.out, mode, every, wt, branch, a.ref, a.repo, who=who, quiet_min=quiet))
            except Exception as exc:
                line["errors"] = status["errors"] + [f"publish: {exc}"[:200]]
        print(json.dumps(line, ensure_ascii=False), flush=True)
        if a.once or (a.minutes is not None and (time.time() - start) / 60 > a.minutes):
            break                                 # DOC-1: without --minutes the laptop loop runs until stopped
        try:
            time.sleep(a.loop)
        except KeyboardInterrupt:                 # Ctrl-C on the laptop: publish what the cadence held back, then stop
            if a.publish:
                CHANGED.clear()
                print(json.dumps(publish_step(a.out, mode, every, wt, branch, a.ref, a.repo, now_publish=True, who=who,
                                              quiet_min=quiet)), flush=True)
            break


if __name__ == "__main__":
    main()
