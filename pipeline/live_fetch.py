"""Election day & night fetcher: official CEC files -> live/*.json for the dashboard.

Runs on GitHub Actions (.github/workflows/live.yml) or on any laptop:

    python3 pipeline/live_fetch.py --out live --loop 60          # poll every 60 s
    python3 pipeline/live_fetch.py --out live --once             # one pass
    python3 pipeline/live_fetch.py --out /tmp/live --once --results-file data/official/k25_expb.csv --as K25
                                                                 # dry run on a past election

Inputs
  * Results: the CEC ballot file (expb.csv) at the URL in pipeline/live_config.json. On election
    night it grows as polling stations are counted; double envelopes come last.
  * Turnout during the day: the CEC national hourly figures and, if the CEC publishes them as
    announced (ruling of 16.8.2026), per-station turnout. National figures are typed into
    live_input/turnout.json (the CEC releases them as statements, not files) or scraped when a
    URL is configured.
  * Exit polls: live_input/exit_polls.json, published only after polls close (22:00).

Outputs (next to the page on GitHub Pages)
  live/results.json   counted totals + projection frame (pipeline/live_model.make_frame)
  live/turnout.json   national hourly series, sector turnout from per-station data
  live/exit_polls.json, live/status.json, live/history.json (projection over the night)

Every download is checked: HTML instead of CSV (maintenance page, WAF) is rejected, rows with
more voters than eligible voters are dropped and counted, and the SHA-256 of each accepted
file is recorded in status.json.
"""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_model as LM  # noqa: E402
from build_data import load_election, read_expb  # noqa: E402

ROOT = LM.ROOT
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live"
IL = dt.timezone(dt.timedelta(hours=2))          # Israel Standard Time from 25.10.2026
AGREEMENTS_2026 = [("Likud", "Religious Zionism"), ("Yashar", "The Democrats"), ("Together", "Yisrael Beiteinu"),
                   ("Ra'am", "Joint List")]


def now_il():
    return dt.datetime.now(dt.timezone.utc).astimezone(IL)


def he_time(t):
    return t.strftime("%H:%M") + (" (" + t.strftime("%d.%m") + ")" if t.date() != now_il().date() else "")


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if "maintenance" in r.geturl():
            raise IOError(f"redirected to {r.geturl()}")
        data = r.read()
    head = data[:200].lstrip().lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        raise IOError("got an HTML page instead of a data file")
    return data


DRILL = False


def write_json(out, name, obj):
    if DRILL and isinstance(obj, dict):
        obj = {**obj, "drill": True}
    os.makedirs(out, exist_ok=True)
    tmp = os.path.join(out, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, os.path.join(out, name))


