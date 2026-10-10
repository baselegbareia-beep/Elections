#!/usr/bin/env python3
"""Find where the CEC publishes the 2026 files, what each one holds, and which live_config.json key
it fits.

GitHub's runners reach the CEC hosts and the build container does not, so this runs from
.github/workflows/discover.yml (daily 15–26.10, every 20 minutes on 27.10, hourly 28–29.10) and
reports to the ops-reports branch. It runs the same way from a laptop or a self-hosted runner:

    python3 pipeline/discover.py --out disc                  # disc/report.json + disc/report.md
    python3 pipeline/discover.py --out disc --push           # and reports/ on the ops-reports branch
    python3 pipeline/discover.py --previous old.json         # new / changed / gone against an older report
    python3 pipeline/discover.py --convert FILE              # a stored turnout release -> live_input/stations.csv

The raw bytes of every candidate turnout / results file (up to 8 MB each, each version once) are kept with
the report: disc/files/<YYYYMMDD-HHMM>/<name>, and with --push reports/files/… on the ops-reports branch,
so a release the feed's reader fails on (JSON, xlsx, other header names, figures written as 45.3% or 1,234)
can be converted by someone who cannot reach gov.il (--convert; docs/FILE_DISCOVERY.md §3).

What it probes. mode full: everything below. mode quick: the known files, the pages and what they
link to, and every URL that answered in the previous report.
  - the results files: media26 …/files/expb.csv and expc.csv, the same names on votes26/cdn-votes26,
    exp[a-z].csv and json/xlsx/zip variants;
  - the per-station turnout the CEC chair ordered on 16.8.2026 (at least four releases on election
    day; name, address and format unknown): plausible names under /files/ and the site roots, as
    csv/json/xlsx, some with hour suffixes;
  - double-envelope files and the national hourly turnout page;
  - every URL in the HTML and scripts of votes26, cdn-votes26, media26 (index pages, S3-style
    listings), bechirot.gov.il, the gov.il turnout pages, data.gov.il, robots.txt and sitemap.xml.
For each URL: HTTP status, content type, length, last-modified/etag, the first bytes decoded
(utf-8-sig, else cp1255), the CSV / xlsx / JSON header and row count, a class (results-ballot,
results-locality, turnout-station, turnout-locality, turnout-national, listing, data-other, html,
error), the live_config.json key it fits and the column_aliases / ignore_columns the feed would need.

Testing against a local server: --rewrite https://media26.bechirot.gov.il=http://127.0.0.1:8765/m26
(repeatable) fetches from the mock and keeps the real URL in the report; --only-rewritten skips
every other host; --candidates FILE replaces the built-in lists (each key optional):
    {"seeds": [pages to harvest], "probe": [URLs], "enumerate": false, "allow_hosts": ["gov.il"], "control": URL}

Exit status 0 whatever the network answers; non-zero only when the script itself fails, or when
--push could not deliver the report (3). --convert exits 1 when the feed's reader fails on its output, or when
it writes nothing: no station rows, no station with a figure, or more than 1% of a figure column unreadable.
"""
import argparse
import ast
import collections
import concurrent.futures as cf
import csv
import datetime as dt
import email.utils
import hashlib
import html
import http.client
import inspect
import io
import json
import math
import os
import platform
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
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-discover"
try:
    from zoneinfo import ZoneInfo
    IL = ZoneInfo("Asia/Jerusalem")
except Exception:                                   # a runner without tz data: IST (UTC+2) from 25.10.2026
    IL = dt.timezone(dt.timedelta(hours=2))

M26, V26, C26 = "https://media26.bechirot.gov.il", "https://votes26.bechirot.gov.il", "https://cdn-votes26.bechirot.gov.il"
CONTROL = "https://media25.bechirot.gov.il/files/expc.csv"   # a 2022 file: do this runner's requests reach the CEC at all?
SEEDS = [   # pages whose links and scripts are harvested
    V26 + "/", C26 + "/", M26 + "/", M26 + "/files/", M26 + "/?list-type=2", M26 + "/?prefix=files/",
    V26 + "/nationalresults", V26 + "/cityresults", V26 + "/ballotresults",
    "https://bechirot.gov.il/", "https://www.bechirot.gov.il/",
    "https://www.gov.il/he/pages/voting-by-hour", "https://www.gov.il/he/pages/voting-by-hour-26",
    "https://bechirot26.bechirot.gov.il/election/about/Pages/Hours_section_turnout.aspx",
    "https://data.gov.il/api/3/action/package_show?id=votes-knesset",
] + [h + p for h in (M26, V26, C26, "https://bechirot.gov.il") for p in ("/robots.txt", "/sitemap.xml")]
KNOWN = [M26 + "/files/expb.csv", M26 + "/files/expc.csv", V26 + "/files/expb.csv", V26 + "/files/expc.csv",
         C26 + "/files/expb.csv", C26 + "/files/expc.csv", CONTROL]
ALLOW = ("gov.il",)          # harvested links are followed and probed only on these domains
TURNOUT_NAMES = (
    "turnout", "turnout_kalpi", "turnout_kalpiot", "turnout_ballot", "turnout_ballots", "turnout_station",
    "turnout_stations", "turnout_by_kalpi", "turnout_by_ballot", "kalpi_turnout", "kalpiot_turnout",
    "ballot_turnout", "ballots_turnout", "station_turnout", "voting_percentage", "votingpercentage",
    "voting_percent", "vote_percent", "votes_percent", "percent", "percentage", "percent_kalpi", "ahuz",
    "ahuz_hatzbaa", "achuz_hatzbaa", "achuz", "hatzbaa", "shiur_hatzbaa", "participation", "hourly", "hours",
    "kalpi", "kalpiot", "ballots", "stations", "turnout26", "turnout_26")
