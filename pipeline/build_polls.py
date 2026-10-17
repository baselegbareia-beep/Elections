"""Normalise 2026 seat polls into site/data/polls_2026.json.

Source records: one row per published poll (fieldwork date, pollster, outlet,
seats per list). Where the poll filing published by the Central Elections
Committee was located, the record carries its URL plus the filing's raw vote shares,
sample size and margin of error. Records are treated as data: every poll must
apportion exactly 120 seats or it is dropped and reported.

The CEC filings matched to the polls (site/data/poll_filings_2026.json, pipeline/build_poll_filings.py, read from
the PDFs themselves) are attached next: every poll carries "official", its filing (address, item, number, publication
date, verified or not, and when not, why: "doubts", the seats that differ) or null when none was found, and the
table "filings", the date of the fetch. A poll whose link in polls-data.js is another poll's filing (a conflict there
with the verdict "matched") gets its own filing's address, and what polls-data.js read from the wrong PDF goes: when
its own filing is verified, its respondents, margin of error, end of fieldwork and raw shares (a complete set only)
take the place of the wrong ones; when not, they are dropped (n back to the poll's own sample size), as for a filing
mismatch below. The same holds for a link to another filing than the match with no verdict on it, when the match is
verified, or when the table the file was built from linked the match (the file rebuilt from a table already
corrected). "corrected" lists each change (field, old, new, why). Seats never change: the seat table is the poll's,
and its filing's. Without the file, or with one that is not what that script writes, the table is built as before it
(no "official", no "filings"), with a warning. poll_filings_2026.json is best rebuilt from the table as polls-data.js
gives it (--filings '' into a scratch file, then build_poll_filings.py --polls with it), so that its conflicts keep
naming the wrong links and their verdicts.

Run: python3 pipeline/build_polls.py --src polls-data.js [--filings site/data/poll_filings_2026.json | --filings '']
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILINGS = os.path.join(ROOT, "site", "data", "poll_filings_2026.json")

# id -> (Hebrew name, leader, default bloc, light colour, dark colour)
# Bloc "coal" = parties of the outgoing Netanyahu government; "arab" = Arab-led
# lists; "opp" = the rest. The UI lets the reader move any list. The leader is the
# head of the list as submitted to the CEC (for Together and the Reservists the first
# two, who lead the two parties that formed the list); the official names, the first
# candidates and the sources: pipeline/reference/lists_2026.json.
PARTIES_2026 = {
    "Likud":            ("הליכוד", "בנימין נתניהו", "coal", "#1d4ed8", "#5b8cff"),
    "Yashar":           ("ישר!", "גדי איזנקוט", "opp", "#be185d", "#f472b6"),
    "Together":         ("ביחד", "נפתלי בנט ויאיר לפיד", "opp", "#0891b2", "#38bdf8"),
    "The Democrats":    ("הדמוקרטים", "יאיר גולן", "opp", "#dc2626", "#f87171"),
    "Yisrael Beiteinu": ("ישראל ביתנו", "אביגדור ליברמן", "opp", "#4c1d95", "#ddd6fe"),
    "Shas":             ("ש״ס", "אריה דרעי", "coal", "#52525b", "#8b8b94"),
    "UTJ":              ("יהדות התורה", "יעקב אשר", "coal", "#0f172a", "#e2e8f0"),
    "Otzma Yehudit":    ("עוצמה יהודית", "איתמר בן גביר", "coal", "#ca8a04", "#eab308"),
    "Religious Zionism":("הציונות הדתית", "בצלאל סמוטריץ׳", "coal", "#b45309", "#c2410c"),
    "Joint List":       ("הרשימה המשותפת", "יוסף ג׳בארין", "arab", "#065f46", "#059669"),
    "Ra'am":            ("רע״ם", "מנסור עבאס", "arab", "#65a30d", "#a3e635"),
    "Amcha Yisrael":    ("עמך ישראל", "עופר וינטר", "coal", "#78350f", "#c08457"),
    "Reservists":       ("המילואימניקים", "יועז הנדל וירון זליכה", "opp", "#0d9488", "#2dd4bf"),
    "National Unity":   ("כחול לבן", "בני גנץ", "opp", "#4f46e5", "#a5b4fc"),
    "Haredi Public":    ("הציבור החרדי", "מוטי ליטנר", "coal", "#78716c", "#a8a29e"),
}
# Official 2026 ballot letters (CEC list approval, 27 Sep 2026): the column headers of the CEC's results files,
# which the election-night feed reads by these letters. Checked against pipeline/reference/lists_2026.json
# (pipeline/test_live.py, 11c) and, from a runner, against the CEC's own pages (pipeline/fetchers/cec_lists.py).
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


# ------------------------------------------------------------------ the CEC filings (poll_filings_2026.json)
FILING_URL = re.compile(r"https://www\.gov\.il/BlobFolder/dynamiccollectorresultitem/(knesset_election\d{1,4})/he/"
                        r"[^\s?#\"'<>\\`]{1,300}")
COLLECTOR_URL = re.compile(r"https://www\.gov\.il/he/departments/dynamiccollectors/\w{1,80}")
VERDICTS = ("matched", "link", "both", "unclear")
# why a matched filing is not verified as the poll's (the page words each): its seat table, the pollster the PDF
# names, its fieldwork dates, its respondents, the PDF not read here (third parties' readings only), anything else
DOUBTS = ("seats", "pollster", "fieldwork", "respondents", "unread", "other")
try:
    from zoneinfo import ZoneInfo
    IL = ZoneInfo("Asia/Jerusalem")
except Exception:                                   # no tz data: summer time (UTC+3) until 25.10.2026
    IL = dt.timezone(dt.timedelta(hours=3))


def item_of(url):
    """the filing's item (knesset_election<N>) in a gov.il filing address, else None"""
    m = FILING_URL.fullmatch((url or "").strip()) if isinstance(url, str) else None
    return m.group(1) if m else None


