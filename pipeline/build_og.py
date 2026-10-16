"""Share cards (Open Graph images, 1200x630 PNG) for the dashboard, rendered with Playwright from an HTML template.

Writes site/og/<card>.png:
  main       the dashboard (site/index.html's og:image, built by build_site.py)
  locality   the locality pages (site/l/, build_pages.py)
  live, arab, polls, coalition, results   one per major tab
and, for each tab card, a share page site/og/<tab>/index.html: its own title, description and card for the
crawlers of WhatsApp, Facebook, X and Telegram (which never see the '#tab' of an address), sending a visitor on
to the dashboard at that tab. The cards carry no poll numbers (they stay valid in the poll-publication ban,
24.10 00:00 to 27.10 22:00) and nothing that changes with the data, so they are rebuilt only when their copy does:
by hand, not in run_pipeline.sh or a workflow.

The site's fonts (IBM Plex Sans Hebrew, Karantina) are read from --fonts, or downloaded from the Google Fonts
repository on GitHub. Playwright: the Python package if installed, otherwise Node's (--node-modules: a folder
holding node_modules/playwright; --chromium: a browser executable, if Playwright's own is not installed).

Run: python3 pipeline/build_og.py [--fonts DIR] [--node-modules DIR] [--chromium PATH] [--only main,arab]
"""
import argparse
import html
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "og")
BASE = "https://baselegbareia-beep.github.io/Elections/site/"
W, H = 1200, 630

FONT_SRC = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {   # file -> (family, weight)
    "Karantina-Bold.ttf": ("Karantina", 700, "karantina/"),
    "IBMPlexSansHebrew-Regular.ttf": ("IBM Plex Sans Hebrew", 400, "ibmplexsanshebrew/"),
    "IBMPlexSansHebrew-Medium.ttf": ("IBM Plex Sans Hebrew", 500, "ibmplexsanshebrew/"),
    "IBMPlexSansHebrew-SemiBold.ttf": ("IBM Plex Sans Hebrew", 600, "ibmplexsanshebrew/"),
    "IBMPlexSansHebrew-Bold.ttf": ("IBM Plex Sans Hebrew", 700, "ibmplexsanshebrew/"),
}

ELECTION = "יום שלישי, 27 באוקטובר 2026"
# copy: the masthead and each tab's own heading and introduction (site/src/index.html, site/src/js/*.js)
CARDS = {
    "main": {
        "eyebrow": f"הבחירות לכנסת ה-26 · {ELECTION}",
        "text": "ממוצע סקרים, תרחישי קואליציה ותוצאות חמש מערכות הבחירות האחרונות, עד רמת הקלפי הבודדת. בדגש על החברה הערבית.",
        "chips": ["יום הבחירות", "החברה הערבית", "סקרים", "קואליציות", "תוצאות ומפה"],
        "alt": "קלפי 26: הבחירות לכנסת ה-26, יום שלישי 27 באוקטובר 2026",
    },
    "live": {
        "tab": "live", "accent": "#ffd400", "eyebrow": f"יום הבחירות · {ELECTION} · 07:00–22:00",
        "title": "יום הבחירות, בזמן אמת",
        "text": "במהלך היום: שיעור ההצבעה הרשמי של ועדת הבחירות, מול אותה שעה בבחירות הקודמות. מ-22:00: ספירת הקולות, קלפי אחר קלפי.",
        "alt": "קלפי 26: יום הבחירות, שיעור ההצבעה וספירת הקולות",
    },
    "arab": {
        "tab": "arab", "accent": "#0b7a55", "eyebrow": "מוקד · החברה הערבית בבחירות",
        "title": "החברה הערבית",
        "text": "השתתפות, פיצולים והכוח לקבוע: חמש מערכות בחירות, עשרה אזורים, ערים מעורבות ודרוזים, מתוצאות הקלפיות הרשמיות.",
        "alt": "קלפי 26: החברה הערבית בבחירות לכנסת",
    },
    "polls": {
        "tab": "polls", "eyebrow": "סקרים · ממוצע משוקלל של אחוזי הקולות",
        "title": "מגמות בסקרים",
        "text": "הסקרים שפורסמו, עם גודל המדגם, טעות הדגימה וקישור לקובץ הדיווח הרשמי לוועדת הבחירות כשנמצא.",
        "alt": "קלפי 26: מגמות בסקרים",
    },
    "coalition": {
        "tab": "coalition", "eyebrow": "בונה קואליציה · מחולל תרחישים",
        "title": "הדרך ל-61",
        "text": "בונים קואליציה מתוך 120 המושבים: מנדטים לפי ממוצע הסקרים בשיטת בדר-עופר, עם אחוז החסימה ומחוון השתתפות.",
        "alt": "קלפי 26: מחשבון קואליציות, הדרך ל-61",
    },
    "results": {
        "tab": "results", "eyebrow": "תוצאות רשמיות · ועדת הבחירות המרכזית",
        "title": "חמש מערכות בחירות, עד הקלפי",
        "text": "מפת יישובים, פרופיל לכל יישוב והתוצאה בכל קלפי, מאפריל 2019 עד נובמבר 2022.",
        "alt": "קלפי 26: תוצאות חמש מערכות הבחירות, עד הקלפי",
    },
    "locality": {
        "eyebrow": "דפי יישוב · תוצאות רשמיות",
        "title": "דף לכל יישוב",
        "text": "תוצאות חמש מערכות הבחירות, מ-{first} עד {last}, בכל אחד מ-{n} היישובים: שיעור הצבעה, הרשימות המובילות וההצבעה לפי משפחה פוליטית.",
        "alt": "קלפי 26: דפי יישוב, תוצאות הבחירות לכל יישוב",
    },
}

