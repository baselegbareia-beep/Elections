#!/usr/bin/env python3
"""Fetch the CEC's own pages and files for the 2026 candidate lists, their ballot letters and the surplus-vote
agreements, and compare them with pipeline/reference/lists_2026.json (read, never written: the lead updates it after
reading summary.md).

    python3 pipeline/fetchers/cec_lists.py --out DIR
    python3 pipeline/fetchers/cec_lists.py --reread DIR --out DIR2      # DIR's files read again, nothing asked

The build container cannot reach gov.il; GitHub's runners can, but www.gov.il's WAF answers them 403 as well (16.10),
while www.bechirot.gov.il and data.gov.il answer. Run from .github/workflows/fetch.yml on the request {"workflow":
"fetch", "what": "cec_lists"} (docs/ELECTION_DAY.md, "בקשות דרך ops-control"); the files land on the ops-reports branch
under reports/fetch/cec_lists/<YYYYMMDD-HHMM>/ and reports/fetch/cec_lists/latest/.

What it asks for, in this order:
  1. gov.il. Its pages are a single-page app: the HTML is a shell, the content comes from the content-pages API. Its
     address and the site's public client id are read from https://www.gov.il/ContentpageWebApi/client-config.js
     (else https://www.gov.il/ContentPageWebApi/api/content-pages), and every page is asked as <api>/<name>?culture=he
     with an Origin of https://www.gov.il (and ?chapterIndex=N for each chapter it lists): the lists page
     candidates-lists-26, its chapters, the files it links to under BlobFolder (the approved ballot slips PDF among
     them), the roster page of each of the 38 lists (cec_key in lists_2026.json), a few likely names of the agreements
     page (surplus-agreements-26 and others), and every gov.il page or file these link to whose address or text names
     the lists or עודפים / surplus / הסכם (two levels); then data.gov.il's catalogue (package_search);
  2. www.bechirot.gov.il, the CEC's own site (Umbraco), crawled within bounds: same host only (its redirects too),
     MAX_PAGES pages at most (HTML, the site's API answers, MAX_API of them, robots.txt, sitemaps, MAX_SITEMAPS of
     them; each redirect counted), MAX_FILES files (PDF, XLSX, XLS, DOCX, DOC, CSV) and MAX_SCRIPTS scripts, one
     request a second (--polite, redirects too). Its pages draw their menus and blocks in the browser: the HTML has no
     links, only elements with component-query / currentPageId attributes and the scripts that fill them
     (/dist/<Name>.bundle.js for #PageHeader, #Banner-..., #ContentShow-...), so the crawl reads those scripts for the
     API addresses they call (/umbraco/api/..., /api/...) and asks each with the attributes of the elements it fills:
     a page's blocks for every page (its content), its header, footer and share bar once (the same on every page).
     It starts from robots.txt (its Disallow rules for every agent are kept, and a longer Crawl-delay), the home page,
     sitemap.xml, Umbraco's content listing (the Delivery API, a 404 where it is off), the links gov.il pages give to
     the site, and the archive's index of the site (the Wayback Machine's CDX listing: addresses only, each then asked
     of the live site); it follows the links whose address or text is about the 26th Knesset's candidate lists
     (רשימות המועמדים), ballot letters, surplus-vote agreements (הסכמי עודפים), rosters, notices (הודעות, רשומות,
     ילקוט הפרסומים), not those about an earlier Knesset only; files when their link is about those or the page
     linking them is. Links to other gov.il hosts go to part 3, links elsewhere are listed. lists_2026.json's
     cec.crawl_seeds (a list of addresses, none yet) are asked too: where to start once the site's structure is known;
  3. the Wayback Machine, for every gov.il address that answered 403 (the lists page first, then what pages and
     snapshots link to, the rosters, the guessed names): the closest snapshot from
     https://archive.org/wayback/available?url=... (for the lists page and what is linked, the latest 200 in the CDX
     index when the closest is not a 200, or there is none), then the raw snapshot
     https://web.archive.org/web/<timestamp>id_/<address>, read as the page it is a copy of and marked "archive
     snapshot <timestamp>", never as the live page; what a snapshot links to is asked live, then here. Also the
     archive's listing of the lists page's BlobFolder. One request every --archive-gap seconds (archive.org allows
     about 15 a minute); a 429 ends this part. MAX_LOOKUPS lookups and MAX_SNAPSHOTS snapshots at most.
Parts 2 and 3 take turns (twice more at most) while either has something new. Only *.gov.il addresses and
archive.org's are fetched, and a redirect is followed only to the same kind (gov.il to gov.il, archive.org to
archive.org, the crawl's to its own site), MAX_HOPS at most, else the body is not read. At most MAX_URLS requests,
MAX_FILE bytes a file (unpacked too), and nothing asked after --deadline (DEADLINE, 20 minutes from the start; a body
still coming, also one dripped a few bytes at a time, is cut GRACE seconds later): the summary is then written with
what came (pipeline/fetchers/__init__.py: fetch.yml stops it at 25).

What it reads: HTML and JSON (the text, one line a block, table cells joined with ' | ', and the links: a JSON
answer's Url / Link with its Title too), PDF (pdftotext -layout where it is installed, else pypdf where it can be
imported; a PDF that comes out right to left, its letters backwards, is turned around), XLSX and DOCX (their XML, a
row a line), CSV. XLS and DOC are stored, not read; so are PDFs where neither reader is (GitHub's runner may have
neither: --reread reads the stored files again where they are).

What it writes: DIR/files/<sha8>-<host>_<name> (each body once), DIR/summary.json and DIR/summary.md. On top, per list
the letters lists_2026.json gives and the CEC pages or files that confirm them (a line that names the list with its
letters alone in a table cell, after אותיות, or in brackets; its roster page's אותיות הרשימה), per agreement those with
a line naming its two lists, each with its address and kind (live page, live file, archive snapshot <timestamp>); what
no official page or file read here confirms, what shows other letters, a pair the reference lacks. Only a text about
the 26th Knesset counts: its address or text says so (26, העשרים ושש; 2026 where it names no earlier Knesset), it is a
roster page, or the page linking to it is and it names no earlier Knesset. Then the crawl, the archive part, the
roster pages against the reference (a list added, withdrawn or renamed), and per URL the HTTP status, type, size,
SHA-256, saved name and how it was read. Reading is best effort; the files are the record. Never raises on a single
URL; exit 0 unless the script itself crashed.

Testing against a local server: --rewrite https://www.gov.il=http://127.0.0.1:8765/govil (repeatable) fetches from
the mock and keeps the real address in the summary; --only-rewritten skips every other host.
"""
import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import hashlib
import heapq
import html
import html.parser
import io
import itertools
import json
import logging
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
import urllib.robotparser
import xml.etree.ElementTree as ET
import zipfile
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
# www.bechirot.gov.il is not here: the crawl (part 2) asks it
HTML_PAGES = (GOVIL + "/he/pages/" + LISTS_PAGE, GOVIL + "/he/departments/guides/" + LISTS_PAGE,
              "https://votes26.bechirot.gov.il/")
DATA_GOV = "https://data.gov.il/api/3/action/package_search?rows=50&q="
DATA_QUERIES = ("עודפים", "רשימות המועמדים", "הכנסת ה-26", "knesset 26")
TOPIC = re.compile(r"עודפים|surplus|odafim|heskem|הסכם|agreement", re.I)
# an agreement's own line names the agreement (or sits under a heading that does, within AGREEMENT_CONTEXT lines);
# the lines of the disqualification proceedings name two lists too ("פ\"ר 5/26 הליכוד נ' רשימת רע\"ם", read 17.10)
AGREEMENT_LINE = re.compile(r"עודפים|surplus|odafim", re.I)   # "הסכם בדבר עודפים", "הסכמי עודפים"; not "בהסכמת"
PROCEEDINGS = re.compile(r"(?:^|\s)נ['׳’]\s|פ[\"״]\s?[מר]\s*\d|פסיל|עתיר|ערעור|בקשות?\s+ל?פסילה|disqualif", re.I)
AGREEMENT_CONTEXT = 3
ENUMERATION = re.compile(r"^\W*[א-ת]{1,2}\s*[.)](?=\s*[א-ת\"])\s*")   # "ג. עליזה אוזן נציגת שס": an item letter, not UTJ's ג
LISTS_TOPIC = re.compile(r"Approved|Slips|letters|אותיות|פתק|candidates-lists|רשימות[\s_-]*המועמדים", re.I)
ROSTER = re.compile(r"(?:list|iist)_?\d*$", re.I)    # a list's roster page: beyahad_list1, yashar_list_2, ..._iist29
MAX_URLS = 420
MAX_HOPS = 5                   # redirects followed for one request (each in its host's turn)
MAX_FILE = 15_000_000
MAX_TOTAL = 80_000_000
TIMEOUT = 30
DEADLINE = 20 * 60             # seconds from the start (pipeline/fetchers/__init__.py: fetch.yml stops it at 25 minutes)
GRACE = 60                     # a body still coming at the deadline is cut this much later
HEB = "א-ת"
# part 2: www.bechirot.gov.il
BECHIROT = "https://www.bechirot.gov.il"
SITE_HOSTS = ("www.bechirot.gov.il", "bechirot.gov.il")
MAX_PAGES = 60                 # HTML pages, API answers, robots.txt and sitemaps (and the redirects among them)
MAX_API = 35                   # of those, the site's API answers (a page's content is in them)
MAX_SITEMAPS = 5               # of those, sitemaps (an index listing thousands would take every page)
MAX_FILES = 40
MAX_SCRIPTS = 12
MAX_ENDPOINTS = 20
POLITE = 1.0                   # seconds between two requests to the site
# Umbraco's own content listing (its pages' paths and names), when the site has the Delivery API on (a 404 if not)
DELIVERY_API = ("/umbraco/delivery/api/v2/content?take=100", "/umbraco/delivery/api/v1/content?take=100")
# part 3: the Wayback Machine
AVAILABLE = "https://archive.org/wayback/available"
WAYBACK = "https://web.archive.org"
CDX = WAYBACK + "/cdx/search/cdx"
ARCHIVE_HOSTS = ("archive.org", "web.archive.org")
ARCHIVE_GAP = 4.0              # seconds between two requests to archive.org (about 15 a minute; a 429 ends part 3)
MAX_LOOKUPS = 70
MAX_SNAPSHOTS = 40
PDF_TIMEOUT = 60
MAX_LINES = 20_000             # lines kept of one text

# about the 26th Knesset: in a text, and in an address (unquoted; not a hex id's "-26ab"); the year alone only in a
# text that names no earlier Knesset (k26_of: "עודכן 3 בינואר 2026" on a page about the 25th is not)
K26_TEXT = re.compile(r"(?:כנסת|לכנסת|הכנסת)\s*ה?\s*[-־–]?\s*26(?!\d)|העשרים\s+ו?שש|knesset\W{0,3}26(?!\d)|26th\s+knesset", re.I)
K26_YEAR = re.compile(r"(?<![\d/.-])2026(?![\d/.-])")
K26_URL = re.compile(r"(?:[-_/]|knesset|bechirot|elections?|votes|media)26(?=$|[/?#._&=-])", re.I)
OLD_KNESSET = re.compile(r"(?:כנסת|לכנסת|הכנסת)\s*ה?\s*[-־–]?\s*(?:1\d|2[0-5])(?!\d)|knesset\W{0,3}(?:1\d|2[0-5])(?!\d)"
                         r"|(?:bechirot|elections?|votes|media)[-_]?(?:1\d|2[0-5])(?=$|[/?#._&=-])", re.I)
# the crawl's topics: the lists, letters, agreements, rosters, notices (0); the 26th Knesset (1); weaker (2)
CRAWL_TOPIC = re.compile(r"רשימ\S*\s*(?:ה)?מועמד|מועמד|אותיות|פתק|עודפים|הסכם|הסכמ|ילקוט\s*הפרסומים|רשומות|הודע|candidat|ballot"
                         r"|letter|surplus|agreement|odafim|heskem|notice|announce|yalkut|reshumot|\blists?\b", re.I)
