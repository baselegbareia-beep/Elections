#!/usr/bin/env python3
"""Fetch the CEC's poll filings for the 26th Knesset: the index of the gov.il collector and every filing's PDF.

    python3 pipeline/fetchers/poll_filings.py --out DIR

Every election poll published from 90 days before the election is filed with the Central Elections Committee
(section 16ה of the Elections (Propaganda Methods) Law: who commissioned and ran it, fieldwork dates, population,
sample, respondents, sampling error, the questions and the results), and the committee posts each filing, as sent,
in the gov.il collector https://www.gov.il/he/departments/dynamiccollectors/knesset_election_polls_26 (one item
knesset_election<N> per filing, its PDF at https://www.gov.il/BlobFolder/dynamiccollectorresultitem/<item>/he/<file>).
The build container cannot reach gov.il; GitHub's runners can. Run from .github/workflows/fetch.yml on the request
{"workflow": "fetch", "what": "poll_filings"} (docs/ELECTION_DAY.md, "בקשות דרך ops-control"); the files land on the
ops-reports branch under reports/fetch/poll_filings/<YYYYMMDD-HHMM>/ and .../latest/, and
pipeline/build_poll_filings.py --fetched <that directory> reads them.

What it asks for, in order:
  1. the collector page itself (?skip=0), for the collector's template id: the GUID in its
     ng-init="dynamicCtrl.Events.initCtrl(...)" (as read by zomer-g/letz-hamimshal-extension, scrapers/govil.js),
     else the id seen in a third party's scraper (TEMPLATE_ID below);
  2. the listing: POST https://www.gov.il/he/api/DynamicCollector {"DynamicTemplateID": id, "QueryFilters":
     {"skip": {"Query": skip}}, "From": skip}, ten results a page, until TotalResults (the request shape of
     kolzchut/srm-etl, srm_tools/gov_data_proxy.py, and OpenBudget/budgetkey-data-pipelines,
     procurement/spending/collect_report_uris.py). The page is behind Cloudflare, which has refused some clients'
     TLS (ticnutai/gemaraca-463c22f4, scripts/download-govil-psakim.mjs, goes through curl for that reason) and
     served a JS challenge to others (amitlev/israel-polls-2026, .github/scripts/update-govil-polls.mjs, uses a
     browser): a request that urllib cannot complete, or that answers with a challenge, is asked again with curl
     when the runner has it;
  3. three third parties' indexes of the same collector, as data only (JSON parsed, nothing run), for the filings
     the listing did not give (or all of them, when the listing failed): or523/or523.github.io
     elections2026/data/polls.json, amitlev/israel-polls-2026 docs/polls-data.js (only the JSON arrays assigned
     to window.BASE_POLLS_DATA and window.GOVIL_TOPICAL_DATA) and idoherling/2026_Election_Model
     data/cec_filings_index.psv; and the filing addresses already in pipeline/reference/poll_filings_index.json
     and site/data/polls_2026.json. Only addresses of the exact form above are taken from any of them;
  4. when the listing failed: a bounded probe for items after the last one known (Survey_<number>.pdf and
     Survey<number>.pdf, the names of the recent filings), at most --probe items;
  5. every filing's PDF (the PDFs are not behind the challenge: amitlev's note above), and, when the runner has
     pdftotext, its text (pdftotext -layout) beside it.

What it writes under DIR: files/page/ (the collector page), files/listing/page-<skip>.json (each API answer),
listing.json (the results gathered, as the API gave them), files/third_party/ (the indexes as fetched),
files/pdf/<item>__<file>.pdf, files/text/<item>__<file>.txt (pdftotext only), filings.json (one row per filing
address: where it was found, the HTTP answer, size, SHA-256, the saved name), summary.json and summary.md.
Never raises on a single URL; exit 0 unless the script itself crashed. Nothing is asked after --deadline (DEADLINE,
20 minutes from the start; a body still coming is cut GRACE seconds later, pdftotext is not run after it): what
was not asked by then is recorded as such and the files are written with what came (pipeline/fetchers/__init__.py:
fetch.yml stops it at 25).

Testing against a local server: --rewrite https://www.gov.il=http://127.0.0.1:8765/govil (repeatable, also for
https://raw.githubusercontent.com) fetches from the mock and keeps the real address in the records;
--only-rewritten skips every other host; --no-curl keeps to urllib.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF = os.path.join(ROOT, "pipeline", "reference", "poll_filings_index.json")
POLLS = os.path.join(ROOT, "site", "data", "polls_2026.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
GOVIL = "https://www.gov.il"
COLLECTOR = GOVIL + "/he/departments/dynamiccollectors/knesset_election_polls_26"
API = GOVIL + "/he/api/DynamicCollector"
BLOB = GOVIL + "/BlobFolder/dynamiccollectorresultitem/{item}/he/{file}"
# a filing's address, the only form taken from a third party's file (and from the listing, once built)
FILING_URL = re.compile(r"https://www\.gov\.il/BlobFolder/dynamiccollectorresultitem/(knesset_election\d{1,4})/he/"
                        r"([^/?#\s\"'<>\\]{1,200})", re.I)
# the collector's template id, from idoherling/2026_Election_Model src/scrape_cec.py ("template
# b043127d-..."); the page's own ng-init is asked first
TEMPLATE_ID = "b043127d-d79d-472e-ac10-5567bc9e8d3d"
GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
GH = "https://raw.githubusercontent.com"
THIRD_PARTY = {
    "or523": GH + "/or523/or523.github.io/main/elections2026/data/polls.json",
    "amitlev": GH + "/amitlev/israel-polls-2026/main/docs/polls-data.js",
    "idoherling": GH + "/idoherling/2026_Election_Model/main/data/cec_filings_index.psv",
}
PAGE_SIZE = 10
MAX_PAGES = 80
MAX_PDFS = 400
MAX_PER_ITEM = 3
MAX_FILE = 25_000_000
MAX_TOTAL = 300_000_000
TIMEOUT = 40
DEADLINE = 20 * 60             # seconds from the start (pipeline/fetchers/__init__.py: fetch.yml stops it at 25 minutes)
GRACE = 60                     # a body still coming at the deadline is cut this much later
LATE = "not fetched: past the deadline (--deadline)"
CHALLENGE = re.compile(rb"cf-chl|challenge-platform|Just a moment|cf_chl_opt|Attention Required", re.I)


# ------------------------------------------------------------------ fetching
class Fetcher:
    def __init__(self, out, rewrite=(), only_rewritten=False, timeout=TIMEOUT, curl=True, deadline=DEADLINE):
        self.out = out
        self.rewrite, self.only_rewritten, self.timeout = list(rewrite), only_rewritten, timeout
        self.curl = shutil.which("curl") if curl else None
        self.entries, self.total, self.lock = [], 0, threading.Lock()
        self.stop_at = time.monotonic() + deadline
        self.cut_at = self.stop_at + GRACE

    def late(self):
        return time.monotonic() >= self.stop_at

    def left(self, cap):
        """A request's time limit: cap, or less near the deadline's grace."""
        return max(1.0, min(cap, self.cut_at - time.monotonic()))

    def target(self, url):
        for a, b in self.rewrite:
            if url.startswith(a):
                return b + url[len(a):]
        return None if self.only_rewritten else url

    def request(self, url, data=None, headers=None, why="", expect=None):
        """One request (POST when data is given): (entry, body). The entry is kept in self.entries; body is None
        when nothing usable came. expect: 'json' or 'pdf', the answer a challenge page is told apart from."""
        entry = {"url": url, "why": why}
        if data is not None:
            entry["post"] = data.decode("utf-8", "replace")[:300]
        with self.lock:
            self.entries.append(entry)
        host = urllib.parse.urlsplit(url).hostname or ""
        if not (host == "gov.il" or host.endswith(".gov.il") or host == "raw.githubusercontent.com"):
            entry["error"] = "not fetched: not a gov.il or raw.githubusercontent.com address"
            return entry, None
        if self.late():
            entry["error"] = LATE
            return entry, None
        target = self.target(url)
        if target is None:
            entry["error"] = "not fetched: --only-rewritten"
            return entry, None
        hdr = {"User-Agent": UA, "Accept": "application/json, text/plain, */*" if expect == "json" else "*/*",
               "Accept-Language": "he-IL,he;q=0.9,en;q=0.8", "Accept-Encoding": "gzip, deflate", **(headers or {})}
        body = self.urllib(entry, target, data, hdr)
        blocked = entry.get("status") in (None, 403, 429, 503) or 520 <= (entry.get("status") or 0) <= 530
        challenged = body is not None and self.refused(entry, body, expect)
        if self.curl and "gov.il" in host and ((body is None and blocked) or challenged):
            first = {k: entry.pop(k) for k in ("status", "type", "error", "head", "bytes") if k in entry}
            entry["urllib"] = first
            body = self.via_curl(entry, target, data, hdr)
        if body is not None and self.refused(entry, body, expect):
            entry["error"] = entry.get("error") or "a challenge page, not the " + (expect or "file")
            entry["head"] = text_head(body)
            body = None
        if body is not None:
            if len(body) > MAX_FILE:
                entry["error"], body = f"over {MAX_FILE // 1_000_000} MB: not kept", None
            else:
                entry["bytes"], entry["sha256"] = len(body), hashlib.sha256(body).hexdigest()
        return entry, body

    def urllib(self, entry, target, data, hdr):
        try:
            if data is not None:
                hdr = {**hdr, "Content-Type": "application/json;charset=UTF-8"}
            req = urllib.request.Request(target, data=data, headers=hdr, method="POST" if data is not None else "GET")
            with urllib.request.urlopen(req, timeout=self.left(self.timeout)) as r:
                entry["status"], raw = r.status, read_until(r, MAX_FILE + 1, self.cut_at)
                entry["type"] = r.headers.get("Content-Type", "")
                if r.headers.get("Last-Modified"):
                    entry["last_modified"] = r.headers.get("Last-Modified")
                enc = r.headers.get("Content-Encoding") or ""
            entry["transport"] = "urllib"
            return decode_body(raw, enc)
        except urllib.error.HTTPError as exc:
            entry["status"], entry["type"] = exc.code, (exc.headers or {}).get("Content-Type", "")
            try:
                entry["head"] = text_head(decode_body(exc.read(4096), (exc.headers or {}).get("Content-Encoding", "")))
            except Exception:
                pass
            entry["error"] = f"HTTP {exc.code}"
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError, ValueError) as exc:
            entry["error"] = f"{exc.__class__.__name__}: {str(getattr(exc, 'reason', exc))[:160]}"
        except Exception as exc:                          # anything else about one URL is that URL's problem
            entry["error"] = f"{exc.__class__.__name__}: {str(exc)[:160]}"
        return None

    def via_curl(self, entry, target, data, hdr):
        """The same request through curl (another TLS client), when urllib was refused or got a challenge."""
        entry["transport"] = "curl"
        if self.late():
            entry["error"] = LATE
            return None
        fd, path = tempfile.mkstemp(prefix="filing-")
        os.close(fd)
        limit = int(self.left(self.timeout + 20))
        try:
            cmd = [self.curl, "-sS", "-L", "--max-redirs", "3", "--proto", "=https,http", "--compressed",
                   "--max-time", str(limit), "-o", path, "-w", "%{http_code}\n%{content_type}\n"]
            for k, v in hdr.items():
                if k.lower() not in ("accept-encoding",):
                    cmd += ["-H", f"{k}: {v}"]
            if data is not None:
                cmd += ["-H", "Content-Type: application/json;charset=UTF-8", "--data-binary", "@-"]
            cmd.append(target)
            p = subprocess.run(cmd, input=data, capture_output=True, timeout=limit + 20)
            info = p.stdout.decode("utf-8", "replace").split("\n")
            code = int(info[0]) if info and info[0].strip().isdigit() else 0
            entry["status"], entry["type"] = code or None, (info[1] if len(info) > 1 else "")
            if p.returncode != 0 and not code:
                entry["error"] = f"curl exit {p.returncode}: {p.stderr.decode('utf-8', 'replace').strip()[:160]}"
                return None
            with open(path, "rb") as f:
                body = f.read(MAX_FILE + 1)
            if code != 200:
                entry["error"], entry["head"] = f"HTTP {code}", text_head(body)
                return None
            return body
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            entry["error"] = f"curl: {exc.__class__.__name__}: {str(exc)[:160]}"
            return None
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def refused(entry, body, expect):
        if body is None:
            return True
        if expect == "pdf":
            return body[:5] != b"%PDF-"
        if expect == "json":
            return body.lstrip()[:1] not in (b"{", b"[")
        return bool(CHALLENGE.search(body[:6000])) and b"<html" in body[:2000].lower()

    def save(self, entry, body, rel):
        with self.lock:
            if self.total + len(body) > MAX_TOTAL:
                entry["note"] = f"not stored: this run already stored {self.total / 1e6:.0f} MB"
                return None
            self.total += len(body)
        path = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
        entry["saved"] = rel
        return path


def read_until(r, limit, cut):
    """r.read(limit), in pieces, stopped at the monotonic time `cut`: a slow body cannot hold the run past the
    deadline's grace."""
    chunks, n = [], 0
    while n < limit:
        if time.monotonic() > cut:
            raise TimeoutError(f"cut at the deadline (--deadline) after {n} bytes")
        b = r.read(min(1 << 16, limit - n))
        if not b:
            break
        chunks.append(b)
        n += len(b)
    return b"".join(chunks)


