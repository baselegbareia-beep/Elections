"""Build site/data/arab_day_2022.json: the 2022 base of the election-day Arab-society section.

Inputs (all in the repository):
  site/data/core.json        locality sector and sub-region (the site's own classification), names, centroids
  site/data/ballots_K25.json 2022 results per polling station (sector code per station)
  pipeline/reference/arab_localities.csv     the CEC regional committee of each Arab/Druze locality
  pipeline/reference/turnout_hourly.json     2022 national hourly series and aChord's Arab estimates

Units: turnout, shares and pace are fractions (0.532); the hourly curve is in percent, as published.

Entries (one per locality, `key`):
  kind "arab"       an Arab locality (core.json sector "arab"), key "<code>";
  kind "druze"      a Druze locality or Ghajar (sector "druze"), key "<code>"; the two Circassian villages are
                    left out, as in the site's Arab+Druze standard (registry.STANDARD_SEGMENTS: 53.2% in 2022);
  kind "mixed_arab" the Arab stations of a mixed city or Jewish locality, key "<code>:arab": stations whose
                    sector code is 1 (code % 10 == 1) in ballots_K25.json, i.e. the vote-based box rule of
                    build_data.py, as live_fetch.station_sector reads it during the day.
Regions (geographic; the community is in `kind`, the site's finer sub-region in `sub`):
  negev      Bedouin localities in the Negev (sub "negev")
  triangle   Wadi Ara and the southern Triangle (subs "wadi_ara", "triangle_south"; al-Arian sits in Wadi Ara)
  haifa      Carmel and the Haifa district outside Wadi Ara: the CEC's Haifa-area committees 7–9
             (Daliyat al-Karmel, Isfiya, Fureidis, Jisr az-Zarqa, Ibtin, Ras Ali, Khawaled, Ein Hawd)
  jerusalem  Abu Ghosh, Ein Rafa, Ein Naqquba (sub "jerusalem")
  golan      the Druze villages of the Golan Heights and Ghajar (subs "golan", "ghajar")
  galilee    every other Arab and Druze locality in the north (Nazareth, the Galilee, the valleys)
  mixed      the Arab stations of mixed cities and Jewish localities (kind "mixed_arab")
2022 vote (shares of valid votes): raam22 = Ra'am (עם); joint22 = Hadash-Ta'al (ום) + Balad (ד), the two lists
that run together in 2026 as the Joint List (live_model.BASE_MAP); other22 = everything else. leader22 is the
larger of raam22 and joint22, or "other" when a single non-Arab list beat both (most Druze localities);
margin22 is the leader's lead over the next of the three (Ra'am, the Joint List, the top non-Arab list).

The hourly Arab curve and the projection range are documented in pipeline/arab_turnout.py. The curve is of the
Arab and Druze localities (its end, 53.2%, is their official final); the Arab stations of mixed cities have no
hourly figures of their own and are given the same timing on their own 2022 final ("mixed_arab"), and the whole
section is the two weighted by their 2022 voters ("section"). The Druze localities, too, follow the Arab timing.

Run: python3 pipeline/build_arab_day.py [--out site/data/arab_day_2022.json]
"""
import argparse
import collections
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arab_turnout as AT  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAAM, JOINT = ["עם"], ["ום", "ד"]
REGION_NAMES = {"negev": "הנגב", "triangle": "המשולש", "galilee": "הגליל והעמקים", "haifa": "הכרמל ומחוז חיפה",
                "jerusalem": "אזור ירושלים", "golan": "רמת הגולן", "mixed": "ערים מעורבות"}
KIND_NAMES = {"arab": "יישובים ערביים", "druze": "יישובים דרוזיים וע׳ג׳ר",
              "mixed_arab": "קלפיות ערביות בערים מעורבות"}
GROUP_SHORT = {"raam": "רע״ם", "joint": "המשותפת", "other": "אחרת"}
GROUP_NAMES = {"raam": "רע״ם הובילה ב-2022", "joint": "חד״ש-תע״ל ובל״ד הובילו ב-2022 (הרשימה המשותפת)",
               "other": "רשימה אחרת הובילה ב-2022"}
HAIFA_COMMITTEES = {"7", "8", "9"}        # CEC regional committees of Haifa, the Carmel and Hadera (2022 file)
REGION_OVERRIDE = {1316: "triangle"}      # al-Arian: in Wadi Ara, though the Hadera committee counts it
SIGMA_FACTOR = 2.0       # Arab timing is less stable than the national one (2022: a late surge), and its 2022
                         # curve is itself an estimate: twice the national spread across 2013-2022
