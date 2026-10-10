#!/usr/bin/env python3
"""Find where the CEC publishes the 2026 files, what each one holds, and which live_config.json key
it fits.

GitHub's runners reach the CEC hosts and the build container does not, so this runs from
.github/workflows/discover.yml (daily 15–26.10, every 20 minutes on 27.10, hourly 28–29.10) and
reports to the ops-reports branch. It runs the same way from a laptop or a self-hosted runner:

    python3 pipeline/discover.py --out disc                  # disc/report.json + disc/report.md
    python3 pipeline/discover.py --out disc --push           # and reports/ on the ops-reports branch
    python3 pipeline/discover.py --previous old.json         # new / changed / gone against an older report

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
--push could not deliver the report (3).
"""
import argparse
import collections
import concurrent.futures as cf
import csv
import datetime as dt
import email.utils
import hashlib
import html
import io
import json
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
          "invalid": "פסולים", "valid": "כשרים"}
# names each reader takes without an alias: read_expb (results) and live_fetch.station_turnout
RESULTS_OK = {"code": {"סמל ישוב", *[k for k, v in HEADER_ALIASES.items() if v == "סמל ישוב"]},
              "name": {"שם ישוב", *[k for k, v in HEADER_ALIASES.items() if v == "שם ישוב"]},
              "station": {"קלפי", "מספר קלפי"}, "eligible": {"בזב", *[k for k, v in HEADER_ALIASES.items() if v == "בזב"]},
              "voters": {"מצביעים"}, "invalid": {"פסולים"}, "valid": {"כשרים"}}
STATION_OK = {"code": {"סמל ישוב", "סמל יישוב"}, "station": {"קלפי", "מספר קלפי"}, "voters": {"מצביעים", "הצביעו"},
              "eligible": {"בזב", "בעלי זכות בחירה"}}
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
    try:          # does live_fetch.station_turnout apply live_config column_aliases? (not at 516627d)
        src = open(os.path.join(ROOT, "pipeline", "live_fetch.py"), encoding="utf-8").read()
        body = src.split("def station_turnout", 1)[1].split("\ndef ", 1)[0]
        station_aliases = "column_aliases" in body
    except Exception:
        station_aliases = False
    _REF.update(l26=l26, l22=l22, st22=st22, st22n={(c, k.split(".")[0]) for c, k in st22}, arab=arab,
                station_aliases=station_aliases)
    return _REF


# ------------------------------------------------------------------ network
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
        target, host = self.target(url), urllib.parse.urlsplit(url).hostname or ""
        if target is None:
            return {"status": 0, "error": "skipped: host not rewritten (test mode)"}
        if self.fails[host] >= 3:
            return {"status": 0, "error": "skipped: the host did not answer 3 times in this run"}
        with self.lock:                             # at most one request start per host every `delay` seconds
            start = max(time.time(), self.slot.get(host, 0.0))
            self.slot[host] = start + self.delay
        time.sleep(max(0.0, start - time.time()))
        req = urllib.request.Request(target, headers={"User-Agent": UA, "Accept": "*/*", "Cache-Control": "no-cache",
                                                      "Accept-Language": "he-IL,he;q=0.9,en;q=0.5"})
        t0 = time.time()
        try:
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
    try:
        return body.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return body.decode("cp1255", "replace"), "cp1255"


def sniff(body, ctype, url):
    h = body.lstrip(b"\xef\xbb\xbf \t\r\n")[:64]
    ctype, path = (ctype or "").lower(), urllib.parse.urlsplit(url).path.lower()
    if h.startswith(b"PK\x03\x04"):
        return "zip"
    if h.startswith(b"%PDF"):
        return "pdf"
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
    return {"format": "json", "header": header, "rows": [[str(d.get(k, "")) for k in header] for d in best if isinstance(d, dict)]}


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


def num(x):
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except ValueError:
        return None