def decode_body(raw, enc):
    enc = (enc or "").lower()
    try:
        if "gzip" in enc or raw[:2] == b"\x1f\x8b":
            return gzip.decompress(raw)
        if "deflate" in enc:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
    except (OSError, EOFError, zlib.error):
        pass
    return raw


def as_text(body):
    for enc in ("utf-8-sig", "cp1255"):
        try:
            return body.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return body.decode("utf-8", "replace")


def text_head(body, n=160):
    if not body or body[:5] == b"%PDF-":
        return ""
    return re.sub(r"\s+", " ", as_text(body[:2000]))[:n]


def safe_file(name):
    """A filing's file name as a local name: Hebrew and Latin letters, digits, '.', '-' and '_' only."""
    base = re.sub(r"[^0-9A-Za-zא-ת.\-]+", "_", urllib.parse.unquote(name)).strip("._") or "file"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base[-100:]


def filing_url(item, file):
    return BLOB.format(item=urllib.parse.quote(item), file=urllib.parse.quote(urllib.parse.unquote(file)))


def canon(url):
    """(item, file name, canonical address) of a filing address, or None when it is not one."""
    m = FILING_URL.fullmatch((url or "").strip())
    if not m:
        return None
    item = "knesset_election" + m.group(1)[16:]
    file = urllib.parse.unquote(m.group(2))
    return item, file, filing_url(item, file)


