"""Attach the CEC's poll filings to the 2026 polls: site/data/poll_filings_2026.json.

Every election poll published from 90 days before the election is filed with the Central Elections Committee
(section 16ה of the Elections (Propaganda Methods) Law), which posts each filing, as sent, in the gov.il collector
https://www.gov.il/he/departments/dynamiccollectors/knesset_election_polls_26 (one item knesset_election<N> per
filing, a PDF each). A filing carries what the seat table in the news does not: the raw vote share of every list
(also those below the threshold), the respondents, the sampling error and the fieldwork dates.

For each poll in site/data/polls_2026.json this finds its filing and writes, in a file of its own, the filing's
address and number, the respondents (n), the initial sample, the sampling error, the fieldwork dates, the raw vote
shares, the share of lists below the threshold and of the undecided, each with where it was read. It never changes
polls_2026.json: the seats and the headline average stay as they are (the move of the average to raw shares,
PLAN.md 5.1 stage 2, is not made here).

Where the values come from, best first (per field; "src" in the output names it):
  cec_pdf      the filing's PDF, read here (pdftotext -layout), from a fetch of pipeline/fetchers/poll_filings.py;
  cec_listing  the collector's own listing (the same fetch);
  amitlev, or523, isaranga
               third parties' readings of the same PDFs (pipeline/reference/poll_filings_index.json, each source with
               its address and the SHA-256 of the file read): kept apart and marked verified: false until the PDF
               itself has been read here.
A poll is matched to a filing by its seats (all lists equal, fieldwork ending at most 10 days before publication);
else by its polling house and the date (at most 3 days apart, at most 6 seats different, the differences listed);
else by the link polls_2026.json already carries. Each filing goes to one poll at most.

Run:
  python3 pipeline/build_poll_filings.py [--fetched DIR ...]      (DIR: a poll_filings fetch, e.g. ops-reports'
                                                                   reports/fetch/poll_filings/latest)
  python3 pipeline/build_poll_filings.py --reference --or523 F --amitlev F [--isaranga DIR]
                                                                  (rewrites the reference index from those files)
"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "pipeline", "reference", "poll_filings_index.json")
POLLS = os.path.join(ROOT, "site", "data", "polls_2026.json")
OUT = os.path.join(ROOT, "site", "data", "poll_filings_2026.json")
COLLECTOR = "https://www.gov.il/he/departments/dynamiccollectors/knesset_election_polls_26"
BLOB = "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/{item}/he/{file}"
FILING_URL = re.compile(r"https://www\.gov\.il/BlobFolder/dynamiccollectorresultitem/(knesset_election\d{1,4})/he/"
                        r"([^/?#\s\"'<>\\]{1,200})", re.I)
THIRD_PARTY = {
    "or523": "https://raw.githubusercontent.com/or523/or523.github.io/main/elections2026/data/polls.json",
    "amitlev": "https://raw.githubusercontent.com/amitlev/israel-polls-2026/main/docs/polls-data.js",
    "isaranga": "https://raw.githubusercontent.com/isaranga/SekerKolshehu/master/data/26th-Knesset-2026/polls/",
}
try:
    from zoneinfo import ZoneInfo
    IL = ZoneInfo("Asia/Jerusalem")
except Exception:                                   # no tz data: summer time (UTC+3) until 25.10.2026
    IL = None

sys.path.insert(0, os.path.join(ROOT, "pipeline"))


# ------------------------------------------------------------------ text
BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
NIQQUD = re.compile("[\u0591-\u05c7]")


def clean(s):
    """A line of extracted text: no bidi controls or niqqud, one spelling of each quote mark and dash."""
    s = BIDI.sub("", s or "")
    s = NIQQUD.sub("", s)
    s = re.sub("[\u05f4\u201c\u201d\u201e]", '"', s)
    s = re.sub("[\u05f3\u2018\u2019`]", "'", s)
    s = re.sub("[\u2010-\u2015\u05be]", "-", s)
    return s.replace("\u00a0", " ").replace("\t", "    ")


def fold(s):
    """For matching: clean, single spaces, final letters folded (רע"ם = רע"מ)."""
    s = re.sub(r"\s+", " ", clean(s)).strip()
    return s.translate(str.maketrans("םןךףץ", "מנכפצ"))


# ------------------------------------------------------------------ lists
# A filing names a list as its pollster typed it ("הליכוד בראשות בנימין נתניהו", "מפלג ת ישר!", a typo, a final
# mem for a final nun), so each list is known by its names and, failing those, by its leaders: a pollster can
# invent a label but not a new leader for it. Names are tried before leaders; the most specific name first (after
# amitlev/israel-polls-2026, .github/scripts/lib/govil-party-map.mjs). Ids are polls_2026.json's.
RULES = [
    ("Yisrael Beiteinu", ["ישראל ביתנו"], ["ליברמנ"]),
    ("Amcha Yisrael", ["עמכ ישראל"], ["וינטר"]),
    ("Religious Zionism", ["הציונות הדתית"], ["סמוטריצ"]),
    ("Otzma Yehudit", ["עוצמה יהודית"], ["בנ גביר", "בנגביר"]),
    ("Haredi Public", ["הציבור החרדי"], ["לייטנר", "ליטנר"]),
    ("UTJ", ["יהדות התורה", "דגל התורה", "אגודת ישראל"], ["גולדקנופפ", "יעקב אשר"]),
    ("Shas", ['ש"ס', "שס בראשות"], ["דרעי"]),
    ("Likud", ["הליכוד", "ליכוד"], ["נתניהו"]),
    ("The Democrats", ["הדמוקרטימ"], ["יאיר גולנ"]),
    ("Yashar", ["ישר!", "ישר !"], ["איזנקוט", "אייזנקוט"]),
    ("Together", ["ביחד", "יחד בראשות"], ["נפתלי בנט", "יאיר לפיד"]),
    ("Reservists", ["המילואימניקימ", "המילואמיניקימ", "המילואימניקיס", "בית ציוני"], ["הנדל", "טרופר"]),
    ("Joint List", ["הרשימה המשותפת", 'חד"ש', 'תע"ל', 'בל"ד'], ["עודה", "ג'בארינ", "גבארינ", "ג'אברינ", "טיבי"]),
    ("Ra'am", ['רע"מ', "רעמ בראשות"], ["עבאס"]),
    ("National Unity", ["כחול לבנ"], ["בני גנצ"]),
]
# lists on some filings that polls_2026.json does not carry: their share counts as below the threshold
OTHER = [("Unity", ["האחדות"], ["ארדנ"]), ("Yesodot Yisrael", ["יסודות ישראל"], [])]
UNTRACKED = ["נעמ", "ישראל תחילה", "עלה ירוק", "הבית היהודי", "מרצ", "העבודה", "זהות", "מפלגות אחרות", "אחרימ",
             "הכלכלית החדשה", "מפלגה אחרת", "רשימות אחרות", "אחר"]
_RULES = [(i, [fold(n) for n in ns], [fold(x) for x in ls]) for i, ns, ls in RULES + OTHER]


def party_id(label):
    """The id of the list a filing's label names, or None. Also tried reversed (text read in visual order)."""
    for f in (fold(label), fold(label)[::-1]):
        if not f:
            continue
        for i, ns, _ in _RULES:
            if any(n in f for n in ns):
                return i
        for i, _, ls in _RULES:
            if any(x in f for x in ls):
                return i
    return None


