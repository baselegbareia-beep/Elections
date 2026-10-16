"""Runner fetcher: the official CBS files behind pipeline/build_cbs.py (the build container cannot reach
cbs.gov.il or data.gov.il; GitHub's runners can).

    python3 pipeline/fetchers/cbs.py --out <dir> [--deadline SECONDS]

Standard library only. Writes the raw files under <dir>/files/, the catalogue listings under
<dir>/listings/, the census dashboards under <dir>/census/, and <dir>/summary.json + <dir>/summary.md
(every URL with its HTTP status, size, SHA-256, Last-Modified and whether the bytes are what was asked
for). A bad URL is recorded and skipped; the exit code is 0 unless the script itself crashed.

What it gets:
  1. The CBS locality files (קובץ היישובים): the listing of www.cbs.gov.il/he/publications/doclib/2019/
     ishuvim/ (SharePoint REST), every bycodeYYYY.xlsx from 2022 on and the documentation (intro.pdf,
     the definitions of דת יישוב and צורת יישוב); the fixed URLs if the listing is refused.
  2. data.gov.il: the CKAN records of the locality-file and 2022-census datasets, the 2022 census CSV
     ("selected data by localities and statistical areas"), and the newest bycode resource there.
     Plain data.gov.il serves the files (aws-e.data.gov.il asks for a login, e.data.gov.il returns HTML),
     so resource hosts are rewritten to it.
  3. The CBS geographic catalogue (/he/publications/doclib/2022/קטלוג/1. יישובים וחלוקות גאוגרפיות) and
     its subfolders (one level): every file whose name looks like a ballot-to-statistical-area crosswalk
     (kalpi / ballot / קלפי: kalpi_<month><year>_stat2011.xlsx of 2019-2022 and any newer one), the
     stable-ballot workbook, a 2011<->2022 statistical-area key (מפתח, stat2011 / stat2022), with their
     ReadMe (GEO_TAKE, at most GEO_MAX files and GEO_TOTAL bytes; the names in GEO_WANTED get fixed ASCII
     names), and the newest statistical-area demography layer (.gdb.zip) that fits the size cap. Every
     listed file not taken is named in summary.md with the reason. The guessed GEO_WANTED paths when the
     listing is refused.
  4. census.cbs.gov.il: the religion dashboard (shares to 0.1%) of the statistical areas of the mixed
     cities and Safed, sequentially at one request a second (the host blocks fast or parallel clients).
     The cities in priority order (CENSUS_CITIES: Jerusalem first), in two passes: first, in every city, the
     locality itself and the 2022 areas that matter (census_priority: those over a 2011 area with an Arab
     share above 5% in pipeline/reference/cbs_mixed_areas.json, or holding a station where the vote rule and
     the area rule disagree in cbs_validation.json), then the rest of each city, as long as the time lasts.

Time (pipeline/fetchers/__init__.py): no request starts after --deadline (DEADLINE, 20 minutes from the start;
fetch.yml stops the run at 25), and a body still coming is cut GRACE seconds after it. summary.json and
summary.md are written at the start, after each part and after each city of part 4 (each write whole, through
a temporary file), so a run stopped anywhere leaves a summary of what it had.
"""
import argparse
import datetime
import hashlib
import html
import io
import json
import os
import platform
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REFERENCE = os.path.join(ROOT, "pipeline", "reference")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
CBS = "https://www.cbs.gov.il"
ISHUVIM = "/he/publications/doclib/2019/ishuvim"
GEO_CATALOG = "/he/publications/doclib/2022/קטלוג/1. יישובים וחלוקות גאוגרפיות"
SP_LIST = CBS + "/he/publications/_api/web/GetFolderByServerRelativeUrl('{folder}')/{what}"
SP_SELECT = {"Files": "?$select=Name,ServerRelativeUrl,Length,TimeLastModified&$top=500",
             "Folders": "?$select=Name,ServerRelativeUrl,ItemCount&$top=100"}
