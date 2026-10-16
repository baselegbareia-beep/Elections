"""Static locality pages at permanent addresses, for sharing and search engines.

Reads site/data/core.json (official CEC counts per locality, built by build_data.py) and writes:
  site/l/<code>/index.html   one page per locality (its CBS code): five elections, turnout, the leading lists
  site/l/index.html          every locality, A to ת, with a small filter
  site/l/l.css               the shared stylesheet: site/src/styles.css (the dashboard's tokens, fonts, light and
                             dark) plus the few rules these pages add
  site/sitemap.xml           the dashboard, the index and every locality page
  site/robots.txt, robots.txt, sitemap.xml (repository root: GitHub Pages in branch mode serves the root, and the
                             root sitemap is an index pointing to site/sitemap.xml)

Nothing in the output depends on the clock, so a rebuild from the same core.json changes no file. The pages carry
no script except the index's filter. District (מחוז) is shown when pipeline/reference/cbs_districts.json exists
({"<code>": {"district": "...", "subdistrict": "..."}, "source": "https://..."}); the CBS / data.gov.il locality
list is reachable only from GitHub's runners (pipeline/fetchers/cbs_localities.py).

Run: python3 pipeline/build_pages.py [--base https://.../site/]
"""
import argparse
import html
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
BASE = "https://baselegbareia-beep.github.io/Elections/site/"   # GitHub Pages, branch mode: main / (root)
OG_LOCALITY = "og/locality.png"   # pipeline/build_og.py
DISTRICTS = os.path.join(ROOT, "pipeline", "reference", "cbs_districts.json")
TRIBES_NOTE = "במפה שבדשבורד שבטי הנגב מוצגים יחד, כעיגול אחד."

SECTOR = {   # the dashboard's own labels (results.js, drawLocality)
    "arab": ("ערבי", "arab"), "jewish": ("יהודי", ""), "druze": ("דרוזי/צ׳רקסי", ""), "mixed": ("עיר מעורבת", ""),
}
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Hebrew:wght@400;500;600;700'
         '&family=Karantina:wght@400;700&display=swap">')

PAGE_CSS = """
/* ---------- locality pages (pipeline/build_pages.py) ---------- */
.lp-mast .wrap { display: flex; align-items: center; justify-content: space-between; gap: 8px 18px; flex-wrap: wrap; padding-block: 12px; }
.lp-brand { font: 700 40px/.85 var(--font-display); text-decoration: none; letter-spacing: .5px; white-space: nowrap; }
.lp-brand .k { background: var(--marker); color: var(--marker-ink); padding: 0 .12em; border-radius: 3px; }
.lp-crumbs { font-size: var(--t-sm); color: var(--muted); min-width: 0; overflow-wrap: anywhere; }
.lp-crumbs a { color: var(--ink-2); }
main.lp { padding-block: 22px 56px; }
.lp h1 { font: 700 var(--t-3xl)/.95 var(--font-display); margin: 2px 0 0; overflow-wrap: anywhere; }
.lp-lede { color: var(--ink-2); max-width: 72ch; margin: 10px 0 0; text-wrap: pretty; }
.lp .card { margin-top: 18px; }
.lp h2 { font-size: var(--t-lg); font-weight: 600; margin: 0 0 2px; text-wrap: balance; }
.lp-els { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr)); gap: 18px; margin-top: 18px; }
.lp-els .card { margin: 0; }
.lp-bars { list-style: none; margin: 10px 0 0; padding: 0; }
.lp-bars li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 3px 10px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--rule); font-size: var(--t-sm); }
.lp-bars li:last-child { border-bottom: 0; }
.lp-bars span { min-width: 0; overflow-wrap: anywhere; }
.lp-bars i { font: normal 700 15px/1 var(--font-display); color: var(--muted); margin-inline-start: 6px; letter-spacing: .4px; }
.lp-bars b, .lp-bars u { font-weight: 600; text-decoration: none; font-variant-numeric: tabular-nums; direction: ltr; unicode-bidi: isolate; white-space: nowrap; }
.lp-bars u { font-weight: 400; color: var(--muted); font-size: var(--t-xs); min-width: 6ch; text-align: end; }
.lp-bars s { grid-column: 1 / -1; height: 6px; border-radius: 3px; text-decoration: none; background: linear-gradient(to left, var(--c, var(--muted)) var(--w), var(--grid) 0); }
.lp-dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; background: var(--c, var(--muted)); margin-inline-end: 7px; vertical-align: 0; flex: none; }
.lp-cta { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; margin-top: 22px; }
.lp-btn { display: inline-block; background: var(--ink); color: var(--surface); border-radius: 8px; padding: 9px 16px; font-weight: 600; text-decoration: none; }
.lp-btn:hover { background: var(--ink-2); }
.lp-cta p { margin: 0; color: var(--muted); font-size: var(--t-sm); }
table.t td.lp-lead, table.t td.lp-e { white-space: nowrap; }
.lp-s { display: none; }
@media (max-width: 560px) {   /* phones: the turnout table drops its count columns, election names go short ('4/19') */
  .lp-w, .lp-l { display: none; }
  .lp-s { display: inline; }
}
.lp-index { columns: 4 190px; column-gap: 28px; }
.lp-index section { margin: 0 0 14px; }
.lp-index h2 { font: 700 var(--t-xl)/1 var(--font-display); margin: 0 0 4px; color: var(--muted); break-after: avoid; }
.lp-index ul { list-style: none; margin: 0; padding: 0; }
.lp-index li { padding: 2px 0; font-size: var(--t-sm); }
.lp-filter { margin: 14px 0 18px; }
.lp-filter input[type="search"] { width: 280px; }
"""


