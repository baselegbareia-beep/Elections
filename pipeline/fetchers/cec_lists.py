#!/usr/bin/env python3
"""Fetch the CEC's own pages for the 2026 candidate lists, their ballot letters and the surplus-vote agreements,
and compare them with pipeline/reference/lists_2026.json.

    python3 pipeline/fetchers/cec_lists.py --out DIR

The build container cannot reach gov.il; GitHub's runners can. Run from .github/workflows/fetch.yml on the request
{"workflow": "fetch", "what": "cec_lists"} (docs/ELECTION_DAY.md, "בקשות דרך ops-control"); the files land on the
ops-reports branch under reports/fetch/cec_lists/<YYYYMMDD-HHMM>/ and reports/fetch/cec_lists/latest/.

What it asks for:
  * gov.il pages are a single-page app: the HTML is a shell, the content comes from the content-pages API. Its
    address and the site's public client id are read from https://www.gov.il/ContentpageWebApi/client-config.js
    (else https://www.gov.il/ContentPageWebApi/api/content-pages), and every page is asked as
    <api>/<name>?culture=he with an Origin of https://www.gov.il (and ?chapterIndex=N for each chapter it lists);
  * the lists page candidates-lists-26, its chapters, the files it links to under BlobFolder (the approved ballot
    slips PDF among them), and the roster page of each of the 38 lists (cec_key in lists_2026.json);
  * the surplus-vote agreements: a few likely page names (surplus-agreements-26 and others), every gov.il page or
    file a fetched page links to whose address or text names עודפים / surplus / הסכם, bechirot.gov.il's pages;
  * data.gov.il's catalogue (package_search) for 26th-Knesset datasets on lists and agreements.
Only *.gov.il addresses are fetched; links elsewhere are listed. At most MAX_URLS requests, MAX_FILE bytes a file.

What it writes: DIR/files/<sha8>-<host>_<name> (each body once), DIR/summary.json and DIR/summary.md: per URL the
HTTP status, type, size, SHA-256 and saved name; per list the letters and title its CEC page shows against
lists_2026.json; the roster pages the lists page links to against the reference's (a list added, withdrawn or
renamed); on the pages about agreements, every line that names two lists (by name or letters) against the
reference's agreements. Reading the text is best effort (no PDF text: read the stored PDF with pdftotext); the files
are the record. Never raises on a single URL; exit 0 unless the script itself crashed.

Testing against a local server: --rewrite https://www.gov.il=http://127.0.0.1:8765/govil (repeatable) fetches from
the mock and keeps the real address in the summary; --only-rewritten skips every other host.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import hashlib
import html
import html.parser
import json
import os
import re
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF = os.path.join(ROOT, "pipeline", "reference", "lists_2026.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
GOVIL = "https://www.gov.il"
CLIENT_CONFIG = GOVIL + "/ContentpageWebApi/client-config.js"
API_FALLBACK = GOVIL + "/ContentPageWebApi/api/content-pages"
LISTS_PAGE = "candidates-lists-26"
# likely names of the agreements page (none confirmed: the CEC had not published it when this was written)
AGREEMENT_PAGES = ("surplus-agreements-26", "surplus-agreement-26", "surplus-votes-agreements-26", "surplus-votes-26",
                   "surplus-26", "agreements-26", "odafim-26", "heskemei-odafim-26", "heskemey-odafim-26")
HTML_PAGES = (GOVIL + "/he/pages/" + LISTS_PAGE, GOVIL + "/he/departments/guides/" + LISTS_PAGE,
              "https://bechirot.gov.il/", "https://www.bechirot.gov.il/", "https://votes26.bechirot.gov.il/")
DATA_GOV = "https://data.gov.il/api/3/action/package_search?rows=50&q="
DATA_QUERIES = ("עודפים", "רשימות המועמדים", "הכנסת ה-26", "knesset 26")
TOPIC = re.compile(r"עודפים|surplus|odafim|heskem|הסכם|agreement", re.I)
LISTS_TOPIC = re.compile(r"Approved|Slips|letters|אותיות|פתק|candidates-lists|רשימות[\s_-]*המועמדים", re.I)
ROSTER = re.compile(r"(?:list|iist)_?\d*$", re.I)    # a list's roster page: beyahad_list1, yashar_list_2, ..._iist29
MAX_URLS = 220
MAX_FILE = 15_000_000
MAX_TOTAL = 80_000_000
TIMEOUT = 30
HEB = "א-ת"


# ------------------------------------------------------------------ fetching
class Fetcher:
    def __init__(self, out, rewrite=(), only_rewritten=False, timeout=TIMEOUT, max_urls=MAX_URLS):
        self.out, self.files = out, os.path.join(out, "files")
        os.makedirs(self.files, exist_ok=True)
        self.rewrite, self.only_rewritten, self.timeout, self.max_urls = list(rewrite), only_rewritten, timeout, max_urls
        self.entries, self.seen, self.saved, self.total = [], {}, {}, 0
        self.lock = threading.Lock()

    def real_to_fetch(self, url):
        for a, b in self.rewrite:
            if url.startswith(a):
                return b + url[len(a):]
        return None if self.only_rewritten else url

    def get(self, url, headers=None, why=""):
        """One request: the entry (also kept in self.entries) and the body (None when nothing usable came)."""
        with self.lock:
            if url in self.seen:
                return self.seen[url]
            if len(self.seen) >= self.max_urls:
                return {"url": url, "error": "skipped: request limit"}, None
            entry = {"url": url, "why": why}
            self.seen[url] = (entry, None)
            self.entries.append(entry)
        body = None
        host = urllib.parse.urlsplit(url).hostname or ""
        target = self.real_to_fetch(url)
        if not (host == "gov.il" or host.endswith(".gov.il")):
            entry["error"] = "not fetched: not a gov.il address"
        elif target is None:
            entry["error"] = "not fetched: --only-rewritten"
        else:
            try:
                req = urllib.request.Request(target, headers={
                    "User-Agent": UA, "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8", "Accept-Encoding": "gzip, deflate", **(headers or {})})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    entry["status"], raw = r.status, r.read(MAX_FILE + 1)
                    entry["type"] = r.headers.get("Content-Type", "")
                    entry["last_modified"] = r.headers.get("Last-Modified")
                    final = r.geturl()
                    if final != target:
                        entry["redirected_to"] = final
                    enc = (r.headers.get("Content-Encoding") or "").lower()
                body = decode_body(raw, enc)
                if len(raw) > MAX_FILE:
                    entry["error"], body = f"over {MAX_FILE // 1_000_000} MB: not stored", None
            except urllib.error.HTTPError as exc:
                entry["status"], entry["type"] = exc.code, exc.headers.get("Content-Type", "") if exc.headers else ""
                try:
                    entry["head"] = text_head(decode_body(exc.read(4096), (exc.headers or {}).get("Content-Encoding", "")))
                except Exception:
                    pass
                entry["error"] = f"HTTP {exc.code}"
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError, ValueError) as exc:
                entry["error"] = f"{exc.__class__.__name__}: {str(getattr(exc, 'reason', exc))[:160]}"
            except Exception as exc:                      # anything else about one URL is that URL's problem
                entry["error"] = f"{exc.__class__.__name__}: {str(exc)[:160]}"
        if body is not None:
            entry["bytes"], entry["sha256"] = len(body), hashlib.sha256(body).hexdigest()
            entry["head"] = text_head(body)
            self.store(entry, body)
        with self.lock:
            self.seen[url] = (entry, body)
        return entry, body

    def store(self, entry, body):
        with self.lock:
            sha = entry["sha256"]
            if sha in self.saved:
                entry["saved"] = self.saved[sha]
                return
            if self.total + len(body) > MAX_TOTAL:
                entry["note"] = f"not stored: this run already stored {self.total / 1e6:.0f} MB"
                return
            name = safe_name(entry["url"], sha, entry.get("type", ""), body)
            with open(os.path.join(self.files, name), "wb") as f:
                f.write(body)
            self.saved[sha], self.total = "files/" + name, self.total + len(body)
            entry["saved"] = "files/" + name

    def many(self, jobs, workers=6):
        """[(url, headers, why)] in parallel: [(entry, body)] in the same order."""
        with cf.ThreadPoolExecutor(workers) as ex:
            return list(ex.map(lambda j: self.get(*j), jobs))


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
    if not body or body[:5] == b"%PDF-" or body[:2] == b"PK":
        return ""
    return re.sub(r"\s+", " ", as_text(body[:2000]))[:n]


def safe_name(url, sha, ctype, body):
    p = urllib.parse.urlsplit(url)
    base = urllib.parse.unquote(p.path.rstrip("/").rsplit("/", 1)[-1]) or "index"
    if p.query:
        base += "_" + urllib.parse.unquote(p.query)
    stem = re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9.-]+", "_", f"{p.hostname}_{base}")).strip("._")[:90]
    if not re.search(r"\.[A-Za-z0-9]{2,5}$", stem):
        stem += (".pdf" if body[:5] == b"%PDF-" else ".json" if "json" in ctype or body.lstrip()[:1] in (b"{", b"[")
                 else ".html" if "html" in ctype else ".zip" if body[:2] == b"PK" else ".js" if "javascript" in ctype else ".txt")
    return f"{sha[:8]}-{stem}"


# ------------------------------------------------------------------ reading what came
class Text(html.parser.HTMLParser):
    """Visible text, one line per block (table cells joined with ' | '), and the links with their text."""
    BLOCK = {"p", "div", "tr", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "ul", "ol", "dd", "dt"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.cur, self.links, self.a, self.skip = [], [], [], None, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.flush()
        elif tag in ("td", "th") and self.cur:
            self.cur.append(" | ")
        if tag == "a":
            self.a = [dict(attrs).get("href") or "", []]
        elif tag in ("img", "iframe", "embed", "source") and dict(attrs).get("src"):
            self.links.append((dict(attrs)["src"], ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.flush()
        if tag == "a" and self.a:
            self.links.append((self.a[0], " ".join("".join(self.a[1]).split())))
            self.a = None

    def handle_data(self, data):
        if self.skip:
            return
        self.cur.append(data)
        if self.a is not None:
            self.a[1].append(data)

    def flush(self):
        s = " ".join("".join(self.cur).split())
        if s.strip(" |"):
            self.lines.append(s)
        self.cur = []


def read_html(s):
    t = Text()
    try:
        t.feed(s)
        t.close()
    except Exception:                                     # a broken page still gives what was read so far
        pass
    t.flush()
    return t.lines, t.links


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def read_body(entry, body):
    """(lines of text, [(href, link text)], the parsed JSON or None) of a fetched body."""
    if body is None or body[:5] == b"%PDF-" or body[:2] == b"PK":
        return [], [], None
    s = as_text(body)
    doc = None
    if s.lstrip()[:1] in ("{", "["):
        try:
            doc = json.loads(s)
        except ValueError:
            doc = None
    if doc is None:
        return (*read_html(s), None)
    lines, links = [], []
    for x in strings(doc):
        if "<" in x and ">" in x:
            ln, lk = read_html(x)
            lines += ln
            links += lk
        elif x.strip():
            lines.append(" ".join(x.split()))
            if re.match(r"(https?://|/BlobFolder/|/he/)", x.strip()):
                links.append((x.strip(), ""))
    return lines, links, doc


def absolute(href, base):
    href = html.unescape((href or "").strip())
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    u = urllib.parse.urljoin(base if base.startswith("http") else GOVIL + "/", href)
    return u.split("#")[0] if u.startswith(("http://", "https://")) else None


def page_name(url):
    """The content-page name of a gov.il page address (/he/pages/<name>, /he/departments/guides/<name>), else None."""
    m = re.match(r"https?://(?:www\.)?gov\.il/(?:he|ar|en)/(?:pages|departments/guides|Departments/Guides)/([^/?#]+)", url, re.I)
    return m.group(1) if m else None


# ------------------------------------------------------------------ comparing with lists_2026.json
def names_of(entry):
    """The names a list goes by in CEC text, longest first: its aliases (as given) and its official name, also cut
    at בראשות / בהנהגת (those two only when 4 characters or more: שמע, בטח are words too)."""
    off = (entry.get("official_name") or "").strip()
    cut = {off, re.split(r"\s+(?:בראשות|בהנהגת)\s+", off)[0].strip(" –-")} if off else set()
    out = {n for n in cut if len(n) >= 4} | {n for n in entry.get("aliases") or [] if len(n) >= 2}
    return sorted(out, key=len, reverse=True)


def lists_named(line, ref_lists):
    """The letters of the lists a line names: by name (longest first, no overlaps); by letters standing alone only
    in a short line, a table row, that names fewer than two by name (רק, עם, כן, די, אמת and דרך are also words)."""
    found, taken = [], []
    for n, L in sorted(((n, e["letters"]) for e in ref_lists for n in names_of(e)), key=lambda x: -len(x[0])):
        for m in re.finditer(re.escape(n), line):
            if not any(a < m.end() and m.start() < b for a, b in taken):
                taken.append((m.start(), m.end()))
                if L not in found:
                    found.append(L)
    if len(found) >= 2 or len(line.replace("|", " ").split()) > 6:
        return found
    for e in ref_lists:
        L = e["letters"]
        if L not in found and any(not any(a < m.end() and m.start() < b for a, b in taken)
                                  for m in re.finditer(rf"(?<![{HEB}\"'״׳]){re.escape(L)}(?![{HEB}\"'״׳-])", line)):
            found.append(L)
    return found


def letters_on_page(lines):
    """Letters a list's own page states (אותיות הרשימה: ...)."""
    got = []
    for ln in lines:
        for m in re.finditer(rf"(?:אותיות|אות)(?:\s+(?:הרשימה|הקלפי|הפתק))?\s*[:\-–]\s*[\"'״׳]?([{HEB}]{{1,4}})", ln):
            if m.group(1) not in got:
                got.append(m.group(1))
    return got


