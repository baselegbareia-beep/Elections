"""Inline site/src (template, CSS, JS modules) into one HTML page.

Outputs:
  site/index.html      full document for static hosting (GitHub Pages etc.)
  site/artifact.html   body-only fragment (the artifact host adds the skeleton)
"""
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "site", "src")
JS_ORDER = ["core.js", "overview.js", "polls.js", "coalition.js", "arab.js", "results.js",
            "sectors.js", "accuracy.js", "method.js", "plan.js", "live.js", "arab_day.js", "main.js"]
CSS_ORDER = ["styles.css", "arab_day.css"]   # arab_day.css: the Arab-society section of the election-day tab


def read(*p):
    with open(os.path.join(SRC, *p), encoding="utf-8") as f:
        return f.read()


# Visitor counts for the owner only (Cloudflare Web Analytics: no cookies, no personal data). The token only
# lets the page send counts; viewing them needs the owner's Cloudflare login. GitHub Pages page only, not the artifact.
ANALYTICS = ("\n<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' "
             "data-cf-beacon='{\"token\": \"4c5dbff159b44452ab501e24fff89e52\"}'></script><!-- End Cloudflare Web Analytics -->")


# Share cards and search: the published address, its card (pipeline/build_og.py) and the template's description.
# GitHub Pages page only: the artifact host builds its own head.
SITE_URL = "https://baselegbareia-beep.github.io/Elections/site/"


def social_meta(tpl):
    m = re.search(r'<meta name="description" content="([^"]*)">', tpl)
    desc = html.unescape(m.group(1)) if m else ""
    title = "קלפי 26: הבחירות לכנסת ה-26"
    q = lambda s: html.escape(s, quote=True)
    return "\n".join([
        f'<link rel="canonical" href="{SITE_URL}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="קלפי 26">',
        '<meta property="og:locale" content="he_IL">',
        f'<meta property="og:title" content="{q(title)}">',
        f'<meta property="og:description" content="{q(desc)}">',
        f'<meta property="og:url" content="{SITE_URL}">',
        f'<meta property="og:image" content="{SITE_URL}og/main.png">',
        '<meta property="og:image:type" content="image/png">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta property="og:image:alt" content="קלפי 26: הבחירות לכנסת ה-26, יום שלישי 27 באוקטובר 2026">',
        '<meta name="twitter:card" content="summary_large_image">',   # title, description and image: X reads the og: tags
    ]) + "\n"


def main():
    tpl = read("index.html")
    css = "\n".join(read(name) for name in CSS_ORDER if os.path.exists(os.path.join(SRC, name)))
    js = "\n".join(read("js", name) for name in JS_ORDER if os.path.exists(os.path.join(SRC, "js", name)))
    body = tpl.replace("/*STYLES*/", css).replace("/*SCRIPTS*/", js)
    with open(os.path.join(ROOT, "site", "artifact.html"), "w", encoding="utf-8") as f:
        f.write(body)
    full = ('<!doctype html>\n<html lang="he" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + social_meta(tpl) + body.replace('<div dir="rtl" lang="he">', '</head>\n<body>\n<div dir="rtl" lang="he">', 1)
            + ANALYTICS + "\n</body>\n</html>\n")
    with open(os.path.join(ROOT, "site", "index.html"), "w", encoding="utf-8") as f:
        f.write(full)
    print(f"index.html {len(full):,} bytes; artifact.html {len(body):,} bytes")


if __name__ == "__main__":
    main()