# ------------------------------------------------------------------ classifying a table
def describe_table(e, tab, body):
    header, rows = tab["header"], tab["rows"]
    roles, notes = {}, e.setdefault("notes", [])
    for h in header:
        r = role_of(h)
        if r and r not in roles:
            roles[r] = h
    for r in ("voters", "percent"):                 # by-hour columns only: the last one stands for the role
        hv = [h for h in header if role_of(h) == r + "_hour"]
        if r not in roles and hv:
            roles[r] = hv[-1]
            notes.append(f"{r} by hour {hv}: the last column is used; check it is the latest release")
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
        if "voters" not in roles and "percent" in roles:
            notes.append("turnout % but no voters column: the feed needs voters (a code change: voters = % × eligible)")
        if "eligible" not in roles:
            notes.append("no eligible-voters column: the feed computes pace against 2022, not turnout %")
        e["aliases"], e["missing"] = aliases_for(header, roles, STATION_OK, optional=("eligible",))
        e["fits"] = "station_turnout_url"
        if e["aliases"] and not ref()["station_aliases"]:
            notes.append("live_fetch.station_turnout does not apply column_aliases yet: rename in code, or add alias support")
        ok = not e["missing"] and (not e["aliases"] or ref()["station_aliases"]) and tab["format"] == "csv"
        e["reader"] = {"ok": ok, "reader": "station_turnout (column names only)"}
        if tab["format"] != "csv":
            notes.append(f"{tab['format']}: the feed reads CSV only (live_fetch.fetch refuses JSON; xlsx needs a converter)")
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
def analyze(url, r):
    e = {"url": url, "status": r.get("status", 0)}
    if r.get("error"):
        e.update(cls="error", error=r["error"])
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
    if kind in ("zip", "pdf"):
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
    return e, (text if kind in ("html", "js", "xml", "json", "text") else None)


# ------------------------------------------------------------------ harvesting links from pages and scripts
URL_ABS = re.compile(r"""https?://[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s"'<>()\\`{}|^]*)?""")
ATTR = re.compile(r"""(?:href|src|data-src|data-url|action|content)\s*=\s*["']([^"'#<>]+)["']""", re.I)
QUOTED = re.compile(r"""["'`]((?:\.{0,2}/)?[A-Za-z0-9_\-./%]*(?:\.(?:csv|json|xlsx?|zip|pdf|txt|xml)|/files/[^"'`\s]*|/api/[^"'`\s]*|/data/[^"'`\s]*|files/[^"'`\s]+)(?:\?[^"'`\s]*)?)["'`]""", re.I)
SCRIPT = re.compile(r"""["'`]((?:\.{0,2}/|https?://)?[A-Za-z0-9_\-./%:]+\.m?js)(?:\?[^"'`\s]*)?["'`]""")
FRAG = re.compile(r"""["'`]([^"'`\n]{0,100}(?:files/|\.csv|\.xlsx|/api/|turnout|kalpi|ballot|percent)[^"'`\n]{0,100})["'`]""", re.I)
ROBOTS = re.compile(r"(?im)^\s*(?:dis)?allow:\s*(\S+)")
S3KEY = re.compile(r"<Key>([^<]+)</Key>")
ASSET = re.compile(r"\.(?:png|jpe?g|gif|svg|webp|ico|css|woff2?|ttf|eot|otf|mp4|webm|mp3|map)(?:[?#]|$)", re.I)
DATA = re.compile(r"\.(?:csv|json|xlsx?|zip|pdf|txt|xml)(?:[?#]|$)|/files/|/api/|/data/", re.I)
# not "election"/"בחירות": every page of the CEC sites has it, and the crawl would follow all of them
INTEREST = re.compile(r"turnout|percent|hatzba|achuz|ahuz|kalpi|ballot|result|voting|envelop|maatafot|"
                      r"הצבעה|קלפי|תוצאות|מעטפות", re.I)


def allowed(url, allow):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in allow)