FIXED_ISHUVIM = ["bycode2025.xlsx", "bycode2024.xlsx", "bycode2023.xlsx", "bycode2022.xlsx", "intro.pdf"]
DATAGOV = "https://data.gov.il"
CKAN_DATASETS = {"census2022": "3bd97fde-6cc3-456d-ab63-1caad16b2b6a",
                 "localities": "d9b1e04c-426f-4e32-ba40-a1ad9d8748a7"}
CENSUS_CSV = (DATAGOV + "/dataset/3bd97fde-6cc3-456d-ab63-1caad16b2b6a/resource/9a9e085f-3bc8-41df-b15f-be0daaf99e30/"
              "download/selected-data-by-localities-and-statistical-areas-2022-census.csv")
# names in the geographic catalogue -> the name written under files/ (ASCII); matched without case, spaces, _ or -
GEO_WANTED = {
    "kalpi_April2019_stat2011.xlsx": "k21_kalpi_to_stat2011.xlsx",
    "kalpi_September2019_stat2011.xlsx": "k22_kalpi_to_stat2011.xlsx",
    "kalpi_March2020_stat2011.xlsx": "k23_kalpi_to_stat2011.xlsx",
    "kalpi_March2021_stat2011.xlsx": "k24_kalpi_to_stat2011.xlsx",
    "kalpi_November2022_stat2011.xlsx": "k25_kalpi_to_stat2011.xlsx",
    "ReadMe_kalpi_November2022_stat2011.pdf": "k25_kalpi_to_stat2011_readme.pdf",
    "Stable_kalp_November2022.xlsx": "k25_stable_kalpi.xlsx",
    "ReadMe_Stable_kalp_November2022.pdf": "k25_stable_kalpi_readme.pdf",
    "מפתח מעבר אס 2011 לאס 2022.xlsx": "stat2011_to_stat2022.xlsx",
    "מפתח מעבר אס 2022 לאס 2011.xlsx": "stat2022_to_stat2011.xlsx",
}
# the catalogue's files taken by name pattern, not by the exact names guessed above: a ballot crosswalk (kalpi,
# ballot, קלפי), a 2011 / 2022 statistical-area key (stat2011, stat2022, מפתח, אס 2011), and their ReadMe
GEO_TAKE = re.compile(r"kalp|ballot|קלפי|stat_?20(?:11|22)|מפתח|אס\s*20(?:11|22)", re.I)
GEO_NEWER = re.compile(r"(kalpi|stable_kalp).*(2023|2024|2025|2026|stat2022)|stat2022.*kalpi", re.I)
GEO_TYPES = (".xlsx", ".xls", ".csv", ".pdf", ".zip")
GEO_MAX = 40                        # files taken from the listing at most: GEO_WANTED's first, then newer, then newest
GEO_TOTAL = 150 * 1024 * 1024       # and at most this many bytes of them (the outputs are pushed to git)
GEO_SUBFOLDERS = 8                  # the catalogue's subfolders listed too, at most
GDB = re.compile(r"statisticalareas_demography(\d{4})\.gdb\.zip$", re.I)
SIZE_CAP = 45 * 1024 * 1024        # bigger files are listed, not downloaded (the outputs are pushed to git)
# census.cbs.gov.il (an htmx front end over Looker): the search partial maps names to opaque area ids,
# get-csv returns a zip of the dashboard's CSVs. The religion dashboard id as used by
# https://github.com/circularsquare/maps/blob/HEAD/religiondots/sources/il.py
CENSUS_SEARCH = "https://census.cbs.gov.il/he/partials/search/area?search="
CENSUS_CSV_API = "https://census.cbs.gov.il/en/api/get-csv?dashboardId={dash}&ID={aid}"
DASH_RELIGION = "gIRhDCmNLsR3sI0G53n89n"
# in priority order: Jerusalem (the most areas, the most important mixed city) first; the time may run out later on
CENSUS_CITIES = {3000: "ירושלים", 4000: "חיפה", 5000: "תל אביב -יפו", 7600: "עכו", 8500: "רמלה", 7000: "לוד",
                 1061: "נוף הגליל", 1063: "מעלות-תרשיחא", 8000: "צפת"}