def item_number(item):
    return int(item[16:]) if item.startswith("knesset_election") and item[16:].isdigit() else 0


# ------------------------------------------------------------------ the listing
def template_ids(html):
    """The template id candidates of the collector page: GUIDs in its initCtrl(...) call first, then the known one,
    then any other GUID on the page (at most three in all)."""
    out = []
    i = html.find("initCtrl")
    if i >= 0:
        window = html[i:i + 4000].replace("&quot;", '"').replace("&#39;", "'")
        out += [g.lower() for g in GUID.findall(window)][:1]
    out.append(TEMPLATE_ID)
    out += [g.lower() for g in GUID.findall(html)]
    seen = []
    for g in out:
        if g not in seen:
            seen.append(g)
    return seen[:3]


def results_of(body):
    try:
        d = json.loads(as_text(body))
    except ValueError:
        return None, None
    if not isinstance(d, dict) or not isinstance(d.get("Results"), list):
        return None, None
    total = d.get("TotalResults")
    return [r for r in d["Results"] if isinstance(r, dict) and isinstance(r.get("UrlName"), str)], \
        (int(total) if isinstance(total, (int, float)) and not isinstance(total, bool) and 0 <= total < 100000 else None)


def fetch_listing(F, ids):
    """All results the API gives for the first template id that answers: (template id, results by UrlName, notes)."""
    notes = []
    hdr = {"Origin": GOVIL, "Referer": COLLECTOR + "?skip=0"}
    for tid in ids:
        got, total, skip, pages, shape = {}, None, 0, 0, "query"
        while pages < MAX_PAGES:
            q = skip if shape == "query" else 0
            body = json.dumps({"DynamicTemplateID": tid, "QueryFilters": {"skip": {"Query": q}}, "From": skip}).encode()
            entry, raw = F.request(API, data=body, headers=hdr, why=f"the collector's listing, from {skip}", expect="json")
            results, t = results_of(raw) if raw is not None else (None, None)
            if results is None:
                if raw is not None:
                    entry["error"] = "no Results list in the answer"
                break
            F.save(entry, raw, f"files/listing/{tid[:8]}-page-{skip:04d}.json")
            pages += 1
            total = t if t is not None else total
            new = [r for r in results if r["UrlName"] not in got]
            for r in results:
                got.setdefault(r["UrlName"], r)
            if results and not new and shape == "query":
                shape = "from"                              # the other request shape (skip given only as From)
                notes.append(f"{tid}: page {skip} repeated the last one; asking with QueryFilters.skip = 0, From = {skip}")
                continue
            if not results or not new:
                break
            skip += len(results)
            if total is not None and skip >= total:
                break
            time.sleep(0.4)
        if got:
            if total is not None and len(got) < total:
                notes.append(f"{tid}: {len(got)} of TotalResults {total} gathered")
            return tid, got, total, notes
        notes.append(f"{tid}: no listing")
    return None, {}, None, notes