CSS = """
:root { --bg: #f2f4f7; --surface: #ffffff; --ink: #0c1320; --ink-2: #3f4a5c; --muted: #6b7587; --rule: #dfe4eb;
  --rule-strong: #c4ccd8; --marker: #ffd400; --land: #e6eaf0; --accent: #b8c1ce; }
* { box-sizing: border-box; }
html, body { margin: 0; width: 1200px; height: 630px; overflow: hidden; }
body { background: var(--bg); color: var(--ink); font-family: "IBM Plex Sans Hebrew", sans-serif; font-feature-settings: "tnum" 1; }
.card { position: absolute; inset: 26px; background: var(--surface); border: 1px solid var(--rule); border-radius: 22px;
  overflow: hidden; display: grid; grid-template-columns: minmax(0, 1fr) 340px; grid-template-rows: minmax(0, 1fr) 74px; }
.card::before { content: ""; position: absolute; inset-inline: 0; top: 0; height: 10px; background: var(--marker); }
.txt { padding: 58px 64px 0 8px; display: flex; flex-direction: column; justify-content: center; gap: 20px; min-width: 0; }
.eyebrow { font-size: 25px; font-weight: 600; color: var(--muted); letter-spacing: .3px; }
.brand { font: 700 176px/.8 Karantina, sans-serif; letter-spacing: 1px; margin: 0; white-space: nowrap; }
.mini { font: 700 58px/.8 Karantina, sans-serif; letter-spacing: .5px; }
.brand .k, .mini .k { display: inline-block; background: var(--marker); padding: .04em .1em 0; line-height: .76; border-radius: .05em; }
h1 { font: 700 104px/.9 Karantina, sans-serif; margin: 0; letter-spacing: .5px; text-wrap: balance; }
p { margin: 0; font-size: 31px; line-height: 1.38; color: var(--ink-2); text-wrap: pretty; max-width: 30ch; }
.chips { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; }
.chips span { font-size: 22px; font-weight: 500; border: 2px solid var(--rule-strong); border-radius: 8px; padding: 3px 12px; color: var(--ink-2); background: #fff; }
.art { display: flex; align-items: center; justify-content: center; padding: 40px 30px 0 40px; }
.art svg { width: 290px; height: auto; }
.foot { grid-column: 1 / -1; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--rule);
  padding: 0 64px 0 48px; font-size: 22px; color: var(--muted); background: #f7f8fa; }
.foot b { color: var(--ink-2); font-weight: 600; }
.url { direction: ltr; unicode-bidi: isolate; font-weight: 500; color: var(--ink-2); }
"""