TRACKED = {i for i, _, _ in RULES}


# ------------------------------------------------------------------ polling houses
# (pattern in the filing's editor or commissioner, house id as in polls_2026.json). Rozner's Channel 13 polls
# (Midgam Project and StatNet) before Midgam's own.
HOUSES = [("רוזנר", "ch13"), ("פרויקט", "ch13"), ("סטטנט", "ch13"), ("קנטאר", "kantar"), ("קאנטר", "kantar"),
          ("kantar", "kantar"), ("דיירקט", "direct-polls"), ("direct polls", "direct-polls"), ("נקסט דאטה", "filber"),
          ("פילבר", "filber"), ("לזר", "lazar"), ("מאגר מוחות", "maagar-mochot"), ("טאטיקה", "yossi-tatika"),
          ("טטיקה", "yossi-tatika"), ("מדגם", "midgam"), ("דיאלוג", "dialog"), ("אקורד", "accord"),
          ("די אר איי", "dri"), ("אפקאר", "afkar")]


def house_of(*names):
    for n in names:
        f = fold(n).lower()
        if f:
            for pat, h in HOUSES:
                if pat in f:
                    return h
    return None


# ------------------------------------------------------------------ dates and numbers
def iso(d):
    return d.isoformat() if d else None


def local_date(s):
    """A date of the listing or a third party: 'YYYY-MM-DD', or gov.il's UTC timestamp of a local midnight
    ('2026-07-26T21:00:00Z' is 27.7 in Israel)."""
    if not isinstance(s, str) or not re.match(r"\d{4}-\d{2}-\d{2}", s):
        return None
    if len(s) <= 10:
        try:
            return dt.date.fromisoformat(s[:10])
        except ValueError:
            return None
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return t.date()
    if IL is not None:
        return t.astimezone(IL).date()
    return (t + dt.timedelta(hours=3 if t < dt.datetime(2026, 10, 24, 23, tzinfo=dt.timezone.utc) else 2)).date()


DATE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})(?!\d)")
DAY_RANGE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–]\s*(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})(?!\d)")


def dates_in(s):
    """The dates a filing writes (12/10/2026, 12.10.26, 11-12/10/2026), sorted, in the 2026 campaign only."""
    out = set()

    def mk(d, m, y):
        y = int(y) + (2000 if len(y) == 2 else 0)
        try:
            v = dt.date(y, int(m), int(d))
        except ValueError:
            return None
        return v if dt.date(2026, 4, 1) <= v <= dt.date(2026, 10, 27) else None
    s = clean(s)
    for m in DAY_RANGE.finditer(s):
        for d in (m.group(1), m.group(2)):
            v = mk(d, m.group(3), m.group(4))
            if v:
                out.add(v)
    for m in DATE.finditer(s):
        v = mk(*m.groups())
        if v:
            out.add(v)
    return sorted(out)


NUM = re.compile(r"(?<![\d.])[±]?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*%?")


def numbers(s):
    return [float(m.group(1).replace(",", "")) for m in NUM.finditer(clean(s))]


def moe_floor(n):
    """The smallest sampling error a simple random sample of n can state (95%): below 0.8 of it is a misreading
    (the rule build_polls.py applies)."""
    return 0.8 * 98 / (n ** 0.5) if n else 0


# ------------------------------------------------------------------ reading a filing's text
# The labels of the disclosure fields, as the three templates read by amitlev/israel-polls-2026
# (.github/scripts/lib/govil-pdf-parser.mjs: Midgam/Lazar, Kantar, Maagar Mochot) and idoherling/2026_Election_Model
# (src/scrape_cec.py) word them; the most specific first.
LABELS = {
    "commissioner": ["שם הגוף שהזמין את הסקר", "מזמין הסקר", "הגוף שהזמין"],
    "pollster": ["הגורם שערך את הסקר", "שם עורך הסקר", "עורך הסקר", "מבצע הסקר"],
    "fieldwork": ["מועד איסוף הנתונים", "מועד עריכת הסקר", "מועד ביצוע הסקר", "תאריך עריכת הסקר", "תאריכי",
                  "התאריכים", "מועד הסקר"],
    "sampling": ["שיטת הדגימה"],
    "n_initial": ["גודל המדגם ההתחלתי", "גודל מדגם התחלתי", "מדגם התחלתי"],
    "population": ["סוגי האוכלוסייה שנדגמו", "סוגי האוכלוסיה שנדגמו", "סוג האוכלוסייה", "האוכלוסייה שנדגמה"],
    "invited": ["מספר המתבקשים להשתתף", "מס' האנשים שהתבקשו להשתתף", "מספר האנשים שהתבקשו", "מס' האנשים אליהם פנו",
                "מספר האנשים אליהם פנו", "מספר המתבקשים"],
    "n": ["מספר המשיבים", "מס' המשיבים", "מס' האנשים שהשתתפו בסקר בפועל", "מספר האנשים שהשתתפו בסקר בפועל",
          "מספר המשתתפים בסקר", "מספר משיבים", "גודל המדגם הסופי"],
    "response_rate": ["אחוז המשתתפים בסקר", "שיעור ההיענות לסקר", "שיעור ההיענות", "שיעור היענות", "אחוז ההיענות"],
    "refused": ["מספר האנשים שסרבו", "מספר האנשים שסירבו", "מס' האנשים שסרבו", "מס' האנשים שסירבו"],
    "refused_pct": ["אחוז האנשים שסרבו", "אחוז האנשים שסירבו", "שיעור האנשים שסרבו", "שיעור האנשים שסירבו",
                    "אחוז הסירוב", "שיעור הסירוב"],
    "moe": ["טעות הדגימה המרבית", "טעות הדגימה המירבית", "טעות הדגימה", "טעות דגימה", "מרווח הטעות",
            "גודל הטעות הסטטיסטית", "טעות סטטיסטית"],
    "method": ["השיטה הסטטיסטית", "שיטה סטטיסטית"],
    "mode": ["אופן ביצוע הסקר", "אופן איסוף הנתונים", "שיטת איסוף הנתונים"],
}
TEXT_FIELDS = ("commissioner", "pollster", "sampling", "population", "method", "mode")
RANGES = {"n_initial": (100, 2_000_000), "invited": (100, 2_000_000), "n": (100, 100_000), "refused": (0, 2_000_000),
          "response_rate": (0.1, 100), "refused_pct": (0, 100), "moe": (0.5, 15)}