SHELL_BYTES = (2803, 2804)          # the site's SPA shell / error page, never an answer
POLITE = 1.0
CENSUS_MAX = 800                    # at most this many requests for part 4
SEARCH_FULL = 90                    # a search answer this long may be cut (the search gives 100 results at most)
SEARCH_MAX = 60                     # search requests a city, at most
DEADLINE = 20 * 60                  # seconds from the start (fetchers/__init__.py: fetch.yml stops it at 25 minutes)
GRACE = 60                          # a body still coming at the deadline is cut this much later


class Stop(Exception):
    """The run's budget is spent (the deadline, part 4's request budget, five failures in a row): nothing more
    is asked."""


class TooBig(IOError):
    """A body over the size cap: not asked again."""


class Fetcher:
    def __init__(self, out, deadline=DEADLINE):
        self.out, self.deadline = out, deadline
        self.stop_at = time.monotonic() + deadline
        self.items, self.not_taken = [], []
        for d in ("files", "listings", "census"):
            os.makedirs(os.path.join(out, d), exist_ok=True)

    def late(self):
        return time.monotonic() >= self.stop_at

    def get(self, url, headers=None, timeout=120, tries=3):
        """(status, bytes, headers) or raises after `tries` attempts; HTTP errors return their status. Nothing is
        asked after the deadline (Stop), and a body still coming is cut GRACE seconds after it."""
        last = None
        for attempt in range(tries):
            if self.late():
                raise last or Stop("not asked: past the deadline (--deadline)")
            cut = self.stop_at + GRACE
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
                with urllib.request.urlopen(req, timeout=max(1.0, min(timeout, cut - time.monotonic()))) as r:
                    return r.status, read_until(r, SIZE_CAP, cut), dict(r.headers)
            except urllib.error.HTTPError as err:
                if err.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                return err.code, err.read() if hasattr(err, "read") else b"", dict(err.headers or {})
            except TooBig:
                raise
            except Exception as err:  # noqa: BLE001 - network errors of every kind are recorded
                last = err
                time.sleep(3 * (attempt + 1))
        raise last

    def save(self, name, url, sub="files", headers=None, magic=None, min_bytes=1, note=None, text_check=None):
        """Download url to <out>/<sub>/<name>; record the outcome; never raise."""
        rec = {"name": name, "url": url, "ok": False, "path": None, "note": note}
        try:
            status, data, hd = self.get(url, headers=headers)
            rec.update(status=status, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                       content_type=hd.get("Content-Type"), last_modified=hd.get("Last-Modified"))
            problem = None
            if status != 200:
                problem = f"HTTP {status}"
            elif len(data) < min_bytes:
                problem = f"{len(data)} bytes, expected at least {min_bytes}"
            elif magic and not data.startswith(magic):
                problem = f"starts with {data[:12]!r}, not {magic!r} (a login page or a fake 200?)"
            elif text_check and not text_check(data):
                problem = "content check failed"
            if problem:
                rec["error"] = problem
                if 0 < len(data) <= 200_000:     # keep small rejected answers for inspection
                    p = os.path.join(self.out, sub, name + ".rejected")
                    open(p, "wb").write(data)
                    rec["rejected_copy"] = os.path.relpath(p, self.out)
            else:
                p = os.path.join(self.out, sub, name)
                open(p, "wb").write(data)
                rec.update(ok=True, path=os.path.relpath(p, self.out))
        except Exception as err:  # noqa: BLE001
            rec["error"] = f"{err.__class__.__name__}: {err}"
        self.items.append(rec)
        print(f"  {'ok ' if rec['ok'] else 'ERR'} {name}: {rec.get('error') or rec.get('bytes')}", flush=True)
        return rec

    def listing(self, name, folder, what="Files"):
        """SharePoint REST listing of a CBS document folder -> [{Name, ServerRelativeUrl, Length, ...}]
        (what="Folders": its subfolders)."""
        url = SP_LIST.format(folder=urllib.parse.quote(folder, safe="/"), what=what) + SP_SELECT[what]
        rec = self.save(name, url, sub="listings", headers={"Accept": "application/json;odata=nometadata"},
                        text_check=lambda b: b.lstrip()[:1] in (b"{", b"["))
        if not rec["ok"]:
            return None
        try:
            doc = json.loads(open(os.path.join(self.out, rec["path"]), "rb").read().decode("utf-8"))
            return doc.get("value", doc.get("d", {}).get("results", []))
        except Exception as err:  # noqa: BLE001
            rec.update(ok=False, error=f"listing did not parse: {err}")
            return None


