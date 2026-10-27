"""The TV exit polls of election night as the news reports them: feed items about the exit polls (מדגם) and the
pages they link, saved as text for the operator, who enters the polls in live_input/exit_polls.json by hand.

    python3 pipeline/fetchers/exit_polls.py --out DIR [--deadline S]

Fetch contract: pipeline/fetchers/__init__.py (standard library only).
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import national_turnout as N  # noqa: E402

GN = "https://news.google.com/rss/search?hl=iw&gl=IL&ceid=IL:he&q="
FEEDS = [(n, u) for n, u in N.FEEDS if not n.startswith("Google News")] + [
    ("Google News: מדגם", GN + urllib.parse.quote("מדגם מנדטים when:1d")),
    ("Google News: exit poll", "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
     + urllib.parse.quote("Israel exit poll seats when:1d")),
    ("Times of Israel", "https://www.timesofisrael.com/feed/"),
    ("ynetnews", "https://www.ynetnews.com/Integration/StoryRss3082.xml"),
]
KEY = re.compile(r"מדגם|exit poll", re.I)
DEADLINE, TIMEOUT = 300, 20


def get(url, left):
    req = urllib.request.Request(url, headers={"User-Agent": N.UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=min(TIMEOUT, left)) as r:
        return r.status, r.read(6_000_000)


def text_of(body):
    s = body.decode("utf-8", "replace")
    s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", "\n", s)
    return re.sub(r"\n\s*\n+", "\n", html.unescape(s))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline", type=float, default=DEADLINE)
    a = ap.parse_args(argv)
    os.makedirs(os.path.join(a.out, "files"), exist_ok=True)
    t0 = time.time()
    found, pages, notes = [], [], []
    for name, url in FEEDS:
        left = a.deadline - (time.time() - t0)
        if left <= 0:
            break
        try:
            st, body = get(url, left)
            its = N.items(body)
        except Exception as e:  # noqa: BLE001
            notes.append(f"{name}: {type(e).__name__}: {e}"[:200])
            continue
        notes.append(f"{name}: HTTP {st}, {len(its)} items")
        for it in its:
            if KEY.search(it["title"] + " " + it["text"]):
                found.append({"feed": name, **{k: it[k] for k in ("title", "published", "link", "outlet")},
                              "text": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", it["text"])))[:3000]})
    for i, f in enumerate(found):
        u = f["link"]
        left = a.deadline - (time.time() - t0)
        if left <= 0 or not u or "news.google.com" in u or len(pages) >= 40:
            continue
        try:
            st, body = get(u, left)
            path = os.path.join(a.out, "files", f"page{i:02d}.txt")
            open(path, "w", encoding="utf-8").write(u + "\n\n" + text_of(body))
            pages.append({"url": u, "http": st, "file": os.path.basename(path)})
        except Exception as e:  # noqa: BLE001
            pages.append({"url": u, "error": f"{type(e).__name__}: {e}"[:200]})
    json.dump({"fetcher": "exit_polls", "notes": notes, "items": found, "pages": pages},
              open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    md = ["# Exit-poll items in the news feeds", ""] + [f"- {n}" for n in notes] + [""]
    md += [f"- [{f['published']}] {f['outlet'] or f['feed']}: {f['title']}\n  {f['text'][:600]}" for f in found]
    open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(json.dumps({"items": len(found), "pages": len(pages)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
