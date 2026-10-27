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
import csv
import datetime as dt
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
    for enc in ("utf-8-sig", "cp1255"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.reader(io.StringIO(text)))
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


def page(rep, date_he, as_of):
    """The report as one self-contained RTL page (A4 width, as tall as its content)."""
    e = html.escape
    T, nat = rep["total"], rep["national"]
    out = []
    for c in rep["categories"]:
        locs, k = c["localities"], -(-len(c["localities"]) // 3)
        cols = [locs[i:i + k] for i in range(0, len(locs), k)] if locs else []
        body = []
        for ci, col in enumerate(cols):
            rows = []
            for i, x in enumerate(col):
                n = ci * k + i + 1
                bar = f'<i style="width:{min(100, x["pct"] or 0):.0f}%"></i>' if x["pct"] is not None else ""
                rows.append(f'<tr><td class="n">{n}</td><td class="nm">{e(x["name"])}</td><td class="v">{fnum(x["voters"])}</td>'
                            f'<td class="bar"><span>{bar}</span></td><td class="p">{fpct(x["pct"])}</td><td class="t">{x["updated"] or "—"}</td></tr>')
            body.append('<table><thead><tr><th></th><th class="nm">יישוב</th><th class="v">מצביעים</th><th></th>'
                        '<th class="p">אחוז</th><th class="t">עודכן</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")
        note = '<span class="apart">לא נכלל בסיכום</span>' if not c["counted"] else ""
        out.append(f'<section><h2><span class="h">{e(c["name"])}</span>{note}<span class="sum"><b>{fpct(c["pct"])}</b>'
                   f'<span class="ltr">{c["with"]}/{c["n"]}</span> יישובים · {fnum(c["voters"])} מצביעים</span></h2><div class="cols">{"".join(body)}</div></section>')
    natline = (f'אחוז הצבעה ארצי: <b>{fpct(nat["pct"]) if nat else "—"}</b>'
               + (f' <small>(נכון ל-{e(nat["hour"])})</small>' if nat and nat.get("hour") else "")
               + f' · ביישובים שברשימה (ללא ערים מעורבות): <b>{fpct(T["pct"])}</b>')
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<title>אחוזי הצבעה ביישובים הערביים, הדרוזיים והצ'רקסיים · {e(date_he)} {e(as_of)}</title>
<style>
:root {{ --ink:#0c1320; --ink2:#4a5568; --rule:#d9dee7; --soft:#eef2f8; --accent:#1f5fd1; --hot:#d4501c; }}
* {{ box-sizing:border-box; }}
html, body {{ margin:0; background:#fff; color:var(--ink); font-family:"Heebo","Assistant","Arial Hebrew","DejaVu Sans","Liberation Sans",Arial,sans-serif; }}
body {{ width:794px; padding:22px 20px 18px; font-size:10.5px; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
header {{ display:flex; gap:16px; align-items:flex-start; justify-content:space-between; }}
h1 {{ margin:0 0 3px; font-size:19px; }}
.src {{ color:var(--ink2); font-size:11px; margin-bottom:8px; }}
.nat {{ display:inline-block; max-width:560px; background:var(--ink); color:#fff; border-radius:6px; padding:6px 10px; font-size:12px; }}
.nat b {{ color:#ffd166; font-size:14px; }} .nat small {{ color:#c7cfdb; }}
.stamp {{ background:var(--hot); color:#fff; border-radius:8px; padding:7px 14px 8px; text-align:center; min-width:120px; }}
.stamp small {{ display:block; font-size:10px; opacity:.9; }} .stamp b {{ display:block; font-size:30px; line-height:1.05; font-variant-numeric:tabular-nums; }}
.brand {{ font-size:10px; color:var(--ink2); text-align:center; margin-top:4px; }} .ltr {{ direction:ltr; unicode-bidi:isolate; }}
.tiles {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:14px 0 6px; }}
.tile {{ background:var(--soft); border-radius:8px; padding:9px 12px; }}
.tile b {{ display:block; font-size:20px; color:var(--accent); font-variant-numeric:tabular-nums; }} .tile span {{ color:var(--ink2); font-size:10.5px; }}
section {{ margin-top:12px; break-inside:avoid; }}
h2 {{ display:flex; align-items:baseline; gap:10px; margin:0 0 4px; padding-bottom:4px; border-bottom:2px solid var(--accent); font-size:15px; }}
h2 .h {{ flex:1; }} h2 .apart {{ font-size:10px; font-weight:400; color:var(--ink2); }}
h2 .sum {{ font-size:10px; font-weight:400; color:var(--ink2); }} h2 .sum b {{ font-size:16px; color:var(--accent); margin-inline-end:6px; }}
.cols {{ display:grid; grid-template-columns:repeat(3,1fr); gap:0 12px; }}
table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }}
th {{ font-weight:500; color:var(--ink2); font-size:9px; text-align:start; padding:3px 2px; border-bottom:1px solid var(--rule); }}
td {{ padding:3.5px 2px; border-bottom:1px solid var(--rule); vertical-align:middle; }}
td.n {{ color:#9aa3b2; font-size:8.5px; width:14px; }} td.nm {{ font-weight:600; }}
td.v, th.v {{ text-align:end; }} td.p {{ font-weight:700; text-align:end; }} td.t, th.t {{ color:var(--ink2); font-size:9px; text-align:end; }}
td.bar {{ width:34px; }} td.bar span {{ display:block; height:5px; background:var(--soft); border-radius:3px; overflow:hidden; }}
td.bar i {{ display:block; height:100%; background:var(--accent); border-radius:3px; }}
footer {{ margin-top:14px; color:var(--ink2); font-size:9.5px; line-height:1.5; }}
</style></head><body>
<header><div><h1>אחוזי הצבעה ביישובים הערביים, הדרוזיים והצ'רקסיים</h1>
<div class="src">מקור הנתונים: ועדת הבחירות המרכזית · עיבוד: קלפי 26</div><div class="nat">{natline}</div></div>
<div><div class="stamp"><small>עדכון אחרון</small><b>{e(as_of)}</b><small>{e(date_he)}</small></div><div class="brand">קלפי 26</div></div></header>
<div class="tiles"><div class="tile"><b>{fpct(T["pct"])}</b><span>אחוז הצבעה (ללא ערים מעורבות)</span></div>
<div class="tile"><b>{fnum(T["voters"])}</b><span>מצביעים</span></div>
<div class="tile"><b>{fnum(T["elig"])}</b><span>בעלי זכות בקלפיות שדיווחו</span></div>
<div class="tile"><b class="ltr">{T["with"]}/{T["n"]}</b><span>יישובים עם נתונים</span></div></div>
{"".join(out)}
<footer>"עודכן": שעת העדכון האחרונה של קלפי ביישוב. מצביעים ובעלי זכות: בקלפיות שכבר דיווחו; אחוז ההצבעה הוא המצביעים בהן חלקי בעלי הזכות בהן.
הערים המעורבות מוצגות בנפרד ואינן נכללות באף סיכום. הנתונים לפי קלפי אינם כוללים מצביעים במעטפות חיצוניות (חיילים, נציגויות, בתי חולים).<br>
מקור: ועדת הבחירות המרכזית (מפת אחוזי ההצבעה mapvotes.bechirot.gov.il וקבצי שיעור ההצבעה בקלפיות ב-gov.il) · רשימת היישובים: נספח 2 להוראת מנכ"ל 4.57 · קלפי 26: <span class="ltr">{SITE}</span></footer>
</body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stations", required=True)
    ap.add_argument("--turnout", default=os.path.join(ROOT, "live_input", "turnout.json"))
    ap.add_argument("--html", required=True)
    ap.add_argument("--json")
    ap.add_argument("--date", default="27.10.2026")
    a = ap.parse_args(argv)
    ref = json.load(open(REF, encoding="utf-8"))
    stations = read_stations(open(a.stations, "rb").read())
    nat = None
    try:
        t = json.load(open(a.turnout, encoding="utf-8"))
        hours = sorted((t.get("national") or {}).items())
    except (OSError, ValueError):
        hours = []
    rep = build(stations, ref)
    as_of = rep["total"]["updated"] or dt.datetime.now(dt.timezone(dt.timedelta(hours=2))).strftime("%H:%M")
    # the national figure of the stations' hour (the latest even hour up to the last station update), like with like
    same = [h for h in hours if h[0] <= as_of] or hours[:1]
    if same:
        nat = rep["national"] = {"hour": same[-1][0], "pct": float(same[-1][1])}
    open(a.html, "w", encoding="utf-8").write(page(rep, a.date, as_of))
    if a.json:
        json.dump({"as_of": as_of, "date": a.date, "total": rep["total"], "national": nat,
                   "categories": [{k: c[k] for k in ("name", "counted", "pct", "voters", "elig", "with", "n")} for c in rep["categories"]]},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"as_of": as_of, "pct": rep["total"]["pct"], "voters": rep["total"]["voters"],
                      "with": f'{rep["total"]["with"]}/{rep["total"]["n"]}'}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