ALL_LABELS = sorted({fold(x) for v in LABELS.values() for x in v}, key=len, reverse=True)
UNDECIDED = ["לא החליטו", "לא החלטתי", "טרם החליט", "לא יודע", "מתלבט", "אינו יודע"]
RESPONDENTS = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d{3,6})\s+(?:משיבים|משיבות|נשאלים|מרואיינים|נדגמים)")


def cells(line):
    """The cells of a line of pdftotext -layout output: runs of text separated by two spaces or more."""
    return [c.strip() for c in re.split(r"\s{2,}", clean(line).strip()) if c.strip()]


def find_field(lines, key):
    """(value, the line it was read from) of one disclosure field, or (None, None). In an RTL table the value cell
    stands left of the label, so pdftotext -layout writes it before the label; in running text it follows."""
    for label in LABELS[key]:
        fl = fold(label)
        for i, line in enumerate(lines):
            cs = cells(line)
            for j, c in enumerate(cs):
                fc = fold(c)
                k = fc.find(fl)
                if k < 0:
                    continue
                if key == "n" and "התחלתי" in fc:
                    continue
                rest = fc[k + len(fl):].strip(" :-")
                # a longer label that starts with this one ("גודל המדגם" in "גודל המדגם ההתחלתי") is another field
                if any(other != fl and other.startswith(fl) and fc[k:].startswith(other) for other in ALL_LABELS):
                    continue
                cands = [rest] if rest else []
                cands += [" ".join(cs[:j])] if j else []
                cands += [" ".join(cs[j + 1:])] if j + 1 < len(cs) else []
                if len(cs) == 1 and not rest:
                    # the label alone on its line: the value wrapped around it (the line above, the line below)
                    near = [" ".join(cells(lines[x])) for x in (i - 1, i + 1)
                            if 0 <= x < len(lines) and not is_field(lines[x])]
                    cands += [" ".join(near)] if key in TEXT_FIELDS and near else near
                for cand in cands:
                    v = value_of(key, cand)
                    if v is not None:
                        return v, clean(line).strip()
    return None, None


def value_of(key, s):
    s = s.strip(" :")
    if not s or any(fold(s).startswith(l) for l in ALL_LABELS):
        return None
    if key == "fieldwork":
        ds = dates_in(s)
        return (ds[0], ds[-1]) if ds else None
    if key in TEXT_FIELDS:
        return re.sub(r"\s+", " ", s)[:200] if re.search("[א-תA-Za-z]", s) else None
    nums = numbers(DATE.sub(" ", DAY_RANGE.sub(" ", clean(s))))    # a date's digits are not a count
    lo, hi = RANGES[key]
    for v in nums:
        if lo <= v <= hi:
            return int(v) if key in ("n", "n_initial", "invited", "refused") and v == int(v) else v
    return None


VALUE = re.compile(r"[±]?\d{1,3}(?:\.\d+)?\s*%?")
NOT_A_LIST = ["לא החליטו", "לא החלטתי", "טרם החליט", "לא יודע", "מתלבט", "אינו יודע", "לא יצביע", "לא אצביע",
              "לא מצביע", "פתק לבן", "מסרב", "סירב", "לא ענה"]


def table_rows(lines):
    """Candidate rows of a seat table, one per line with a value: {"i": line index, "label", "seats", "pct",
    "ambiguous"}. In pdftotext -layout output a cell that is all number (17.0%, 21, 4) is a value and the other
    cells are the label; a line not split in cells ("הליכוד 21 17.0%") gives its leading and trailing numbers."""
    rows, text_only = [], None
    for i, line in enumerate(lines):
        cs = cells(line)
        vals = [c for c in cs if VALUE.fullmatch(c)]
        label = " ".join(c for c in cs if c not in vals)
        if not vals:
            toks = clean(line).split()
            lead, tail = [], []
            while toks and VALUE.fullmatch(toks[0]):
                lead.append(toks.pop(0))
            while toks and VALUE.fullmatch(toks[-1]):
                tail.insert(0, toks.pop())
            vals, label = lead + tail, " ".join(toks)
        if not vals:
            text_only = (i, label) if re.search("[א-ת]", label) else None
            continue
        if not re.search("[א-ת]", label):
            # the numbers of a row whose name the layout put on the line above
            if text_only and text_only[0] == i - 1 and not label:
                label = text_only[1]
            else:
                continue
        text_only = None
        seats = [c for c in vals if "%" not in c and "." not in c]
        pcts = [c for c in vals if "%" in c or "." in c]
        rows.append({"i": i, "label": label, "seats": int(seats[0].strip("± ")) if len(seats) == 1 else None,
                     "pct": float(pcts[0].strip("%± ")) if len(pcts) == 1 else None,
                     "ambiguous": len(seats) > 1 or len(pcts) > 1})
    return rows


def is_total(label):
    return 'סה"כ' in fold(label) or "סך הכל" in fold(label) or 'סה"כ' in fold(label)[::-1]


def is_field(label):
    f = fold(label)
    return any(l in f for l in ALL_LABELS)


