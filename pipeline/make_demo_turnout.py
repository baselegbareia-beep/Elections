"""Synthetic per-station turnout releases for the Arab-society section: the page's demo and the tests.

A release at hour h gives every 2022 polling station (site/data/ballots_K25.json, 2022 register) its 2022
final voters x a per-locality level factor x the share of the day's turnout cast by h: the 2022 Arab curve
(arab_day_2022.json "curve") for the stations of the section, the national 2022 curve elsewhere, each
locality shifted by a random timing offset. The level factors average 1, so the demo is shaped like 2022
and is neither a result nor a forecast. Seeded, so the output is the same on every run.

    python3 pipeline/make_demo_turnout.py                 # site/data/arab_day_demo.json (10:00, 14:00, 18:00, 21:00)
    python3 pipeline/make_demo_turnout.py --csv DIR       # also DIR/turnout_HHMM.csv per release (expb.csv layout)
    python3 pipeline/make_demo_turnout.py --csv F.csv [--at 14:00]   # one release in F.csv, nothing else
                                                          # (with --out also the demo JSON there)
    python3 pipeline/make_demo_turnout.py --check         # the unit checks of pipeline/arab_turnout.py
"""
import argparse
import json
import math
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arab_turnout as AT  # noqa: E402
import registry as R  # noqa: E402

ROOT = AT.ROOT
OUT = os.path.join(ROOT, "site", "data", "arab_day_demo.json")
TIMES = ["10:00", "14:00", "18:00", "21:00"]
SEED = 20261027
LEVEL_SD = 0.06          # locality turnout level, log scale
STATION_SD = 0.03        # station level within a locality, log scale
TIMING_SD = 0.35         # locality timing offset, hours
NOTE = ("הדגמה בנתונים מדומים: לא תוצאות ולא תחזית. ארבעה פרסומים מדומים (10:00, 14:00, 18:00 ו-21:00) נבנו "
        "מהמצביעים בכל קלפי ב-2022, לפי קצב ההצבעה המשוער בחברה הערבית ב-2022 ועם רעש אקראי לכל יישוב. ביום "
        "הבחירות יוצגו כאן נתוני ועדת הבחירות לפי קלפי.")


def national_share(curve, h):
    """The 2022 national share of the day's turnout cast by hour h (linear, 0 at 07:00)."""
    hs = [AT.OPEN_H] + [AT.hour(x) for x in curve["hours"]]
    sh = [0.0] + list(curve["national_share"])
    if h >= hs[-1]:
        return 1.0
    h = max(h, AT.OPEN_H)
    i = next(i for i in range(1, len(hs)) if h <= hs[i])
    return sh[i - 1] + (h - hs[i - 1]) / (hs[i] - hs[i - 1]) * (sh[i] - sh[i - 1])