def read_until(r, limit, cut):
    """r's body, at most limit bytes (more is an error), read in pieces until the monotonic time `cut`: a slow
    body cannot hold the run past the deadline's grace."""
    chunks, n = [], 0
    while True:
        if time.monotonic() > cut:
            raise TimeoutError(f"cut at the deadline (--deadline) after {n} bytes")
        b = r.read(1 << 16)
        if not b:
            return b"".join(chunks)
        chunks.append(b)
        n += len(b)
        if n > limit:
            raise TooBig(f"over the size cap ({limit // (1024 * 1024)} MB)")


def write_atomic(path, text):
    """text to path through a temporary file beside it: a reader (or a kill) never meets half a file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def file_url(server_relative):
    return CBS + urllib.parse.quote(server_relative, safe="/")


def ascii_name(name):
    """name as an ASCII file name; one that loses letters on the way (a Hebrew name) gets 8 hex digits of its
    hash, so that two of them never meet."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    if base and base not in (".", "..") and re.fullmatch(r"[A-Za-z0-9._ -]+", name):
        return base
    ext = os.path.splitext(name)[1].lower()
    ext = ext if re.fullmatch(r"\.[a-z0-9]{1,5}", ext) else ""
    stem = re.sub(r"[^A-Za-z0-9-]+", "_", name[:len(name) - len(ext)]).strip("_")
    h = hashlib.sha256(name.encode()).hexdigest()[:8]
    return f"{stem}_{h}{ext}" if stem else h + ext


def geo_key(name):
    return re.sub(r"[\s_-]+", "", name).lower()


GEO_KEYS = {geo_key(k): v for k, v in GEO_WANTED.items()}


def is_csv_census(b):
    head = b[:4000].decode("utf-8-sig", "replace")
    return "LocNameHeb" in head or ("," in head and "<html" not in head.lower())


def part_localities(f):
    print("1. CBS locality files", flush=True)
    files = f.listing("ishuvim.json", ISHUVIM)
    names = []
    if files:
        for x in files:
            n = x.get("Name", "")
            m = re.fullmatch(r"bycode(\d{4})(.*)\.xlsx", n, re.I)
            if (m and int(m.group(1)) >= 2022) or re.fullmatch(r"intro.*\.pdf", n, re.I):
                if int(x.get("Length") or 0) <= SIZE_CAP:
                    names.append((n, file_url(x["ServerRelativeUrl"])))
    if not names:
        names = [(n, f"{CBS}{ISHUVIM}/{n}") for n in FIXED_ISHUVIM]
    for n, url in names:
        magic = b"%PDF" if n.lower().endswith(".pdf") else b"PK\x03\x04"
        f.save(ascii_name(n), url, magic=magic, min_bytes=20_000)