def compare_lists(ref, pages):
    """Per list: what its CEC roster page says against the reference."""
    rows = []
    for e in ref.get("lists", []):
        entry, lines = pages.get(e["cec_key"], (None, []))
        title = ""
        if entry is not None and entry.get("doc") is not None:
            title = str(((entry["doc"].get("contentHead") or {}) if isinstance(entry["doc"], dict) else {}).get("title") or "")
        seen = letters_on_page(lines)
        text = "\n".join(lines)
        rows.append({"letters": e["letters"], "id": e.get("id"), "cec_key": e["cec_key"],
                     "status": entry.get("status") if entry else None, "error": entry.get("error") if entry else "not asked",
                     "title": title[:160], "letters_on_page": seen,
                     "letters_match": (e["letters"] in seen) if seen else None,
                     "name_on_page": any(n in text for n in names_of(e)) if lines else None})
    return rows


def find_agreements(ref, docs):
    """Lines that name exactly two lists, on pages whose text is about surplus-vote agreements."""
    expected = {frozenset(a["lists"]) for a in ref.get("agreements", [])}
    found = {}
    for url, lines in docs:
        text = "\n".join(lines)
        if not TOPIC.search(text) and not TOPIC.search(url):
            continue
        for ln in lines:
            named = lists_named(ln, ref.get("lists", []))
            if len(named) == 2:
                k = frozenset(named)
                found.setdefault(k, {"lists": named, "lines": [], "urls": []})
                if len(found[k]["lines"]) < 3:
                    found[k]["lines"].append(ln[:200])
                if url not in found[k]["urls"]:
                    found[k]["urls"].append(url)
    return {"seen": list(found.values()),
            "expected_seen": [sorted(k) for k in expected if k in found],
            "expected_not_seen": [sorted(k) for k in expected if k not in found],
            "not_expected": [v["lists"] for k, v in found.items() if k not in expected]}


