"""Election day: load the CEC's web apps in a real browser and record the data requests they make.

The per-station turnout and the results sites of 2026 are web apps (elections.govmap.gov.il, votes26.bechirot.gov.il)
whose data addresses are not in their HTML; the page's own scripts ask for them. This fetcher opens each page in the
runner's headless Chrome (playwright, Chrome's own User-Agent, no stealth: what any visitor's browser does), waits
for the page to settle, and records every request the page made (address, method, HTTP status, type, size), saving
the JSON/CSV/XML answers from the CEC's and govmap's hosts under DIR/files/ (5 MB each at most) for the operator to
read and to set station_turnout_url / column_aliases (docs/FILE_DISCOVERY.md).

    python3 pipeline/fetchers/net_capture.py --out DIR [--deadline S] [--url URL ...]

Fetch contract (pipeline/fetchers/__init__.py) but for one exception: playwright is pip-installed at run time.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse

DEADLINE = 20 * 60
# the final results by locality as an open-source site serves them (the CEC's own site answers only from Israel)
PAGES = ["https://elections.kaplanopensource.co.il/locality/", "https://elections.kaplanopensource.co.il/"]
KEEP_HOSTS = re.compile(os.environ.get("NET_CAPTURE_KEEP") or r"(^|\.)(bechirot\.gov\.il|govmap\.gov\.il|gov\.il|kaplanopensource\.co\.il)$")
DATA_TYPES = re.compile(r"json|csv|xml|text/plain|octet-stream|excel|spreadsheet", re.I)
MAX_SAVE = 5 * 1024 * 1024
SETTLE_S = 30                                     # after network idle, for timers and lazy requests


def find_chrome():
    for p in (os.environ.get("LIVE_CHROME"), "/opt/google/chrome/chrome", shutil.which("google-chrome"),
              shutil.which("google-chrome-stable"), shutil.which("chromium"), shutil.which("chromium-browser")):
        if p and os.path.exists(p):
            return p
    return None


def ensure_playwright(notes):
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        pass
    p = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright"], capture_output=True, text=True)
    notes.append(f"pip install playwright: rc {p.returncode}")
    try:
        import playwright  # noqa: F401,F811
        return True
    except ImportError:
        return False


def capture(urls, out, stop_at, notes):
    from playwright.sync_api import sync_playwright
    rows, files = [], os.path.join(out, "files")
    os.makedirs(files, exist_ok=True)
    chrome = find_chrome()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, **({"executable_path": chrome} if chrome else {}))
        notes.append(f"Chrome {browser.version} at {chrome or 'playwright default'}")
        for url in urls:
            if time.monotonic() > stop_at - 60:
                notes.append(f"not opened (deadline): {url}")
                continue
            ctx = browser.new_context()
            page = ctx.new_page()
            seen = []

            def on_response(r, seen=seen, page_url=url):
                try:
                    req = r.request
                    host = urllib.parse.urlsplit(r.url).hostname or ""
                    ctype = (r.headers or {}).get("content-type", "")
                    rec = {"page": page_url, "url": r.url, "method": req.method, "status": r.status,
                           "kind": req.resource_type, "type": ctype[:60], "bytes": None, "saved": None}
                    data_like = DATA_TYPES.search(ctype) or re.search(r"\.(json|csv|xml|xlsx?)(\?|$)", r.url, re.I)
                    if req.resource_type == "script" and (host.endswith("govmap.gov.il") or host.startswith("mapvotes.")) and r.status == 200:
                        js = r.body().decode("utf-8", "replace")      # the app's own bundle: the addresses it may ask
                        found = sorted(set(re.findall(r"https?://[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]{6,200}", js))
                                       | set(re.findall(r"[\"'`](/[A-Za-z0-9._~/-]*(?:api|Api|API|data|Data|json|csv|turnout|vote|Vote|kalpi|ballot|Ballot|elect|Elect)[A-Za-z0-9._~/?=&-]*)[\"'`]", js)))
                        rec["strings"] = found[:400]
                    if KEEP_HOSTS.search(host) and data_like and req.resource_type in ("xhr", "fetch", "document", "other"):
                        body = r.body()
                        rec["bytes"] = len(body)
                        if 0 < len(body) <= MAX_SAVE:
                            name = hashlib.sha256(r.url.encode()).hexdigest()[:8] + "-" + re.sub(
                                r"[^A-Za-z0-9._-]+", "_", (host + urllib.parse.urlsplit(r.url).path))[-90:]
                            with open(os.path.join(files, name), "wb") as f:
                                f.write(body)
                            rec["saved"] = "files/" + name
                            rec["first"] = body[:300].decode("utf-8", "replace")
                    seen.append(rec)
                except Exception as err:  # noqa: BLE001 - one bad response never stops the capture
                    seen.append({"page": page_url, "url": getattr(r, "url", "?"), "error": f"{err.__class__.__name__}: {err}"[:200]})

            page.on("response", on_response)
            t0 = time.monotonic()
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                notes.append(f"{url}: HTTP {resp.status if resp else '-'}, title {page.title()[:80]!r}")
                try:                              # what the page shows (labels, menus): the operator's map of it
                    page.wait_for_timeout(3000)
                    notes.append(f"{url}: visible text: {page.inner_text('body')[:600]!r}")
                except Exception:  # noqa: BLE001
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:  # noqa: BLE001
                    notes.append(f"{url}: no network idle in 30 s")
                page.wait_for_timeout(min(SETTLE_S, max(0, stop_at - time.monotonic() - 60)) * 1000)
            except Exception as err:  # noqa: BLE001
                notes.append(f"{url}: {err.__class__.__name__}: {str(err)[:200]}")
            notes.append(f"{url}: {len(seen)} responses in {time.monotonic() - t0:.0f} s")
            rows.extend(seen)
            ctx.close()
        browser.close()
    return rows


def write(out, started, urls, rows, notes):
    data = [r for r in rows if r.get("saved")]
    S = {"fetcher": "net_capture", "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "pages": urls, "notes": notes, "responses": rows}
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(S, f, ensure_ascii=False, indent=1)
    md = [f"# The CEC's web apps: the requests their pages make ({started})", "",
          f"**Data answers saved: {len(data)}** (JSON/CSV/XML from the CEC's and govmap's hosts, under files/).", ""]
    md += [f"- {n}" for n in notes] + ["", "## Data answers", "", "| page | URL | method | HTTP | type | bytes | saved | first bytes |",
                                       "|---|---|---|---|---|---|---|---|"]
    for r in data:
        first = (r.get("first") or "").replace("|", "/").replace("\n", " ")[:120]
        md.append(f"| {r['page']} | {r['url'][:160]} | {r['method']} | {r['status']} | {r['type']} | {r['bytes']} | {r['saved']} | {first} |")
    for r in rows:
        if r.get("strings"):
            md += ["", f"## Addresses and paths in {r['url']}", ""] + [f"- `{x}`" for x in r["strings"]]
    md += ["", "## Every request (address, kind, HTTP)", "", "| page | kind | HTTP | type | URL |", "|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r.get('page')} | {r.get('kind', '')} | {r.get('status', r.get('error', ''))} | {r.get('type', '')} | {str(r.get('url'))[:180]} |")
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline", type=float, default=DEADLINE)
    ap.add_argument("--url", action="append", default=[])
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    started, stop_at = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), time.monotonic() + a.deadline
    urls, rows, notes = a.url or PAGES, [], []
    if a.deadline <= 0:
        notes.append("Stopped at the deadline: nothing opened")
    elif not ensure_playwright(notes):
        notes.append("playwright is not available: nothing opened")
    else:
        try:
            rows = capture(urls, a.out, stop_at, notes)
        except Exception as err:  # noqa: BLE001 - the summary is still written
            notes.append(f"the browser failed: {err.__class__.__name__}: {str(err)[:300]}")
    write(a.out, started, urls, rows, notes)
    print(json.dumps({"responses": len(rows), "saved": sum(1 for r in rows if r.get("saved"))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