def is_num(x, lo, hi):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and lo <= x <= hi


def is_day(x):
    try:
        return isinstance(x, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", x) and bool(dt.date.fromisoformat(x))
    except ValueError:
        return False


def load_filings(path):
    """poll_filings_2026.json as build() uses it: {"rows": {poll key: row}, "conflicts": {poll key: conflict},
    "ambiguous": keys that name two rows or conflicts, "fetched": the Israel date of the latest fetch (None for the
    reference alone), "collector"}. Every value taken into the table is checked here: anything else than what
    pipeline/build_poll_filings.py writes raises ValueError, and the table is then built without the file."""
    def no_constant(x):
        raise ValueError(f"{x} is not JSON")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f, parse_constant=no_constant)
    if not (isinstance(doc, dict) and isinstance(doc.get("polls"), list) and isinstance(doc.get("conflicts"), list)
            and isinstance(doc.get("inputs"), dict) and COLLECTOR_URL.fullmatch(str(doc.get("collector")))):
        raise ValueError("not the file pipeline/build_poll_filings.py writes (polls, conflicts, inputs, collector)")
    rows, conflicts, ambiguous = {}, {}, set()
    for r in doc["polls"]:
        f = r.get("filing") if isinstance(r, dict) else None
        fw = r.get("fieldwork") if isinstance(r, dict) else None
        if not (isinstance(f, dict) and isinstance(r.get("key"), str) and item_of(f.get("url"))
                and f.get("item") == item_of(f["url"]) and isinstance(r.get("verified"), bool)
                and (f.get("number") is None or isinstance(f["number"], str) and re.fullmatch(r"\d{1,8}", f["number"]))
                and (f.get("published") is None or is_day(f["published"]))
                and (r.get("n") is None or isinstance(r["n"], int) and is_num(r["n"], 1, 1_000_000))
                and (r.get("moe") is None or is_num(r["moe"], 0.01, 20))
                and (r.get("pct") is None or isinstance(r["pct"], dict)
                     and all(isinstance(k, str) and is_num(v, 0, 100) for k, v in r["pct"].items()))
                and (r.get("pct_total") is None or is_num(r["pct_total"], 0, 200))
                and (fw is None or isinstance(fw, dict) and (fw.get("end") is None or is_day(fw["end"])))
                and (r.get("seat_diff") is None or isinstance(r["seat_diff"], dict) and all(
                    k in PARTIES_2026 and isinstance(v, list) and len(v) == 2
                    and all(isinstance(x, int) and is_num(x, 0, 120) for x in v) for k, v in r["seat_diff"].items()))
                and all(isinstance(x, str) for x in r.get("notes") or [])
                and (r.get("src") is None or isinstance(r["src"], dict))):
            raise ValueError(f"a poll's filing is not as build_poll_filings.py writes it: {str(r)[:100]}")
        if r["key"] in rows:
            ambiguous.add(r["key"])
        rows[r["key"]] = r
    for c in doc["conflicts"]:
        if not (isinstance(c, dict) and isinstance(c.get("key"), str) and c.get("verdict") in VERDICTS
                and (c.get("polls_2026_link") is None or isinstance(c["polls_2026_link"], str))
                and (c.get("matched") is None or isinstance(c["matched"], str))):
            raise ValueError(f"a conflict is not as build_poll_filings.py writes it: {str(c)[:100]}")
        if c["verdict"] == "matched" and (rows.get(c["key"]) or {}).get("filing", {}).get("url") != c["matched"]:
            raise ValueError(f"{c['key']}: the conflict's matched filing is not the one its poll has")
        if c["key"] in conflicts:
            ambiguous.add(c["key"])
        conflicts[c["key"]] = c
    fetched = doc["inputs"].get("fetched") or []
    if not (isinstance(fetched, list) and all(isinstance(x, dict) and isinstance(x.get("started"), (str, type(None)))
                                              for x in fetched)):
        raise ValueError("inputs.fetched: not a list of fetches, each with its start time or none")
    days = []
    for s in (x["started"] for x in fetched if x.get("started")):   # a fetch with no start time gives no date
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))       # ValueError when it is no timestamp
        days.append((t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).astimezone(IL).date().isoformat())
    return {"rows": rows, "conflicts": conflicts, "ambiguous": ambiguous, "fetched": max(days, default=None),
            "collector": doc["collector"]}


