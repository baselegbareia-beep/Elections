"""The election-day turnout report of the Arab, Druze, Circassian and Bedouin localities, as a page to print (HTML)
and a PDF the dashboard offers for download (tools/html_to_pdf.js renders it).

Localities and their division: pipeline/reference/arab_report_localities.json (appendix 2 of the CEC directive 4.57,
as the CEC-sourced report of 27.10.2026 groups them; the mixed cities are shown apart and summed nowhere). Figures:
a per-station turnout file of the CEC (live_input/stations.csv, or the converted map or gov.il file with its update
time column). A locality's turnout is its reporting stations' voters over their eligible voters; a station with no
figure (blank, '-' or 0 voters) has not reported. "עודכן" is the latest update time among its stations.

    python3 pipeline/arab_report.py --stations FILE [--turnout live_input/turnout.json] --html OUT.html [--json OUT.json]
"""
import argparse
import base64
import csv
import hashlib
import html
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "pipeline", "reference", "arab_report_localities.json")
SITE = "https://baselegbareia-beep.github.io/Elections/"
COLS = {"code": ("סמל יישוב", "סמל ישוב", "קוד ישוב"), "elig": ('בז"ב', "בזב", "בעלי זכות בחירה"),
        "voters": ("מצביעים", "הצביעו", "מספר מצביעים"), "time": ("שעת עידכון", "שעת עדכון", "עודכן")}


def read_stations(data):
    """bytes of a per-station CSV -> {code: [(eligible, voters, 'HH:MM' or '')]} of the stations that reported."""
    text = None
    for enc in ("utf-8-sig", "cp1255"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not text or not text.strip():
        raise ValueError("the stations file is empty or neither UTF-8 nor cp1255")
    first = text.splitlines()[0]
    delim = max(",;\t|", key=first.count)          # the separators live_input/README.md allows
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    head = [h.strip() for h in rows[0]]
    at = {k: next((head.index(n) for n in names if n in head), None) for k, names in COLS.items()}
    if at["code"] is None or at["elig"] is None or at["voters"] is None:
        raise ValueError(f"no code, eligible or voters column in {head}")
    out = {}
    for r in rows[1:]:
        try:
            code, elig = int(float(r[at["code"]])), int(float(r[at["elig"]].replace(",", "")))
            voters = int(float(r[at["voters"]].replace(",", "") or 0))
        except (ValueError, IndexError):
            continue
        if voters <= 0 or elig <= 0 or voters > elig * 1.02:
            continue
        t = (r[at["time"]].strip()[:5] if at["time"] is not None and at["time"] < len(r) else "")
        out.setdefault(code, []).append((elig, voters, t if len(t) == 5 and t[2] == ":" else ""))
    return out


def build(stations, ref, national=None):
    """The report's figures: categories with their localities (sorted by turnout, no data last) and the totals."""
    cats, tot = [], {"voters": 0, "elig": 0, "with": 0, "n": 0, "updated": ""}
    for c in ref["categories"]:
        locs = []
        for l in c["localities"]:
            st = [s for code in l["codes"] for s in stations.get(code, [])]
            v, e = sum(s[1] for s in st), sum(s[0] for s in st)
            locs.append({"name": l["name"], "voters": v if st else None, "elig": e if st else None,
                         "pct": round(100 * v / e, 1) if e else None, "updated": max((s[2] for s in st), default="")})
        locs.sort(key=lambda x: (x["pct"] is None, -(x["pct"] or 0)))
        v, e = sum(x["voters"] or 0 for x in locs), sum(x["elig"] or 0 for x in locs)
        cat = {"name": c["name"], "counted": c.get("counted", True), "localities": locs, "voters": v, "elig": e,
               "pct": round(100 * v / e, 1) if e else None, "with": sum(x["pct"] is not None for x in locs), "n": len(locs)}
        cats.append(cat)
        upd = max((x["updated"] for x in locs), default="")
        tot["updated"] = max(tot["updated"], upd)
        if cat["counted"]:
            for k in ("voters", "elig", "with", "n"):
                tot[k] += cat[k]
    tot["pct"] = round(100 * tot["voters"] / tot["elig"], 1) if tot["elig"] else None
    return {"categories": cats, "total": tot, "national": national}


def fnum(x):
    return "—" if x is None else f"{x:,}"


def fpct(x):
    return "—" if x is None else f"{x:.1f}%"


FONTS = os.path.join(ROOT, "pipeline", "fonts")
HEB = "U+0307-0308,U+0590-05FF,U+200C-2010,U+20AA,U+25CC,U+FB1D-FB4F"
LAT = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,"
       "U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD")