def part_datagov(f):
    print("2. data.gov.il", flush=True)
    for key, ds in CKAN_DATASETS.items():
        rec = f.save(f"ckan_{key}.json", f"{DATAGOV}/api/3/action/package_show?id={ds}", sub="listings",
                     text_check=lambda b: b.lstrip()[:1] == b"{")
        if key != "localities" or not rec["ok"]:
            continue
        try:   # the newest bycode resource of the locality dataset
            pkg = json.loads(open(os.path.join(f.out, rec["path"]), "rb").read().decode("utf-8"))["result"]
            res = [r for r in pkg.get("resources", []) if re.search(r"bycode\d{4}", r.get("url", "") or "", re.I)]
            res.sort(key=lambda r: re.search(r"bycode(\d{4})", r["url"], re.I).group(1), reverse=True)
            for r in res[:2]:
                u = urllib.parse.urlsplit(r["url"])
                url = urllib.parse.urlunsplit(("https", "data.gov.il", u.path, u.query, ""))
                f.save("datagov_" + ascii_name(os.path.basename(u.path)), url, magic=b"PK\x03\x04", min_bytes=20_000,
                       note=f"resource {r.get('id')} modified {r.get('last_modified') or r.get('metadata_modified')}")
        except Exception as err:  # noqa: BLE001
            f.items.append({"name": "datagov_bycode", "url": rec["url"], "ok": False, "error": str(err)})
    f.save("census2022_localities_statareas.csv", CENSUS_CSV, min_bytes=300_000, text_check=is_csv_census)


def part_geo_catalog(f):
    print("3. CBS geographic catalogue", flush=True)
    files = f.listing("geo_catalog.json", GEO_CATALOG)
    if not files:
        for n, out in GEO_WANTED.items():      # the catalogue's own paths, if the listing is refused
            magic = b"%PDF" if n.endswith(".pdf") else b"PK\x03\x04"
            f.save(out, file_url(f"{GEO_CATALOG}/{n}"), magic=magic, min_bytes=5_000)
        return
    # one level of subfolders too (Forms is SharePoint's own)
    subs = [x for x in f.listing("geo_catalog_folders.json", GEO_CATALOG, what="Folders") or []
            if x.get("Name") and x.get("Name") != "Forms" and x.get("ServerRelativeUrl")]
    for i, x in enumerate(subs):
        if i < GEO_SUBFOLDERS:
            files = files + (f.listing(f"geo_catalog_{i + 1}.json", x["ServerRelativeUrl"]) or [])
        else:
            f.not_taken.append({"name": x["Name"] + "/", "why": f"a subfolder after the first {GEO_SUBFOLDERS}: not listed"})
    gdbs, cand = [], []
    for x in files:
        n, size = x.get("Name", ""), int(x.get("Length") or 0)
        if not n or not x.get("ServerRelativeUrl"):
            continue
        m = GDB.search(n)
        if m:
            gdbs.append((int(m.group(1)), n, size, file_url(x["ServerRelativeUrl"]), x.get("TimeLastModified")))
        elif not n.lower().endswith(GEO_TYPES):
            f.not_taken.append({"name": n, "bytes": size, "modified": x.get("TimeLastModified"),
                                "why": "not a table, a PDF or a zip"})
        elif geo_key(n) in GEO_KEYS or GEO_TAKE.search(n):
            cand.append(x)
        else:
            f.not_taken.append({"name": n, "bytes": size, "modified": x.get("TimeLastModified"),
                                "why": "the name is not a crosswalk's or an area key's (GEO_TAKE)"})
    # GEO_WANTED's names first, then the newer crosswalks, then the rest, each newest first
    cand.sort(key=lambda x: str(x.get("TimeLastModified") or ""), reverse=True)
    cand.sort(key=lambda x: 0 if geo_key(x["Name"]) in GEO_KEYS else 1 if GEO_NEWER.search(x["Name"]) else 2)
    taken, total, used = 0, 0, set()
    for x in cand:
        n, size, mod = x["Name"], int(x.get("Length") or 0), x.get("TimeLastModified")
        why = ("over the size cap" if size > SIZE_CAP else f"beyond the first {GEO_MAX} files" if taken >= GEO_MAX
               else f"over the {GEO_TOTAL >> 20} MB taken from the catalogue" if total + size > GEO_TOTAL else None)
        if why:
            f.not_taken.append({"name": n, "bytes": size, "modified": mod, "why": why})
            continue
        out = GEO_KEYS.get(geo_key(n)) or ascii_name(n)
        if out in used:                         # the same name in two folders
            root, ext = os.path.splitext(out)
            out = f"{root}_{hashlib.sha256(x['ServerRelativeUrl'].encode()).hexdigest()[:8]}{ext}"
        used.add(out)
        taken, total = taken + 1, total + size
        rel, low = x["ServerRelativeUrl"], n.lower()
        magic = (b"%PDF" if low.endswith(".pdf") else b"PK\x03\x04" if low.endswith((".xlsx", ".zip"))
                 else b"\xd0\xcf\x11\xe0" if low.endswith(".xls") else None)
        f.save(out, file_url(x["ServerRelativeUrl"]), magic=magic, min_bytes=1_000,
               note=f"catalogue: {rel[len(GEO_CATALOG) + 1:] if rel.startswith(GEO_CATALOG + '/') else rel}, modified {mod}")
    got_gdb = False
    for year, n, size, url, mod in sorted(gdbs, reverse=True):
        if size <= SIZE_CAP and not got_gdb:
            f.save(ascii_name(n), url, magic=b"PK\x03\x04", min_bytes=100_000,
                   note=f"newest statistical-area demography layer under the cap ({year})")
            got_gdb = True
        else:
            f.not_taken.append({"name": n, "bytes": size, "modified": mod,
                                "why": "over the size cap" if size > SIZE_CAP else "an older demography layer"})