CRAWL_WEAK = re.compile(r"רשימות|רשימה|פרסומים|מסמכים|בחירות\s*לכנסת|publication|document", re.I)
FILE_EXT = re.compile(r"\.(pdf|xlsx?|docx?|csv)$", re.I)
ASSET_EXT = re.compile(r"\.(css|js|map|png|jpe?g|gif|svg|ico|webp|bmp|woff2?|ttf|eot|otf|mp4|mp3|webm|avi|mov)$", re.I)
SCRIPT_SKIP = re.compile(r"ruxit|bootstrap|jquery|gtag|googletag|analytics|accessibility|countup|polyfill", re.I)
# an API address in a script: "/umbraco/api/MiniSite/GetMenu?currentPageId=", '/api/items', `/umbraco/surface/...`
API_LIT = re.compile(r"""(["'`])((?:https?://[^"'`\s]{1,80}?)?/?(?:umbraco/(?:api|surface|delivery/api/v\d)|api)/"""
                     r"""[^"'`\s<>\\]{1,200}?)\1""", re.I)
BIDI = re.compile("[%s]" % "".join(map(chr, (0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A)))))  # LRM, RLE...
FILE_READS = ("pdftotext", "pypdf", "xlsx", "docx", "csv")
# answers that are not texts to compare (an index, a lookup, a script, robots.txt): --reread leaves them as they were
NOT_TEXT = ("config", "data.gov.il catalogue", "crawl robots", "crawl sitemap", "crawl script", "archive lookup", "archive index")


# ------------------------------------------------------------------ fetching
def fetchable(host):
    return host == "gov.il" or host.endswith(".gov.il") or host in ARCHIVE_HOSTS


def family(u):
    """Where a redirect from u may go (Fetcher.get's default): "gov.il" for a gov.il address, "archive.org" for the
    archive's; None elsewhere."""
    host = (urllib.parse.urlsplit(u or "").hostname or "").lower()
    return "archive.org" if host in ARCHIVE_HOSTS else "gov.il" if host == "gov.il" or host.endswith(".gov.il") else None


class NotFollowed(Exception):
    """A redirect Fetcher.get did not follow: its status, the (real) address it pointed to, and why."""

    def __init__(self, code, url, why):
        super().__init__(f"redirect ({code}) to {url[:160]} not followed: {why}")
        self.code, self.url = code, url


class Redirects(urllib.request.HTTPRedirectHandler):
    """Redirects followed only where the request's allow (of the real address) says, each in its host's turn (the
    polite gap, the deadline) and counted in its entry's hops, its hops at most: an off-site body is never read as the
    page asked. Those three ride on the request (req.rules: entry, allow, hops), the opener is the Fetcher's."""
    max_redirections = MAX_HOPS

    def __init__(self, F):
        super().__init__()
        self.F = F

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        entry, allow, hops = req.rules
        real, seen = self.F.real_of(newurl), getattr(req, "redirect_dict", {})     # urllib's loop check, done first
        why = ("not the same site" if not allow(real) else "--only-rewritten" if self.F.real_to_fetch(real) is None
               else "a loop" if seen.get(newurl, 0) >= self.max_repeats
               else "over the limit of redirects" if entry.get("hops", 0) >= hops or len(seen) >= self.max_redirections
               else None if self.F.turn(urllib.parse.urlsplit(real).hostname) else "past the deadline (--deadline)")
        if why:
            fp.close()
            raise NotFollowed(code, real, why)
        entry["hops"] = entry.get("hops", 0) + 1
        new = super().redirect_request(req, fp, code, msg, headers, iri(self.F.real_to_fetch(real)))
        if new is not None:
            new.rules = req.rules
        return new


def host_key(host):
    """The host a polite gap is kept for: www.bechirot.gov.il and bechirot.gov.il are one, archive.org's hosts one."""
    host = (host or "").lower()
    if host.endswith("archive.org"):
        return "archive.org"
    return host[4:] if host.startswith("www.") else host


def iri(u):
    """u with what a request line cannot carry (non-ASCII letters, spaces) percent-encoded; its %XX kept."""
    return urllib.parse.quote(u, safe=":/?#[]@!$&'()*+,;=%~")


class Fetcher:
    def __init__(self, out, rewrite=(), only_rewritten=False, timeout=TIMEOUT, max_urls=MAX_URLS, deadline=DEADLINE,
                 gaps=None):
        self.out, self.files = out, os.path.join(out, "files")
        os.makedirs(self.files, exist_ok=True)
        self.rewrite, self.only_rewritten, self.timeout, self.max_urls = list(rewrite), only_rewritten, timeout, max_urls
        self.entries, self.seen, self.saved, self.total = [], {}, {}, 0
        self.stop_at, self.late = time.monotonic() + deadline, 0      # late: requests not made, past the deadline
        self.gaps, self.next_at = dict(gaps or {}), {}                  # seconds between two requests to one host_key
        self.lock = threading.Lock()
        self.opener = urllib.request.build_opener(Redirects(self))     # once: building one makes an SSL context

    def real_to_fetch(self, url):
        for a, b in self.rewrite:
            if url.startswith(a):
                return b + url[len(a):]
        return None if self.only_rewritten else url

    def real_of(self, target):
        """The real address of a fetched one (a redirect's target under --rewrite); None for None."""
        for a, b in self.rewrite:
            if target and target.startswith(b):
                return a + target[len(b):]
        return target

    def past(self):
        return time.monotonic() >= self.stop_at

    def turn(self, host):
        """Wait for this host's turn (self.gaps); False when it would come after the deadline."""
        key = host_key(host)
        gap = self.gaps.get(key)
        if not gap:
            return True
        while True:    # the turn is taken when it comes, not reserved ahead: a thread that wakes late keeps the gap
            with self.lock:
                now = time.monotonic()
                at = max(now, self.next_at.get(key, 0.0))
                if at >= self.stop_at:
                    return False
                if at <= now:
                    self.next_at[key] = now + gap
                    return True
            time.sleep(at - now)

    def get(self, url, headers=None, why="", allow=None, hops=MAX_HOPS):
        """One request: the entry (also kept in self.entries) and the body (None when nothing usable came). A redirect
        is followed where allow(its real address) is true (by default: from gov.il to gov.il, from archive.org to
        archive.org), `hops` at most (Redirects); else the entry has the 3xx, redirect_refused and no body."""
        with self.lock:
            if url in self.seen:
                return self.seen[url]
        host = urllib.parse.urlsplit(url).hostname or ""
        if fetchable(host) and self.real_to_fetch(url) is not None and not self.turn(host):
            with self.lock:
                self.late += 1
            return {"url": url, "error": "skipped: past the deadline (--deadline)"}, None
        with self.lock:
            if url in self.seen:
                return self.seen[url]
            if len(self.seen) >= self.max_urls:
                return {"url": url, "error": "skipped: request limit"}, None
            if time.monotonic() >= self.stop_at:
                self.late += 1
                return {"url": url, "error": "skipped: past the deadline (--deadline)"}, None
            entry = {"url": url, "why": why}
            self.seen[url] = (entry, None)
            self.entries.append(entry)
        body = None
        target = self.real_to_fetch(url)
        if not fetchable(host):
            entry["error"] = "not fetched: not a gov.il address"
        elif target is None:
            entry["error"] = "not fetched: --only-rewritten"
        else:
            try:
                req = urllib.request.Request(iri(target), headers={
                    "User-Agent": UA, "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8", "Accept-Encoding": "gzip, deflate", **(headers or {})})
                cut, fam = self.stop_at + GRACE, family(url)
                req.rules = (entry, allow or (lambda v: family(v) == fam), hops)
                with self.opener.open(req, timeout=max(1.0, min(self.timeout, cut - time.monotonic()))) as r:
                    entry["status"], raw = r.status, read_until(r, MAX_FILE + 1, cut)
                    entry["type"] = r.headers.get("Content-Type", "")
                    entry["last_modified"] = r.headers.get("Last-Modified")
                    final = r.geturl()
                    if final != iri(target):
                        entry["redirected_to"] = final
                    enc = (r.headers.get("Content-Encoding") or "").lower()
                body = decode_body(raw, enc)
                if len(raw) > MAX_FILE or len(body) > MAX_FILE:
                    unpacked = " unpacked" if len(raw) <= MAX_FILE else ""
                    entry["error"], body = f"over {MAX_FILE // 1_000_000} MB{unpacked}: not stored, not read", None
            except NotFollowed as exc:
                entry["status"], entry["error"], entry["redirect_refused"] = exc.code, str(exc), exc.url
            except urllib.error.HTTPError as exc:
                entry["status"], entry["type"] = exc.code, exc.headers.get("Content-Type", "") if exc.headers else ""
                try:
                    entry["head"] = text_head(decode_body(read_until(getattr(exc, "fp", None) or exc, 4096, cut),
                                                          (exc.headers or {}).get("Content-Encoding", ""), 4096))
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


def read_until(r, limit, cut):
    """r.read(limit), in pieces, stopped at the monotonic time `cut`: a slow body cannot hold the run past the
    deadline's grace. read1 where there is one (an HTTP response): what one read of the socket gives, so a body
    dripped a few bytes at a time comes back to the clock between pieces (read(64 KB) waits for all 64)."""
    read, chunks, n = getattr(r, "read1", None) or r.read, [], 0
    while n < limit:
        if time.monotonic() > cut:
            raise TimeoutError(f"cut at the deadline (--deadline) after {n} bytes")
        b = read(min(1 << 16, limit - n))
        if not b:
            break
        chunks.append(b)
        n += len(b)
    return b"".join(chunks)