def resolve(base, m):
    m = html.unescape(m.strip()).replace("\\/", "/")
    if not m or m.startswith(("javascript:", "mailto:", "tel:", "data:", "#", "${")) or "${" in m or "{{" in m:
        return None
    u = urllib.parse.urljoin(base, m).split("#")[0]
    return u if u.startswith(("http://", "https://")) else None


def harvest(text, page, doc, kind):
    """Links, scripts and unresolved fragments in a page or script. `doc` is the page a script was
    loaded by: relative fetches in a bundle resolve against the document, not the script."""
    links, scripts, frags = set(), set(), []
    raw = set(URL_ABS.findall(text)) | set(QUOTED.findall(text))
    if kind == "html":
        raw |= set(ATTR.findall(text))
    if kind == "text":
        raw |= set(ROBOTS.findall(text))
    if kind == "xml":
        raw |= {"/" + k.lstrip("/") for k in S3KEY.findall(text)}
    for m in raw:
        u = resolve(doc if kind == "js" else page, m)
        if u and kind == "js" and re.search(r"(?:^|/)\.\w+$|[_-]$", m):   # "/files/turnout_" + h + ".csv": pieces
            if len(frags) < 30 and m not in frags:
                frags.append(m)
            continue
        if not u or ASSET.search(u):
            continue
        (scripts if re.search(r"\.m?js(?:\?|$)", u) else links).add(u)
    if kind in ("html", "js"):
        scripts |= {u for u in (resolve(doc if kind == "js" else page, m) for m in SCRIPT.findall(text)) if u}
        for m in FRAG.findall(text):
            if (("${" in m or "+" in m or not resolve(page, m)) and len(frags) < 30 and m not in frags
                    and not ASSET.search(m)):
                frags.append(m)
    return links, scripts, frags


def crawl(net, seeds, allow, pool, results, sources, max_pages=80):
    """Seeds, then the scripts and the interesting pages they link to (two levels). Returns the data-like
    links found and, per page, what was harvested."""
    level, seen, found_on, log, js_per_host = [(u, u) for u in seeds], set(), collections.defaultdict(set), {}, collections.Counter()
    for depth in range(3):
        todo = [(u, d) for u, d in dict(level).items() if u not in seen][:max_pages]
        seen |= {u for u, _ in todo}
        nxt = []
        for (u, doc), (e, text) in zip(todo, pool.map(lambda ud: analyze(ud[0], net.get(ud[0])), todo)):
            results[u] = e
            sources[u].add("seed" if depth == 0 and u in seeds else "harvested")
            if text is None:
                continue
            links, scripts, frags = harvest(text, u, doc, e.get("kind"))
            links = {x for x in links if allowed(x, allow)}
            data = sorted(x for x in links if DATA.search(x) or INTEREST.search(urllib.parse.unquote(x)))
            log[u] = {"links": len(links), "scripts": len(scripts), "data_links": data[:60], "fragments": frags}
            for x in data:
                found_on[x].add(u)
            if depth < 2:
                for s in sorted(scripts):
                    h = urllib.parse.urlsplit(s).hostname
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


