#!/usr/bin/env python3
"""Tests of the CEC poll filings: pipeline/fetchers/poll_filings.py and pipeline/build_poll_filings.py.

    python3 pipeline/test_filings.py

Self-contained (no network): a temporary folder, a local stand-in for gov.il and raw.githubusercontent.com.
  1. reading a filing's text: the pdftotext -layout rendering of an RTL filing (value cells left of their labels,
     the bidi marks pdftotext writes), a narrative template, a trend table that must be refused, list labels as
     pollsters type them, dates (ranges, two-digit years, gov.il's UTC midnights);
  1b. excerpts of the real filings fetched on 16.10.2026, a few lines each and four seat tables whole: Hebrew month
     names, a range's day moved by the layout, Direct Polls' table with no total and a share written twice, Maagar
     Mochot's weeks side by side, Tatika's running text and its seats beside a count of respondents, Channel 13's
     July table that must be refused, labels alone on their line (and a footnote that only starts with one),
     Channel 13's sub-samples, a text value cut in two, Next Data's labels wrapped over lines and its lists below
     the threshold in a table of their own (raw or weighted), a count glued to a bracket, the houses' Latin names
     and in running text, sector polls;
  2. the same filing as a PDF whose glyphs stand in visual order (as an RTL PDF stores them), read with pdftotext
     (skipped when this machine has none);
  3. the builder: polls matched by their seats, by house and date, and by the link they carry; a filing read here
     wins over the third parties and is marked verified; shares never attached to a table that is not the poll's;
     polls_2026.json byte for byte unchanged and no seat in the output; a fetch's paths that leave it ignored;
     the same input, the same output, the fetch named as ops-reports names it (no local path, whatever its
     directory or summary.json say); the rules on the real cases: respondents over the initial sample (up to
     10%), fieldwork dates with a typo, the five conflicts with polls_2026.json's links, the classes of the
     filings no poll has;
  4. the fetcher against the stand-in: the template id from the collector page, the listing paged, PDFs saved,
     a 404 and a challenge page recorded, addresses from third parties taken only in the filing form, a listing
     that is refused falling back on the indexes and a bounded probe; summary.json and summary.md written.

The fixtures of 1, 2 and 3 are constructed (those of 1b are not). Their format: the field labels the three templates read by
amitlev/israel-polls-2026 use (.github/scripts/lib/govil-pdf-parser.mjs, LABEL_ALIASES and ALL_LABELS), the main
table as its README quotes Kantar's filing of 9.9.2026 ("תחזית המנדטים / מנדטים / אחוזים (נתונים גולמיים)", rows
"<list> בראשות <leader>  <seats>  <share>%", lists below the threshold with a share only, a "סה"כ" row); the values
of the Midgam fixture are those amitlev's parser read from filing 4202 (knesset_election106, Survey_4202.pdf: n 509,
invited 2,521, response rate 20%, sampling error 4.4, the method texts, the shares); its undecided line and the
other fixtures' numbers are invented.
"""
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import build_poll_filings as B  # noqa: E402

FETCHER = os.path.join(ROOT, "pipeline", "fetchers", "poll_filings.py")
failures = []


