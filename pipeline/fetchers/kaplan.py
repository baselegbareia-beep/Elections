"""Election results as the open-source site elections.kaplanopensource.co.il serves them (the CEC's own results site
answers only from Israel): its pages, their scripts, and every data file (JSON/CSV) the scripts name, followed one
level deep, saved under DIR/files/ for the operator.

    python3 pipeline/fetchers/kaplan.py --out DIR [--deadline S]

Fetch contract: pipeline/fetchers/__init__.py (standard library only).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://elections.kaplanopensource.co.il/"
START = ["locality/", "", "locality/js/locality.js", "locality/js/strings.js", "js/_2.js", "js/_3.js",
         "26/data/parties.json", "26/data/national_results.json"]
UA = "Kalpi26-dashboard/1.0 (+https://github.com/baselegbareia-beep/Elections)"
DATA = re.compile(r"""["'`]([^"'`\s]*?\.(?:json|csv|js))(?:\?[^"'`\s]*)?["'`]""")
MAX, DEADLINE = 40 * 1024 * 1024, 600


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline", type=float, default=DEADLINE)
    a = ap.parse_args(argv)
    os.makedirs(os.path.join(a.out, "files"), exist_ok=True)
    t0, seen, log, queue = time.time(), set(), [], [(urllib.parse.urljoin(BASE, u), 0) for u in START]
    while queue and time.time() - t0 < a.deadline and len(seen) < 120:
        url, depth = queue.pop(0)
        if url in seen or urllib.parse.urlsplit(url).hostname != urllib.parse.urlsplit(BASE).hostname:
            continue
        seen.add(url)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read(MAX)
                st = r.status
        except Exception as e:  # noqa: BLE001
            log.append({"url": url, "error": f"{type(e).__name__}: {e}"[:200]})
            continue
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", urllib.parse.urlsplit(url).path.strip("/") or "index") or "index"
        if not os.path.splitext(name)[1]:
            name += ".html"
        open(os.path.join(a.out, "files", name), "wb").write(body)
        log.append({"url": url, "http": st, "bytes": len(body), "file": name})
        if depth < 2 and (name.endswith((".js", ".html")) or url.endswith("/")):
            for m in DATA.finditer(body.decode("utf-8", "replace")):
                u = m.group(1)
                if "${" in u or u.startswith(("http://", "https://")) and BASE not in u:
                    log.append({"template": u}) if "${" in u else None
                    continue
                queue.append((urllib.parse.urljoin(url, u), depth + 1))
    json.dump({"fetcher": "kaplan", "log": log}, open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    md = ["# elections.kaplanopensource.co.il", ""] + [
        f"- {x.get('url') or 'template'} {x.get('http', '')} {x.get('bytes', '')} {x.get('file') or x.get('error') or x.get('template', '')}" for x in log]
    open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(json.dumps({"files": sum(1 for x in log if x.get("file"))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