def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    return f"{round(n):,}"


def pct(x, d=1):
    return f"{x:.{d}f}%"


def num(s):
    return f'<span class="num">{s}</span>'


def signed_pp(x):
    if round(x, 1) == 0:
        return num("0.0")
    return num(("+" if x > 0 else "−") + f"{abs(x):.1f}")


COUNT_F = {2: "שתי", 3: "שלוש", 4: "ארבע", 5: "חמש", 6: "שש", 7: "שבע", 8: "שמונה", 9: "תשע", 10: "עשר"}


def count_f(n):   # "חמש" (מערכות): the number word for a feminine noun
    return COUNT_F.get(n, str(n))


def fam_class(key):
    return "f-" + re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")


class Core:
    def __init__(self, core):
        self.core = core
        self.els = [e["id"] for e in core["elections"]]
        self.E = {e["id"]: e for e in core["elections"]}
        self.parties = {e["id"]: {p["id"]: p for p in e["parties"]} for e in core["elections"]}
        self.cols = core["party_cols"]

    def votes(self, loc, eid):
        row = loc["el"].get(eid)
        if not row:
            return None
        boxes, elig, voters, valid, arab_boxes, *v = row
        return {"boxes": boxes, "elig": elig, "voters": voters, "valid": valid, "arab_boxes": arab_boxes,
                "votes": dict(zip(self.cols[eid], v))}

    def name(self, eid, letter):
        if letter == "other":
            return "אחרות"
        p = self.parties[eid].get(letter)
        return p["name"] if p else letter

    def family(self, eid, letter):
        if letter == "other":
            return "other"
        p = self.parties[eid].get(letter)
        return p["family"] if p else "other"

    def ran(self, eid, fam):
        return any(p["family"] == fam for p in self.E[eid]["parties"])

    def label(self, eid):   # "הכנסת ה-25" -> "לכנסת ה-25"
        return "ל" + self.E[eid]["label"][1:] if self.E[eid]["label"].startswith("ה") else self.E[eid]["label"]

    def compact(self, eid):   # '2019-04-09' -> '4/19': the dashboard's narrow-screen label (core.js COMPACT)
        y, m, _ = self.E[eid]["date"].split("-")
        return f"{int(m)}/{y[2:]}"

    def years(self):   # titles: "2019–2022"
        y = [self.E[e]["date"][:4] for e in self.els]
        return f"{y[0]}–{y[-1]}" if y[0] != y[-1] else y[0]

    def span(self):    # running text: "מ-2019 עד 2022" (a range in Hebrew text reads right to left)
        y = [self.E[e]["date"][:4] for e in self.els]
        return f"מ-{y[0]} עד {y[-1]}" if y[0] != y[-1] else f"ב-{y[0]}"


