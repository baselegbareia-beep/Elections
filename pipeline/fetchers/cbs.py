"""Runner fetcher: the official CBS files behind pipeline/build_cbs.py (the build container cannot reach
cbs.gov.il or data.gov.il; GitHub's runners can).

    python3 pipeline/fetchers/cbs.py --out <dir>

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
  3. The CBS geographic catalogue (/he/publications/doclib/2022/קטלוג/1. יישובים וחלוקות גאוגרפיות):
     the ballot-to-statistical-area crosswalks of 2019-2022 (kalpi_<month><year>_stat2011.xlsx) and their
     ReadMe, the stable-ballot workbook of 2022, the 2011<->2022 statistical-area keys, any newer
     crosswalk (a 2026 or a stat2022 one), and the newest statistical-area demography layer (.gdb.zip)
     that fits the size cap.
  4. census.cbs.gov.il: the religion dashboard (shares to 0.1%) of every statistical area of the mixed
     cities and Safed, sequentially at one request a second (the host blocks fast or parallel clients).
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

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
CBS = "https://www.cbs.gov.il"
ISHUVIM = "/he/publications/doclib/2019/ishuvim"
GEO_CATALOG = "/he/publications/doclib/2022/קטלוג/1. יישובים וחלוקות גאוגרפיות"
SP_FILES = CBS + "/he/publications/_api/web/GetFolderByServerRelativeUrl('{folder}')/Files" \
    "?$select=Name,ServerRelativeUrl,Length,TimeLastModified&$top=500"
FIXED_ISHUVIM = ["bycode2025.xlsx", "bycode2024.xlsx", "bycode2023.xlsx", "bycode2022.xlsx", "intro.pdf"]
DATAGOV = "https://data.gov.il"
CKAN_DATASETS = {"census2022": "3bd97fde-6cc3-456d-ab63-1caad16b2b6a",
                 "localities": "d9b1e04c-426f-4e32-ba40-a1ad9d8748a7"}
CENSUS_CSV = (DATAGOV + "/dataset/3bd97fde-6cc3-456d-ab63-1caad16b2b6a/resource/9a9e085f-3bc8-41df-b15f-be0daaf99e30/"
              "download/selected-data-by-localities-and-statistical-areas-2022-census.csv")
# names in the geographic catalogue -> the name written under files/ (ASCII)
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
GEO_NEWER = re.compile(r"(kalpi|stable_kalp).*(2023|2024|2025|2026|stat2022)|stat2022.*kalpi", re.I)
GDB = re.compile(r"statisticalareas_demography(\d{4})\.gdb\.zip$", re.I)
SIZE_CAP = 45 * 1024 * 1024        # bigger files are listed, not downloaded (the outputs are pushed to git)
# census.cbs.gov.il (an htmx front end over Looker): the search partial maps names to opaque area ids,
# get-csv returns a zip of the dashboard's CSVs. The religion dashboard id as used by
# https://github.com/circularsquare/maps/blob/HEAD/religiondots/sources/il.py
CENSUS_SEARCH = "https://census.cbs.gov.il/he/partials/search/area?search="
CENSUS_CSV_API = "https://census.cbs.gov.il/en/api/get-csv?dashboardId={dash}&ID={aid}"
DASH_RELIGION = "gIRhDCmNLsR3sI0G53n89n"
CENSUS_CITIES = {4000: "חיפה", 5000: "תל אביב -יפו", 7000: "לוד", 8500: "רמלה", 7600: "עכו",
                 1063: "מעלות-תרשיחא", 1061: "נוף הגליל", 3000: "ירושלים", 8000: "צפת"}
SHELL_BYTES = (2803, 2804)          # the site's SPA shell / error page, never an answer
POLITE = 1.0
CENSUS_BUDGET = (800, 25 * 60)      # at most this many requests / seconds for part 4


class Fetcher:
    def __init__(self, out):
        self.out = out
        self.items = []
        for d in ("files", "listings", "census"):
            os.makedirs(os.path.join(out, d), exist_ok=True)

    def get(self, url, headers=None, timeout=120, tries=3):
        """(status, bytes, headers) or raises after `tries` attempts; HTTP errors return their status."""
        last = None
        for attempt in range(tries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.status, r.read(), dict(r.headers)
            except urllib.error.HTTPError as err:
                if err.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                return err.code, err.read() if hasattr(err, "read") else b"", dict(err.headers or {})
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

    def listing(self, name, folder):
        """SharePoint REST listing of a CBS document folder -> [{Name, ServerRelativeUrl, Length, ...}]."""
        url = SP_FILES.format(folder=urllib.parse.quote(folder, safe="/"))
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


def file_url(server_relative):
    return CBS + urllib.parse.quote(server_relative, safe="/")


def ascii_name(name):
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return base if base and base not in (".", "..") else hashlib.sha256(name.encode()).hexdigest()[:12]


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
    gdbs = []
    for x in files:
        n, size = x.get("Name", ""), int(x.get("Length") or 0)
        url = file_url(x["ServerRelativeUrl"])
        magic = b"%PDF" if n.lower().endswith(".pdf") else b"PK\x03\x04" if n.lower().endswith((".xlsx", ".zip")) else None
        if n in GEO_WANTED or GEO_NEWER.search(n):
            if size > SIZE_CAP:
                f.items.append({"name": n, "url": url, "ok": False, "bytes": size, "error": "over the size cap"})
                continue
            f.save(GEO_WANTED.get(n) or ascii_name(n), url, magic=magic, min_bytes=1_000,
                   note=f"catalogue: {n}, modified {x.get('TimeLastModified')}")
        m = GDB.search(n)
        if m:
            gdbs.append((int(m.group(1)), n, size, url))
    for year, n, size, url in sorted(gdbs, reverse=True):
        if size <= SIZE_CAP:
            f.save(ascii_name(n), url, magic=b"PK\x03\x04", min_bytes=100_000,
                   note=f"newest statistical-area demography layer under the cap ({year})")
            break
        f.items.append({"name": n, "url": url, "ok": False, "bytes": size, "error": "over the size cap"})


def part_census_dashboards(f):
    print("4. census.cbs.gov.il religion dashboards", flush=True)
    t0, n_req, fails = time.time(), 0, 0
    state = {"requests": 0, "areas": 0, "ok": 0, "stopped": None}

    def polite_get(url, headers=None):
        nonlocal n_req, fails
        if n_req >= CENSUS_BUDGET[0] or time.time() - t0 > CENSUS_BUDGET[1]:
            raise RuntimeError("budget")
        time.sleep(POLITE)
        n_req += 1
        try:
            status, data, _ = f.get(url, headers=headers, timeout=60, tries=2)
        except Exception:
            fails += 1
            raise
        if status != 200 or len(data) in SHELL_BYTES:
            fails += 1
            raise IOError(f"HTTP {status}, {len(data)} bytes")
        fails = 0
        return data

    for code, city in CENSUS_CITIES.items():
        found, out = {}, {"code": code, "city": city, "areas": [], "errors": []}
        terms = [f"{city} אזור סטטיסטי"] + [f"{city} אזור סטטיסטי {d}" for d in range(1, 10)]
        for term in terms:
            if state["stopped"]:
                break
            try:
                doc = polite_get(CENSUS_SEARCH + urllib.parse.quote(term), {"HX-Request": "true"}).decode("utf-8", "replace")
            except RuntimeError:
                state["stopped"] = "budget"
                break
            except Exception as err:  # noqa: BLE001
                out["errors"].append(f"search {term}: {err}")
                if fails >= 5:
                    state["stopped"] = "five failures in a row"
                continue
            for aid, label, typ in re.findall(r'data-id="([^"]*)"\s+data-search="([^"]*)"\s+data-type="([^"]*)"', doc):
                label, typ = html.unescape(label), html.unescape(typ)
                m = re.search(r"אזור סטטיסטי\s*(\d+)", label)
                if m and city.replace(" ", "") in label.replace(" ", ""):
                    found[int(m.group(1))] = (aid, label, typ)
                elif label.strip() == city and "unit" not in out:
                    out["unit"] = {"id": aid, "label": label, "type": typ}
            if term == terms[0] and found and len(found) < 90:
                break     # the plain query returned every area (the search caps at 100 results)
        targets = ([("locality", out["unit"]["id"], out["unit"]["label"])] if "unit" in out else []) + \
            [(num, aid, label) for num, (aid, label, _) in sorted(found.items())]
        for num, aid, label in targets:
            if state["stopped"]:
                break
            rec = {"area": num, "id": aid, "label": label}
            try:
                blob = polite_get(CENSUS_CSV_API.format(dash=DASH_RELIGION, aid=urllib.parse.quote(aid)))
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    rec["csv"] = {i.filename: z.read(i).decode("utf-8-sig", "replace") for i in z.infolist()
                                  if i.file_size < 2_000_000}
                rec["sha256"] = hashlib.sha256(blob).hexdigest()
                state["ok"] += 1
            except RuntimeError:
                state["stopped"] = "budget"
                break
            except Exception as err:  # noqa: BLE001
                rec["error"] = f"{err.__class__.__name__}: {err}"
                if fails >= 5:
                    state["stopped"] = "five failures in a row"
            out["areas"].append(rec)
            state["areas"] += 1
        path = os.path.join(f.out, "census", f"religion_{code}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False)
        f.items.append({"name": f"census/religion_{code}.json", "url": CENSUS_SEARCH, "ok": bool(out["areas"]),
                        "path": os.path.relpath(path, f.out), "areas": len(out["areas"]),
                        "areas_with_data": sum(1 for a in out["areas"] if "csv" in a),
                        "error": "; ".join(out["errors"][:3]) or None})
        print(f"  {city}: {len(found)} areas found, {sum(1 for a in out['areas'] if 'csv' in a)} fetched", flush=True)
    state["requests"] = n_req
    return state


def write_summary(f, started, census_state):
    ok = sum(1 for i in f.items if i.get("ok"))
    summary = {"fetcher": "cbs", "started": started,
               "finished": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "runner": {"python": platform.python_version(), "host": platform.node()},
               "ok": ok, "failed": len(f.items) - ok, "census_dashboards": census_state, "items": f.items}
    with open(os.path.join(f.out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    lines = [f"# CBS fetch {summary['finished']}", "",
             f"{ok} ok, {len(f.items) - ok} failed. Census dashboards: {json.dumps(census_state, ensure_ascii=False)}", "",
             "| file | ok | status | bytes | sha256 | last-modified | error / note |", "|---|---|---|---|---|---|---|"]
    for i in f.items:
        cell = lambda v: str(v if v is not None else "").replace("|", "/")
        lines.append(f"| {cell(i.get('path') or i['name'])} | {'yes' if i.get('ok') else 'no'} | {cell(i.get('status'))} | "
                     f"{cell(i.get('bytes'))} | {cell((i.get('sha256') or '')[:16])} | {cell(i.get('last_modified'))} | "
                     f"{cell(i.get('error') or i.get('note'))} |")
    with open(os.path.join(f.out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"summary: {ok} ok, {len(f.items) - ok} failed -> {f.out}/summary.md", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-census", action="store_true", help="leave out part 4 (census.cbs.gov.il)")
    a = ap.parse_args()
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    f = Fetcher(a.out)
    census_state = None
    for part in (part_localities, part_datagov, part_geo_catalog):
        try:
            part(f)
        except Exception as err:  # noqa: BLE001 - one part failing leaves the others
            f.items.append({"name": part.__name__, "url": None, "ok": False, "error": f"{err.__class__.__name__}: {err}"})
    if not a.skip_census:
        try:
            census_state = part_census_dashboards(f)
        except Exception as err:  # noqa: BLE001
            census_state = {"error": f"{err.__class__.__name__}: {err}"}
    write_summary(f, started, census_state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