def decode_body(raw, enc, limit=MAX_FILE + 1):
    """raw unpacked (gzip, deflate), `limit` bytes at most: a small body that would unpack to gigabytes stops there
    (get() then drops it as over MAX_FILE); raw itself where it does not unpack."""
    enc = (enc or "").lower()
    for wbits in ((31,) if "gzip" in enc or raw[:2] == b"\x1f\x8b" else (15, -15) if "deflate" in enc else ()):
        try:
            return zlib.decompressobj(wbits).decompress(raw, limit)
        except zlib.error:
            continue
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
    """Visible text, one line per block (table cells joined with ' | '), the links with their text, the scripts, and
    the elements a page's scripts fill (those with component-* or currentPageId attributes: www.bechirot.gov.il)."""
    BLOCK = {"p", "div", "tr", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "ul", "ol", "dd", "dt"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.cur, self.links, self.a, self.skip = [], [], [], None, 0
        self.scripts, self.components = [], []

    def handle_starttag(self, tag, attrs):
        d = {k: v for k, v in attrs if v is not None}
        if tag in ("script", "style"):
            self.skip += 1
            if tag == "script" and d.get("src"):
                self.scripts.append(d["src"])
        elif tag in self.BLOCK:
            self.flush()
        elif tag in ("td", "th") and self.cur:
            self.cur.append(" | ")
        if tag == "a":
            self.a = [d.get("href") or "", []]
        elif tag in ("img", "iframe", "embed", "source") and d.get("src"):
            self.links.append((d["src"], ""))
        if len(self.components) < 100 and any(k.startswith("component-") or k == "currentpageid" for k in d):
            self.components.append(d)

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


def parse_html(s):
    t = Text()
    try:
        t.feed(s)
        t.close()
    except Exception:                                     # a broken page still gives what was read so far
        pass
    t.flush()
    return t


def read_html(s):
    t = parse_html(s)
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


URL_KEYS = ("url", "link", "href", "path", "fileurl", "mediaurl", "src", "file")
TITLE_KEYS = ("title", "name", "text", "linktitle", "label", "caption", "description")


def json_links(o, title=""):
    """(address, its title) pairs of a JSON answer: a dict's Url / Link / Href (also a nested {"Url": ...}) with its
    Title / Name / Text, the way the site's API gives its menus and blocks."""
    if isinstance(o, list):
        for v in o:
            yield from json_links(v, title)
    elif isinstance(o, dict):
        low = {str(k).lower(): v for k, v in o.items()}
        t = next((low[k] for k in TITLE_KEYS if isinstance(low.get(k), str) and low[k].strip()), title)
        for k in URL_KEYS:
            v = low.get(k)
            if isinstance(v, str) and re.match(r"(?:https?://|/(?!/))\S{0,400}$", v.strip()):
                yield v.strip(), " ".join(t.split())[:200]
        for v in o.values():
            if isinstance(v, (dict, list)):
                yield from json_links(v, t)


def json_rows(o):
    """A line per JSON object of two short values or more (a table row as the site's API may give it), its values
    joined with ' | '."""
    if isinstance(o, list):
        for v in o:
            yield from json_rows(v)
    elif isinstance(o, dict):
        vals = [" ".join(str(v).split()) for v in o.values() if isinstance(v, (str, int, float)) and not isinstance(v, bool)
                and str(v).strip() and len(str(v)) <= 200 and "<" not in str(v)]
        if len(vals) >= 2:
            yield " | ".join(vals)
        for v in o.values():
            if isinstance(v, (dict, list)):
                yield from json_rows(v)


def read_body(entry, body):
    """(lines of text, [(href, link text)], the parsed JSON or None) of a fetched body."""
    if body is None or body[:5] == b"%PDF-" or body[:2] == b"PK":
        return [], [], None
    s = as_text(body)
    doc = None
    if s.lstrip()[:1] in ("{", "["):
        try:
            doc = json.loads(s)
        except (ValueError, RecursionError):
            doc = None
    if doc is None:
        return (*read_html(s), None)
    try:
        lines, links = [], list(json_links(doc))
        for x in strings(doc):
            if "<" in x and ">" in x:
                ln, lk = read_html(x)
                lines += ln
                links += lk
            elif x.strip():
                lines.append(" ".join(x.split()))
                if re.match(r"(https?://|/BlobFolder/|/he/)", x.strip()):
                    links.append((x.strip(), ""))
        return (lines + list(json_rows(doc)))[:MAX_LINES], links, doc
    except RecursionError:                                # nested deeper than the walk goes: read as text
        return (*read_html(s), None)


def read_any(entry, body):
    """(lines, [(href, link text)], the parsed JSON or None, how it was read) of a fetched body: HTML, JSON, CSV, a
    PDF, an XLSX or a DOCX; ([], [], None, "not read: ...") for what cannot be."""
    if body is None:
        return [], [], None, ""
    if body[:5] == b"%PDF-":
        lines, how = pdf_lines(body)
        return lines, [], None, how
    if body[:2] == b"PK":
        lines, how = office_lines(body)
        return lines, [], None, how
    if body[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return [], [], None, "not read: an XLS or DOC (stored)"
    path = urllib.parse.urlsplit(entry.get("snapshot_of") or entry.get("url") or "").path.lower()
    if "csv" in (entry.get("type") or "").lower() or path.endswith(".csv"):
        return csv_lines(body), [], None, "csv"
    lines, links, doc = read_body(entry, body)
    return lines, links, doc, "json" if doc is not None else "html"


def pdf_reader():
    """What reads a PDF here: pdftotext, pypdf, or None."""
    if shutil.which("pdftotext"):
        return "pdftotext"
    try:
        import pypdf  # noqa: F401
        return "pypdf"
    except ImportError:
        return None


def pdf_lines(body):
    """(lines, how it was read) of a PDF, a line a row (3 spaces or more between two pieces: ' | '), by pdftotext
    -layout where it is installed, else pypdf where it can be imported; ([], "not read: ...") when neither is."""
    text, how = None, ""
    exe = shutil.which("pdftotext")
    if exe:
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "in.pdf")
            with open(p, "wb") as f:
                f.write(body)
            try:
                r = subprocess.run([exe, "-layout", "-enc", "UTF-8", p, "-"], capture_output=True, timeout=PDF_TIMEOUT)
                if r.returncode == 0:
                    text, how = r.stdout.decode("utf-8", "replace"), "pdftotext"
                else:
                    how = f"pdftotext exit {r.returncode}"
            except (OSError, subprocess.SubprocessError) as exc:
                how = f"pdftotext {exc.__class__.__name__}"
    if text is None:
        try:
            import pypdf
        except ImportError:
            return [], (f"not read: {how}, no pypdf here" if how
                        else "not read: neither pdftotext nor pypdf here (stored; --reread)")
        logging.getLogger("pypdf").setLevel(logging.ERROR)     # its warnings on a broken PDF: the result says it
        try:
            pages = []
            for pg in pypdf.PdfReader(io.BytesIO(body)).pages[:300]:
                try:
                    pages.append(pg.extract_text(extraction_mode="layout") or "")
                except TypeError:                         # pypdf before 3.17: no layout mode
                    pages.append(pg.extract_text() or "")
            text, how = "\n".join(pages), "pypdf"
        except Exception as exc:                          # a broken PDF is that file's problem
            return [], f"not read: pypdf {exc.__class__.__name__}: {str(exc)[:80]}"
    lines = []
    for ln in BIDI.sub("", text).splitlines():
        ln = re.sub(r"\s+", " ", re.sub(r"\s{3,}", " | ", ln.strip()))
        if ln.strip(" |"):
            lines.append(ln)
    return orient(lines[:MAX_LINES]), how


COMMON =("הכנסת", "לכנסת", "רשימת", "הרשימה", "רשימות", "בחירות", "הבחירות", "המועמדים", "הסכם", "עודפים", "ועדת",
          "בראשות", "מפלגת", "ישראל")


def orient(lines):
    """Lines of a PDF in reading order: one drawn right to left can come out backwards (visual order, every word's
    letters reversed); such a line is turned around, its runs of digits and Latin letters kept as they were. Decided by
    common words read either way, line by line, else for the whole text."""
    def score(s):
        return sum(s.count(w) for w in COMMON) - sum(s.count(w[::-1]) for w in COMMON)
    whole = score("\n".join(lines))
    return [unvisual(ln) if (score(ln) or whole) < 0 else ln for ln in lines]


def unvisual(s):
    return re.sub(r"[0-9A-Za-z](?:[0-9A-Za-z.,:/%_-]*[0-9A-Za-z])?", lambda m: m.group(0)[::-1], s[::-1])


def office_lines(body):
    """The text of an XLSX (a line a row, its cells joined with ' | ') or a DOCX (a line a paragraph or table row)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(body))
        names = set(z.namelist())

        def xml(n):
            if z.getinfo(n).file_size > 60_000_000:
                raise ValueError(f"{n} is over 60 MB unpacked")
            return ET.fromstring(z.read(n))
        if "word/document.xml" in names:
            return docx_lines(xml("word/document.xml")), "docx"
        sheets = sorted((n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                        key=lambda n: int(re.sub(r"\D", "", n)))
        if not sheets:
            return [], "not read: a zip that is neither an XLSX nor a DOCX"
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = ["".join(t.text or "" for t in si.iterfind(".//{*}t"))
                      for si in xml("xl/sharedStrings.xml").iterfind(".//{*}si")]
        lines = []
        for n in sheets[:30]:
            for row in xml(n).iterfind(".//{*}row"):
                cells = []
                for c in row.iterfind(".//{*}c"):
                    v = c.find("{*}v")
                    if c.get("t") == "s" and v is not None:
                        try:
                            cells.append(shared[int(v.text)])
                        except (ValueError, IndexError, TypeError):
                            continue
                    elif c.get("t") == "inlineStr":
                        cells.append("".join(t.text or "" for t in c.iterfind(".//{*}t")))
                    elif v is not None and v.text:
                        cells.append(v.text)
                ln = " | ".join(" ".join(x.split()) for x in cells if x and x.strip())
                if ln:
                    lines.append(ln)
                if len(lines) >= MAX_LINES:
                    return lines, "xlsx"
        return lines, "xlsx"
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, OSError, EOFError, zlib.error) as exc:
        return [], f"not read: {exc.__class__.__name__}"


def docx_lines(root):
    def text(el):
        return "".join(t.text or "" for t in el.iterfind(".//{*}t"))
    lines, body = [], root.find("{*}body")
    for child in (body if body is not None else []):
        if child.tag.endswith("}tbl"):
            for tr in child.iterfind(".//{*}tr"):
                cells = [" ".join(" ".join(text(p) for p in tc.iterfind(".//{*}p")).split()) for tc in tr.findall("{*}tc")]
                ln = " | ".join(c for c in cells if c)
                if ln:
                    lines.append(ln)
        else:
            ln = " ".join(text(child).split())
            if ln:
                lines.append(ln)
    return lines[:MAX_LINES]


def csv_lines(body):
    s = as_text(body)
    first = s.split("\n", 1)[0]
    delim = max((",", ";", "\t", "|"), key=first.count)
    try:
        rows = list(itertools.islice(csv.reader(io.StringIO(s), delimiter=delim), MAX_LINES))
    except csv.Error:
        rows = [ln.split(delim) for ln in s.splitlines()[:MAX_LINES]]
    return [" | ".join(c.strip() for c in r if c.strip()) for r in rows if any(c.strip() for c in r)]


def absolute(href, base):
    href = html.unescape((href or "").strip())
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    u = urllib.parse.urljoin(base if base.startswith("http") else GOVIL + "/", href)
    return u.split("#")[0] if u.startswith(("http://", "https://")) else None


def unwrap_archive(u):
    """The original address of a Wayback Machine address (https://web.archive.org/web/<ts>[id_]/<url>), else u."""
    m = re.match(r"(?:https?://web\.archive\.org)?/web/\d{1,14}[a-z_]*/(https?://.+)$", u or "")
    return m.group(1) if m else u


def page_name(url):
    """The content-page name of a gov.il page address (/he/pages/<name>, /he/departments/guides/<name>), else None."""
    m = re.match(r"https?://(?:www\.)?gov\.il/(?:he|ar|en)/(?:pages|departments/guides|Departments/Guides)/([^/?#]+)", url, re.I)
    return m.group(1) if m else None


def is_govil(u):
    host = urllib.parse.urlsplit(u or "").hostname or ""
    return host == "gov.il" or host.endswith(".gov.il")


def site_url(u):
    """u as the crawl keys it (https://www.bechirot.gov.il/<path>[?<query>], percent-encoded, no fragment); None for
    another host."""
    try:
        p = urllib.parse.urlsplit(u or "")
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or (p.hostname or "").lower() not in SITE_HOSTS:
        return None
    return iri(urllib.parse.urlunsplit(("https", "www.bechirot.gov.il", p.path or "/", p.query, "")))


def classify(u):
    path = urllib.parse.unquote(urllib.parse.urlsplit(u).path)
    return "file" if FILE_EXT.search(path) else "asset" if ASSET_EXT.search(path) else "page"


def k26_of(s):
    """A text says it is about the 26th Knesset: by name (K26_TEXT), or by the year 2026 where no earlier Knesset is
    named."""
    return bool(K26_TEXT.search(s) or (K26_YEAR.search(s) and not OLD_KNESSET.search(s)))


def crawl_score(url, label=""):
    """0 for a link about the lists, letters, agreements, rosters or notices; 1 for one about the 26th Knesset; 2 for
    a weaker match (lists, publications); None for the rest, and for a link about an earlier Knesset only."""
    s = f"{urllib.parse.unquote(url or '')} {label}"
    k26 = k26_of(s) or K26_URL.search(s)
    if OLD_KNESSET.search(s) and not k26:
        return None
    return 0 if CRAWL_TOPIC.search(s) else 1 if k26 else 2 if CRAWL_WEAK.search(s) else None


def cdx_rows(body):
    """The rows of a CDX answer (output=json: a header row, then a row a capture) as dicts."""
    try:
        d = json.loads(as_text(body)) if body else []
    except (ValueError, RecursionError):
        return []
    if not isinstance(d, list) or len(d) < 2 or not isinstance(d[0], list):
        return []
    return [dict(zip(d[0], r)) for r in d[1:] if isinstance(r, list)]


# ------------------------------------------------------------------ comparing with lists_2026.json
def names_of(entry):
    """The names a list goes by in CEC text, longest first: its aliases (as given) and its official name, also cut
    at בראשות / בהנהגת (those two only when 4 characters or more: שמע, בטח are words too), and that cut again at a
    spaced dash, a leading מפלגת dropped (when two words or more, 6 characters or more, or an acronym: הקהל is a word):
    ביחד נצליח, list בד's short name, so that a row of it is not read as naming ביחד (list רק) by the longer match."""
    off = (entry.get("official_name") or "").strip()
    out = set()
    if off:
        head = re.split(r"\s+(?:בראשות|בהנהגת)\s+", off)[0].strip(" –-")
        out = {n for n in (off, head) if len(n) >= 4}
        short = re.sub(r"^מפלג[תה]\s+", "", re.split(r"\s+[–-]\s+", head)[0]).strip()
        if len(short.split()) >= 2 or len(short) >= 6 or re.search("[\"״]", short):
            out.add(short)
    out |= {n for n in entry.get("aliases") or [] if len(n) >= 2}
    return sorted(out, key=len, reverse=True)


_NAMES = {}


def name_spans(line, ref_lists):
    """[(letters, start, end)] of the lists a line names by name: longest name first, no overlaps."""
    table = _NAMES.get(id(ref_lists))
    if table is None:
        table = _NAMES[id(ref_lists)] = sorted(((n, e["letters"]) for e in ref_lists for n in names_of(e)),
                                               key=lambda x: -len(x[0]))
    out = []
    for n, L in table:
        if n not in line:
            continue
        for m in re.finditer(re.escape(n), line):
            if not any(a < m.end() and m.start() < b for _, a, b in out):
                out.append((L, m.start(), m.end()))
    return out


def lists_named(line, ref_lists):
    """The letters of the lists a line names: by name (longest first, no overlaps); by letters standing alone only
    in a short line, a table row, that names fewer than two by name (רק, עם, כן, די, אמת and דרך are also words)."""
    spans = name_spans(line, ref_lists)
    found = list(dict.fromkeys(L for L, _, _ in spans))
    if len(found) >= 2 or len(line.replace("|", " ").split()) > 6:
        return found
    for e in ref_lists:
        L = e["letters"]
        if L not in found and any(not any(a < m.end() and m.start() < b for _, a, b in spans)
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


def letter_cells(line, spans, strict=False):
    """The ballot letters a line shows apart from the names in it: a table cell of 1 to 4 letters alone, after
    אותיות (הרשימה):, or in brackets. strict (for other letters than the reference's): a cell only in a row where a
    list's name is its own cell (it starts it, or is half of it or more: not a word inside a longer text, ביחד in
    'מטעם מפלגת אנחנו. ביחד-'; a one-word name starts it only when בראשות, a dash, a bracket or nothing follows: not
    ביחד in 'ביחד נצליח', another list's name), brackets only just after a name."""
    def free(a, b):
        return not any(x < b and a < y for _, x, y in spans)

    def own_cell(x, y):
        for a, b, t in cells:
            if a <= x and y <= b:
                c, n = t.strip(" \t\"'״׳"), line[x:y]
                if c.startswith(n):
                    rest = c[len(n):].lstrip()
                    return " " in n.strip() or not rest or bool(re.match(r"(?:בראשות|בהנהגת|לראשות)\s|[–\-(,;:.!]", rest))
                return (y - x) * 2 >= len(c)
        return False
    cells = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"[^|]+", line)] if "|" in line else []
    whole = not strict or any(own_cell(x, y) for _, x, y in spans)
    out = []
    for a, b, t in cells:
        c = t.strip(" \t\"'״׳.:,;()[]")
        if whole and re.fullmatch(f"[{HEB}]{{1,4}}", c) and free(a, b):
            out.append(c)
    for m in re.finditer(rf"(?:אותיות|אות)(?:\s+(?:הרשימה|הקלפי|הפתק))?\s*[:\-–]\s*[\"'״׳]?([{HEB}]{{1,4}})(?![{HEB}])", line):
        out.append(m.group(1))
    for m in re.finditer(rf"\(\s*([{HEB}]{{1,4}})\s*\)", line):
        if free(m.start(), m.end()) and (not strict or any(0 <= m.start() - y <= 3 for _, _, y in spans)):
            out.append(m.group(1))
    return list(dict.fromkeys(out))


def compare_lists(ref, pages, snaps=None):
    """Per list: what its CEC roster page says against the reference (the live page; an archive snapshot of it when
    the live one gave nothing)."""
    rows = []
    for e in ref.get("lists", []):
        entry, lines = pages.get(e["cec_key"], (None, []))
        read, source = entry, "live page" if lines else None
        if not lines and (snaps or {}).get(e["cec_key"]):
            read, lines = snaps[e["cec_key"]]
            source = read.get("source")
        title = ""
        if read is not None and isinstance(read.get("doc"), dict):
            title = str((read["doc"].get("contentHead") or {}).get("title") or "")
        seen = letters_on_page(lines)
        text = "\n".join(lines)
        rows.append({"letters": e["letters"], "id": e.get("id"), "cec_key": e["cec_key"],
                     "status": entry.get("status") if entry else None, "error": entry.get("error") if entry else "not asked",
                     "source": source, "address": (read or {}).get("snapshot_of") or (read or {}).get("url"),
                     "title": title[:160], "letters_on_page": seen,
                     "letters_match": (e["letters"] in seen) if seen else None,
                     "name_on_page": any(n in text for n in names_of(e)) if lines else None})
    return rows


def find_agreements(ref, docs):
    """Lines that name exactly two lists, on pages about surplus-vote agreements and the 26th Knesset, with the
    agreement named on the line or in the AGREEMENT_CONTEXT lines above it, and not a line of a legal proceeding."""
    expected = {frozenset(a["lists"]) for a in ref.get("agreements", [])}
    found = {}
    for d in docs:
        url, lines = d["url"], d["lines"]
        text = "\n".join(lines)
        if not d.get("k26") or not (TOPIC.search(text) or TOPIC.search(urllib.parse.unquote(url))):
            continue
        for i, ln in enumerate(lines):
            named = lists_named(ENUMERATION.sub("", ln), ref.get("lists", []))
            near = lines[max(0, i - AGREEMENT_CONTEXT):i + 1]
            if len(named) == 2 and not PROCEEDINGS.search(ln) and any(AGREEMENT_LINE.search(x) for x in near):
                k = frozenset(named)
                f = found.setdefault(k, {"lists": named, "lines": [], "urls": [], "sources": []})
                if len(f["lines"]) < 3:
                    f["lines"].append(ln[:200])
                if url not in f["urls"]:
                    f["urls"].append(url)
                if len(f["sources"]) < 6 and not any(s["url"] == url and s["kind"] == d["kind"] for s in f["sources"]):
                    f["sources"].append({"url": url, "kind": d["kind"], "line": ln[:200]})
    return {"seen": list(found.values()),
            "expected_seen": [sorted(k) for k in expected if k in found],
            "expected_not_seen": [sorted(k) for k in expected if k not in found],
            "not_expected": [v["lists"] for k, v in found.items() if k not in expected]}


def confirm(ref, texts, rows, agreements):
    """What the CEC's pages and files read here say of each list's letters and each agreement in lists_2026.json:
    the sources that confirm it (a line naming the list with its letters shown apart, letter_cells; the roster page's
    letters; a line naming the agreement's two lists), and those that show other letters. Texts about the 26th
    Knesset only."""
    lists = ref.get("lists", [])
    refl = {e["letters"] for e in lists}
    per = {e["letters"]: {"confirmed": [], "other": []} for e in lists}

    def add(L, key, url, kind, line, extra=None):
        b = per[L][key]
        if len(b) < 6 and not any(x["url"] == url and x["kind"] == kind for x in b):
            b.append({"url": url, "kind": kind, "line": line[:200], **(extra or {})})
    for t in texts:
        if not t.get("k26"):
            continue
        for ln in t["lines"]:
            spans = name_spans(ln, lists)
            named = list(dict.fromkeys(L for L, _, _ in spans))
            shown = letter_cells(ln, spans) if named else []
            if not shown:
                continue
            if len(named) == 1:
                other = [] if named[0] in shown else [x for x in letter_cells(ln, spans, strict=True)
                                                      if len(x) <= 3 or x in refl]    # 4 letters alone: a word, mostly
                if named[0] in shown:
                    add(named[0], "confirmed", t["url"], t["kind"], ln)
                elif other:
                    add(named[0], "other", t["url"], t["kind"], ln, {"letters": other})
            elif set(shown) == set(named):
                for L in named:
                    add(L, "confirmed", t["url"], t["kind"], ln)
    for r in rows:
        if r.get("letters_match") is not None:
            add(r["letters"], "confirmed" if r["letters_match"] else "other", r.get("address") or "",
                r.get("source") or "live page", "אותיות הרשימה: " + " ".join(r["letters_on_page"]),
                None if r["letters_match"] else {"letters": r["letters_on_page"]})
    out_l = []
    for e in lists:
        p = per[e["letters"]]
        live = [x for x in p["confirmed"] if not x["kind"].startswith("archive")]
        out_l.append({"letters": e["letters"], "id": e.get("id"), "name": e.get("official_name"), "cec_key": e.get("cec_key"),
                      "status": "live" if live else "archive snapshot" if p["confirmed"] else "not confirmed",
                      "other_letters": sorted({x for o in p["other"] for x in o.get("letters", [])}),
                      "confirmed_by": p["confirmed"], "other": p["other"]})
    seen = {frozenset(v["lists"]): v for v in agreements.get("seen", [])}
    out_a = []
    for a in ref.get("agreements", []):
        srcs = (seen.get(frozenset(a["lists"])) or {}).get("sources", [])
        live = [x for x in srcs if not x["kind"].startswith("archive")]
        out_a.append({"lists": a["lists"], "ids": a.get("ids"), "confirmed_by": srcs,
                      "status": "live" if live else "archive snapshot" if srcs else "not confirmed"})
    expected = {frozenset(a["lists"]) for a in ref.get("agreements", [])}
    extra = [{"lists": v["lists"], "sources": v["sources"]} for k, v in seen.items() if k not in expected]

    def n(rows_, st):
        return sum(1 for x in rows_ if x["status"] == st)
    return {"letters": out_l, "agreements": out_a, "not_expected": extra,
            "counts": {"letters_live": n(out_l, "live"), "letters_archive": n(out_l, "archive snapshot"),
                       "letters_other": sum(1 for x in out_l if x["other_letters"]), "letters_none": n(out_l, "not confirmed"),
                       "agreements_live": n(out_a, "live"), "agreements_archive": n(out_a, "archive snapshot"),
                       "agreements_none": n(out_a, "not confirmed"), "agreements_not_expected": len(extra)}}


# ------------------------------------------------------------------ the run
class Run:
    """One run's reading: every text read (a live page or file, an archive snapshot of one) with its address, kind
    and whether it is about the 26th Knesset; the roster pages by cec_key (live, and archive snapshots)."""

    def __init__(self, F, ref):
        self.F, self.ref, self.texts, self.done = F, ref, [], {}
        self.base, self.hdr = API_FALLBACK, {}
        self.pages, self.snaps = {}, {}
        self.keys = {e.get("cec_key") for e in ref.get("lists", [])}
        self.site_links = []          # links to www.bechirot.gov.il on gov.il pages: seeds of the crawl
        self.lists_snapshot = None    # (kind, links) of the lists page's archive snapshot

    def api(self, name, chapter=None, why=""):
        q = "?culture=he" + (f"&chapterIndex={chapter}" if chapter else "")
        return (f"{self.base}/{urllib.parse.quote(name)}{q}", self.hdr, why)

    def api_name(self, url):
        """The page name of a content-pages API address, else None."""
        if not url.startswith(self.base + "/"):
            return None
        return urllib.parse.unquote(url[len(self.base) + 1:].split("?")[0]) or None

    def take(self, results, role=""):
        roles = role if isinstance(role, list) else [role] * len(results)
        return [self.take1(e, b, r) for (e, b), r in zip(results, roles)]

    def take1(self, entry, body, role="", parent_k26=False, roster=None):
        """(entry, lines, links) of one answer, read once; its text kept (self.texts) with where it came from."""
        u = entry.get("url", "")
        if u in self.done:
            return self.done[u]
        if role:
            entry.setdefault("role", role)
        if roster:
            entry["roster"] = roster
        if parent_k26:
            entry["parent_k26"] = True
        if body is None:
            return entry, [], []
        try:
            lines, links, doc, how = read_any(entry, body)
        except Exception as exc:                          # a body no reader copes with is that URL's problem
            lines, links, doc, how = [], [], None, f"not read: {exc.__class__.__name__}: {str(exc)[:80]}"
        if doc is not None:
            entry["doc"] = doc
        address = entry.get("snapshot_of") or u
        kind = entry.get("source") or ("live file" if how in FILE_READS or how.startswith("not read") else "live page")
        text = "\n".join(lines[:3000])
        k26 = bool(roster or K26_URL.search(urllib.parse.unquote(address)) or k26_of(text)
                   or (parent_k26 and not OLD_KNESSET.search(text)))
        entry.update({"source": kind, "read": how, "lines": len(lines), "k26": k26})
        if lines:
            self.texts.append({"url": address, "kind": kind, "lines": lines, "k26": k26, "roster": roster, "read": how})
        self.done[u] = (entry, lines, links)
        return self.done[u]

    def govil_jobs(self, u, label, why):
        """The requests for a gov.il link about the lists or the agreements: a page by its content-pages API address
        (a guide's own address too), a file as it is; [] for anything else."""
        name = page_name(u)
        s = f"{urllib.parse.unquote(u)} {label}"
        if not (TOPIC.search(s) or LISTS_TOPIC.search(s) or (name and ROSTER.search(name) and name not in self.pages)):
            return []
        if name and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name):
            return [self.api(name, why=why)] + ([] if "/pages/" in u else [(u, None, why)])
        if "/BlobFolder/" in u or re.search(r"\.(pdf|xlsx?|csv|docx?|json)(\?|$)", u, re.I):
            return [(u, None, why)]
        return []