# ------------------------------------------------------------------ the run
def api_config(F):
    """(content-pages API base, client id) from gov.il's client-config.js; the www fallback otherwise."""
    entry, body = F.get(CLIENT_CONFIG, why="the content-pages API address and the site's public client id")
    base, cid = API_FALLBACK, ""
    if body:
        m = re.search(r"govilRunConfig'?\"?\]\s*=\s*(\{.*?\})\s*;", as_text(body), re.S)
        if m:
            try:
                cfg = json.loads(m.group(1))
                if str(cfg.get("contentPageWebApi") or "").startswith("http"):
                    base = cfg["contentPageWebApi"].rstrip("/") + "/api/content-pages"
                cid = str(cfg.get("clientId") or "").strip()
            except ValueError:
                entry["note"] = "govilRunConfig is not JSON"
    return base, cid


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref", default=REF, help="the reference file (pipeline/reference/lists_2026.json)")
    ap.add_argument("--rewrite", action="append", default=[], metavar="FROM=TO", help="fetch FROM... from TO... (tests)")
    ap.add_argument("--only-rewritten", action="store_true")
    ap.add_argument("--timeout", type=float, default=TIMEOUT)
    ap.add_argument("--max-urls", type=int, default=MAX_URLS)
    a = ap.parse_args(argv)
    started = dt.datetime.now(dt.timezone.utc)
    os.makedirs(a.out, exist_ok=True)
    try:
        ref = json.load(open(a.ref, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        ref, ref_err = {}, f"{exc.__class__.__name__}: {exc}"
    else:
        ref_err = None
    F = Fetcher(a.out, [tuple(r.split("=", 1)) for r in a.rewrite if "=" in r], a.only_rewritten, a.timeout, a.max_urls)
    base, cid = api_config(F)
    hdr = {"Origin": GOVIL, "Referer": GOVIL + "/", "Accept": "application/json", **({"x-client-id": cid} if cid else {})}

    def api(name, chapter=None, why=""):
        q = "?culture=he" + (f"&chapterIndex={chapter}" if chapter else "")
        return (f"{base}/{urllib.parse.quote(name)}{q}", hdr, why)

    texts, pages, queued = [], {}, set()

    def take(results):
        out = []
        for entry, body in results:
            lines, links, doc = read_body(entry, body)
            if doc is not None:
                entry["doc"] = doc
            texts.append((entry["url"], lines))
            out.append((entry, lines, links))
        return out

    # 1. the lists page and its chapters, the agreement pages guessed, the HTML pages
    first = take(F.many([api(LISTS_PAGE, why="the CEC's lists page")]
                        + [api(n, why="a likely name of the agreements page") for n in AGREEMENT_PAGES]
                        + [(u, None, "the page itself (a gov.il page is a shell without the API)") for u in HTML_PAGES]))
    chapters = set()
    for entry, lines, links in first[:1]:
        for s in strings(entry.get("doc") or {}):
            chapters.update(int(c) for c in re.findall(r"chapterIndex=(\d{1,2})", s))
    more = take(F.many([api(LISTS_PAGE, c, why="a chapter of the lists page") for c in sorted(chapters) if 1 < c <= 12]))
    # 2. each list's roster page, and the approved ballot slips
    keys = [e["cec_key"] for e in ref.get("lists", []) if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(e.get("cec_key", "")))]
    rosters = take(F.many([api(k, why="the list's roster page") for k in keys]))
    for k, (entry, lines, _) in zip(keys, rosters):
        pages[k] = (entry, lines)
    slips = (ref.get("cec") or {}).get("approved_slips_pdf")
    frontier = first + more + rosters + (take([F.get(slips, why="the approved ballot slips")]) if slips else [])
    # the roster pages the lists page links to, against the reference's (a list withdrawn, renamed or added)
    indexed = sorted({n for entry, _, links in first[:1] + more for href, _ in links
                      for n in [page_name(absolute(href, GOVIL + "/") or "")] if n and ROSTER.search(n)})
    # 3. what the pages link to, two levels deep: gov.il files and pages about the lists or the agreements
    for _level in range(2):
        jobs = []
        for entry, lines, links in frontier:
            # a page's content from the API links relative to www.gov.il, not to the API's host
            at = GOVIL + "/" if entry.get("url", "").startswith(base) else entry.get("url", GOVIL + "/")
            for href, label in links:
                u = absolute(href, at)
                name = page_name(u or "")
                if not u or u in queued or u in F.seen or not (TOPIC.search(f"{u} {label}") or LISTS_TOPIC.search(f"{u} {label}")
                                                               or (name and ROSTER.search(name) and name not in pages)):
                    continue
                queued.add(u)
                if name and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name):
                    jobs.append(api(name, why=f"linked: {label[:60]}"))
                    if "/pages/" not in u:                # a guide: its API address is not known, the page itself too
                        jobs.append((u, None, f"linked: {label[:60]}"))
                elif "/BlobFolder/" in u or "bechirot.gov.il" in u or re.search(r"\.(pdf|xlsx?|csv|docx?|json)(\?|$)", u, re.I):
                    jobs.append((u, None, f"linked: {label[:60]}"))
        if not jobs:
            break
        frontier = take(F.many(jobs[:50]))
    # data.gov.il's catalogue
    for q in DATA_QUERIES:
        entry, body = F.get(DATA_GOV + urllib.parse.quote(q), why="data.gov.il catalogue")
        for res in datagov_resources(body):
            if TOPIC.search(res["name"]) or LISTS_TOPIC.search(res["name"]):
                take([F.get(res["url"], why=f"data.gov.il resource: {res['name'][:60]}")])
    # 4. what it says
    list_rows = compare_lists(ref, pages)
    agreements = find_agreements(ref, texts)
    for e in F.entries:
        e.pop("doc", None)
    summary = {
        "fetcher": "cec_lists", "started": started.isoformat(timespec="seconds"),
        "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "reference": os.path.relpath(a.ref, ROOT) if a.ref.startswith(ROOT) else a.ref, "reference_error": ref_err,
        "content_api": base, "client_id_found": bool(cid),
        "requests": len(F.entries), "answered": sum(1 for e in F.entries if e.get("status") == 200),
        "stored": sorted(set(F.saved.values())),
        "index": {"roster_pages_linked": len(indexed), "not_in_reference": [k for k in indexed if k not in pages],
                  "not_linked": [k for k in pages if indexed and ROSTER.search(k) and k not in indexed]},
        "lists": list_rows, "agreements": agreements, "urls": F.entries,
    }
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(markdown(summary))
    print(f"cec_lists: {summary['requests']} requests, {summary['answered']} answered (200), {len(summary['stored'])} files "
          f"stored; roster pages read: {sum(1 for r in list_rows if r['status'] == 200)}/{len(list_rows)}; letters that "
          f"differ: {sum(1 for r in list_rows if r['letters_match'] is False)}; expected agreements seen: "
          f"{len(agreements['expected_seen'])}/{len(agreements['expected_seen']) + len(agreements['expected_not_seen'])}")
    return 0