def census_priority():
    """({city code: the 2022 statistical areas asked first}, error): the areas over a 2011 area with an Arab share
    above 5% (pipeline/reference/cbs_mixed_areas.json) or holding a station where the vote rule and the area rule
    disagree (cbs_validation.json, mixed_city_stations). ({}, the error) when the files cannot be read."""
    try:
        areas = json.load(open(os.path.join(REFERENCE, "cbs_mixed_areas.json"), encoding="utf-8"))["areas"]
        dis = json.load(open(os.path.join(REFERENCE, "cbs_validation.json"), encoding="utf-8"))["mixed_city_stations"]
        picked = {str(a) for rows in dis["disagreements"].values() for r in rows for a in r.get("areas_2011") or []}
        out = {}
        for key, a in areas.items():
            if key in picked or (a.get("arab_share") or 0) > 0.05:
                units = {int(n) for u in a.get("units_2022") or {} for n in re.findall(r"\d+", u.split("(")[0])}
                out.setdefault(int(a["code"]), set()).update(units)
        return out, None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        return {}, f"{err.__class__.__name__}: {err}"


def part_census_dashboards(f, priority=None, progress=None):
    """Part 4 (see the top): every city's file under census/ and its line in f.items rewritten after each city,
    then progress(state). Returns the state: requests, areas, ok, and why it stopped (None: it did not)."""
    print("4. census.cbs.gov.il religion dashboards", flush=True)
    priority = priority or {}
    state = {"requests": 0, "areas": 0, "ok": 0, "stopped": None, "cities": [str(c) for c in CENSUS_CITIES], "searched": [],
             "priority_units": {str(c): len(priority.get(c, ())) for c in CENSUS_CITIES}}
    fails = 0

    def polite_get(url, headers=None):
        nonlocal fails
        if state["requests"] >= CENSUS_MAX:
            raise Stop(f"the request budget ({CENSUS_MAX})")
        if f.late():
            raise Stop("the deadline (--deadline)")
        time.sleep(POLITE)
        state["requests"] += 1
        try:
            status, data, _ = f.get(url, headers=headers, timeout=60, tries=2)
        except Stop:                       # the deadline came during the pause
            raise Stop("the deadline (--deadline)") from None
        except Exception:
            fails += 1
            raise
        if status != 200 or len(data) in SHELL_BYTES:
            fails += 1
            raise IOError(f"HTTP {status}, {len(data)} bytes")
        fails = 0
        return data

    def query(out, term):
        """One search: its areas into out["found"] (and the locality itself into out["unit"]); the number of
        results, None when it failed."""
        city = out["city"]
        try:
            doc = polite_get(CENSUS_SEARCH + urllib.parse.quote(term), {"HX-Request": "true"}).decode("utf-8", "replace")
        except Stop:
            raise
        except Exception as err:  # noqa: BLE001
            out["errors"].append(f"search {term}: {err}")
            if fails >= 5:
                raise Stop("five failures in a row")
            return None
        items = re.findall(r'data-id="([^"]*)"\s+data-search="([^"]*)"\s+data-type="([^"]*)"', doc)
        for aid, label, typ in items:
            label, typ = html.unescape(label), html.unescape(typ)
            m = re.search(r"אזור סטטיסטי\s*(\d+)", label)
            if m and city.replace(" ", "") in label.replace(" ", ""):
                out["found"][int(m.group(1))] = (aid, label, typ)
            elif label.strip() == city and "unit" not in out:
                out["unit"] = {"id": aid, "label": label, "type": typ}
        return len(items)

    def search(out):
        """The city's areas. The search answers 100 results at most: the plain query, when it comes back that
        long (or with none of the city's areas), is asked again with each first digit, and a digit query that
        comes back that long with one more digit (to three); an area of the priority list still missing is asked
        by its number. At most SEARCH_MAX queries a city."""
        base, want = f"{out['city']} אזור סטטיסטי", priority.get(out["code"], set())
        queue, asked = [""], 0
        while queue and asked < SEARCH_MAX:
            p = queue.pop(0)
            n = query(out, f"{base} {p}" if p else base)
            asked += 1
            if not p and (n is None or not out["found"] or n >= SEARCH_FULL):
                queue += [str(d) for d in range(1, 10)]
            elif p and n is not None and n >= SEARCH_FULL and len(p) < 3:
                queue += [p + str(d) for d in range(10)]
        for num in sorted(want - set(out["found"])):
            if asked >= SEARCH_MAX:
                break
            query(out, f"{base} {num}")
            asked += 1
        out["searches"] = asked

    def dashboard(out, num, aid, label):
        rec = {"area": num, "id": aid, "label": label}
        try:
            blob = polite_get(CENSUS_CSV_API.format(dash=DASH_RELIGION, aid=urllib.parse.quote(aid)))
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                rec["csv"] = {i.filename: z.read(i).decode("utf-8-sig", "replace") for i in z.infolist()
                              if i.file_size < 2_000_000}
            rec["sha256"] = hashlib.sha256(blob).hexdigest()
            state["ok"] += 1
        except Stop:
            raise
        except Exception as err:  # noqa: BLE001
            rec["error"] = f"{err.__class__.__name__}: {err}"
        out["areas"].append(rec)
        state["areas"] += 1
        if "error" in rec and fails >= 5:
            raise Stop("five failures in a row")

    cities, lines = {}, {}

    def save_city(out):
        code = out["code"]
        doc = {k: v for k, v in out.items() if k != "found"}
        doc.update(areas_found=len(out["found"]), priority_units=sorted(priority.get(code, ())))
        path = os.path.join(f.out, "census", f"religion_{code}.json")
        write_atomic(path, json.dumps(doc, ensure_ascii=False))
        with_data = sum(1 for a in out["areas"] if "csv" in a)
        if code not in lines:       # one line in the summary a city, kept up to date
            lines[code] = {"name": f"census/religion_{code}.json", "url": CENSUS_SEARCH,
                           "path": os.path.relpath(path, f.out)}
            f.items.append(lines[code])
        lines[code].update(ok=with_data > 0, areas=len(out["areas"]), areas_with_data=with_data,
                           error="; ".join(out["errors"][:3]) or None)
        print(f"  {out['city']}: {len(out['found'])} areas found, {with_data} fetched", flush=True)

    try:
        for first in (True, False):        # the locality and the priority areas of every city, then the rest
            for code, city in CENSUS_CITIES.items():
                out = cities.setdefault(code, {"code": code, "city": city, "areas": [], "errors": [], "found": {}})
                want = priority.get(code, set())
                try:
                    if first:
                        search(out)
                        state["searched"].append(str(code))
                    unit = [("locality", out["unit"]["id"], out["unit"]["label"])] if first and "unit" in out else []
                    targets = unit + [(num, aid, label) for num, (aid, label, _) in sorted(out["found"].items())
                                      if (num in want) == first]
                    for num, aid, label in targets:
                        dashboard(out, num, aid, label)
                finally:
                    save_city(out)
                    if progress:
                        progress(state)
    except Stop as err:
        state["stopped"] = str(err)
    return state


