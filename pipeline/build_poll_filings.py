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
               itself has been read here and gave the pollster (the poll's and the listing's), the fieldwork dates
               (within two weeks, ending at most 10 days before the poll), a seat table of 120 (the poll's) and the
               respondents (no more than were asked, up to 10% over the initial sample: a panel's overshoot, and as
               those readings give them). polls_2026.json's own n is not a condition: where it differs, polls_n
               and the notes say so.
A poll is matched to a filing by its seats (all lists equal, fieldwork ending at most 10 days before publication);
else by its polling house and the date (at most 3 days apart, at most 6 seats different, the differences listed);
else by the link polls_2026.json already carries. Each filing goes to one poll at most. Where polls_2026.json links
another filing than the one matched, "conflicts" says from the two PDFs which is the poll's (conflict); each filing
no poll has is in "unmatched_filings" with why (classify: a sector poll, a re-filing, before the poll table, not in
it...), for adding polls by hand: polls_2026.json is not changed here.

Run:
  python3 pipeline/build_poll_filings.py [--fetched DIR ...]      (DIR: a poll_filings fetch, e.g. ops-reports'
                                                                   reports/fetch/poll_filings/latest)
  python3 pipeline/build_poll_filings.py --reference --or523 F --amitlev F [--isaranga DIR]
                                                                  (rewrites the reference index from those files)
  python3 pipeline/build_poll_filings.py --selftest               (the houses, the list names, the verified flag)
"""
import argparse
import datetime as dt
import functools
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
BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]")      # and the word joiner
NIQQUD = re.compile("[\u0591-\u05c7]")


@functools.lru_cache(maxsize=1 << 16)             # the field readers look at each line of a filing many times
def clean(s):
    """A line of extracted text: no bidi controls or niqqud, one spelling of each quote mark and dash."""
    s = BIDI.sub("", s or "")
    s = NIQQUD.sub("", s)
    s = re.sub("[\u05f4\u201c\u201d\u201e]", '"', s)
    s = re.sub("[\u05f3\u2018\u2019`]", "'", s)
    s = re.sub("[\u2010-\u2015\u05be]", "-", s)
    return s.replace("\u00a0", " ").replace("\t", "    ")


@functools.lru_cache(maxsize=1 << 16)
def fold(s):
    """For matching: clean, single spaces, final letters folded (רע"ם = רע"מ)."""
    s = re.sub(r"\s+", " ", clean(s)).strip()
    return s.translate(str.maketrans("םןךףץ", "מנכפצ"))


def word(name):
    """A folded name found as whole words only: 'ביחד' is not in 'ביחדנו', 'מדגם' not in 'במדגם'."""
    return re.compile(("(?<!\\w)" if re.match(r"\w", name) else "") + re.escape(name)
                      + ("(?!\\w)" if re.search(r"\w$", name) else ""))


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
    ("Shas", ['ש"ס', "שס בראשות", "התאחדות הספרדימ"], ["דרעי"]),
    ("Likud", ["הליכוד", "ליכוד"], ["נתניהו"]),
    ("The Democrats", ["הדמוקרטימ"], ["יאיר גולנ"]),
    ("Yashar", ["ישר!", "ישר !", "ישר"], ["איזנקוט", "אייזנקוט"]),        # 'ישר' alone: Direct Polls'
    ("Together", ["ביחד", "יחד בראשות"], ["נפתלי בנט", "יאיר לפיד"]),
    ("Reservists", ["המילואימניקימ", "המילואמיניקימ", "המילואימניקיס", "בית ציוני"], ["הנדל", "טרופר"]),
    # Lazar's 'רשימה ערבית משותפת של חדש תעל ובלד בראשות יוסף גאברין': no quote marks, the leader spelt with א
    ("Joint List", ["הרשימה המשותפת", 'חד"ש', 'תע"ל', 'בל"ד', "חדש תעל"],
     ["עודה", "ג'בארינ", "גבארינ", "ג'אברינ", "גאברינ", "טיבי"]),
    ("Ra'am", ['רע"מ', "רעמ בראשות", "הרשימה הערבית המאוחדת"], ["עבאס"]),
    ("National Unity", ["כחול לבנ"], ["בני גנצ"]),
]
# lists on some filings that polls_2026.json does not carry: their share counts as below the threshold
OTHER = [("Unity", ["האחדות"], ["ארדנ"]), ("Yesodot Yisrael", ["יסודות ישראל"], [])]
# names of no list polls_2026.json carries, with those of the untracked lists on the ballot (lists_2026.json): a
# tracked list's name inside one of them is not that list ('ביחד' in 'ביחד נצליח', list בד)
UNTRACKED = ["נעמ", "ישראל תחילה", "עלה ירוק", "הבית היהודי", "מרצ", "העבודה", "זהות", "מפלגות אחרות", "אחרימ",
             "הכלכלית החדשה", "מפלגה אחרת", "רשימות אחרות", "אחר"]
LISTS = os.path.join(ROOT, "pipeline", "reference", "lists_2026.json")


def ballot_names(path=LISTS):
    """(names, leaders), folded, of the lists on the ballot that polls_2026.json does not carry (lists_2026.json, the
    lists without an id): each official name and the short forms a pollster types (the words before a dash or
    'בראשות', without 'מפלגת'), and the leader the name gives ('בראשות אבי שקד')."""
    try:
        lists = json.load(open(path, encoding="utf-8"))["lists"]
    except (OSError, ValueError, KeyError, TypeError):
        return [], []
    names, leaders = set(), set()
    for l in lists:
        if l.get("id") or not isinstance(l.get("official_name"), str):
            continue
        full = fold(l["official_name"])
        for n in (full, full.split(" - ")[0], full.split(" בראשות ")[0]):
            n = n.strip(' "-')
            names.update(x for x in (n, re.sub(r"^מפלג[הת] ", "", n)) if x)
        if " בראשות " in full:
            leaders.add(re.sub(r"^הרב ", "", full.split(" בראשות ", 1)[1].strip()))
    return sorted(names), sorted(leaders)


_RULES = [(i, [word(fold(n)) for n in ns], [fold(x) for x in ls]) for i, ns, ls in RULES + OTHER]
_BALLOT, _BALLOT_LEADERS = ballot_names()
_OFF = [word(n) for n in sorted({fold(n) for n in UNTRACKED} | set(_BALLOT))]
_OFF_LEADERS = [word(x) for x in _BALLOT_LEADERS]


def party_id(label):
    """The id of the list a filing's label names, or None. A name counts as whole words and not inside the name of
    a list this does not track ('ביחד' in 'מפלגת ביחד נצליח', list בד), and a label that names such a list, or its
    leader, and no tracked leader is none of the tracked lists. Also tried reversed (text read in visual order)."""
    for f in (fold(label), fold(label)[::-1]):
        if not f:
            continue
        led = next((i for i, _, ls in _RULES if any(x in f for x in ls)), None)
        if led is None and any(r.search(f) for r in _OFF_LEADERS):
            return None
        off = [m.span() for r in _OFF for m in r.finditer(f)]
        for i, ns, _ in _RULES:
            for r in ns:
                if any(not any(a <= m.start() and m.end() <= b and b - a > m.end() - m.start() for a, b in off)
                       for m in r.finditer(f)):
                    return i
        if led is not None or off:
            return led
    return None


TRACKED = {i for i, _, _ in RULES}


# ------------------------------------------------------------------ polling houses
# (pattern in the filing's editor or commissioner, house id as in polls_2026.json). Rozner's Channel 13 polls
# (Midgam Project and StatNet) before Midgam's own. Channel 14's polls are Next Data's, which its PDFs name in Latin
# letters ('חברת Next Data', Shlomo Filber its research director); the DRI institute's name too ('מכון DRI'). No
# PDF names S.M.L.T., the house polls_2026.json gives the DRI filing of 7.9.2026 (knesset_election59): the two are
# kept apart, and that poll is reported, not verified.
HOUSES = [("רוזנר", "ch13"), ("פרויקט", "ch13"), ("סטטנט", "ch13"), ("קנטאר", "kantar"), ("קאנטר", "kantar"),
          ("kantar", "kantar"), ("דיירקט", "direct-polls"), ("direct polls", "direct-polls"), ("נקסט דאטה", "filber"),
          ("next data", "filber"), ("פילבר", "filber"), ("לזר", "lazar"), ("מאגר מוחות", "maagar-mochot"),
          ("טאטיקה", "yossi-tatika"), ("טטיקה", "yossi-tatika"), ("מדגם", "midgam"), ("דיאלוג", "dialog"),
          ("אקורד", "accord"), ("די אר איי", "dri"), ("dri", "dri"), ("אפקאר", "afkar")]


def _house_re(p):
    """A pattern of HOUSES as whole words; a Latin one bounded by Latin letters only, since the layout glues it to
    the Hebrew next to it ('חברת  ,Next Dataהמנופים', 'מכון  ,DRIבוסתנאי')."""
    if re.fullmatch(r"[a-z0-9 .]+", p):
        return re.compile(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])")
    return word(fold(p).lower())                      # folded as the text is: 'מדגם' is 'מדגמ' in both


_HOUSES = [(_house_re(p), h) for p, h in HOUSES]


def house_of(*names):
    """The house the first of these names that names one gives (a filing's editor, then its commissioner)."""
    for n in names:
        f = fold(n).lower()
        if f:
            for r, h in _HOUSES:
                if r.search(f):
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
DASHED = re.compile(r"(?<![\d-])(\d{1,2})-(\d{1,2})-(20\d\d)(?!\d)")         # Afkar's '27-8-2026'
# a range in a fieldwork value whose first day the layout moved after the date ('4.8.2026–3' is '3–4.8.2026')
RANGE_AFTER = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})\s*-\s*(\d{1,2})(?![\d./:])")
# a day and month with no year ('בתאריכים ה 26/8-בשעה 12:00'), read in a fieldwork value only: not a time
# (12:00), a share (4.4%) or a decimal
BARE_DATE = re.compile(r"(?<![\d.:/])(\d{1,2})[./](\d{1,2})(?![\d.:/%])")
MONTHS = {"ינואר": 1, "פברואר": 2, "מרצ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6, "יולי": 7, "אוגוסט": 8,
          "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12}
MONTH = re.compile(r"(?<![א-ת])[בל]?(" + "|".join(MONTHS) + r")(?![א-ת])")
DAY = re.compile(r"(?<![\d:.,/])(\d{1,2})(?![\d:.,/%])")


def dates_in(s, bare=False):
    """The dates a filing writes (12/10/2026, 12.10.26, 11-12/10/2026), sorted, in the 2026 campaign only. With
    bare (a fieldwork value): also a day and month alone (26/8) and a day and a Hebrew month ('6 בספטמבר (11:40) – 6
    בספטמבר (16:15)', '17בספטמבר ,2026'), of 2026, when the value writes no full date. The layout moves the second
    day of an RTL range away from its month ('2 בספטמבר ( 3 – )15:40 בספטמבר'): the days, not times, are paired with
    the months in their order."""
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
    for m in list(DATE.finditer(s)) + list(DASHED.finditer(s)):
        v = mk(*m.groups())
        if v:
            out.add(v)
    for m in RANGE_AFTER.finditer(s) if bare else []:
        v = mk(m.group(4), m.group(2), m.group(3))
        if v and out and 0 < (min(out) - v).days <= 7:
            out.add(v)
    if bare and not out:
        f = fold(s)
        months = [MONTHS[m.group(1)] for m in MONTH.finditer(f)]
        if months:
            days = [int(m.group(1)) for m in DAY.finditer(re.sub(r"\d{1,2}:\d{2}", " ", f))
                    if 1 <= int(m.group(1)) <= 31]
            if len(months) == 1:
                months = months * len(days)
            if days and len(days) == len(months):
                out.update(v for v in (mk(d, mo, "2026") for d, mo in zip(days, months)) if v)
        else:
            out.update(v for v in (mk(d, mo, "2026") for d, mo in BARE_DATE.findall(s))
                       if v and v >= dt.date(2026, 7, 1))
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
# (src/scrape_cec.py) word them, and as the filings fetched on 16.10.2026 do (Channel 13's 'מועד איסוף נתונים',
# Next Data's and DRI's 'תאריך ביצוע הסקר', 'שיעור האנשים שלא השתתפו', 'איסוף הנתונים' and 'עיבוד הסקר', Next
# Data's running text 'היקף הפנייה :הסקר נשלח ל 59,580-איש', Direct Polls' 'מרווח טעות', Tatika's running text
# 'השיבו לו 500משיבים ,סטיית תקן 4.4%', the sampling error it states); the most specific first.
LABELS = {
    "commissioner": ["שם הגוף שהזמין את הסקר", "מזמין הסקר ומענו", "מזמין הסקר", "הגוף שהזמין"],
    "pollster": ["הגורם שערך את הסקר", "הגוף שערך את הסקר", "שם עורך הסקר", "עורך הסקר ומענו", "עורך הסקר",
                 "מבצע הסקר"],
    "fieldwork": ["מועד איסוף הנתונים", "מועד איסוף נתונים", "מועד עריכת הסקר", "מועד ביצוע הסקר",
                  "תאריך עריכת הסקר", "תאריך ביצוע הסקר", "תאריך הביצוע", "תאריכי", "התאריכים", "מועד הסקר"],
    "sampling": ["שיטת הדגימה"],
    "n_initial": ["גודל המדגם ההתחלתי", "גודל מדגם התחלתי", "מדגם התחלתי"],
    "population": ["סוגי האוכלוסייה שנדגמו", "סוגי האוכלוסיה שנדגמו", "סוג האוכלוסייה", "האוכלוסייה שנדגמה",
                   "אוכלוסיית המדגם", "אוכלוסיית המחקר"],
    "invited": ["מספר המתבקשים להשתתף", "מס' האנשים שהתבקשו להשתתף", "מספר האנשים שהתבקשו", "מס' האנשים אליהם פנו",
                "מספר האנשים אליהם פנו", "מספר המתבקשים", "היקף הפנייה"],
    "n": ["מספר המשיבים", "מס' המשיבים", "מס' האנשים שהשתתפו בסקר בפועל", "מספר האנשים שהשתתפו בסקר בפועל",
          "מספר המשתתפים בסקר", "מספר משיבים", "גודל המדגם הסופי"],
    "response_rate": ["אחוז המשתתפים בסקר", "שיעור ההיענות לסקר", "שיעור ההיענות", "שיעור היענות", "אחוז ההיענות"],
    "refused": ["מספר האנשים שסרבו", "מספר האנשים שסירבו", "מס' האנשים שסרבו", "מס' האנשים שסירבו"],
    "refused_pct": ["אחוז האנשים שסרבו", "אחוז האנשים שסירבו", "שיעור האנשים שסרבו", "שיעור האנשים שסירבו",
                    "שיעור האנשים שלא השתתפו", "אחוז הסירוב", "שיעור הסירוב"],
    "moe": ["טעות הדגימה המרבית", "טעות הדגימה המירבית", "טעות הדגימה", "טעות דגימה", "מרווח הטעות", "מרווח טעות",
            "גודל הטעות הסטטיסטית", "טעות סטטיסטית", "סטיית תקן"],
    "method": ["השיטה הסטטיסטית", "שיטה סטטיסטית", "עיבוד הסקר"],
    "mode": ["אופן ביצוע הסקר", "אופן איסוף הנתונים", "שיטת איסוף הנתונים", "איסוף הנתונים"],
}
TEXT_FIELDS = ("commissioner", "pollster", "sampling", "population", "method", "mode")
RANGES = {"n_initial": (100, 2_000_000), "invited": (100, 2_000_000), "n": (100, 100_000), "refused": (0, 2_000_000),
          "response_rate": (0.1, 100), "refused_pct": (0, 100), "moe": (0.5, 15)}
ALL_LABELS = sorted({fold(x) for v in LABELS.values() for x in v}, key=len, reverse=True)
UNDECIDED = ["לא החליטו", "לא החלטתי", "טרם החליט", "לא יודע", "מתלבט", "אינו יודע"]
# '550 משיבים', 'השיבו לו  500משיבים', 'משיבים 588 :נדגמים'; not the year the layout glues to the word ('| 2026משיבים')
RESPONDENTS = re.compile(r"(?<![\d.,])(?!2026)(\d{1,3}(?:,\d{3})+|\d{3,6})\s*:?\s*"
                         r"(?:משיבים|משיבות|נשאלים|מרואיינים|נדגמים)")
RAN_BY = re.compile(r'(?<![א-ת])(?:נאספו|בוצע|נערך|עובד|נותח)\s+(?:[^\s]+\s+){0,5}?(?:בידי|על ידי|ע"י)\s+(חברת\s+.{2,40}?|'
                    r'(?!חברת).{2,40}?)(?=\s{2,}|\s*(?:באמצעות|בשיטת|בע"מ)|[.,;]|$)')
N_EQUALS = re.compile(r"(?<![A-Za-z])N\s*=\s*(\d{1,3}(?:,\d{3})+|\d{3,6})(?![\d,])")      # 'N = 656 | ...'
COUNTS = ("n", "n_initial", "invited", "refused")


def cells(line):
    """The cells of a line of pdftotext -layout output: runs of text separated by two spaces or more."""
    return list(_cells(line))


@functools.lru_cache(maxsize=1 << 16)
def _cells(line):
    return tuple(c.strip() for c in re.split(r"\s{2,}", clean(line).strip()) if c.strip())


def find_field(lines, key):
    """(value, the line it was read from) of one disclosure field, or (None, None). In an RTL table the value cell
    stands left of the label, so pdftotext -layout writes it before the label; in running text it follows. A label
    whose cell holds nothing else but a few words of the label ('מספר המשיבים בפועל', 'מס' האנשים שסירבו /') is
    alone on its line: its value wrapped around it, on the line above and the line below; a sentence that starts
    with a label ('שיעור ההיענות כולל את כל מי שניגש לשאלון...', a footnote) is not. A text value cut in the middle
    ('...בסקר אינטרנטי ו-' over '221מהאוכלוסייה הלא יהודית בתשאול טלפוני  שיטת איסוף הנתונים') takes its other
    half from the line before or after. A fieldwork value is the dates anywhere on the label's line (running text
    splits it in cells: 'בתאריכים ה 26/8-בשעה  12:00עד ה 27/8-בשעה'), else on the lines around it (Maagar Mochot's
    '25-26.8.26' above a line with a typo, '25/7'). A label wrapped over two or three lines in its column, its
    value on one of them (Next Data's 'גודל המדגם' / '2,200איש' / 'ההתחלתי'), is read last (wrapped_field)."""
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
                if key in TEXT_FIELDS:
                    # a cell is single-spaced and stripped, so fold() kept its places: the text as written
                    rest = clean(c)[k + len(fl):].strip(" :-")
                # a longer label that holds this one here ("גודל המדגם" in "גודל המדגם ההתחלתי", "איסוף הנתונים" in
                # "מועד איסוף הנתונים") is another field
                if any(len(o) > len(fl) and fl in o and any(m.start() <= k and k + len(fl) <= m.end()
                                                            for m in re.finditer(re.escape(o), fc))
                       for o in ALL_LABELS):
                    continue
                if key == "fieldwork":
                    cands = [" ".join([rest] + cs[:j] + cs[j + 1:])]
                elif key in TEXT_FIELDS and j == 0 and rest:
                    cands = [" ".join([rest] + cs[1:])]             # running text: 'label: value' to the line's end
                else:
                    cands = [rest] if rest else []
                    if j:
                        cands += [cut(lines, i, " ".join(cs[:j])) if key in TEXT_FIELDS else " ".join(cs[:j])]
                    cands += [" ".join(cs[j + 1:])] if j + 1 < len(cs) else []
                alone = len(cs) == 1 and not re.search(r"\d", rest) and len(re.findall(r"[^\s/,.:()-]+", rest)) <= 3
                if key == "fieldwork" or alone and value_of(key, rest) is None:
                    # the label alone on its line: the value wrapped around it (the line above, the line below)
                    near = [" ".join(cells(lines[x])) for x in (i - 1, i + 1)
                            if 0 <= x < len(lines) and not is_field(lines[x])]
                    cands += [" ".join(near)] if key in TEXT_FIELDS + ("fieldwork",) and near else near
                for cand in cands:
                    v = value_of(key, cand)
                    if v is not None:
                        return v, clean(line).strip()
    return wrapped_field(lines, key)


def cut(lines, i, value):
    """A text value on line i with its half on the line before or after, when it was cut in the middle: the line
    before ends in '-' or ',' ('...בסקר אינטרנטי ו-' over '221מהאוכלוסייה...'), or the value does ('...אריאל
    איילון,' over 'חברת סטטנט נט...'); that line no field's."""
    def other(x):
        return " ".join(cells(lines[x])) if 0 <= x < len(lines) and not is_field(lines[x]) else None
    before, after = other(i - 1), other(i + 1)
    if before and re.search(r"[-,]$", before):
        value = before + " " + value
    if after and re.search(r"[-,]$", value):
        value = value + " " + after
    return value


def wrapped_field(lines, key):
    """(value, its lines) of a field whose label wraps over two or three lines in the label column, as Next Data's
    table sets it: 'מספר האנשים' / '7,862איש  שהתבקשו להשתתף' / 'בסקר', 'גודל המדגם' / '2,200איש' / 'ההתחלתי',
    'שיעור האנשים שלא' / '89%' / 'השתתפו'. A line's last cell is a piece of the label when it has no figure and
    a few words; the label's pieces, joined, start with the label, and its first line holds a piece; the value is in
    the other cells of those lines. (None, None) when there is none."""
    def piece(cs):
        return cs[-1] if cs and not re.search(r"\d", cs[-1]) and len(cs[-1].split()) <= 4 else None
    for label in LABELS[key]:
        fl = fold(label)
        for i in range(len(lines) - 1):
            for w in (2, 3):
                win = [cells(l) for l in lines[i:i + w]]
                if len(win) < w or piece(win[0]) is None or fl in fold(piece(win[0])):
                    continue
                if any(is_field(l) and fl not in fold(l) for l in lines[i:i + w]):
                    continue
                heads = [piece(cs) for cs in win]
                joined = fold(" ".join(h for h in heads if h))
                if not joined.startswith(fl):
                    continue
                vals = [c for cs, h in zip(win, heads) for c in (cs[:-1] if h else cs)]
                for cand in vals + ([" ".join(vals)] if key in TEXT_FIELDS and vals else []):
                    v = value_of(key, cand)
                    if v is not None:
                        return v, " / ".join(" ".join(cs) for cs in win)
                break
    return None, None


def value_of(key, s):
    s = s.strip(" :")
    if not s or any(fold(s).startswith(l) for l in ALL_LABELS):
        return None
    if key == "fieldwork":
        ds = dates_in(s, bare=True)
        return (ds[0], ds[-1]) if ds else None
    if key in TEXT_FIELDS:
        s = s.strip(" :§•")                                            # Tatika's bullets
        return re.sub(r"\s+", " ", s)[:200] if re.search("[א-תA-Za-z]", s) else None
    s = DATE.sub(" ", DAY_RANGE.sub(" ", clean(s)))                    # a date's digits are not a count
    nums = numbers(s)
    lo, hi = RANGES[key]
    for k, v in enumerate(nums):
        if lo <= v <= hi:
            if key in COUNTS and glued(s, k):
                # a count glued to an opening bracket ('333( 815אינטרנטי ו 482 -תשאול טלפוני)', which is
                # '815 (333 אינטרנטי ו-482 טלפוני)' with its figures moved by the layout): a part of a
                # wrapped sentence, taken only as the total its other figures add up to, else not at all
                tot = [x for x in nums if lo <= x <= hi and x == sum(y for y in nums if y != x) and x == int(x)]
                return int(tot[0]) if tot else None
            return int(v) if key in COUNTS and v == int(v) else v
    return None


def glued(s, k):
    """Whether the k-th number of s (as numbers() reads them) is written glued to an opening bracket after it."""
    ms = list(NUM.finditer(s))
    return k < len(ms) and s[ms[k].end(1):ms[k].end(1) + 1] == "("


VALUE = re.compile(r"[±]?\d{1,3}(?:\.\d+)?\s*%?")
NO_SEATS = ("-", "לא עבר")             # a seats cell that says the list did not pass (Tatika, Maagar Mochot)
JUNK = re.compile(r"[\d.,+%±/()\s-]+")  # '3.1+0.9', '18-29': figures that are neither a label nor one value
NOT_A_LIST = ["לא החליטו", "לא החלטתי", "טרם החליט", "טרם החלטתי", "לא יודע", "מתלבט", "אינו יודע", "לא יצביע",
              "לא אצביע", "לא מצביע", "לא מתכוון להצביע", "פתק לבן", "מסרב", "סירב", "לא ענה"]


def spans(text):
    """The cells of a line of pdftotext -layout output with their columns: [(text, start, end)]. The layout sets
    each cell at its place on the page and the bidi marks it adds take no column, so after clean() a column is a
    column on every line."""
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+(?: \S+)*", clean(text))]


def is_seat(text):
    return "%" not in text and "." not in text


def table_rows(lines):
    """Candidate rows of a seat table, one per line with a value: {"i": line index, "label", "lstart": its
    column, "vals" and "marks": [(text, start, end)]}. In pdftotext -layout output a cell that is all number
    (17.0%, 21, 4) is a value, '-' or 'לא עבר' in a seats column a mark, and the other cells the label; a line not
    split in cells ("הליכוד 21 17.0%") gives its leading and trailing numbers. A line of numbers only is the row of
    the label on the line above, else the total of a table that writes none ("100.0%  120"), else a figure the
    layout set apart from its row ("orphan")."""
    rows, text_only = [], None
    for i, line in enumerate(lines):
        cs = spans(line)
        vals = [c for c in cs if VALUE.fullmatch(c[0])]
        marks = [c for c in cs if c[0] in NO_SEATS]
        junk = [c for c in cs if c not in vals and c not in marks and JUNK.fullmatch(c[0])]
        rest = [c for c in cs if c not in vals and c not in marks and c not in junk]
        if not vals:
            toks = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", clean(line))]
            lead, tail = [], []
            while toks and VALUE.fullmatch(toks[0][0]):
                lead.append(toks.pop(0))
            while toks and VALUE.fullmatch(toks[-1][0]):
                tail.insert(0, toks.pop())
            vals, rest, marks, junk = lead + tail, toks, [], []
        label = " ".join(c[0] for c in rest)
        if not vals:
            text_only = (i, label, rest[0][1]) if re.search("[א-ת]", label) else None
            continue
        lstart = rest[0][1] if rest else None
        if not re.search("[א-ת]", label):
            if text_only and text_only[0] == i - 1 and not label:
                # the numbers of a row whose name the layout put on the line above
                label, lstart = text_only[1], text_only[2]
            else:
                total = any(is_seat(v[0]) and v[0].strip("± ") == "120" for v in vals)
                rows.append({"i": i, "label": 'סה"כ' if total else "", "lstart": None, "vals": vals,
                             "marks": marks + junk, "orphan": not total})
                text_only = None
                continue
        text_only = None
        rows.append({"i": i, "label": label, "lstart": lstart, "vals": vals, "marks": marks + junk})
    return rows


def resolve(row, cols=None):
    """(seats, share, ambiguous) of a row. Alone, its values say it: one figure with neither '%' nor '.' is the
    seats, one share the share; several shares give none (Channel 13: one per sub-sample), one share written twice
    is one (Direct Polls: a list below the threshold has its share in the seats column too), several seat figures
    are ambiguous. With the table's header (cols, from header_cols, one seats column in it) the columns say it:
    each figure belongs to the header cell nearest it (the layout shifts a few rows of a column: Tatika's), the
    seats are what is in the seats column ('-', 'לא עבר', a share or a fraction there: a list below the threshold,
    no seats), the share the one in a column of raw shares, other figures (a count of respondents, earlier weeks,
    the share of those with an opinion) are not the row's; two figures in the seats column are ambiguous."""
    vals = row["vals"]
    pcts = [v for v in vals if not is_seat(v[0])]
    if len(pcts) == 2 and pcts[0][0] == pcts[1][0] and len(vals) == 2:
        pcts = pcts[:1]
    if cols and sum(1 for c in cols if c[0] == "seats") == 1:
        cols = sorted(cols, key=lambda c: c[1])
        cells = sorted(vals + row["marks"], key=lambda c: c[1])
        weeks = [c[0] for c in cols if c[0] in ("week", "seats")]

        def kind(cell):
            if len(cells) == len(cols):
                # as many figures as the header has columns: in its order, wherever the layout set them (Tatika's
                # last rows at another scale, a narrow column's cell moved: '9        9             9       8')
                return cols[cells.index(cell)][0]
            mid = (cell[1] + cell[2]) / 2
            return min(cols, key=lambda c: abs(mid - (c[1] + c[2]) / 2))[0]
        if len(cells) != len(cols) and len(weeks) > 1 and len(cells) > len(weeks) and not any(
                "%" in c[0] for c in cells[:len(weeks)]):
            # a table of several weeks: a row's first figures are its weeks, in the header's order
            under = [cells[weeks.index("seats")]]
        else:
            under = [v for v in cells if kind(v) == "seats"]
        if len(under) > 1:
            return None, None, True
        u = under[0][0].strip("± ") if under else None
        seats = int(u) if u and u.isdigit() else (0 if u else None)
        pcts = [v for v in pcts if not under or v is not under[0]]
        if len(pcts) > 1:
            pcts = [v for v in pcts if kind(v) == "raw"]
    else:
        ints = [v for v in vals if is_seat(v[0])]
        if len(ints) > 1:
            return None, None, True
        seats = int(ints[0][0].strip("± ")) if ints else None
    pct = float(pcts[0][0].strip("%± ")) if len(pcts) == 1 else None
    return seats, pct, False


def header_cols(lines, i0, rows_at, right, fw_end=None):
    """The columns a seat table's header names, from the lines just above its first row (up to five, none of
    them a row), left of the labels (right: where they start): [(kind, start, end)], one per header cell, kind
    "seats" ('מנדטים'), "raw" (raw shares: 'גולמי', 'ללא שקלול'), "share" ('אחוז משיבים'), "count" ('מספר
    משיבים'), or "other" (a cell naming none of them, or two). In a table of several weeks side by side (Maagar
    Mochot: '26.8.26  2.9.26  9.9.26 16.9.26') each date is a column, the seats column the one dated the end of the
    poll's fieldwork (none when the fieldwork is not known: such a table is not read) and a cell naming seats there
    is the heading over all the weeks, not a column."""
    cols, dated = [], []
    for k in range(i0 - 1, max(-1, i0 - 6), -1):
        if k in rows_at:
            break
        text = clean(lines[k])
        ds = [(m.start(), m.end(), dates_in(m.group(0))) for m in DATE.finditer(text)
              if (m.start() + m.end()) / 2 < right]
        dated += ds
        for t, a, b in spans(text):
            if (a + b) / 2 >= right or any(a <= x < b for x, _, _ in ds):
                continue
            f = fold(t)
            kinds = [x for x, hit in (("seats", "מנדט" in f), ("raw", "גולמי" in f or "ללא שקלול" in f),
                                      ("count", "מספר" in f and "אחוז" not in f)) if hit]
            cols.append((kinds[0] if len(kinds) == 1 else "share" if "אחוז" in f and not kinds else "other", a, b))
    if len(dated) >= 2:
        cols = [c for c in cols if c[0] != "seats"]
        cols += [("seats" if d and fw_end and d[0].isoformat() == fw_end else "week", a, b) for a, b, d in dated]
    # the cells of one column on the header's several lines ('אחוזים' / 'גולמיים' / 'ללא שקלול'): one column,
    # of the most telling kind among them
    rank = ["seats", "raw", "count", "share", "week", "other"]
    out = []
    for k, a, b in sorted(cols, key=lambda c: (c[1], c[2])):
        if out and a < out[-1][2]:
            k0, a0, b0 = out[-1]
            out[-1] = (min(k0, k, key=rank.index), a0, max(b0, b))
        else:
            out.append((k, a, b))
    return out


def is_total(label):
    return 'סה"כ' in fold(label) or "סך הכל" in fold(label) or 'סה"כ' in fold(label)[::-1]


@functools.lru_cache(maxsize=1 << 16)
def is_field(label):
    f = fold(label)
    return any(l in f for l in ALL_LABELS)


def find_main_table(lines, fw_end=None):
    """The first seat table: a run of rows (at most two lines that are not rows between two rows), cut at a
    disclosure field's line and ended by a total row (סה"כ, or a line of numbers with 120), whose seats add up to
    120, with five rows or more naming a list: [row with "seats" and "pct"]. Its rows are read alone (resolve) and,
    where that is not one seats figure per row, a share column beside a count of respondents or a '-' in the seats
    column, by its header's columns (header_cols): a table of several weeks side by side only when its header
    dates the poll's own week. None when there is none, or when a figure stands apart from its row inside the run
    (Channel 13's filings of July: a seats column one row out of step with the names), or anything else this
    reader did not clearly understand."""
    rows = table_rows(lines)
    rows_at = {r["i"] for r in rows}
    orphans = [r for r in rows if r.get("orphan")]
    segs, cur = [], []
    for r in rows:
        if r.get("orphan"):
            continue
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
        if sum(1 for r in body if party_id(r["label"]) and any(is_seat(v[0]) for v in r["vals"])) < 5:
            continue
        # the first table of lists with seats is the poll's; when it is not read, a later one (a scenario: 'if
        # the two lists ran together') is not taken for it. The longest run that ends where the segment ends (at
        # its total row) and adds up to 120: a line above the table that happens to end in a number ("עבור ערוץ
        # 16") is not one of its rows
        for start in range(len(body)):
            run = body[start:]
            named = [r for r in run if party_id(r["label"])]
            if len(named) < 5:
                break
            right = min(r["lstart"] for r in named if r["lstart"] is not None)
            res = [resolve(r) for r in run]
            cols = header_cols(lines, run[0]["i"], rows_at, right, fw_end)
            if any(c[0] == "count" for c in cols) or any(r["marks"] for r in run) or any(
                    x[2] for r, x in zip(run, res) if party_id(r["label"])):
                res = [resolve(r, cols) for r in run]
            if any(x[2] for r, x in zip(run, res) if party_id(r["label"])):
                continue
            res = below_threshold(res)
            if sum(x[0] or 0 for x in res) != 120:
                continue
            if any(run[0]["i"] < o["i"] < run[-1]["i"] and min(v[1] for v in o["vals"]) < right for o in orphans):
                continue
            return [dict(r, seats=x[0], pct=x[1]) for r, x in zip(run, res)]
        return None
    return None


THRESHOLD = 3.25


def below_threshold(res):
    """A table that gives the lists below the threshold what they would win without it (Maagar Mochot's of
    3.9.2026: 'הבית הציוני  3  2%', 'המפלגה הכלכלית  2.7  2%'): when its seats pass 120, the rows after those that
    make 120, each with a share under 3.25%, have no seats. Anything else stays as it is (and is not read)."""
    total, k = 0, 0
    while k < len(res) and total < 120:
        total += res[k][0] or 0
        k += 1
    rest = res[k:]
    if total != 120 or not any(x[0] for x in rest) or not all(x[1] is not None and x[1] < THRESHOLD
                                                              for x in rest if x[0]):
        return res
    return res[:k] + [(0 if x[0] else x[0], x[1], x[2]) for x in rest]


# a poll of one group, not of the electorate: its population (or, lacking one, its title) names the group. A
# national poll's says 'כלל האוכלוסייה', 'אזרחי ישראל', 'יהודים וערבים'.
SECTOR = ["משרתי מילואים", "ליברלים", "הזרם הדתי", "דתי-לאומי", "דתי לאומי", "האוכלוסיה הערבית",
          "האוכלוסייה הערבית", "בחברה הערבית", "המגזר הערבי", "שאינם חרדים", "בוחרי הימין", "בוחרי השמאל", "תושבי"]
AGE_RANGE = re.compile(r"(?:בני|בגילאי|גילאי)\s*\(?\s*\d{2}\s*-\s*\d{2}(?!\d)")


def sector_of(population, head):
    """The words that make a filing a sector poll (SECTOR, or an age range: 'בני 18-22', 'בגילאי ( 34–22'), or
    None: its population field first, else its first lines."""
    for text in ([population] if population else []) + [" ".join(head)]:
        f = fold(text)
        hit = [w for w in SECTOR if word(fold(w)).search(f)] + [m.group(0) for m in AGE_RANGE.finditer(f)]
        if hit:
            return hit[0]
    return None


# Channel 13's sub-samples, each on a line of its own in the field of those asked: 'מדגם בוגרים יהודים - 4,478מתבקשים
# להשיב ,שיעור היענות ,32.6%...', 'מדגם 5098 - 1מתבקשים להשיב 11.7% ,היענות' (sample 1, its number moved by the
# layout), and one with no count, 'מדגם חרדים טלפוני - 220משיבים תקינים'
ASKED = re.compile(r"(?<![\d,])(\d{1,3}(?:,\d{3})+|\d{3,6})(?:\s*-\s*\d)?\s*מתבקשימ להשיב")
SUBSAMPLE = re.compile(r"(?:^|\s)מדגמ\s[^-]{0,30}-")


def subsamples(lines):
    """([count of those asked, per sub-sample], [the lines of sub-samples that state none]) of a filing whose field
    of those asked lists two sub-samples or more (Channel 13's), else None."""
    asked = [(i, int(m.group(1).replace(",", ""))) for i, l in enumerate(lines) for m in [ASKED.search(fold(l))] if m]
    if len(asked) < 2:
        return None
    missing = [re.sub(r"\s+", " ", clean(l)).strip() for l in lines[asked[0][0]:asked[-1][0] + 1]
               if not ASKED.search(fold(l)) and SUBSAMPLE.search(fold(l))]
    return [c for _, c in asked], missing


def below_table(lines, start):
    """(kind, [(label, share)]) of the lists below the threshold that a filing gives in a table of their own after
    its seat table (Next Data's: 'מפלגות שלא עברו את אחוז החסימה (מתחת ל-3.25%)', a header 'אחוז גולמי  רשימה',
    then '2.1%   עמך ישראל בראשות עופר וינטר'...), from its line start on: each row one share and a name, up to the
    first line that is not one. kind is what its header says the shares are: "raw" ('גולמי', as the seat table's),
    "weighted" ('אחוז משוקלל', some of Next Data's: not raw shares) or None; (None, []) when there is none."""
    for k in range(start, min(len(lines), start + 12)):
        if "שלא עברו את אחוז" not in fold(lines[k]):
            continue
        out, kind = [], None
        for x in range(k + 1, min(len(lines), k + 25)):
            r = table_rows([lines[x]])
            r = r[0] if r else None
            if (r and re.search("[א-ת]", r["label"]) and len(r["vals"]) == 1 and not is_seat(r["vals"][0][0])
                    and not r["marks"] and not is_total(r["label"])):
                out.append((re.sub(r"\s+", " ", r["label"]).strip(), float(r["vals"][0][0].strip("%± "))))
            elif out or x > k + 2:
                break
            elif not r:
                f = fold(lines[x])
                kind = kind or ("raw" if "גולמי" in f else "weighted" if "משוקלל" in f else None)
        return kind, out
    return None, []


def parse_filing(text):
    """The fields of one filing's text (pdftotext -layout): metadata, the main seat table, the shares."""
    lines = [l for l in (text or "").splitlines() if l.strip()]
    out, read_from = {}, {}
    for key in LABELS:
        v, line = find_field(lines, key)
        if v is not None:
            out[key] = v
            read_from[key] = line[:160]
    if "pollster" not in out:
        # no editor's label: who ran it, in running text ('הנתונים נאספו בידי חברת Next Data', 'הסקר בוצע ע"י
        # מאגר מוחות', 'ע"י חברת Next Data בע"מ')
        m = RAN_BY.search(clean(" ".join(lines)))
        if m:
            out["pollster"], read_from["pollster"] = re.sub(r"\s+", " ", m.group(1)).strip(" .,"), m.group(0)[:160]
    if "n" not in out:
        # running text ("הסקר נערך בקרב 550 משיבים"), the narrative template; its 'N = 656' first, before the
        # counts of its sub-groups ('בוחרי הליכוד 387 :משיבים')
        m = N_EQUALS.search(clean(" ".join(lines))) or RESPONDENTS.search(clean(" ".join(lines)))
        if m and 100 <= int(m.group(1).replace(",", "")) <= 100_000:
            out["n"], read_from["n"] = int(m.group(1).replace(",", "")), m.group(0)[:160]
    if "fieldwork" in out:
        out["fieldwork_start"], out["fieldwork_end"] = iso(out["fieldwork"][0]), iso(out["fieldwork"][1])
        if (out["fieldwork"][1] - out["fieldwork"][0]).days > 14:
            # Maagar Mochot's '1600-2400 1/8' over '0700-1500 2/9' (1/9): kept as written, said, and a doubt
            out["fieldwork_typo"] = True
            out.setdefault("notes", []).append(f"fieldwork {out['fieldwork_start']} to {out['fieldwork_end']} as "
                                               "the PDF writes it: over two weeks, its first date likely a typo")
        del out["fieldwork"]
    if out.get("moe") and out.get("n") and out["moe"] < moe_floor(out["n"]):
        out.setdefault("notes", []).append(f"sampling error {out['moe']} is below the minimum for n={out['n']}: "
                                           "not kept")
        del out["moe"]
    subs = subsamples(lines)
    if subs:
        # Channel 13's: no response rate of the whole; those asked the sum of the sub-samples', when each says it
        counts, missing = subs
        out.pop("response_rate", None)
        read_from.pop("response_rate", None)
        out["subsamples"] = len(counts) + len(missing)
        what = f"{out['subsamples']} sub-samples, each with its own response rate: none of the whole kept"
        if missing:
            out.pop("invited", None)
            read_from.pop("invited", None)
            what += (f"; {len(missing)} of them ('{missing[0][:40]}') states no count of those asked, so the "
                     f"number asked ({' + '.join(f'{c:,}' for c in counts)} in the others) is not given")
        else:
            out["invited"] = sum(counts)
            read_from["invited"] = "the sum of the sub-samples' 'מתבקשים להשיב': " + " + ".join(map(str, counts))
            what += f"; those asked, {out['invited']:,}, are the sum of theirs"
            if out.get("n_initial") and out["n_initial"] != out["invited"]:
                what += f" (the PDF's initial sample is {out['n_initial']:,})"
        out.setdefault("notes", []).append(what)
    sector = sector_of(out.get("population"), lines[:4])
    if sector:
        out["sector"] = sector
    table = find_main_table(lines, out.get("fieldwork_end"))
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
        kind, extra = below_table(lines, table[-1]["i"] + 1)
        if extra and kind != "raw":
            # weighted shares (or shares of a kind not said) are not the raw shares of the seat table: kept apart
            out["below_weighted" if kind == "weighted" else "below_other"] = [
                {"name": n[:80], "pct": x, **({"id": party_id(n)} if party_id(n) else {})} for n, x in extra]
            out.setdefault("notes", []).append(
                f"the {len(extra)} lists below the threshold are given "
                + ("as weighted shares only ('אחוז משוקלל')" if kind == "weighted" else "with no word of their kind")
                + ": kept apart, not in the raw shares; the share below the threshold is not known")
            extra = []
        for name, share in extra:
            pid = party_id(name)
            if pid in TRACKED:
                if pid in seats and pid != "Joint List":
                    dup.add(pid)
                else:                                      # Balad below the threshold beside Hadash-Ta'al's seats
                    pct[pid] = round(pct.get(pid, 0) + share, 2)
            below.append({"name": name[:80], "pct": share, **({"id": pid} if pid else {})})
        for pid in dup:                                    # one list on two rows: neither share is kept
            pct.pop(pid, None)
        out["seats"] = {k: v for k, v in seats.items() if v}
        out["pct"] = pct
        withp = [r for r in table if r["pct"] is not None]
        out["pct_total"] = round(sum(r["pct"] for r in withp) + sum(x for _, x in extra), 1)
        out["table_rows"] = len(table)
        out["seats_total"] = sum(r["seats"] or 0 for r in table)
        out["pct_complete"] = len(withp) >= 0.8 * len(table) and 95 <= out["pct_total"] <= 105
        # the share of the lists below the threshold: theirs where the filing names them; none named, nothing when
        # the shares do not add up to the whole (Next Data's table alone is 92%: the rest is not known) or the
        # lists below it are given in weighted shares only, else 0
        out["wasted_pct"] = (round(sum(b["pct"] for b in below), 1) if below else None
                             if "below_weighted" in out or "below_other" in out or not out["pct_complete"] else 0.0)
        if extra:
            out["below_table"] = len(extra)
        if below:
            out["below"] = below
        if dup or unknown:
            out.setdefault("notes", []).extend(
                [f"two rows map to {p}: its share is not kept" for p in sorted(dup)]
                + [f"a row with seats names no list known here: {u[:60]}" for u in unknown])
        after = lines[table[-1]["i"] + 1: table[-1]["i"] + 8]
        for k, line in enumerate(after) if "undecided_pct" not in out else []:
            if any(fold(u) in fold(line) for u in UNDECIDED):
                # one share on the line, or alone on the next ('לא החליטו' over '8.1%'); several (one per
                # sub-sample, Channel 13's) are not the undecided
                ps = [v for v in numbers(line) if 0 < v < 60]
                if not ps and k + 1 < len(after) and VALUE.fullmatch(clean(after[k + 1]).strip()):
                    ps = [v for v in numbers(after[k + 1]) if 0 < v < 60]
                if len(ps) == 1:
                    out["undecided_pct"] = ps[0]
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
        elif ("date" in lk or lk.endswith("_to_cec")) and local_date(s):
            # date_the_survey; transfer_to_cec, public_to_cec, update_to_cec: when it was sent, posted, updated
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
        notes.append(f"{fetch_label(fetched)['source']}: no listing.json ({exc.__class__.__name__})")
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
        put("below_weighted", ("cec_pdf", P.get("below_weighted")))
    elif src.get("pct") == "amitlev":
        put("wasted_pct", ("amitlev", A.get("wasted_pct")))
        put("below", ("amitlev", A.get("below")))
    elif src.get("pct") == "or523":
        put("pct_total", ("or523", O.get("pct_total")))   # its shares are of the lists with seats: under 100
    for key, akey in (("n", "n"), ("n_initial", None), ("invited", "invited"), ("response_rate", "response_rate"),
                      ("refused_pct", "refused_pct"), ("moe", "moe"), ("undecided_pct", "undecided_pct"),
                      ("sampling", "sampling"), ("population", "population"), ("mode", "mode"), ("method", "method"),
                      ("commissioner", None)):
        if key in ("invited", "response_rate") and (P or {}).get("subsamples"):
            akey = None             # the PDF read here has none of the whole: a third party's is one sub-sample's
        put(key, ("cec_pdf", (P or {}).get(key)), ("amitlev", A.get(akey) if akey else None),
            ("isaranga", S.get("n") if key == "n" else None))
    if out.get("moe") and out.get("n") and out["moe"] < moe_floor(out["n"]):
        out.pop("moe")
        src.pop("moe")
    out["house"] = house_of(out.get("editor") or "", out.get("media") or "")
    out["national"] = (I.get("national") if I.get("national") is not None else bool(out.get("seats")))
    if L:
        out["listing"] = L
    out["notes"] = list(P.get("notes") or []) if P else []
    if P and P.get("sector"):
        out["sector"] = P["sector"]
    out["src"] = src
    # read: the PDF gave a value here, not merely some text (a scanned page, a garbled font or text in visual order
    # parses to next to nothing); verified: no doubts, the concrete fields read and checked against each other
    out["read"] = any(v == "cec_pdf" for v in src.values())
    out["pdf_house"] = house_of(P.get("pollster") or "") if P else None
    out["doubts"] = doubts(P, out, T)
    n, n0 = (P or {}).get("n"), (P or {}).get("n_initial")
    if n and n0 and n0 < n <= n0 * (1 + OVERSHOOT):
        out["notes"].append(f"respondents {n}, {round(100 * (n - n0) / n0, 1)}% over the initial sample {n0}: a "
                            f"panel's overshoot of its planned sample, accepted (up to {round(100 * OVERSHOOT)}%)")
    if not out["notes"]:
        del out["notes"]
    return out


# A filing's respondents may exceed its initial sample: the initial sample is the size planned, and an internet
# panel's answers come in after the quota is met (Midgam 509 of 500, Direct Polls 1,054 of 1,000). Up to 10% over
# it is that and does not hold verification back; more is a misreading or a filing to look at. More respondents
# than people asked to take part is always a doubt.
OVERSHOOT = 0.10
THIRD_N = "respondents {n} here, {other} by {name}"


def doubts(P, f, third):
    """Why a filing's PDF does not verify it, [] when it does: the PDF itself must give the pollster (a house known
    here, the listing's), the fieldwork dates (within two weeks), the respondents (no more than were asked, at most
    10% over the initial sample, as the third parties read them) and a seat table of 120."""
    if not f["read"]:
        return ["the PDF was not read here" if not P else "nothing was read from the PDF's text"]
    why = [f"no {what} in the PDF" for k, what in (("seats", "seat table of 120"), ("n", "respondents"),
                                                   ("fieldwork_end", "fieldwork dates")) if f["src"].get(k) != "cec_pdf"]
    if not f["pdf_house"]:
        why.append("the PDF names no polling house known here" + (f" ({P['pollster'][:40]})" if P.get("pollster") else ""))
    elif f.get("house") and f["house"] != f["pdf_house"]:
        why.append(f"the PDF's pollster ({f['pdf_house']}) is not the listing's ({f['house']})")
    if P.get("sector"):
        why.append(f"a poll of one group ('{P['sector']}'): its seat table, if any, is not the electorate's")
    if P.get("fieldwork_typo"):
        why.append(f"the PDF's fieldwork dates ({P['fieldwork_start']} to {P['fieldwork_end']}) span over two weeks: "
                   "one of them likely a typo")
    n = P.get("n")
    if n and P.get("invited") and n > P["invited"]:
        why.append(f"more respondents ({n}) than people asked to take part ({P['invited']})")
    if n and P.get("n_initial") and n > P["n_initial"] * (1 + OVERSHOOT):
        why.append(f"respondents ({n}) more than {round(100 * OVERSHOOT)}% over the initial sample ({P['n_initial']})")
    for name in ("amitlev", "isaranga"):
        other = (third.get(name) or {}).get("n")
        if n and other and other != n:
            why.append(THIRD_N.format(n=n, other=other, name=name))
    return why


HOUSE_IDS = {h for _, h in HOUSES}


def poll_doubts(p, f, seats_equal):
    """Why a filing read here is not verified as this poll's, [] when it is: its seats, its house and its dates."""
    why = [] if seats_equal is True else ["the filing's seat table is not the poll's"]
    if f.get("pdf_house") and f["pdf_house"] != p.get("house"):
        why.append(f"the PDF's pollster ({f['pdf_house']}) is not the poll's ({p.get('house')}"
                   + (", a house no filing names" if p.get("house") not in HOUSE_IDS else "") + ")")
    end = f.get("fieldwork_end") if f["src"].get("fieldwork_end") == "cec_pdf" else None
    if end and not -1 <= days(p["date"], end) <= 10:
        why.append(f"fieldwork ended {end}, the poll is of {p['date']}")
    return why


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


# ------------------------------------------------------------------ conflicts and the filings left over
def filed(f):
    """When a filing reached the CEC (the listing's transfer date), for the order of two filings of one poll."""
    lst = f.get("listing") or {}
    return (lst.get("date_transfer_to_cec") or lst.get("date_public_to_cec") or f.get("published") or "9999",
            item_no(f["item"]))


def pdf_seats(f):
    return nonzero(f.get("seats")) if f["src"].get("seats") == "cec_pdf" else {}


def same_poll(a, b):
    """Two filings of one poll: other items, the same house, fieldwork and respondents, and the same seat table
    read in both PDFs (or in neither)."""
    return (a["item"] != b["item"] and bool(a.get("house")) and a.get("house") == b.get("house")
            and bool(a.get("fieldwork_end") and a.get("n"))
            and all(a.get(k) == b.get(k) for k in ("fieldwork_start", "fieldwork_end", "n"))
            and pdf_seats(a) == pdf_seats(b))


def describe(f):
    return (f"{f['item']} ({f.get('editor') or '?'} for {f.get('media') or '?'}, fieldwork "
            f"{f.get('fieldwork_start')}..{f.get('fieldwork_end')}, n {f.get('n')})")


def close(a, b):
    """Two readings of the same raw shares (five lists or more, each within 0.15)."""
    common = [k for k in (a or {}) if k in (b or {})]
    return len(common) >= 5 and all(abs(a[k] - b[k]) <= 0.15 for k in common)


VERDICTS = ("matched", "link", "both", "unclear")


def conflict(p, linked, m):
    """(verdict, note) for a poll whose polls_2026.json link is not the filing matched to it, from what the two
    PDFs say: "matched" (the matched filing is the poll's: its seat table is the poll's, or the nearer one and of
    the poll's house, the seats that differ named; the link's is another poll's), "link" (the other way round),
    "both" (one poll filed twice: either is right) or "unclear". The note names what of the poll in polls_2026.json
    came from the linked filing (its n, its shares)."""
    def moved(f):
        s = pdf_seats(f) if f else {}
        return sum(abs(x - y) for x, y in seat_diff(p["seats"], s).values()) if s else None

    def diff(f):
        return ", ".join(f"{k} {a} here, {b} filed" for k, (a, b) in seat_diff(p["seats"], pdf_seats(f)).items())
    if linked is None:
        return "unclear", "the link is to no filing known here"
    if m is not None and same_poll(linked, m):
        a, b = sorted([linked, m], key=filed)
        return "both", (f"one poll filed twice: {b['item']} (sent {filed(b)[0]}) repeats {a['item']} (sent "
                        f"{filed(a)[0]}): the same pollster, fieldwork, respondents and seats; either link is right")
    taken = []
    if p.get("n") and linked.get("n") == p["n"] and (m is None or m.get("n") != p["n"]):
        taken.append(f"n ({p['n']})")
    if close(p.get("pct"), linked.get("pct")) and (m is None or not close(p.get("pct"), m.get("pct"))):
        taken.append("raw shares")
    also = (f"; polls_2026.json's {' and '.join(taken)} {'are' if len(taken) > 1 else 'is'} the linked filing's, "
            "not this poll's" if taken else "")
    ml, mm = moved(linked), moved(m)
    other = f"the linked one, {describe(linked)}, is another poll's" + (f" ({ml} seats differ)" if ml else
                                                                         " (its seat table not read)")
    if mm == 0 and ml != 0:
        return "matched", f"the matched filing {describe(m)} has the poll's seat table; {other}{also}"
    if mm and (ml is None or mm < ml) and m.get("house") == p.get("house") != linked.get("house"):
        return "matched", (f"the matched filing {describe(m)}, of the poll's house, is the poll's: its seat table "
                           f"the nearest ({diff(m)}); {other}{also}")
    if ml == 0 and mm != 0:
        return "link", (f"the linked filing {describe(linked)} has the poll's seat table"
                        + (f"; the matched {describe(m)} has not" if m else ""))
    return "unclear", (f"neither filing's seat table is the poll's: linked {describe(linked)}"
                       + (f", matched {describe(m)}" if m else ", none matched") + also)


CLASSES = ("sector", "refiling", "duplicate", "before_polls", "no_seat_table", "not_in_polls", "unread")


def classify(f, filings, polls, first, matched=()):
    """(class, why, nearest poll) of a filing no poll in polls_2026.json was matched to, the first that holds of:
      sector         a poll of one group (its population or title: reservists, the Arab public, an age range...);
      refiling       the same poll as an item filed before it (same house, fieldwork, respondents and seats);
      duplicate      the same poll as an item filed after it and matched to a poll (that one taken);
      before_polls   fieldwork ended before polls_2026.json's first poll (its table starts later);
      no_seat_table  read, but no national seat table of 120 in it (questions only, or a layout not read here);
      not_in_polls   a national seat table of 120 read, in the table's time, and no poll of polls_2026.json has it
                     (the nearest poll of its house within three days named, with how many seats differ);
      unread         its PDF not read here."""
    if f.get("sector"):
        return "sector", f"a poll of one group: '{f['sector']}'", None
    twins = sorted((g for g in filings.values() if same_poll(f, g)
                    and (filed(g) <= filed(f) or g["item"] in matched)), key=filed)
    if twins:
        g = twins[0]
        cls = "refiling" if filed(g) <= filed(f) else "duplicate"
        return cls, (f"the poll of {g['item']} (sent {filed(g)[0]}) sent again on {filed(f)[0]}" if cls == "refiling"
                     else f"the poll of {g['item']}, which polls_2026.json has, sent again on {filed(g)[0]}"), None
    end = f.get("fieldwork_end") or (f.get("listing") or {}).get("survey_date")
    if not f["read"]:
        return "unread", "its PDF was not read here", None
    if first and end and days(first, end) > 1:
        return "before_polls", f"fieldwork ended {end}, before polls_2026.json's first poll ({first})", None
    if f["src"].get("seats") != "cec_pdf":
        return "no_seat_table", "no national seat table of 120 read in its PDF", None
    near = []
    for p in polls:
        if f.get("house") and p.get("house") == f["house"] and end and -1 <= days(p["date"], end) <= 3:
            moved = sum(abs(x - y) for x, y in seat_diff(p["seats"], f["seats"]).values())
            near.append((abs(days(p["date"], end)), moved, f"{p['date']}|{p['pollster']}|{p.get('outlet', '')}"))
    if near:
        d, moved, key = min(near)
        return "not_in_polls", (f"a national seat table of 120 not in polls_2026.json; its house's poll {key} is "
                                f"{d} day(s) after the fieldwork, {moved} seats differ"), key
    return "not_in_polls", "a national seat table of 120, no poll of its house in polls_2026.json then", None


STAMP_DIR = re.compile(r"latest|\d{8}-\d{4}")                       # fetch.yml's directories: latest/, YYYYMMDD-HHMM/
FETCHER_NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")
STARTED = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?")


def fetch_label(d):
    """A fetch directory as the ops-reports branch names it, not where it lies here: {"source":
    "ops-reports:reports/fetch/<fetcher>/<its directory>", "started" (summary.json's: the run's own stamp
    directory holds the same files), "listing_sha256", "filings_sha256"}; the same fetch, the same record. Only
    what has the shape fetch.yml gives is taken from the fetch: the fetcher's name in summary.json (else
    poll_filings, the only fetch this reads), a directory named latest or YYYYMMDD-HHMM (else none: the SHA-256s
    say which fetch it was), a start time as an ISO timestamp (else none); never a local path."""
    try:
        s = json.load(open(os.path.join(d, "summary.json"), encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    s = s if isinstance(s, dict) else {}
    what = s.get("fetcher") if isinstance(s.get("fetcher"), str) and FETCHER_NAME.fullmatch(s["fetcher"]) \
        else "poll_filings"
    name = os.path.basename(os.path.abspath(d))
    started = s.get("started") if isinstance(s.get("started"), str) and STARTED.fullmatch(s["started"]) else None
    out = {"source": f"ops-reports:reports/fetch/{what}" + (f"/{name}" if STAMP_DIR.fullmatch(name) else ""),
           "started": started}
    for name in ("listing", "filings"):
        path = os.path.join(d, name + ".json")
        out[name + "_sha256"] = sha256(path) if os.path.isfile(path) else None
    return out


# ------------------------------------------------------------------ the output
FIELDS = ("n", "n_initial", "invited", "response_rate", "refused_pct", "moe", "pct", "pct_total", "below",
          "below_weighted", "wasted_pct", "undecided_pct", "sampling", "population", "mode", "method", "commissioner")


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
            for k in ("pct", "pct_total", "below", "below_weighted", "wasted_pct"):
                row.pop(k, None)
            row.setdefault("notes", []).append("the filing's seat table is not the poll's (or was not read): its "
                                               "shares are not attached")
        if f.get("listing"):
            row["filing"]["listing"] = f["listing"]
        row["src"] = {k: v for k, v in f["src"].items()
                      if k in row or k in ("fieldwork_start", "fieldwork_end", "seats") or k in row["filing"]}
        # the PDF itself read here, its pollster, dates, respondents and seats this poll's
        why = f["doubts"] + (poll_doubts(p, f, row["seats_equal"]) if f["read"] else [])
        fn = f.get("n") if f["src"].get("n") == "cec_pdf" else None
        if fn and p.get("n") == fn:
            # the PDF and polls_2026.json agree on the respondents: a third party's other count is its own misreading
            pre = THIRD_N.split("{other}")[0].format(n=fn)
            for w in [w for w in why if w.startswith(pre)]:
                why.remove(w)
                row.setdefault("notes", []).append(f"{w[len(pre):]}: not kept, the PDF and polls_2026.json say {fn}")
        elif fn and p.get("n"):
            # not a doubt of the filing: polls_2026.json's n may be another filing's (conflicts) or a typo there
            row["polls_n"] = p["n"]
            row.setdefault("notes", []).append(f"polls_2026.json's n ({p['n']}) is not the filing's ({fn})")
        row["verified"] = not why
        if f["read"] and why:
            row.setdefault("notes", []).append("not verified: " + "; ".join(why))
        prev = canon(p.get("filing") or "")
        if prev and prev[2] != f["url"] and prev[2] not in f["also"]:
            row["previous_link"] = prev[2]
        if f.get("notes"):
            row.setdefault("notes", []).extend(f["notes"])
        rows.append(row)
    matched_polls = {i for i, _, _ in pairs}
    by_url = {}
    for f in filings.values():
        for u in [f["url"]] + f["also"]:
            by_url.setdefault(u, f["item"])
    conflicts = []
    row_of = {i: rows[k] for k, (i, _, _) in enumerate(pairs)}
    for i, p in enumerate(polls):
        c = canon(p.get("filing") or "")
        r = row_of.get(i)
        if not c or (r and not r.get("previous_link")):
            continue
        linked, m = filings.get(by_url.get(c[2])), filings[r["filing"]["item"]] if r else None
        verdict, note = conflict(p, linked, m)
        conflicts.append({"key": f"{p['date']}|{p['pollster']}|{p.get('outlet', '')}", "polls_2026_link": c[2],
                          "matched": m["url"] if m else None, "match": r["match"] if r else None,
                          "verdict": verdict, "note": note})
    first = min((p["date"] for p in polls), default=None)
    unmatched_filings = []
    for item in sorted(filings, key=item_no):
        f = filings[item]
        if item in matched_items:
            continue
        cls, why_not, near = classify(f, filings, polls, first, matched_items)
        unmatched_filings.append({k: f.get(k) for k in ("item", "number", "editor", "media", "house", "fieldwork_end",
                                                        "url") if f.get(k) is not None}
                                 | {"national": bool(f.get("national") and f.get("seats")), "class": cls,
                                    "why": why_not} | ({"nearest_poll": near} if near else {}))
    inputs = {"polls": rel(polls_path), "polls_sha256": sha256(polls_path), "reference": rel(ref_path),
              "reference_sha256": sha256(ref_path) if os.path.exists(ref_path) else None,
              "lists": rel(LISTS), "lists_sha256": sha256(LISTS) if os.path.exists(LISTS) else None,  # party_id's names
              "fetched": [fetch_label(d) for d in fetched]}
    doc = {
        "about": "קובצי הדיווח על סקרי הבחירות שהוגשו לוועדת הבחירות המרכזית, מוצמדים לסקרים שבטבלת הסקרים: מספר "
                 "המשיבים, טעות הדגימה, מועדי איסוף הנתונים והאחוזים הגולמיים של כל רשימה. המנדטים והממוצע אינם "
                 "משתנים; שדה src אומר מאין נקרא כל ערך. verified: true רק כשהקובץ עצמו נקרא כאן ונמצאו בו עורך "
                 "הסקר, מועדי איסוף הנתונים (בטווח של עד שבועיים), מספר המשיבים וטבלת מנדטים של 120: טבלת המנדטים "
                 "היא של הסקר, עורך הסקר הוא של הסקר ושל הרישום, האיסוף הסתיים עד 10 ימים לפני הפרסום, ומספר המשיבים "
                 "תואם לקריאות האחרות, אינו עולה על מספר המתבקשים ואינו עולה ביותר מ-10% על גודל המדגם ההתחלתי "
                 "(פאנל שעבר את המכסה שתוכננה). מספר המשיבים שבטבלת הסקרים אינו תנאי: כשהוא שונה משל הקובץ, polls_n "
                 "ו-notes אומרים זאת. below: הרשימות שמתחת לאחוז החסימה באחוזים גולמיים; below_weighted: כשהקובץ "
                 "נותן אותן באחוז משוקלל בלבד, ואז wasted_pct חסר. conflicts: סקר שהקישור שלו בטבלת הסקרים אינו הקובץ "
                 "שהותאם לו, ו-verdict אומר לפי שני הקבצים איזה מהם שלו; unmatched_filings: קבצים שאין להם סקר "
                 "בטבלה, ו-class אומר למה",
        "source": "ועדת הבחירות המרכזית, מאגר הסקרים לכנסת ה-26 ב-gov.il (" + COLLECTOR + "); עד לקריאת הקבצים מכאן: "
                  "קריאות של צד שלישי (" + ", ".join(sorted(THIRD_PARTY)) + ") כמפורט ב-"
                  "pipeline/reference/poll_filings_index.json",
        "collector": COLLECTOR, "inputs": inputs,
        "counts": {"polls": len(polls), "matched": len(rows),
                   "by_match": {h: sum(1 for r in rows if r["match"] == h) for h in ("seats", "house+date", "source link")},
                   "with_pct": sum(1 for r in rows if r.get("pct")), "with_n": sum(1 for r in rows if r.get("n")),
                   "with_moe": sum(1 for r in rows if r.get("moe")), "verified": sum(1 for r in rows if r["verified"]),
                   "verified_polls_n_differs": sum(1 for r in rows if r["verified"] and "polls_n" in r),
                   "filings": len(filings), "filings_read": sum(1 for f in filings.values() if f["read"]),
                   "filings_verified": sum(1 for f in filings.values() if not f["doubts"]),
                   "conflicts": {v: sum(1 for c in conflicts if c["verdict"] == v) for v in VERDICTS},
                   "unmatched_filings": {c: sum(1 for u in unmatched_filings if u["class"] == c) for c in CLASSES}},
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
    """A path as the repository names it; one outside it by its name alone (its SHA-256 beside it says which), never
    where it lies on this machine."""
    a = os.path.abspath(p)
    return os.path.relpath(a, ROOT) if a.startswith(ROOT + os.sep) else os.path.basename(a)


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


# ------------------------------------------------------------------ self-test
# each pattern of HOUSES by a name as the filings write it (the editors in the reference index and the listing;
# the PDFs' own 'עורך הסקר' cell, as pdftotext -layout gives it, for the Latin ones)
HOUSE_NAMES = {"רוזנר": "שמואל רוזנר", "פרויקט": "מדגם פרויקט", "סטטנט": 'סטטנט בע"מ', "קנטאר": "קנטאר ישראל",
               "קאנטר": "קאנטר ישראל ,אריאל שרון 4גבעתיים", "kantar": "Kantar Israel",
               "דיירקט": 'דיירקט פולס בע"מ בראשות צוריאל שרון', "direct polls": "Direct Polls Ltd",
               "נקסט דאטה": "נקסט דאטה - שלמה פילבר", "next data": "חברת  ,Next Dataהמנופים  ,1הרצליה",
               "פילבר": "שלמה פילבר", "לזר": 'לזר מחקרים בראשות ד"ר מנחם לזר', "מאגר מוחות": 'מאגר מוחות בע"מ',
               "טאטיקה": "טאטיקה מחקרים ומדיה", "טטיקה": "יוסי טטיקה", "מדגם": 'מדגם יעוץ ומחקר בראשות מנו גבע',
               "דיאלוג": 'דיאלוג – יעוץ ארגוני ,מחקר והדרכה בע"מ', "אקורד": "מרכז אקורד ,חוצות שפיים",
               "די אר איי": "מכון די אר איי", "dri": "מכון  ,DRIבוסתנאי  ,43רמת השרון",
               "אפקאר": "אפקאר מחקר וידע בראשות ד\"ר הישאם ג'ובראן"}


def selftest():
    """--selftest: the polling houses, the list names (against lists_2026.json) and the verified flag, on
    constructed text; no network, nothing written. Exit 0 when all pass."""
    failures = []

    def check(cond, what):
        print(("  ok   " if cond else "  FAIL ") + what)
        if not cond:
            failures.append(what)

    print("houses")
    wrong = {}
    for pat, h in HOUSES:
        name = HOUSE_NAMES.get(pat, "")
        if house_of(name) != h or not _house_re(pat).search(fold(name).lower()):
            wrong[pat] = house_of(name)
    check(not wrong, f"each of the {len(HOUSES)} patterns of HOUSES, by a name as the filings write it: {wrong or 'all'}")
    check(house_of("מדגם יעוץ ומחקר") == "midgam", "Midgam: 'מדגם' folded (final mem) in the pattern as in the text")
    check(house_of("במדגם ארצי ומייצג", "סקר עצמאי") is None, "a word holding a house's name ('במדגם') is not the house")
    check(house_of("ADRIATIC") is None and house_of("מכון DRI") == "dri",
          "a Latin name bounded by Latin letters only: 'DRI' glued to Hebrew is DRI, inside 'ADRIATIC' it is not")

    print("lists")
    try:
        lists = json.load(open(LISTS, encoding="utf-8"))["lists"]
    except (OSError, ValueError, KeyError):
        lists = []
    wrong = {n: party_id(n) for l in lists for n in [l.get("official_name")] + (l.get("aliases") or [])
             if isinstance(n, str) and party_id(n) != l.get("id")}
    check(len(lists) >= 30 and bool(_BALLOT) and not wrong,
          f"the {len(lists)} lists on the ballot (lists_2026.json), by official name and alias: {wrong or 'all'}")
    labels = {"מפלגת ביחד נצליח – רשימה משותפת ערבית יהודית בראשות אבי שקד": None, "מפלגת ביחד נצליח": None,
              "ביחד נצליח"[::-1]: None, "ביחד בראשות אבי שקד": None, "ביחדנו": None, "ביחד": "Together",
              "ביחד בראשות נפתלי בנט ויאיר לפיד": "Together", "יחד בראשות נפתלי בנט": "Together",
              "הליכוד ושרשר לאהבה ואחדות העם": "Likud", "תקומה בראשות בצלאל סמוטריץ'": "Religious Zionism",
              "הציונות הדתית וזהות": "Religious Zionism", 'מפלגות אחרות עד 1% כ"א': None, "דוכילה": "Likud"}
    wrong = {k: party_id(k) for k, v in labels.items() if party_id(k) != v}
    check(not wrong, "Together by its own words only: not in בד's 'ביחד נצליח' (also in visual order) or under its "
          f"leader; a tracked list named beside an untracked one is still found: {wrong or 'all'}")

    print("verified")
    table = [("הליכוד בראשות בנימין נתניהו", "30", "24.1%"), ("ישר! בראשות גדי איזנקוט", "25", "20.2%"),
             ("ביחד בראשות נפתלי בנט", "20", "16.0%"), ("הדמוקרטים בראשות יאיר גולן", "15", "12.1%"),
             ("ישראל ביתנו", "15", "12.0%"), ('ש"ס', "15", "11.9%"), ("מפלגת ביחד נצליח בראשות אבי שקד", "", "0.9%"),
             ('סה"כ', "120", "97.2%")]
    fields = [("מועד איסוף הנתונים", "11-12/10/2026"), ("מספר המתבקשים להשתתף בסקר", "2,521"),
              ("מספר המשיבים לסקר בפועל", "509"), ("טעות הדגימה המרבית", "±4.4%")]
    poll = {"date": "2026-10-13", "house": "midgam", "seats": {"Likud": 30, "Yashar": 25, "Together": 20,
                                                              "The Democrats": 15, "Yisrael Beiteinu": 15, "Shas": 15}}

    def filing(pollster='מדגם יעוץ ומחקר בע"מ', with_fields=True, third=None, text=None):
        lines = [f"{v:>30}      {k}" for k, v in [("עורך הסקר", pollster)] + fields] if with_fields else []
        lines += [f"{p:>10}    {s:>4}    {name}" for name, s, p in table]
        rec = new_rec("knesset_election1")
        rec["listing"], rec["third"] = {"editor": "מדגם יעוץ ומחקר"}, third or {}
        P = parse_filing("\n".join(lines) if text is None else text(lines))
        rec["texts"] = [dict(P, url=BLOB.format(item="knesset_election1", file="Survey_4001.pdf"))]
        return merged(rec), P

    def verified(f, p=poll):
        return not (f["doubts"] + poll_doubts(p, f, not seat_diff(p["seats"], f.get("seats"))))
    f, P = filing()
    check(f["read"] and not f["doubts"] and verified(f),
          f"pollster, dates, respondents and seats read and agreeing: verified ({f['doubts']})")
    check(P.get("pct", {}).get("Together") == 16.0 and not any(b.get("id") for b in P.get("below", [])),
          "בד's row in the table is a list below the threshold, not Together's share")
    f, _ = filing(text=lambda lines: "")
    check(not f["read"] and not verified(f), f"a PDF with no text (a scanned page): not verified ({f['doubts']})")
    f, _ = filing(text=lambda lines: "\n".join(l[::-1] for l in lines))
    check(not verified(f), f"text in visual order (each line reversed): not verified ({f['doubts'][:2]})")
    f, _ = filing(with_fields=False)
    check(f["read"] and not verified(f), f"the seat table alone: read, not verified ({f['doubts']})")
    f, _ = filing(pollster="קנטאר ישראל")
    check(not verified(f), f"the PDF's pollster not the listing's: not verified ({f['doubts']})")
    f, _ = filing(third={"amitlev": {"n": 609}})
    check(not verified(f), f"respondents a third party read otherwise: not verified ({f['doubts']})")
    f, _ = filing()
    others = [dict(poll, seats=dict(poll["seats"], Likud=29, Yashar=26)), dict(poll, house="kantar"),
              dict(poll, date="2026-10-30")]
    check(not any(verified(f, p) for p in others),
          "a poll with other seats, of another house or long after the fieldwork: not verified as that poll's")
    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


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
    ap.add_argument("--selftest", action="store_true", help="test the houses, the list names and the verified flag")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.reference:
        if not (a.or523 and a.amitlev):
            ap.error("--reference needs --or523 and --amitlev")
        doc = reference(a.or523, a.amitlev, a.isaranga, a.ref, a.seen)
        print(f"{len(doc['filings'])} filings in {rel(a.ref)}")
        return 0
    doc = build(a.polls, a.ref, a.fetched, a.out)
    c = doc["counts"]
    print(f"{c['matched']}/{c['polls']} polls matched to a filing ({c['by_match']}); shares {c['with_pct']}, n {c['with_n']}, "
          f"sampling error {c['with_moe']}; verified here: {c['verified']}; conflicts with polls_2026.json links: "
          f"{len(doc['conflicts'])} ({c['conflicts']}); filings {c['filings']}, read {c['filings_read']}, verified "
          f"{c['filings_verified']}, unmatched {len(doc['unmatched_filings'])} ({c['unmatched_filings']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