def ranked(C, v, eid):
    """Lists by votes in the locality, minor lists ('other') left out of the ranking."""
    return sorted(((k, n) for k, n in v["votes"].items() if k != "other" and n > 0), key=lambda kn: (-kn[1], kn[0]))


def fam_shares(C, v, eid):
    out = {}
    for k, n in v["votes"].items():
        f = C.family(eid, k)
        out[f] = out.get(f, 0) + n / v["valid"]
    return out


def locality_page(C, loc, base, districts):
    code, name = loc["code"], loc["name"]
    url = f"{base}l/{code}/"
    rows = {e: C.votes(loc, e) for e in C.els}
    rows = {e: v for e, v in rows.items() if v and v["valid"]}
    have = [e for e in C.els if e in rows]
    last = have[-1] if have else None
    sec = SECTOR.get(loc["sector"], ("", ""))
    region = None
    if loc.get("region") and loc["sector"] != "mixed":
        region = C.core["arab_regions"].get(loc["region"]) or C.core["druze_regions"].get(loc["region"])
    dist = districts.get(str(code)) if districts else None
    first_short, last_short = C.E[C.els[0]]["short"], C.E[C.els[-1]]["short"]

    # ---- head
    desc = f"{name}: תוצאות רשמיות של {count_f(len(C.els))} מערכות הבחירות לכנסת, {C.span()}, לפי קובצי הקלפיות של ועדת הבחירות המרכזית."
    if last:
        v = rows[last]
        top = ranked(C, v, last)
        lead = f", הרשימה המובילה: {C.name(last, top[0][0])} ({pct(100 * top[0][1] / v['valid'])})" if top else ""
        desc += f" ב{C.E[last]['short']}: שיעור הצבעה {pct(100 * v['voters'] / v['elig'])}{lead}."
    title = f"{name}: תוצאות הבחירות לכנסת {C.years()} | קלפי 26"
    og_title = f"{name}: תוצאות הבחירות לכנסת {C.years()}"
    img = base + OG_LOCALITY
    head = f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
{social(og_title, desc, url, img, "קלפי 26: דפי יישוב, תוצאות הבחירות לכל יישוב")}
{FONTS}
<link rel="stylesheet" href="../l.css">
</head>"""

    # ---- chips and tiles
    chips = [f'<span class="{"badge " + sec[1] if sec[1] else "badge"}">{esc(sec[0])}</span>'] if sec[0] else []
    if region:
        chips.append(f'<span class="badge">{esc(region)}</span>')
    if dist and dist.get("district"):
        chips.append(f'<span class="badge" title="מחוז לפי הלמ״ס">מחוז {esc(dist["district"])}</span>')
    chips.append('<span class="badge off" title="תוצאות לפי קובצי הקלפיות של ועדת הבחירות המרכזית">תוצאות רשמיות</span>')
    if loc.get("ses"):
        chips.append(f'<span class="badge est" title="מקור משני: מדד חברתי-כלכלי של הלמ״ס">אשכול חברתי-כלכלי {loc["ses"]} מתוך 10 (למ״ס)</span>')
    chips.append(f'<span class="badge" title="סמל היישוב של הלמ״ס, כפי שהוא מופיע בקובצי הוועדה">סמל יישוב {num(code)}</span>')

    tiles = ""
    if last:
        v = rows[last]
        top = ranked(C, v, last)
        w = top[0] if top else None
        arab_b = f" ({fmt(v['arab_boxes'])} ערביות)" if v["arab_boxes"] and loc["sector"] == "mixed" else ""
        tiles = f"""<div class="kv">