HOURS = ("10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "22")
ENVELOPE_NAMES = ("envelopes", "double_envelopes", "maatafot", "maatafot_kfulot", "kfulot", "expb_env",
                  "expb_maatafot", "soldiers")


def enumerated():
    """Guessed names (mode full). The 2019–2022 files were media2X…/files/exp{b,c}.csv."""
    f = M26 + "/files/"
    out = [f + f"exp{c}.csv" for c in "abcdefghijklmnopqrstuvwxyz"]
    out += [f + f"exp{x}.{e}" for x in "bc" for e in ("json", "xlsx", "zip", "txt")]
    out += [f + f"{n}.{e}" for n in TURNOUT_NAMES for e in ("csv", "json", "xlsx")]
    out += [f + f"{b}_{h}{s}.csv" for b in ("turnout", "turnout_kalpi", "kalpi_turnout") for h in HOURS for s in ("", "00")]
    out += [f + f"{n}.csv" for n in ENVELOPE_NAMES]
    out += [M26 + f"/{n}.csv" for n in ("expb", "expc") + TURNOUT_NAMES]
    for h in (V26, C26):
        out += [h + f"/files/{n}.csv" for n in TURNOUT_NAMES]
        out += [h + "/" + p for p in ("turnout", "votingpercentage", "voting-percentage", "percent", "api", "api/turnout",
                                      "api/results", "api/ballots", "data", "files/")]
    return out


# ------------------------------------------------------------------ what the feed's readers accept
try:        # the feed's own reader (needs numpy); without it the report says the reader was not run
    from build_data import HEADER_ALIASES, OFFICIAL_META, read_expb
except Exception as _exc:                      # noqa: BLE001
    read_expb, READER_ERR = None, f"{_exc.__class__.__name__}: {_exc}"
    HEADER_ALIASES = {"סמל יישוב": "סמל ישוב", "שם יישוב": "שם ישוב", "בעלי זכות בחירה": "בזב"}
    OFFICIAL_META = {"סמל ועדה", "ברזל", "שם ישוב", "סמל ישוב", "קלפי", "מספר קלפי", "ריכוז", "שופט",
                     "בזב", "מצביעים", "פסולים", "כשרים", "ת. עדכון", "סמל קלפי", ""}
EXPECT = {"code": "סמל ישוב", "name": "שם ישוב", "station": "קלפי", "eligible": "בזב", "voters": "מצביעים",
          "invalid": "פסולים", "valid": "כשרים", "percent": "אחוז הצבעה"}
# names each reader takes without an alias: read_expb (results) and live_fetch.station_rows (per-station turnout;
# station_names() reads them from live_fetch.py, STATION_OK is the fallback: the names at ebb3201)
RESULTS_OK = {"code": {"סמל ישוב", *[k for k, v in HEADER_ALIASES.items() if v == "סמל ישוב"]},
              "name": {"שם ישוב", *[k for k, v in HEADER_ALIASES.items() if v == "שם ישוב"]},
              "station": {"קלפי", "מספר קלפי"}, "eligible": {"בזב", *[k for k, v in HEADER_ALIASES.items() if v == "בזב"]},
              "voters": {"מצביעים"}, "invalid": {"פסולים"}, "valid": {"כשרים"}}
STATION_OK = {"code": {"סמל ישוב", "סמל יישוב"}, "station": {"קלפי", "מספר קלפי"}, "voters": {"מצביעים", "הצביעו"},
              "eligible": {"בזב", "בעלי זכות בחירה"}}
LIVE_FETCH = os.path.join(ROOT, "pipeline", "live_fetch.py")
SYN = {   # header spellings by role, matched after norm(); guesses beyond the 2019–2022 names
    "code": ["סמל ישוב", "קוד ישוב", "סמל הישוב", "מספר ישוב", "סמל רשות", "city_code", "citycode", "locality_code",
             "locality_id", "settlement_code", "semel_yeshuv", "yeshuv_code"],
    "name": ["שם ישוב", "שם הישוב", "ישוב", "שם רשות", "city_name", "cityname", "locality_name", "locality", "settlement"],
    "station": ["קלפי", "מספר קלפי", "מס' קלפי", "מספר הקלפי", "קלפי מס'", "ballot", "ballot_id", "ballot_number", "ballotid",
                "kalpi", "kalpi_number", "station", "station_id", "polling_station"],
    "eligible": ["בזב", "בעלי זכות בחירה", "בעלי זכות", "מספר בעלי זכות בחירה", "בעלי זכות הצבעה", "eligible",
                 "eligible_voters", "registered", "registered_voters", "bzb"],
    "voters": ["מצביעים", "הצביעו", "מספר מצביעים", "מספר המצביעים", "מצביעים בפועל", "סה\"כ מצביעים", "voters", "voted",
               "votes_cast", "total_voters"],
    "invalid": ["פסולים", "קולות פסולים", "פתקים פסולים", "invalid", "invalid_votes"],
    "valid": ["כשרים", "קולות כשרים", "valid", "valid_votes"],
    "percent": ["אחוז הצבעה", "אחוז ההצבעה", "שיעור הצבעה", "שיעור ההצבעה", "אחוז מצביעים", "אחוז", "turnout",
                "turnout_percent", "turnout_pct", "percent", "pct", "voting_percentage", "votingpercentage"],
    "time": ["שעה", "שעת עדכון", "ת. עדכון", "תאריך עדכון", "זמן עדכון", "עדכון", "עודכן", "time", "hour", "updated",
             "update_time", "last_update", "timestamp"],
    "meta": ["סמל ועדה", "ועדה", "ברזל", "ריכוז", "שופט", "סמל קלפי", "סהכ", "סה\"כ", "מחוז", "נפה"],
}


def norm(h):
    return re.sub(r"[\s_\-\"'״׳`.:]", "", str(h)).replace("יי", "י").lower()


ROLE = {norm(s): r for r, names in SYN.items() for s in names}
LETTERS = re.compile(r"[א-ת]{1,4}")      # a ballot-letter header (as build_data.LIST_HEADER)
HOUR = re.compile(r"(?:עד\s*)?(?:השעה\s*)?([012]?\d):([0-5]\d)")


def role_of(h):
    r = ROLE.get(norm(h))
    if r:
        return r
    n = norm(h)                                     # "מצביעים עד 14:00", "אחוז הצבעה 10:00" …
    for key, r in (("מצביעים", "voters_hour"), ("הצביעו", "voters_hour"), ("אחוז", "percent_hour"), ("שיעור", "percent_hour")):
        if key in n and HOUR.search(h):
            return r
    return None


# ------------------------------------------------------------------ reference data (local files)
_REF = {}


def ref():
    """2026 letters, the 2022 letters and stations, the Arab localities: what a candidate is checked against."""
    if _REF:
        return _REF
    try:
        polls = json.load(open(os.path.join(ROOT, "site", "data", "polls_2026.json"), encoding="utf-8"))
        l26 = {p["letters"] for p in polls["parties"]}
    except Exception:
        l26 = {"מחל", "דרך", "רק", "אמת", "ל", "שס", "ג", "ב", "ט", "ודם", "עם", "ך", "די", "כן", "זך"}
    l22, st22 = set(), set()
    try:
        rows = list(csv.reader(open(os.path.join(ROOT, "data", "official", "k25_expb.csv"), encoding="utf-8-sig")))
        hd = [h.strip() for h in rows[0]]
        l22 = {h for h in hd if LETTERS.fullmatch(h) and h not in OFFICIAL_META}
        ic, ik = hd.index("סמל ישוב"), hd.index("קלפי")
        st22 = {(int(r[ic]), r[ik].strip()) for r in rows[1:] if len(r) > ik and r[ic].strip().isdigit()}
    except Exception:
        pass
    try:
        arab = {int(r["locality_code"]) for r in csv.DictReader(open(os.path.join(ROOT, "pipeline", "reference",
                                                                                  "arab_localities.csv"), encoding="utf-8"))}
    except Exception:
        arab = set()
    _REF.update(l26=l26, l22=l22, st22=st22, st22n={(c, k.split(".")[0]) for c, k in st22}, arab=arab,
                station_aliases=station_alias_support(), station_names=station_names())
    return _REF


def from_source(path, wanted, ns):
    """The top-level functions and literal constants `wanted` of a module, with the ones they use, compiled from its
    source into the namespace `ns` (which supplies the imports), without importing the module: live_fetch imports
    numpy, and its per-station reader needs only the standard library. KeyError when one of `wanted` is not there."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            try:
                ast.literal_eval(n.value)
                defs.setdefault(n.targets[0].id, n)
            except Exception:                       # noqa: BLE001 - not a literal (re.compile …): not taken
                pass
    take, todo = {}, list(wanted)
    while todo:
        name = todo.pop()
        if name in take or (name in ns and name not in wanted):
            continue
        if name not in defs:
            if name in wanted:
                raise KeyError(f"{name} not in {os.path.basename(path)}")
            continue
        take[name] = defs[name]
        todo += [x.id for x in ast.walk(defs[name]) if isinstance(x, ast.Name)]
    exec(compile(ast.Module(body=sorted(take.values(), key=lambda n: n.lineno), type_ignores=[]), path, "exec"), ns)
    return ns


_STATION = {}


def station_reader():
    """The feed's own per-station reader: live_fetch.station_rows, behind live_fetch.check_body as turnout_pass reads
    a release (read_source). Imported when it can be (live_fetch needs numpy); otherwise the same functions compiled
    from live_fetch.py's source. (None, why) when neither works: the check then says it was not run."""
    if not _STATION:
        try:
            import live_fetch
            _STATION.update(fn=live_fetch.station_rows, body=getattr(live_fetch, "check_body", None),
                            name="live_fetch.station_rows", err="")
        except Exception as exc:                # noqa: BLE001
            err = f"{exc.__class__.__name__}: {exc}"[:120]
            try:
                ns = from_source(LIVE_FETCH, ("station_rows",), {"csv": csv, "io": io, "collections": collections,
                                                                 "re": re, "json": json, "HEADER_ALIASES": HEADER_ALIASES})
                try:
                    from_source(LIVE_FETCH, ("check_body",), ns)
                except KeyError:
                    pass
                _STATION.update(fn=ns["station_rows"], body=ns.get("check_body"), err="",
                                name=f"live_fetch.station_rows, compiled from its source (live_fetch not importable: {err})")
            except Exception as exc2:           # noqa: BLE001
                _STATION.update(fn=None, body=None, name="", err=f"{err}; from source: {exc2.__class__.__name__}: {exc2}"[:200])
    return _STATION["fn"], _STATION["err"]


def read_stations(body, aliases=None):
    """(rows, excluded) as the feed reads a per-station release: check_body, then station_rows with column_aliases
    when it takes them. Raises what they raise."""
    fn, err = station_reader()
    if fn is None:
        raise RuntimeError(f"live_fetch.station_rows not loaded: {err}")
    if _STATION.get("body"):
        body = _STATION["body"](body)
    param = _alias_param(fn)
    res = fn(body, **({param: aliases} if aliases and param else {}))
    rows, excluded = res if isinstance(res, tuple) else (res, {})
    return rows, dict(excluded or {})


def station_names():
    """{role: the header names live_fetch.station_rows finds without an alias}: its STATION_COLS, read from
    live_fetch.py, and the build_data.HEADER_ALIASES spellings it maps onto them first. STATION_OK (the names at
    ebb3201, no percentage) when live_fetch.py has no STATION_COLS."""
    try:
        cols = from_source(LIVE_FETCH, ("STATION_COLS",), {})["STATION_COLS"]
    except Exception:                               # noqa: BLE001
        return STATION_OK
    role = {"code": "code", "kalpi": "station", "elig": "eligible", "voters": "voters", "pct": "percent"}
    out = {role[k]: set(v) for k, v in cols.items() if k in role}
    for theirs, ours in HEADER_ALIASES.items():
        for names in out.values():
            if ours in names:
                names.add(theirs)
    return out if {"code", "station", "voters"} <= out.keys() else STATION_OK


def _alias_param(fn):
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return None
    return next((p for p in ("column_aliases", "aliases") if p in params), None)


def station_alias_support():
    """Does the feed map per-station turnout headers through live_config column_aliases? (not at ebb3201)
    Either station_rows takes the aliases as a parameter and turnout_pass hands it column_aliases, or the
    function that parses the header (station_rows; station_turnout before r5/feed) reads column_aliases."""
    try:
        src = open(LIVE_FETCH, encoding="utf-8").read()
    except OSError:
        return False

    def body(name):
        return src.split(f"def {name}(", 1)[1].split("\ndef ", 1)[0] if f"def {name}(" in src else ""
    parsers = [b for b in (body("station_rows"), body("station_turnout")) if "header" in b]
    if any("column_aliases" in b for b in parsers):
        return True
    fn, _ = station_reader()
    return bool(fn and _alias_param(fn) and "column_aliases" in body("turnout_pass"))


# ------------------------------------------------------------------ network
URL_SAFE = ":/?#[]@!$&'()*+,;=%~"


def enc_url(url):
    """The URL as it goes on the wire: raw Hebrew, spaces and other unsafe characters percent-encoded (UTF-8),
    what is already encoded left alone. The report and the suggested live_config.json values use this form,
    because live_fetch.fetch() sends the configured URL as it is."""
    url = re.sub(r"[\t\r\n]", "", url.strip())
    return urllib.parse.quote(url, safe=URL_SAFE)


def host_of(url):
    """The host of a URL that can be sent, else "" (an invalid IPv6 literal "http://[x/…", a port out of range)."""
    try:
        p = urllib.parse.urlsplit(url)
        p.port                                      # noqa: B018 - raises ValueError when out of range
        return (p.hostname or "").lower()
    except ValueError:
        return ""


def is_web(url):
    return bool(url) and str(url).startswith(("http://", "https://"))


def network_error(exc):
    """True for a failure of the network or the host; False for a URL this script could not send at all
    (InvalidURL, a non-ASCII character, an unknown scheme), which says nothing about the host."""
    if isinstance(exc, urllib.error.URLError) and "unknown url type" in str(exc.reason):
        return False
    return isinstance(exc, OSError) or (isinstance(exc, http.client.HTTPException)
                                        and not isinstance(exc, http.client.InvalidURL))


class Net:
    """GET with a per-host pace, a size cap, and the test-mode host rewrite."""

    def __init__(self, a):
        self.rewrite = [tuple(r.split("=", 1)) for r in a.rewrite]
        self.only, self.max, self.timeout, self.delay = a.only_rewritten, a.max_bytes, a.timeout, a.delay
        self.lock, self.slot, self.fails = threading.Lock(), {}, collections.Counter()

    def target(self, url):
        for src, dst in self.rewrite:
            if url.startswith(src):
                return dst + url[len(src):]
        return None if self.only else url

    def logical(self, url):
        for src, dst in self.rewrite:
            if url.startswith(dst):
                return src + url[len(dst):]
        return url

    def get(self, url):
        target, host = self.target(url), host_of(url)
        if target is None:
            return {"status": 0, "error": "skipped: host not rewritten (test mode)"}
        target = enc_url(target)
        if not is_web(target) or not host:
            return {"status": 0, "local": True, "error": "bad URL, not sent: not an http(s) URL with a host"}
        if self.fails[host] >= 3:
            return {"status": 0, "error": "skipped: the host did not answer 3 times in this run"}
        with self.lock:                             # at most one request start per host every `delay` seconds
            start = max(time.time(), self.slot.get(host, 0.0))
            self.slot[host] = start + self.delay
        time.sleep(max(0.0, start - time.time()))
        t0 = time.time()
        try:
            req = urllib.request.Request(target, headers={"User-Agent": UA, "Accept": "*/*", "Cache-Control": "no-cache",
                                                          "Accept-Language": "he-IL,he;q=0.9,en;q=0.5"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read(self.max + 1)
                out = {"status": r.status, "headers": r.headers, "final": r.geturl()}
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read(8192)
            except Exception:
                body = b""
            out = {"status": exc.code, "headers": exc.headers, "final": exc.geturl() or target}
        except Exception as exc:                    # DNS, refused, timeout, TLS: a finding, not a crash
            if not network_error(exc):              # never sent: not held against the host
                return {"status": 0, "local": True, "error": f"bad URL, not sent: {exc.__class__.__name__}: {exc}"[:200]}
            with self.lock:
                self.fails[host] += 1
            return {"status": 0, "error": f"{exc.__class__.__name__}: {exc}"[:200], "ms": round(1000 * (time.time() - t0))}
        out.update(body=body[:self.max], truncated=len(body) > self.max, ms=round(1000 * (time.time() - t0)),
                   final=self.logical(out["final"] or target))
        return out


# ------------------------------------------------------------------ reading a body
def decode(body, truncated=False):
    if truncated and b"\n" in body:
        body = body[:body.rindex(b"\n")]
    if body.startswith(b"\xef\xbb\xbf"):
        return body[3:].decode("utf-8", "replace"), "utf-8-sig"
    if body[:2] in (b"\xff\xfe", b"\xfe\xff"):     # Excel's "Unicode text": UTF-16, usually tab-separated
        return body.decode("utf-16", "replace"), "utf-16"
    try:
        return body.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return body.decode("cp1255", "replace"), "cp1255"


def sniff(body, ctype, url):
    h = body.lstrip(b"\xef\xbb\xbf \t\r\n")[:64]
    ctype, path = (ctype or "").lower(), url.split("?", 1)[0].lower()
    if h.startswith(b"PK\x03\x04"):
        return "zip"
    if h.startswith(b"%PDF"):
        return "pdf"
    if h.startswith(b"\xd0\xcf\x11\xe0"):           # OLE2: Excel 97–2003 (.xls)
        return "xls"
    if body[:2] in (b"\xff\xfe", b"\xfe\xff"):      # UTF-16 text (decode() reads it)
        return "text"
    if b"\x00" in body[:1024]:
        return "binary"
    if h[:1] == b"<":
        low = body[:3000].lower()
        return "html" if (b"<html" in low or b"<!doctype html" in low or b"<body" in low) else "xml"
    if h[:1] in (b"{", b"["):
        return "json"
    if "javascript" in ctype or path.endswith((".js", ".mjs")):
        return "js"
    return "text"       # the body decides, not the content type: a CSV may be served as text/html


def server_hint(status, hdrs, body):
    """What answered: a missing S3 key, a block, bot protection … (404 from CloudFront is ambiguous)."""
    b = body[:3000]
    via = " ".join(str(hdrs.get(k, "")) for k in ("Server", "Via", "X-Cache")).lower() if hdrs else ""
    for needle, hint in ((b"NoSuchKey", "S3: no such file (the bucket answers; the file is not there)"),
                         (b"AccessDenied", "S3: access denied (a missing file when listing is not allowed, or a block)"),
                         (b"NoSuchBucket", "S3: no such bucket"),
                         (b"could not be satisfied", "CloudFront: request could not be satisfied (blocked or no origin)"),
                         (b"Request blocked", "blocked by a firewall rule"), (b"Incapsula", "Imperva bot protection"),
                         (b"_Incapsula_", "Imperva bot protection"), (b"cf-chl", "Cloudflare challenge")):
        if needle in b:
            return hint
    if "cloudfront" in via:
        return f"CloudFront ({hdrs.get('X-Cache', '') or 'no X-Cache'})"
    if status == 404:
        return "not found"
    return ""


def printable(s, n=300):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "·", s[:n])


def csv_table(text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    delim = max(",;\t|", key=lines[0].count)
    if lines[0].count(delim) == 0 or (len(lines) > 1 and lines[1].count(delim) == 0):
        return None
    rows = list(csv.reader(lines, delimiter=delim))
    return {"format": "csv", "delimiter": delim, "header": [h.strip().strip('"') for h in rows[0]], "rows": rows[1:]}


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]*", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def xlsx_table(body):
    """Header and rows of the first sheet, with the standard library only."""
    z = zipfile.ZipFile(io.BytesIO(body))
    if any(i.file_size > 200_000_000 for i in z.infolist()):
        raise ValueError("xlsx part too large")
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    names = z.namelist()
    ss = ["".join(t.text or "" for t in si.iter(ns + "t"))
          for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(ns + "si")] if "xl/sharedStrings.xml" in names else []
    sheets = sorted((n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                    key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[1]).group(0)))
    if not sheets:
        return None
    rows = []
    for r in ET.fromstring(z.read(sheets[0])).iter(ns + "row"):
        vals = {}
        for i, c in enumerate(r.iter(ns + "c")):
            v, t = c.find(ns + "v"), c.get("t")
            if t == "s" and v is not None:
                val = ss[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(ns + "t"))
            else:
                val = v.text if v is not None else ""
            vals[_col(c.get("r")) if c.get("r") else i] = val or ""
        if any(str(x).strip() for x in vals.values()):
            rows.append([vals.get(i, "") for i in range(max(vals) + 1)])
    if not rows:
        return None
    return {"format": "xlsx", "sheets": len(sheets), "header": [str(h).strip() for h in rows[0]], "rows": rows[1:]}


def json_table(obj):
    """The longest list of objects in a JSON document, as a table (keys of its first item)."""
    best = []

    def walk(o, depth=0):
        nonlocal best
        if depth > 6:
            return
        if isinstance(o, list):
            if len(o) > len(best) and o and all(isinstance(x, dict) for x in o[:20]):
                best = o
            for x in o[:50]:
                walk(x, depth + 1)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v, depth + 1)
    walk(obj)
    if not best:
        return None
    header = list(best[0].keys())
    return {"format": "json", "header": header,               # null is a blank cell (not reported), not "None"
            "rows": [["" if d.get(k) is None else str(d[k]) for k in header] for d in best if isinstance(d, dict)]}