def write_summary(f, started, census_state, stage="done"):
    """summary.json and summary.md as they stand: at the start, after each part and each city, and at the end
    (stage "done"); each write replaces the last one whole."""
    ok = sum(1 for i in f.items if i.get("ok"))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    summary = {"fetcher": "cbs", "started": started, "written": now, "finished": now if stage == "done" else None,
               "stage": stage, "deadline_s": f.deadline, "past_deadline": f.late(),
               "runner": {"python": platform.python_version(), "host": platform.node()},
               "ok": ok, "failed": len(f.items) - ok, "census_dashboards": census_state, "items": f.items,
               "geo_catalogue_not_taken": f.not_taken}
    write_atomic(os.path.join(f.out, "summary.json"), json.dumps(summary, ensure_ascii=False, indent=1))
    cell = lambda v: str(v if v is not None else "").replace("|", "/")
    lines = [f"# CBS fetch {now}", ""]
    if stage != "done":
        lines += [f"**Partial:** written {stage}; the run had not finished (if this is the last copy, it was stopped "
                  f"there).", ""]
    lines += [f"{ok} ok, {len(f.items) - ok} failed. Deadline {f.deadline:.0f} s from the start"
              f"{' (passed: what was not asked by then is not here)' if f.late() else ''}. Census dashboards: "
              f"{json.dumps(census_state, ensure_ascii=False)}", "",
              "| file | ok | status | bytes | sha256 | last-modified | error / note |", "|---|---|---|---|---|---|---|"]
    for i in f.items:
        lines.append(f"| {cell(i.get('path') or i['name'])} | {'yes' if i.get('ok') else 'no'} | {cell(i.get('status'))} | "
                     f"{cell(i.get('bytes'))} | {cell((i.get('sha256') or '')[:16])} | {cell(i.get('last_modified'))} | "
                     f"{cell(i.get('error') or i.get('note'))} |")
    if f.not_taken:
        lines += ["", f"## Geographic catalogue: listed, not taken ({len(f.not_taken)})", "",
                  "| name | bytes | modified | why |", "|---|---|---|---|"]
        for x in f.not_taken[:400]:
            lines.append(f"| {cell(x['name'])} | {cell(x.get('bytes'))} | {cell(x.get('modified'))} | {cell(x['why'])} |")
    write_atomic(os.path.join(f.out, "summary.md"), "\n".join(lines) + "\n")
    print(f"summary ({stage}): {ok} ok, {len(f.items) - ok} failed -> {f.out}/summary.md", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-census", action="store_true", help="leave out part 4 (census.cbs.gov.il)")
    ap.add_argument("--deadline", type=float, default=DEADLINE,
                    help=f"seconds from the start after which nothing is asked (default {DEADLINE}; fetch.yml stops it at 1500)")
    a = ap.parse_args(argv)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    f = Fetcher(a.out, a.deadline)
    census_state = None
    write_summary(f, started, census_state, "at the start")
    for part in (part_localities, part_datagov, part_geo_catalog):
        try:
            part(f)
        except Exception as err:  # noqa: BLE001 - one part failing leaves the others
            f.items.append({"name": part.__name__, "url": None, "ok": False, "error": f"{err.__class__.__name__}: {err}"})
        write_summary(f, started, census_state, f"after {part.__name__}")
    if not a.skip_census:
        priority, err = census_priority()
        try:
            census_state = part_census_dashboards(f, priority,
                                                  lambda st: write_summary(f, started, st, "during part 4 (census)"))
            census_state["priority_error"] = err
        except Exception as exc:  # noqa: BLE001
            census_state = {"error": f"{exc.__class__.__name__}: {exc}", "priority_error": err}
    write_summary(f, started, census_state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