def listing_files(r):
    """The file names a listing result carries: every {"FileName": ...} in its Data, PDF fields first."""
    data = r.get("Data") if isinstance(r.get("Data"), dict) else {}
    names = []
    for k in sorted(data, key=lambda k: (0 if "pdf" in k.lower() else 1, k)):
        v = data[k]
        for f in v if isinstance(v, list) else [v]:
            if isinstance(f, dict) and isinstance(f.get("FileName"), str) and f["FileName"].strip():
                names.append(f["FileName"].strip())
    return names


def compact(v, n=300):
    """A listing field as a short JSON value (text cut at n characters)."""
    if isinstance(v, str):
        return v[:n]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        if "DescriptionBlankTextString" in v:
            return str(v.get("DescriptionBlankTextString") or "")[:n]
        return {str(k)[:40]: compact(x, n) for k, x in list(v.items())[:12]}
    if isinstance(v, list):
        return [compact(x, n) for x in v[:12]]
    return str(v)[:n]


# ------------------------------------------------------------------ addresses known elsewhere
def js_array(text, name):
    m = re.search(r"window\." + name + r"\s*=\s*", text)
    if not m:
        return []

    def no_constant(x):
        raise ValueError(x)
    try:
        data, _ = json.JSONDecoder(parse_constant=no_constant).raw_decode(text, m.end())
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def urls_in_third_party(name, body):
    """Filing addresses in a third party's index (data only: JSON decoded, never run)."""
    out = []
    text = as_text(body) if body else ""
    if name == "or523":
        try:
            d = json.loads(text)
        except ValueError:
            d = {}
        for p in (d.get("polls") or []) + (d.get("excluded") or []) if isinstance(d, dict) else []:
            if isinstance(p, dict) and isinstance(p.get("pdf"), str):
                out.append(p["pdf"])
    elif name == "amitlev":
        for p in js_array(text, "BASE_POLLS_DATA"):
            if isinstance(p, dict) and isinstance(p.get("govilSourceUrl"), str):
                out.append(p["govilSourceUrl"])
        for t in js_array(text, "GOVIL_TOPICAL_DATA"):
            if isinstance(t, dict) and isinstance(t.get("sourceUrl"), str):
                out.append(t["sourceUrl"])
    elif name == "idoherling":
        for line in text.splitlines():
            cells = line.split("|")
            if len(cells) >= 3 and re.fullmatch(r"knesset_election\d{1,4}", cells[1].strip()):
                out.append(filing_url(cells[1].strip(), cells[2].strip()))
    return out