def read_input(name):
    p = os.path.join(ROOT, "live_input", name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


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


def poll_prior(polls, half_life=10.0, window=28):
    """Recency-weighted average of the 2026 polls (seats) -> national vote shares."""
    dates = [dt.date.fromisoformat(p["date"]) for p in polls["polls"]]
    last = max(dates)
    acc, wsum = collections.Counter(), 0.0
    for p, d in zip(polls["polls"], dates):
        age = (last - d).days
        if age > window:
            continue
        w = 0.5 ** (age / half_life)
        wsum += w
        for k, v in p["seats"].items():
            acc[k] += w * v
    avg = {k: v / wsum for k, v in acc.items()}
    for p in polls["parties"]:
        avg.setdefault(p["id"], 0.0)
    return LM.seats_to_shares(avg)


# ------------------------------------------------------------------ results
def results_pass(E, data, out, source_url, history):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        cols, rows = read_expb(path)
    finally:
        os.unlink(path)
    # The CEC file was briefly empty during the 2020 and 2021 counts. Rows only ever get added,
    # so an empty or shrunken file is rejected and the last good results stay published.
    state_p = os.path.join(out, ".state.json")
    state = json.load(open(state_p)) if os.path.exists(state_p) else {}
    n_counted = sum(1 for r in rows if r["voters"])
    if n_counted == 0 and state.get("rows", 0) > 0:
        raise IOError("empty results file; keeping the last good snapshot")
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
    prev = set(map(tuple, state.get("stations", [])))
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
    t = now_il()
    history.append({"t": t.strftime("%H:%M"), "counted": frame["counted"]["share"],
                    "coal": frame["blocs"]["coal"]["seats"], "coal_lo": frame["blocs"]["coal"]["lo"],
                    "coal_hi": frame["blocs"]["coal"]["hi"], "p61": frame["blocs"]["coal"]["p61"]})
    write_json(out, "results.json", {
        "election": E.dry or "K26", "updated_at": t.isoformat(), "updated_he": he_time(t),
        "source_url": source_url, "source_label": "ועדת הבחירות המרכזית · expb.csv",
        "frame": frame, "accuracy": replay_accuracy(), "history": history[-240:],
        "checks": {"rows": len(rows), "dropped_impossible": dropped, "unknown_lists": unknown,
                   "sha256": hashlib.sha256(data).hexdigest()},
    })
    write_json(out, "history.json", history[-240:])
    with open(state_p, "w") as f:
        json.dump({"rows": n_counted, "sha256": hashlib.sha256(data).hexdigest(), "at": t.isoformat(),
                   "stations": sorted([list(k) for k in stations], key=str)}, f)
    return frame


def replay_accuracy():
    p = os.path.join(ROOT, "site", "data", "replay_night.json")
    try:
        return json.load(open(p, encoding="utf-8")).get("accuracy")
    except Exception:
        return None


# ------------------------------------------------------------------ turnout
def turnout_pass(E, cfg, out):
    manual = read_input("turnout.json") or {}
    national = dict(manual.get("national", {}))
    doc = {"updated_at": now_il().isoformat(), "updated_he": he_time(now_il()), "national": national,
           "eligible": E.eligible, "claims": manual.get("claims", []), "source": manual.get("source", "")}
    url = cfg.get("station_turnout_url")
    if url:
        try:
            data = fetch(url)
            st = station_turnout(E, data)
            if st["sectors"]:
                doc.update({"sectors": st["sectors"], "lean": st["lean"], "stations_national": st["national"],
                            "sectors_time": manual.get("sectors_time", "") or now_il().strftime("%H:%M"),
                            "sectors_coverage": st["coverage"], "sectors_excluded": st["excluded"],
                            "sectors_sha256": hashlib.sha256(data).hexdigest()})
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


# ------------------------------------------------------------------ publishing from a laptop
def publish(out):
    """Copy live/*.json into a gh-pages worktree (.live-pages) and push it: the laptop fallback
    when GitHub's runners cannot reach the CEC. Needs push rights to the repository."""
    import shutil
    import subprocess
    wt = os.path.join(ROOT, ".live-pages")
    git = lambda *a, cwd=ROOT: subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    if not os.path.exists(wt):
        git("fetch", "-q", "origin", "gh-pages")
        r = git("worktree", "add", "-B", "gh-pages-live", wt, "origin/gh-pages")
        if r.returncode:
            raise RuntimeError(r.stderr.strip()[:200])
    os.makedirs(os.path.join(wt, "live"), exist_ok=True)
    for name in os.listdir(out):
        if name.endswith(".json"):
            shutil.copy(os.path.join(out, name), os.path.join(wt, "live", name))
    git("add", "live", cwd=wt)
    if not git("status", "--porcelain", cwd=wt).stdout.strip():
        return "unchanged"
    git("commit", "-q", "-m", f"live {now_il().strftime('%H:%M')} (laptop)", cwd=wt)
    for _ in range(3):
        git("pull", "-q", "--rebase", "origin", "gh-pages", cwd=wt)
        if git("push", "-q", "origin", "HEAD:gh-pages", cwd=wt).returncode == 0:
            return "pushed"
        time.sleep(5)
    return "push failed"


# ------------------------------------------------------------------ exit polls
def exit_polls_pass(out, election_day):
    ep = read_input("exit_polls.json")
    t = now_il()
    closed = t >= dt.datetime.combine(election_day, dt.time(22, 0), IL)
    if ep and closed:
        write_json(out, "exit_polls.json", ep)
        return True
    return False                                   # never before polls close (Elections Law)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "live"))
    ap.add_argument("--config", default=os.path.join(ROOT, "pipeline", "live_config.json"))
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=60, help="seconds between passes")
    ap.add_argument("--minutes", type=float, default=345, help="stop after this many minutes")
    ap.add_argument("--results-file", default="", help="read results from a local file (testing)")
    ap.add_argument("--as", dest="as_election", default=None, help="treat the file as this past election")
    ap.add_argument("--drill", action="store_true", help="mark every output as a rehearsal (shown as such on the page)")
    ap.add_argument("--publish", action="store_true", help="push live/*.json to the gh-pages branch after every pass (laptop mode)")
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    global DRILL
    DRILL = a.drill
    E = Election2026(cfg, a.as_election)
    election_day = dt.date.fromisoformat(cfg.get("election_day", "2026-10-27"))
    hist_path = os.path.join(a.out, "history.json")
    history = json.load(open(hist_path, encoding="utf-8")) if os.path.exists(hist_path) else []
    last_hash, start = None, time.time()
    while True:
        try:
            E.cfg = json.load(open(a.config, encoding="utf-8"))
        except Exception:
            pass
        has_res = os.path.exists(os.path.join(a.out, "results.json"))
        status = {"updated_at": now_il().isoformat(), "updated_he": he_time(now_il()), "errors": [],
                  "phase": "night" if has_res else "day", "has_results": has_res, "has_turnout": False}
        try:
            td = turnout_pass(E, cfg, a.out)
            status["has_turnout"] = bool(td.get("national") or td.get("sectors"))
        except Exception as exc:
            status["errors"].append(f"turnout: {exc.__class__.__name__}: {exc}"[:200])
        try:
            data = open(a.results_file, "rb").read() if a.results_file else fetch(cfg["results_url"])
            h = hashlib.sha256(data).hexdigest()
            if h != last_hash:
                frame = results_pass(E, data, a.out, a.results_file or cfg["results_url"], history)
                last_hash = h
                status["results"] = {"counted": frame["counted"]["share"], "sha256": h}
            status["results_state"] = "ok"
            status["has_results"] = True
            status["phase"] = "night"
        except Exception as exc:
            status["results_state"] = "waiting"
            status["errors"].append(f"results: {exc.__class__.__name__}: {exc}"[:200])
        try:
            status["exit_polls"] = exit_polls_pass(a.out, election_day)
        except Exception as exc:
            status["errors"].append(f"exit polls: {exc}"[:200])
        write_json(a.out, "status.json", status)
        if a.publish:
            try:
                status["published"] = publish(a.out)
            except Exception as exc:
                status["errors"].append(f"publish: {exc}"[:200])
        print(json.dumps(status, ensure_ascii=False), flush=True)
        if a.once or (time.time() - start) / 60 > a.minutes:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