<div><b class="num">{fmt(v['elig'])}</b><span>בעלי זכות · {esc(C.E[last]['short'])}</span></div>
<div><b class="num">{pct(100 * v['voters'] / v['elig'])}</b><span>שיעור הצבעה</span></div>
<div><b class="num">{fmt(v['boxes'])}</b><span>קלפיות{arab_b}</span></div>
<div><b>{esc(C.name(last, w[0])) if w else '—'}</b><span>מובילה{', ' + num(pct(100 * w[1] / v['valid'])) if w else ''}</span></div>
</div>"""

    lede = (f"תוצאות הבחירות לכנסת ב{esc(name)} ב{count_f(len(C.els))} מערכות הבחירות האחרונות, מ{esc(first_short)} עד {esc(last_short)}: "
            "ספירות רשמיות של ועדת הבחירות המרכזית מקובצי התוצאות לפי קלפי, מסוכמות לכל קלפיות היישוב.")
    if loc.get("tribe"):
        lede += " " + TRIBES_NOTE

    # ---- five elections: turnout table
    trs, prev = [], None
    for e in C.els:
        v = rows.get(e)
        if not v:
            # the same cells as a full row (the phone layout hides the same columns), the reason in the last one
            trs.append(f'<tr><td class="lp-e">{esc(C.E[e]["short"])}</td><td class="n lp-w">—</td><td class="n lp-w">—</td>'
                       '<td class="n">—</td><td class="n">—</td><td class="n lp-w">—</td><td>אין קלפיות ליישוב</td></tr>')
            prev = None
            continue
        t = 100 * v["voters"] / v["elig"]
        d = signed_pp(t - prev) if prev is not None else "—"
        top = ranked(C, v, e)
        lead = f'{esc(C.name(e, top[0][0]))} {num(pct(100 * top[0][1] / v["valid"]))}' if top else "—"
        trs.append(f'<tr><td class="lp-e">{esc(C.E[e]["short"])}</td><td class="n lp-w">{fmt(v["elig"])}</td><td class="n lp-w">{fmt(v["voters"])}</td>'
                   f'<td class="n"><b>{pct(t)}</b></td><td class="n">{d}</td><td class="n lp-w">{fmt(v["boxes"])}</td><td class="lp-lead">{lead}</td></tr>')
        prev = t
    turnout = f"""<section class="card">
<h2>שיעור ההצבעה ב{count_f(len(C.els))} מערכות בחירות</h2>
<p class="sub">המצביעים בקלפיות היישוב מתוך בעלי הזכות הרשומים בהן. השינוי בנקודות אחוז לעומת הבחירות הקודמות.</p>
<div class="tbl-wrap"><table class="t">
<thead><tr><th>בחירות</th><th class="n lp-w">בעלי זכות</th><th class="n lp-w">הצביעו</th><th class="n">שיעור הצבעה</th><th class="n">שינוי (נק׳)</th><th class="n lp-w">קלפיות</th><th>הרשימה המובילה</th></tr></thead>
<tbody>{''.join(trs)}</tbody>
</table></div>
<p class="foot">מי שהצביע במעטפה כפולה (חיילים, אנשי סגל ועוד) נספר בשורת המעטפות הארצית של הוועדה ולא ביישוב, ולכן שיעור ההצבעה ביישוב אינו כולל אותם.</p>
</section>"""

    # ---- by political family, across the elections
    shares = {e: fam_shares(C, rows[e], e) for e in have}
    fams = {f for e in have for f, s in shares[e].items() if s >= 0.08 and f != "other"}
    fam_list = sorted(fams, key=lambda f: (-max(shares[e].get(f, 0) for e in have), f))[:6]
    fam_rows = []
    if loc["sector"] != "jewish":
        cells = []
        for e in C.els:
            if e not in rows:
                cells.append('<td class="n">—</td>')
                continue
            v = rows[e]
            a = sum(n for k, n in v["votes"].items() if k != "other" and C.parties[e].get(k, {}).get("bloc") == "arab")
            cells.append(f'<td class="n">{pct(100 * a / v["valid"])}</td>')
        fam_rows.append(f'<tr><td><b>כל הרשימות הערביות</b></td>{"".join(cells)}</tr>')
    for f in fam_list:
        fm = C.core["families"].get(f, C.core["families"]["other"])
        cells = []
        for e in C.els:
            ok = e in rows and C.ran(e, f)
            cells.append(f'<td class="n">{pct(100 * shares[e].get(f, 0)) if ok else "—"}</td>')
        fam_rows.append(f'<tr><td><span class="lp-dot {fam_class(f)}"></span>{esc(fm["name"])}</td>{"".join(cells)}</tr>')
    families = ""
    if fam_rows:
        families = f"""<section class="card">
