"""Replay of election night 2022 for the dashboard demo.

The official 2022 ballot results (every box) are fed to the projection model
(pipeline/live_model.py) in a SIMULATED counting order, with 2021 as the
baseline and the final-week 2022 poll average as the prior, exactly as the
model will run on 27 October 2026 with 2022 as the baseline. The order of
counting is not public, so it is simulated (smaller localities somewhat
earlier); the page labels the replay as a simulation.

Also stores the backtest accuracy (error by share counted) shown next to the
projection.

Run: python3 pipeline/build_replay.py [--out site/data/replay_night.json]
"""
import argparse
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_model as LM  # noqa: E402
import registry as R  # noqa: E402
from build_data import load_election  # noqa: E402

ROOT = LM.ROOT
STEPS = [0.01, 0.03, 0.06, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def main(out, n_boot, backtest_orders):
    core = json.load(open(os.path.join(ROOT, "site", "data", "core.json"), encoding="utf-8"))
    src = os.path.join(ROOT, "data", "raw", "mirror")
    base_e, cur_e = "K24", "K25"
    (_, base_rows), _ = load_election(src, base_e)
    (_, cur_rows), _ = load_election(src, cur_e)
    B = LM.Baseline(base_e, base_rows, core)
    main_lists = list(R.PARTIES[cur_e])
    keep = set(main_lists)
    g = sum(r["elig"] for r in cur_rows if not r["env"] and r["code"] is not None) / sum(L["elig"] for L in B.loc.values())
    camp = {p: ("coal" if v[2] == "nb" else "arab" if v[2] == "arab" else "opp") for p, v in R.PARTIES[cur_e].items()}
    proj = LM.Projector(B, main_lists, LM.BASE_MAP[cur_e], g, LM.AGREEMENTS[cur_e], prior=LM.final_poll_prior(cur_e), camp=camp)
    el = next(e for e in core["elections"] if e["id"] == cur_e)
    fam = {p["id"]: p["family"] for p in el["parties"]}
    meta = {p: {"name": next(x["name"] for x in el["parties"] if x["id"] == p), "letters": p,
                "color": R.FAMILIES[fam.get(p, "other")]["color"], "dark": R.FAMILIES[fam.get(p, "other")]["dark"],
                "bloc": "coal" if v[2] == "nb" else "arab" if v[2] == "arab" else "opp"}
            for p, v in R.PARTIES[cur_e].items()}
    official = {p["id"]: p["seats"] for p in el["parties"] if p["id"] in keep}
    rng = random.Random(20221101)
    order = LM.counting_order(cur_rows, "small_first", rng, B)
    total = sum(r["elig"] for r in order)
    frames, counted, done, si = [], {}, 0, 0
    for r in order:
        LM.add_row(counted.setdefault(r["code"], LM.new_unit()), r, keep)
        done += r["elig"]
        while si < len(STEPS) and done >= STEPS[si] * total - 1e-6:
            frames.append(LM.make_frame(proj, counted, None, meta, n_boot=n_boot, seed=si))
            print(f"frame {STEPS[si]:.2f}: coal {frames[-1]['blocs']['coal']['seats']}")
            si += 1
    env = LM.new_unit()
    for r in cur_rows:
        if r["env"] or r["code"] is None:
            LM.add_row(env, r, keep)
    frames.append(LM.make_frame(proj, counted, env, meta, n_boot=n_boot, seed=99, final=official))
    # backtest accuracy by share counted, over several simulated orders: 2022 (calm) and 2021 (new lists, splits)
    accuracy = {}
    for be, ce in (("K24", "K25"), ("K23", "K24")):
        res = LM.backtest(be, ce, src, core, ["random", "locality", "small_first", "arab_haredi_late"],
                          backtest_orders, 30, [0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 0.9, 1.0])
        acc = collections.defaultdict(list)
        for r in res:
            acc[r["counted"]].append(r)
        accuracy[ce] = [{"counted": k, "seat_err": round(sum(x["seat_abs_err"] for x in v) / len(v) / 2, 1),
                         "bloc_err": round(sum(abs(x["bloc_err"]) for x in v) / len(v), 1),
                         "cover80": round(sum(x["cover80"] for x in v) / len(v), 2),
                         "bloc_cover80": round(sum(x["bloc_cover"] for x in v) / len(v), 2), "runs": len(v)}
                        for k, v in sorted(acc.items())]
    doc = {"election": cur_e, "baseline": base_e, "simulated_order": True,
           "eligible_expected": round(sum(L["elig"] for L in B.loc.values()) * g),
           "frames": frames, "accuracy": accuracy,
           "note": "תוצאות 2022 הרשמיות ברמת הקלפי, בסדר ספירה מדומה; בסיס 2021; ממוצע הסקרים של השבוע האחרון כנקודת מוצא."}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out}: {len(frames)} frames; accuracy {accuracy}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "site", "data", "replay_night.json"))
    ap.add_argument("--boot", type=int, default=200)
    ap.add_argument("--orders", type=int, default=4)
    a = ap.parse_args()
    main(a.out, a.boot, a.orders)