def hourly_figures(text):
    """Best effort: {"10:00": 15.9, …} from a page or document that talks about turnout."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))
    if not re.search(r"אחוז ה?הצבעה|שיעור ה?הצבעה|הצבעה המצטבר|turnout|voting percentage|percent", t, re.I):
        return {}, ""
    out, ctx = {}, ""
    for m in re.finditer(r"\b([012]?\d):00\b((?:(?!\b[012]?\d:\d\d\b)[^%]){0,60}?)\b(\d{1,2}(?:\.\d{1,2})?)\s*%", t):
        h, p = f"{int(m.group(1)):02d}:00", float(m.group(3))
        if "08:00" <= h <= "22:00" and 0 < p < 100 and h not in out:
            out[h] = p
            ctx = ctx or t[max(0, m.start() - 80):m.end() + 40]
    return out, ctx


DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")     # Arabic-Indic and Persian digits
MARKS = re.compile("[\u200e\u200f\u061c\u202a-\u202e\u2066-\u2069\ufeff]")   # direction marks in Hebrew/Arabic exports
COMMA_GROUPS = re.compile(r"[+-]?\d{1,3}(?:,\d{3})+")
SPACE_GROUPS = re.compile(r"[+-]?\d{1,3}(?: \d{3})+(?:\.\d+)?")


def clean(x):
    return MARKS.sub("", str(x)).strip()


def num(x, percent=False):
    """A number cell as an export writes it -> float; None when blank or not a number. Reads a percent sign (45.3%,
    ٪), thousands separators (1,234; 1 234 with a space, NBSP or thin space; ١٬٢٣٤), a decimal comma (45,3; in a
    percentage a comma is always the decimal point, as no percentage has thousands), Arabic-Indic and Persian digits,
    the Arabic decimal separator and the direction marks around a figure. "1,234" outside a percentage is 1234."""
    s = clean(x).translate(DIGITS).replace("\u066b", ".").replace("\u2212", "-")
    s = re.sub(r"^[%\u066a]\s*|\s*[%\u066a]$", "", s)
    s = re.sub(r"[\s\u066c']+", " ", s).strip()
    if "," in s and "." in s:                       # 1,234.5 or 1.234,5: the later one is the decimal point
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "") if not percent and COMMA_GROUPS.fullmatch(s) else s.replace(",", ".") if s.count(",") == 1 else s
    if " " in s:
        if not SPACE_GROUPS.fullmatch(s):
            return None
        s = s.replace(" ", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


# ------------------------------------------------------------------ classifying a table
def table_roles(header, notes):
    """{role: header} for the columns this script recognises (SYN)."""
    roles = {}
    for h in header:
        r = role_of(h)
        if r and r not in roles:
            roles[r] = h
    for r in ("voters", "percent"):                 # by-hour columns only: the last one stands for the role
        hv = [h for h in header if role_of(h) == r + "_hour"]
        if r not in roles and hv:
            roles[r] = hv[-1]
            notes.append(f"{r} by hour {hv}: the last column is used; check it is the latest release")
    return roles


def describe_table(e, tab, body):
    header, rows = tab["header"], tab["rows"]
    notes = e.setdefault("notes", [])
    roles = table_roles(header, notes)
    letters = [h for h in header if LETTERS.fullmatch(h) and not role_of(h) and h not in OFFICIAL_META]
    hour_cols = [h for h in header if HOUR.fullmatch(h.strip())]
    if "code" in roles and len(letters) >= 3 and ("valid" in roles or "voters" in roles):
        cls = "results-ballot" if "station" in roles else "results-locality"
    elif "code" in roles and roles.keys() & {"voters", "percent", "voters_hour", "percent_hour"}:
        cls = "turnout-station" if "station" in roles else "turnout-locality"
    elif len(hour_cols) >= 2 or ("time" in roles and "percent" in roles):
        cls = "turnout-national"
    else:
        cls = "data-other"
    info = {k: v for k, v in tab.items() if k not in ("rows", "header")}
    info.update(header=header[:80], columns=len(header), rows=len(rows), roles=roles)
    e.update(cls=cls, table=info)
    idx = {r: header.index(h) for r, h in roles.items()}

    def val(rec, r):
        i = idx.get(r)
        return rec[i].strip() if i is not None and i < len(rec) else ""
    if cls in ("results-ballot", "results-locality", "turnout-station", "turnout-locality"):
        codes, voters, elig, counted, env, keys = set(), 0, 0, 0, 0, []
        for rec in rows:
            c = val(rec, "code")
            if c in ("9999", "99999"):
                env += 1
                continue
            if c.isdigit():
                codes.add(int(c))
                if "station" in idx:
                    keys.append((int(c), val(rec, "station")))
            v, b = num(val(rec, "voters")) or 0, num(val(rec, "eligible")) or 0
            voters, elig, counted = voters + v, elig + b, counted + (v > 0)
        R = ref()
        info.update(localities=len(codes), counted_rows=counted, voters=int(voters), eligible=int(elig),
                    turnout=round(voters / elig, 4) if elig else None, envelope_rows=env,
                    arab_localities=f"{len(codes & R['arab'])}/{len(R['arab'])}")
        if keys and R["st22"]:
            info["match_2022"] = {"exact": round(sum(k in R["st22"] for k in keys) / len(keys), 3),
                                  "by_number": round(sum((c, k.split(".")[0]) in R["st22n"] for c, k in keys) / len(keys), 3)}
        if "time" in idx:
            ts = sorted(val(r, "time") for r in rows if val(r, "time"))
            info["data_time"] = ts[-1] if ts else None
    if cls.startswith("results"):
        R = ref()
        have = set(letters)
        p26, only22 = sorted(have & R["l26"]), sorted(have & (R["l22"] - R["l26"]))
        verdict = ("2026" if len(p26) >= max(len(R["l26"]) - 2, len(R["l26"] & R["l22"]) + 1) else
                   "2022 (a test file?)" if (R["l22"] and have <= R["l22"]) or len(only22) >= 3 else "unclear")
        e["letters"] = {"lists": len(letters), "verdict": verdict, "found_2026": p26,
                        "missing_2026": sorted(R["l26"] - have), "only_2022": only22, "unknown": sorted(have - R["l22"] - R["l26"])}
        need = dict(RESULTS_OK)
        if cls == "results-locality":
            need.pop("station")
        e["aliases"], e["missing"] = aliases_for(header, roles, need)
        e["fits"] = "results_url" if cls == "results-ballot" else "results_url_localities"
        if cls == "results-ballot":
            e["reader"] = reader_check(body, e["aliases"], header, letters, roles) if tab["format"] == "csv" else \
                {"ok": False, "error": f"{tab['format']}: the feed reads CSV only (a converter is a code change)"}
        if env and env == len(rows):
            e.update(envelopes_only=True, fits="none (double envelopes only)")
            notes.append("double envelopes only: the feed takes envelopes from the 9999 rows of the results file; "
                         "a separate file needs a code change (or a results file that includes them)")
        elif env:
            notes.append(f"{env} double-envelope rows (סמל ישוב 9999)")
    elif cls == "turnout-station":
        R = ref()
        names, alias_ok = R["station_names"], R["station_aliases"]
        by_pct = "voters" not in roles and "percent" in roles and "percent" in names   # voters = % × eligible
        need = {r: names[r] for r in ("code", "station", "percent" if by_pct else "voters", "eligible")}
        if "eligible" not in roles and not by_pct:
            notes.append("no eligible-voters column: the feed computes pace against 2022, not turnout %")
        e["aliases"], e["missing"] = aliases_for(header, roles, need, optional=() if by_pct else ("eligible",))
        e["fits"] = "station_turnout_url"
        if e["aliases"] and not alias_ok and tab["format"] == "csv":
            notes.append("the per-station turnout reader (live_fetch.station_rows) does not apply column_aliases yet: "
                         "convert the file to live_input/stations.csv (--convert), or add alias support")
        rd = e["reader"] = station_check(body, e["aliases"] if alias_ok else {})
        pv = [] if "voters" in roles else [x for x in (num(val(rec, "percent"), percent=True) for rec in rows) if x is not None]
        if rd["ok"] and pv and max(pv) <= 1 and rd.get("turnout") is not None and rd["turnout"] < 0.02:
            rd.update(ok=False, error=f"every turnout % in the file is at most 1 (fractions?), and the reader made a "
                                      f"turnout of {rd['turnout']:.2%} of them")
        # what the feed takes is whatever its reader does: these notes follow the reader's result, never a rule kept here
        if rd["ok"] is False:
            err = printable(rd["error"], 90) + ("…" if len(rd["error"]) > 90 else "")     # in full: reader.error
            notes.append(f"the feed's reader fails on this {tab['format']} file ({err})" +
                         (f"; columns not found: {', '.join(e['missing'])}" if e["missing"] else "") +
                         "; convert the stored copy to live_input/stations.csv (--convert)")
        elif rd["ok"] is None:
            notes.append(f"the feed's reader was not run ({rd['error']}); convert the stored copy (--convert) and "
                         "check its feed_reader line, or run the report where live_fetch loads")
        e["release"] = release_hint(e)
    elif cls == "turnout-locality":
        e["fits"] = "none (by locality: the feed reads stations); usable by hand"
    elif cls == "turnout-national":
        e["fits"] = "live_input/turnout.json (by hand)"
    return e


def aliases_for(header, roles, need, optional=()):
    """{their header: the name the reader expects} for each role the reader does not find under a name it
    accepts, and the required names that are not there at all."""
    aliases, missing = {}, []
    for r, ok in need.items():
        if any(h in ok for h in header):
            continue
        if r in roles:
            aliases[roles[r]] = EXPECT[r]
        elif r not in optional:
            missing.append(EXPECT[r])
    return aliases, missing


def station_check(body, aliases):
    """Run the feed's own per-station reader on the file's bytes, whatever their format, as turnout_pass reads a
    release (read_stations: check_body, then station_rows with the suggested column_aliases when it applies them),
    as reader_check does for results. ok None when the reader could not be loaded or compiled: then nothing is
    assumed about what it takes. "turnout" is Σ voters / Σ eligible over the rows it read with both."""
    fn, err = station_reader()
    if fn is None:
        return {"ok": None, "reader": "not run", "error": f"not checked: live_fetch.station_rows not loaded ({err})"[:240]}
    name = _STATION["name"]
    try:
        rows, excluded = read_stations(body, aliases)
    except NameError as exc:                        # compiled from source without something it needs
        return {"ok": None, "reader": name, "error": f"not checked: {exc}"[:200]}
    except Exception as exc:                        # noqa: BLE001
        return {"ok": False, "reader": name, "error": f"{exc.__class__.__name__}: {exc}"[:200]}
    out = {"reader": name, "rows": len(rows), "excluded": excluded}
    ve = [(r.get("voters"), r.get("elig")) for r in rows if isinstance(r, dict)]
    ve = [(v, el) for v, el in ve if isinstance(v, (int, float)) and isinstance(el, (int, float)) and el > 0]
    if ve:
        out["turnout"] = round(sum(v for v, _ in ve) / sum(el for _, el in ve), 4)
    bad = excluded.get("unreadable", 0)
    if not rows or bad > UNREADABLE_MAX * (len(rows) + bad):
        return {"ok": False, **out, "error": (f"{bad} of {len(rows) + bad} rows unreadable (a figure it cannot parse: the "
                                              "feed leaves the row out)") if bad else "no rows"}
    return {"ok": True, **out}


def release_hint(e):
    """The release's cut-off time, for sectors_time in live_input/turnout.json: the file's time column, else an
    hour in its name. Last-Modified is the upload time (later than the cut-off), shown for reference only."""
    out, t = {}, (e.get("table") or {}).get("data_time")
    m = HOUR.search(str(t or ""))
    base = urllib.parse.unquote(e["url"]).split("?", 1)[0].rsplit("/", 1)[-1]
    n = re.search(r"(?<!\d)(0?\d|1\d|2[0-3])[:_.-]?00(?!\d)", base) or re.search(r"[_-](0?[7-9]|1\d|2[0-2])(?=\.\w+$)", base)
    if m:
        out.update(sectors_time=f"{int(m.group(1)):02d}:{m.group(2)}", source="the file's time column")
    elif n:
        out.update(sectors_time=f"{int(n.group(1)):02d}:00", source="the file name")
    try:
        lm = email.utils.parsedate_to_datetime(e["last_modified"]).astimezone(IL) if e.get("last_modified") else None
    except (TypeError, ValueError):
        lm = None
    if lm:
        out["last_modified_il"] = lm.strftime("%d.%m %H:%M")
    return out or None


def reader_check(body, aliases, header, letters, roles):
    """Run the feed's own reader (build_data.read_expb, lenient as on election night) on the file."""
    if read_expb is None:
        return {"ok": None, "error": f"reader not loaded ({READER_ERR})"}
    fd, path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        tries = [[]]
        extra = [h for h in header if h not in OFFICIAL_META and h not in letters and h not in roles.values() and h]
        if extra:
            tries.append(extra)               # numeric columns that are not lists: what ignore_columns would drop
        err = ""
        for ign in tries:
            checks = {}
            try:
                cols, rows = read_expb(path, strict=False, checks=checks, ignore_columns=ign, column_aliases=aliases or None)
                return {"ok": True, "lists": len(cols), "rows": len(rows), "ignore_columns": ign, **checks}
            except Exception as exc:
                err = f"{exc.__class__.__name__}: {exc}".replace(path, "file")[:200]
        return {"ok": False, "error": err}
    finally:
        os.remove(path)