<h2>ההצבעה לפי משפחה פוליטית</h2>
<p class="sub">שיעור הקולות הכשרים ביישוב. רשימות שהתמודדו בשמות שונים או באיחודים מקובצות למשפחה אחת, כמו בדשבורד; ״—״: המשפחה לא התמודדה באותן בחירות.</p>
<div class="tbl-wrap"><table class="t sticky1">
<thead><tr><th>משפחה</th>{''.join(f'<th class="n"><span class="lp-l">{esc(C.E[e]["short"])}</span><span class="lp-s">{C.compact(e)}</span></th>' for e in C.els)}</tr></thead>
<tbody>{''.join(fam_rows)}</tbody>
</table></div>
</section>"""

    # ---- each election: the leading lists
    cards = []
    for e in reversed(C.els):
        v = rows.get(e)
        if not v:
            continue
        top = ranked(C, v, e)
        shown = top[:5]
        rest = v["valid"] - sum(n for _, n in shown)
        lis = []
        for k, n in shown:
            s = 100 * n / v["valid"]
            lis.append(f'<li class="{fam_class(C.family(e, k))}"><span>{esc(C.name(e, k))}<i>{esc(k)}</i></span>'
                       f'<b>{pct(s)}</b><u>{fmt(n)}</u><s style="--w:{s:.1f}%"></s></li>')
        if rest > 0:
            s = 100 * rest / v["valid"]
            lis.append(f'<li class="f-other"><span>כל השאר</span><b>{pct(s)}</b><u>{fmt(rest)}</u><s style="--w:{s:.1f}%"></s></li>')
        ent = C.E[e]
        cards.append(f"""<section class="card">
<h2>{esc(ent['short'])} · הבחירות {esc(C.label(e))}</h2>
<p class="sub">שיעור הצבעה {num(pct(100 * v['voters'] / v['elig']))} · {num(fmt(v['valid']))} קולות כשרים · {num(fmt(v['boxes']))} קלפיות</p>
<ul class="lp-bars">{''.join(lis)}</ul>
</section>""")
    by_el = f'<div class="lp-els">{"".join(cards)}</div>' if cards else '<p class="empty">אין ליישוב קלפיות בקובצי הוועדה.</p>'

    src_links = " · ".join(f'<a href="{esc(C.E[e]["official_url"])}">{esc(C.E[e]["short"])}</a>' for e in C.els if C.E[e].get("official_url"))
    body = f"""