def urls_in_local(path, kind):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if kind == "reference":
        return [f.get("pdf") for f in d.get("filings", []) if isinstance(f, dict) and isinstance(f.get("pdf"), str)]
    return [p.get("filing") for p in d.get("polls", []) if isinstance(p, dict) and isinstance(p.get("filing"), str)]


# ------------------------------------------------------------------ the run
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref", default=REF, help="pipeline/reference/poll_filings_index.json")
    ap.add_argument("--polls", default=POLLS, help="site/data/polls_2026.json (its filing links)")
    ap.add_argument("--rewrite", action="append", default=[], metavar="FROM=TO", help="fetch FROM... from TO... (tests)")
    ap.add_argument("--only-rewritten", action="store_true")
    ap.add_argument("--no-curl", action="store_true", help="never retry through curl")
    ap.add_argument("--timeout", type=float, default=TIMEOUT)
    ap.add_argument("--max-pdfs", type=int, default=MAX_PDFS)
    ap.add_argument("--probe", type=int, default=15, help="items to probe after the last known, when the listing failed")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--deadline", type=float, default=DEADLINE,
                    help=f"seconds from the start after which nothing is asked (default {DEADLINE}; fetch.yml stops it at 1500)")
    a = ap.parse_args(argv)
    started = dt.datetime.now(dt.timezone.utc)
    os.makedirs(a.out, exist_ok=True)
    F = Fetcher(a.out, [tuple(r.split("=", 1)) for r in a.rewrite if "=" in r], a.only_rewritten, a.timeout,
                curl=not a.no_curl, deadline=a.deadline)

    # 1-2. the collector page and its listing
    page, html = F.request(COLLECTOR + "?skip=0", why="the collector page (its template id)")
    if html is not None:
        F.save(page, html, "files/page/knesset_election_polls_26.html")
    ids = template_ids(as_text(html) if html else "")
    tid, results, total, listing_notes = fetch_listing(F, ids)
    with open(os.path.join(a.out, "listing.json"), "w", encoding="utf-8") as f:
        json.dump({"collector": COLLECTOR, "api": API, "template_id": tid, "template_ids_tried": ids,
                   "total_results": total, "notes": listing_notes,
                   "results": [results[k] for k in sorted(results, key=item_number)]}, f, ensure_ascii=False, indent=1)

    # 3. third parties' indexes and the addresses already known here
    found = {}                                             # canonical url -> {"item", "file", "from": [...], "listing"}

    def add(url, source, listing=None):
        c = canon(url)
        if not c:
            return
        item, file, u = c
        rec = found.setdefault(u, {"item": item, "file": file, "url": u, "from": []})
        if source not in rec["from"]:
            rec["from"].append(source)
        if listing is not None:
            rec["listing"] = listing

    for item, r in results.items():
        for name in listing_files(r)[:MAX_PER_ITEM]:
            add(filing_url(item, name), "listing", {k: compact(v) for k, v in (r.get("Data") or {}).items()})
    third = {}
    for name, url in THIRD_PARTY.items():
        entry, body = F.request(url, why=f"{name}'s index of the collector (data only)")
        if body is not None:
            F.save(entry, body, f"files/third_party/{name}_{url.rsplit('/', 1)[-1]}")
        urls = urls_in_third_party(name, body)
        third[name] = {"url": url, "status": entry.get("status"), "error": entry.get("error"), "filings": len(urls)}
        for u in urls:
            add(u, name)
    for u in urls_in_local(a.ref, "reference"):
        add(u, "reference")
    for u in urls_in_local(a.polls, "polls"):
        add(u, "polls_2026")

    # 4. the probe, when the listing gave nothing
    probe = []
    if not results and a.probe > 0:
        probe = run_probe(F, found, a.probe)
        for u in probe:
            add(u, "probe")

    # 5. the PDFs (each item at most MAX_PER_ITEM addresses; the listing's first)
    per_item, jobs = {}, []
    for u, rec in sorted(found.items(), key=lambda kv: (-item_number(kv[1]["item"]), "listing" not in kv[1]["from"], kv[0])):
        if per_item.get(rec["item"], 0) >= MAX_PER_ITEM or len(jobs) >= a.max_pdfs:
            rec["error"] = "not fetched: limit"
            continue
        per_item[rec["item"]] = per_item.get(rec["item"], 0) + 1
        jobs.append(rec)
    pdftotext = shutil.which("pdftotext")

    def get_pdf(rec):
        entry, body = F.request(rec["url"], why="a filing", expect="pdf")
        for k in ("status", "error", "bytes", "sha256", "transport", "last_modified"):
            if k in entry:
                rec[k] = entry[k]
        if body is None:
            return
        rel = f"files/pdf/{rec['item']}__{safe_file(rec['file'])}"
        if F.save(entry, body, rel):
            rec["saved"] = rel
            if pdftotext and F.late():
                rec["text_error"] = "pdftotext not run: past the deadline (--deadline)"
            elif pdftotext:
                rec["text"] = to_text(pdftotext, os.path.join(a.out, rel), a.out, rec)

    with cf.ThreadPoolExecutor(max(1, a.workers)) as ex:
        list(ex.map(get_pdf, jobs))
    filings = sorted(found.values(), key=lambda r: (item_number(r["item"]), r["url"]))
    with open(os.path.join(a.out, "filings.json"), "w", encoding="utf-8") as f:
        json.dump(filings, f, ensure_ascii=False, indent=1)

    summary = {
        "fetcher": "poll_filings", "started": started.isoformat(timespec="seconds"),
        "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "collector": COLLECTOR, "page": {k: page.get(k) for k in ("status", "error", "transport", "bytes")},
        "listing": {"template_id": tid, "tried": ids, "total_results": total, "results": len(results),
                    "transport": sorted({e.get("transport") for e in F.entries if e["url"] == API and e.get("saved")} - {None}),
                    "notes": listing_notes},
        "third_party": third, "probe_found": probe, "curl": bool(F.curl), "pdftotext": bool(pdftotext),
        "filings": {"addresses": len(filings), "items": len({r["item"] for r in filings}),
                    "from_listing": sum(1 for r in filings if "listing" in r["from"]),
                    "pdfs_saved": sum(1 for r in filings if r.get("saved")),
                    "texts": sum(1 for r in filings if r.get("text")),
                    "failed": sum(1 for r in filings if r.get("error"))},
        "requests": len(F.entries), "deadline_s": a.deadline,
        "not_fetched_past_deadline": sum(1 for e in F.entries if e.get("error") == LATE), "rows": filings,
        "urls": [e for e in F.entries if e.get("why") != "a filing"],
    }
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(markdown(summary))
    s = summary["filings"]
    print(f"poll_filings: listing {len(results)} results (template {tid or 'none'}, TotalResults {total}); "
          f"{s['items']} filings known, {s['pdfs_saved']} PDFs saved, {s['failed']} failed; {len(F.entries)} requests")
    return 0


