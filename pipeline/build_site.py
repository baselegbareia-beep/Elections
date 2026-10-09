"""Inline site/src (template, CSS, JS modules) into one HTML page.

Outputs:
  site/index.html      full document for static hosting (GitHub Pages etc.)
  site/artifact.html   body-only fragment (the artifact host adds the skeleton)
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "site", "src")
JS_ORDER = ["core.js", "overview.js", "polls.js", "coalition.js", "arab.js", "results.js",
            "sectors.js", "accuracy.js", "method.js", "plan.js", "live.js", "main.js"]


def read(*p):
    with open(os.path.join(SRC, *p), encoding="utf-8") as f:
        return f.read()


def main():
    tpl = read("index.html")
    css = read("styles.css")
    js = "\n".join(read("js", name) for name in JS_ORDER if os.path.exists(os.path.join(SRC, "js", name)))
    body = tpl.replace("/*STYLES*/", css).replace("/*SCRIPTS*/", js)
    with open(os.path.join(ROOT, "site", "artifact.html"), "w", encoding="utf-8") as f:
        f.write(body)
    full = ('<!doctype html>\n<html lang="he" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + body.replace('<div dir="rtl" lang="he">', '</head>\n<body>\n<div dir="rtl" lang="he">', 1)
            + "\n</body>\n</html>\n")
    with open(os.path.join(ROOT, "site", "index.html"), "w", encoding="utf-8") as f:
        f.write(full)
    print(f"index.html {len(full):,} bytes; artifact.html {len(body):,} bytes")


if __name__ == "__main__":
    main()