def verdicts(entries, cfg, now, election_day):
    closed = now >= dt.datetime.combine(election_day, dt.time(22, 0), IL)
    by_url, out = {e["url"]: e for e in entries}, []
    for key, cls in (("results_url", "results-ballot"), ("results_url_localities", "results-locality"),
                     ("station_turnout_url", "turnout-station")):
        cur = cfg.get(key)
        ce = by_url.get(cur) if cur else None
        cands = sorted((e for e in entries if e.get("cls") == cls and answering(e) and not e.get("envelopes_only")),
                       key=score, reverse=True)
        best = cands[0] if cands else None
        test = lambda e: e and ((e.get("letters") or {}).get("verdict", "").startswith("2022")  # noqa: E731
                                or (cls.startswith("results") and not closed and (e.get("table") or {}).get("counted_rows")))
        if ce and ce.get("cls") == cls:
            state = "test file" if test(ce) else "ok" if (ce.get("reader") or {}).get("ok") is not False else "reader fails"
        elif ce:
            state = f"answers as {ce.get('cls')} ({ce.get('status') or ce.get('error', '')})"
        else:
            state = "not set" if not cur else "not probed"
        switch = best if best and best["url"] != cur and (not ce or ce.get("cls") != cls or score(best) > score(ce)) else None
        out.append({"key": key, "current": cur, "state": state, "best": best and best["url"],
                    "switch": switch and switch["url"], "aliases": (switch or ce or {}).get("aliases") or {},
                    "candidates": [c["url"] for c in cands[:5]]})
    nat = [e for e in entries if e.get("cls") == "turnout-national" and answering(e)]
    out.append({"key": "national hourly (live_input/turnout.json)", "current": None,
                "state": f"{len(nat)} page(s) with hourly figures" if nat else "none found",
                "best": nat[0]["url"] if nat else None, "switch": None, "aliases": {},
                "candidates": [f"{e['url']} {e.get('hourly')}" for e in nat[:5]]})
    return out