def doubts(r):
    """why a matched filing is not verified as the poll's, as DOUBTS codes: from its seats, from where its seat table
    was read (an unread PDF has no note: its values are third parties'), and from build_poll_filings.py's own words
    for the rest ("not verified: ..." in its notes)"""
    why = " ".join(n for n in r.get("notes") or [] if n.startswith("not verified"))
    out = ["seats"] if r.get("seats_equal") is not True else []
    out += [code for code, words in (("pollster", ("pollster", "polling house")), ("fieldwork", ("fieldwork",)),
                                     ("respondents", ("respondents",))) if any(w in why for w in words)]
    if (r.get("src") or {}).get("seats") != "cec_pdf" or "not read" in why or "nothing was read" in why:
        out.append("unread")
    return out or ["other"]


def complete(pct, total, seats):
    """raw shares that are a whole table: one for every list the poll seats, adding up to 95-105% (with the lists
    no poll tracks, as the filing totals them)"""
    total = total if total is not None else sum(pct.values())
    return all(k in pct for k, v in seats.items() if v) and 95 <= total <= 105


def correct(p, r, why, sample):
    """p as its own filing r has it, for a poll that polls-data.js linked to another poll's filing; the changes, in
    the order of the fields (the old values, read from that filing, are replaced or dropped; never the seats)"""
    old, item, ok = item_of(p["filing"]) or "its link", r["filing"]["item"], r["verified"]
    changes = []

    def put(field, new, because):
        if p[field] != new:
            changes.append({"field": field, "old": p[field], "new": new, "why": because})
            p[field] = new
    put("filing", r["filing"]["url"], why)
    wrong = f"{old} is another poll's filing"
    if ok:
        pct = {k: v for k, v in (r.get("pct") or {}).items() if k in PARTIES_2026}
        full = bool(pct) and complete(pct, r.get("pct_total"), p["seats"])
        end = (r.get("fieldwork") or {}).get("end")
        put("n", r.get("n") or sample, f"{wrong}: {item}'s respondents (verified)")
        put("pct", pct if full else None, f"{wrong}: {item}'s raw shares (verified, a complete set)" if full else
            f"{wrong}; {item}'s raw shares are not a complete set: none kept")
        moe = r.get("moe")
        if moe and p["n"] and moe < 0.8 * 98 / (p["n"] ** 0.5):
            moe = None  # below the sampling minimum for this n: a parsing error
        put("moe", moe, f"{wrong}: {item}'s margin of error (verified)" if moe else f"{wrong}: none kept")
        put("fieldwork", min(end, p["date"]) if end else p["date"], f"{wrong}: the end of {item}'s fieldwork")
    else:
        unv = f"{wrong}, and {item} is not verified as this poll's"
        put("n", sample, f"{unv}: the poll's own sample size")
        put("pct", None, f"{unv}: none kept")
        put("moe", None, f"{unv}: none kept")
        put("fieldwork", p["date"], f"{unv}: the publication date")
    return changes