def find_main_table(lines):
    """The first seat table: a run of rows (at most two lines that are not rows between two rows), cut at a
    disclosure field's line and ended by a total row (סה"כ), whose seats add up to 120, with five rows or more
    naming a list. None when there is none: a trend table (several weeks side by side, more than one seat or share
    on a line) or anything else this reader did not clearly understand."""
    segs, cur = [], []
    for r in table_rows(lines):
        if cur and (r["i"] - cur[-1]["i"] > 3 or is_field(r["label"])):
            segs.append(cur)
            cur = []
        if is_field(r["label"]):
            continue
        cur.append(r)
        if is_total(r["label"]):
            segs.append(cur)
            cur = []
    segs.append(cur)
    for seg in segs:
        body = [r for r in seg if not is_total(r["label"]) and r["label"]]
        # the longest run that ends where the segment ends (at its total row) and adds up to 120: a line above
        # the table that happens to end in a number ("עבור ערוץ 16") is not one of its rows
        for start in range(len(body)):
            run = body[start:]
            named = [r for r in run if party_id(r["label"])]
            if len(named) < 5:
                break
            if any(r["ambiguous"] for r in named):
                continue
            if sum(r["seats"] or 0 for r in run) == 120:
                return run
    return None


def parse_filing(text):
    """The fields of one filing's text (pdftotext -layout): metadata, the main seat table, the shares."""
    lines = [l for l in (text or "").splitlines() if l.strip()]
    out, read_from = {}, {}
    for key in LABELS:
        v, line = find_field(lines, key)
        if v is not None:
            out[key] = v
            read_from[key] = line[:160]
    if "n" not in out:
        # running text ("הסקר נערך בקרב 550 משיבים"), the narrative template
        m = RESPONDENTS.search(clean(" ".join(lines)))
        if m and 100 <= int(m.group(1).replace(",", "")) <= 100_000:
            out["n"], read_from["n"] = int(m.group(1).replace(",", "")), m.group(0)[:160]
    if "fieldwork" in out:
        out["fieldwork_start"], out["fieldwork_end"] = iso(out["fieldwork"][0]), iso(out["fieldwork"][1])
        del out["fieldwork"]
    if out.get("moe") and out.get("n") and out["moe"] < moe_floor(out["n"]):
        out["notes"] = [f"sampling error {out['moe']} is below the minimum for n={out['n']}: not kept"]
        del out["moe"]
    table = find_main_table(lines)
    if table:
        seats, pct, below, dup, unknown = {}, {}, [], set(), []
        for r in [r for r in table if any(fold(x) in fold(r["label"]) for x in NOT_A_LIST)]:
            if r["pct"] is not None and any(fold(u) in fold(r["label"]) for u in UNDECIDED):
                out["undecided_pct"] = r["pct"]
        table = [r for r in table if not any(fold(x) in fold(r["label"]) for x in NOT_A_LIST)]
        for r in table:
            pid = party_id(r["label"])
            name = re.sub(r"\s+", " ", r["label"]).strip()
            if pid in TRACKED:
                if pid in seats and pid != "Joint List":
                    dup.add(pid)
                seats[pid] = seats.get(pid, 0) + (r["seats"] or 0)
                if r["pct"] is not None:
                    pct[pid] = round(pct.get(pid, 0) + r["pct"], 2)
            elif not r["seats"]:
                pass
            else:
                unknown.append(name)
            if not r["seats"] and r["pct"] is not None:
                below.append({"name": name[:80], "pct": r["pct"], **({"id": pid} if pid else {})})
        for pid in dup:                                    # one list on two rows: neither share is kept
            pct.pop(pid, None)
        out["seats"] = {k: v for k, v in seats.items() if v}
        out["pct"] = pct
        withp = [r for r in table if r["pct"] is not None]
        out["pct_total"] = round(sum(r["pct"] for r in withp), 1)
        out["wasted_pct"] = round(sum(b["pct"] for b in below), 1)
        out["table_rows"] = len(table)
        out["seats_total"] = sum(r["seats"] or 0 for r in table)
        out["pct_complete"] = len(withp) >= 0.8 * len(table) and 95 <= out["pct_total"] <= 105
        if below:
            out["below"] = below
        if dup or unknown:
            out.setdefault("notes", []).extend(
                [f"two rows map to {p}: its share is not kept" for p in sorted(dup)]
                + [f"a row with seats names no list known here: {u[:60]}" for u in unknown])
        for line in lines[table[-1]["i"] + 1: table[-1]["i"] + 8] if "undecided_pct" not in out else []:
            if any(fold(u) in fold(line) for u in UNDECIDED):
                ps = [v for v in numbers(line) if 0 < v < 60]
                if ps:
                    out["undecided_pct"] = ps[-1]
                    break
    out["read_from"] = read_from
    return out


def pdf_text(path):
    """(text, error) of a PDF through pdftotext -layout (poppler), when this machine has it."""
    exe = shutil.which("pdftotext")
    if not exe:
        return None, "no pdftotext on this machine"
    try:
        p = subprocess.run([exe, "-layout", "-enc", "UTF-8", path, "-"], capture_output=True, timeout=120,
                           cwd=os.path.dirname(os.path.abspath(path)))
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"pdftotext: {exc.__class__.__name__}"
    if p.returncode != 0:
        return None, f"pdftotext exit {p.returncode}: {p.stderr.decode('utf-8', 'replace')[:120]}"
    return p.stdout.decode("utf-8", "replace"), None


# ------------------------------------------------------------------ filings
def canon(url):
    m = FILING_URL.fullmatch((url or "").strip())
    if not m:
        return None
    item = "knesset_election" + m.group(1)[16:]
    file = urllib.parse.unquote(m.group(2))
    return item, file, BLOB.format(item=item, file=urllib.parse.quote(file))


def item_no(item):
    return int(item[16:]) if item and item[16:].isdigit() else 0


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def listing_fields(data):
    """What the collector's listing says of a filing (its Data, field names as gov.il gives them; the names other
    than survey_editor, date_the_survey and file_PDF are not known in advance, so they are recognised by shape)."""
    out = {}
    for k, v in (data or {}).items():
        lk = k.lower()
        txt = v.get("DescriptionBlankTextString") if isinstance(v, dict) else v
        if isinstance(txt, list):
            txt = " ".join(str(x) for x in txt if isinstance(x, (str, int, float)))
        if not isinstance(txt, (str, int, float)) or isinstance(txt, bool):
            continue
        s = str(txt).strip()
        if not s:
            continue
        if "editor" in lk:
            out.setdefault("editor", s[:120])
        elif any(x in lk for x in ("media", "publisher", "commission", "orderer", "mazmin", "client")):
            out.setdefault("media", s[:160])
        elif "note" in lk or "remark" in lk or "comment" in lk:
            out.setdefault("cec_notes", s[:400])
        elif "date" in lk and local_date(s):
            key = "survey_date" if ("survey" in lk or "seker" in lk) else "date_" + re.sub(r"[^a-z0-9_]", "", lk)[:30]
            out.setdefault(key, iso(local_date(s)))
        elif re.fullmatch(r"\d{4}", s) and any(x in lk for x in ("num", "serial", "mispar", "id", "number")):
            out.setdefault("number", s)
    return out