Z80 = 1.2816             # the range is a rough 80% interval
NOTE_HE = ("בסיס 2022 לשיעור ההצבעה בחברה הערבית ביום הבחירות. היישובים לפי הסיווג של האתר: יישובים ערביים "
           "ודרוזיים (בלי שני הכפרים הצ׳רקסיים), והקלפיות הערביות בערים מעורבות וביישובים יהודיים, רשומה אחת לכל "
           "עיר. שיעור ההצבעה הוא מצביעים בקלפיות חלקי בעלי זכות הבחירה בהן, בלי המעטפות הכפולות. הרשימה שהובילה "
           "ב-2022 היא רע״ם או חד״ש-תע״ל ובל״ד יחד (ב-2026 הן רצות כרשימה המשותפת), לפי הגדולה מביניהן, או רשימה "
           "אחרת כשרשימה שאינה ערבית קיבלה יותר מכל אחת מהן (רוב היישובים הדרוזיים). עקומת השעות של 2022 בחברה "
           "הערבית אינה רשמית: אומדני "
           "מרכז אקורד (האוניברסיטה העברית) ל-14:00 (17%), ל-16:00 (23%) ול-20:00 (44%), 30% ל-18:00 שפורסם בלי "
           "ייחוס, והשיעור הסופי הרשמי, 53.2%; שעות הבוקר חושבו מהיחס לשיעור הארצי. ההערכה לסוף היום מחלקת את "
           "שיעור ההצבעה עד שעה מסוימת בחלק מכלל מצביעי היום שהצביעו עד אותה שעה ב-2022, ולכן מניחה שדפוס "
           "ההצבעה המאוחרת של 2022 יחזור (ב-2022 הצביע כשישית מהמצביעים אחרי 20:00). לקלפיות הערביות בערים "
           "המעורבות וליישובים הדרוזיים אין נתוני שעות משלהם, ולכן גם אצלם ההשוואה ל-2022 באותה שעה, הקצב הצפוי "
           "והטווח לסוף היום מחושבים לפי העיתוי המשוער של החברה הערבית, על השיעור הסופי שלהם ב-2022. הטווח הוא "
           "הערכה גסה (כ-80%): פי שניים מהפיזור של העקומה הארצית בבחירות 2013–2022. נתוני השתתפות בלבד: שום דבר "
           "כאן אינו מתורגם לקולות או למנדטים.")
WATCH = 10               # the largest Arab localities flagged for the page


def region_of(kind, sub, code, committee, lat):
    if kind == "mixed_arab":
        return "mixed"
    if code in REGION_OVERRIDE:
        return REGION_OVERRIDE[code]
    if sub == "negev" or (committee is None and lat is not None and lat < 31.6):
        return "negev"
    if sub in ("wadi_ara", "triangle_south"):
        return "triangle"
    if sub == "jerusalem":
        return "jerusalem"
    if sub in ("golan", "ghajar"):
        return "golan"
    if committee in HAIFA_COMMITTEES:
        return "haifa"
    return "galilee"