# the group's colour: the site's --arab green, its --druze amber for the Druze groups, grey for the mixed cities
TONE = {"יישובים דרוזיים": "druze", "יישובים דרוזיים ברמת הגולן": "druze", "ערים מעורבות": "mixed"}


def font_faces():
    """@font-face rules with the site's fonts inline (pipeline/fonts), so the page needs no network."""
    out = []
    for fam, stem, weights in (("IBM Plex Sans Hebrew", "ibm-plex-sans-hebrew", (400, 500, 600, 700)),
                               ("Karantina", "karantina", (400, 700))):
        for w in weights:
            for sub, rng in (("hebrew", HEB), ("latin", LAT)):
                path = os.path.join(FONTS, f"{stem}-{sub}-{w}-normal.woff2")
                if os.path.exists(path):
                    b64 = base64.b64encode(open(path, "rb").read()).decode()
                    out.append(f'@font-face{{font-family:"{fam}";font-style:normal;font-weight:{w};font-display:block;'
                               f'src:url(data:font/woff2;base64,{b64}) format("woff2");unicode-range:{rng}}}')
    return "\n".join(out)


def gap_words(d, unit):
    """The distance from the national turnout in words: '4.7 נקודות מתחת לשיעור הארצי'."""
    if abs(d) < 0.05:
        return "כמו השיעור הארצי"
    return f'<span class="num">{abs(d):.1f}</span> {unit} ' + ("מעל השיעור הארצי" if d > 0 else "מתחת לשיעור הארצי")