def fill(names, attrs):
    """Query values for an endpoint's parameters from the attributes of the element its script fills
    (component-query, currentPageId, ...); with no names known, all of the element's attributes."""
    a = {}
    for k, v in attrs.items():
        if not v or len(v) > 100 or v.lstrip()[:1] in ("{", "[") or k in ("id", "class", "style", "role"):
            continue
        a[k[len("component-"):] if k.startswith("component-") and k != "component-id" else k.replace("-", "")] = v
    if not names:
        return a
    page, q = attrs.get("currentpageid", ""), {}
    for n in names:
        low = n.lower()
        v = a.get(low)
        if v is None:
            if "page" in low:
                v = page
            elif low in ("culture", "lang", "language"):
                v = attrs.get("htmllangattribute") or "he"
            elif low in ("id", "nodeid", "contentid", "parentid", "rootid", "queryid", "folderid", "itemid", "query"):
                v = a.get("query") or page
        if v:
            q[n] = v
    return q


class Crawl:
    """Part 2: the bounded crawl of www.bechirot.gov.il (module docstring)."""
    LIMIT = {"page": MAX_PAGES, "file": MAX_FILES, "script": MAX_SCRIPTS}
    SUB = {"api": ("MAX_API", MAX_API), "sitemap": ("MAX_SITEMAPS", MAX_SITEMAPS)}      # within MAX_PAGES

    def __init__(self, R):
        self.R, self.heap, self.queued, self.n = R, [], set(), itertools.count()
        self.count = {"page": 0, "file": 0, "script": 0, "api": 0, "sitemap": 0}
        self.endpoints, self.components = {}, []     # (stem, address) -> [parameter names]; (page, attrs, prio, k26)
        self.chrome = set()                          # the endpoints asked for a page's own elements (once each)
        self.gov_links, self.begun, self.dead, self.robots = [], False, None, None
        self.log = {"home": None, "asked": [], "not_asked": [], "not_asked_n": 0, "not_followed": 0, "elsewhere": [],
                    "api_found": [], "sitemap_urls": 0, "stopped": None, "seeds": [], "robots": None}

    def push(self, prio, url, label="", what="page", why="", k26=False):
        u = site_url(url)
        if not u or u in self.queued or (what not in ("api", "robots", "sitemap", "script") and classify(u) == "asset"):
            return
        self.queued.add(u)
        heapq.heappush(self.heap, (prio, next(self.n), u, label, what, why, bool(k26)))

    def left(self, u, what, why):
        self.log["not_asked_n"] += 1
        if len(self.log["not_asked"]) < 60:
            self.log["not_asked"].append({"url": u, "what": what, "why": why})

    def run(self):
        F = self.R.F
        if not self.begun:
            self.begun = True
            self.push(-4, BECHIROT + "/robots.txt", what="robots", why="the site's robots.txt (its rules, its sitemaps)")
            self.push(-3, BECHIROT + "/", why="the CEC site's home page")
            self.push(-2, BECHIROT + "/sitemap.xml", what="sitemap", why="the site's sitemap")
            for u in DELIVERY_API:
                self.push(-1, BECHIROT + u, what="api", why="Umbraco's content listing (the Delivery API, where it is on)")
        while self.heap:
            prio, _, u, label, what, why, k26 = heapq.heappop(self.heap)
            group = what if what in ("file", "script") else "page"
            if self.dead or self.log["stopped"]:
                self.left(u, what, self.dead or self.log["stopped"])
                continue
            if F.past():
                self.log["stopped"] = "the deadline (--deadline)"
                F.late += 1
                self.left(u, what, self.log["stopped"])
                continue
            if what != "robots" and self.robots is not None and not self.robots.can_fetch("*", u):
                self.left(u, what, "disallowed by robots.txt")
                continue
            name, room = f"MAX_{group.upper()}S", self.LIMIT[group] - self.count[group]
            if what in self.SUB and self.SUB[what][1] - self.count[what] < room:
                name, room = self.SUB[what][0], self.SUB[what][1] - self.count[what]
            if room <= 0:
                self.left(u, what, f"over the limit ({name})")
                continue
            new = u not in F.seen
            # a redirect: on this site only (and not where robots.txt says no), in the site's turn, within the limit
            entry, body = F.get(u, why=why[:160], allow=self.allowed, hops=min(MAX_HOPS, room - 1))
            err = entry.get("error") or ""
            if err.startswith("skipped"):
                self.log["stopped"] = err[len("skipped: "):]
                self.left(u, what, self.log["stopped"])
                continue
            if new:
                n = 1 + entry.get("hops", 0)
                self.count[group] += n
                self.count["api"] += n * (what == "api")
                self.count["sitemap"] += n * (what == "sitemap")
                if is_govil(entry.get("redirect_refused")) and not site_url(entry["redirect_refused"]):
                    self.gov_links.append((entry["redirect_refused"], label, k26, u))      # another gov.il host: part 3
            entry.setdefault("role", f"crawl {what}")
            if k26:
                entry["parent_k26"] = True
            self.log["asked"].append({"url": u, "what": what, "why": why[:120]})
            if u == BECHIROT + "/":
                self.log["home"] = entry.get("status") or err
                if entry.get("status") is None:
                    self.dead = f"the site did not answer: {err[:120]}"
            if body is None:
                continue
            final = F.real_of(entry.get("redirected_to"))
            if site_url(final):
                self.queued.add(site_url(final))
            base = final or u
            if what == "robots":
                self.read_robots(entry, as_text(body))
                for m in re.finditer(r"(?im)^\s*sitemap\s*:\s*(\S+)", as_text(body)):
                    self.push(-2, m.group(1), what="sitemap", why="named in robots.txt")
            elif what == "sitemap":
                self.read_sitemap(as_text(body))
            elif what == "script":
                self.read_script(u, as_text(body))
            else:
                self.read_page(entry, body, u, base, label, what, k26, prio)

    def allowed(self, u):
        """Where a redirect of the crawl may go: this site, where robots.txt does not say no."""
        v = site_url(u)
        return bool(v) and (self.robots is None or self.robots.can_fetch("*", v))

    def read_robots(self, entry, s):
        """robots.txt's rules for every agent (*), kept for the rest of the crawl, and its Crawl-delay when longer than
        --polite (30 s at most); one that does not answer 200 sets no rules."""
        self.log["robots"] = entry.get("status")
        if entry.get("status") != 200:
            return
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(s.splitlines())
        self.robots = rp
        delay, F = rp.crawl_delay("*"), self.R.F
        if delay and float(delay) > F.gaps.get("bechirot.gov.il", 0):
            F.gaps["bechirot.gov.il"] = min(30.0, float(delay))
            self.log["robots"] = f"200, Crawl-delay {F.gaps['bechirot.gov.il']:g} s"

    def read_sitemap(self, s):
        locs = [html.unescape(x) for x in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", s)]
        self.log["sitemap_urls"] += len(locs)
        for x in locs[:2000]:
            if "<sitemapindex" in s:
                self.push(-2, x, what="sitemap", why="in the sitemap index")
                continue
            sc = crawl_score(x)
            if sc is not None:
                self.push(sc, x, "", classify(x), "in the sitemap")

    def read_script(self, u, text):
        """The API addresses a script of the site calls (API_LIT), with the parameter names it sends: those in the
        address, '&name=' pieces and params: {...} keys just after it."""
        stem = os.path.basename(urllib.parse.urlsplit(u).path).split(".")[0]
        for m in API_LIT.finditer(text):
            path, _, q = m.group(2).partition("?")
            target = site_url(urllib.parse.urljoin(BECHIROT + "/", path)) if not re.search(r"[${}+]", path) else None
            if not target and is_govil(path) and len(self.log["api_found"]) < 40:   # another gov.il host: listed only
                self.log["api_found"].append({"script": u, "address": path, "params": [], "elsewhere": True})
            if not target or (stem, target) in self.endpoints or len(self.endpoints) >= MAX_ENDPOINTS:
                continue
            window = text[m.end():m.end() + 400]
            names = re.findall(r"([A-Za-z_]\w{0,40})=", q) + re.findall(r"""["'`][?&]([A-Za-z_]\w{0,40})=""", window)
            pm = re.search(r"params\s*:\s*\{([^{}]{0,400})\}", window)
            if pm:
                names += re.findall(r"""(?:^|[,{])\s*["']?([A-Za-z_]\w{0,40})["']?\s*:""", pm.group(1))
            self.endpoints[(stem, target)] = list(dict.fromkeys(names))
            self.log["api_found"].append({"script": u, "address": target, "params": self.endpoints[(stem, target)]})
        self.api_calls()

    def api_calls(self):
        """The site's API asked as its scripts would: each endpoint with the attributes of the elements its script
        fills (Header for #PageHeader, Banner for #Banner-..., by name), else once with the page's own. A page's own
        elements (#PageHeader, #PageFooter, #PageShare: currentPageId, no component-* attribute) draw the same menus on
        every page: asked once, for the first page that has them. A block (#ContentShow-..., #Banner-...) is its page's
        content: asked for every page, just ahead of the pages ranked with it (its page's priority, less 0.5), and about
        the 26th Knesset when its page is (and it names no earlier one)."""
        for (stem, target), names in self.endpoints.items():
            st = stem.lower()
            mine = [x for x in self.components if st and st in f"{x[1].get('id', '')} {x[1].get('component-type', '')}".lower()]
            for page, c, prio, k26 in mine or [x for x in self.components if x[1].get("currentpageid")][:1]:
                block = any(k.startswith("component-") for k in c)
                if not block:
                    if (stem, target) in self.chrome:
                        continue
                    self.chrome.add((stem, target))
                q = fill(names, c)
                u = target + (("&" if "?" in target else "?") + urllib.parse.urlencode(q) if q else "")
                self.push(prio - 0.5, u, what="api", why=f"the site's API ({stem}) for {c.get('id') or page}", k26=block and k26)

    def read_page(self, entry, body, u, base, label, what, k26, prio):
        R = self.R
        entry, lines, links = R.take1(entry, body, f"crawl {what}", parent_k26=k26)
        if what == "file":
            return
        on_topic = (crawl_score(u, label) is not None or entry.get("k26")
                    or bool(CRAWL_TOPIC.search("\n".join(lines[:500]))))
        if entry.get("read") == "html":
            t = parse_html(as_text(body))
            for src in t.scripts:
                v = site_url(absolute(src, base))
                if v and urllib.parse.urlsplit(v).path.lower().endswith(".js") and not SCRIPT_SKIP.search(v):
                    self.push(-1.5, v, what="script", why=f"a script of {u}")
            self.components += [(u, c, prio, entry.get("k26")) for c in t.components][:100]
            self.api_calls()
        for href, text in links:
            v = absolute(href, base)
            v = unwrap_archive(v) if v else None
            if not v:
                continue
            s = site_url(v)
            if s:
                kind, sc = classify(s), crawl_score(s, text)
                if kind == "file" and (sc is not None or on_topic):
                    self.push(0 if sc == 0 else 1, s, text, "file", f"linked from {u}: {text[:60]}", entry.get("k26"))
                elif kind == "page" and sc is not None:
                    self.push(sc, s, text, "page", f"linked from {u}: {text[:60]}", entry.get("k26"))
                elif kind == "page" and s not in self.queued:
                    self.log["not_followed"] += 1
            elif is_govil(v):
                path = urllib.parse.urlsplit(v).path
                if crawl_score(v, text) is not None or (on_topic and FILE_EXT.search(path)):
                    self.gov_links.append((v, text, entry.get("k26"), u))
            elif len(self.log["elsewhere"]) < 40 and v not in self.log["elsewhere"]:
                self.log["elsewhere"].append(v)

    def report(self):
        return {**self.log, "count": self.count, "limits": {"pages": MAX_PAGES, "api": MAX_API, "sitemaps": MAX_SITEMAPS,
                                                            "files": MAX_FILES, "scripts": MAX_SCRIPTS}, "dead": self.dead}


class Archive:
    """Part 3: the Wayback Machine for the gov.il addresses that answered 403 (module docstring)."""
    ROLE_PRIO = {"lists page": 0, "lists page html": 0, "lists page chapter": 0, "slips": 0, "linked": 1, "crawl page": 1,
                 "crawl file": 1, "crawl api": 1, "data.gov.il": 2, "roster": 2, "agreement guess": 3}

    def __init__(self, R, crawl):
        self.R, self.crawl = R, crawl
        self.heap, self.queued, self.n = [], set(), itertools.count()
        self.lookups = self.snapshots = self.fails = 0
        self.stopped, self.blob_asked = None, False
        self.rows, self.index = [], {}

    def ask(self, url, why, role):
        """One request to archive.org; (None, None) once this part is over (a 429, no answer, the deadline)."""
        if self.stopped:
            return None, None
        entry, body = self.R.F.get(url, why=why[:200])
        entry.setdefault("role", role)
        err = entry.get("error") or ""
        if entry.get("status") == 429:
            self.stopped = "archive.org answered 429 (too many requests): nothing more asked of it"
        elif err.startswith("skipped"):
            self.stopped = err[len("skipped: "):]
        elif entry.get("status") is None:
            self.fails += 1
            if self.fails >= 3 or err.startswith("not fetched"):
                self.stopped = f"archive.org did not answer: {err[:120]}"
        else:
            self.fails = 0
        return entry, body

    def offer(self, addr, prio, why, k26=False, roster=None, ts=None):
        if addr in self.queued or not is_govil(addr):
            return
        self.queued.add(addr)
        heapq.heappush(self.heap, (prio, next(self.n), addr, why, bool(k26), roster, ts))

    def offer_failed(self):
        """Every gov.il address asked live that answered 403 (not client-config.js: no content)."""
        for e in list(self.R.F.entries):
            role = e.get("role") or ""
            if e.get("status") == 403 and is_govil(e["url"]) and not e.get("snapshot_of") and role != "config":
                self.offer(e["url"], self.ROLE_PRIO.get(role, 2), f"answered 403 ({role or 'asked'})",
                           e.get("parent_k26") or e.get("k26"), e.get("roster"))

    def live(self, job, prio, k26=False, roster=None):
        """A gov.il address a page or snapshot links to: asked live first; on a 403, looked up here."""
        url, headers, why = job
        name = self.R.api_name(url)
        roster = roster or (name if name in self.R.keys else None)
        entry, body = self.R.F.get(url, headers, why)
        entry.setdefault("role", "linked")
        if k26:
            entry["parent_k26"] = True
        if body is not None:
            self.R.take1(entry, body, "linked", parent_k26=k26, roster=roster)
        elif entry.get("status") == 403:
            self.offer(url, prio, "answered 403 (linked)", k26, roster)

    def site_index(self):
        """The archive's index of www.bechirot.gov.il: its addresses about the lists (and its API addresses) as seeds
        of the crawl, each asked of the live site."""
        q = urllib.parse.urlencode({"url": "www.bechirot.gov.il/", "matchType": "prefix", "from": "2025", "output": "json",
                                    "fl": "original,timestamp,statuscode,mimetype", "filter": "statuscode:200",
                                    "collapse": "urlkey", "limit": "1500"})
        entry, body = self.ask(f"{CDX}?{q}", "the archive's index of www.bechirot.gov.il (addresses for the crawl)",
                               "archive index")
        rows = cdx_rows(body)
        n = {"listed": len(rows), "on_topic": 0, "api": 0, "status": (entry or {}).get("status") or (entry or {}).get("error")
             or self.stopped}
        for r in rows:
            v = site_url(r.get("original"))
            if not v:
                continue
            if re.search(r"/umbraco/|/api/", urllib.parse.urlsplit(v).path, re.I):
                if n["api"] < 15:
                    self.crawl.push(-1, v, what="api", why="in the archive's index of the site (an API address)")
                    n["api"] += 1
            elif classify(v) != "asset" and crawl_score(v) is not None and n["on_topic"] < 40:
                self.crawl.push(crawl_score(v), v, "", classify(v), "in the archive's index of the site")
                n["on_topic"] += 1
        self.index["www.bechirot.gov.il"] = n

    def blob_index(self):
        """The archive's listing of the lists page's files (BlobFolder/guide/candidates-lists-26/): each file's latest
        200, read without a lookup."""
        q = urllib.parse.urlencode({"url": f"www.gov.il/BlobFolder/guide/{LISTS_PAGE}/", "matchType": "prefix",
                                    "output": "json", "fl": "original,timestamp,statuscode,mimetype",
                                    "filter": "statuscode:200", "limit": "300"})
        entry, body = self.ask(f"{CDX}?{q}", "the archive's index of the lists page's files", "archive index")
        last = {}
        for r in cdx_rows(body):
            p = urllib.parse.urlsplit(r.get("original") or "")
            if p.path and r.get("timestamp"):
                last[GOVIL + iri(p.path)] = r["timestamp"]          # rows are in time order: the latest stays
        for addr, ts in list(last.items())[:15]:
            self.offer(addr, 0, "in the archive's index of the lists page's files", True, None, ts)
        self.index["lists page files"] = {"listed": len(last), "status": (entry or {}).get("status") or (entry or {}).get("error")
                                          or self.stopped}

    def run(self):
        F = self.R.F
        if not self.blob_asked:
            self.blob_asked = True
            self.blob_index()
        self.offer_failed()
        while self.heap and not self.stopped:
            if F.past():
                self.stopped = "the deadline (--deadline)"
                break
            prio, _, addr, why, k26, roster, ts = heapq.heappop(self.heap)
            row = {"address": addr, "why": why, "live": (F.seen.get(addr) or ({},))[0].get("status")}
            self.rows.append(row)
            if ts:
                row["result"] = f"in the archive's index: {ts}"
            elif self.lookups >= MAX_LOOKUPS:
                row["result"] = "not looked up: the limit (MAX_LOOKUPS)"
                continue
            else:
                self.lookups += 1
                ts, row["result"] = self.lookup(addr, deep=prio <= 1)
            if not ts or self.stopped:
                continue
            if self.snapshots >= MAX_SNAPSHOTS:
                row["result"] += "; not read: the limit (MAX_SNAPSHOTS)"
                continue
            self.snapshots += 1
            self.snapshot(addr, ts, k26, roster, row)

    def lookup(self, addr, deep=False):
        """(the timestamp of the snapshot to read or None, what the archive said)."""
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
        entry, body = self.ask(f"{AVAILABLE}?{urllib.parse.urlencode({'url': addr, 'timestamp': now})}",
                               f"the archive's closest snapshot of {addr}", "archive lookup")
        if body is None:
            return None, f"lookup failed: {(entry or {}).get('error') or self.stopped}"
        try:
            c = ((json.loads(as_text(body)) or {}).get("archived_snapshots") or {}).get("closest") or {}
        except (ValueError, AttributeError, RecursionError):
            return None, "lookup failed: not the availability JSON"
        if c.get("timestamp") and str(c.get("status") or "200") == "200" and c.get("available", True) is not False:
            return str(c["timestamp"]), f"closest snapshot {c['timestamp']}"
        said = f"closest snapshot {c['timestamp']} is HTTP {c.get('status')}" if c.get("timestamp") else "no snapshot"
        if not (c.get("timestamp") or deep) or self.stopped:
            return None, said
        q = urllib.parse.urlencode({"url": addr, "output": "json", "fl": "timestamp,original,statuscode",
                                    "filter": "statuscode:200", "limit": "-1"})
        _, b2 = self.ask(f"{CDX}?{q}", f"the archive's latest 200 of {addr}", "archive index")
        rows = cdx_rows(b2)
        if rows and rows[-1].get("timestamp"):
            return rows[-1]["timestamp"], f"{said}; the index has a 200 of {rows[-1]['timestamp']}"
        return None, f"{said}; none with HTTP 200 in the index"

    def snapshot(self, addr, ts, k26, roster, row):
        """The raw snapshot, read as the page it copies (marked as a snapshot); what it links to, asked live, then here."""
        R = self.R
        entry, body = self.ask(f"{WAYBACK}/web/{ts}id_/{addr}", f"archive snapshot {ts} of {addr}", "archive snapshot")
        if entry is None:
            return
        m = re.search(r"/web/(\d{14})", R.F.real_of(entry.get("redirected_to")) or "")
        ts = m.group(1) if m else ts
        row.update({"timestamp": ts, "snapshot": entry.get("status") or entry.get("error")})
        if body is None:
            return
        entry["snapshot_of"], entry["source"] = addr, f"archive snapshot {ts}"
        entry, lines, links = R.take1(entry, body, "archive snapshot", parent_k26=k26, roster=roster)
        row.update({"read": entry.get("read"), "lines": len(lines)})
        if roster and lines:
            R.snaps[roster] = (entry, lines)
        name = R.api_name(addr)
        if name == LISTS_PAGE:                      # the lists page itself: its roster links, its chapters
            R.lists_snapshot = R.lists_snapshot or (entry["source"], links)
            chapters = {int(c) for s_ in strings(entry.get("doc") or {}) for c in re.findall(r"chapterIndex=(\d{1,2})", s_)}
            for c in sorted(chapters):
                if 1 < c <= 12:
                    self.live(R.api(LISTS_PAGE, c, why="a chapter of the lists page (its archive snapshot)"), 0, True)
        at = GOVIL + "/" if name else addr
        why = f"linked from the archive snapshot of {addr[:70]}"
        for href, label in links:
            v = absolute(href, at)
            v = unwrap_archive(v) if v else None
            if not v:
                continue
            s = site_url(v)
            if s:
                sc = crawl_score(s, label)
                if sc is not None:
                    self.crawl.push(sc, s, label, classify(s), f"{why}: {label[:40]}", entry.get("k26"))
            elif is_govil(v) and v not in self.queued:
                for job in R.govil_jobs(v, label, f"{why}: {label[:40]}"):
                    self.live(job, 1, entry.get("k26"))

    def report(self):
        left = sorted(self.heap)
        return {"lookups": self.lookups, "snapshots": self.snapshots,
                "limits": {"lookups": MAX_LOOKUPS, "snapshots": MAX_SNAPSHOTS},
                "stopped": self.stopped, "index": self.index, "rows": self.rows,
                "not_looked_up": len(left), "not_looked_up_sample": [x[2] for x in left[:20]]}


def api_config(F):
    """(content-pages API base, client id) from gov.il's client-config.js; the www fallback otherwise."""
    entry, body = F.get(CLIENT_CONFIG, why="the content-pages API address and the site's public client id")
    entry.setdefault("role", "config")
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


def roster_index(R, lists_reads):
    """The roster pages the lists page links to (live, else its archive snapshot), against the reference's."""
    links = [lk for _, _, ls in lists_reads for lk in ls]
    source = "live page" if links else None
    if not links and R.lists_snapshot:
        source, links = R.lists_snapshot
    indexed = sorted({n for href, _ in links for n in [page_name(absolute(href, GOVIL + "/") or "")] if n and ROSTER.search(n)})
    return {"roster_pages_linked": len(indexed), "source": source, "not_in_reference": [k for k in indexed if k not in R.pages],
            "not_linked": [k for k in R.pages if indexed and ROSTER.search(k) and k not in indexed]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref", default=REF, help="the reference file (pipeline/reference/lists_2026.json), read only")
    ap.add_argument("--rewrite", action="append", default=[], metavar="FROM=TO", help="fetch FROM... from TO... (tests)")
    ap.add_argument("--only-rewritten", action="store_true")
    ap.add_argument("--timeout", type=float, default=TIMEOUT)
    ap.add_argument("--max-urls", type=int, default=MAX_URLS)
    ap.add_argument("--deadline", type=float, default=DEADLINE,
                    help=f"seconds from the start after which nothing is asked (default {DEADLINE}; fetch.yml stops it at 1500)")
    ap.add_argument("--polite", type=float, default=POLITE,
                    help=f"seconds between two requests to www.bechirot.gov.il (default {POLITE})")
    ap.add_argument("--archive-gap", type=float, default=ARCHIVE_GAP,
                    help=f"seconds between two requests to archive.org (default {ARCHIVE_GAP})")
    ap.add_argument("--reread", metavar="DIR", help="read DIR's files (an earlier run's --out) again and compare; nothing asked")
    a = ap.parse_args(argv)
    started = dt.datetime.now(dt.timezone.utc)
    os.makedirs(a.out, exist_ok=True)
    try:
        ref = json.load(open(a.ref, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        ref, ref_err = {}, f"{exc.__class__.__name__}: {exc}"
    else:
        ref_err = None
    if a.reread:
        return reread(a, ref, ref_err)
    F = Fetcher(a.out, [tuple(r.split("=", 1)) for r in a.rewrite if "=" in r], a.only_rewritten, a.timeout, a.max_urls,
                a.deadline, {"bechirot.gov.il": a.polite, "archive.org": a.archive_gap})
    R = Run(F, ref)
    base, cid = api_config(F)
    R.base, R.hdr = base, {"Origin": GOVIL, "Referer": GOVIL + "/", "Accept": "application/json",
                           **({"x-client-id": cid} if cid else {})}
    api, queued = R.api, set()

    # 1. gov.il: the lists page and its chapters, the agreement pages guessed, the HTML pages
    first = R.take(F.many([api(LISTS_PAGE, why="the CEC's lists page")]
                          + [api(n, why="a likely name of the agreements page") for n in AGREEMENT_PAGES]
                          + [(u, None, "the page itself (a gov.il page is a shell without the API)") for u in HTML_PAGES]),
                   ["lists page"] + ["agreement guess"] * len(AGREEMENT_PAGES) + ["lists page html"] * len(HTML_PAGES))
    chapters = set()
    for entry, lines, links in first[:1]:
        for s in strings(entry.get("doc") or {}):
            chapters.update(int(c) for c in re.findall(r"chapterIndex=(\d{1,2})", s))
    more = R.take(F.many([api(LISTS_PAGE, c, why="a chapter of the lists page") for c in sorted(chapters) if 1 < c <= 12]),
                  "lists page chapter")
    # each list's roster page, and the approved ballot slips
    keys = [e["cec_key"] for e in ref.get("lists", []) if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(e.get("cec_key", "")))]
    rosters = [R.take1(e, b, "roster", roster=k)
               for k, (e, b) in zip(keys, F.many([api(k, why="the list's roster page") for k in keys]))]
    for k, (entry, lines, _) in zip(keys, rosters):
        R.pages[k] = (entry, lines)
    slips = (ref.get("cec") or {}).get("approved_slips_pdf")
    frontier = first + more + rosters + (R.take([F.get(slips, why="the approved ballot slips")], "slips") if slips else [])
    lists_reads = [x for x in first[:1] + more if x[1]]
    # what the pages link to, two levels deep: gov.il files and pages about the lists or the agreements; the links to
    # www.bechirot.gov.il are the crawl's
    for _level in range(2):
        jobs = []
        for entry, lines, links in frontier:
            # a page's content from the API links relative to www.gov.il, not to the API's host
            at = GOVIL + "/" if entry.get("url", "").startswith(base) else entry.get("url", GOVIL + "/")
            for href, label in links:
                u = absolute(href, at)
                if not u or u in queued or u in F.seen:
                    continue
                if site_url(u):
                    R.site_links.append((u, label, entry.get("k26")))
                    queued.add(u)
                    continue
                new = R.govil_jobs(u, label, f"linked: {label[:60]}")
                if new:
                    queued.add(u)
                    jobs += [(j, entry.get("k26")) for j in new]
        if not jobs:
            break
        res = F.many([j for j, _ in jobs[:50]])
        for (entry, _), (_, k26) in zip(res, jobs[:50]):
            if k26:
                entry["parent_k26"] = True
        frontier = [R.take1(e, b, "linked", parent_k26=k26) for (e, b), (_, k26) in zip(res, jobs[:50])]
    # data.gov.il's catalogue
    for q in DATA_QUERIES:
        entry, body = F.get(DATA_GOV + urllib.parse.quote(q), why="data.gov.il catalogue")
        entry.setdefault("role", "data.gov.il catalogue")
        for res in datagov_resources(body):
            if TOPIC.search(res["name"]) or LISTS_TOPIC.search(res["name"]):
                R.take([F.get(res["url"], why=f"data.gov.il resource: {res['name'][:60]}")], "data.gov.il")
    # 2 and 3: the CEC's site and the archive, in turns while either has something new
    crawl = Crawl(R)
    archive = Archive(R, crawl)
    for u, label, k26 in R.site_links:
        sc = crawl_score(u, label)
        crawl.push(2 if sc is None else sc, u, label, classify(u), f"linked from gov.il: {label[:60]}", k26)
    for u in (ref.get("cec") or {}).get("crawl_seeds") or []:          # optional: lists_2026.json's cec.crawl_seeds
        crawl.push(0, u, "", classify(u), "a seed in lists_2026.json (cec.crawl_seeds)")
        crawl.log["seeds"].append(u)
    archive.site_index()
    for _round in range(3):
        crawl.run()
        for v, text, k26, page in crawl.gov_links:
            for job in R.govil_jobs(v, text, f"linked from {page[:70]}: {text[:40]}"):
                archive.live(job, 1, k26)
        crawl.gov_links = []
        archive.run()
        if not crawl.heap or F.past():
            break
    # 4. what it says
    list_rows = compare_lists(ref, R.pages, R.snaps)
    agreements = find_agreements(ref, R.texts)
    confirmation = confirm(ref, R.texts, list_rows, agreements)
    for e in F.entries:
        e.pop("doc", None)
    summary = {
        "fetcher": "cec_lists", "started": started.isoformat(timespec="seconds"),
        "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "reference": os.path.relpath(a.ref, ROOT) if a.ref.startswith(ROOT) else a.ref, "reference_error": ref_err,
        "content_api": base, "client_id_found": bool(cid),
        "requests": len(F.entries), "answered": sum(1 for e in F.entries if e.get("status") == 200),
        "deadline_s": a.deadline, "skipped_past_deadline": F.late, "polite_s": a.polite, "archive_gap_s": a.archive_gap,
        "pdf_reader": pdf_reader(),
        "stored": sorted(set(F.saved.values())),
        "index": roster_index(R, lists_reads),
        "confirmation": confirmation, "crawl": crawl.report(), "archive": archive.report(),
        "lists": list_rows, "agreements": agreements, "urls": F.entries,
    }
    write_summary(a.out, summary)
    c = confirmation["counts"]
    print(f"cec_lists: {summary['requests']} requests, {summary['answered']} answered (200), {len(summary['stored'])} files "
          f"stored; roster pages read: {sum(1 for r in list_rows if r['status'] == 200)}/{len(list_rows)}; www.bechirot.gov.il: "
          f"{crawl.count['page']} pages, {crawl.count['file']} files; archive: {archive.lookups} lookups, {archive.snapshots} "
          f"snapshots; letters confirmed live {c['letters_live']}, by a snapshot only {c['letters_archive']}, other "
          f"{c['letters_other']}; agreements confirmed live {c['agreements_live']}, by a snapshot only {c['agreements_archive']}, "
          f"of {len(confirmation['agreements'])}")
    return 0


def reread(a, ref, ref_err):
    """--reread DIR: the files of an earlier run (DIR/summary.json, DIR/files/) read again with what is installed here
    (pdftotext, pypdf) and compared again with the reference; nothing is asked, the earlier run's crawl and archive
    reports kept as they were."""
    src = a.reread
    try:
        old = json.load(open(os.path.join(src, "summary.json"), encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cec_lists --reread: {src}/summary.json: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2
    R = Run(None, ref)
    R.base = old.get("content_api") or API_FALLBACK
    root, entries = os.path.realpath(src), []
    for e in old.get("urls") or []:
        e = {k: v for k, v in e.items() if k not in ("read", "lines", "k26") and (k != "source" or e.get("snapshot_of"))}
        p, body = os.path.realpath(os.path.join(src, e.get("saved") or "-")), None
        if e.get("saved") and p.startswith(root + os.sep) and os.path.isfile(p):
            with open(p, "rb") as f:
                body = f.read()
        entries.append(e)
        if e.get("role") in NOT_TEXT:
            continue
        name = R.api_name(e.get("snapshot_of") or e.get("url") or "")      # a run before roster was recorded
        roster = e.get("roster") or (name if name in R.keys else None)
        _, lines, links = R.take1(e, body, e.get("role", ""), parent_k26=bool(e.get("parent_k26")), roster=roster)
        if roster:
            (R.snaps if e.get("snapshot_of") else R.pages)[roster] = (e, lines)
        if e.get("snapshot_of") and R.api_name(e["snapshot_of"]) == LISTS_PAGE and not R.lists_snapshot:
            R.lists_snapshot = (e.get("source"), links)
    list_rows = compare_lists(ref, R.pages, R.snaps)
    agreements = find_agreements(ref, R.texts)
    for e in entries:
        e.pop("doc", None)
    summary = {**old, "reference_error": ref_err, "reread_from": src,
               "reread_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "pdf_reader": pdf_reader(),
               "lists": list_rows, "agreements": agreements, "confirmation": confirm(ref, R.texts, list_rows, agreements),
               "urls": entries}
    write_summary(a.out, summary)
    c = summary["confirmation"]["counts"]
    print(f"cec_lists --reread {src}: {len(entries)} entries, {len(R.texts)} texts; letters confirmed live {c['letters_live']}, "
          f"by a snapshot only {c['letters_archive']}; agreements confirmed live {c['agreements_live']}, by a snapshot only "
          f"{c['agreements_archive']}")
    return 0


def write_summary(out, summary):
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(markdown(summary))


def datagov_resources(body):
    try:
        d = json.loads(as_text(body)) if body else {}
    except (ValueError, RecursionError):
        return []
    out = []
    for p in ((d.get("result") or {}).get("results") or []) if isinstance(d, dict) else []:
        title = f"{p.get('title') or ''} {p.get('name') or ''}"
        for r in p.get("resources") or []:
            if isinstance(r, dict) and str(r.get("url", "")).startswith("http"):
                out.append({"name": f"{title} {r.get('name') or ''}".strip(), "url": r["url"]})
    return out[:40]


def cell(x, n=120):
    return str(x if x is not None else "").replace("|", "/").replace("\n", " ")[:n]


def src_cell(srcs):
    """The first sources of a confirmation: kind: address (unquoted)."""
    return cell("; ".join(f"{s['kind']}: {urllib.parse.unquote(s['url'])}" for s in srcs[:2]), 320)


def index_cell(ix):
    """An archive index's answer: how many addresses it listed (on topic, API), and its HTTP status."""
    if not ix:
        return "not asked"
    more = ", ".join(f"{ix[k]} {k.replace('_', ' ')}" for k in ("on_topic", "api") if k in ix)
    return cell(f"{ix.get('listed', 0)} addresses{f' ({more})' if more else ''}, HTTP {ix.get('status')}")


def markdown(s):
    L = [f"# CEC lists and surplus agreements ({s['started'][:16].replace('T', ' ')} UTC)", "",
         f"{s['requests']} requests, {s['answered']} answered with 200, {len(s['stored'])} files stored under files/. "
         f"Content-pages API: `{s['content_api']}` (client id found: {s['client_id_found']}). PDFs read with: "
         f"{s.get('pdf_reader') or 'nothing here (stored, not read: --reread where pdftotext or pypdf is)'}.", ""]
    if s.get("reread_from"):
        L += [f"**Read again** ({s['reread_at'][:16].replace('T', ' ')} UTC) from `{cell(s['reread_from'])}`: nothing asked; "
              "that run's files read with what is installed here, the crawl and archive reports are that run's.", ""]
    if s.get("reference_error"):
        L += [f"**The reference file could not be read:** {cell(s['reference_error'])}", ""]
    if s.get("skipped_past_deadline"):
        L += [f"**Stopped at the deadline** ({s['deadline_s']:.0f} s from the start): {s['skipped_past_deadline']} requests "
              "not made; the comparison below is of what came before.", ""]
    L += ["lists_2026.json is read, never written here: what is confirmed below is for the lead to apply.", ""]
    C = s.get("confirmation") or {"letters": [], "agreements": [], "not_expected": [], "counts": {}}
    c = C["counts"]
    nl, na = len(C["letters"]), len(C["agreements"])
    L += ["## Confirmed by the CEC's own pages and files", "",
          f"Letters: **{c.get('letters_live', 0)} of {nl} confirmed by a live official page or file**; "
          f"{c.get('letters_archive', 0)} more only by an archive snapshot of one (the Wayback Machine's copy, not the live "
          f"page); **{c.get('letters_other', 0)} with other letters** next to the list's name (read the line); "
          f"{c.get('letters_none', 0)} not confirmed by anything read here.", "",
          "| letters (reference) | list | confirmed by | where (kind) | the line |", "|---|---|---|---|---|"]
    for r in C["letters"]:
        st = {"live": "**live page or file**", "archive snapshot": "archive snapshot only"}.get(r["status"], "not confirmed")
        if r["other_letters"]:
            st += f"; **OTHER LETTERS: {' '.join(r['other_letters'])}**"
        srcs = r["confirmed_by"] or r["other"]
        L.append(f"| {cell(r['letters'])} | {cell(r['id'] or (r['name'] or '')[:40])} | {st} | {src_cell(srcs)} | "
                 f"{cell((srcs[0]['line'] if srcs else '')[:100])} |")
    def pairs(st):
        return cell(", ".join("+".join(a["lists"]) for a in C["agreements"] if a["status"] == st)) or "none"
    L += ["", f"Agreements: **{c.get('agreements_live', 0)} of {na} confirmed by a live official page or file** "
              f"({pairs('live')}); only by an archive snapshot: {pairs('archive snapshot')}; not confirmed: "
              f"{pairs('not confirmed')}; **pairs named on such a page that lists_2026.json lacks: "
              f"{c.get('agreements_not_expected', 0)}**.", "",
          "| agreement | lists | confirmed by | where (kind) | the line |", "|---|---|---|---|---|"]
    for a in C["agreements"]:
        st = {"live": "**live page or file**", "archive snapshot": "archive snapshot only"}.get(a["status"], "not confirmed")
        L.append(f"| {cell(' + '.join(a['lists']))} | {cell(' + '.join(a.get('ids') or []))} | {st} | "
                 f"{src_cell(a['confirmed_by'])} | {cell((a['confirmed_by'][0]['line'] if a['confirmed_by'] else '')[:100])} |")
    for x in C["not_expected"]:
        L.append(f"| {cell(' + '.join(x['lists']))} | **not in lists_2026.json** | seen | {src_cell(x['sources'])} | "
                 f"{cell(x['sources'][0]['line'][:100] if x['sources'] else '')} |")
    cr = s.get("crawl")
    if cr:
        n, lim = cr["count"], cr["limits"]
        L += ["", "## www.bechirot.gov.il (the crawl)", "",
              f"Home page: {cell(cr.get('home'))}. Asked: {n['page']} pages of {lim['pages']} (the site's API: {n['api']} of "
              f"{lim['api']}; sitemaps: {n.get('sitemap', '-')} of {lim.get('sitemaps', '-')}), {n['file']} files of "
              f"{lim['files']}, {n['script']} scripts of {lim['scripts']}, each redirect counted; one request every "
              f"{s.get('polite_s')} s, redirects followed on this site only."
              + (f" **Stopped: {cell(cr['stopped'] or cr.get('dead'))}.**" if cr.get("stopped") or cr.get("dead") else ""), "",
              "API addresses its scripts call: " + (cell("; ".join(
                  f"{x['address']} ({', '.join(x['params']) or 'no parameters seen'})"
                  + (" (another host: not asked)" if x.get("elsewhere") else "") for x in cr["api_found"][:12]), 1500)
                  if cr["api_found"] else "none found (read the stored *.bundle.js)") + ".",
              f"robots.txt: {cell(cr.get('robots') or 'none')}; its sitemaps list {cr['sitemap_urls']} addresses; the archive's "
              f"index of the site: {index_cell((s.get('archive') or {}).get('index', {}).get('www.bechirot.gov.il'))}; seeds in "
              f"lists_2026.json: {len(cr.get('seeds') or [])}.",
              f"Not asked: {cr['not_asked_n']} ({cell('; '.join(sorted({x['why'] for x in cr['not_asked']})))}); links not "
              f"followed (about none of the topics, or an earlier Knesset): {cr['not_followed']}; links elsewhere (not fetched): "
              f"{len(cr['elsewhere'])} {cell(' '.join(cr['elsewhere'][:4]))}.", "",
              "| address | what | HTTP | read | lines | why |", "|---|---|---|---|---|---|"]
        by = {e["url"]: e for e in s["urls"]}
        for x in cr["asked"]:
            e = by.get(x["url"]) or {}
            http_ = str(e.get("status") or e.get("error"))
            http_ += (f" (to {urllib.parse.unquote(e['redirect_refused'])}: not followed)" if e.get("redirect_refused")
                      else f" (after {e['hops']} redirects)" if e.get("hops") else "")
            L.append(f"| {cell(urllib.parse.unquote(x['url']))} | {x['what']} | {cell(http_, 200)} | "
                     f"{cell(e.get('read'))} | {cell(e.get('lines'))} | {cell(x['why'][:80])} |")
    ar = s.get("archive")
    if ar:
        L += ["", "## Wayback Machine (the gov.il addresses that answered 403)", "",
              f"{ar['lookups']} lookups of {ar['limits']['lookups']}, {ar['snapshots']} snapshots of {ar['limits']['snapshots']}, "
              f"one request every {s.get('archive_gap_s')} s"
              + (f"; **stopped: {cell(ar['stopped'])}**" if ar.get("stopped") else "")
              + f"; not looked up: {ar['not_looked_up']}. The lists page's files in the archive's index: "
              f"{index_cell(ar['index'].get('lists page files'))}. A snapshot is read as the page it copies and marked \"archive "
              "snapshot <timestamp>\": the live page answered 403.", "",
              "| address | live | the archive | snapshot | read | lines |", "|---|---|---|---|---|---|"]
        for x in ar["rows"]:
            L.append(f"| {cell(x['address'])} | {cell(x.get('live'))} | {cell(x.get('result'))} | {cell(x.get('snapshot'))} | "
                     f"{cell(x.get('read'))} | {cell(x.get('lines'))} |")
    rows, ix = s["lists"], s["index"]
    bad = [r for r in rows if r["letters_match"] is False]
    L += ["", "## Lists (the roster pages on gov.il)", "",
          f"The lists page ({cell(ix.get('source') or 'not read')}) links to {ix['roster_pages_linked']} roster pages; **not in "
          f"lists_2026.json: {len(ix['not_in_reference'])}** {cell(' '.join(ix['not_in_reference']))}; in it but not linked: "
          f"{len(ix['not_linked'])} {cell(' '.join(ix['not_linked']))}.", "",
          f"Roster pages read: {sum(1 for r in rows if r['status'] == 200)} of {len(rows)} live, "
          f"{sum(1 for r in rows if str(r.get('source') or '').startswith('archive'))} from archive snapshots; letters stated "
          f"on the page: {sum(1 for r in rows if r['letters_on_page'])}; **different from lists_2026.json: {len(bad)}**.", "",
          "| letters (reference) | list | HTTP | read from | page title | letters on the page | match |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["id"] or r["letters_match"] is False:
            L.append(f"| {cell(r['letters'])} | {cell(r['id'] or r['cec_key'])} | {cell(r['status'] or r['error'])} | "
                     f"{cell(r.get('source') or '-')} | {cell(r['title'])} | {cell(' '.join(r['letters_on_page']))} | "
                     f"{'yes' if r['letters_match'] else 'NO' if r['letters_match'] is False else '-'} |")
    ag = s["agreements"]
    L += ["", "## Surplus-vote agreements (every line naming two lists on a page about them)", "",
          f"Expected (lists_2026.json) and seen on a CEC page: {len(ag['expected_seen'])}; expected, not seen: "
          f"{len(ag['expected_not_seen'])}; seen, not expected: **{len(ag['not_expected'])}**.", ""]
    for v in ag["seen"]:
        src = (v.get("sources") or [{"url": v["urls"][0], "kind": ""}])[0]
        L.append(f"- {' + '.join(v['lists'])}: {cell(v['lines'][0])} ({cell(src['url'])}, {cell(src['kind'])})")
    if not ag["seen"]:
        L.append("- no CEC page read here names two lists in one line about agreements (the page may not be out, may "
                 "be a PDF not read: read the stored files)")
    L += ["", "## Requests", "", "| URL | HTTP | type | bytes | read | saved / error |", "|---|---|---|---|---|---|"]
    for e in s["urls"]:
        L.append(f"| {cell(e['url'])} | {cell(e.get('status'))} | {cell((e.get('type') or '').split(';')[0])} | "
                 f"{cell(e.get('bytes'))} | {cell(e.get('read'))} | {cell(e.get('saved') or e.get('error') or e.get('note'))} |")
    L += ["", "Reading the text is best effort (a PDF: pdftotext -layout, else pypdf; XLS and DOC are not read). The files "
          "are the record.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