def ballot_box(accent):
    """A ballot box (קלפי) taking a slip with the counting-marker highlight: the site's visual language."""
    ink = "#0c1320"
    return f"""<svg viewBox="0 0 300 380" aria-hidden="true">
<g transform="rotate(-7 150 110)">
  <rect x="78" y="6" width="144" height="178" rx="8" fill="#fff" stroke="{ink}" stroke-width="6"/>
  <rect x="100" y="34" width="100" height="44" rx="5" fill="#ffd400"/>
  <text x="150" y="72" text-anchor="middle" font-family="Karantina" font-weight="700" font-size="50" fill="{ink}">26</text>
  <rect x="100" y="96" width="100" height="10" rx="5" fill="#c4ccd8"/>
  <rect x="100" y="118" width="74" height="10" rx="5" fill="#c4ccd8"/>
</g>
<path d="M28 168 H272 L258 368 H42 Z" fill="{accent}" stroke="{ink}" stroke-width="6" stroke-linejoin="round"/>
<rect x="14" y="146" width="272" height="40" rx="9" fill="#fff" stroke="{ink}" stroke-width="6"/>
<rect x="86" y="158" width="128" height="15" rx="7.5" fill="{ink}"/>
<rect x="88" y="236" width="124" height="66" rx="8" fill="#fff" stroke="{ink}" stroke-width="5"/>
<text x="150" y="286" text-anchor="middle" font-family="Karantina" font-weight="700" font-size="54" fill="{ink}">קלפי</text>
</svg>"""


def card_html(key, card, fonts_dir):
    faces = "\n".join(
        f'@font-face {{ font-family: "{fam}"; font-weight: {wt}; src: url("file://{os.path.join(fonts_dir, f)}"); }}'
        for f, (fam, wt, _) in FONTS.items())
    e = html.escape
    if key == "main":
        txt = (f'<span class="eyebrow">{e(card["eyebrow"])}</span>'
               '<div class="brand">קלפי <span class="k">26</span></div>'
               f'<p>{e(card["text"])}</p>'
               f'<div class="chips">{"".join(f"<span>{e(c)}</span>" for c in card["chips"])}</div>')
    else:
        txt = ('<div class="mini">קלפי <span class="k">26</span></div>'
               f'<span class="eyebrow">{e(card["eyebrow"])}</span>'
               f'<h1>{e(card["title"])}</h1><p>{e(card["text"])}</p>')
    url = BASE.replace("https://", "").replace("/site/", "")
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><style>{faces}{CSS}</style></head>
<body><div class="card"><div class="txt">{txt}</div><div class="art">{ballot_box(card.get("accent", "#b8c1ce"))}</div>
<div class="foot"><span><b>תוצאות רשמיות</b> מוועדת הבחירות המרכזית · כל אומדן מסומן</span><span class="url">{e(url)}</span></div></div></body></html>"""


def share_page(key, card):
    """A share address for one tab: its card for the crawlers (no script runs there), the tab for people."""
    url = f"{BASE}og/{key}/"
    title = f"{card['title']} | קלפי 26"
    q = lambda s: html.escape(s, quote=True)
    tab = card["tab"]
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{q(title)}</title>
<meta name="robots" content="noindex">
<meta name="description" content="{q(card['text'])}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="קלפי 26">
<meta property="og:locale" content="he_IL">
<meta property="og:title" content="{q(title)}">
<meta property="og:description" content="{q(card['text'])}">
<meta property="og:url" content="{q(url)}">
<meta property="og:image" content="{BASE}og/{key}.png">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="{W}">
<meta property="og:image:height" content="{H}">
<meta property="og:image:alt" content="{q(card['alt'])}">
<meta name="twitter:card" content="summary_large_image">
<script>location.replace('../../#{tab}');</script>
</head>
<body style="font-family:system-ui,sans-serif;padding:2rem">
<a href="../../#{tab}">קלפי 26: {html.escape(card['title'])}</a>
</body>
</html>
"""


def ensure_fonts(fonts_dir):
    """The site's fonts, from --fonts or downloaded (Google Fonts' repository, OFL)."""
    if not fonts_dir:
        fonts_dir = tempfile.mkdtemp(prefix="og-fonts-")
    os.makedirs(fonts_dir, exist_ok=True)
    for f, (_, _, sub) in FONTS.items():
        p = os.path.join(fonts_dir, f)
        if not os.path.exists(p):
            data = urllib.request.urlopen(FONT_SRC + sub + f, timeout=60).read()
            with open(p, "wb") as fh:
                fh.write(data)
    return os.path.abspath(fonts_dir)