<body>
<header class="mast lp-mast"><div class="wrap">
<a class="lp-brand" href="../../">קלפי <span class="k">26</span></a>
<nav class="lp-crumbs" aria-label="מיקום בדף"><a href="../../">הדשבורד</a> › <a href="../">כל היישובים</a> › <span aria-current="page">{esc(name)}</span></nav>
</div></header>
<main class="wrap lp" id="main">
<div class="loc-head"><div><span class="eyebrow">דף יישוב · תוצאות הבחירות לכנסת</span><h1>{esc(name)}</h1></div>
<div class="chips">{''.join(chips)}</div></div>
<p class="lp-lede">{lede}</p>
{tiles}
{turnout}
{families}
{by_el}
<div class="lp-cta"><a class="lp-btn" href="../../#results">למפה ולתוצאות לפי קלפי בדשבורד</a>
<p>בלשונית ״תוצאות ומפה״ חפשו ״{esc(name)}״ כדי לראות את התוצאה בכל קלפי ביישוב.</p></div>
<p class="disclaimer">מקור: ועדת הבחירות המרכזית, קובצי ״תוצאות לפי קלפיות״ לכל מערכת בחירות ({src_links}); 2019 א׳ מעותק ציבורי של הקובץ הרשמי. הסכומים נבדקו מול הסיכומים הארציים הרשמיים. {('אשכול חברתי-כלכלי: הלמ״ס, מדד 2021, דרך עותק משני. ' if loc.get('ses') else '')}{district_src(dist)}השיטה והמקורות המלאים: <a href="../../#method">שיטה ומקורות</a>.</p>
</main>
</body>
</html>
"""
    return head + body


def district_src(dist):
    if not (dist and dist.get("district")):
        return ""
    url = dist.get("source", "")
    if not url.startswith("https://"):
        return "מחוז: הלמ״ס. "
    host = "data.gov.il" if "data.gov.il" in url else "הלמ״ס"
    return f'מחוז: <a href="{esc(url)}">רשימת היישובים ({host})</a>. '


def social(title, desc, url, img, alt):
    return "\n".join([
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="קלפי 26">',
        '<meta property="og:locale" content="he_IL">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc)}">',
        f'<meta property="og:url" content="{esc(url)}">',
        f'<meta property="og:image" content="{esc(img)}">',
        '<meta property="og:image:type" content="image/png">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        f'<meta property="og:image:alt" content="{esc(alt)}">',
        '<meta name="twitter:card" content="summary_large_image">',   # title, description and image: X reads the og: tags
    ])


def sort_key(name):
    return re.sub(r"[\s\"'׳״`’().\-־]", "", name)


def index_page(C, locs, base):
    url = base + "l/"
    groups = {}
    for loc in sorted(locs, key=lambda l: (sort_key(l["name"]), l["code"])):
        groups.setdefault(sort_key(loc["name"])[:1] or "#", []).append(loc)
    secs = []
    for letter, items in groups.items():
        lis = "".join(f'<li><a href="{l["code"]}/">{esc(l["name"])}</a></li>' for l in items)
        secs.append(f'<section><h2>{esc(letter)}</h2><ul>{lis}</ul></section>')
    desc = (f"תוצאות הבחירות לכנסת {C.span()} בכל אחד מ-{fmt(len(locs))} היישובים: שיעור הצבעה, הרשימות המובילות וההצבעה "
            "לפי משפחה פוליטית בכל מערכת בחירות. נתונים רשמיים של ועדת הבחירות המרכזית.")
    title = f"תוצאות הבחירות לפי יישוב, {C.years()} | קלפי 26"
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
{social(f"תוצאות הבחירות לפי יישוב, {C.years()}", desc, url, base + OG_LOCALITY, "קלפי 26: דפי יישוב, תוצאות הבחירות לכל יישוב")}
{FONTS}
<link rel="stylesheet" href="l.css">
</head>
<body>
<header class="mast lp-mast"><div class="wrap">
<a class="lp-brand" href="../">קלפי <span class="k">26</span></a>
<nav class="lp-crumbs" aria-label="מיקום בדף"><a href="../">הדשבורד</a> › <span aria-current="page">כל היישובים</span></nav>
</div></header>
<main class="wrap lp" id="main">
<span class="eyebrow">דפי יישוב · תוצאות רשמיות</span>
<h1>תוצאות הבחירות לפי יישוב</h1>
<p class="lp-lede">{esc(desc)} לכל יישוב דף בכתובת קבועה, לשיתוף ולקישור.</p>
<div class="lp-filter" id="lp-filter" hidden><input type="search" id="lq" placeholder="סינון לפי שם…" aria-label="סינון יישובים לפי שם"> <span class="ctl-label" id="lq-n" role="status"></span></div>
<div class="lp-index" id="lx">{''.join(secs)}</div>
<p class="disclaimer">מקור: ועדת הבחירות המרכזית, קובצי התוצאות לפי קלפי. השיטה והמקורות המלאים: <a href="../#method">שיטה ומקורות</a>.</p>
</main>
<script>
(() => {{
  const box = document.getElementById('lp-filter'), q = document.getElementById('lq'), n = document.getElementById('lq-n');
  const norm = s => s.replace(/[\\s"'׳״`’().\\-־]/g, '');
  const items = [...document.querySelectorAll('#lx li')].map(li => [li, norm(li.textContent)]);
  box.hidden = false;
  q.addEventListener('input', () => {{
    const v = norm(q.value); let k = 0;
    items.forEach(([li, t]) => {{ li.hidden = !!v && !t.includes(v); if (!li.hidden) k++; }});
    document.querySelectorAll('#lx section').forEach(s => {{ s.hidden = !s.querySelector('li:not([hidden])'); }});
    n.textContent = v ? `${{k}} יישובים` : '';
  }});
}})();
</script>
</body>
</html>
"""