def datagov_resources(body):
    try:
        d = json.loads(as_text(body)) if body else {}
    except ValueError:
        return []
    out = []
    for p in ((d.get("result") or {}).get("results") or []) if isinstance(d, dict) else []:
        title = f"{p.get('title') or ''} {p.get('name') or ''}"
        for r in p.get("resources") or []:
            if isinstance(r, dict) and str(r.get("url", "")).startswith("http"):
                out.append({"name": f"{title} {r.get('name') or ''}".strip(), "url": r["url"]})
    return out[:40]


def cell(x):
    return str(x if x is not None else "").replace("|", "/").replace("\n", " ")[:120]


def markdown(s):
    L = [f"# CEC lists and surplus agreements ({s['started'][:16].replace('T', ' ')} UTC)", "",
         f"{s['requests']} requests, {s['answered']} answered with 200, {len(s['stored'])} files stored under files/. "
         f"Content-pages API: `{s['content_api']}` (client id found: {s['client_id_found']}).", ""]
    if s.get("reference_error"):
        L += [f"**The reference file could not be read:** {cell(s['reference_error'])}", ""]
    rows, ix = s["lists"], s["index"]
    bad = [r for r in rows if r["letters_match"] is False]
    L += ["## Lists", "",
          f"The lists page links to {ix['roster_pages_linked']} roster pages; **not in lists_2026.json: "
          f"{len(ix['not_in_reference'])}** {cell(' '.join(ix['not_in_reference']))}; in it but not linked: "
          f"{len(ix['not_linked'])} {cell(' '.join(ix['not_linked']))}.", "",
          f"Roster pages read: {sum(1 for r in rows if r['status'] == 200)} of {len(rows)}; letters stated on the page: "
          f"{sum(1 for r in rows if r['letters_on_page'])}; **different from lists_2026.json: {len(bad)}**.", "",
          "| letters (reference) | list | HTTP | page title | letters on the page | match |", "|---|---|---|---|---|---|"]
    for r in rows:
        if r["id"] or r["letters_match"] is False:
            L.append(f"| {cell(r['letters'])} | {cell(r['id'] or r['cec_key'])} | {cell(r['status'] or r['error'])} | "
                     f"{cell(r['title'])} | {cell(' '.join(r['letters_on_page']))} | "
                     f"{'yes' if r['letters_match'] else 'NO' if r['letters_match'] is False else '-'} |")
    ag = s["agreements"]
    L += ["", "## Surplus-vote agreements", "",
          f"Expected (lists_2026.json) and seen on a CEC page: {len(ag['expected_seen'])}; expected, not seen: "
          f"{len(ag['expected_not_seen'])}; seen, not expected: **{len(ag['not_expected'])}**.", ""]
    for v in ag["seen"]:
        L.append(f"- {' + '.join(v['lists'])}: {cell(v['lines'][0])} ({cell(v['urls'][0])})")
    if not ag["seen"]:
        L.append("- no CEC page read here names two lists in one line about agreements (the page may not be out, may "
                 "be a PDF: read the stored files)")
    L += ["", "## Requests", "", "| URL | HTTP | type | bytes | saved / error |", "|---|---|---|---|---|"]
    for e in s["urls"]:
        L.append(f"| {cell(e['url'])} | {cell(e.get('status'))} | {cell((e.get('type') or '').split(';')[0])} | "
                 f"{cell(e.get('bytes'))} | {cell(e.get('saved') or e.get('error') or e.get('note'))} |")
    L += ["", "Reading the text is best effort; PDFs are stored, not read (`pdftotext -layout`). The files are the record.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