NODE_RENDER = r"""
const path = require('path');
const [mods, chromium, jobsFile] = process.argv.slice(2);
const { chromium: C } = require(mods ? path.join(mods, 'playwright') : 'playwright');
(async () => {
  const jobs = JSON.parse(require('fs').readFileSync(jobsFile, 'utf8'));
  const b = await C.launch(chromium ? { executablePath: chromium } : {});
  const p = await b.newPage({ viewport: { width: %W%, height: %H% }, deviceScaleFactor: 1 });
  for (const [src, out] of jobs) {
    await p.goto('file://' + src);
    await p.evaluate(() => document.fonts.ready);
    const ok = await p.evaluate(() => document.fonts.check('700 100px Karantina') && document.fonts.check('400 30px "IBM Plex Sans Hebrew"'));
    if (!ok) throw new Error('fonts did not load for ' + src);
    const over = await p.evaluate(() => { const c = document.querySelector('.txt'); return c.scrollHeight - c.clientHeight; });
    if (over > 1) throw new Error(`text overflows the card by ${over}px: ${src}`);
    await p.screenshot({ path: out, clip: { x: 0, y: 0, width: %W%, height: %H% } });
    console.log(out);
  }
  await b.close();
})().catch(e => { console.error(e.message || e); process.exit(1); });
""".replace("%W%", str(W)).replace("%H%", str(H))


def render(jobs, node_modules, chromium):
    try:
        from playwright.sync_api import sync_playwright   # noqa: F401
    except ImportError:
        sync_playwright = None
    if sync_playwright:
        with sync_playwright() as pw:
            b = pw.chromium.launch(**({"executable_path": chromium} if chromium else {}))
            p = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            for src, out in jobs:
                p.goto("file://" + src)
                p.evaluate("document.fonts.ready")
                if not p.evaluate("document.fonts.check('700 100px Karantina') && document.fonts.check('400 30px \"IBM Plex Sans Hebrew\"')"):
                    sys.exit(f"fonts did not load for {src}")
                over = p.evaluate("(() => { const c = document.querySelector('.txt'); return c.scrollHeight - c.clientHeight; })()")
                if over > 1:
                    sys.exit(f"text overflows the card by {over}px: {src}")
                p.screenshot(path=out, clip={"x": 0, "y": 0, "width": W, "height": H})
                print(out)
            b.close()
        return
    tmp = tempfile.mkdtemp(prefix="og-node-")
    js, jf = os.path.join(tmp, "render.js"), os.path.join(tmp, "jobs.json")
    with open(js, "w") as f:
        f.write(NODE_RENDER)
    with open(jf, "w") as f:
        json.dump(jobs, f)
    subprocess.run(["node", js, node_modules or "", chromium or "", jf], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fonts", default="", help="folder with the site's TTF fonts (downloaded when missing)")
    ap.add_argument("--node-modules", default=os.environ.get("PLAYWRIGHT_NODE_MODULES", ""),
                    help="node_modules folder holding playwright (when the Python package is not installed)")
    ap.add_argument("--chromium", default=os.environ.get("PLAYWRIGHT_CHROMIUM", ""), help="browser executable")
    ap.add_argument("--only", default="", help="comma-separated card names (default: all)")
    ap.add_argument("--pages-only", action="store_true", help="write the share pages, render nothing")
    args = ap.parse_args()

    core = json.load(open(os.path.join(ROOT, "site", "data", "core.json"), encoding="utf-8"))
    years = [e["date"][:4] for e in core["elections"]]
    loc = CARDS["locality"]
    loc["text"] = loc["text"].format(first=years[0], last=years[-1], n=f"{len(core['localities']):,}")

    os.makedirs(OUT, exist_ok=True)
    for key, card in CARDS.items():
        if card.get("tab"):
            d = os.path.join(OUT, key)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "index.html"), "w", encoding="utf-8", newline="\n") as f:
                f.write(share_page(key, card))
    if args.pages_only:
        return
    keys = [k for k in (args.only.split(",") if args.only else CARDS) if k]
    unknown = [k for k in keys if k not in CARDS]
    if unknown:
        sys.exit(f"unknown card(s): {', '.join(unknown)}; known: {', '.join(CARDS)}")
    fonts_dir = ensure_fonts(args.fonts)
    tmp = tempfile.mkdtemp(prefix="og-cards-")
    jobs = []
    for key in keys:
        src = os.path.join(tmp, f"{key}.html")
        with open(src, "w", encoding="utf-8") as f:
            f.write(card_html(key, CARDS[key], fonts_dir))
        jobs.append([src, os.path.join(OUT, f"{key}.png")])
    render(jobs, args.node_modules, args.chromium)
    for _, out in jobs:
        print(f"{os.path.relpath(out, ROOT)} {os.path.getsize(out):,} bytes")


if __name__ == "__main__":
    main()
