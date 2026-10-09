"""Final pre-election polls for K21–K25 → site/data/final_polls.json.

Input: a JSON file of the last published polls before each election (fieldwork
in the final ~5 days before the Friday publication cut-off), one record per
poll with seats per list as published by the media outlet. Lists are mapped to
the election's official ballot letters so they can be compared with the
official CEC seat results in core.json.
"""
import argparse
import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYS = {"2019a": "K21", "2019s": "K22", "2019b": "K22", "2020": "K23", "2021": "K24", "2022": "K25"}
NAME_TO_LETTER = {
    "K21": {"Blue and White": "פה", "Likud": "מחל", "Shas": "שס", "UTJ": "ג", "Hadash-Ta'al": "ום", "Labor": "אמת",
            "URWP (Union of Right-Wing Parties)": "טב", "Yisrael Beiteinu": "ל", "Kulanu": "כ", "Meretz": "מרצ",
            "Ra'am-Balad": "דעם", "Gesher": "נר", "New Right": "נ", "Zehut": "ז"},
    "K22": {"Blue and White": "פה", "Likud": "מחל", "Joint List": "ודעם", "Shas": "שס", "Yisrael Beiteinu": "ל",
            "UTJ": "ג", "Yamina": "טב", "Labor-Gesher": "אמת", "Democratic Union": "מרצ", "Otzma Yehudit": "כף"},
    "K23": {"Likud": "מחל", "Blue and White": "פה", "Joint List": "ודעם", "Shas": "שס", "Labor-Gesher-Meretz": "אמת",
            "UTJ": "ג", "Yisrael Beiteinu": "ל", "Yamina": "טב", "Otzma Yehudit": "נץ"},
    "K24": {"Likud": "מחל", "Yesh Atid": "פה", "Shas": "שס", "Blue and White": "כן", "Labor": "אמת", "UTJ": "ג",
            "Yamina": "ב", "Yisrael Beiteinu": "ל", "Joint List": "ודעם", "Meretz": "מרצ", "New Hope": "ת",
            "Religious Zionism": "ט", "Ra'am": "עם", "New Economic Party": "יז"},
    "K25": {"Likud": "מחל", "Yesh Atid": "פה", "Religious Zionism (RZP-Otzma-Noam)": "ט", "National Unity": "כן",
            "Shas": "שס", "UTJ": "ג", "Yisrael Beiteinu": "ל", "Hadash-Ta'al": "ום", "Ra'am": "עם", "Labor": "אמת",
            "Balad": "ד", "Jewish Home": "ב", "Meretz": "מרצ"},
}
POLLSTER_HE = {
    "Midgam": "מדגם", "Midgam Project": "מדגם פרויקט", "Dialog": "דיאלוג", "Panels Politics": "פאנלס פוליטיקס",
    "Maagar Mochot": "מאגר מוחות", "Miskar": "מסקר", "Smith Consulting": "סמית", "TNS (later Kantar)": "TNS",
    "Kantar": "קנטאר", "Kantar (Dudi Hasid)": "קנטאר", "Shvakim Panorama": "שווקים פנורמה", "Direct Polls": "דיירקט פולס",
    "Camil Fuchs": "קמיל פוקס", "Panels Politics (Menachem Lazar / Panel4All)": "פאנלס (לזר)",
}


def main(src, core_path, out):
    raw = json.load(open(src, encoding="utf-8"))
    core = json.load(open(core_path, encoding="utf-8"))
    actual = {e["id"]: {p["id"]: p["seats"] for p in e["parties"]} for e in core["elections"]}
    doc = {"source": "סקרים אחרונים שפורסמו בכלי התקשורת לפני כל מערכת בחירות (ריכוז: טבלאות הסקרים בוויקיפדיה, "
                     "שתי סריקות עצמאיות זהות; כותרות מרכזיות אומתו מול דיווחי חדשות)", "elections": []}
    for key, polls in raw.items():
        eid = KEYS[key]
        names = NAME_TO_LETTER[eid]
        rows, seen = [], {}
        for p in polls:
            # One 2021 row is seat-for-seat identical to another house's poll of the same day
            # in both independent scrapes; a likely transcription duplicate, so it is dropped.
            sig = (p["date"], p["seats_json"])
            if sig in seen:
                print(f"{eid}: dropped duplicate {p['date']} {p['pollster']} (= {seen[sig]})")
                continue
            seen[sig] = p["pollster"]
            seats = json.loads(p["seats_json"])
            mapped = {}
            for name, v in seats.items():
                if name not in names:
                    raise KeyError(f"{eid}: unmapped list {name}")
                mapped[names[name]] = int(v)
            if sum(mapped.values()) != 120:
                raise ValueError(f"{eid} {p['date']} {p['pollster']}: sums to {sum(mapped.values())}")
            rows.append({"date": p["date"], "pollster": p["pollster"],
                         "pollster_he": POLLSTER_HE.get(p["pollster"], p["pollster"]),
                         "outlet": p.get("outlet", ""), "seats": mapped,
                         "confidence": "high" if p.get("confidence", "").startswith("high") else "medium"})
        letters = sorted({k for r in rows for k in r["seats"]} | {k for k, v in actual[eid].items() if v})
        avg = {k: round(statistics.mean(r["seats"].get(k, 0) for r in rows), 2) for k in letters}
        err = {k: round(avg[k] - actual[eid].get(k, 0), 2) for k in letters}
        doc["elections"].append({"id": eid, "polls": rows, "avg": avg, "actual": {k: actual[eid].get(k, 0) for k in letters},
                                 "error": err, "mae": round(statistics.mean(abs(v) for v in err.values()), 2)})
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    for e in doc["elections"]:
        print(e["id"], len(e["polls"]), "polls, MAE", e["mae"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--core", default=os.path.join(ROOT, "site", "data", "core.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "site", "data", "final_polls.json"))
    a = ap.parse_args()
    main(a.src, a.core, a.out)