# ------------------------------------------------------------------ one URL
BINARY = ("zip", "pdf", "xls", "binary")
STORE_CLASSES = ("turnout-station", "turnout-locality", "results-ballot", "results-locality")


def candidate_file(e):
    """A file whose bytes are kept: anything classified as turnout or results, and an unreadable data file
    (xls, a broken xlsx, JSON, PDF …) whose address talks about turnout or results."""
    if e.get("cls") in STORE_CLASSES:
        return True
    u = urllib.parse.unquote(e["url"])
    return e.get("cls") == "data-other" and e.get("kind") != "xml" and bool(INTEREST.search(u)) and bool(DATA.search(u))


def analyze(url, r, keep=None):
    """One answer -> its report entry, and the text to harvest links from. `keep` (a dict) receives the
    body of a candidate file (candidate_file) by URL."""
    e = {"url": url, "status": r.get("status", 0)}
    if "%" in url and urllib.parse.unquote(url) != url:
        e["url_decoded"] = urllib.parse.unquote(url)
    if r.get("error"):
        e.update(cls="error", error=r["error"])
        if r.get("local"):
            e["local"] = True
        return e, None
    h, body = r["headers"], r["body"]
    for k, n in (("type", "Content-Type"), ("length", "Content-Length"), ("last_modified", "Last-Modified"),
                 ("etag", "ETag"), ("cache", "Cache-Control"), ("age", "Age"), ("x_cache", "X-Cache"), ("server", "Server")):
        if h.get(n):
            e[k] = h.get(n)
    if r["final"] != url:
        e["final_url"] = r["final"]
    e.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), ms=r["ms"])
    if r.get("truncated"):
        e["truncated"] = True
    kind = e["kind"] = sniff(body, e.get("type"), url)
    text, enc = decode(body, r.get("truncated"))
    if kind in BINARY:
        e["first"] = f"(binary: {kind})"
    else:
        e.update(encoding=enc, first=printable(text))
    if not 200 <= e["status"] < 300:
        e.update(cls="error", hint=server_hint(e["status"], h, body), first=e.get("first", "")[:120])
        if e["status"] == 404:                      # hundreds of these per run: the hint says enough
            for k in ("first", "sha256", "encoding", "kind", "ms"):
                e.pop(k, None)
        return e, None
    low = (text[:20000] + " " + r["final"]).lower()
    if "maintenance" in r["final"].lower() or (kind == "html" and re.search(r"maintenance|תחזוקה|האתר אינו זמין|בשיפוצים", low)):
        e.setdefault("notes", []).append("maintenance page")
    tab = None
    try:
        if kind == "text":
            tab = csv_table(text)
        elif kind == "zip":
            tab = xlsx_table(body)
        elif kind == "json":
            obj = json.loads(text)
            tab = json_table(obj)
            if not tab and isinstance(obj, dict):
                hours = {k: v for k, v in obj.items() if HOUR.fullmatch(str(k)) and isinstance(v, (int, float))}
                if len(hours) >= 2:
                    e.update(cls="turnout-national", hourly=hours, fits="live_input/turnout.json (by hand)")
    except Exception as exc:
        e.setdefault("notes", []).append(f"could not read as {kind}: {exc.__class__.__name__}: {exc}"[:160])
    if tab and tab["header"]:
        describe_table(e, tab, body)
    elif "cls" not in e:
        if kind == "xml" and b"ListBucketResult" in body[:2000]:
            e["cls"] = "listing"
        elif kind in ("html", "xml", "js", "text"):
            hours, ctx = hourly_figures(text) if kind in ("html", "xml", "text") else ({}, "")
            if len(hours) >= 2:
                e.update(cls="turnout-national", hourly=hours, context=printable(ctx, 200), fits="live_input/turnout.json (by hand)")
            else:
                e["cls"] = "html" if kind == "html" else "data-other" if kind in ("text", "xml") else "script"
            if kind == "html":
                m = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
                if m:
                    e["title"] = printable(html.unescape(m.group(1)).strip(), 120)
        else:
            e["cls"] = "data-other"
            if kind == "pdf":
                e.setdefault("notes", []).append("PDF: figures have to be entered by hand")
            elif kind == "xls":
                e.setdefault("notes", []).append("xls (Excel 97–2003): save the stored copy as xlsx or CSV, then --convert")
    if keep is not None and candidate_file(e):
        keep[url] = (body, bool(r.get("truncated")))
    return e, (text if kind in ("html", "js", "xml", "json", "text") else None)