def load_reference(path):
    try:
        ref = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {"filings": [], "sources": {}}
    return ref


def from_reference(ref):
    """The reference's filings as records: {item: rec} with third parties' values kept per source."""
    recs = {}
    for f in ref.get("filings", []):
        c = canon(f.get("pdf"))
        if not c:
            continue
        item, file, url = c
        rec = recs.setdefault(item, new_rec(item))
        add_url(rec, url, "reference")["primary"] = True
        for u in f.get("also") or []:
            c2 = canon(u)
            if c2 and c2[0] == item:
                add_url(rec, c2[2], "reference")
        for k in ("number", "editor", "media", "cec_notes", "published", "cec_date", "national", "excluded"):
            if f.get(k) is not None:
                rec["index"].setdefault(k, f[k])
        if f.get("fieldwork"):
            rec["index"].setdefault("fieldwork", f["fieldwork"])
        for src in ("or523", "amitlev", "isaranga"):
            if isinstance(f.get(src), dict):
                rec["third"][src] = f[src]
    return recs


def new_rec(item):
    return {"item": item, "urls": [], "index": {}, "listing": {}, "pdf": None, "third": {}, "texts": []}


def add_url(rec, url, source):
    for u in rec["urls"]:
        if u["url"] == url:
            if source not in u["from"]:
                u["from"].append(source)
            return u
    u = {"url": url, "from": [source]}
    rec["urls"].append(u)
    return u


