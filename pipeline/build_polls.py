"""Normalise 2026 seat polls into site/data/polls_2026.json.

Source records: one row per published poll (fieldwork date, pollster, outlet,
seats per list). Where the poll filing published by the Central Elections
Committee was located, the record carries its URL plus the filing's raw vote shares,
sample size and margin of error. Records are treated as data: every poll must
apportion exactly 120 seats or it is dropped and reported.

Run: python3 pipeline/build_polls.py --src polls-data.js
"""
import argparse
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# id -> (Hebrew name, leader, default bloc, light colour, dark colour)
# Bloc "coal" = parties of the outgoing Netanyahu government; "arab" = Arab-led
# lists; "opp" = the rest. The UI lets the reader move any list.
PARTIES_2026 = {
    "Likud":            ("הליכוד", "בנימין נתניהו", "coal", "#1d4ed8", "#5b8cff"),
    "Yashar":           ("ישר!", "גדי איזנקוט", "opp", "#0f766e", "#2dd4bf"),
    "Together":         ("ביחד", "נפתלי בנט ויאיר לפיד", "opp", "#0891b2", "#38bdf8"),
    "The Democrats":    ("הדמוקרטים", "יאיר גולן", "opp", "#dc2626", "#f87171"),
    "Yisrael Beiteinu": ("ישראל ביתנו", "אביגדור ליברמן", "opp", "#7c3aed", "#a78bfa"),
    "Shas":             ("ש״ס", "אריה דרעי", "coal", "#3f3f46", "#c4c4cc"),
    "UTJ":              ("יהדות התורה", "יצחק גולדקנופף", "coal", "#0f172a", "#e2e8f0"),
    "Otzma Yehudit":    ("עוצמה יהודית", "איתמר בן גביר", "coal", "#ca8a04", "#facc15"),
    "Religious Zionism":("הציונות הדתית", "בצלאל סמוטריץ׳", "coal", "#b45309", "#fb923c"),
    "Joint List":       ("הרשימה המשותפת", "חד״ש-תע״ל ובל״ד", "arab", "#047857", "#34d399"),
    "Ra'am":            ("רע״ם", "מנסור עבאס", "arab", "#4d7c0f", "#a3e635"),
    "Amcha Yisrael":    ("עמך ישראל", "עופר וינטר", "coal", "#9a3412", "#fdba74"),
    "Reservists":       ("המילואימניקים", "יועז הנדל וחילי טרופר", "opp", "#57534e", "#d6d3d1"),
    "National Unity":   ("כחול לבן", "בני גנץ", "opp", "#4f46e5", "#a5b4fc"),
    "Haredi Public":    ("הציבור החרדי", "מוטי לייטנר", "coal", "#52525b", "#a1a1aa"),
}
# Official 2026 ballot letters (CEC list approval, 27 Sep 2026).
LETTERS_2026 = {
    "Likud": "מחל", "Yashar": "דרך", "Together": "רק", "The Democrats": "אמת",
    "Yisrael Beiteinu": "ל", "Shas": "שס", "UTJ": "ג", "Otzma Yehudit": "ב",
    "Religious Zionism": "ט", "Joint List": "ודם", "Ra'am": "עם", "Amcha Yisrael": "ך",
    "Reservists": "די", "National Unity": "כן", "Haredi Public": "זך",
}
# Columns that are halves of a list now running jointly: summed into it.
FOLD = {"Hadash-Ta'al": "Joint List", "Balad": "Joint List"}
DROP = {"Yesh Atid", "Bennett 2026", "Yesodot Yisrael", "Unity"}  # superseded or withdrawn

OUTLET_HE = {
    "Channel 12 (HaHadashot 12)": "חדשות 12", "Channel 13": "חדשות 13", "Channel 14": "ערוץ 14",
    "Channel 14 (Direct Polls)": "ערוץ 14", "Israel Hayom": "ישראל היום", "Kan 11": "כאן 11",
    "Maariv": "מעריב", "Zman Israel / Times of Israel": "זמן ישראל", "i24NEWS": "i24NEWS",
    "Walla": "וואלה", "": "—",
}
# Kantar polls are broadcast by Kan 11 (kan.org.il publishes them); the source table labels them Israel Hayom.
OUTLET_BY_POLLSTER = {"Kantar": "כאן 11"}
POLLSTER_HE = {
    "Midgam": "מדגם", "Kantar": "קנטאר", "Lazar": "לזר", "Maagar Mochot": "מאגר מוחות",
    "Direct Polls": "דיירקט פולס", "Filber": "פילבר", "S.M.L.T.": "S.M.L.T.",
    "Yossi Tatika": "יוסי טטיקה", "LRI+P4A": "לזר + פאנל4אול", "SF+ND": "פילבר + נקסט דאטה",
    "MP+TM+SN+A": "מאגר מוחות + שותפים", "Filber, NEXT DATA": "פילבר + נקסט דאטה",
}


