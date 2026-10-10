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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# id -> (Hebrew name, leader, default bloc, light colour, dark colour)
# Bloc "coal" = parties of the outgoing Netanyahu government; "arab" = Arab-led
# lists; "opp" = the rest. The UI lets the reader move any list.
PARTIES_2026 = {
    "Likud":            ("הליכוד", "בנימין נתניהו", "coal", "#1d4ed8", "#5b8cff"),
    "Yashar":           ("ישר!", "גדי איזנקוט", "opp", "#be185d", "#f472b6"),
    "Together":         ("ביחד", "נפתלי בנט ויאיר לפיד", "opp", "#0891b2", "#38bdf8"),
    "The Democrats":    ("הדמוקרטים", "יאיר גולן", "opp", "#dc2626", "#f87171"),
    "Yisrael Beiteinu": ("ישראל ביתנו", "אביגדור ליברמן", "opp", "#4c1d95", "#ddd6fe"),
    "Shas":             ("ש״ס", "אריה דרעי", "coal", "#52525b", "#8b8b94"),
    "UTJ":              ("יהדות התורה", "יצחק גולדקנופף", "coal", "#0f172a", "#e2e8f0"),
    "Otzma Yehudit":    ("עוצמה יהודית", "איתמר בן גביר", "coal", "#ca8a04", "#eab308"),
    "Religious Zionism":("הציונות הדתית", "בצלאל סמוטריץ׳", "coal", "#b45309", "#c2410c"),
    "Joint List":       ("הרשימה המשותפת", "חד״ש-תע״ל ובל״ד", "arab", "#065f46", "#059669"),
    "Ra'am":            ("רע״ם", "מנסור עבאס", "arab", "#65a30d", "#a3e635"),
    "Amcha Yisrael":    ("עמך ישראל", "עופר וינטר", "coal", "#78350f", "#c08457"),
    "Reservists":       ("המילואימניקים", "יועז הנדל וחילי טרופר", "opp", "#0d9488", "#2dd4bf"),
    "National Unity":   ("כחול לבן", "בני גנץ", "opp", "#4f46e5", "#a5b4fc"),
    "Haredi Public":    ("הציבור החרדי", "מוטי לייטנר", "coal", "#78716c", "#a8a29e"),
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
# One polling operation sometimes appears under several labels; weights and
# house effects are computed per canonical house.
def house_of(pollster, outlet):
    if pollster in ("Filber", "SF+ND", "Filber, NEXT DATA"):
        return "filber", "פילבר (ערוץ 14)"
    if pollster in ("Lazar", "LRI+P4A"):
        return "lazar", "לזר / פאנל4אול"
    if pollster == "MP+TM+SN+A" or (pollster == "Midgam" and outlet.startswith("Channel 13")):
        return "ch13", "מדגם פרויקט וסטטנט (חדשות 13)"
    if pollster == "Midgam":
        return "midgam", "מדגם (חדשות 12)"
    return pollster.lower().replace(" ", "-").replace(".", ""), None


# Firms that run more than one house: Filber's company Direct Polls also polls for i24NEWS.
# The houses keep separate house effects (their numbers differ by outlet), but the
# per-firm damping in the average counts them together.
FIRM_OF_HOUSE = {"direct-polls": "filber"}


# Kantar polls are broadcast by Kan 11 (kan.org.il publishes them); the source table labels them Israel Hayom.
OUTLET_BY_POLLSTER = {"Kantar": "כאן 11"}
POLLSTER_HE = {
    "Midgam": "מדגם", "Kantar": "קנטאר", "Lazar": "לזר", "Maagar Mochot": "מאגר מוחות",
    "Direct Polls": "דיירקט פולס", "Filber": "פילבר", "S.M.L.T.": "S.M.L.T.",
    "Yossi Tatika": "יוסי טטיקה", "LRI+P4A": "לזר + פאנל4אול", "SF+ND": "פילבר + נקסט דאטה",
    "MP+TM+SN+A": "מדגם פרויקט וסטטנט", "Filber, NEXT DATA": "פילבר + נקסט דאטה",
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
    """The poll records of polls-data.js, a third party's file: the JSON array assigned to
    window.BASE_POLLS_DATA, read as data. Nothing in the file is ever executed (no node): the
    workflows that build from it hold write credentials (official-data.yml) or hand the result to
    a job that does (daily.yml). Anything other than a plain JSON array of records there (code, a
    NaN or Infinity, a missing assignment) raises, so a changed or tampered file fails closed."""
    with open(path, encoding="utf-8-sig") as f:
        s = f.read()
    m = re.search(r"window\.BASE_POLLS_DATA\s*=\s*", s)
    if not m:
        raise ValueError(f"{path}: no 'window.BASE_POLLS_DATA = [...]' in the file")

    def no_constant(x):
        raise ValueError(f"{path}: {x} in BASE_POLLS_DATA is not JSON")
    try:
        data, _ = json.JSONDecoder(parse_constant=no_constant).raw_decode(s, m.end())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: BASE_POLLS_DATA is not a JSON array ({exc})") from None
    if not isinstance(data, list) or not all(isinstance(p, dict) for p in data):
        raise ValueError(f"{path}: BASE_POLLS_DATA is not a list of poll records")
    return data


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
        filing, n, moe = p.get("govilSourceUrl"), p.get("respondents") or p.get("sampleSize"), p.get("marginOfError")
        fieldwork = p.get("fieldworkDate") or p["date"]
        if fieldwork > p["date"]:
            # a filing dated after publication belongs to a different poll: drop the enrichment
            dropped.append(f"filing mismatch: {p['date']} {p['pollster']} (filing fieldwork {fieldwork})")
            filing, pct, moe, fieldwork, n = None, {}, None, p["date"], p.get("sampleSize")
        if moe and n and moe < 0.8 * 98 / (n ** 0.5):
            moe = None  # below the sampling minimum for this n: a parsing error
        house, house_he = house_of(p["pollster"], p.get("outlet", ""))
        polls.append({
            "date": p["date"], "fieldwork": fieldwork,
            "pollster": p["pollster"], "pollster_he": POLLSTER_HE.get(p["pollster"], p["pollster"]),
            "house": house, "firm": FIRM_OF_HOUSE.get(house, house), "house_he": house_he or POLLSTER_HE.get(p["pollster"], p["pollster"]),
            "outlet": p.get("outlet", ""),
            "outlet_he": OUTLET_BY_POLLSTER.get(p["pollster"]) or OUTLET_HE.get(p.get("outlet", ""), p.get("outlet", "")),
            "n": n, "moe": moe,
            "seats": seats, "pct": pct or None,
            "filing": filing,
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