def run_probe(F, found, items):
    """Addresses after the last known item: Survey_<n>.pdf / Survey<n>.pdf for the next survey numbers. Stops after
    three items in a row with nothing."""
    last_item = max((item_number(r["item"]) for r in found.values()), default=0)
    nums = [int(m.group(1)) for r in found.values() for m in [re.match(r"Survey_?(\d{4})\.pdf$", r["file"], re.I)] if m]
    if not last_item or not nums:
        return []
    last_num, hits, misses = max(nums), [], 0
    for n in range(last_item + 1, last_item + 1 + items):
        if F.late():
            break
        hit = None
        for num in range(last_num + 1, last_num + 9):
            for name in (f"Survey_{num}.pdf", f"Survey{num}.pdf"):
                u = filing_url(f"knesset_election{n}", name)
                entry, body = F.request(u, why="probe: an item after the last known", expect="pdf")
                if body is not None:
                    hit = (u, num)
                    break
            if hit:
                break
        if hit:
            hits.append(hit[0])
            last_num, misses = hit[1], 0
        else:
            misses += 1
            if misses >= 3:
                break
    return hits


def to_text(pdftotext, path, out, rec):
    rel = "files/text/" + os.path.basename(path)[:-4] + ".txt"
    dest = os.path.join(out, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        p = subprocess.run([pdftotext, "-layout", "-enc", "UTF-8", path, dest], capture_output=True, timeout=90)
        if p.returncode == 0 and os.path.exists(dest):
            return rel
        rec["text_error"] = f"pdftotext exit {p.returncode}: {p.stderr.decode('utf-8', 'replace')[:120]}"
    except (OSError, subprocess.SubprocessError) as exc:
        rec["text_error"] = f"pdftotext: {exc.__class__.__name__}"
    return None


def cell(x):
    return str(x if x is not None else "").replace("|", "/").replace("\n", " ")[:120]


def markdown(s):
    L, ls, fs = [], s["listing"], s["filings"]
    L += [f"# CEC poll filings ({s['started'][:16].replace('T', ' ')} UTC)", "",
          f"Collector: {s['collector']}. Page: HTTP {cell(s['page'].get('status') or s['page'].get('error'))} "
          f"({cell(s['page'].get('transport'))}).", "",
          f"**Listing:** {ls['results']} results, TotalResults {cell(ls['total_results'])}, template "
          f"`{cell(ls['template_id'] or 'none answered')}` (tried {', '.join(ls['tried'])}), transport "
          f"{cell(', '.join(ls['transport']) or '-')}. curl on the runner: {s['curl']}; pdftotext: {s['pdftotext']}.", ""]
    for n in ls["notes"]:
        L.append(f"- {cell(n)}")
    if s.get("not_fetched_past_deadline"):
        L += ["", f"**Stopped at the deadline** ({s['deadline_s']:.0f} s from the start): {s['not_fetched_past_deadline']} "
              "requests not made (`not fetched: past the deadline` below); what came before is here."]
    L += ["", f"**Filings:** {fs['items']} items ({fs['addresses']} addresses): from the listing {fs['from_listing']}; "
          f"PDFs saved {fs['pdfs_saved']}; texts {fs['texts']}; failed or not fetched {fs['failed']}.", "",
          "| third party | HTTP | filings named |", "|---|---|---|"]
    for name, t in s["third_party"].items():
        L.append(f"| {name} ({cell(t['url'])}) | {cell(t['status'] or t['error'])} | {t['filings']} |")
    if s["probe_found"]:
        L += ["", "Found by the probe: " + ", ".join(s["probe_found"])]
    L += ["", "## Filings", "", "| item | file | found in | HTTP | bytes | saved / error |", "|---|---|---|---|---|---|"]
    for r in s["rows"]:
        L.append(f"| {r['item']} | {cell(r['file'])} | {cell(' '.join(r['from']))} | {cell(r.get('status'))} | "
                 f"{cell(r.get('bytes'))} | {cell(r.get('saved') or r.get('error'))} |")
    L += ["", "## Other requests", "", "| URL | HTTP | via | bytes | saved / error |", "|---|---|---|---|---|"]
    for e in s["urls"]:
        L.append(f"| {cell(e['url'])} | {cell(e.get('status'))} | {cell(e.get('transport'))} | {cell(e.get('bytes'))} | "
                 f"{cell(e.get('saved') or e.get('error') or e.get('note'))} |")
    L += ["", "Read with `python3 pipeline/build_poll_filings.py --fetched <this directory>` (pdftotext reads the PDFs "
          "where the runner had none). The files are the record.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