# The same poll is sometimes recorded twice under two names for one polling
# operation (Filber = SF+ND for Channel 14, Lazar = LRI+P4A for Maariv/Walla,
# Midgam = MP+TM+SN+A for Channel 13). Two records with identical non-zero
# seats within two days are treated as one poll; the record carrying the CEC
# filing (or a sample size) is kept.
def dedupe(polls):
    from datetime import date
    kept, dropped = [], []
    for p in polls:
        key = {k: v for k, v in p["seats"].items() if v}
        twin = next((q for q in kept if {k: v for k, v in q["seats"].items() if v} == key
                     and abs((date.fromisoformat(q["date"]) - date.fromisoformat(p["date"])).days) <= 2), None)
        if twin is None:
            kept.append(p)
            continue
        better = p if (p["filing"] and not twin["filing"]) or (not twin["n"] and p["n"]) else twin
        worse = twin if better is p else p
        if better is p:
            kept[kept.index(twin)] = p
        dropped.append(f"duplicate: {worse['date']} {worse['pollster']} = {better['date']} {better['pollster']}")
    return kept, dropped


def load_js(path):
    out = subprocess.run(
        ["node", "-e", "const fs=require('fs');const w={};new Function('window',fs.readFileSync(process.argv[1],'utf8'))(w);"
                       "process.stdout.write(JSON.stringify(w.BASE_POLLS_DATA))", path],
        check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def build(src, out):
    raw = load_js(src)
    polls, dropped = [], []
    for p in raw:
        seats = {}
        for k, v in p.items():
            if not isinstance(v, (int, float)) or k.startswith("_") or k in (
                    "sampleSize", "respondents", "invited", "responseRate", "refusedPct",
                    "marginOfError", "undecidedPct", "wastedPct"):
                continue
            if k in DROP:
                if v:
                    seats.setdefault("_dropped", 0)
                    seats["_dropped"] += v
                continue
            key = FOLD.get(k, k)
            if key not in PARTIES_2026:
                continue
            seats[key] = seats.get(key, 0) + int(v)
        total = sum(v for k, v in seats.items() if not k.startswith("_"))
        if total != 120 or seats.get("_dropped"):
            dropped.append(f"{p['date']} {p['pollster']}: total={total} dropped={seats.get('_dropped', 0)}")
            continue
        pct = {FOLD.get(k, k): v for k, v in (p.get("pct") or {}).items() if FOLD.get(k, k) in PARTIES_2026}
        polls.append({
            "date": p["date"], "fieldwork": p.get("fieldworkDate") or p["date"],
            "pollster": p["pollster"], "pollster_he": POLLSTER_HE.get(p["pollster"], p["pollster"]),
            "outlet": p.get("outlet", ""),
            "outlet_he": OUTLET_BY_POLLSTER.get(p["pollster"]) or OUTLET_HE.get(p.get("outlet", ""), p.get("outlet", "")),
            "n": p.get("respondents") or p.get("sampleSize"),
            "moe": p.get("marginOfError"),
            "seats": seats, "pct": pct or None,
            "filing": p.get("govilSourceUrl"),
        })
    polls.sort(key=lambda x: (x["date"], x["pollster"]))
    polls, dupes = dedupe(polls)
    dropped += dupes
    doc = {
        "parties": [{"id": k, "name": v[0], "leader": v[1], "bloc": v[2], "color": v[3], "dark": v[4],
                     "letters": LETTERS_2026.get(k, "")}
                    for k, v in PARTIES_2026.items()],
        "polls": polls,
        "dropped": dropped,
        "source": "רשומות סקרים שפורסמו (טבלת הסקרים בוויקיפדיה), מוצלבות מול קובצי הדיווח על סקרים "
                  "שמפרסמת ועדת הבחירות המרכזית ב-gov.il, כשנמצאו",
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    return len(polls), dropped


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "site", "data", "polls_2026.json"))
    a = ap.parse_args()
    n, d = build(a.src, a.out)
    print(f"{n} polls written; dropped: {d}")