def check(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        failures.append(what)


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(obj, bytes) else "w"
    with open(path, mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as f:
        f.write(obj if isinstance(obj, (str, bytes)) else json.dumps(obj, ensure_ascii=False))
    return path


# ---------------------------------------------------------------- fixtures
# (right edge of the label column, label, [(right edge, value)...]) as an RTL table: the label at the right, each
# value cell further left. Rendered as pdftotext -layout writes it (layout_text) and as a PDF (make_pdf).
MIDGAM = {
    "head": ["ממצאי סקר חדשות12 בנושא: מנדטים ואקטואליה"],
    "fields": [("מזמין הסקר", 'חברת החדשות הישראלית בע"מ'), ("עורך הסקר", 'מדגם יעוץ ומחקר בע"מ'),
               ("מועד איסוף הנתונים", "12/10/2026"), ("שיטת הדגימה", "דגימת שכבות ובתוך השכבות דגימה אקראית"),
               ("סוגי האוכלוסייה שנדגמו", "מדגם ארצי ומייצג של בעלי זכות בחירה - כלל האוכלוסייה בישראל מגיל 18 ומעלה"),
               ("מספר המתבקשים להשתתף בסקר", "2,521"), ("מספר המשיבים לסקר בפועל", "509"),
               ("אחוז המשתתפים בסקר", "20%"), ("אחוז האנשים שסרבו להשתתף", "80%"),
               ("טעות הדגימה המרבית", "±4.4%"), ("שיטה סטטיסטית", "הסקר בוצע בשיטות סטטיסטיות מקובלות"),
               ("אופן ביצוע הסקר", "טלפוני + אינטרנטי")],
    "question": "שאלה: אם הבחירות לכנסת היו מתקיימות היום, לאיזו מפלגה היית מצביע?",
    "header": ("תחזית המנדטים", "מנדטים", "אחוזים (נתונים גולמיים)"),
    "rows": [("ישר! בראשות גדי איזנקוט", "23", "18.2%"), ("הליכוד בראשות בנימין נתניהו", "20", "16.1%"),
             ("ביחד בראשות נפתלי בנט ויאיר לפיד", "13", "10.4%"), ("הדמוקרטים בראשות יאיר גולן", "9", "7.3%"),
             ("ישראל ביתנו בראשות אביגדור ליברמן", "9", "7.2%"), ("עוצמה יהודית בראשות איתמר בן גביר", "8", "6.4%"),
             ('ש"ס בראשות אריה דרעי', "8", "6.3%"), ('הרשימה המשותפת חד"ש-תע"ל ובל"ד', "8", "6.2%"),
             ("יהדות התורה", "7", "5.6%"), ("הציונות הדתית בראשות בצלאל סמוטריץ'", "6", "4.8%"),
             ('רע"ם בראשות מנסור עבאס', "5", "4.1%"), ("המילואימניקים בראשות יועז הנדל", "4", "3.4%"),
             ("עמך ישראל בראשות עופר וינטר", "", "1.8%"), ('מפלגות אחרות עד 1% כ"א', "", "2.2%"),
             ('סה"כ (מנדטים)', "120", "100%")],
    "after": ["לא החליטו: 14%"],
}
MIDGAM_SEATS = {"Yashar": 23, "Likud": 20, "Together": 13, "The Democrats": 9, "Yisrael Beiteinu": 9, "Otzma Yehudit": 8,
                "Shas": 8, "Joint List": 8, "UTJ": 7, "Religious Zionism": 6, "Ra'am": 5, "Reservists": 4}
MIDGAM_PCT = {"Yashar": 18.2, "Likud": 16.1, "Together": 10.4, "The Democrats": 7.3, "Yisrael Beiteinu": 7.2,
              "Otzma Yehudit": 6.4, "Shas": 6.3, "Joint List": 6.2, "UTJ": 5.6, "Religious Zionism": 4.8, "Ra'am": 4.1,
              "Reservists": 3.4, "Amcha Yisrael": 1.8}
RLE, LRE, PDF = "\u202b", "\u202a", "\u202c"


def layout_text(doc, marks=True):
    """The fixture as pdftotext -layout writes an RTL page: each line's cells left to right (values first), runs
    wrapped in the embedding marks it adds (RLE ... PDF; numbers LRE ... PDF inside)."""
    def m(s):
        if not marks:
            return s
        s = re.sub(r"([\d][\d,./%±]*)", lambda x: LRE + x.group(1) + PDF, s)
        return RLE + s + PDF
    L = [" " * 40 + m(h) for h in doc["head"]]
    for label, value in doc["fields"]:
        L.append(m(value).rjust(70) + " " * 6 + m(label))
    L += ["", " " * 20 + m(doc["question"]), ""]
    h = doc["header"]
    L.append(" " * 20 + m(h[2]) + " " * 5 + m(h[1]) + " " * 17 + m(h[0]))
    for name, seats, pct in doc["rows"]:
        L.append(" " * 30 + m(pct).rjust(8) + " " * 10 + (m(seats) if seats else "").rjust(5) + " " * 10 + m(name))
    L += [""] + [" " * 50 + m(a) for a in doc["after"]]
    return "\n".join(L) + "\n"


NARRATIVE = """\
סקר מאגר מוחות עבור ערוץ 16
הסקר נערך בתאריכים 28-29.9.26 בקרב 550 משיבים, מדגם מייצג של האוכלוסייה הבוגרת בישראל.
טעות הדגימה המרבית: 4.2% ברמת ביטחון של 95%.
הליכוד בראשות בנימין נתניהו 24 19.6%
ישר! בראשות גדי איזנקוט 21 17.2%
ביחד בראשות נפתלי בנט 12 10.0%
הדמוקרטים 9 7.6%
ישראל ביתנו 8 6.6%
ש"ס 9 7.4%
יהדות התורה 7 6.0%
עוצמה יהודית 8 6.5%
הציונות הדתית 5 4.2%
הרשימה המשותפת 8 6.4%
רע"מ בראשות מנסור עבאס 5 4.1%
עמך ישראל 4 3.4%
כחול לבן בראשות בני גנץ 1.1%
לא החליטו 12%
סה"כ 120 100%
"""
TREND = """\
                 שבוע 1    שבוע 2    שבוע 3    שבוע 4                  תחזית המנדטים
                   24        25        23        24             הליכוד בראשות בנימין נתניהו
                   21        20        22        21                 ישר! בראשות גדי איזנקוט
                   12        12        13        12                                 ביחד
                    9         9         8         9                            הדמוקרטים
                    8         8         9         8                          ישראל ביתנו
                   46        46        45        46                               אחרות
                  120       120       120       120                                  סה"כ
"""


def visual(s):
    """An RTL line's characters in visual order (left to right), as an RTL PDF places its glyphs: runs of digits
    and Latin keep their order, the rest is reversed, and the runs go right to left."""
    if not re.search("[א-ת]", s):
        return s
    runs, pos = [], 0
    for mt in re.finditer(r"[0-9A-Za-z%.,/±+]+(?:[ ]?[0-9A-Za-z%.,/±+]+)*", s):
        if mt.start() > pos:
            runs.append(("r", s[pos:mt.start()]))
        runs.append(("l", mt.group(0)))
        pos = mt.end()
    if pos < len(s):
        runs.append(("r", s[pos:]))
    return "".join(t if kind == "l" else t[::-1] for kind, t in reversed(runs))


def make_pdf(rows, size=9):
    """A one-page PDF: rows of (right edge, text) cells, glyphs placed one by one in visual order, a Type 3 font
    whose glyphs draw nothing and whose ToUnicode map gives each code its character (what pdftotext reads)."""
    chars = sorted({c for row in rows for _, t in row for c in t} | {" "})
    if len(chars) > 250:
        raise ValueError("too many characters for a one-byte code")
    code = {c: i + 1 for i, c in enumerate(chars)}
    w, y, ops = size * 0.5, 800, []
    for row in rows:
        for right, text in row:
            vis = visual(text)
            x = right - len(vis) * w
            for k, c in enumerate(vis):
                if c != " ":
                    ops.append(f"BT /F1 {size} Tf {x + k * w:.2f} {y:.1f} Td <{code[c]:02x}> Tj ET")
        y -= size * 1.8
    content = zlib.compress("\n".join(ops).encode())
    n = len(chars)
    cmap = "\n".join(["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
                      "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
                      "/CMapName /Adobe-Identity-UCS def", "/CMapType 2 def", "1 begincodespacerange", "<01> <ff>",
                      "endcodespacerange", f"{n} beginbfchar"] + [f"<{code[c]:02x}> <{ord(c):04x}>" for c in chars]
                     + ["endbfchar", "endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]).encode()
    glyph = b"500 0 0 0 0 0 d1"
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> "
            b"/Contents 4 0 R >>",
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(content) + content + b"\nendstream",
            (f"<< /Type /Font /Subtype /Type3 /FontBBox [0 0 500 700] /FontMatrix [0.001 0 0 0.001 0 0] "
             f"/CharProcs << /g 7 0 R >> /Encoding << /Type /Encoding /Differences [1 {' '.join(['/g'] * n)}] >> "
             f"/FirstChar 1 /LastChar {n} /Widths [{' '.join(['500'] * n)}] /ToUnicode 6 0 R >>").encode(),
            b"<< /Length %d >>\nstream\n" % len(cmap) + cmap + b"\nendstream",
            b"<< /Length %d >>\nstream\n" % len(glyph) + glyph + b"\nendstream"]
    out, offs = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def midgam_pdf():
    rows = [[(560, h)] for h in MIDGAM["head"]]
    rows += [[(560, label), (380, value)] for label, value in MIDGAM["fields"] if len(value) < 40]
    rows += [[(560, MIDGAM["question"])]]
    h = MIDGAM["header"]
    rows += [[(560, h[0]), (330, h[1]), (230, h[2])]]
    rows += [[(560, name)] + ([(330, seats)] if seats else []) + [(230, pct)] for name, seats, pct in MIDGAM["rows"]]
    rows += [[(560, a)] for a in MIDGAM["after"]]
    return make_pdf(rows)


# ---------------------------------------------------------------- 1. reading a filing's text
def test_text():
    print("1. reading a filing's text")
    check(B.house_of('מדגם יעוץ ומחקר') == 'midgam', "the house in a Midgam filing (final letters folded): midgam")
    check(B.selftest() == 0, "build_poll_filings.py --selftest: houses, list names, the verified flag")
    for marks in (True, False):
        p = B.parse_filing(layout_text(MIDGAM, marks))
        tag = "with pdftotext's bidi marks" if marks else "without marks"
        check(p.get("n") == 509 and p.get("invited") == 2521 and p.get("moe") == 4.4,
              f"RTL layout ({tag}): respondents 509, invited 2,521, sampling error 4.4 (got {p.get('n')}, "
              f"{p.get('invited')}, {p.get('moe')})")
        check(p.get("response_rate") == 20 and p.get("refused_pct") == 80,
              f"RTL layout ({tag}): response rate 20, refused 80")
        check(p.get("fieldwork_start") == p.get("fieldwork_end") == "2026-10-12", f"RTL layout ({tag}): fieldwork 12.10.2026")
        check(p.get("seats") == MIDGAM_SEATS and p.get("seats_total") == 120, f"RTL layout ({tag}): the seat table, 120")
        check(p.get("pct") == MIDGAM_PCT, f"RTL layout ({tag}): raw shares of every list, also below the threshold")
        check(p.get("wasted_pct") == 4.0 and p.get("pct_complete") is True and p.get("pct_total") == 100.0,
              f"RTL layout ({tag}): below the threshold 4.0 (1.8 + 2.2: a label with '1%' in it is still a label)")
        check(p.get("undecided_pct") == 14, f"RTL layout ({tag}): undecided 14% read after the table")
        check(p.get("commissioner") == 'חברת החדשות הישראלית בע"מ' and p.get("mode") == "טלפוני + אינטרנטי",
              f"RTL layout ({tag}): the text fields")
    n = B.parse_filing(NARRATIVE)
    check(n.get("n") == 550 and n.get("moe") == 4.2, f"narrative: 550 respondents, 4.2 (got {n.get('n')}, {n.get('moe')})")
    check((n.get("fieldwork_start"), n.get("fieldwork_end")) == ("2026-09-28", "2026-09-29"),
          f"narrative: the range 28-29.9.26 (got {n.get('fieldwork_start')}..{n.get('fieldwork_end')})")
    check(n.get("seats_total") == 120 and n.get("seats", {}).get("Likud") == 24 and n.get("pct", {}).get("National Unity") == 1.1,
          "narrative: rows written with single spaces, a list below the threshold")
    check(n.get("undecided_pct") == 12 and "לא החליטו" not in json.dumps(n.get("below"), ensure_ascii=False),
          "narrative: the undecided row inside the table is neither a list nor a wasted vote")
    t = B.parse_filing(TREND)
    check("seats" not in t, "a trend table (four weeks side by side) is refused, not read as one ballot")
    labels = {"מפלג ת ישר! בראשות גדי איזנקוט": "Yashar", "המילואמיניקים בראשות יועז הנדל": "Reservists",
              'רע"מ בראשות מנסור עבאס': "Ra'am", "מפלגת ימין חדשה בראשות עופר וינטר": "Amcha Yisrael",
              "יחד בראשות נפתלי בנט": "Together", 'חד"ש-תע"ל-בל"ד': "Joint List", "ש״ס": "Shas",
              "כחול לבן בראשות בני גנץ": "National Unity", "הציבור החרדי בראשות מוטי לייטנר": "Haredi Public",
              "ישראל תחילה ועלה ירוק בראשות שרן השכל": None, "מפלגת נעם בראשות אבי מעוז": None,
              "הציונות הדתית וזהות": "Religious Zionism", "האחדות בראשות גלעד ארדן": "Unity",
              "דוכילה": "Likud"}            # the last: text read in visual order (reversed)
    bad = {k: B.party_id(k) for k, v in labels.items() if B.party_id(k) != v}
    check(not bad, f"list labels as pollsters type them (a split word, a typo, a final mem, a new name, a leader): {bad}")
    d = B.dates_in("11-12/10/2026 ו-13.10.26")
    check([x.isoformat() for x in d] == ["2026-10-11", "2026-10-12", "2026-10-13"], f"dates: a day range and a short year {d}")
    check(str(B.local_date("2026-07-26T21:00:00Z")) == "2026-07-27" and str(B.local_date("2026-10-25T22:00:00Z")) == "2026-10-26",
          "gov.il's UTC midnights are Israel's dates, before and after summer time ends (25.10)")
    check(B.parse_filing("טעות הדגימה המרבית  ±0.9%\nמספר המשיבים  500").get("moe") is None,
          "a sampling error below the minimum for its n is a misreading, not kept")


# ---------------------------------------------------------------- 1b. the real filings
# Excerpts of the filings fetched on 16.10.2026 (pdftotext -layout, the bidi marks it adds taken out; the item
# each comes from named): a few lines each, and the seat tables of three templates whole, the readings each rule
# was written for.
KANTAR_FW = ("         2בספטמבר ( 3 – )15:40בספטמבר ()08:30                                      "
             "תאריכי ושעות ביצוע הסקר")                                          # knesset_election53
DIRECT = """\
           חדשות המזרח התיכון  24Iבע״מ               שם הגוף שהזמין את הסקר
    דיירקט פולס בע"מ בראשות צוריאל שרון                 הגורם שערך את הסקר
   17בספטמבר  ,2026בין השעות 9:00-14:00                    תאריכי ביצוע הסקר
                                   8,550   מס' האנשים שהתבקשו להשתתף בסקר
                                    500                 גודל המדגם ההתחלתי
                              525נדגמים      מס' האנשים שהשתתפו בסקר בפועל
               -+4.2%בהסתברות של 95%                              מרווח טעות
     1.אילו הבחירות לכנסת היו מתקיימות היום ,למי הייתם מצביעים?
 %גולמי                מנדטים                   מפלגה
 21.6%                    27                    הליכוד
 17.0%                    21                     ישר
 8.0%                     10                  הדמוקרטים
 7.4%                     9                      ביחד
 6.4%                     8                  ישראל ביתנו
 6.1%                     8                  יהדות התורה
 5.7%                     7                  עוצמה יהודית
 5.4%                     7               הרשימה המשותפת
 5.3%                     7                      ש"ס
 5.2%                     6              הציונות הדתית וזהות
 4.2%                     5                      רע"ם
 3.7%                     5                   עמך ישראל
 2.2%                    2.2%               המילואימניקים
                                              והכלכלית
     נדגמו וקיבלו מתחת ל :1%-צבע שחור ,הציבור החרדי ,אח"י ,כחול לבן
"""                                                                              # knesset_election80
MAAGAR = """\
              )7:00-12:00( 29.9.26                   התאריכים והשעות בהם בוצע הסקר
                    מנדטים                              אחוזים
                                            בעלי        גולמיים
                                                                                                 התשובות
    9.9.26   16.9.26 24.9.26 29.9.26        הדעה      ללא שקלול
                                                        מנדטים
     23        21        23         21       17%         16%                     "ישר!" בראשות גדי איזנקוט
     20        18        19         19       16%         15%                   הליכוד בראשות בנימין נתניהו
      16       16        13         14       12%         11%                     "ביחד" בראשות נפתלי בנט
      9        9             9       8        7%         7%            עוצמה יהודית בראשות איתמר בן גביר
      9        9             8       8        6%         6%                         ש"ס בראשות אריה דרעי
      9        9             8       9        8%         7%                    הדמוקרטים בראשות יאיר גולן
      7        7             7       7        6%         6%                 יהדות התורה בראשות יעקב אשר
      7        7             8       7        5%         5%             ישראל ביתנו בראשות אביגדור ליברמן
                                                                   הרשימה המשותפת בראשות פרופ' יוסף
      7        6             7       7        6%         5%
                                                                                              ג׳בארין
      5        5             5       5        4%         4%                      רע"מ בראשות מנסור עבאס
                                                                   הציונות הדתית  +זהות ,בראשות בצלאל
      4        5             5       6        5%         5%
                                                                                             סמוטריץ'
      4        4             4       5        4%         4%                  עמך ישראל בראשות עופר וינטר
                                                                          המילואימניקים והכלכלית בראשות
     2.2       4             4       4       3.3%        3%
                                                                                     יועז הנדל וירון זליכה
     1.2      0.9        1.1        0.5      0.4%        0.4%                      כחול לבן בראשות בני גנץ
     0.9       1.4       0.5        0.8      0.6%        0.6%           "הציבור החרדי" בראשות מוטי לייטנר
      -         -            -       -         -         0.8%                               מפלגות אחרות
      -         -            -       -         -         4%                                      לא יודע/ת
     120      120        120        120     100%        100%                                         סה"כ
"""                                                                              # knesset_election88
MAAGAR_SEATS = {"Yashar": 21, "Likud": 19, "Together": 14, "Otzma Yehudit": 8, "Shas": 8, "The Democrats": 9, "UTJ": 7,
                "Yisrael Beiteinu": 7, "Joint List": 7, "Ra'am": 5, "Religious Zionism": 6, "Amcha Yisrael": 5,
                "Reservists": 4}
TATIKA = """\
                  הסקר נערך בתאריכים ה 12/8-בשעה  10:00עד ה 13/8-בשעה ,13:00השיבו לו  500משיבים ,סטיית תקן 4.4%
                    100%             500                                   סה"כ
                                               אם הבחירות היו מתקיימות היום ,וכל
                                           המפלגות הקיימות היו מתמודדות בנפרד,
                                                               למי היית מצביע/ה?
חלוקת מנדטים   אחוז משיבים   מספר משיבים
          25       19.20%             96                ישר בראשות גדי אייזנקוט
          21       16.00%             80                                   הליכוד
          13       10.20%             51                ביחד בראשות נפתלי בנט
          11        9.00%             45                             ישראל ביתנו
           9        6.80%             34                               הדמוקרטים
           8        6.40%             32                             יהדות התורה
           8        6.40%             32                                     ש"ס
           7        5.60%             28                            עוצמה יהודית
           6        5.20%             26                        חד"ש תע"ל בל״ד
                        6                     4.60%                        23                              הציונות הדתית
                        6                     4.60%                        23                                        רע"ם
                   לא עבר                     3.00%                        15       בית ציוני בהובלת יועז הנדל וחילי טרופר
                   לא עבר                     2.00%                        10           כחול לבן בהובלת בני גנץ ודדי שמחי
"""                                                                              # knesset_election16
CH13_JULY = """\
 אחוזים גולמיים לא   אחוזים גולמיים לא       תוצאות סקר נוכחי:             שם המפלגה
  משוקללים  -מגזר     משוקללים  -מגזר                   מנדטים
              ערבי                יהודי
             0.57%                1.4%                       23                 כחול לבן
             2.18%               10.7%                       23                    ליכוד
             0.00%                7.8%                       13                     ש"ס
             0.00%                4.4%                       10           הציונות הדתית
             0.00%               15.1%                        9            יהדות התורה
             2.03%                6.0%                        7             ישראל ביתנו
            25.94%                0.0%                        8                    רע"מ
            23.90%                0.0%                        9              חד"ש-תע"ל
            12.58%                0.0%                        4                    בל"ד
             0.00%                4.8%                        4            עוצמה יהודית
             8.29%                5.4%                        5              הדמוקרטים
                                                              5
             0.21%                7.0%                                            ביחד
             2.90%               12.7%                                              ישר
             0.00%                2.3%                                     יסודות ישראל
"""                                                                              # knesset_election1
CH13 = """\
                                                 15.9.2026בשעה  9:00עד  16.9.2026בשעה 9:00                  מועד איסוף נתונים
                                                                                          8,097         גודל המדגם ההתחלתי
 ( 1,023לחישוב המנדטים נכללו  886משיבים –  137משיבים חרדים ולא יהודים מהמדגם הכללי הוצאו
                                                                                                        מספר המשיבים בפועל
                                             כדי למנוע ספירה כפולה עם מדגם החרדים והערבים)
                                                                                          3.1%          טעות הדגימה המקרית
"""                                                                              # knesset_election75
CH13_ROW = "              29.5%            0.0%              0.0%              0.2%                6                                 רע\"מ"
AFKAR = """\
                     אפקאר מחקר וידע בראשות ד"ר הישאם ג'ובראן                 עורך הסקר
         מתאריך  27-8-2026שעה  15:30עד  1-9-2026שעה14:51 :             מועד איסוף נתונים
         מדגם מייצג של כלל האוכלוסיה הערבית בישראל בגילאי +18           אוכלוסיית המדגם
                                                              800      גודל מדגם התחלתי
                          333( 815אינטרנטי ו 482 -תשאול טלפוני)      מספר משיבים בפועל
                                                           +_3.4%   טעות הדגימה המקרית
"""                                                                              # knesset_election55

# Channel 13's sub-samples, each with its count of those asked and its own response rate, and the footnote that
# starts with the label 'שיעור ההיענות' (knesset_election101); one sub-sample with no count (knesset_election86)
CH13_SUBS = """\
מדגם בוגרים יהודים -  4,478מתבקשים להשיב ,שיעור היענות  ,32.6%שיעור משיבים תקינים 13.5%
                                                        ( 603שאלונים תקינים 23 ,השיבו חלקית)
    מדגם צעירים -  1,642מתבקשים להשיב ,שיעור היענות  ,8.4%שיעור משיבים תקינים 60( 3.6%
 מדגם חרדים -  3,135מתבקשים להשיב ,שיעור היענות  ,15.9%שיעור משיבים תקינים 500( 15.9%
                                                                              שאלונים תקינים)      מספר המתבקשים להשתתף
 מדגם ערבים -  439מתבקשים להשיב ,שיעור היענות  230( 52.4%משיבים) ,שיעור משיבים תקינים
                                                                   100( 22.8%שאלונים מלאים)
 שיעור ההיענות כולל את כל מי שניגש לשאלון :מי שהשיב בפועל ,מי שהתחיל וסונן ,מי שהתחיל ולא
 סיים ,ומי שניסה להשיב לאחר סגירת המכסה או סיום האיסוף .שיעור המשיבים התקינים הוא מספר
                                                                                        9,694           גודל המדגם ההתחלתי
"""                                                                              # knesset_election101
CH13_NO_COUNT = """\
    מדגם חרדים אינטרנטי -  1,899מתבקשים להשיב ,שיעור היענות  ,15.4%שיעור משיבים
                           תקינים  293( 15.4%שאלונים תקינים)
                        מדגם חרדים טלפוני -  220משיבים תקינים
 מדגם ערבים -  170מתבקשים להשיב ,שיעור היענות  ,58.8%שיעור משיבים תקינים ( 58.8%
"""                                                                              # knesset_election86
CH13_MODE = """\
  תשאול משולב -  1,119נשאלים ,מהם  898מהאוכלוסייה היהודית בסקר אינטרנטי ו-
                                        221מהאוכלוסייה הלא יהודית בתשאול טלפוני      שיטת איסוף הנתונים
                                     דגימת שכבות עם דגימה אקראית בתוך השכבות               שיטת הדגימה
"""                                                                              # knesset_election64
# Next Data's labels wrapped over two or three lines in their column, the value on one of them
NEXT_DATA = """\
                                                                          מספר האנשים
                                 14,970איש                                שהתבקשו להשתתף
                                                                          בסקר
                                                                           גודל המדגם
                                 2,200איש
                                                                          ההתחלתי
    2,145נדגמים בוגרים (בני  ,)+18המהווים מדגם מייצג של אוכלוסיית אזרחי
                                                                          מספר המשיבים
                          ישראל הרשאים לבחור
                                  14.7%                                   שיעור ההיענות לסקר
                                                                           שיעור האנשים שלא
                                  85.3%
                                                                          השתתפו
"""                                                                              # knesset_election91
# Next Data's seat table, then the lists below the threshold in a table of their own
NEXT_DATA_TABLE = """\
        אחוז גולמי*              מנדטים                                                          רשימה
               24%                     31                                    הליכוד בראשות בנימין נתניהו
               17%                     22                                        ישר בראשות גדי איזנקוט
                8%                     10                                         ש"ס בראשות אריה דרעי
                6%                      8                     הציונות הדתית בראשות בצלאל סמוטריץ' וזהות
                6%                      8                                    הדמוקרטים בראשות יאיר גולן
                6%                      8                             עוצמה יהודית בראשות איתמר בן גביר
                5%                      7                                                   יהדות התורה
                5%                      7                                         יחד בראשות נפתלי בנט
                5%                      7                             ישראל ביתנו בראשות אביגדור ליברמן
                5%                      6                                      רע"מ בראשות מנסור עבאס
                5%                      6                                              חד"ש-תע"ל-בל"ד
               92%                   120                                                          סה"כ
                3%                                                                           לא החליטו
        * אינו לוקח בחשבון פיצוח מתלבטים וחישובי בדר-עופר; יתרת האחוזים מתחלקת בין המפלגות שמתחת
                                                                                       לחסימה.
                                                מפלגות שלא עברו את אחוז החסימה (מתחת ל)3.25%-
              אחוז גולמי                                                                         רשימה
                      2.1%                                                 עמך ישראל בראשות עופר וינטר
                      1.6%                                    המילואימניקים והכלכלית בראשות הנדל וזליכה
                      0.2%                                                       כחול לבן בראשות בני גנץ
                      0.1%                                                                 הציבור החרדי
                                              עמוד  2מתוך 4
"""                                                                              # knesset_election66
NEXT_DATA_WEIGHTED = """\
                                                מפלגות שלא עברו את אחוז החסימה (מתחת ל)3.25%-
           אחוז משוקלל                                                                           רשימה
                      2.9%                                                 עמך ישראל בראשות עופר וינטר
                      0.9%                                                 נועם לישראל בראשות אבי מעוז
                                              עמוד  2מתוך 8
"""                                                                              # knesset_election108


def test_real():
    print("1b. the real filings (excerpts)")
    v, _ = B.find_field(KANTAR_FW.splitlines(), "fieldwork")
    check(v and [d.isoformat() for d in v] == ["2026-09-02", "2026-09-03"],
          f"Kantar: '2בספטמבר ( 3 – )15:40בספטמבר': a Hebrew month, the second day moved by the layout ({v})")
    p = B.parse_filing(DIRECT)
    check(B.house_of(p.get("pollster") or "") == "direct-polls" and (p.get("fieldwork_start"), p.get("fieldwork_end"))
          == ("2026-09-17", "2026-09-17") and p.get("n") == 525 and p.get("n_initial") == 500 and p.get("moe") == 4.2,
          f"Direct Polls: '17בספטמבר ,2026', '525נדגמים', 'מרווח טעות' ({p.get('fieldwork_end')}, {p.get('n')}, "
          f"{p.get('moe')})")
    check(p.get("seats_total") == 120 and p.get("seats", {}).get("Likud") == 27 and p.get("seats", {}).get("Yashar") == 21
          and "Reservists" not in p.get("seats", {}) and p.get("pct", {}).get("Reservists") == 2.2,
          "Direct Polls: no total row; 'ישר' alone is Yashar; '2.2%  2.2%' is one share below the threshold, no seats")
    p = B.parse_filing(MAAGAR)
    check(p.get("seats") == MAAGAR_SEATS and p.get("fieldwork_end") == "2026-09-29",
          "Maagar Mochot: four weeks side by side, the seats of the week dated the fieldwork (29.9.26), a row's "
          f"cells moved by the layout ('9  9  9  8') read in the header's order ({B.seat_diff(MAAGAR_SEATS, p.get('seats'))})")
    check(p.get("pct", {}).get("Yashar") == 16 and p.get("pct", {}).get("Otzma Yehudit") == 7
          and p.get("undecided_pct") == 4 and p.get("pct", {}).get("National Unity") == 0.4,
          "Maagar Mochot: the raw share is the column 'גולמיים ללא שקלול', not that of those with an opinion; "
          "'-' and fractions in the seats column are no seats")
    check("seats" not in B.parse_filing(MAAGAR.split("\n", 1)[1]),
          "Maagar Mochot: the same table with its fieldwork unknown is not read (which week is the poll's?)")
    p = B.parse_filing(TATIKA)
    check((p.get("fieldwork_start"), p.get("fieldwork_end")) == ("2026-08-12", "2026-08-13") and p.get("n") == 500
          and p.get("moe") == 4.4, f"Tatika's running text: '12/8' to '13/8' (no year), '500משיבים', 'סטיית תקן 4.4%' "
                                   f"({p.get('fieldwork_start')}..{p.get('fieldwork_end')}, {p.get('n')})")
    check(p.get("seats_total") == 120 and p.get("seats", {}).get("Ra'am") == 6 and "Reservists" not in p.get("seats", {})
          and p.get("pct", {}).get("Reservists") == 3.0,
          "Tatika: seats, share and a count of respondents side by side, the last rows at another scale, 'לא עבר'")
    check("seats" not in B.parse_filing(CH13_JULY),
          "Channel 13's July layout: a seats figure alone on a line, the column out of step with the names: not read")
    p = B.parse_filing(CH13)
    check(p.get("n") == 1023 and p.get("moe") == 3.1 and p.get("n_initial") == 8097
          and (p.get("fieldwork_start"), p.get("fieldwork_end")) == ("2026-09-15", "2026-09-16"),
          f"Channel 13: 'מועד איסוף נתונים', 'מספר המשיבים בפועל' alone on its line, its value wrapped around it "
          f"({p.get('n')}, {p.get('fieldwork_start')}..{p.get('fieldwork_end')})")
    r = B.table_rows([CH13_ROW])[0]
    check(B.resolve(r) == (6, None, False), "Channel 13: one seats figure beside four sub-samples' shares: the seats, "
                                            "no share")
    p = B.parse_filing(CH13_SUBS)
    check(p.get("invited") == 9694 == p.get("n_initial") and "response_rate" not in p and p.get("subsamples") == 4,
          f"Channel 13: those asked the sum of four sub-samples' 'מתבקשים להשיב'; each has its own response rate, so "
          f"none of the whole ({p.get('invited')}, {p.get('response_rate')})")
    check(B.find_field(CH13_SUBS.splitlines()[6:9], "response_rate") == (None, None),
          "a footnote that starts with the label ('שיעור ההיענות כולל את כל מי...') is no label alone on its line: "
          "the figure on the next line is not its value")
    p = B.parse_filing(CH13_NO_COUNT)
    check("invited" not in p and "response_rate" not in p and p.get("subsamples") == 3
          and any("states no count" in n for n in p.get("notes", [])),
          "Channel 13: a sub-sample with no count of those asked ('מדגם חרדים טלפוני - 220משיבים'): no total given")
    p = B.parse_filing(CH13_MODE)
    check(p.get("mode", "").startswith("תשאול משולב") and p["mode"].endswith("בתשאול טלפוני")
          and p.get("sampling") == "דגימת שכבות עם דגימה אקראית בתוך השכבות",
          f"a text value cut after 'ו-': its first half from the line above ({p.get('mode', '')[:30]}...)")
    p = B.parse_filing(NEXT_DATA)
    got = {k: p.get(k) for k in ("invited", "n_initial", "n", "response_rate", "refused_pct")}
    check(got == {"invited": 14970, "n_initial": 2200, "n": 2145, "response_rate": 14.7, "refused_pct": 85.3},
          f"Next Data: labels wrapped over two or three lines, the value on one of them ({got})")
    p = B.parse_filing(NEXT_DATA_TABLE)
    check(p.get("seats_total") == 120 and p.get("pct", {}).get("Amcha Yisrael") == 2.1
          and p.get("pct", {}).get("Reservists") == 1.6 and p.get("wasted_pct") == 4.0 and len(p.get("below", [])) == 4
          and p.get("pct_total") == 96.0 and p.get("undecided_pct") == 3,
          f"Next Data: the lists below the threshold from their own table after the seat table ({p.get('wasted_pct')}, "
          f"{p.get('pct_total')})")
    kind, rows = B.below_table(NEXT_DATA_WEIGHTED.splitlines(), 0)
    p = B.parse_filing(NEXT_DATA_TABLE.split("                                                מפלגות")[0]
                       + NEXT_DATA_WEIGHTED)
    check(kind == "weighted" and len(rows) == 2 and "below" not in p and p.get("wasted_pct") is None
          and len(p.get("below_weighted", [])) == 2 and "Amcha Yisrael" not in p.get("pct", {}),
          "... given in weighted shares ('אחוז משוקלל'): kept apart, not raw shares, the share below it unknown")
    p = B.parse_filing("איסוף הנתונים :הנתונים נאספו בידי חברת  Next Dataבאמצעות מערכת דיגיטלית אינטרנטית לאיסוף "
                       "נתונים.")                                                 # knesset_election21
    check(B.house_of(p.get("pollster") or "") == "filber" and p.get("mode", "").endswith("לאיסוף נתונים."),
          f"Next Data named in running text ('הנתונים נאספו בידי חברת Next Data'), no editor's label ({p.get('pollster')})")
    p = B.parse_filing(AFKAR)
    check(p.get("n") == 815 and p.get("n_initial") == 800 and p.get("moe") == 3.4 and B.house_of(p["pollster"]) == "afkar"
          and (p.get("fieldwork_start"), p.get("fieldwork_end")) == ("2026-08-27", "2026-09-01")
          and p.get("sector") == "האוכלוסיה הערבית",
          f"Afkar: '333( 815... 482': the total its parts add up to; '27-8-2026'; a poll of the Arab public "
          f"({p.get('n')}, {p.get('fieldwork_end')}, {p.get('sector')})")
    houses = {"חברת  ,Next Dataהמנופים  ,1הרצליה                עורך הסקר": "filber",            # knesset_election68
              "מכון  ,DRIבוסתנאי  ,43רמת השרון                                     עורך הסקר": "dri",  # knesset_election59
              "     מרכז אקורד ,חוצות שפיים ,באמצעות חברת  iPanelבר כוכבא , 21בני       עורך הסקר ומענו": "accord"}
    bad = {k[:20]: B.house_of(B.parse_filing(k).get("pollster") or "") for k, v in houses.items()
           if B.house_of(B.parse_filing(k).get("pollster") or "") != v}
    check(not bad, f"houses as the PDFs name them: 'Next Data' and 'DRI' glued to Hebrew, 'עורך הסקר ומענו' {bad}")
    lines = {"                                                                   תאריך ביצוע הסקר4.8.2026–3 :":
             ("2026-08-03", "2026-08-04"),                                       # knesset_election21
             "                    25-26.8.26\n                 1400-2400 :25/7                      התאריכים והשעות "
             "בהם בוצע הסקר\n                 0800-1300 :26/8": ("2026-08-25", "2026-08-26"),  # knesset_election38
             "תאריך הביצוע 27 :ביולי  N = 656 | 2026משיבים מתוך  4982נמענים שאליהם נשלח הסקר המגדירים":
             ("2026-07-27", "2026-07-27")}                                       # knesset_election26
    bad = {k.strip()[:24]: (p.get("fieldwork_start"), p.get("fieldwork_end")) for k, v in lines.items()
           for p in [B.parse_filing(k)] if (p.get("fieldwork_start"), p.get("fieldwork_end")) != v}
    check(not bad, f"fieldwork: a range's first day moved after the date, the lines around a typo, '27 :ביולי' {bad}")
    p = B.parse_filing("                 1600-2400 1/8\n                                                      התאריכים "
                       "והשעות בהם בוצע הסקר\n                 0700-1500 2/9")   # knesset_election48
    check(p.get("fieldwork_start") == "2026-08-01" and any("typo" in n for n in p.get("notes", [])),
          "fieldwork '1/8' to '2/9' kept as written, with a note: over two weeks")
    p = B.parse_filing("       משיבים 588 :נדגמים בוגרים (בני  )+18המהווים מדגם מייצג של האוכלוסייה הכללית של אזרחי "
                       "ישראל.")                                                  # knesset_election21
    check(p.get("n") == 588 and B.parse_filing(                                  # knesset_election26"סקר בוחרי הימין בישראל\nקבוצה  – 1בוחרי הליכוד 387 :משיבים ( 59%מהמדגם).\n"
                                               "תאריך הביצוע 27 :ביולי  N = 656 | 2026משיבים מתוך  4982נמענים").get("n")
          == 656, "respondents in running text: 'משיבים 588 :נדגמים'; 'N = 656' before a sub-group's count, never "
                  "the year glued to the word ('2026משיבים')")
    p = B.parse_filing("                                                        237( 21.4%שאלונים תקינים)       מספר "
                       "המתבקשים")                                                # knesset_election64
    check("invited" not in p, "a count glued to a bracket, a piece of a wrapped sentence ('237( 21.4%...'), is no count")
    pops = {"מדגם ארצי מייצג של ליברלים ,בגילאי +18": "ליברלים", "מדגם ארצי מייצג של בני 18-22": "בני 18-22",
            "אזרחי ישראל יהודים שאינם חרדים ,בגילאי ( 34–22חילונים ,מסורתיים": "שאינם חרדים",
            "מדגם ארצי ומייצג של האוכלוסייה בישראל בגילאי +18 (יהודים וערבים)": None,
            "מדגם מייצג של אזרחי ישראל מגיל  18ומעלה ,יהודים וערבים כאחד": None}
    bad = {k[:30]: B.sector_of(k, []) for k, v in pops.items() if B.sector_of(k, []) != v}
    check(not bad, f"a sector poll by its population (Dialog's, Accord's), not a national one (Kantar's, Lazar's) {bad}")
    labels = {"רשימה ערבית משותפת של חדש תעל ובלד בראשות יוסף גאברין": "Joint List", "רעמ בראשות דר מנסור עבאס": "Ra'am",
              "ישר": "Yashar", "ישראל ביתנו": "Yisrael Beiteinu", "מפלגת ימין חדשה בראשות עופר וינטר": "Amcha Yisrael"}
    bad = {k: B.party_id(k) for k, v in labels.items() if B.party_id(k) != v}
    check(not bad, f"Lazar's and Direct Polls' list names {bad}")
    total = B.table_rows(["       1.1%          0                    כחול לבן בראשות בני גנץ",
                          "     100.0%         120"])[-1]                       # knesset_election67
    check(B.is_total(total["label"]) and not total.get("orphan"), "Lazar: a total row of numbers only ('100.0%  120')")
    # Maagar Mochot's of 3.9.2026 (knesset_election48): what the lists below the threshold would win without it
    res = [(20, 15.0, False), (19, 14.0, False), (18, 13.0, False), (10, 7.0, False), (9, 6.0, False), (9, 7.0, False),
           (7, 5.0, False), (7, 5.0, False), (7, 5.0, False), (5, 4.0, False), (5, 4.0, False), (4, 3.0, False),
           (3, 2.0, False), (None, None, False), (None, None, False), (1, 1.0, False), (1, 1.0, False),
           (None, 1.0, False), (None, 4.0, False)]
    out = B.below_threshold(res)
    check(sum(x[0] or 0 for x in out) == 120 and out[12][0] == 0 and out[11][0] == 4,
          "seats past 120 given to lists under 3.25% ('הבית הציוני  3  2%'): no seats")
    check(B.below_threshold(res[:12] + [(3, 4.0, False)]) == res[:12] + [(3, 4.0, False)],
          "but not to a list over the threshold: such a table is not read")


# ---------------------------------------------------------------- 2. the PDF path
def test_pdf(tmp):
    print("2. a PDF read with pdftotext")
    if not shutil.which("pdftotext"):
        print("  skip no pdftotext on this machine")
        return None
    path = write(os.path.join(tmp, "midgam.pdf"), midgam_pdf())
    text, err = B.pdf_text(path)
    p = B.parse_filing(text or "")
    check(err is None and p.get("seats") == MIDGAM_SEATS and p.get("pct") == MIDGAM_PCT,
          f"the seat table and the shares from a PDF with glyphs in visual order ({err or 'read'})")
    check(p.get("n") == 509 and p.get("moe") == 4.4 and p.get("fieldwork_end") == "2026-10-12",
          f"respondents, sampling error and fieldwork from the PDF (got {p.get('n')}, {p.get('moe')}, {p.get('fieldwork_end')})")
    return path


# ---------------------------------------------------------------- 3. the builder
def poll(polls, date, house):
    return next(p for p in polls if p["date"] == date and p["house"] == house)


def test_builder(tmp, pdf_path):
    print("3. the builder")
    polls_src = os.path.join(ROOT, "site", "data", "polls_2026.json")
    polls_doc = json.load(open(polls_src, encoding="utf-8"))
    polls = polls_doc["polls"]
    polls_path = write(os.path.join(tmp, "b", "polls_2026.json"), polls_doc)
    before = open(polls_path, "rb").read()
    ref_path = os.path.join(ROOT, "pipeline", "reference", "poll_filings_index.json")
    ref = json.load(open(ref_path, encoding="utf-8"))
    check(ref.get("verified") is False and all(s.get("url") and s.get("seen") for s in ref["sources"].values()),
          "the reference index: every source with its address and date, verified: false")
    check(all(B.canon(f["pdf"]) for f in ref["filings"]), f"the reference index: {len(ref['filings'])} filings, "
          "each at a CEC filing address")
    # a fetch: the listing for knesset_election106 and its PDF (as pdftotext's text; and, below, as the PDF
    # itself), a path that leaves the fetch
    fetched = os.path.join(tmp, "b", "fetch")
    listing = {"results": [
        {"UrlName": "knesset_election106", "Data": {"survey_editor": "מדגם יעוץ ומחקר", "media": "חדשות 12",
                                                   "date_the_survey": "2026-10-11T21:00:00Z", "survey_number": "4202",
                                                   "file_PDF": [{"FileName": "Survey_4202.pdf", "Extension": "pdf"}]}},
        {"UrlName": "../../etc", "Data": {}}]}
    write(os.path.join(fetched, "listing.json"), listing)
    write(os.path.join(fetched, "files", "text", "knesset_election106__Survey_4202.txt"), layout_text(MIDGAM))
    write(os.path.join(fetched, "files", "pdf", "knesset_election106__Survey_4202.pdf"), b"%PDF-1.4 not read: text given")
    write(os.path.join(tmp, "b", "outside.txt"), layout_text(MIDGAM))
    url106 = "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/knesset_election106/he/Survey_4202.pdf"
    url81 = "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/knesset_election81/he/Survey_4162.pdf"
    rows = [{"item": "knesset_election106", "url": url106, "saved": "files/pdf/knesset_election106__Survey_4202.pdf",
             "text": "files/text/knesset_election106__Survey_4202.txt", "from": ["listing"]},
            {"item": "knesset_election81", "url": url81, "saved": "files/pdf/../../outside.txt",
             "text": "../outside.txt", "from": ["or523"]}]
    write(os.path.join(fetched, "filings.json"), rows)
    out1 = os.path.join(tmp, "b", "out1.json")
    doc = B.build(polls_path, ref_path, [fetched], out1)
    check(open(polls_path, "rb").read() == before, "polls_2026.json is unchanged, byte for byte")
    check(not any("seats" in r for r in doc["polls"]), "no seat number in the output (only seat_diff where they differ)")
    by = {r["key"]: r for r in doc["polls"]}
    p106 = poll(polls, "2026-10-12", "midgam")
    r = by.get(f"{p106['date']}|{p106['pollster']}|{p106['outlet']}", {})
    check(r.get("match") == "seats" and r.get("seats_equal") is True and r.get("filing", {}).get("url") == url106,
          "Midgam 12.10 matched to knesset_election106 by its seats")
    check(r.get("verified") is True and r.get("src", {}).get("n") == "cec_pdf" and r.get("src", {}).get("pct") == "cec_pdf",
          "a filing read here wins over the third parties and is marked verified")
    check(r.get("n") == 509 and r.get("moe") == 4.4 and r.get("pct") == MIDGAM_PCT and r.get("wasted_pct") == 4.0
          and r.get("fieldwork") == {"start": "2026-10-12", "end": "2026-10-12"},
          "its respondents, sampling error, shares, wasted share and fieldwork")
    check(r.get("filing", {}).get("number") == "4202" and r.get("filing", {}).get("listing", {}).get("survey_date") == "2026-10-12",
          "the listing's number and its UTC date as Israel's")
    p81 = poll(polls, "2026-09-22", "midgam")
    r81 = by.get(f"{p81['date']}|{p81['pollster']}|{p81['outlet']}", {})
    check(r81.get("filing", {}).get("item") == "knesset_election81" and r81.get("verified") is False
          and r81.get("src", {}).get("n") == "isaranga",
          "a fetch path that leaves the fetch directory is ignored: knesset_election81 stays a third party's reading")
    check(r81.get("previous_link", "").endswith("knesset_election86/he/Survey_4169.pdf")
          and any(c["key"] == r81["key"] for c in doc["conflicts"]),
          "polls_2026.json's link to another poll's filing (Midgam 22.9 -> Channel 13's 86) is reported as a conflict")
    check(all(r["seats_equal"] or "pct" not in r for r in doc["polls"]),
          "shares are attached only where the filing's seats are the poll's")
    hd = [r for r in doc["polls"] if r["match"] == "house+date"]
    check(hd and all(r.get("seat_diff") and "pct" not in r for r in hd),
          f"house and date matches list their seat differences and carry no shares ({len(hd)})")
    items = [r["filing"]["item"] for r in doc["polls"]]
    check(len(items) == len(set(items)), "each filing goes to one poll at most")
    check(doc["counts"]["matched"] >= 40, f"most polls matched ({doc['counts']['matched']}/{doc['counts']['polls']})")
    out2 = os.path.join(tmp, "b", "out2.json")
    B.build(polls_path, ref_path, [fetched], out2)
    check(open(out1, "rb").read() == open(out2, "rb").read(), "the same input, the same output")
    lab = doc["inputs"]["fetched"][0]
    check(lab["source"].startswith("ops-reports:reports/fetch/") and tmp not in open(out1, encoding="utf-8").read()
          and lab["listing_sha256"] == B.sha256(os.path.join(fetched, "listing.json")),
          f"the fetch recorded as ops-reports names it, with its listing's SHA-256, no local path in the file ({lab})")
    check(lab["source"] == "ops-reports:reports/fetch/poll_filings" and lab["started"] is None,
          f"... a directory not named as fetch.yml names one (latest/, YYYYMMDD-HHMM/) and no summary.json: neither "
          f"its local name nor its parent's taken ({lab['source']})")
    stamp = os.path.join(tmp, "b", "20261017-0002")
    shutil.copytree(fetched, stamp)
    write(os.path.join(stamp, "summary.json"), {"fetcher": "poll_filings", "started": "2026-10-16T21:02:41+00:00"})
    lab = B.fetch_label(stamp)
    check(lab["source"] == "ops-reports:reports/fetch/poll_filings/20261017-0002"
          and lab["started"] == "2026-10-16T21:02:41+00:00",
          f"... its stamp directory, its fetcher and start from summary.json ({lab['source']})")
    write(os.path.join(stamp, "summary.json"), {"fetcher": "/root/secret/dir", "started": {"x": "/home/user/leak"}})
    lab = B.fetch_label(stamp)
    check(lab["source"] == "ops-reports:reports/fetch/poll_filings/20261017-0002" and lab["started"] is None,
          f"... a summary.json whose fetcher is a path and whose start is no timestamp: neither taken ({lab})")
    test_rules(polls)
    if pdf_path:
        # the same fetch with the PDF itself and no text: read here with pdftotext
        fp = os.path.join(tmp, "b", "fetch_pdf")
        write(os.path.join(fp, "listing.json"), listing)
        shutil.copy(pdf_path, write(os.path.join(fp, "files", "pdf", "knesset_election106__Survey_4202.pdf"), b""))
        write(os.path.join(fp, "filings.json"), [{**rows[0], "text": None}])
        d2 = B.build(polls_path, ref_path, [fp], os.path.join(tmp, "b", "out_pdf.json"))
        r2 = {r["key"]: r for r in d2["polls"]}.get(r.get("key"), {})
        check(r2.get("verified") is True and r2.get("n") == 509 and r2.get("pct") == MIDGAM_PCT
              and r2.get("src", {}).get("moe") == "cec_pdf", "a fetched PDF without text is read here with pdftotext")
    # the committed file: the reference alone (no fetch yet)
    committed = os.path.join(ROOT, "site", "data", "poll_filings_2026.json")
    if os.path.exists(committed):
        built_from = json.load(open(committed, encoding="utf-8")).get("inputs", {})
        if built_from.get("polls_sha256") != B.sha256(polls_src) or built_from.get("fetched"):
            # the daily update rewrites polls_2026.json; the file is rebuilt from it, not checked against it
            print("  note site/data/poll_filings_2026.json was built from another polls_2026.json or from a fetch: "
                  "python3 pipeline/build_poll_filings.py [--fetched DIR] rebuilds it")
        else:
            out3 = os.path.join(tmp, "b", "out3.json")
            B.build(polls_src, ref_path, [], out3)
            check(open(out3, "rb").read() == open(committed, "rb").read(),
                  "site/data/poll_filings_2026.json is the builder's output for the committed inputs")
        text = open(committed, encoding="utf-8").read()
        check(all(isinstance(x, dict) and x.get("source", "").startswith("ops-reports:") for x in built_from.get("fetched", []))
              and not re.search(r'"(?:/tmp|/home|/root|[A-Z]:\\\\)', text),
              "site/data/poll_filings_2026.json names its fetch as ops-reports does, and no local path")


def filing_rec(item, house, fw, n, seats, sent, **kw):
    """A filing as build() holds it (merged), its seats read from its PDF."""
    return {"item": item, "house": house, "fieldwork_start": fw[0], "fieldwork_end": fw[1], "n": n, "seats": seats,
            "src": {"seats": "cec_pdf", "n": "cec_pdf"}, "read": True, "url": f"https://x/{item}", "also": [],
            "listing": {"date_transfer_to_cec": sent}, **kw}


def test_rules(polls):
    """The rules on the real cases of 16.10.2026, as the filings' numbers give them: the respondents over the
    initial sample, the conflicts with polls_2026.json's links, the filings no poll has."""
    rec = B.new_rec("knesset_election80")
    rec["texts"] = [{"url": "u", "pollster": 'דיירקט פולס בע"מ', "n": 525, "n_initial": 500, "fieldwork_end": "2026-09-17",
                     "seats_total": 120, "seats": {"Likud": 120}}]
    rec["listing"] = {"editor": 'דיירקט פולס בע"מ'}
    f = B.merged(rec)
    check(not f["doubts"] and any("5.0% over the initial sample 500" in n for n in f.get("notes", [])),
          f"525 respondents of an initial 500 (Direct Polls, 17.9): a panel's overshoot, said, not a doubt ({f['doubts']})")
    rec["texts"][0].update(n=1210, n_initial=1000)
    check(any("more than 10% over" in d for d in B.merged(rec)["doubts"]),
          "1,210 of 1,000 (Direct Polls, 13.10): more than 10% over, a doubt")
    rec["texts"][0].update(n=525, invited=500)
    check(any("asked to take part" in d for d in B.merged(rec)["doubts"]), "more respondents than were asked: a doubt")
    rec["texts"][0].update(invited=8550, fieldwork_start="2026-08-01", fieldwork_end="2026-09-02", fieldwork_typo=True)
    check(any("span over two weeks" in d for d in B.merged(rec)["doubts"]),
          "fieldwork dates over two weeks apart as written (Maagar Mochot's '1/8' for 1/9): a doubt, not verified")
    s57 = {"Likud": 20, "Together": 13, "Yashar": 23, "The Democrats": 8, "Religious Zionism": 6, "Otzma Yehudit": 7,
           "Amcha Yisrael": 4, "Yisrael Beiteinu": 7, "Shas": 7, "UTJ": 8, "Reservists": 4, "Joint List": 7, "Ra'am": 6}
    s53 = dict(s57, Likud=21, Yashar=24, **{"The Democrats": 9, "Yisrael Beiteinu": 9, "Reservists": 0, "Ra'am": 5})
    p = {"date": "2026-09-06", "house": "kantar", "seats": s57, "n": 555}
    kan = filing_rec("knesset_election57", "kantar", ("2026-09-06", "2026-09-06"), 551, s57, "2026-09-07")
    ih = filing_rec("knesset_election53", "kantar", ("2026-09-02", "2026-09-03"), 555, s53, "2026-09-06")
    v, note = B.conflict(p, ih, kan)
    check(v == "matched" and "n (555) is the linked filing's" in note,
          f"Kantar 6.9: the matched filing has the poll's seats, the link is Israel Hayom's of 3.9 and gave its n ({v})")
    again = filing_rec("knesset_election82", "kantar", ("2026-09-09", "2026-09-09"), 554, s57, "2026-09-24")
    first = filing_rec("knesset_election60", "kantar", ("2026-09-09", "2026-09-09"), 554, s57, "2026-09-10")
    v, note = B.conflict(dict(p, date="2026-09-09"), again, first)
    check(v == "both" and "knesset_election82 (sent 2026-09-24) repeats knesset_election60" in note,
          f"Kantar 9.9: one poll filed twice, either link right ({v})")
    s64 = dict(s57, Yashar=22, **{"Amcha Yisrael": 3})
    ch13 = filing_rec("knesset_election64", "ch13", ("2026-09-09", "2026-09-09"), 1119, s64, "2026-09-13")
    ch12 = filing_rec("knesset_election69", "midgam", ("2026-09-09", "2026-09-09"), 504, s53, "2026-09-13")
    v, note = B.conflict({"date": "2026-09-09", "house": "ch13", "seats": s57, "n": 504}, ch12, ch13)
    check(v == "matched" and "nearest" in note and "Yashar 23 here, 22 filed" in note,
          f"Channel 13 9.9: the matched filing, of the poll's house, the nearest; the link is Channel 12's ({v})")
    filings = {f["item"]: f for f in (kan, ih, again, first)}
    first_date = min(q["date"] for q in polls)
    cls = {f["item"]: B.classify(f, filings, polls, first_date, {"knesset_election82"})[0] for f in (again, first, ih)}
    check(cls == {"knesset_election82": "refiling", "knesset_election60": "duplicate", "knesset_election53": "before_polls"},
          f"the filings no poll has: a re-filing, the first filing of a poll whose re-filing was taken, one before the "
          f"poll table's first poll ({cls})")
    sector = filing_rec("knesset_election85", "dialog", ("2026-09-22", "2026-09-23"), 500, {}, "2026-09-27",
                        sector="ליברלים")
    sector["src"] = {}
    new = filing_rec("knesset_election110", "direct-polls", ("2026-10-13", "2026-10-13"), 1210, s57, "2026-10-14")
    cls = {f["item"]: B.classify(f, {**filings, "s": sector, "n": new}, polls, first_date) for f in (sector, new)}
    check(cls["knesset_election85"][0] == "sector" and cls["knesset_election110"][0] == "not_in_polls",
          f"a sector poll; a national one polls_2026.json does not have ({[c[1][:50] for c in cls.values()]})")


# ---------------------------------------------------------------- 4. the fetcher
GUID = "11111111-2222-3333-4444-555555555555"


class Govil(http.server.BaseHTTPRequestHandler):
    items, mode, hits = [], "ok", []

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        Govil.hits.append(("GET", self.path))
        p = self.path
        if p.startswith("/govil/he/departments/dynamiccollectors/knesset_election_polls_26"):
            return self.send(200, f'<div ng-init="dynamicCtrl.Events.initCtrl(&#39;{GUID}&#39;, 10)"></div>', "text/html")
        m = re.match(r"/govil/BlobFolder/dynamiccollectorresultitem/(knesset_election\d+)/he/(.+)$", p)
        if m:
            item, name = m.group(1), m.group(2)
            if item == "knesset_election3":
                return self.send(404, "not found", "text/html")
            if item == "knesset_election7" and self.headers.get("Accept-Encoding") == "gzip, deflate":
                # refuses urllib's request (its headers), answers curl's: a TLS client turned away by Cloudflare
                return self.send(403, "<html>Attention Required! | Cloudflare</html>", "text/html")
            if item == "knesset_election4":
                return self.send(200, "<html><head><title>Just a moment...</title></head>cf-chl</html>", "text/html")
            if (item == "knesset_election201" and name != "Survey_4302.pdf") or B.item_no(item) > 201:
                return self.send(404, "not found", "text/html")
            return self.send(200, b"%PDF-1.4\n% " + f"{item} {name}".encode() + b"\n%%EOF\n", "application/pdf")
        if p.startswith("/gh/or523/"):
            return self.send(200, json.dumps({"polls": [
                {"id": "knesset_election200", "pdf": "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/knesset_election200/he/Survey_4300.pdf"},
                {"id": "x", "pdf": "https://evil.example/BlobFolder/dynamiccollectorresultitem/knesset_election99/he/a.pdf"},
                {"id": "y", "pdf": "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/knesset_election98/he/../../x.pdf"}],
                "excluded": []}))
        if p.startswith("/gh/amitlev/"):
            return self.send(200, "/* data */\nwindow.BASE_POLLS_DATA = [{\"govilSourceUrl\": "
                                  "\"https://www.gov.il/BlobFolder/dynamiccollectorresultitem/knesset_election2/he/Survey_4040.pdf\"}];\n"
                                  "window.GOVIL_TOPICAL_DATA = [];\n", "application/javascript")
        if p.startswith("/gh/idoherling/"):
            return self.send(200, "4041|knesset_election1|סקר בחירות מיום 28.7.2026.pdf|x|y|2026-07-27|2026-08-01|\n", "text/plain")
        return self.send(404, "no", "text/plain")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        Govil.hits.append(("POST", self.path, body))
        if not self.path.startswith("/govil/he/api/DynamicCollector"):
            return self.send(404, "{}")
        if Govil.mode == "blocked":
            return self.send(403, "<html>Attention Required! | Cloudflare</html>", "text/html")
        if body.get("DynamicTemplateID") != GUID:
            return self.send(200, json.dumps({"Results": [], "TotalResults": 0}))
        skip = body.get("From", 0)
        if Govil.mode == "from-only" and body["QueryFilters"]["skip"]["Query"] != 0:
            skip = 0                                       # a server that takes the offset from From only
        page = Govil.items[skip:skip + 10]
        return self.send(200, json.dumps({"Results": page, "TotalResults": len(Govil.items)}, ensure_ascii=False))


def run_fetcher(out, base, ref, polls, curl=False):
    args = [sys.executable, FETCHER, "--out", out, "--rewrite", f"https://www.gov.il={base}/govil",
            "--rewrite", f"https://raw.githubusercontent.com={base}/gh", "--only-rewritten",
            "--timeout", "5", "--ref", ref, "--polls", polls, "--workers", "2"] + ([] if curl else ["--no-curl"])
    p = subprocess.run(args, capture_output=True, text=True, timeout=120)
    return p


def test_fetcher(tmp):
    print("4. the fetcher against a stand-in for gov.il")
    Govil.items = [{"UrlName": f"knesset_election{i}", "Data": {
        "survey_editor": "מדגם", "date_the_survey": "2026-10-11T21:00:00Z",
        "file_PDF": [{"FileName": f"Survey_{4000 + i}.pdf"}]}} for i in range(1, 14)]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Govil)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    ref = write(os.path.join(tmp, "f", "ref.json"), {"filings": [
        {"pdf": "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/knesset_election5/he/Survey_4005.pdf"}]})
    polls = write(os.path.join(tmp, "f", "polls.json"), {"polls": [
        {"filing": "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/knesset_election6/he/Survey_4006-b.pdf"}]})
    try:
        for mode in ("ok", "from-only"):
            Govil.mode, Govil.hits = mode, []
            out = os.path.join(tmp, "f", mode)
            p = run_fetcher(out, base, ref, polls)
            check(p.returncode == 0, f"[{mode}] exit 0 ({p.stdout.strip()[-200:]}{p.stderr.strip()[-300:]})")
            s = json.load(open(os.path.join(out, "summary.json"), encoding="utf-8"))
            lst = json.load(open(os.path.join(out, "listing.json"), encoding="utf-8"))
            posts = [h for h in Govil.hits if h[0] == "POST"]
            check(lst["template_id"] == GUID and len(lst["results"]) == 13 and s["listing"]["total_results"] == 13,
                  f"[{mode}] the template id from the page's initCtrl, all 13 results paged ({len(posts)} requests)")
            check(all(h[2].get("DynamicTemplateID") and "QueryFilters" in h[2] and "From" in h[2] for h in posts),
                  f"[{mode}] the request shape: DynamicTemplateID, QueryFilters.skip.Query, From")
            all_rows = json.load(open(os.path.join(out, "filings.json"), encoding="utf-8"))
            rows = {r["item"]: r for r in all_rows if "listing" in r["from"] or r["item"] not in
                    {x["item"] for x in all_rows if "listing" in x["from"]}}
            found_in = {}
            for r in all_rows:
                found_in.setdefault(r["item"], set()).update(r["from"])
            check(rows["knesset_election1"].get("saved") and open(os.path.join(out, rows["knesset_election1"]["saved"]), "rb").read(5) == b"%PDF-",
                  f"[{mode}] a PDF saved under files/pdf/")
            check(sum(1 for r in all_rows if r["item"] == "knesset_election1" and r.get("saved")) == 2,
                  f"[{mode}] both files of an item filed twice (the listing's and an index's) are fetched")
            check(rows["knesset_election3"].get("status") == 404 and not rows["knesset_election3"].get("saved"),
                  f"[{mode}] a 404 recorded, the run goes on")
            check("challenge" in (rows["knesset_election4"].get("error") or "") and not rows["knesset_election4"].get("saved"),
                  f"[{mode}] a challenge page instead of a PDF is not saved ({rows['knesset_election4'].get('error')})")
            check(found_in["knesset_election1"] >= {"listing", "idoherling"} and "or523" in found_in.get("knesset_election200", ())
                  and "amitlev" in found_in["knesset_election2"] and "reference" in found_in["knesset_election5"]
                  and "polls_2026" in found_in["knesset_election6"],
                  f"[{mode}] addresses from the listing, the third parties, the reference and polls_2026.json")
            gets = [h[1] for h in Govil.hits if h[0] == "GET"]
            check(not any("evil" in g or "x.pdf" in g for g in gets) and not ({"knesset_election98", "knesset_election99"} & set(found_in)),
                  f"[{mode}] a third party's address not of the filing form is never fetched")
            files = [os.path.join(dp, f) for dp, _, fs in os.walk(out) for f in fs]
            check(all(os.path.realpath(f).startswith(os.path.realpath(out) + os.sep) for f in files)
                  and os.path.exists(os.path.join(out, "summary.md")), f"[{mode}] everything under --out, summary.md written")
            if mode == "ok":
                # the builder reads what the fetcher wrote (these PDFs are stand-ins: no text, no crash)
                try:
                    d = B.build(os.path.join(ROOT, "site", "data", "polls_2026.json"),
                                os.path.join(ROOT, "pipeline", "reference", "poll_filings_index.json"), [out],
                                os.path.join(tmp, "f", "built.json"))
                    ok = d["counts"]["filings"] >= 109 and d["counts"]["verified"] == 0
                except Exception as exc:                  # noqa: BLE001 - reported as a failure
                    ok = f"{exc.__class__.__name__}: {exc}"
                check(ok is True, f"the builder reads the fetcher's directory ({ok})")
        if shutil.which("curl"):
            Govil.mode, Govil.hits = "ok", []
            out = os.path.join(tmp, "f", "curl")
            p = run_fetcher(out, base, ref, polls, curl=True)
            r7 = next((r for r in json.load(open(os.path.join(out, "filings.json"), encoding="utf-8"))
                       if r["item"] == "knesset_election7"), {})
            check(p.returncode == 0 and r7.get("saved") and r7.get("transport") == "curl",
                  f"a request urllib was refused (403) is asked again through curl and saved ({r7.get('transport')})")
        else:
            print("  skip no curl on this machine")
        Govil.mode, Govil.hits = "blocked", []
        out = os.path.join(tmp, "f", "blocked")
        p = run_fetcher(out, base, ref, polls)
        s = json.load(open(os.path.join(out, "summary.json"), encoding="utf-8"))
        check(p.returncode == 0 and s["listing"]["results"] == 0 and s["filings"]["items"] >= 5,
              "a refused listing: exit 0, the filings known from the indexes are still fetched")
        check(any("knesset_election201/he/Survey_4302.pdf" in u for u in s["probe_found"]),
              f"the probe finds the next item after the last known ({s['probe_found']})")
        probes = [h for h in Govil.hits if h[0] == "GET" and "probe" not in h[1] and "knesset_election20" in h[1]]
        check(len(probes) <= 15 * 16 + 2, f"the probe is bounded ({len(probes)} requests)")
        check("Listing:** 0 results" in open(os.path.join(out, "summary.md"), encoding="utf-8").read(),
              "summary.md says the listing gave nothing")
    finally:
        srv.shutdown()


def main():
    tmp = tempfile.mkdtemp(prefix="kalpi26-filings-")
    test_text()
    test_real()
    pdf_path = test_pdf(tmp)
    test_builder(tmp, pdf_path)
    test_fetcher(tmp)
    print(f"\n{len(failures)} failure(s); scratch in {tmp}")
    if not failures:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