def build_curve(ref):
    """2022 hourly curve: national (CEC) and Arab (aChord estimates, the official final, two modelled
    morning points and an interpolated 19:00), plus the log-spread used for the projection range."""
    hours = ref["hours"]
    k25 = ref["elections"]["K25"]
    nat = dict(zip(hours, k25["values"]))
    nat.update(k25.get("extra", {}))
    est = ref["arab_estimates"]["K25"]
    arab = {h: float(v) for h, v in est["points"].items()}
    kind = {h: "estimate" for h in arab}
    kind["18:00"] = "reported"                                # not attributed to aChord (points_note)
    final = float(est["final"])
    arab["22:00"], kind["22:00"] = final, "official"
    # 10:00 and 12:00: the Arab/national ratio rose steadily through the day (0.44, 0.48, 0.52 at
    # 14/16/18); its least-squares line, carried back, gives the morning (12:00 lands near the 12%
    # Hadash-Ta'al claimed at noon, which is not used).
    xs = [h for h in ("14:00", "16:00", "18:00") if h in arab]
    t = [AT.hour(h) for h in xs]
    r = [arab[h] / nat[h] for h in xs]
    tm, rm = sum(t) / len(t), sum(r) / len(r)
    slope = sum((a - tm) * (b - rm) for a, b in zip(t, r)) / sum((a - tm) ** 2 for a in t)
    for h in ("10:00", "12:00"):
        arab[h], kind[h] = round(nat[h] * (rm + slope * (AT.hour(h) - tm)), 1), "model"
    # 19:00 (CBS sample hour since 2022): the national path between 18:00 and 20:00
    if "19:00" in nat:
        w = (nat["19:00"] - nat["18:00"]) / (nat["20:00"] - nat["18:00"])
        arab["19:00"], kind["19:00"] = round(arab["18:00"] + w * (arab["20:00"] - arab["18:00"]), 1), "model"
    out_hours = sorted(set(arab) & set(nat), key=AT.hour)
    # spread of log(final / figure at h) across the national series 2013-2022
    sig = {}
    for i, h in enumerate(hours):
        logs = [math.log(d["final"] / d["values"][i]) for d in ref["elections"].values()]
        m = sum(logs) / len(logs)
        sig[h] = math.sqrt(sum((x - m) ** 2 for x in logs) / (len(logs) - 1))
    sig["19:00"] = (sig["18:00"] + sig["20:00"]) / 2
    sigma = [SIGMA_FACTOR * sig[h] for h in out_hours]
    for i in range(len(sigma) - 2, -1, -1):     # an earlier hour is never more certain than a later one
        sigma[i] = max(sigma[i], sigma[i + 1])
    return {
        "hours": out_hours,
        "arab": [arab[h] for h in out_hours],
        "national": [nat[h] for h in out_hours],
        "arab_kind": [kind[h] for h in out_hours],
        "arab_share": [round(arab[h] / final, 4) for h in out_hours],
        "national_share": [round(nat[h] / nat["22:00"], 4) for h in out_hours],
        "sigma": [round(s, 4) for s in sigma],
        "z": Z80,
        "units": "percent of eligible voters (turnout so far); arab_share = share of the day's final turnout",
        "source": ("national: CEC hourly turnout 2022 (pipeline/reference/turnout_hourly.json). Arab: aChord Center "
                   "(Hebrew University) estimates during the day, 14:00 17%, 16:00 23%, 20:00 44%; 18:00 30% reported "
                   "without attribution; 22:00 = the official final turnout of Arab and Druze localities (53.2%); "
                   "10:00 and 12:00 modelled from the Arab/national ratio, 19:00 interpolated. Not official."),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "site", "data", "arab_day_2022.json"))
    a = ap.parse_args()
    core = json.load(open(os.path.join(ROOT, "site", "data", "core.json"), encoding="utf-8"))
    b25 = json.load(open(os.path.join(ROOT, "site", "data", "ballots_K25.json"), encoding="utf-8"))
    ref = json.load(open(os.path.join(ROOT, "pipeline", "reference", "turnout_hourly.json"), encoding="utf-8"))
    with open(os.path.join(ROOT, "pipeline", "reference", "arab_localities.csv"), encoding="utf-8") as f:
        committee = {int(r["locality_code"]): (r.get("cec_committee_k25") or "").strip() or None
                     for r in csv.DictReader(f)}
    el25 = next(e for e in core["elections"] if e["id"] == "K25")
    list_name = {p["id"]: p["name"] for p in el25["parties"]}
    loc = {L["code"]: L for L in core["localities"]}
    cols = b25["cols"]
    subnames = {**core["arab_regions"], **core["druze_regions"]}

    acc = {}
    for row in b25["rows"]:
        code, kalpi, sc, elig, voters, valid = row[:6]
        L = loc.get(code)
        sec = L["sector"] if L else "jewish"
        if sec in ("arab", "druze"):
            if L["region"] == "circassian":
                continue
            key, kind = str(code), sec
        elif sc % 10 == 1:
            key, kind = f"{code}:arab", "mixed_arab"
        else:
            continue
        e = acc.setdefault(key, {"code": code, "kind": kind, "elig": 0, "voters": 0, "valid": 0, "stations": 0,
                                 "votes": collections.Counter()})
        e["elig"] += elig; e["voters"] += voters; e["valid"] += valid; e["stations"] += 1
        for c, v in zip(cols, row[6:]):
            e["votes"][c] += v

    entries = []
    for key, e in acc.items():
        L = loc[e["code"]]
        sh = {c: v / e["valid"] for c, v in e["votes"].items()} if e["valid"] else {}
        raam = sum(sh.get(c, 0) for c in RAAM)
        hadash, balad = sh.get("ום", 0), sh.get("ד", 0)
        joint = hadash + balad
        top = max(((c, s) for c, s in sh.items() if c not in RAAM + JOINT + ["other"]), key=lambda x: x[1],
                  default=(None, 0))
        if top[1] > max(raam, joint):
            leader = "other"
        else:
            leader = "raam" if raam > joint else "joint"
        ranked = sorted([raam, joint, top[1]], reverse=True)
        sub = L["region"] if e["kind"] != "mixed_arab" else "mixed"
        lat, lon = (None, None) if L.get("tribe") else (L.get("lat"), L.get("lng"))
        name = L["name"] if e["kind"] != "mixed_arab" else f"{L['name']} (קלפיות ערביות)"
        entries.append({
            "code": e["code"], "key": key, "name": name, "city": L["name"],
            "region": region_of(e["kind"], sub, e["code"], committee.get(e["code"]), L.get("lat")),
            "sub": sub, "kind": e["kind"],
            "elig22": e["elig"], "voters22": e["voters"],
            "turnout22": round(e["voters"] / e["elig"], 4) if e["elig"] else None,
            "stations22": e["stations"], "leader22": leader,
            "raam22": round(raam, 4), "joint22": round(joint, 4), "hadash_taal22": round(hadash, 4),
            "balad22": round(balad, 4), "other22": round(1 - raam - joint, 4),
            "margin22": round(ranked[0] - ranked[1], 4),
            "top_other22": {"id": top[0], "name": list_name.get(top[0], top[0]), "share": round(top[1], 4)}
            if top[0] else None,
            "lat": lat, "lon": lon, "tribe": bool(L.get("tribe")),
        })
    entries.sort(key=lambda x: (-x["elig22"], x["key"]))
    watch = 0
    for i, x in enumerate(entries):
        x["rank"] = i + 1
        x["watch"] = x["kind"] == "arab" and watch < WATCH
        watch += x["watch"]

    def agg(sel):
        out = {}
        for x in entries:
            g = out.setdefault(sel(x), {"elig22": 0, "voters22": 0, "localities": 0, "stations22": 0})
            g["elig22"] += x["elig22"]; g["voters22"] += x["voters22"]
            g["localities"] += 1; g["stations22"] += x["stations22"]
        for g in out.values():
            g["turnout22"] = round(g["voters22"] / g["elig22"], 4) if g["elig22"] else None
        return dict(sorted(out.items()))

    groups, regions, kinds = agg(lambda x: x["leader22"]), agg(lambda x: x["region"]), agg(lambda x: x["kind"])
    total = agg(lambda x: "all")["all"]
    std = [x for x in entries if x["kind"] != "mixed_arab"]
    std_t = sum(x["voters22"] for x in std) / sum(x["elig22"] for x in std)
    curve = build_curve(ref)
    # the 2022 curve of each part and of the whole section, so that a release is compared like with like: the Arab
    # and Druze localities follow the curve itself; the Arab stations of mixed cities take the same timing (no hourly
    # figures of their own) on their own final; the section is the two weighted by their 2022 voters
    shares = {"arab_druze": curve["arab_share"], "mixed_arab": curve["arab_share"]}
    v22 = {"arab_druze": sum(x["voters22"] for x in std), "mixed_arab": kinds.get("mixed_arab", {}).get("voters22", 0)}
    w = {k: v / sum(v22.values()) for k, v in v22.items()}
    section_share = [sum(w[k] * shares[k][i] for k in w) for i in range(len(curve["hours"]))]
    if "mixed_arab" in kinds:
        curve["mixed_arab"] = [round(100 * s * kinds["mixed_arab"]["turnout22"], 1) for s in shares["mixed_arab"]]
    curve["section"] = [round(100 * s * total["turnout22"], 1) for s in section_share]
    curve["section_weights"] = {k: round(v, 4) for k, v in w.items()}
    curve["units"] = ("percent of eligible voters (turnout so far): arab = the Arab and Druze localities, mixed_arab = "
                      "the Arab stations of mixed cities, section = both, national = the whole country; arab_share = "
                      "share of the day's final turnout")
    for k, name in REGION_NAMES.items():
        if k in regions:
            regions[k]["name"] = name
    for k, name in KIND_NAMES.items():
        if k in kinds:
            kinds[k]["name"] = name
    for k, name in GROUP_NAMES.items():
        if k in groups:
            groups[k]["name"] = name
    doc = {
        "generated": "pipeline/build_arab_day.py from site/data/core.json and site/data/ballots_K25.json "
                     "(official CEC results of 1.11.2022)",
        "note": NOTE_HE,
        "method": ("2022 base of the election-day Arab-society section. Localities as the site classifies them: Arab "
                   "and Druze localities (sector of core.json; the two Circassian villages left out) and, as one entry "
                   "per city, the Arab polling stations of mixed cities and Jewish localities (box rule of "
                   "build_data.py, as live_fetch reads per-station turnout). Turnout = station voters / eligible "
                   "voters, without double envelopes. Shares are of valid votes; joint22 = Hadash-Ta'al + Balad, "
                   "which run together in 2026 as the Joint List; leader22 = the larger of raam22 and joint22, or "
                   "'other' where a single non-Arab list led. Regions are geographic (see build_arab_day.py). The "
                   "hourly Arab curve of 2022 is built from unofficial estimates (aChord Center, Hebrew University: "
                   "14:00 17%, 16:00 23%, 20:00 44%; 18:00 30% reported without attribution) and the official final "
                   "53.2%, with the morning modelled; a projected final from a release at hour h divides turnout so "
                   "far by the 2022 share of the day's turnout cast by h, with a rough 80% range that is twice the "
                   "spread of the national curve across 2013-2022. It assumes 2026 keeps the 2022 Arab timing, which "
                   "is the main uncertainty (a sixth of the 2022 Arab vote came after 20:00). The Druze localities "
                   "and the Arab stations of mixed cities have no hourly figures of their own and are given the same "
                   "timing on their own 2022 final, for the same-hour comparison, on_track and the range alike "
                   "(curve.mixed_arab; curve.section is the whole section, the two weighted by 2022 voters). Turnout "
                   "only: nothing here is translated into votes or seats. Details: pipeline/arab_turnout.py."),
        "units": {"turnout": "fraction", "shares": "fraction of valid votes", "curve": "percent"},
        "region_names": REGION_NAMES, "kind_names": KIND_NAMES, "group_names": GROUP_NAMES, "group_short": GROUP_SHORT,
        "sub_names": subnames,
        "localities": entries,
        "groups": groups, "regions": regions, "kinds": kinds,
        "total": {**total, "turnout22_standard": round(std_t, 4)},
        "curve": curve,
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    report(doc)
    print(f"wrote {a.out}: {len(entries)} entries, {os.path.getsize(a.out):,} bytes")


def report(doc):
    E = doc["localities"]
    t = doc["total"]
    print(f"total: {t['localities']} entries, elig {t['elig22']:,}, turnout {t['turnout22']:.1%} "
          f"(Arab+Druze localities {t['turnout22_standard']:.1%})")
    for name in ("groups", "regions", "kinds"):
        print(f"{name}: " + "; ".join(f"{k} {g['localities']} loc, elig {g['elig22']:,}, {g['turnout22']:.1%}"
                                       for k, g in doc[name].items()))
    by = collections.Counter((x["region"], x["leader22"]) for x in E)
    print("leader by region: " + "; ".join(f"{r}: " + ", ".join(f"{g} {by[(r, g)]}" for g in ("raam", "joint", "other")
                                                                   if by[(r, g)]) for r in doc["regions"]))
    print("20 largest:")
    for x in E[:20]:
        print(f"  {x['rank']:>2} {x['name']:<28} {x['kind']:<10} {x['region']:<9} elig {x['elig22']:>6,} "
              f"turnout {x['turnout22']:.1%} raam {x['raam22']:.1%} joint {x['joint22']:.1%} "
              f"-> {x['leader22']} by {x['margin22']:.1%}{' watch' if x['watch'] else ''}")
    c = doc["curve"]
    print("curve: " + ", ".join(f"{h} {a}%/{n}% ({k}, f={s:.3f}, sigma={g:.3f})" for h, a, n, k, s, g in
                                zip(c["hours"], c["arab"], c["national"], c["arab_kind"], c["arab_share"], c["sigma"])))
    print("section curve: " + ", ".join(f"{h} {s}% (mixed-city Arab stations {m}%)" for h, s, m in
                                        zip(c["hours"], c["section"], c.get("mixed_arab", c["section"])))
          + f"; weights {c['section_weights']}")


if __name__ == "__main__":
    main()