def family_css(core):
    """The colours of the political families (core.json), light and dark the way styles.css switches its tokens."""
    fams = list(core["families"].items())

    def rules(key, scope=""):
        return "\n".join(f"{scope}.{fam_class(k)} {{ --c: {f[key]}; }}" for k, f in fams)
    return ("\n/* political families (core.json 'families'), light then dark */\n" + rules("color") + "\n"
            "@media (prefers-color-scheme: dark) {\n" + rules("dark", ':root:not([data-theme="light"]) ') + "\n}\n"
            + rules("dark", ':root[data-theme="dark"] ') + "\n")


def sitemap(base, codes):
    urls = [base, base + "l/"] + [f"{base}l/{c}/" for c in codes]
    body = "".join(f"<url><loc>{esc(u)}</loc></url>\n" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n'


def root_of(base):
    return base[: -len("site/")] if base.endswith("site/") else base


def robots(base):
    return ("# Crawlers read robots.txt only at a host's root (https://baselegbareia-beep.github.io/robots.txt): this copy\n"
            "# documents the intent and names the sitemap; submit the sitemap in Google Search Console to have it read.\n"
            "User-agent: *\n"
            "Disallow: /Elections/site/artifact.html\n"
            "Allow: /\n\n"
            f"Sitemap: {root_of(base)}sitemap.xml\n")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default=BASE, help="public address of site/ (with the trailing slash)")
    ap.add_argument("--core", default=os.path.join(SITE, "data", "core.json"))
    ap.add_argument("--districts", default=DISTRICTS, help="optional {code: {district, subdistrict}} file")
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"
    core = json.load(open(args.core, encoding="utf-8"))
    C = Core(core)
    districts = None
    if args.districts and os.path.exists(args.districts):
        d = json.load(open(args.districts, encoding="utf-8"))
        src = d.get("source", "")
        districts = {k: dict(v, source=src) for k, v in d.items() if isinstance(v, dict)}
    locs = core["localities"]
    codes = sorted(l["code"] for l in locs)
    assert len(set(codes)) == len(codes), "locality codes must be unique"

    out = os.path.join(SITE, "l")
    # pages of localities that left core.json go too (the folder holds only what this script writes)
    keep = {str(c) for c in codes}
    if os.path.isdir(out):
        for name in os.listdir(out):
            p = os.path.join(out, name)
            if os.path.isdir(p) and name.isdigit() and name not in keep:
                shutil.rmtree(p)
    total = 0
    for loc in locs:
        page = locality_page(C, loc, base, districts)
        write(os.path.join(out, str(loc["code"]), "index.html"), page)
        total += len(page.encode("utf-8"))
    idx = index_page(C, locs, base)
    write(os.path.join(out, "index.html"), idx)
    styles = open(os.path.join(SITE, "src", "styles.css"), encoding="utf-8").read()
    css = ("/* Built by pipeline/build_pages.py from site/src/styles.css (the dashboard's tokens and components) and the\n"
           "   locality-page rules below. Edit those, not this file. */\n" + styles + PAGE_CSS + family_css(core))
    write(os.path.join(out, "l.css"), css)
    sm = sitemap(base, codes)
    write(os.path.join(SITE, "sitemap.xml"), sm)
    write(os.path.join(ROOT, "sitemap.xml"),
          '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"<sitemap><loc>{esc(base)}sitemap.xml</loc></sitemap>\n</sitemapindex>\n")
    rb = robots(base)
    write(os.path.join(SITE, "robots.txt"), rb)
    write(os.path.join(ROOT, "robots.txt"), rb)
    print(f"{len(locs)} locality pages, {total:,} bytes ({total // max(1, len(locs)):,} per page); "
          f"index {len(idx.encode('utf-8')):,} bytes; l.css {len(css.encode('utf-8')):,} bytes; "
          f"sitemap {len(codes) + 2} URLs; districts {'yes' if districts else 'no'}")


if __name__ == "__main__":
    main()