def from_fetch(recs, fetched, notes):
    """A poll_filings fetch: the listing's results and each saved PDF, read with pdftotext here."""
    try:
        listing = json.load(open(os.path.join(fetched, "listing.json"), encoding="utf-8"))
    except (OSError, ValueError) as exc:
        listing = {}
        notes.append(f"{fetched}: no listing.json ({exc.__class__.__name__})")
    for r in listing.get("results") or []:
        if not isinstance(r, dict) or not re.fullmatch(r"knesset_election\d{1,4}", str(r.get("UrlName", ""))):
            continue
        rec = recs.setdefault(r["UrlName"], new_rec(r["UrlName"]))
        rec["listing"] = listing_fields(r.get("Data"))
        data = r.get("Data") if isinstance(r.get("Data"), dict) else {}
        for v in data.values():
            for f in v if isinstance(v, list) else [v]:
                if isinstance(f, dict) and isinstance(f.get("FileName"), str):
                    c = canon(BLOB.format(item=r["UrlName"], file=urllib.parse.quote(f["FileName"])))
                    if c:
                        add_url(rec, c[2], "listing")
    try:
        rows = json.load(open(os.path.join(fetched, "filings.json"), encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    for row in rows:
        c = canon(row.get("url"))
        if not c or not row.get("saved"):
            continue
        item, file, url = c
        rec = recs.setdefault(item, new_rec(item))
        u = add_url(rec, url, "fetched")
        path = inside(fetched, row["saved"])
        if not path:
            continue
        text, err = None, None
        tpath = inside(fetched, row.get("text"))
        if tpath:
            text = open(tpath, encoding="utf-8", errors="replace").read()
        else:
            text, err = pdf_text(path)
        u["sha256"] = row.get("sha256") or sha256(path)
        if text is None:
            u["text_error"] = err
            continue
        parsed = parse_filing(text)
        parsed["url"] = url
        rec["texts"].append(parsed)


def inside(base, relpath):
    """base/relpath when it is a file under base (the fetch's own file list is data, not trusted paths)."""
    if not isinstance(relpath, str) or not relpath:
        return None
    root = os.path.realpath(base)
    p = os.path.realpath(os.path.join(base, relpath))
    return p if p.startswith(root + os.sep) and os.path.isfile(p) else None


def best_parse(rec):
    """The best reading of an item's PDFs: a seat table of 120 first, then complete shares, then most fields; the
    listing's own file first among equals."""
    if not rec["texts"]:
        return None
    listed = {u["url"] for u in rec["urls"] if "listing" in u["from"]}

    def score(p):
        return (p.get("seats_total") == 120, bool(p.get("pct_complete")), sum(1 for k in LABELS if k in p),
                p["url"] in listed, p["url"])
    return max(rec["texts"], key=score)


def merged(rec):
    """One filing: every field from its best source, and where it came from."""
    out, src = {"item": rec["item"]}, {}
    P = best_parse(rec)
    L, I, T = rec["listing"], rec["index"], rec["third"]
    A, O, S = T.get("amitlev") or {}, T.get("or523") or {}, T.get("isaranga") or {}

    def put(key, *cands):
        for name, val in cands:
            if val not in (None, "", {}, []):
                out[key], src[key] = val, name
                return

    listed = [u["url"] for u in rec["urls"] if "listing" in u["from"]]
    primary = [u["url"] for u in rec["urls"] if u.get("primary")]
    urls = sorted({u["url"] for u in rec["urls"]}, key=lambda u: (u not in listed, u not in primary, u))
    out["url"] = P["url"] if P else (listed[0] if listed else urls[0] if urls else None)
    out["also"] = [u for u in urls if u != out["url"]]
    m = re.search(r"(\d{4})", urllib.parse.unquote((out["url"] or "").rsplit("/", 1)[-1]))
    put("number", ("cec_listing", L.get("number")), ("or523", I.get("number")), ("file name", m.group(1) if m else None))
    put("editor", ("cec_listing", L.get("editor")), ("cec_pdf", (P or {}).get("pollster")), ("or523", I.get("editor")))
    put("media", ("cec_listing", L.get("media")), ("cec_pdf", (P or {}).get("commissioner")), ("or523", I.get("media")))
    put("published", ("cec_listing", next((v for k, v in sorted(L.items()) if k.startswith("date_")), None)),
        ("or523", I.get("published")))
    put("cec_notes", ("cec_listing", L.get("cec_notes")), ("or523", I.get("cec_notes")))
    fw = I.get("fieldwork") or [None, None]
    put("fieldwork_start", ("cec_pdf", (P or {}).get("fieldwork_start")), ("or523", fw[0]), ("amitlev", A.get("fieldwork")),
        ("cec_listing", L.get("survey_date")))
    put("fieldwork_end", ("cec_pdf", (P or {}).get("fieldwork_end")), ("or523", fw[1]), ("amitlev", A.get("fieldwork")),
        ("cec_listing", L.get("survey_date")))
    pdf_seats = P.get("seats") if P and P.get("seats_total") == 120 else None
    put("seats", ("cec_pdf", pdf_seats), ("or523", O.get("seats")))
    pdf_pct = P.get("pct") if P and P.get("seats_total") == 120 and P.get("pct") else None
    put("pct", ("cec_pdf", pdf_pct), ("amitlev", A.get("pct")), ("or523", O.get("pct")))
    if src.get("pct") == "cec_pdf":
        put("pct_total", ("cec_pdf", P.get("pct_total")))
        put("wasted_pct", ("cec_pdf", P.get("wasted_pct")))
        put("below", ("cec_pdf", P.get("below")))
    elif src.get("pct") == "amitlev":
        put("wasted_pct", ("amitlev", A.get("wasted_pct")))
        put("below", ("amitlev", A.get("below")))
    elif src.get("pct") == "or523":
        put("pct_total", ("or523", O.get("pct_total")))   # its shares are of the lists with seats: under 100
    for key, akey in (("n", "n"), ("n_initial", None), ("invited", "invited"), ("response_rate", "response_rate"),
                      ("refused_pct", "refused_pct"), ("moe", "moe"), ("undecided_pct", "undecided_pct"),
                      ("sampling", "sampling"), ("population", "population"), ("mode", "mode"), ("method", "method"),
                      ("commissioner", None)):
        put(key, ("cec_pdf", (P or {}).get(key)), ("amitlev", A.get(akey) if akey else None),
            ("isaranga", S.get("n") if key == "n" else None))
    if out.get("moe") and out.get("n") and out["moe"] < moe_floor(out["n"]):
        out.pop("moe")
        src.pop("moe")
    out["house"] = house_of(out.get("editor") or "", out.get("media") or "")
    out["national"] = (I.get("national") if I.get("national") is not None else bool(out.get("seats")))
    if L:
        out["listing"] = L
    if P and P.get("notes"):
        out["notes"] = P["notes"]
    out["src"] = src
    out["read"] = bool(P)
    return out


# ------------------------------------------------------------------ matching polls and filings
def days(a, b):
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


def nonzero(seats):
    return {k: v for k, v in (seats or {}).items() if v and k in TRACKED}


def seat_diff(a, b):
    a, b = nonzero(a), nonzero(b)
    return {k: [a.get(k, 0), b.get(k, 0)] for k in sorted(set(a) | set(b)) if a.get(k, 0) != b.get(k, 0)}


def match(polls, filings):
    """[(poll index, filing item, how)]: each poll at most one filing and each filing at most one poll; seats first,
    then house and date, then the poll's own link."""
    cands = []
    by_url = {}
    for f in filings.values():
        for u in [f["url"]] + f["also"]:
            by_url[u] = f["item"]
    for i, p in enumerate(polls):
        ps = nonzero(p["seats"])
        for f in filings.values():
            end = f.get("fieldwork_end") or f.get("published")
            if not end or not f.get("seats"):
                continue
            gap = days(p["date"], end)                    # publication minus end of fieldwork
            if gap < -1 or gap > 10:
                continue
            diff = seat_diff(p["seats"], f["seats"])
            moved = sum(abs(x - y) for x, y in diff.values())
            # the same house only: Direct Polls (i24NEWS) and Filber (Channel 14) are one firm but two polls
            same_house = bool(f.get("house")) and f["house"] == p.get("house")
            if not diff and ps:
                cands.append((0, abs(gap), 0, i, f["item"], "seats"))
            elif same_house and abs(gap) <= 3 and moved <= 6:
                cands.append((1, abs(gap), moved, i, f["item"], "house+date"))
        c = canon(p.get("filing") or "")
        if c and c[2] in by_url:
            f = filings[by_url[c[2]]]
            end = f.get("fieldwork_end")
            moved = sum(abs(x - y) for x, y in seat_diff(p["seats"], f.get("seats")).values()) if f.get("seats") else 0
            if (not end or -1 <= days(p["date"], end) <= 10) and moved <= 6:
                cands.append((2, 0, moved, i, f["item"], "source link"))
    cands.sort(key=lambda c: c[:3] + (c[3], item_no(c[4])))
    used_p, used_f, out = set(), set(), []
    for tier, gap, moved, i, item, how in cands:
        if i in used_p or item in used_f:
            continue
        used_p.add(i)
        used_f.add(item)
        out.append((i, item, how))
    return sorted(out)


# ------------------------------------------------------------------ the output
FIELDS = ("n", "n_initial", "invited", "response_rate", "refused_pct", "moe", "pct", "pct_total", "below",
          "wasted_pct", "undecided_pct", "sampling", "population", "mode", "method", "commissioner")


def build(polls_path=POLLS, ref_path=REF, fetched=(), out_path=OUT):
    polls_doc = json.load(open(polls_path, encoding="utf-8"))
    polls = polls_doc["polls"]
    ref = load_reference(ref_path)
    notes = []
    recs = from_reference(ref)
    for d in fetched:
        from_fetch(recs, d, notes)
    filings = {item: merged(rec) for item, rec in recs.items()}
    pairs = match(polls, filings)
    rows, matched_items = [], set()
    for i, item, how in pairs:
        p, f = polls[i], filings[item]
        matched_items.add(item)
        row = {"key": f"{p['date']}|{p['pollster']}|{p.get('outlet', '')}", "date": p["date"], "pollster": p["pollster"],
               "outlet": p.get("outlet", ""), "house": p.get("house"), "match": how}
        diff = seat_diff(p["seats"], f.get("seats"))
        row["seats_equal"] = not diff if f.get("seats") else None
        if diff:
            row["seat_diff"] = diff                       # {list: [polls_2026.json, the filing]}
        row["filing"] = {k: f.get(k) for k in ("url", "item", "number", "editor", "media", "published", "cec_notes")
                         if f.get(k) is not None}
        if f["also"]:
            row["filing"]["also"] = f["also"]
        row["fieldwork"] = {"start": f.get("fieldwork_start"), "end": f.get("fieldwork_end")}
        for k in FIELDS:
            if f.get(k) not in (None, "", {}, []):
                row[k] = f[k]
        if row.get("pct") and not row["seats_equal"]:
            # the shares of a table whose seats are not the poll's (or not known): not this poll's table
            for k in ("pct", "pct_total", "below", "wasted_pct"):
                row.pop(k, None)
            row.setdefault("notes", []).append("the filing's seat table is not the poll's (or was not read): its "
                                               "shares are not attached")
        if f.get("listing"):
            row["filing"]["listing"] = f["listing"]
        row["src"] = {k: v for k, v in f["src"].items()
                      if k in row or k in ("fieldwork_start", "fieldwork_end", "seats") or k in row["filing"]}
        row["verified"] = f["read"]                        # the PDF itself was read here
        prev = canon(p.get("filing") or "")
        if prev and prev[2] != f["url"] and prev[2] not in f["also"]:
            row["previous_link"] = prev[2]
        if f.get("notes"):
            row.setdefault("notes", []).extend(f["notes"])
        rows.append(row)
    matched_polls = {i for i, _, _ in pairs}
    conflicts = [{"key": r["key"], "polls_2026_link": r["previous_link"], "matched": r["filing"]["url"], "match": r["match"]}
                 for r in rows if r.get("previous_link")]
    for i, p in enumerate(polls):
        c = canon(p.get("filing") or "")
        if i not in matched_polls and c:
            conflicts.append({"key": f"{p['date']}|{p['pollster']}|{p.get('outlet', '')}", "polls_2026_link": c[2],
                              "matched": None, "match": None})
    unmatched_filings = []
    for item in sorted(filings, key=item_no):
        f = filings[item]
        if item in matched_items:
            continue
        unmatched_filings.append({k: f.get(k) for k in ("item", "number", "editor", "media", "fieldwork_end", "url")
                                  if f.get(k) is not None} | {"national": bool(f.get("national") and f.get("seats"))})
    inputs = {"polls": rel(polls_path), "polls_sha256": sha256(polls_path), "reference": rel(ref_path),
              "reference_sha256": sha256(ref_path) if os.path.exists(ref_path) else None,
              "fetched": [rel(d) for d in fetched]}
    doc = {
        "about": "קובצי הדיווח על סקרי הבחירות שהוגשו לוועדת הבחירות המרכזית, מוצמדים לסקרים שבטבלת הסקרים: מספר "
                 "המשיבים, טעות הדגימה, מועדי איסוף הנתונים והאחוזים הגולמיים של כל רשימה. המנדטים והממוצע אינם "
                 "משתנים; שדה src אומר מאין נקרא כל ערך, ו-verified: false כשהקובץ עצמו עוד לא נקרא כאן",
        "source": "ועדת הבחירות המרכזית, מאגר הסקרים לכנסת ה-26 ב-gov.il (" + COLLECTOR + "); עד לקריאת הקבצים מכאן: "
                  "קריאות של צד שלישי (" + ", ".join(sorted(THIRD_PARTY)) + ") כמפורט ב-"
                  "pipeline/reference/poll_filings_index.json",
        "collector": COLLECTOR, "inputs": inputs,
        "counts": {"polls": len(polls), "matched": len(rows),
                   "by_match": {h: sum(1 for r in rows if r["match"] == h) for h in ("seats", "house+date", "source link")},
                   "with_pct": sum(1 for r in rows if r.get("pct")), "with_n": sum(1 for r in rows if r.get("n")),
                   "with_moe": sum(1 for r in rows if r.get("moe")), "verified": sum(1 for r in rows if r["verified"]),
                   "filings": len(filings), "filings_read": sum(1 for f in filings.values() if f["read"])},
        "polls": rows,
        "unmatched_polls": [f"{p['date']}|{p['pollster']}|{p.get('outlet', '')}" for i, p in enumerate(polls)
                            if i not in matched_polls],
        "unmatched_filings": unmatched_filings,
        "conflicts": conflicts,
        "notes": notes,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    return doc


def rel(p):
    a = os.path.abspath(p)
    return os.path.relpath(a, ROOT) if a.startswith(ROOT + os.sep) else p


# ------------------------------------------------------------------ the reference index
def reference(or523_path, amitlev_path, isaranga_dir=None, out_path=REF, seen=None):
    """pipeline/reference/poll_filings_index.json from three third parties' readings of the CEC's filings."""
    from build_polls import load_js
    o = json.load(open(or523_path, encoding="utf-8"))
    filings = {}

    def rec(url):
        c = canon(url)
        if not c:
            return None
        item, file, u = c
        r = filings.setdefault(item, {"item": item, "pdf": u})
        if r["pdf"] != u:
            r.setdefault("also", [])
            if u not in r["also"]:
                r["also"].append(u)
        return r

    def ids(d):
        out, other = {}, {}
        for name, v in (d or {}).items():
            if v is None:
                continue
            pid = party_id(name)
            if pid in TRACKED:
                out[pid] = round(out.get(pid, 0) + v, 2)
            else:
                other[name] = v
        return out, other
    def en_ids(d):
        """amitlev's keys are English ids already; its two halves of the Joint List are summed into it (FOLD in
        build_polls.py), lists polls_2026.json does not carry dropped."""
        out = {}
        for k, v in (d or {}).items():
            k = {"Hadash-Ta'al": "Joint List", "Balad": "Joint List"}.get(k, k)
            if k in TRACKED and isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = round(out.get(k, 0) + v, 2)
        return out
    for p in o.get("polls", []) + o.get("excluded", []):
        r = rec(p.get("pdf"))
        if r is None:
            continue
        national = p in o.get("polls", [])
        r.update({k: v for k, v in (("number", p.get("reference")), ("editor", p.get("pollster")),
                                    ("media", p.get("publisher")), ("cec_date", p.get("cecDate")),
                                    ("published", p.get("published")), ("cec_notes", p.get("notes"))) if v})
        if p.get("fieldworkStart") or p.get("fieldworkEnd"):
            r["fieldwork"] = [p.get("fieldworkStart"), p.get("fieldworkEnd")]
        r["national"] = national
        if not national:
            r["excluded"] = p.get("reason")
        seats, s_other = ids(p.get("seats"))
        pct, p_other = ids(p.get("percents"))
        if seats:
            r["or523"] = {"seats": {k: int(v) for k, v in seats.items() if v}, "pct": pct or None,
                          "pct_total": p.get("percentTotal"), "other": (s_other | p_other) or None}
            r["or523"] = {k: v for k, v in r["or523"].items() if v is not None}
    for p in load_js(amitlev_path):
        r = rec(p.get("govilSourceUrl"))
        if r is None:
            continue
        n = p.get("respondents")
        moe = p.get("marginOfError")
        a = {"n": n, "invited": p.get("invited"), "response_rate": p.get("responseRate"),
             "refused_pct": p.get("refusedPct"), "moe": moe if (moe and n and moe >= moe_floor(n)) else None,
             "fieldwork": p.get("fieldworkDate"), "undecided_pct": p.get("undecidedPct"),
             "sampling": p.get("samplingMethod"), "population": p.get("populationSampled"), "mode": p.get("mode"),
             "method": p.get("statisticalMethod"),
             "pct": en_ids(p.get("pct")) or None, "wasted_pct": p.get("wastedPct"),
             "below": [{"name": b.get("name"), "pct": b.get("pct"), **({"id": b["id"]} if b.get("id") else {})}
                       for b in p.get("belowThreshold") or [] if isinstance(b, dict)] or None}
        if moe and a["moe"] is None:
            a["moe_dropped"] = moe
        for b in a["below"] or []:
            # a list amitlev does not track but polls_2026.json does (הציבור החרדי): its share from the row's name
            pid = b.get("id") or party_id(b.get("name") or "")
            if pid in TRACKED and isinstance(b.get("pct"), (int, float)):
                b["id"] = pid
                a["pct"] = a["pct"] or {}
                a["pct"].setdefault(pid, b["pct"])
        r["amitlev"] = {k: v for k, v in a.items() if v is not None}
    try:
        text = open(amitlev_path, encoding="utf-8").read()
        m = re.search(r"window\.GOVIL_TOPICAL_DATA\s*=\s*", text)
        topical = json.JSONDecoder().raw_decode(text, m.end())[0] if m else []
    except ValueError:
        topical = []
    for t in topical:
        if isinstance(t, dict):
            rec(t.get("sourceUrl"))
    isaranga_files = {}
    for path in sorted(glob.glob(os.path.join(isaranga_dir, "*.json"))) if isaranga_dir else []:
        try:
            d = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        r = rec(d.get("link")) if isinstance(d, dict) else None
        if r is not None and isinstance(d.get("sample_size"), int) and not isinstance(d["sample_size"], bool):
            name = re.sub(r"^isaranga_", "", os.path.basename(path))
            r["isaranga"] = {"n": d["sample_size"], "file": name}
            isaranga_files[name] = sha256(path)
    seen = seen or dt.date.today().isoformat()
    doc = {
        "about": "An index of the CEC's 2026 poll filings as read by third parties, kept until the filings are "
                 "fetched from a GitHub runner (pipeline/fetchers/poll_filings.py) and read here: every value is a "
                 "third party's reading of the PDF at 'pdf', verified: false. Party names mapped to polls_2026.json "
                 "ids by build_poll_filings.party_id.",
        "verified": False,
        "collector": COLLECTOR,
        "api": "https://www.gov.il/he/api/DynamicCollector",
        "template_id": "b043127d-d79d-472e-ac10-5567bc9e8d3d",
        "template_id_source": "https://raw.githubusercontent.com/idoherling/2026_Election_Model/main/src/scrape_cec.py",
        "filing_rule": "https://www.bhol.co.il/news/1734638 (CEC director-general's letter, 29.7.2026: every poll "
                       "published from 90 days before the election is filed within 96 hours and posted as sent)",
        "sources": {
            "or523": {"url": THIRD_PARTY["or523"], "seen": seen, "sha256": sha256(or523_path),
                      "gives": "the collector's index (item, survey number, editor, outlet, CEC dates and notes, "
                               "fieldwork dates) and each filing's seat table with the shares of the lists that won "
                               "seats; filings without a national seat table listed as excluded with the reason"},
            "amitlev": {"url": THIRD_PARTY["amitlev"], "seen": seen, "sha256": sha256(amitlev_path),
                        "gives": "for the filings it matched to a poll: respondents, invited, response rate, sampling "
                                 "error, method fields and the shares of all lists (pdf-parse; its parser validated on "
                                 "the Midgam/Lazar, Kantar and Maagar Mochot templates)"},
            "isaranga": {"url": THIRD_PARTY["isaranga"], "seen": seen, "sha256": isaranga_files,
                         "gives": "respondents (sample_size, 'the number of respondents, not the initial sample' by its "
                                  ".claude/skills/add-poll/SKILL.md) for the filings it transcribed; its shares are "
                                  "normalised to 100%, not used"},
        },
        "filings": [filings[k] for k in sorted(filings, key=item_no)],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fetched", action="append", default=[], help="a poll_filings fetch directory (repeatable)")
    ap.add_argument("--polls", default=POLLS)
    ap.add_argument("--ref", default=REF)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--reference", action="store_true", help="rewrite the reference index from third parties' files")
    ap.add_argument("--or523")
    ap.add_argument("--amitlev")
    ap.add_argument("--isaranga", help="a directory of isaranga/SekerKolshehu poll files")
    ap.add_argument("--seen", help="the date the third parties' files were read (YYYY-MM-DD)")
    a = ap.parse_args(argv)
    if a.reference:
        if not (a.or523 and a.amitlev):
            ap.error("--reference needs --or523 and --amitlev")
        doc = reference(a.or523, a.amitlev, a.isaranga, a.ref, a.seen)
        print(f"{len(doc['filings'])} filings in {rel(a.ref)}")
        return 0
    doc = build(a.polls, a.ref, a.fetched, a.out)
    c = doc["counts"]
    print(f"{c['matched']}/{c['polls']} polls matched to a filing ({c['by_match']}); shares {c['with_pct']}, n {c['with_n']}, "
          f"sampling error {c['with_moe']}; read here: {c['verified']}; conflicts with polls_2026.json links: "
          f"{len(doc['conflicts'])}; filings {c['filings']}, unmatched {len(doc['unmatched_filings'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