FIELDS = ("status", "cls", "sha256", "bytes", "last_modified", "etag")


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
    out = ["| " + " | ".join(c for c, _ in cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(cell(f(r)) for _, f in cols) + " |" for r in rows]
    return "\n".join(out)


def brief(e):
    t, bits = e.get("table") or {}, []
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
    bits += e.get("notes", [])
    return "; ".join(bits)


def markdown(rep, short=False):
    L = [f"## CEC file discovery, {rep['generated_he']} Israel time ({rep['mode']}, {rep['runner']['where']})", "",
         f"{rep['counts']['probed']} URLs probed, {rep['counts']['answered']} answered. Control (2022 file): "
         f"{rep['control']}. How to read this: docs/FILE_DISCOVERY.md.", "",
         table(rep["verdicts"], [("live_config key", lambda v: v["key"]), ("now", lambda v: v["current"] or "—"),
                                 ("state", lambda v: v["state"]), ("switch to", lambda v: v["switch"] or "—"),
                                 ("column_aliases", lambda v: json.dumps(v["aliases"], ensure_ascii=False) if v["aliases"] else "")])]
    if rep.get("suggested_config"):
        L += ["", "Suggested live_config.json change (confirm first: header, rows, 2026 letters, time):", "", "```json",
              json.dumps(rep["suggested_config"], ensure_ascii=False, indent=1), "```"]
    d = rep.get("diff")
    if d:
        L += ["", f"### Since {d['previous']}: {len(d['new'])} new, {len(d['changed'])} changed, {len(d['gone'])} gone"]
        rows = ([("new", x["url"], x["cls"], f"was {x['was']}") for x in d["new"]] +
                [("changed", x["url"], x["cls"], ", ".join(f"{k}: {a} → {b}" for k, (a, b) in x["diff"].items())) for x in d["changed"]] +
                [("gone", x["url"], x["cls"], f"now {x['now']}") for x in d["gone"]])
        if rows:
            L += ["", table(rows[:15 if short else 200], [("", lambda r: r[0]), ("URL", lambda r: r[1]), ("class", lambda r: r[2]),
                                                       ("what", lambda r: r[3])])]
    data = [e for e in rep["urls"] if answering(e) and e["cls"] not in ("html", "script")]
    if data:
        L += ["", "### Files and pages with data", "",
              table(data[:12 if short else 300], [("class", lambda e: e["cls"]), ("URL", lambda e: e["url"]),
                                                  ("HTTP", lambda e: e["status"]), ("bytes", lambda e: e.get("bytes")),
                                                  ("last-modified", lambda e: e.get("last_modified")), ("details", brief)])]
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
            L += [f"  - fragment: `{cell(x, 120)}`" for x in h["fragments"][:10]]
    errs = [e for e in rep["urls"] if not answering(e)]
    L += ["", f"<details><summary>{len(errs)} URLs that did not answer with data</summary>", "",
          table(errs, [("URL", lambda e: e["url"]), ("HTTP", lambda e: e["status"]),
                       ("why", lambda e: e.get("error") or e.get("hint") or ("same page as the site root" if e.get("spa") else ""))]),
          "", "</details>"]
    return "\n".join(L) + "\n"


def host_table(entries, rewrite, only_rewritten):
    hosts = {}
    for e in entries:
        h = urllib.parse.urlsplit(e["url"]).hostname or ""
        d = hosts.setdefault(h, {"probed": 0, "answered": 0, "status": collections.Counter(), "hints": collections.Counter()})
        d["probed"] += 1
        d["answered"] += answering(e)
        d["status"][str(e.get("status") or "no answer")] += 1
        if e.get("hint") or e.get("error"):
            d["hints"][e.get("hint") or re.sub(r":.*", "", e.get("error", ""))] += 1
    for h, d in hosts.items():
        real = next((urllib.parse.urlsplit(dst).hostname for src, dst in rewrite if urllib.parse.urlsplit(src).hostname == h),
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
            else:
                git("checkout", "-q", "--orphan", tmp, cwd=wt)
                git("rm", "-rfq", "--ignore-unmatch", ".", cwd=wt)
            git("clean", "-fdxq", cwd=wt)
            os.makedirs(os.path.join(wt, "reports"), exist_ok=True)
            for name, src in files.items():
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
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc).astimezone(IL)
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

    seeds = list(dict.fromkeys(list(over.get("seeds", SEEDS)) + a.url))
    allow = tuple(over.get("allow_hosts", ALLOW))
    control = over.get("control", CONTROL)
    sources = collections.defaultdict(set)
    for u in a.url:
        sources[u].add("operator")
    probe = []
    for u, src in ([(u, "known") for u in over.get("probe", KNOWN) + [control]] +
                   [(cfg.get(k), "config") for k in ("results_url", "results_url_localities", "station_turnout_url")] +
                   [(u, "enumerated") for u in (enumerated() if over.get("enumerate", mode == "full") else [])] +
                   [(e["url"], "previous") for e in (prev or {}).get("urls", [])
                    if answering(e) and (e["cls"] not in ("html", "script") or "seed" in e.get("source", []))]):
        if u:
            sources[u].add(src)
            probe.append(u)

    net, results = Net(a), {}
    with cf.ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        found_on, log = crawl(net, seeds, allow, pool, results, sources)
        linked = [u for u in sorted(found_on) if DATA.search(u)][:400] + [u for u in sorted(found_on) if not DATA.search(u)][:100]
        rest = list(dict.fromkeys(u for u in probe + linked if u not in results))
        for u, (e, _) in zip(rest, pool.map(lambda u: analyze(u, net.get(u)), rest)):
            results[u] = e
    roots = {}
    for u, e in results.items():
        p = urllib.parse.urlsplit(u)
        if p.path in ("", "/") and not p.query and e.get("sha256"):
            roots[p.hostname] = e["sha256"]
    for u, e in results.items():
        p = urllib.parse.urlsplit(u)
        e["source"] = sorted(sources[u])
        if u in found_on:
            e["found_on"] = sorted(found_on[u])[:5]
        if e.get("kind") == "html" and (p.path not in ("", "/") or p.query) and e.get("sha256") == roots.get(p.hostname):
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
           "verdicts": verdicts(entries, cfg, now, election_day)}
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
    rep["urls"] = entries

    os.makedirs(a.out, exist_ok=True)
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
            "new": len(d["new"]), "changed": len(d["changed"]), "gone": len(d["gone"]),
            "verdicts": {v["key"]: v["state"] for v in rep["verdicts"]}, "report": pm}
    if a.push:
        stamp = now.strftime("%Y%m%d-%H%M")
        try:
            line["pushed"] = push_report({f"discover-{stamp}.json": pj, f"discover-{stamp}.md": pm, "latest.json": pj,
                                          "latest.md": pm}, a.branch, a.remote,
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