def attach_filings(polls, F, samples):
    """official (and corrected) on every poll from load_filings' F; samples: each poll's own sample size by key.
    Returns the warnings (polls that cannot be told apart, links left as they are without a verdict)."""
    warn = []
    keys = [f"{p['date']}|{p['pollster']}|{p['outlet']}" for p in polls]
    twice = {k for k in keys if keys.count(k) > 1} | F["ambiguous"]
    for p, key in zip(polls, keys):
        r, c = F["rows"].get(key), F["conflicts"].get(key)
        if key in twice:
            r = None
            warn.append(f"{key}: two polls or two filings under one key, no filing attached")
        if c and item_of(c.get("polls_2026_link")) != item_of(p["filing"]):
            c = None                                   # a verdict on another link than the one polls-data.js has now
        if r is None or (c and c["verdict"] == "link"):
            p["official"] = None                       # none found, or the link's filing is the poll's, not the match
            continue
        f = r["filing"]
        p["official"] = {"url": f["url"], "item": f["item"], "number": f.get("number"), "verified": r["verified"],
                         "published": f.get("published")}
        if not r["verified"]:
            p["official"]["doubts"] = doubts(r)
            if r.get("seat_diff"):
                p["official"]["seat_diff"] = r["seat_diff"]       # {list: [the poll's seats, the filing's]}
        linked = item_of(p["filing"])
        if not p["filing"] or linked == f["item"]:
            continue
        if c and c["verdict"] == "matched":
            why = (f"polls-data.js links {linked or 'an address'}, another poll's filing (poll_filings_2026.json: "
                   f"conflict, verdict matched); this poll's is {f['item']}")
        elif c is None and r["verified"]:
            # no verdict on this link (the file built from a table already corrected, or the link changed since):
            # the filing verified as the poll's wins; a re-filing of the same poll would give the same values
            why = (f"polls-data.js links {linked or 'an address'}; this poll's filing, {f['item']}, is verified as its "
                   "own (seats, pollster, dates, respondents) and poll_filings_2026.json has no verdict on that link")
        elif c is None and not r.get("previous_link"):
            # the table the file was built from linked the match (or nothing): a correction made before is made again;
            # not verified, so the values only go (at worst a right link's values are dropped, never a wrong one's kept)
            why = (f"polls-data.js links {linked or 'an address'}; poll_filings_2026.json matches this poll to "
                   f"{f['item']} (not verified) and has no verdict on that link: the table it was built from linked "
                   f"{f['item']} or nothing")
        else:
            if c is None:
                warn.append(f"{key}: links {linked or 'an address'}, not its filing {f['item']} (not verified), and "
                            "poll_filings_2026.json has a verdict only on another link: left as it is")
            continue                                   # "both" (a re-filing: either link is right) or "unclear"
        p["corrected"] = correct(p, r, why, samples.get(key))
    return warn


def build(src, out, filings=FILINGS):
    raw = load_js(src)
    polls, dropped, samples = [], [], {}
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
        samples[f"{p['date']}|{p['pollster']}|{p.get('outlet', '')}"] = p.get("sampleSize")
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
    F = None
    if filings:
        try:
            F = load_filings(filings)
        except (OSError, ValueError) as exc:
            print(f"warning: {os.path.basename(filings)}: {str(exc)[:200]}; the polls are built without the CEC "
                  "filings", file=sys.stderr)
    if F:
        for w in attach_filings(polls, F, samples):
            print(f"warning: {w}", file=sys.stderr)
        print(f"CEC filings ({os.path.basename(filings)}, fetched {F['fetched'] or '-'}): "
              f"{sum(1 for p in polls if p['official'])} of {len(polls)} polls, "
              f"{sum(1 for p in polls if p['official'] and p['official']['verified'])} verified, "
              f"{sum(1 for p in polls if p.get('corrected'))} corrected")
    doc = {
        "parties": [{"id": k, "name": v[0], "leader": v[1], "bloc": v[2], "color": v[3], "dark": v[4],
                     "letters": LETTERS_2026.get(k, "")}
                    for k, v in PARTIES_2026.items()],
        "polls": polls,
        "dropped": dropped,
        "source": "רשומות סקרים שפורסמו (טבלת הסקרים בוויקיפדיה), מוצלבות מול קובצי הדיווח על סקרים "
                  "שמפרסמת ועדת הבחירות המרכזית ב-gov.il, כשנמצאו",
    }
    if F:
        doc["filings"] = {"fetched": F["fetched"], "collector": F["collector"]}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    return len(polls), dropped


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "site", "data", "polls_2026.json"))
    ap.add_argument("--filings", default=FILINGS, help="poll_filings_2026.json; '' builds without the CEC filings")
    a = ap.parse_args()
    n, d = build(a.src, a.out, a.filings)
    print(f"{n} polls written; dropped: {d}")