def _ballots(path=AT.BALLOTS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def synthetic_rows(base, at, noise=True, seed=SEED, ballots_path=AT.BALLOTS_PATH):
    """Every 2022 station at hour `at` ('HH:MM' or hours) as arab_section rows, plus its name for the CSV."""
    idx = AT._index(base, ballots_path)
    curve = base["curve"]
    h = AT.hour(at)
    names = {x["code"]: x["city"] for x in base["localities"]}
    with open(ballots_path, encoding="utf-8") as f:
        b25 = json.load(f)
    rng = random.Random(seed)       # same draw order for every hour, so a station's factors do not change
    level, shift = {}, {}
    rows = []
    for code, kalpi, sc, elig, voters in (r[:5] for r in b25["rows"]):
        arab = (code, AT.kalpi_base(kalpi)) in idx["cls"]      # a station of the section
        unit = (code, arab)
        if unit not in level:
            level[unit] = math.exp(rng.gauss(0, LEVEL_SD)) if noise else 1.0
            shift[unit] = rng.gauss(0, TIMING_SD) if noise else 0.0
        st = math.exp(rng.gauss(0, STATION_SD)) if noise else 1.0
        final = min(elig, voters * level[unit] * st)
        t = min(max(h + shift[unit], AT.OPEN_H), 22.0)
        f = AT.curve_at(curve, t)[1] if arab else national_share(curve, t)
        rows.append({"code": code, "kalpi": kalpi, "elig": elig, "voters": int(round(final * f)),
                     "name": names.get(code, "")})
    return rows


def write_csv(rows, path):
    """The rows in the layout of the CEC's expb.csv (Hebrew header), UTF-8 with BOM like the 2022 file."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("סמל ישוב,שם ישוב,קלפי,בזב,מצביעים\n")
        for r in rows:
            f.write(f"{r['code']},{r['name'].replace(',', ' ')},{r['kalpi']},{r['elig']},{r['voters']}\n")


def build(base, times=TIMES, csv_dir=None):
    releases = []
    for t in times:
        rows = synthetic_rows(base, t)
        if csv_dir:
            write_csv(rows, os.path.join(csv_dir, f"turnout_{t.replace(':', '')}.csv"))
        releases.append(AT.arab_section(rows, base, released=t))
    return {"demo": True, "note": NOTE, "times": list(times), "releases": releases,
            "history": [AT.history_entry(r) for r in releases]}


def check(base):
    """Unit checks: shares, leaders, the top other list, the mixed cities' Arab stations, a 100% release equals 2022,
    monotone releases, projections; partial, split, renumbered, absent, blank, duplicate and impossible stations; one
    basis per locality from release to release (blank stations with registers grown by new ones); a locality above
    its 2022 final; the same-hour 2022 curve; the history entry; CSV round trip; the official 2022 file and the 2021
    file read as releases."""
    fails = []

    def ok(cond, what):
        print(("  ok   " if cond else "  FAIL ") + what)
        if not cond:
            fails.append(what)
    def at22(rows, **kw):
        return AT.arab_section(rows, base, released="22:00", **kw)

    def loc(sec, key):
        return next(x for x in sec["localities"] if x["key"] == key)
    L = base["localities"]
    ok(all(abs(x["raam22"] + x["joint22"] + x["other22"] - 1) < 1e-3 for x in L), "2022 shares sum to 1")
    ok(all(abs(x["joint22"] - x["hadash_taal22"] - x["balad22"]) < 2e-4 for x in L), "joint22 = Hadash-Ta'al + Balad")
    ok(all((x["leader22"] == "raam") == (x["raam22"] > x["joint22"] and x["leader22"] != "other") for x in L),
       "leader22 follows the larger of raam22 and joint22")
    ok(all(x["kind"] == "druze" for x in L if x["leader22"] == "other" and x["elig22"] > 2000),
       "a non-Arab list led only in Druze localities (above 2,000 eligible voters)")
    ok(sum(x["watch"] for x in L) == 10 and all(x["kind"] == "arab" for x in L if x["watch"]),
       "ten largest Arab localities flagged")
    t = base["total"]
    ok(abs(t["turnout22_standard"] - 0.532) < 0.001,
       f"Arab+Druze localities 2022 turnout {t['turnout22_standard']:.4f} = 53.2%")
    ok(sum(g["elig22"] for g in base["groups"].values()) == t["elig22"] ==
       sum(g["elig22"] for g in base["regions"].values()), "groups and regions add up to the total")
    ok(set(base["regions"]) <= {"negev", "triangle", "galilee", "haifa", "jerusalem", "mixed", "golan"}, "region keys")

    full = at22(synthetic_rows(base, "22:00", noise=False))
    by = {x["key"]: x for x in L}
    ok(len(full["localities"]) == len(L), f"100% release covers every entry ({len(full['localities'])}/{len(L)})")
    ok(all(x["pace"] == 1.0 and x["coverage"] == 1.0 for x in full["localities"])
       and all(x["basis"] == ("stations" if by[x["key"]]["kind"] == "mixed_arab" else "whole")
               for x in full["localities"]),
       "100% release: pace 1.0 and coverage 1.0 everywhere, every Arab and Druze locality compared whole")
    ok(all(x["voters"] == by[x["key"]]["voters22"] for x in full["localities"])
       and full["kinds"]["mixed_arab"]["voters"] == base["kinds"]["mixed_arab"]["voters22"]
       and AT.arab_boxes(_ballots()) >= {(5000, 875), (4000, 85), (4000, 301)}
       and AT.ARAB_LISTS_K25 == tuple(R.ARAB_LISTS["K25"]) and AT.ARAB_BOX_SHARE == R.ARAB_BOX_MIN_SHARE,
       "mixed cities: the Arab stations of the base and of a release are the same (the box rule or an Arab-list "
       "majority in 2022: Jaffa's 875, Haifa's 85 and 301 too), with registry.py's lists and threshold")
    mas = by["4203"]

    def lead(x):        # the first of Ra'am, the Joint List and the top other list, ahead of the second
        s = sorted([x["raam22"], x["joint22"], x["top_other22"]["share"]])
        return s[-1] - s[-2]
    ok(mas["top_other22"]["id"] == "ז" and mas["margin22"] > 0.3
       and all(x["top_other22"]["share"] > max(x["raam22"], x["joint22"]) for x in L if x["leader22"] == "other")
       and all(abs(x["margin22"] - lead(x)) < 2e-4 for x in L if x["top_other22"]),
       f"top other list from every list of the official file: Mas'ade {mas['top_other22']['name']} "
       f"{mas['top_other22']['share']:.1%} (not the Likud's 12.9%), margin {mas['margin22']:.1%}")
    ok(all(x["voters"] == by[x["key"]]["voters22"] and x["elig"] == by[x["key"]]["elig22"]
           and x["turnout"] == by[x["key"]]["turnout22"] for x in full["localities"]),
       "100% release equals the 2022 finals")
    ok(all(g["pace"] == 1.0 and g["turnout"] == base["groups"][k]["turnout22"] for k, g in full["groups"].items()),
       "100% release: groups equal 2022")
    ok(full["total"]["turnout"] == t["turnout22"] and full["total"]["projected_final"]["mid"] == t["turnout22"],
       "100% release at 22:00 projects the 2022 final")

    hours = ["10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "21:00", "22:00"]
    demo = [AT.arab_section(synthetic_rows(base, h), base, released=h) for h in hours]
    mono = all(a["total"]["turnout"] < b["total"]["turnout"] and a["total"]["pace"] < b["total"]["pace"]
               for a, b in zip(demo, demo[1:]))
    ok(mono, "total turnout and pace rise with time: "
       + ", ".join(f"{d['as_of']} {d['total']['turnout']:.3f}" for d in demo))
    ok(all(all(a["groups"][k]["turnout"] <= b["groups"][k]["turnout"] for k in a["groups"])
           and all(a["regions"][k]["turnout"] <= b["regions"][k]["turnout"] for k in a["regions"])
           for a, b in zip(demo, demo[1:])), "groups and regions rise with time")
    loc_ok = all(x["voters"] <= y["voters"] for a, b in zip(demo, demo[1:])
                 for x, y in zip(a["localities"], b["localities"]))
    ok(loc_ok, "every locality's voters rise with time")
    for d in demo:
        p = d["total"]["projected_final"]
        if p:
            print(f"       {d['as_of']}: turnout {d['total']['turnout']:.3f} pace {d['total']['pace']:.3f} "
                  f"on_track {d['total']['on_track']:.3f} projected {p['lo']:.3f}-{p['mid']:.3f}-{p['hi']:.3f} "
                  f"ratio_to_national {d['total']['ratio_to_national']:.3f}")
    final = t["turnout22"]          # the section: Arab and Druze localities and the mixed cities' Arab stations
    at21 = demo[6]["total"]["projected_final"]
    ok(abs(at21["mid"] - final) < 0.03 and at21["lo"] <= final <= at21["hi"],
       f"projected final at 21:00 {at21['mid']:.3f} within 3 points of the 2022 final {final:.3f}, and in its range")
    ok(all(p["lo"] <= p["mid"] <= p["hi"] for p in (d["total"]["projected_final"] for d in demo)), "lo <= mid <= hi")
    ok(AT.arab_section(synthetic_rows(base, "09:00"), base, released="09:00")["total"]["projected_final"] is None,
       "no projection before 10:00")

    # partial releases, renumbered and split stations, missing eligible counts, bad rows
    rows = synthetic_rows(base, "22:00", noise=False)
    part = at22([r for i, r in enumerate(rows) if i % 2 == 0])
    ok(abs(part["total"]["pace"] - 1.0) < 1e-9 and 0.35 < part["total"]["coverage"] < 0.65,
       f"half the stations: pace 1.0 on the matched ones, coverage {part['total']['coverage']}")
    noelig = at22([{**r, "elig": None} for r in rows])["total"]
    ok(noelig["turnout"] is None and noelig["projected_final"]["basis"] == "pace"
       and abs(noelig["projected_final"]["mid"] - t["turnout22"]) < 1e-3, "no eligible counts: projected from pace")
    sub = [{**r, "kalpi": f"{AT.kalpi_base(r['kalpi'])}.7{i}"} if r["code"] == 4000 else r for i, r in enumerate(rows)]
    ok(at22(sub)["kinds"]["mixed_arab"]["pace"] == 1.0,
       "mixed-city stations matched by station number when sub-station numbers change")
    naz = [r for r in rows if r["code"] == 7300]
    split = [r for r in rows if r["code"] != 7300]
    for i, r in enumerate(naz):     # every Nazareth station split in two, with new sub-station numbers
        v1 = r["voters"] // 2
        split += [{**r, "kalpi": f"{AT.kalpi_base(r['kalpi'])}.8{i}", "voters": v1, "elig": r["elig"] // 2},
                  {**r, "kalpi": f"{AT.kalpi_base(r['kalpi'])}.9{i}", "voters": r["voters"] - v1,
                   "elig": r["elig"] - r["elig"] // 2}]
    ns = loc(at22(split), "7300")
    ok(ns["pace"] == 1.0 and ns["coverage"] == 1.0 and ns["stations"] == 2 * len(naz),
       "a locality whose stations were all split compares as a whole")
    last = AT.kalpi_base(naz[-1]["kalpi"])
    gone = [r for r in rows if not (r["code"] == 7300 and AT.kalpi_base(r["kalpi"]) == last)]
    ns = loc(at22(gone), "7300")
    ok(ns["pace"] == 1.0 and ns["coverage"] < 1.0 and ns["basis"] == "stations",
       "a locality with a station missing from the file is compared station by station")
    moved = [{**r, "elig": r["elig"] * 3} if r["code"] == 7300 and r is naz[0] else r for r in gone]
    sec = at22(moved)
    ok(loc(sec, "7300")["pace"] == 1.0 and sec["checks"].get("register changed") == 1,
       "a matched station whose register tripled is another station, left out of pace")
    blank = [{**r, "voters": "" if r["code"] == 7300 and AT.kalpi_base(r["kalpi"]) == last else r["voters"]}
             for r in rows]
    sec = at22(blank)
    ns = loc(sec, "7300")
    ok(ns["pace"] == 1.0 and ns["coverage"] < 1.0 and sec["checks"].get("no figure", 0) >= 1
       and ns["basis"] == "whole-minus-blank",
       "a station without a figure (blank) is left out, not read as zero voters: the whole locality less its station")
    # a station split under its own number (N -> N and a new N.1) in a locality compared station by station
    idx = AT._index(base)
    b1 = next(b for b in sorted(idx["groups"]["7300"]) if len(idx["subs"][(7300, b)]) == 1 and b != last)

    def split_n(rs, blank_new=False):
        out = []
        for r in rs:
            if r["code"] == 7300 and AT.kalpi_base(r["kalpi"]) == b1:
                v1, e1 = round(0.7 * r["voters"]), round(0.7 * r["elig"])
                out += [{**r, "voters": v1, "elig": e1},
                        {**r, "kalpi": f"{b1}.1", "voters": "" if blank_new else r["voters"] - v1,
                         "elig": r["elig"] - e1}]
            else:
                out.append(r)
        return out
    sec = at22(split_n(gone))
    ns = loc(sec, "7300")
    ok(ns["pace"] == 1.0 and ns["coverage"] < 1.0 and sec["checks"].get("split station") == 1
       and not sec["checks"].get("register changed"),
       f"station {b1} split into {b1} (70%) and a new {b1}.1: compared as one block, nothing dropped "
       f"(pace {ns['pace']}, checks {sec['checks']})")
    sec = at22(split_n(gone, blank_new=True))
    ns = loc(sec, "7300")
    ok(ns["pace"] == 1.0 and sec["checks"].get("unplaced station") == 1 and not sec["checks"].get("split station"),
       f"the new {b1}.1 without a figure yet: {b1} is not compared alone (left out and counted as unplaced)")
    # stations absent from the file (not blank) while the register grew 8% and new stations were added: the counts
    # pass, so only the 2022 station numbers show that the locality is not whole
    grow = [{**r, "elig": round(1.08 * r["elig"])} if r["code"] == 7300 else r for r in gone]
    extra = [{"code": 7300, "kalpi": str(900 + i), "elig": 600, "voters": 300} for i in range(6)]
    x7300 = next(x for x in L if x["key"] == "7300")
    n_naz = sum(1 for r in grow if r["code"] == 7300) + len(extra)
    sec = at22(grow + extra)
    ns = loc(sec, "7300")
    ok(n_naz >= x7300["stations22"] and ns["elig"] >= x7300["elig22"] and ns["pace"] == 1.0
       and ns["coverage"] < 1.0 and sec["checks"].get("new station") == len(extra),
       f"a 2022 station group absent from the file is not hidden by new stations: compared station by station "
       f"(pace {ns['pace']}, coverage {ns['coverage']}; {n_naz} stations, {ns['elig']:,} eligible against "
       f"{x7300['stations22']} and {x7300['elig22']:,} in 2022)")
    whole = [{**r, "elig": round(1.08 * r["elig"])} if r["code"] == 7300 else r for r in rows] + extra
    ns = loc(at22(whole), "7300")
    ok(ns["coverage"] == 1.0 and ns["pace"] == round((x7300["voters22"] + 300 * len(extra)) / x7300["voters22"], 3),
       "the same with every 2022 station there: the whole locality, new stations included")
    renum = [{**r, "kalpi": str(1000 + i)} if r["code"] == 7300 else r for i, r in enumerate(rows)]
    ns = loc(at22(renum), "7300")
    ok(ns["pace"] == 1.0 and ns["coverage"] == 1.0 if AT.RENUMBERED else ns["pace"] is None,
       "every station renumbered (no 2022 number left): compared whole by the counts"
       if AT.RENUMBERED else "every station renumbered: nothing to compare (RENUMBERED = 0: numbers only)")
    first = next(r for r in renum if r["code"] == 7300)
    sec = at22([r for r in renum if r is not first])
    ns = loc(sec, "7300")
    ok(ns["pace"] is None and ns["coverage"] == 0.0 and sec["checks"].get("new station") == len(naz) - 1,
       "renumbered and a station short: nothing to compare, every station counted as new")
    dup = at22(rows + [naz[0]])
    ok(dup["checks"].get("duplicate row") == 1 and dup["total"] == full["total"],
       "a second row for the same station is dropped and counted")
    late = AT.arab_section(rows, base, released="22:40")
    ok(late["as_of"] == "22:00" and late["released"] == "22:40"
       and late["total"]["projected_final"]["mid"] == t["turnout22"],
       "a release labelled after the polls closed (22:40) is read as 22:00")
    newst = rows + [{"code": 4000, "kalpi": "9999", "elig": 500, "voters": 100}]
    ok(at22(newst)["checks"].get("unclassified") == 1,
       "a new mixed-city station is reported as unclassified")
    bad = rows + [{"code": 7300, "kalpi": "1", "elig": 100, "voters": 500}]
    ok(at22(bad)["checks"].get("more voters than eligible") == 1,
       "a row with more voters than eligible voters is dropped")
    ok(at22(rows, national_turnout=64.0)["national"] == 0.64,
       "national turnout accepted in percent")

    # one definition per locality from release to release: whole, whole less its blank stations, station by station
    rng = random.Random(7)
    some = [{**r, "voters": ""} if rng.random() < 0.3 else r for r in rows]
    sec = at22(some)
    std = [x for x in sec["localities"] if by[x["key"]]["kind"] != "mixed_arab"]
    ok(all(x["pace"] == 1.0 and x["basis"] in ("whole", "whole-minus-blank") for x in std)
       and sum(x["basis"] == "whole-minus-blank" for x in std) > 100 and sec["total"]["pace"] == 1.0
       and abs(sec["total"]["coverage"] - sec["total"]["voters"] / t["voters22"]) < 0.01,
       f"100% release with 30% of the stations blank: every Arab and Druze locality on its whole less the blank "
       f"stations' 2022 counterparts, pace 1.0 ({sum(x['basis'] == 'whole-minus-blank' for x in std)} of {len(std)} "
       f"localities), coverage {sec['total']['coverage']}")
    two = next(b for b in sorted(idx["groups"]["7300"]) if len(idx["subs"][(7300, b)]) >= 2)
    k2 = idx["subs"][(7300, two)][-1]
    sec = at22([{**r, "voters": ""} if r["code"] == 7300 and AT.kalpi_id(r["kalpi"]) == k2 else r for r in rows])
    ns, v2 = loc(sec, "7300"), idx["st22"][(7300, k2)][0]
    ok(ns["basis"] == "whole-minus-blank" and ns["pace"] == 1.0
       and ns["coverage"] == round((x7300["voters22"] - v2) / x7300["voters22"], 3)
       and not sec["checks"].get("unplaced station"),
       f"blank sub-station {k2} of a group that kept its 2022 sub-stations: only its own 2022 voters ({v2}) leave the "
       f"comparison (coverage {ns['coverage']})")
    sec = at22(split_n(rows, blank_new=True))
    ns, v1 = loc(sec, "7300"), sum(idx["st22"][(7300, k)][0] for k in idx["subs"][(7300, b1)])
    ok(ns["basis"] == "whole-minus-blank" and ns["pace"] == 1.0 and sec["checks"].get("unplaced station") == 1
       and ns["coverage"] == round((x7300["voters22"] - v1) / x7300["voters22"], 3),
       f"station {b1} split, the new {b1}.1 blank: the whole group {b1} leaves both sides, the rest whole")
    ns = loc(at22(split_n(rows)), "7300")
    ok(ns["basis"] == "whole" and ns["pace"] == 1.0 and ns["coverage"] == 1.0, f"the same with {b1}.1 reported: whole")
    # the register grew: new stations under numbers not used in 2022 in the ten largest Arab localities, 5% more
    # voters; then one old station of each without a figure. Station by station would drop the new stations
    big = [x for x in L if x["watch"]]
    r18 = synthetic_rows(base, "18:00", noise=False)
    grown = []
    for x in big:
        n = max(1, round(0.05 * x["stations22"]))
        v = round(0.05 * sum(r["voters"] for r in r18 if r["code"] == x["code"]) / n)
        grown += [{"code": x["code"], "kalpi": str(900 + i), "elig": 600, "voters": v} for i in range(n)]
    lone = {}
    for r in r18:
        if r["code"] in {x["code"] for x in big} and r["code"] not in lone:
            lone[r["code"]] = r["kalpi"]
    f18 = AT.arab_section(r18 + grown, base, released="18:00")
    b18 = AT.arab_section([{**r, "voters": ""} if lone.get(r["code"]) == r["kalpi"] else r for r in r18] + grown,
                          base, released="18:00")
    F, B = ({x["key"]: x for x in s["localities"]} for s in (f18, b18))
    gap = max(abs(F[x["key"]]["pace"] - B[x["key"]]["pace"]) for x in big)
    ggap = max(abs(f18["groups"][g]["pace"] - b18["groups"][g]["pace"]) for g in ("raam", "joint"))
    f18h = AT.curve_at(base["curve"], 18.0)[1]       # the 2022 share of the day cast by 18:00
    ok(all(F[x["key"]]["basis"] == "whole" and B[x["key"]]["basis"] == "whole-minus-blank" for x in big)
       and gap < 0.002 and ggap < 0.002 and all(B[x["key"]]["pace"] > 1.04 * f18h for x in big)
       and abs(f18["total"]["projected_final"]["mid"] - b18["total"]["projected_final"]["mid"]) < 0.003,
       f"one station blank in each of the ten largest localities, whose registers grew: the same pace as with "
       f"every station (largest gap {gap:.4f}; Ra'am-led and Joint-led groups {ggap:.4f}), new stations counted")
    # a locality above its 2022 final: Majdal Shams voted 23% in 2022
    up = [{**r, "voters": min(r["elig"], round(2.2 * r["voters"]))} if r["code"] == 4201 else r for r in rows]
    sec = at22(up)
    g = loc(sec, "4201")
    ok(g["basis"] == "whole" and g["pace"] > 2.0 and g["coverage"] == 1.0
       and sec["kinds"]["druze"]["coverage"] == 1.0 and not sec["checks"].get("implausible pace"),
       f"a locality at 2.2 times its 2022 voters (Majdal Shams, 23% in 2022) with eligible counts: compared whole, "
       f"pace {g['pace']}, not dropped")
    sec = at22([{**r, "elig": None} if r["code"] == 4201 else r for r in up])
    g = loc(sec, "4201")
    ok(g["basis"] == "stations" and g["pace"] is None and sec["checks"].get("implausible pace") == 2,
       "the same without eligible counts: no register to check, the 2x cap holds station by station")
    x4201 = by["4201"]
    new2 = [{"code": 4201, "kalpi": str(900 + i), "elig": round(0.35 * x4201["elig22"]),
             "voters": round(0.175 * x4201["elig22"])} for i in range(2)]
    sec = at22(up + new2)
    g = loc(sec, "4201")
    ok(g["basis"] == "whole" and g["pace"] > 3 and g["coverage"] == 1.0 and g["elig"] > 1.6 * x4201["elig22"]
       and not sec["checks"].get("register changed") and not sec["checks"].get("implausible pace"),
       f"the same with its register 1.7 times 2022's in two new stations (as residents take citizenship): still "
       f"whole, pace {g['pace']}")
    blank1 = [{**r, "voters": ""} if r["code"] == 4201 and AT.kalpi_base(r["kalpi"]) == 1 else r for r in up]
    gb = loc(at22(blank1 + new2), "4201")
    ok(gb["basis"] == "whole-minus-blank" and abs(gb["pace"] - g["pace"]) < 0.01 and gb["coverage"] < 0.6,
       f"... and with one of its two 2022 stations blank: the whole less that station, the new stations in "
       f"proportion, pace {gb['pace']} (counted in full against the one station left: "
       f"{sum(r['voters'] or 0 for r in blank1 + new2 if r['code'] == 4201) / idx['st22'][(4201, '2')][0]:.2f})")
    allold = [{**r, "voters": ""} if r["code"] == 4201 else r for r in rows] + new2
    g = loc(at22(allold), "4201")
    ok(g["pace"] is None and g["coverage"] == 0.0, "only new stations reported: nothing to compare")
    worst = []
    for d in demo + [f18, b18, at22(up), at22(some)]:
        for m in [d["total"], *d["groups"].values(), *d["regions"].values(), *d["kinds"].values()]:
            p = m["projected_final"]
            if p and not ((m["turnout"] or 0) <= p["lo"] + 1e-9 and p["lo"] <= p["mid"] <= p["hi"] <= 1.0):
                worst.append((d["as_of"], m.get("localities"), p))
    ok(not worst, f"projected_final: turnout so far <= lo <= mid <= hi <= 100% everywhere {worst[:3]}")

    with tempfile.TemporaryDirectory() as d:
        r14 = synthetic_rows(base, "14:00")
        p = os.path.join(d, "t.csv")
        write_csv(r14, p)
        with open(p, "rb") as f:
            back = AT.read_station_csv(f.read())
        a, b = AT.arab_section(back, base, released="14:00"), AT.arab_section(r14, base, released="14:00")
        ok(a == b, "CSV round trip (expb.csv layout, BOM) gives the same section")
        with open(p, "w", encoding="utf-8") as f:       # a percentage column instead of a voter count
            f.write("סמל יישוב,מספר קלפי,בעלי זכות בחירה,אחוז הצבעה\n")
            f.writelines(f"{r['code']},{r['kalpi']},{r['elig']},{100 * r['voters'] / r['elig']:.2f}%\n"
                         for r in r14)
        with open(p, "rb") as f:
            pct = AT.arab_section(AT.read_station_csv(f.read()), base, released="14:00")
        ok(abs(pct["total"]["turnout"] - b["total"]["turnout"]) < 2e-4,
           "CSV with a turnout percentage instead of voters")
    k25 = os.path.join(ROOT, "data", "official", "k25_expb.csv")
    if os.path.exists(k25):
        with open(k25, "rb") as f:
            off = at22(AT.read_station_csv(f.read()))
        ok(all(x["pace"] == 1.0 and x["coverage"] == 1.0 for x in off["localities"])
           and len(off["localities"]) == len(L) and off["total"]["turnout"] == t["turnout22"],
           "the official 2022 file (data/official/k25_expb.csv) matches its own base")
    k24 = os.path.join(ROOT, "data", "official", "k24_expb.csv")
    if os.path.exists(k24):       # 2021, numbered its own way, read as if it were a 2026 release
        with open(k24, "rb") as f:
            rows21 = AT.read_station_csv(f.read())
        sec = at22(rows21)
        v21 = {}
        for r in rows21:
            if str(r["code"]).isdigit() and str(r["voters"]).isdigit():
                v21[r["code"]] = v21.get(r["code"], 0) + int(r["voters"])
        got = {x["key"]: x for x in sec["localities"]}
        for kind in ("arab", "druze"):
            # Kisra-Sumei aside: a local boycott in 2022 left two of its stations with 37 and 67 voters, beyond the
            # pace cap, so its renumbered stations hardly match (pace 1.28 against 1.87 true)
            xs = [x for x in L if x["kind"] == kind and x["key"] != "1296" and x["key"] in got]
            truth = sum(v21.get(x["key"], 0) for x in xs) / sum(x["voters22"] for x in xs)
            th = {x["key"]: got[x["key"]]["coverage"] * x["voters22"] for x in xs if got[x["key"]]["pace"] is not None}
            pace = sum(got[k]["pace"] * w for k, w in th.items()) / sum(th.values())
            ok(abs(pace - truth) < 0.02,
               f"2021 file as a release: {kind} pace {pace:.3f} vs 2021/2022 voters {truth:.3f} (Kisra-Sumei aside)")
        rn, small = [], []
        for x in L:
            if x["kind"] == "mixed_arab" or x["key"] not in got:
                continue
            mine = [r for r in rows21 if r["code"] == x["key"]]
            nums = {AT.kalpi_base(AT.kalpi_id(r["kalpi"])) for r in mine}
            if len(nums & idx["groups"][x["key"]]) < AT.RENUMBERED * len(idx["groups"][x["key"]]):
                el = sum(int(r["elig"]) for r in mine if str(r["elig"]).isdigit())
                (rn if len(mine) >= x["stations22"] or el >= x["elig22"] else small).append(x)
        ok(not AT.RENUMBERED or rn and all(got[x["key"]]["coverage"] == 1.0
                      and abs(got[x["key"]]["pace"] - v21.get(x["key"], 0) / x["voters22"]) < 6e-4 for x in rn)
           and all(got[x["key"]]["coverage"] < 1.0 for x in small),
           f"2021 file: of the {len(rn) + len(small)} renumbered localities (fewer than half of the 2022 numbers), the "
           f"{len(rn)} with as many stations as in 2022 compare whole, exactly; the {len(small)} with fewer do not")
    # 2022 at the same hour, on the same stations: a release shaped exactly like 2022 sits on it at every hour
    C = base["curve"]
    ok(C["section"][-1] == round(100 * t["turnout22"], 1)
       and C["mixed_arab"][-1] == round(100 * base["kinds"]["mixed_arab"]["turnout22"], 1)
       and all(m <= s <= a for m, s, a in zip(C["mixed_arab"], C["section"], C["arab"])),
       f"base curves: section {C['section'][-1]}% and mixed-city Arab stations {C['mixed_arab'][-1]}% at 22:00, "
       f"the section between them and the Arab and Druze localities' {C['arab'][-1]}% at every hour")
    worst = 0.0
    for hh in ("10:00", "14:00", "18:00", "21:00"):
        s0 = AT.arab_section(synthetic_rows(base, hh, noise=False), base, released=hh)
        for m in [s0["total"], *s0["kinds"].values(), *s0["groups"].values(), *s0["regions"].values()]:
            worst = max(worst, abs(m["turnout"] - m["curve22"]))
    ok(worst < 1e-3, f"a release shaped like 2022: turnout = curve22 for the total, every kind, group and region "
                     f"(largest gap {worst:.5f})")
    ok(full["total"]["curve22"] == full["total"]["turnout22"] == t["turnout22"]
       and all(k["curve22"] == k["turnout22"] for k in full["kinds"].values()), "curve22 at 22:00 is the 2022 final")
    s14 = demo[hours.index("14:00")]
    ok(s14["total"]["curve22"] < C["arab"][C["hours"].index("14:00")] / 100,
       f"the total's curve22 at 14:00 ({s14['total']['curve22']}) is below the Arab and Druze localities' curve "
       f"({C['arab'][C['hours'].index('14:00')]}%): it holds the mixed cities' Arab stations")
    sec = demo[2]
    h = AT.history_entry(sec)
    size = len(json.dumps(h, ensure_ascii=False, separators=(",", ":")))
    ok(size < 8000 and h["total"]["turnout"] == sec["total"]["turnout"]
       and h["total"]["curve22"] == sec["total"]["curve22"]
       and h["kinds"] == {k: {"turnout": v["turnout"], "pace": v["pace"]} for k, v in sec["kinds"].items()}
       and h["localities"] == {x["key"]: [x["turnout"], x["pace"]] for x in sec["localities"]}
       and h["basis"] == {"stations": [x["key"] for x in sec["localities"] if by[x["key"]]["kind"] == "mixed_arab"]},
       f"history entry: total, groups, regions, kinds and every locality as [turnout, pace], the basis of those not "
       f"compared whole, {size:,} bytes")
    hb = AT.history_entry(b18)
    ok(sorted(hb["basis"]) == ["stations", "whole-minus-blank"]
       and sorted(hb["basis"]["whole-minus-blank"]) == sorted(x["key"] for x in big),
       f"history entry of the release with blank stations: basis {[(k, len(v)) for k, v in hb['basis'].items()]}")
    print("FAILED: " + "; ".join(fails) if fails else "all arab_turnout checks passed")
    return not fails


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help=f"the demo JSON (default {os.path.relpath(OUT, ROOT)}; "
                                  "with --csv F.csv written only when given)")
    ap.add_argument("--csv", help="a folder: also write the synthetic per-station CSV of each release there "
                                  "(turnout_HHMM.csv); a path ending in .csv: write one release there (--at) and "
                                  "nothing else unless --out is given")
    ap.add_argument("--at", default="14:00", help="the release written by --csv F.csv (default 14:00)")
    ap.add_argument("--check", action="store_true", help="run the unit checks instead of writing the demo")
    a = ap.parse_args(argv)
    base = AT.load_base()
    if a.check:
        sys.exit(0 if check(base) else 1)
    if a.csv and a.csv.lower().endswith(".csv"):
        if AT.hour(a.at) is None:
            ap.error(f"--at: not a time: {a.at!r}")
        if os.path.dirname(os.path.abspath(a.csv)):
            os.makedirs(os.path.dirname(os.path.abspath(a.csv)), exist_ok=True)
        write_csv(synthetic_rows(base, a.at), a.csv)
        print(f"wrote {a.csv}: the synthetic release of {a.at}")
        if not a.out:
            return
        a.csv = None
    elif a.csv:
        os.makedirs(a.csv, exist_ok=True)
    out = a.out or OUT
    doc = build(base, csv_dir=a.csv)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    for r in doc["releases"]:
        t, p = r["total"], r["total"]["projected_final"]
        print(f"{r['as_of']}: turnout {t['turnout']:.1%} (national {r['national']:.1%}), pace {t['pace']:.3f}, "
              f"raam-led {r['groups']['raam']['turnout']:.1%}, joint-led {r['groups']['joint']['turnout']:.1%}, "
              f"projected {p['lo']:.1%}-{p['mid']:.1%}-{p['hi']:.1%}" if p else "")
    print(f"wrote {out}: {len(doc['releases'])} releases, {os.path.getsize(out):,} bytes")


if __name__ == "__main__":
    main()