def page(rep, date_he, as_of):
    """The report as one self-contained RTL page in the site's look (A4 width, as tall as its content)."""
    e = html.escape
    T, nat = rep["total"], rep["national"]
    npct = nat["pct"] if nat else None

    def bar(p):
        if p is None:
            return '<span class="bar"></span>'
        tick = f'<b style="inset-inline-start:{npct:.1f}%"></b>' if npct is not None else ""
        return f'<span class="bar"><i style="width:{min(100, p):.1f}%"></i>{tick}</span>'

    out = []
    for c in rep["categories"]:
        locs, k = c["localities"], -(-len(c["localities"]) // 3)
        cols = [locs[i:i + k] for i in range(0, len(locs), k)] if locs else []
        body = []
        for ci, col in enumerate(cols):
            rows = []
            for i, x in enumerate(col):
                none = x["pct"] is None
                rows.append(f'<tr class="{"none" if none else ""}"><td class="n">{ci * k + i + 1}</td><td class="nm">{e(x["name"])}</td>'
                            f'<td class="v">{fnum(x["voters"])}</td><td class="b">{bar(x["pct"])}</td>'
                            f'<td class="p">{fpct(x["pct"])}</td><td class="t">{x["updated"] or "—"}</td></tr>')
            body.append('<table><thead><tr><th></th><th class="nm">יישוב</th><th class="v">מצביעים</th><th class="b"></th>'
                        '<th class="p">הצבעה</th><th class="t">עודכן</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")
        tone = TONE.get(c["name"], "arab")
        apart = '<span class="chip">לא נכלל בסיכום</span>' if not c["counted"] else ""
        gap = ""
        if c["pct"] is not None and npct is not None:
            d = c["pct"] - npct
            gap = f'<span class="gap">{gap_words(d, "נק׳")}</span>'
        out.append(f'<section class="card {tone}{"" if c["counted"] else " apart"}"><div class="ch">'
                   f'<div class="ct"><h3>{e(c["name"])}</h3>{apart}<p><span class="num">{c["with"]}/{c["n"]}</span> יישובים עם נתונים · '
                   f'<span class="num">{fnum(c["voters"])}</span> מצביעים</p></div>'
                   f'<div class="cv"><span class="big num">{fpct(c["pct"])}</span>{gap}</div></div>'
                   f'<div class="cols">{"".join(body)}</div></section>')
    nat_tile = (f'<div class="tile"><span class="l">שיעור ההצבעה הארצי</span><span class="v num">{fpct(npct)}</span>'
                f'<span class="d">נכון ל-<span class="num">{e(nat["hour"])}</span>, לפי ועדת הבחירות</span></div>') if nat else ""
    gap_all = ""
    if T["pct"] is not None and npct is not None:
        d = T["pct"] - npct
        gap_all = f'<span class="d">{gap_words(d, "נקודות")}</span>'
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<title>קלפי 26 · אחוזי הצבעה ביישובים הערביים, הדרוזיים והצ'רקסיים · {e(date_he)} {e(as_of)}</title>
<style>
{font_faces()}
:root {{ --bg:#f2f4f7; --surface:#fff; --surface-2:#f7f8fa; --ink:#0c1320; --ink-2:#3f4a5c; --muted:#6b7587; --rule:#dfe4eb;
  --rule-strong:#c4ccd8; --marker:#ffd400; --grid:#e9edf2; --arab:#1baf7a; --arab-strong:#0b7a55; --druze:#eda100;
  --druze-strong:#9a6400; --crit:#d03b3b; --r:10px;
  --font-display:"Karantina","Arial Hebrew",sans-serif; --font-ui:"IBM Plex Sans Hebrew","Arial Hebrew","DejaVu Sans",sans-serif; }}
* {{ box-sizing:border-box; }}
html, body {{ margin:0; background:var(--bg); color:var(--ink); font-family:var(--font-ui); }}
body {{ width:794px; padding:26px 22px 20px; font-size:10.5px; line-height:1.35; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
.num {{ font-variant-numeric:tabular-nums; direction:ltr; unicode-bidi:isolate; display:inline-block; }}
.mast {{ display:flex; align-items:flex-end; justify-content:space-between; gap:16px; padding-bottom:14px; border-bottom:1px solid var(--rule-strong); }}
.brand {{ display:flex; align-items:baseline; gap:12px; }}
.brand .logo {{ font:700 48px/.8 var(--font-display); letter-spacing:.5px; }}
.brand .logo .k {{ background:var(--marker); padding:0 .12em; border-radius:3px; }}
.brand h1 {{ margin:0; font-size:17px; font-weight:600; line-height:1.25; }}
.brand .sub {{ color:var(--ink-2); font-size:11px; margin-top:3px; }}
.when {{ text-align:end; white-space:nowrap; }}
.chip-live {{ display:inline-flex; align-items:center; gap:6px; background:var(--crit); color:#fff; font-weight:700; font-size:10.5px; padding:4px 10px; border-radius:99px; }}
.chip-live::before {{ content:''; width:7px; height:7px; border-radius:50%; background:#fff; }}
.when .t {{ font:700 40px/.9 var(--font-display); display:block; margin-top:6px; }}
.when .dt {{ color:var(--muted); font-size:10.5px; }}
.tiles {{ display:grid; grid-template-columns:1.25fr 1fr 1fr 1fr 1fr; gap:10px; margin:16px 0 14px; }}
.tile {{ background:var(--surface); border:1px solid var(--rule); border-radius:var(--r); padding:11px 13px 10px; display:flex; flex-direction:column; gap:3px; }}
.tile .v {{ font:700 38px/.9 var(--font-display); }}
.tile .l {{ font-size:10.5px; color:var(--ink-2); font-weight:500; }}
.tile .d {{ font-size:9.5px; color:var(--muted); }}
.tile.hero {{ background:var(--arab-strong); border-color:var(--arab-strong); color:#fff; }}
.tile.hero .l, .tile.hero .d {{ color:#d9f3e8; }}
.card {{ background:var(--surface); border:1px solid var(--rule); border-radius:var(--r); padding:12px 14px 8px; margin-top:10px; break-inside:avoid;
  border-top:4px solid var(--tone); --tone:var(--arab); --tone-ink:var(--arab-strong); }}
.card.druze {{ --tone:var(--druze); --tone-ink:var(--druze-strong); }}
.card.mixed {{ --tone:var(--rule-strong); --tone-ink:var(--ink-2); }}
.card.apart {{ background:var(--surface-2); border-style:dashed; border-top-style:solid; }}
.ch {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:6px; }}
.ct h3 {{ display:inline; margin:0; font-size:14.5px; font-weight:600; }}
.ct p {{ margin:2px 0 0; color:var(--muted); font-size:10px; }}
.chip {{ display:inline-block; margin-inline-start:8px; padding:1px 8px; border-radius:99px; border:1px dashed var(--rule-strong); color:var(--ink-2); font-size:9.5px; font-weight:600; vertical-align:2px; }}
.cv {{ text-align:end; white-space:nowrap; }}
.cv .big {{ font:700 32px/.85 var(--font-display); color:var(--tone-ink); }}
.cv .gap {{ display:block; font-size:9.5px; color:var(--muted); margin-top:3px; }}
.cols {{ display:grid; grid-template-columns:repeat(3,1fr); gap:0 14px; }}
table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; table-layout:fixed; }}
col, th, td {{ overflow:hidden; }}
th {{ font-weight:500; color:var(--muted); font-size:8.5px; text-align:start; padding:2px 2px 3px; border-bottom:1px solid var(--rule-strong); }}
td {{ padding:3.2px 2px; border-bottom:1px solid var(--grid); vertical-align:middle; }}
th:first-child, td.n {{ width:15px; }} td.n {{ color:var(--muted); font-size:8px; }}
td.nm {{ font-weight:600; font-size:10px; line-height:1.2; }} th.nm {{ width:auto; }}
th.v, td.v {{ width:40px; text-align:end; }} td.v {{ color:var(--ink-2); }}
th.b, td.b {{ width:38px; padding-inline:5px 3px; }}
th.p, td.p {{ width:37px; text-align:end; }} td.p {{ font-weight:700; }}
th.t, td.t {{ width:29px; text-align:end; }} td.t {{ color:var(--muted); font-size:8.5px; }}
tr.none td.nm {{ color:var(--muted); font-weight:500; }}
.bar {{ position:relative; display:block; height:6px; background:var(--grid); border-radius:3px; }}
.bar i {{ position:absolute; inset-block:0; inset-inline-start:0; background:var(--tone); border-radius:3px; }}
.bar b {{ position:absolute; top:-2px; bottom:-2px; width:1.5px; margin-inline-start:-.75px; background:var(--ink); opacity:.55; }}
.key {{ display:flex; gap:16px; flex-wrap:wrap; align-items:center; color:var(--ink-2); font-size:9.5px; margin:4px 2px 0; }}
.key .bar {{ display:inline-block; width:38px; vertical-align:middle; margin-inline-end:5px; --tone:var(--arab); }}
footer {{ margin-top:14px; padding-top:10px; border-top:1px solid var(--rule-strong); color:var(--muted); font-size:9px; line-height:1.55; display:flex; justify-content:space-between; gap:18px; }}
footer .src {{ max-width:600px; }}
footer .logo {{ font:700 22px/.9 var(--font-display); color:var(--ink); white-space:nowrap; }}
footer .logo .k {{ background:var(--marker); padding:0 .12em; border-radius:2px; }}
.ltr {{ direction:ltr; unicode-bidi:isolate; }}
</style></head><body>
<header class="mast"><div class="brand"><div class="logo">קלפי <span class="k">26</span></div>
<div><h1>אחוזי הצבעה ביישובים הערביים, הדרוזיים והצ'רקסיים</h1>
<div class="sub">יום הבחירות לכנסת ה-26 · כל יישוב לפי חלוקת ועדת הבחירות · מקור הנתונים: ועדת הבחירות המרכזית</div></div></div>
<div class="when"><span class="chip-live">עדכון אחרון</span><span class="t num">{e(as_of)}</span><span class="dt">{e(date_he)}</span></div></header>
<div class="tiles">
<div class="tile hero"><span class="l">שיעור ההצבעה ביישובים שברשימה</span><span class="v num">{fpct(T["pct"])}</span>{gap_all or '<span class="d">ללא הערים המעורבות</span>'}</div>
{nat_tile}
<div class="tile"><span class="l">מצביעים</span><span class="v num">{fnum(T["voters"])}</span><span class="d">בקלפיות שדיווחו</span></div>
<div class="tile"><span class="l">בעלי זכות בחירה</span><span class="v num">{fnum(T["elig"])}</span><span class="d">בקלפיות שדיווחו</span></div>
<div class="tile"><span class="l">יישובים עם נתונים</span><span class="v num">{T["with"]}/{T["n"]}</span><span class="d">ללא הערים המעורבות</span></div>
</div>
<div class="key"><span><span class="bar"><i style="width:62%"></i><b style="inset-inline-start:{npct or 0:.1f}%"></b></span>שיעור ההצבעה ביישוב; הקו הדק: השיעור הארצי{f' ({fpct(npct)})' if npct is not None else ''}</span>
<span>הקבוצות לפי נספח 2 להוראת מנכ"ל 4.57 של ועדת הבחירות; בכל קבוצה היישובים מהשיעור הגבוה לנמוך</span></div>
{"".join(out)}
<footer><div class="src">"עודכן": שעת העדכון האחרונה של קלפי ביישוב. מצביעים ובעלי זכות בחירה: בקלפיות שכבר דיווחו, ושיעור ההצבעה הוא היחס ביניהם. הערים המעורבות מוצגות בנפרד ואינן נכללות באף סיכום. הנתונים לפי קלפי אינם כוללים מצביעים במעטפות חיצוניות (חיילים, נציגויות, בתי חולים).<br>
מקור: ועדת הבחירות המרכזית (מפת אחוזי ההצבעה וקבצי שיעור ההצבעה בקלפיות). <span class="ltr">{SITE}</span></div>
<div class="logo">קלפי <span class="k">26</span></div></footer>
</body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stations", required=True)
    ap.add_argument("--turnout", default=os.path.join(ROOT, "live_input", "turnout.json"))
    ap.add_argument("--html", required=True)
    ap.add_argument("--json")
    ap.add_argument("--date", default="27.10.2026")
    ap.add_argument("--as-of", help="HH:MM of the data when the stations file has no update-time column "
                    "(default: sectors_time in --turnout)")
    a = ap.parse_args(argv)
    ref = json.load(open(REF, encoding="utf-8"))
    stations = read_stations(open(a.stations, "rb").read())
    nat = None
    try:
        t = json.load(open(a.turnout, encoding="utf-8"))
    except (OSError, ValueError):
        t = {}
    hours = sorted((k, v) for k, v in (t.get("national") or {}).items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool) and len(k) == 5 and k[2] == ":")
    rep = build(stations, ref)
    # the data's own time: the latest station update; without that column, the release's time, never the clock
    as_of = rep["total"]["updated"] or a.as_of or str(t.get("sectors_time") or "")[:5]
    if not (len(as_of) == 5 and as_of[2] == ":"):
        print("no time for the data: the stations file has no update-time column; pass --as-of HH:MM", file=sys.stderr)
        return 1
    # the national figure of the stations' hour (the latest even hour up to the last station update), like with like
    same = [h for h in hours if h[0] <= as_of] or hours[:1]
    if same:
        nat = rep["national"] = {"hour": same[-1][0], "pct": float(same[-1][1])}
    doc = page(rep, a.date, as_of)
    open(a.html, "w", encoding="utf-8").write(doc)
    if a.json:   # version: the page's content, so a rebuild with the same time still reaches the readers' caches
        json.dump({"as_of": as_of, "date": a.date, "version": hashlib.sha256(doc.encode()).hexdigest()[:12],
                   "total": rep["total"], "national": nat,
                   "categories": [{k: c[k] for k in ("name", "counted", "pct", "voters", "elig", "with", "n")} for c in rep["categories"]]},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"as_of": as_of, "pct": rep["total"]["pct"], "voters": rep["total"]["voters"],
                      "with": f'{rep["total"]["with"]}/{rep["total"]["n"]}'}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