# ------------------------------------------------------------------ harvesting links from pages and scripts
URL_ABS = re.compile(r"""https?://[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s"'<>()\\`{}|^]*)?""")
# not <meta content=…>: that is prose (description, keywords, og:title), and harvested as a relative link it
# became a request with raw Hebrew and spaces; absolute og:url / og:image values are caught by URL_ABS
ATTR = re.compile(r"""(?:href|src|data-src|data-url|action)\s*=\s*["']([^"'#<>]+)["']""", re.I)
REFRESH = re.compile(r"""content\s*=\s*["']\s*\d+\s*;\s*url\s*=\s*['"]?([^"'>\s]+)""", re.I)   # <meta http-equiv=refresh>
ANCHOR = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*["']([^"'#<>]+)["'][^>]*>(.*?)</a\s*>""", re.I | re.S)
QUOTED = re.compile(r"""["'`]((?:\.{0,2}/)?[A-Za-z0-9_\-./%]*(?:\.(?:csv|json|xlsx?|zip|pdf|txt|xml)|/files/[^"'`\s]*|/api/[^"'`\s]*|/data/[^"'`\s]*|files/[^"'`\s]+)(?:\?[^"'`\s]*)?)["'`]""", re.I)
SCRIPT = re.compile(r"""["'`]((?:\.{0,2}/|https?://)?[A-Za-z0-9_\-./%:]+\.m?js)(?:\?[^"'`\s]*)?["'`]""")
FRAG = re.compile(r"""["'`]([^"'`\n]{0,100}(?:files/|\.csv|\.xlsx|/api/|turnout|kalpi|ballot|percent)[^"'`\n]{0,100})["'`]""", re.I)
JS_CONTEXT = re.compile(r"files/|turnout|kalpi|/api/", re.I)
ROBOTS = re.compile(r"(?im)^\s*(?:dis)?allow:\s*(\S+)")
S3KEY = re.compile(r"<Key>([^<]+)</Key>")
ASSET = re.compile(r"\.(?:png|jpe?g|gif|svg|webp|ico|css|woff2?|ttf|eot|otf|mp4|webm|mp3|map)(?:[?#]|$)", re.I)
DATA = re.compile(r"\.(?:csv|json|xlsx?|zip|pdf|txt|xml)(?:[?#]|$)|/files/|/api/|/data/", re.I)
# not "election"/"בחירות": every page of the CEC sites has it, and the crawl would follow all of them
INTEREST = re.compile(r"turnout|percent|hatzba|achuz|ahuz|kalpi|ballot|result|voting|envelop|maatafot|"
                      r"הצבעה|קלפי|תוצאות|מעטפות", re.I)
MAX_FRAGS = 30


def allowed(url, allow):
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in allow)


def resolve(base, m):
    """An href, src or quoted path -> an absolute, percent-encoded http(s) URL, or None. Never raises: one
    malformed link on a page (e.g. href="//[x/…", an invalid IPv6 literal) must not stop the run."""
    try:
        m = re.sub(r"[\t\r\n]", "", html.unescape(m.strip())).replace("\\/", "/")
        if not m or m.startswith(("javascript:", "mailto:", "tel:", "data:", "#", "${")) or "${" in m or "{{" in m:
            return None
        u = urllib.parse.urljoin(base, m).split("#")[0]
        if not u.startswith(("http://", "https://")):
            return None
        u = enc_url(u)
        return u if host_of(u) else None
    except ValueError:
        return None


def harvest(text, page, doc, kind):
    """Links, scripts, unresolved fragments, and the links whose anchor text talks about turnout or results
    (`named`: gov.il news addresses are numbers or English slugs) in a page or script. `doc` is the page a
    script was loaded by: relative fetches in a bundle resolve against the document, not the script."""
    links, scripts, frags, named = set(), set(), [], set()
    base = doc if kind == "js" else page

    def frag(m):
        if len(frags) < MAX_FRAGS and m not in frags:
            frags.append(m)
    raw = set(URL_ABS.findall(text)) | set(QUOTED.findall(text))
    if kind == "html":
        raw |= set(ATTR.findall(text)) | set(REFRESH.findall(text))
        for href, label in ANCHOR.findall(text):
            u = resolve(page, href)
            if u and not ASSET.search(u) and INTEREST.search(html.unescape(re.sub(r"<[^>]+>", " ", label))):
                named.add(u)
    if kind == "text":
        raw |= set(ROBOTS.findall(text))
    if kind == "xml":
        raw |= {"/" + k.lstrip("/") for k in S3KEY.findall(text)}
    for m in sorted(raw):
        u = resolve(base, m)
        if u and kind == "js" and re.search(r"(?:^|/)\.\w+$|[_-]$", m):   # "/files/turnout_" + h + ".csv": pieces
            frag(m)
            continue
        if not u or ASSET.search(u):
            continue
        (scripts if re.search(r"\.m?js(?:\?|$)", u) else links).add(u)
    if kind in ("html", "js"):
        scripts |= {u for u in (resolve(base, m) for m in SCRIPT.findall(text)) if u}
    if kind == "html":
        for m in FRAG.findall(text):
            if ("${" in m or "+" in m or not resolve(page, m)) and not ASSET.search(m):
                frag(m)
    elif kind == "js":      # ±80 characters around each mention, so a split concatenation is read whole
        end = -1
        for mt in JS_CONTEXT.finditer(text):
            if mt.start() < end:
                continue
            a, end = max(0, mt.start() - 80), mt.end() + 80
            frag(re.sub(r"\s+", " ", text[a:end]))
            if len(frags) >= MAX_FRAGS:
                break
    return links, scripts, frags, named


def probe_one(net, url, keep=None, answer=None):
    """analyze(url, net.get(url)) that never raises: a URL that trips this script is one error entry.
    `answer` replaces the request (a file read from the repository)."""
    try:
        return analyze(url, answer if answer is not None else net.get(url), keep)
    except Exception as exc:                        # noqa: BLE001
        return {"url": url, "status": 0, "cls": "error", "local": True,
                "error": f"discover.py failed on this URL: {exc.__class__.__name__}: {exc}"[:200]}, None


def crawl(net, seeds, allow, pool, results, sources, max_pages=80, keep=None):
    """Seeds, then the scripts and the interesting pages they link to (two levels). Returns the data-like
    links found and, per page, what was harvested."""
    level, seen, found_on, log, js_per_host = [(u, u) for u in seeds], set(), collections.defaultdict(set), {}, collections.Counter()
    for depth in range(3):
        todo = [(u, d) for u, d in dict(level).items() if u not in seen][:max_pages]
        seen |= {u for u, _ in todo}
        nxt = []
        for (u, doc), (e, text) in zip(todo, pool.map(lambda ud: probe_one(net, ud[0], keep), todo)):
            results[u] = e
            sources[u].add("seed" if depth == 0 and u in seeds else "harvested")
            if text is None:
                continue
            try:
                links, scripts, frags, named = harvest(text, u, doc, e.get("kind"))
            except Exception as exc:                # noqa: BLE001 - a page this script cannot parse is a note, not a crash
                e.setdefault("notes", []).append(f"links not harvested: {exc.__class__.__name__}: {exc}"[:160])
                continue
            links = {x for x in links | named if allowed(x, allow)}
            data = sorted(x for x in links if DATA.search(x) or x in named or INTEREST.search(urllib.parse.unquote(x)))
            log[u] = {"links": len(links), "scripts": len(scripts), "data_links": data[:60], "fragments": frags}
            for x in data:
                found_on[x].add(u)
            if depth < 2:
                for s in sorted(scripts):
                    h = host_of(s)
                    if allowed(s, allow) and js_per_host[h] < 40 and s not in seen:
                        js_per_host[h] += 1
                        nxt.append((s, doc if e.get("kind") == "js" else u))
            if depth < 1:                           # pages that talk about turnout/results, one level down
                nxt += [(x, x) for x in data if not DATA.search(x) and x not in seen]
        level = nxt
    for x in found_on:
        sources[x].add("harvested")
    return found_on, log


# ------------------------------------------------------------------ verdicts, diff, report
def answering(e):
    return bool(e) and e.get("cls") not in (None, "error") and not e.get("spa")


def score(e):
    letters = (e.get("letters") or {}).get("verdict") == "2026"
    reader = (e.get("reader") or {}).get("ok") is True
    match = ((e.get("table") or {}).get("match_2022") or {}).get("by_number", 0)
    try:                                            # among equals, the latest release
        lm = email.utils.parsedate_to_datetime(e["last_modified"]).timestamp() if e.get("last_modified") else 0
    except (TypeError, ValueError):
        lm = 0
    return (reader, letters, M26 in e["url"], (e.get("table") or {}).get("data_time") or "", lm, match,
            (e.get("table") or {}).get("rows", 0))


def turnout_test(e, now, election_day):
    """A per-station turnout file before election day, or one uploaded before it, is a test file: turnout files
    carry no ballot letters that would tell."""
    if now.date() < election_day:
        return True
    try:
        lm = email.utils.parsedate_to_datetime(e["last_modified"]).astimezone(IL) if e.get("last_modified") else None
    except (TypeError, ValueError):
        lm = None
    return bool(lm and lm.date() < election_day)


BLOCKING = ("control", "2022/test", "letters ", "before 27.10", "uploaded before", "reader fails", "repo file")  # rule out a switch


def verdicts(entries, cfg, now, election_day, control=None):
    closed = now >= dt.datetime.combine(election_day, dt.time(22, 0), IL)
    by_url, out = {e["url"]: e for e in entries}, []
    for key, cls in (("results_url", "results-ballot"), ("results_url_localities", "results-locality"),
                     ("station_turnout_url", "turnout-station")):
        cur = cfg.get(key)
        ce = (by_url.get(cur) or by_url.get(enc_url(cur))) if cur else None

        def tags(e):
            t, v = [], (e.get("letters") or {}).get("verdict", "")
            if e["url"] == control:
                t.append("control")
            if v.startswith("2022"):
                t.append("2022/test")
            elif cls.startswith("results") and v != "2026":
                t.append(f"letters {v or 'not checked'}")
            if cls.startswith("results") and not closed and (e.get("table") or {}).get("counted_rows") and not v.startswith("2022"):
                t.append("counted rows before 22:00: test")
            if cls == "turnout-station" and turnout_test(e, now, election_day):
                t.append("before 27.10: test?" if now.date() < election_day else "uploaded before 27.10: test?")
            if (e.get("reader") or {}).get("ok") is False:
                t.append("reader fails")
            if not is_web(e["url"]):
                t.append("repo file")
            return t

        def usable(e):
            return not any(x.startswith(BLOCKING) for x in tags(e))
        cands = sorted((e for e in entries if e.get("cls") == cls and answering(e) and not e.get("envelopes_only")),
                       key=lambda e: (usable(e), score(e)), reverse=True)
        best = next((e for e in cands if usable(e)), None)
        test = lambda e: e and ((e.get("letters") or {}).get("verdict", "").startswith("2022")  # noqa: E731
                                or (cls.startswith("results") and not closed and (e.get("table") or {}).get("counted_rows")))
        ok = lambda e: (e.get("reader") or {}).get("ok") is not False  # noqa: E731
        if cur and not is_web(cur):                 # the operator's converted copy (live_input/stations.csv): read, not probed
            state = (f"repo copy, {'ok' if ok(ce) else 'reader fails'}" if ce and ce.get("cls") == cls else
                     f"repo copy, reads as {ce.get('cls')} {ce.get('error', '')}".strip() if ce else "repo copy, not read")
        elif ce and ce.get("cls") == cls:
            state = ("test file" if test(ce) else "test file?" if cls == "turnout-station" and turnout_test(ce, now, election_day)
                     else "ok" if ok(ce) else "reader fails")
        elif ce:
            state = f"answers as {ce.get('cls')} ({ce.get('status') or ce.get('error', '')})"
        else:
            state = "not set" if not cur else "not probed"
        switch = best if (best and best["url"] != (ce or {}).get("url", cur) and (not cur or is_web(cur))
                          and (not ce or ce.get("cls") != cls or score(best) > score(ce))) else None
        v = {"key": key, "current": cur, "state": state, "best": best and best["url"],
             "switch": switch and switch["url"], "aliases": (switch or ce or {}).get("aliases") or {},
             "candidates": [c["url"] + (f" ({', '.join(tags(c))})" if tags(c) else "") for c in cands[:6]]}
        if cls == "turnout-station" and (switch or ce or {}).get("release"):
            v["release"] = (switch or ce)["release"]
        out.append(v)
    nat = [e for e in entries if e.get("cls") == "turnout-national" and answering(e)]
    out.append({"key": "national hourly (live_input/turnout.json)", "current": None,
                "state": f"{len(nat)} page(s) with hourly figures" if nat else "none found",
                "best": nat[0]["url"] if nat else None, "switch": None, "aliases": {},
                "candidates": [f"{e['url']} {e.get('hourly')}" for e in nat[:5]]})
    return out


FIELDS = ("status", "cls", "bytes", "last_modified", "etag", "sha256")    # the hashes last: they fill a Markdown cell


def compare(prev, cur):
    if not prev:
        return None
    p = {e["url"]: e for e in prev.get("urls", [])}
    new, changed, gone = [], [], []
    for u, e in cur.items():
        o = p.get(u)
        page = e.get("cls") in ("html", "script")
        if answering(e) and not answering(o) and not (page and o and o.get("spa")):   # a shell that changed is not news
            new.append({"url": u, "cls": e["cls"], "was": (o.get("status") or o.get("error")) if o else "not probed"})
        elif answering(e) and answering(o):
            fields = ("status", "cls") if page else FIELDS
            d = {f: [o.get(f), e.get(f)] for f in fields if o.get(f) != e.get(f)}
            if d:
                changed.append({"url": u, "cls": e["cls"], "diff": d})
    for u, o in p.items():
        if answering(o) and o.get("cls") not in ("html", "script") and not answering(cur.get(u)):
            e = cur.get(u)
            gone.append({"url": u, "cls": o["cls"], "now": (e.get("status") or e.get("error")) if e else "no longer linked"})
    return {"previous": prev.get("generated_at"), "new": new, "changed": changed, "gone": gone}


def cell(x, n=90):
    s = "" if x is None else str(x)
    s = s if len(s) <= n else s[:n - 1] + "…"
    return s.replace("|", "\\|").replace("\n", " ")


def table(rows, cols):
    """cols: (title, value function[, cell width])."""
    out = ["| " + " | ".join(c[0] for c in cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(cell(c[1](r), *c[2:]) for c in cols) + " |" for r in rows]
    return "\n".join(out)


def brief(e):
    t, bits = e.get("table") or {}, []
    if e.get("url_decoded"):
        bits.append(f"address {e['url_decoded']}")
    if t:
        bits.append(f"{t.get('format')} {t.get('rows')} rows")
        if t.get("localities") is not None:
            bits.append(f"{t['localities']} loc, {t.get('counted_rows')} counted")
        if t.get("match_2022"):
            bits.append(f"2022 stations {t['match_2022']['by_number']:.0%}")
    if e.get("letters"):
        bits.append(f"letters {e['letters']['verdict']}")
    if e.get("reader"):
        bits.append("reader " + {True: "ok", False: "FAILS", None: "not run"}[e["reader"].get("ok")])
    if e.get("aliases"):
        bits.append(f"aliases {json.dumps(e['aliases'], ensure_ascii=False)}")
    if e.get("hourly"):
        bits.append(json.dumps(e["hourly"]))
    if (e.get("release") or {}).get("sectors_time"):
        bits.append(f"release {e['release']['sectors_time']} (from {e['release']['source']})")
    bits += e.get("notes", [])
    if e.get("saved"):
        bits.append(f"stored: {e['saved']}")
    elif e.get("not_saved"):
        bits.append(f"not stored: {e['not_saved']}")
    return "; ".join(bits)


def short_hash(k, x):
    return x[:12] if k == "sha256" and isinstance(x, str) else x


def markdown(rep, short=False):
    L = [f"## CEC file discovery, {rep['generated_he']} Israel time ({rep['mode']}, {rep['runner']['where']})", "",
         f"{rep['counts']['probed']} URLs probed, {rep['counts']['answered']} answered. Control (2022 file): "
         f"{rep['control']}. How to read this: docs/FILE_DISCOVERY.md.", "",
         table(rep["verdicts"], [("live_config key", lambda v: v["key"]), ("now", lambda v: v["current"] or "—"),
                                 ("state", lambda v: v["state"]), ("switch to", lambda v: v["switch"] or "—"),
                                 ("column_aliases", lambda v: json.dumps(v["aliases"], ensure_ascii=False) if v["aliases"] else "")])]
    others = [(v["key"], c) for v in rep["verdicts"] if not v["key"].startswith("national")
              for c in v["candidates"] if c.split(" (", 1)[0] not in (v["switch"], v["current"])]
    if others:
        L += ["", "Other candidates (in brackets: why not suggested, or what to check):", ""]
        L += [f"- {k}: {cell(c, 220)}" for k, c in others[:12 if short else 30]]
    if rep.get("suggested_config"):
        L += ["", "Suggested live_config.json change (confirm first: header, rows, 2026 letters, time):", "", "```json",
              json.dumps(rep["suggested_config"], ensure_ascii=False, indent=1), "```"]
    rel = next((v.get("release") for v in rep["verdicts"]
                if v["key"] == "station_turnout_url" and (v["switch"] or v["current"])), None)
    if rel:
        L += ["", "Per-station release time: " + (f'"sectors_time": "{rel["sectors_time"]}" (from {rel["source"]})'
                                                  if rel.get("sectors_time") else "not in the file or its name") +
              (f"; Last-Modified {rel['last_modified_il']} Israel time is the upload, later than the cut-off"
               if rel.get("last_modified_il") else "") +
              ". In live_input/turnout.json, in the same commit as the switch, use the cut-off time the CEC states."]
    d = rep.get("diff")
    if d:
        L += ["", f"### Since {d['previous']}: {len(d['new'])} new, {len(d['changed'])} changed, {len(d['gone'])} gone"]
        rows = ([("new", x["url"], x["cls"], f"was {x['was']}") for x in d["new"]] +
                [("changed", x["url"], x["cls"], ", ".join(f"{k}: {short_hash(k, a)} → {short_hash(k, b)}"
                                                            for k, (a, b) in x["diff"].items())) for x in d["changed"]] +
                [("gone", x["url"], x["cls"], f"now {x['now']}") for x in d["gone"]])
        if rows:
            L += ["", table(rows[:15 if short else 200], [("", lambda r: r[0]), ("URL", lambda r: r[1]), ("class", lambda r: r[2]),
                                                       ("what", lambda r: r[3], 200)])]
    data = [e for e in rep["urls"] if answering(e) and e["cls"] not in ("html", "script")]
    if data:
        L += ["", "### Files and pages with data", "",
              table(data[:12 if short else 300], [("class", lambda e: e["cls"]), ("URL", lambda e: e["url"]),
                                                  ("HTTP", lambda e: e["status"]), ("bytes", lambda e: e.get("bytes")),
                                                  ("last-modified", lambda e: e.get("last_modified")), ("details", brief, 400)])]
    stored = [e for e in rep["urls"] if e.get("saved")]
    if stored:
        L += ["", f"### Stored files ({len(stored)}; on the ops-reports branch under reports/, locally under the --out folder)", "",
              "`git fetch origin ops-reports && git show origin/ops-reports:reports/<path> > <file>`; convert a turnout "
              "release with `python3 pipeline/discover.py --convert <file>` (docs/FILE_DISCOVERY.md §3).", "",
              table(stored[:12 if short else 100], [("class", lambda e: e["cls"]), ("URL", lambda e: e.get("url_decoded") or e["url"]),
                                                    ("bytes", lambda e: e.get("bytes")), ("path", lambda e: e["saved"])])]
    L += ["", "### Hosts", "", table(sorted(rep["hosts"].items()), [
        ("host", lambda h: h[0]), ("IPs", lambda h: ", ".join(h[1]["ips"][:3])), ("probed", lambda h: h[1]["probed"]),
        ("answered", lambda h: h[1]["answered"]), ("status codes", lambda h: json.dumps(h[1]["status"])),
        ("hint", lambda h: "; ".join(h[1]["hints"][:2]))])]
    if short:
        return "\n".join(L) + "\n"
    pages = [e for e in rep["urls"] if answering(e) and e["cls"] in ("html", "script")]
    if pages:
        L += ["", "### Pages and scripts that answered", "", table(pages, [
            ("URL", lambda e: e["url"]), ("HTTP", lambda e: e["status"]), ("title / notes", lambda e: "; ".join(
                ([e["title"]] if e.get("title") else []) + e.get("notes", []) + (["same page as the site root"] if e.get("spa") else [])))])]
    hv = [(u, h) for u, h in rep["harvest"].items() if h["data_links"] or h["fragments"]]
    if hv:
        L += ["", "### Harvested from pages and scripts", ""]
        for u, h in hv:
            L.append(f"- {u}: {h['links']} links, {h['scripts']} scripts")
            L += [f"  - {x}" for x in h["data_links"][:25]]
            L += [f"  - fragment: `{cell(x, 180).replace('`', chr(39))}`" for x in h["fragments"][:12]]
    errs = [e for e in rep["urls"] if not answering(e)]
    L += ["", f"<details><summary>{len(errs)} URLs that did not answer with data</summary>", "",
          table(errs, [("URL", lambda e: e["url"]), ("HTTP", lambda e: e["status"]),
                       ("why", lambda e: e.get("error") or e.get("hint") or ("same page as the site root" if e.get("spa") else ""))]),
          "", "</details>"]
    return "\n".join(L) + "\n"


def host_table(entries, rewrite, only_rewritten):
    hosts = {}
    for e in entries:
        if not is_web(e["url"]):                    # the operator's copy in the repository
            continue
        h = host_of(e["url"])
        d = hosts.setdefault(h, {"probed": 0, "answered": 0, "status": collections.Counter(), "hints": collections.Counter()})
        d["probed"] += 1
        d["answered"] += answering(e)
        d["status"][str(e.get("status") or ("bad URL" if e.get("local") else "no answer"))] += 1
        if e.get("hint") or e.get("error"):
            d["hints"][e.get("hint") or re.sub(r":.*", "", e.get("error", ""))] += 1
    for h, d in hosts.items():
        real = next((host_of(dst) for src, dst in rewrite if host_of(src) == h),
                    None if only_rewritten else h)
        try:                                        # CloudFront, a gov.il front end, or no DNS at all
            d["ips"] = sorted({a[4][0] for a in socket.getaddrinfo(real, 443, proto=socket.IPPROTO_TCP)})[:6] if real else ["skipped"]
        except Exception as exc:
            d["ips"] = [f"DNS: {exc.__class__.__name__}"]
        d["status"], d["hints"] = dict(d["status"]), [k for k, _ in d["hints"].most_common(3)]
    return hosts


# ------------------------------------------------------------------ the ops-reports branch
def git(*args, cwd=ROOT, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:300]}")
    return r


def fetch_branch(branch, remote):
    """True when the branch exists on the remote (then origin/<branch> is up to date)."""
    if git("ls-remote", "--exit-code", "--heads", remote, branch, check=False).returncode:
        return False
    git("fetch", "-q", "--depth=1", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}")
    return True


def previous_from_branch(branch, remote):
    try:
        if fetch_branch(branch, remote):
            return json.loads(git("show", f"{remote}/{branch}:reports/latest.json").stdout)
    except Exception as exc:
        print(f"previous report not read: {exc}", file=sys.stderr)
    return None


def push_report(files, branch, remote, message):
    """Commit reports/ to the orphan branch and push. Same cycle as the live feed: fetch, reset to the
    branch tip, copy, commit, push; a rejected push repeats it. Never touches main (a Pages build)."""
    wt = tempfile.mkdtemp(prefix="ops-reports-")
    tmp = f"ops-reports-tmp-{os.getpid()}"
    ident = [] if git("config", "user.email", check=False).stdout.strip() else [
        "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]
    try:
        git("worktree", "add", "-q", "--detach", "-f", wt, "HEAD")
        for attempt in range(6):
            if fetch_branch(branch, remote):
                git("checkout", "-q", "--detach", f"{remote}/{branch}", cwd=wt)
                git("reset", "-q", "--hard", f"{remote}/{branch}", cwd=wt)
            else:                                   # first report; a retry drops the branch its rejected commit made
                git("checkout", "-q", "--detach", cwd=wt, check=False)
                git("branch", "-D", tmp, cwd=wt, check=False)
                git("checkout", "-q", "--orphan", tmp, cwd=wt)
                git("rm", "-rfq", "--ignore-unmatch", ".", cwd=wt)
            git("clean", "-fdxq", cwd=wt)
            os.makedirs(os.path.join(wt, "reports"), exist_ok=True)
            for name, src in files.items():             # name may be a path: files/<stamp>/<name>
                os.makedirs(os.path.dirname(os.path.join(wt, "reports", name)), exist_ok=True)
                shutil.copyfile(src, os.path.join(wt, "reports", name))
            git("add", "reports", cwd=wt)
            if not git("diff", "--cached", "--quiet", cwd=wt, check=False).returncode:
                return "unchanged"
            git(*ident, "commit", "-qm", message, cwd=wt)
            if not git("push", "-q", remote, f"HEAD:refs/heads/{branch}", cwd=wt, check=False).returncode:
                return git("rev-parse", "--short", "HEAD", cwd=wt).stdout.strip()
            time.sleep(2 + 3 * attempt)
        raise RuntimeError(f"push to {branch} rejected 6 times")
    finally:
        git("worktree", "remove", "--force", wt, check=False)
        shutil.rmtree(wt, ignore_errors=True)
        git("worktree", "prune", check=False)
        git("branch", "-D", tmp, check=False)


# ------------------------------------------------------------------ stored copies, and converting one
STORE_MAX = 8_000_000                   # bytes per stored file
STORE_RUN_MAX = 40_000_000              # bytes stored per run
RESULTS_EVERY = dt.timedelta(hours=3)   # a results file that keeps changing is stored at most this often
STATIONS_HEADER = ["סמל ישוב", "שם ישוב", "קלפי", "בזב", "מצביעים"]   # live_input/stations.csv (live_input/README.md)
UNREADABLE_MAX = 0.01                   # share of a figure column that may be unreadable before --convert (and the check) stop
NOT_REPORTED = {"", "-", "–", "—", "\u2212"}  # a figure cell of a station that has not reported yet


def safe_name(url, sha, e):
    p = urllib.parse.urlsplit(url)
    base = urllib.parse.unquote(p.path.rstrip("/").rsplit("/", 1)[-1]) or "index"
    if p.query:
        base += "_" + urllib.parse.unquote(p.query)
    stem = re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9.-]+", "_", f"{p.hostname}_{base}")).strip("._")[:90]
    if not re.search(r"\.[A-Za-z0-9]{2,5}$", stem):
        fmt = (e.get("table") or {}).get("format")
        stem += {"json": ".json", "xls": ".xls", "pdf": ".pdf", "binary": ".bin",
                 "zip": ".xlsx" if fmt == "xlsx" else ".zip"}.get(e.get("kind"), ".csv" if fmt == "csv" else ".txt")
    return f"{sha[:8]}-{stem}"


def store_files(results, kept, prev, now, closed, out, stamp, max_bytes=STORE_MAX):
    """Write the bytes of the candidate files to <out>/files/<stamp>/ (pushed as reports/files/<stamp>/), so a
    release the feed cannot read can be converted by someone who cannot reach gov.il. Each version (SHA-256)
    once across runs (the index travels in report.json); turnout files every time they change, a results file
    at most every 3 hours; nothing over max_bytes; and no results file with counted rows before the polls
    close (test data that would read as results), unless it is a copy of 2022. Returns ({path under reports/:
    local path}, the updated index)."""
    index, files, total = dict((prev or {}).get("files_index") or {}), {}, 0
    for u in sorted(kept, key=lambda u: (not str(results.get(u, {}).get("cls", "")).startswith("turnout"), u)):
        e, (body, truncated) = results.get(u), kept[u]
        if not e or not answering(e) or not candidate_file(e):
            continue
        sha, cls = e.get("sha256"), e["cls"]
        if sha in index:
            e["saved"] = index[sha]["path"]
            continue
        last = max((v["at"] for v in index.values() if v.get("url") == u), default=None)
        if truncated or len(body) > max_bytes:
            why = f"over the {max_bytes / 1e6:g} MB limit for a stored copy"
        elif total + len(body) > STORE_RUN_MAX:
            why = f"this run already stored {total / 1e6:.1f} MB"
        elif (cls.startswith("results") and not closed and (e.get("table") or {}).get("counted_rows")
              and not (e.get("letters") or {}).get("verdict", "").startswith("2022")):
            why = "a results file with counted rows before the polls close (test data)"
        elif cls.startswith("results") and last and now - dt.datetime.fromisoformat(last) < RESULTS_EVERY:
            at = dt.datetime.fromisoformat(last).astimezone(IL).strftime("%d.%m %H:%M")
            why = f"a version from {at} is stored (results: every 3 hours)"
        else:
            why = ""
        if why:
            e["not_saved"] = why
            continue
        name = f"files/{stamp}/{safe_name(u, sha, e)}"
        os.makedirs(os.path.dirname(os.path.join(out, name)), exist_ok=True)
        with open(os.path.join(out, name), "wb") as f:
            f.write(body)
        files[name], total, e["saved"] = os.path.join(out, name), total + len(body), name
        index[sha] = {"path": name, "url": u, "cls": cls, "bytes": len(body), "at": now.isoformat(timespec="seconds")}
    return files, index


def convert(src, dest, maps=(), blanks=()):
    """A per-station turnout release the feed's reader fails on (xlsx, JSON, UTF-16, other header names, figures
    written as 45.3% or 1,234 …) -> the CSV live_fetch.station_rows reads: סמל ישוב,שם ישוב,קלפי,בזב,מצביעים in
    UTF-8, one row per station; a station without a figure keeps a blank מצביעים. --map ROLE=HEADER names a
    column the report did not recognise (roles: code, name, station, eligible, voters, percent, time).
    Figures are read by num() (percent signs, thousands separators, a decimal comma, Arabic-Indic digits). A blank,
    '-' or a --blank TEXT is a station not reported yet; any other cell that is still not a number is counted, and
    when more than 1% of the stations' voters (or percent, or eligible) cells are, or no station has a figure,
    nothing is written and the exit status is 1: such a cell would otherwise read as 'not reported yet'."""
    body = open(src, "rb").read()
    kind = sniff(body, "", src)
    text, _ = decode(body)
    if kind == "xls":
        raise SystemExit(f"{src}: xls (Excel 97–2003): open it, save it as xlsx or CSV, and convert that")
    try:
        tab = (csv_table(text) if kind == "text" else xlsx_table(body) if kind == "zip" else
               json_table(json.loads(text)) if kind == "json" else None)
    except Exception as exc:                        # noqa: BLE001
        raise SystemExit(f"{src}: could not read as {kind}: {exc.__class__.__name__}: {exc}"[:300])
    if not tab or not tab["header"]:
        raise SystemExit(f"{src}: no table found ({kind})")
    notes, header = [], tab["header"]
    roles = table_roles(header, notes)
    for m in maps:
        r, _, h = m.partition("=")
        if h not in header:
            raise SystemExit(f"--map {m}: no column {h!r}; the header is {header[:20]}")
        roles[r.strip()] = h
    if not {"code", "station"} <= roles.keys() or not ("voters" in roles or {"percent", "eligible"} <= roles.keys()):
        raise SystemExit(f"{src}: need columns for code, station and voters (or percent and eligible); found {roles}; "
                         f"header {header[:20]}; name the missing ones with --map ROLE=HEADER")
    idx = {r: header.index(h) for r, h in roles.items()}
    blank = NOT_REPORTED | {clean(b) for b in blanks}
    vcol = "voters" if "voters" in roles else "percent"
    bad = {vcol: collections.Counter(), "eligible": collections.Counter()}     # unreadable cells by column, by text

    def get(rec, r):
        i = idx.get(r)
        return str(rec[i]).strip() if i is not None and i < len(rec) else ""

    def figure(rec, r):
        """The cell as a number: None for a blank (not reported yet), and for a cell that is not a number, a
        negative one, a count with a fraction or a percentage over 100, which is also counted in `bad`."""
        s = get(rec, r)
        if clean(s) in blank:
            return None
        v = num(s, percent=r == "percent")
        if v is not None and v >= 0 and (v <= 100 if r == "percent" else abs(v - round(v)) < 0.01):
            return v
        bad[r][s] += 1
        return None
    cells = [get(rec, "percent") for rec in tab["rows"]] if vcol == "percent" else []
    pv = [x for x in (num(s, percent=True) for s in cells if clean(s) not in blank) if x is not None]
    # a fraction (0.453) or a percentage (45.3, 45.3%): a cell written with a percent sign is a percentage
    scale = 1 if pv and max(pv) <= 1 and not any(re.search("[%\u066a]", s) for s in cells) else 100
    out, skipped, times = [], collections.Counter(), []
    for rec in tab["rows"]:
        code = num(get(rec, "code"))
        kalpi = re.sub(r"^(\d+)\.0$", r"\1", clean(get(rec, "station")).translate(DIGITS).replace("\u066b", "."))
        if not get(rec, "code") or code is None or code != int(code) or code <= 0:
            skipped["no locality code (a total or a note)"] += 1
            continue
        if int(code) in (9999, 99999):
            skipped["double envelopes (9999)"] += 1
            continue
        if not kalpi:
            skipped["no station number"] += 1
            continue
        elig = figure(rec, "eligible")
        if vcol == "voters":
            v = figure(rec, "voters")
        else:
            p = figure(rec, "percent")
            if p is not None and elig is None and clean(get(rec, "eligible")) in blank:
                bad["eligible"]["(blank, next to a turnout %)"] += 1       # voters = % × eligible cannot be computed
            v = p * elig / scale if p is not None and elig else None
        if get(rec, "time"):
            times.append(get(rec, "time"))
        out.append([int(code), get(rec, "name"), kalpi, "" if elig is None else int(round(elig)),
                    "" if v is None else int(round(v))])
    n, figures = len(out), sum(r[4] != "" for r in out)
    unreadable = {r: {"cells": sum(c.values()), "examples": dict(c.most_common(5))} for r, c in bad.items() if c}
    over = [r for r, u in unreadable.items() if u["cells"] > UNREADABLE_MAX * n]
    rel = release_hint({"url": src, "table": {"data_time": max(times) if times else None}})
    summary = {"rows": n, "skipped": dict(skipped), "columns": roles, "voters_from_percent": vcol == "percent",
               "blank_voters": n - figures, "unreadable": unreadable, "notes": notes, "release": rel}
    if not n or over or not figures:                # stop before writing: never a file that reads as "not reported"
        if not n:
            why = "no station rows: every row lacks a locality code or a station number"
            fix = "Name the columns with --map ROLE=HEADER."
        elif over:
            why = "; ".join(f"{unreadable[r]['cells']} of {n} {r} cells ({unreadable[r]['cells'] / n:.1%}) are not numbers "
                            f"it can read (more than {UNREADABLE_MAX:.0%}), e.g. " + ", ".join(
                                f"{s!r} x{k}" for s, k in unreadable[r]["examples"].items()) for r in over)
            fix = ("Each would become a blank, which the feed reads as 'not reported yet'. If it is the wrong column, name "
                   "the right one with --map ROLE=HEADER; if a text does mean 'not reported yet', pass --blank TEXT.")
        else:
            why = f"no station has a voters figure: every {roles[vcol]!r} cell is blank"
            fix = f"Is this the release itself, and the right column (--map {vcol}=HEADER)?"
        print(json.dumps({"wrote": None, **summary, "error": why}, ensure_ascii=False))
        print(f"{src}: {why}. Nothing was written. {fix}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([STATIONS_HEADER] + out)
    fn, err = station_reader()
    check = {"ok": None, "error": f"live_fetch not loaded: {err}"}
    if fn:
        try:
            rows, excluded = read_stations(open(dest, "rb").read())
            check = {"ok": bool(rows), "reader": _STATION["name"], "rows": len(rows), "excluded": excluded}
        except Exception as exc:                    # noqa: BLE001
            check = {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"[:200]}
    print(json.dumps({"wrote": dest, **summary, "feed_reader": check}, ensure_ascii=False))
    for r, u in unreadable.items():
        print(f"warning: {u['cells']} {r} cells are not numbers and were left blank (not reported): "
              + ", ".join(f"{s!r} x{k}" for s, k in u["examples"].items()), file=sys.stderr)
    print("Next, in ONE commit to main: this file as live_input/stations.csv, \"station_turnout_url\": "
          "\"live_input/stations.csv\" in pipeline/live_config.json (once), and \"sectors_time\": \"HH:MM\" (the CEC's "
          "cut-off for this release) in live_input/turnout.json.", file=sys.stderr)
    return 0 if check.get("ok") is not False else 1


# ------------------------------------------------------------------ main
def auto_mode(now, election_day):
    """Full everywhere except on election day, where the :07 run of each hour is full and the other two quick."""
    if now.date() == election_day and now.hour >= 6:
        return "full" if now.minute < 20 else "quick"
    return "full"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="discover-out", help="directory for report.json and report.md")
    ap.add_argument("--mode", choices=("auto", "full", "quick"), default="auto")
    ap.add_argument("--previous", help="an earlier report.json to compare with (with --push: reports/latest.json of the branch)")
    ap.add_argument("--candidates", help="JSON file replacing the built-in lists (see the module docstring)")
    ap.add_argument("--url", action="append", default=[], help="also probe (and harvest) this URL, e.g. one named in the news")
    ap.add_argument("--config", default=os.path.join(ROOT, "pipeline", "live_config.json"))
    ap.add_argument("--rewrite", action="append", default=[], metavar="FROM=TO", help="fetch URLs starting with FROM from TO (testing)")
    ap.add_argument("--only-rewritten", action="store_true", help="skip URLs that no --rewrite covers (testing)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--delay", type=float, default=0.25, help="seconds between request starts on one host")
    ap.add_argument("--timeout", type=float, default=20)
    ap.add_argument("--max-bytes", type=int, default=16_000_000)
    ap.add_argument("--summary", help="append a short Markdown summary here ($GITHUB_STEP_SUMMARY)")
    ap.add_argument("--push", action="store_true", help="commit the report to the ops-reports branch and push")
    ap.add_argument("--branch", default="ops-reports")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--store-max-bytes", type=int, default=STORE_MAX, help="largest file whose bytes are kept with the report")
    ap.add_argument("--convert", metavar="FILE", help="convert a stored per-station turnout release for the feed, and stop")
    ap.add_argument("--convert-out", default=os.path.join(ROOT, "live_input", "stations.csv"), help="where --convert writes")
    ap.add_argument("--map", action="append", default=[], metavar="ROLE=HEADER", help="--convert: a column it did not recognise")
    ap.add_argument("--blank", action="append", default=[], metavar="TEXT",
                    help="--convert: a cell text that means 'not reported yet' (besides a blank cell and '-')")
    ap.add_argument("--now", help=argparse.SUPPRESS)       # testing: pretend it is this Israel time, e.g. 2026-10-27T14:30
    a = ap.parse_args()
    if a.convert:
        return convert(a.convert, a.convert_out, a.map, a.blank)

    now = (dt.datetime.fromisoformat(a.now).replace(tzinfo=IL) if a.now else dt.datetime.now(dt.timezone.utc).astimezone(IL))
    try:
        cfg = json.load(open(a.config, encoding="utf-8"))
    except Exception as exc:
        print(f"config not read ({exc}); comparing with nothing", file=sys.stderr)
        cfg = {}
    election_day = dt.date.fromisoformat(cfg.get("election_day", "2026-10-27"))
    over = json.load(open(a.candidates, encoding="utf-8")) if a.candidates else {}
    mode = auto_mode(now, election_day) if a.mode == "auto" else a.mode
    prev = None
    if a.previous:
        try:
            prev = json.load(open(a.previous, encoding="utf-8"))
        except Exception as exc:
            print(f"previous report not read: {exc}", file=sys.stderr)
    elif a.push:
        prev = previous_from_branch(a.branch, a.remote)

    a.url = [enc_url(u) for u in a.url]           # every URL in the report is in the encoded form fetch() sends
    seeds = list(dict.fromkeys([enc_url(u) for u in over.get("seeds", SEEDS)] + a.url))
    allow = tuple(over.get("allow_hosts", ALLOW))
    control = enc_url(over.get("control", CONTROL))
    sources = collections.defaultdict(set)
    for u in a.url:
        sources[u].add("operator")
    probe, repo_copies = [], []
    for u, src in ([(u, "known") for u in over.get("probe", KNOWN) + [control]] +
                   [(cfg.get(k), "config") for k in ("results_url", "results_url_localities", "station_turnout_url")] +
                   [(u, "enumerated") for u in (enumerated() if over.get("enumerate", mode == "full") else [])] +
                   [(e["url"], "previous") for e in (prev or {}).get("urls", [])
                    if answering(e) and (e["cls"] not in ("html", "script") or "seed" in e.get("source", []))]):
        if u and not is_web(u):                   # a repository path (live_input/stations.csv): read, never probed
            if src == "config":
                repo_copies.append(u)
            continue
        if u:
            u = enc_url(u)
            sources[u].add(src)
            probe.append(u)

    net, results, kept = Net(a), {}, {}
    with cf.ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        found_on, log = crawl(net, seeds, allow, pool, results, sources, keep=kept)
        linked = [u for u in sorted(found_on) if DATA.search(u)][:400] + [u for u in sorted(found_on) if not DATA.search(u)][:100]
        rest = list(dict.fromkeys(u for u in probe + linked if u not in results))
        for u, (e, _) in zip(rest, pool.map(lambda u: probe_one(net, u, kept), rest)):
            results[u] = e
    for u in dict.fromkeys(repo_copies):
        try:
            with open(os.path.join(ROOT, u), "rb") as f:
                r = {"status": 200, "headers": {}, "body": f.read(), "final": u, "ms": 0}
        except OSError as exc:
            r = {"status": 0, "local": True,
                 "error": f"repository file not read: {exc.__class__.__name__} ({exc.strerror or exc})"[:200]}
        results[u] = probe_one(net, u, answer=r)[0]
        sources[u].add("config (repository file)")
    roots, split = {}, {}
    for u, e in results.items():
        try:
            split[u] = p = urllib.parse.urlsplit(u)
        except ValueError:
            continue
        if p.path in ("", "/") and not p.query and e.get("sha256"):
            roots[p.hostname] = e["sha256"]
    for u, e in results.items():
        p = split.get(u)
        e["source"] = sorted(sources[u])
        if u in found_on:
            e["found_on"] = sorted(found_on[u])[:5]
        if p and e.get("kind") == "html" and (p.path not in ("", "/") or p.query) and e.get("sha256") == roots.get(p.hostname):
            e["spa"] = True                       # a single-page app answers every path with its shell

    entries = sorted(results.values(), key=lambda e: (not answering(e), e.get("cls", ""), e["url"]))
    ce = results.get(control)
    rep = {"generated_at": now.isoformat(timespec="seconds"), "generated_he": now.strftime("%d.%m %H:%M"), "mode": mode,
           "runner": {"where": "self-hosted" if os.environ.get("RUNNER_ENVIRONMENT") == "self-hosted" else
                      "github-hosted" if os.environ.get("GITHUB_ACTIONS") else "local",
                      "name": os.environ.get("RUNNER_NAME"), "os": platform.platform(terse=True),
                      "test_rewrite": a.rewrite or None},
           "control": (f"{ce['status']} ({ce['cls']}, {ce.get('bytes')} bytes)" if ce and answering(ce) else
                       f"FAILED ({(ce or {}).get('status') or (ce or {}).get('error', 'not probed')}): " +
                       ("other CEC hosts did answer" if any(answering(e) and "bechirot.gov.il" in e["url"] for e in entries)
                        else "this runner may not reach the CEC at all")),
           "counts": {"probed": len(entries), "answered": sum(map(answering, entries)),
                      "by_class": dict(collections.Counter(e.get("cls") for e in entries))},
           "verdicts": verdicts(entries, cfg, now, election_day, control)}
    sugg = {v["key"]: v["switch"] for v in rep["verdicts"] if v.get("switch") and not v["key"].startswith("national")}
    aliases = {k: x for v in rep["verdicts"] if v["key"] in ("results_url",) or (v["key"] == "station_turnout_url" and ref()["station_aliases"])
               for k, x in v["aliases"].items()}
    ign = sorted({c for v in rep["verdicts"] if v["key"] == "results_url" and (v["switch"] or v["current"])
                  for c in (results.get(v["switch"] or v["current"]) or {}).get("reader", {}).get("ignore_columns", []) or []})
    if aliases:
        sugg["column_aliases"] = {**(cfg.get("column_aliases") or {}), **aliases}
    if ign:
        sugg["ignore_columns"] = sorted(set(cfg.get("ignore_columns") or []) | set(ign))
    rep["suggested_config"] = sugg or None
    rep["diff"] = compare(prev, results)
    rep["hosts"] = host_table(entries, net.rewrite, a.only_rewritten)
    rep["harvest"] = log
    stamp = now.strftime("%Y%m%d-%H%M")
    os.makedirs(a.out, exist_ok=True)
    stored, rep["files_index"] = store_files(results, kept, prev, now, now >= dt.datetime.combine(election_day, dt.time(22, 0), IL),
                                             a.out, stamp, a.store_max_bytes)
    rep["counts"]["stored"] = len(stored)
    rep["urls"] = entries

    pj, pm = os.path.join(a.out, "report.json"), os.path.join(a.out, "report.md")
    with open(pj, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1, default=str)
    with open(pm, "w", encoding="utf-8") as f:
        f.write(markdown(rep))
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(markdown(rep, short=True))
    d = rep["diff"] or {"new": [], "changed": [], "gone": []}
    line = {"mode": mode, "probed": rep["counts"]["probed"], "answered": rep["counts"]["answered"],
            "new": len(d["new"]), "changed": len(d["changed"]), "gone": len(d["gone"]), "stored": sorted(stored),
            "verdicts": {v["key"]: v["state"] for v in rep["verdicts"]}, "report": pm}
    if a.push:
        try:
            line["pushed"] = push_report({f"discover-{stamp}.json": pj, f"discover-{stamp}.md": pm, "latest.json": pj,
                                          "latest.md": pm, **stored}, a.branch, a.remote,
                                         f"discover {now.strftime('%d.%m %H:%M')} IL ({mode}): {len(d['new'])} new, "
                                         f"{len(d['changed'])} changed, {len(d['gone'])} gone")
        except Exception as exc:
            print(json.dumps(line, ensure_ascii=False))
            print(f"could not push the report: {exc}", file=sys.stderr)
            return 3
    print(json.dumps(line, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
