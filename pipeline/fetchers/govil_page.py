"""A gov.il content page's own data: its JSON through the content-pages API and every file it links (election day).

gov.il pages are shells; their text and their file links come from the content-pages API (cec_lists.py finds its
address and the site's public client id in client-config.js). The CEC's per-station turnout page
(turnout_at_polling_stations) replaces its file under a new name for every release, so the feed's
station_turnout_url has to follow what the page links now. This fetcher asks the API for the page (and its
chapters), lists every linked address with its title, and downloads the linked files (CSV/XLSX/PDF/ZIP), each with
its HTTP Last-Modified, under DIR/files/.

    python3 pipeline/fetchers/govil_page.py --out DIR [--page NAME ...] [--deadline S]

Fetch contract: pipeline/fetchers/__init__.py (standard library only).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_lists as C  # noqa: E402

PAGES = ["turnout_at_polling_stations", "voting-by-hour-26"]
FILE_RE = re.compile(r"\.(csv|xlsx?|pdf|zip|json|txt)(\?|$)", re.I)
DEADLINE = 20 * 60


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--page", action="append", default=[])
    ap.add_argument("--deadline", type=float, default=DEADLINE)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    started = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    pages, notes, links, files = a.page or PAGES, [], [], []
    if a.deadline > 0:
        F = C.Fetcher(a.out, deadline=a.deadline)
        base, cid = C.api_config(F)
        hdr = {"Origin": C.GOVIL, "Referer": C.GOVIL + "/", "Accept": "application/json", **({"x-client-id": cid} if cid else {})}
        notes.append(f"content-pages API: {base} (client id found: {bool(cid)})")
        for name in pages:
            for chapter in (None, 1, 2, 3):
                url = f"{base}/{urllib.parse.quote(name)}?culture=he" + (f"&chapterIndex={chapter}" if chapter else "")
                entry, body = F.get(url, headers=hdr, why=f"the page {name}")
                notes.append(f"{name} chapter {chapter or 0}: HTTP {entry.get('status') or entry.get('http')} "
                             f"{len(body or b'')} bytes {entry.get('error') or ''}".strip())
                if not body:
                    continue
                try:
                    doc = json.loads(C.as_text(body))
                except ValueError:
                    continue
                for href, title in C.json_links(doc):
                    u = C.absolute(href, C.GOVIL + "/") or href
                    if (u, title) not in links:
                        links.append((u, title))
        for u, title in links:
            if FILE_RE.search(u):
                entry, body = F.get(u, why=f"a file the page links: {title}")
                files.append({"url": u, "title": title, "http": entry.get("status") or entry.get("http"),
                              "bytes": len(body or b""), "last_modified": entry.get("last_modified") or entry.get("headers", {}).get("Last-Modified"),
                              "saved": entry.get("path") or entry.get("file"), "error": entry.get("error")})
    else:
        notes.append("Stopped at the deadline: nothing asked")
    json.dump({"fetcher": "govil_page", "started": started, "pages": pages, "notes": notes,
               "links": [{"url": u, "title": t} for u, t in links], "files": files},
              open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    md = [f"# gov.il pages through the content-pages API ({started})", ""] + [f"- {n}" for n in notes]
    md += ["", "## Files the pages link", "", "| title | URL | HTTP | bytes | last-modified | saved |", "|---|---|---|---|---|---|"]
    md += [f"| {f['title']} | {f['url']} | {f['http']} | {f['bytes']} | {f['last_modified']} | {f['saved'] or f['error'] or ''} |" for f in files]
    md += ["", "## Every link", ""] + [f"- {t}: {u}" for u, t in links]
    open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(json.dumps({"links": len(links), "files": len(files)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
