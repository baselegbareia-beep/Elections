"""Election-night replays for the dashboard demo, and the projection's track record.

1. 2021, real counting order: snapshots of the official CEC ballot file taken
   during the night of 23–25 March 2021 (git history of sapir/israel-votes24-data;
   the final snapshot is identical to the official file, all 12,926 rows). Each
   snapshot is fed to the projection model (pipeline/live_model.py) with 2020 as
   the baseline and the final-week 2021 poll average as the prior, exactly as on
   27 October 2026 with 2022 as the baseline.
2. 2022, simulated counting order: the official 2022 ballot results in a
   simulated order (smaller localities somewhat earlier); labelled as such.
3. Accuracy: projection error by share counted, from backtests over several
   simulated orders (2022 and 2021) and along the real 2021 order.

Run: python3 pipeline/build_replay.py [--out site/data/replay_night.json]
"""
import argparse
import collections
import datetime as dt
import json
import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_model as LM  # noqa: E402
import registry as R  # noqa: E402
from build_data import load_election, read_expb  # noqa: E402

ROOT = LM.ROOT
STEPS = [0.01, 0.03, 0.06, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
SNAP_DIR = os.path.join(ROOT, "data", "raw", "snapshots", "votes24")
IL = dt.timezone(dt.timedelta(hours=2))      # March 2021, before DST (26.3.2021)

# Exit polls aired at 22:00 (seats). Source: Wikipedia election-day poll rows, as collected in
# idoherling/2026_Election_Model data/processed/polls.csv; checked against two scrapes.
EXIT_POLLS = {
    "K24": {"note": "המדגמים של 22:00 ב-23.3.2021 (מקור: טבלאות הסקרים בוויקיפדיה). כל שלושת הערוצים נתנו לרע״ם 0; היא קיבלה 4.",
            "polls": [
                {"outlet": "כאן 11", "seats": {"מחל": 30, "פה": 18, "שס": 9, "כן": 8, "ב": 7, "אמת": 7, "ג": 7, "ל": 7, "ט": 7, "ודעם": 8, "ת": 6, "מרצ": 6, "עם": 0}},
                {"outlet": "חדשות 12", "seats": {"מחל": 30, "פה": 18, "שס": 9, "כן": 7, "ב": 7, "אמת": 8, "ג": 6, "ל": 7, "ט": 7, "ודעם": 9, "ת": 6, "מרצ": 7, "עם": 0}},
                {"outlet": "חדשות 13", "seats": {"מחל": 32, "פה": 16, "שס": 8, "כן": 8, "ב": 7, "אמת": 7, "ג": 7, "ל": 8, "ט": 7, "ודעם": 8, "ת": 5, "מרצ": 7, "עם": 0}}]},
    "K25": {"note": "המדגמים של 22:00 ב-1.11.2022 (מקור: טבלאות הסקרים בוויקיפדיה). כולם נתנו למרצ 4–5 מנדטים; היא לא עברה את אחוז החסימה.",
            "polls": [
                {"outlet": "כאן 11", "seats": {"מחל": 30, "פה": 22, "ט": 15, "כן": 13, "שס": 10, "ג": 7, "ל": 5, "עם": 5, "ום": 4, "אמת": 5, "מרצ": 4, "ד": 0, "ב": 0}},
                {"outlet": "חדשות 12", "seats": {"מחל": 30, "פה": 24, "ט": 14, "כן": 11, "שס": 10, "ג": 7, "ל": 4, "עם": 5, "ום": 4, "אמת": 6, "מרצ": 5, "ד": 0, "ב": 0}},
                {"outlet": "חדשות 13", "seats": {"מחל": 31, "פה": 24, "ט": 14, "כן": 12, "שס": 10, "ג": 7, "ל": 4, "עם": 5, "ום": 4, "אמת": 5, "מרצ": 4, "ד": 0, "ב": 0}},
                {"outlet": "ערוץ 14", "seats": {"מחל": 31, "פה": 23, "ט": 12, "כן": 11, "שס": 10, "ג": 8, "ל": 6, "עם": 4, "ום": 4, "אמת": 6, "מרצ": 5, "ד": 0, "ב": 0}}]},
}


def setup(core, base_e, cur_e, src):
    (_, base_rows), _ = load_election(src, base_e)
    (_, cur_rows), _ = load_election(src, cur_e)
    B = LM.Baseline(base_e, base_rows, core)
    keep = set(R.PARTIES[cur_e])
    g = sum(r["elig"] for r in cur_rows if not r["env"] and r["code"] is not None) / sum(L["elig"] for L in B.loc.values())
    camp = {p: ("coal" if v[2] == "nb" else "arab" if v[2] == "arab" else "opp") for p, v in R.PARTIES[cur_e].items()}
    proj = LM.Projector(B, list(R.PARTIES[cur_e]), LM.BASE_MAP[cur_e], g, LM.AGREEMENTS[cur_e],
                        prior=LM.final_poll_prior(cur_e), camp=camp)
    el = next(e for e in core["elections"] if e["id"] == cur_e)
    fam = {p["id"]: p["family"] for p in el["parties"]}
    meta = {p: {"name": next(x["name"] for x in el["parties"] if x["id"] == p), "letters": p,
                "color": R.FAMILIES[fam.get(p, "other")]["color"], "dark": R.FAMILIES[fam.get(p, "other")]["dark"],
                "bloc": camp[p]} for p in R.PARTIES[cur_e]}
    official = {p["id"]: p["seats"] for p in el["parties"] if p["id"] in keep}
    return proj, meta, official, keep, cur_rows


def accumulate(rows, keep):
    counted, env = {}, None
    for r in rows:
        if not r["voters"]:
            continue
        if r["env"] or r["code"] is None:
            env = env or LM.new_unit()
            LM.add_row(env, r, keep)
        else:
            LM.add_row(counted.setdefault(r["code"], LM.new_unit()), r, keep)
    return counted, env


def replay_simulated(core, src, n_boot):
    proj, meta, official, keep, cur_rows = setup(core, "K24", "K25", src)
    rng = random.Random(20221101)
    order = LM.counting_order(cur_rows, "small_first", rng, proj.B)
    total = sum(r["elig"] for r in order)
    frames, counted, done, si = [], {}, 0, 0
    for r in order:
        LM.add_row(counted.setdefault(r["code"], LM.new_unit()), r, keep)
        done += r["elig"]
        while si < len(STEPS) and done >= STEPS[si] * total - 1e-6:
            frames.append(LM.make_frame(proj, counted, None, meta, n_boot=n_boot, seed=si))
            frames[-1]["label"] = f"נספרו {round(100 * STEPS[si])}%"
            si += 1
    env = LM.new_unit()
    for r in cur_rows:
        if r["env"] or r["code"] is None:
            LM.add_row(env, r, keep)
    frames.append(LM.make_frame(proj, counted, env, meta, n_boot=n_boot, seed=99, final=official))
    frames[-1]["label"] = "כולל המעטפות הכפולות"
    print(f"2022 simulated: {len(frames)} frames")
    return {"election": "K25", "baseline": "K24", "simulated_order": True,
            "label": "ליל הבחירות 2022 · סדר ספירה מדומה", "frames": frames, "exit_polls": EXIT_POLLS["K25"],
            "note": "תוצאות 2022 הרשמיות ברמת הקלפי, בסדר ספירה מדומה; בסיס 2021; ממוצע הסקרים של השבוע האחרון כנקודת מוצא."}


def snapshot_commits():
    if not os.path.exists(SNAP_DIR):
        return []
    out = subprocess.run(["git", "-C", SNAP_DIR, "log", "--reverse", "--format=%H %aI"], capture_output=True, text=True).stdout
    return [line.split() for line in out.splitlines() if line.strip()]


def replay_real(core, src, n_boot):
    commits = snapshot_commits()
    if not commits:
        print("no 2021 snapshots (run pipeline/fetch_sources.py); skipping the real-order replay")
        return None, []
    proj, meta, official, keep, _ = setup(core, "K23", "K24", src)
    nb = [p for p, v in R.PARTIES["K24"].items() if v[2] == "nb"]
    frames, track = [], []
    for h, when in commits:
        data = subprocess.run(["git", "-C", SNAP_DIR, "show", f"{h}:expb.csv"], capture_output=True).stdout
        if len(data) < 2000:
            continue                                   # empty file early in the night
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            tf.write(data)
            path = tf.name
        try:
            _, rows = read_expb(path)
        finally:
            os.unlink(path)
        counted, env = accumulate(rows, keep)
        last = h == commits[-1][0]
        f = LM.make_frame(proj, counted, env, meta, n_boot=n_boot, seed=len(frames), final=official if last else None)
        t = dt.datetime.fromisoformat(when)            # local Israel time as recorded (DST began 26.3.2021)
        f["label"] = t.strftime("%d.%m %H:%M")
        f["time"] = t.isoformat()
        # how far this snapshot's projection is from the final official seats
        err = sum(abs(l["seats"] - official.get(l["id"], 0)) for l in f["lists"]) / 2
        bloc = sum(l["seats"] for l in f["lists"] if l["id"] in nb) - sum(official.get(p, 0) for p in nb)
        cover = sum(1 for l in f["lists"] if l["lo"] <= official.get(l["id"], 0) <= l["hi"]) / len(f["lists"])
        track.append({"time": f["label"], "counted": f["counted"]["share"], "envelopes": f["counted"]["env_valid"],
                      "seat_err": err, "bloc_err": bloc, "cover80": round(cover, 2)})
        frames.append(f)
        print(f"2021 {f['label']}: counted {f['counted']['share']:.3f}, env {f['counted']['env_valid']}, moved {err}, bloc {bloc:+d}")
    # keep the night readable: every snapshot up to the end of the regular count, then the envelope days sparsely
    keep_idx = [i for i, fr in enumerate(frames) if not fr["counted"]["envelopes"]]
    env_idx = [i for i, fr in enumerate(frames) if fr["counted"]["envelopes"]]
    keep_idx += env_idx[::3] + ([env_idx[-1]] if env_idx and env_idx[-1] not in env_idx[::3] else [])
    frames = [frames[i] for i in sorted(set(keep_idx))]
    return ({"election": "K24", "baseline": "K23", "simulated_order": False,
             "label": "ליל הבחירות 2021 · סדר הספירה האמיתי", "frames": frames, "exit_polls": EXIT_POLLS["K24"],
             "source": "https://github.com/sapir/israel-votes24-data",
             "note": "קובץ הקלפיות הרשמי של ועדת הבחירות כפי שהתעדכן בליל הבחירות 23–25.3.2021 (תיעוד ציבורי של גרסאות הקובץ; הגרסה האחרונה זהה לקובץ הרשמי). בסיס: 2020; נקודת מוצא: ממוצע הסקרים של השבוע האחרון."},
            track)


def backtest_accuracy(core, src, orders):
    accuracy = {}
    for be, ce in (("K24", "K25"), ("K23", "K24")):
        res = LM.backtest(be, ce, src, core, ["random", "locality", "small_first", "arab_haredi_late"],
                          orders, 30, [0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 0.9, 1.0])
        acc = collections.defaultdict(list)
        for r in res:
            acc[r["counted"]].append(r)
        accuracy[ce] = [{"counted": k, "seat_err": round(sum(x["seat_abs_err"] for x in v) / len(v) / 2, 1),
                         "bloc_err": round(sum(abs(x["bloc_err"]) for x in v) / len(v), 1),
                         "cover80": round(sum(x["cover80"] for x in v) / len(v), 2),
                         "bloc_cover80": round(sum(x["bloc_cover"] for x in v) / len(v), 2), "runs": len(v)}
                        for k, v in sorted(acc.items())]
    return accuracy


def main(out, n_boot, orders):
    core = json.load(open(os.path.join(ROOT, "site", "data", "core.json"), encoding="utf-8"))
    src = os.path.join(ROOT, "data", "raw", "mirror")
    real, track = replay_real(core, src, n_boot)
    sim = replay_simulated(core, src, n_boot)
    replays = {"K25": sim}
    if real:
        replays = {"K24": real, "K25": sim}
    doc = {"replays": replays, "default": "K24" if real else "K25",
           "accuracy": backtest_accuracy(core, src, orders), "accuracy_real": track}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "site", "data", "replay_night.json"))
    ap.add_argument("--boot", type=int, default=200)
    ap.add_argument("--orders", type=int, default=4)
    a = ap.parse_args()
    main(a.out, a.boot, a.orders)
