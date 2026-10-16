"""Build the CBS locality reference (קובץ היישובים של הלמ״ס) and validate the site's classification.

Input (each a local file; `--fetch` downloads the pinned copies listed in SOURCES into --cache):
  --bycode   the CBS locality file, bycodeYYYY.xlsx (official: www.cbs.gov.il/he/publications/doclib/2019/
             ishuvim/; the runner fetcher pipeline/fetchers/cbs.py downloads it, this container cannot)
  --bycode-check  an earlier year's locality file from a second, independent copy (cross-check only)
  --census   CBS 2022 census, "selected data by localities and statistical areas" (data.gov.il CSV):
             the modal religion of every locality and statistical area (2022 areas)
  --sa2011 / --sa2022 / --localities   CBS polygons (statistical areas 2011 and 2022, localities 2022),
             GeoJSON in zip, from the public-data release the ballot mirror comes from
  --ballots  the ballot mirror (data/raw/mirror/ballots): every ballot's statistical area (2011 areas), from
             the CBS ballot-to-area crosswalks (kalpi_<month><year>_stat2011.xlsx)
  site/data/core.json, site/data/ballots_K2x.json and pipeline/reference/arab_localities.csv (the site's
  own classification, compared, never changed here)

Output (pipeline/reference/):
  cbs_localities.json  one row per CBS locality: code, names, district, sub-district, natural region,
                       municipal status, the locality religion code (דת יישוב) and the population groups
                       (Jews and others / Arabs / foreigners), locality form (צורת יישוב), founding year,
                       ITM coordinates and their WGS84 conversion, the 2022 census modal religion; with the
                       source URL, file date and SHA-256 of every input.
  cbs_validation.json  every disagreement between the CBS classification and arab_localities.csv / the
                       sectors of core.json, with numbers; the statistical-area test of the mixed-city rule.
  cbs_mixed_areas.json the statistical areas (2011) of the mixed cities and of the Jewish localities with
                       an Arab area or an Arab polling station, their Arab share (2022 census, see below),
                       and every polling station's class by area and by vote, K21-K25.

Run: python3 pipeline/build_cbs.py --fetch            (downloads the pinned copies into data/raw/cbs)
     python3 pipeline/build_cbs.py --bycode F.xlsx --census F.csv --sa2011 F.zip --sa2022 F.zip ...

Statistical areas. The ballot crosswalk gives each polling station its statistical area in the 2011
division; the 2022 census reports areas in the 2022 division. A 2011 area's Arab share is estimated by
sampling points on a ~30 m grid inside it, giving each point the 2022 area it falls in, weighting it by
that area's population density (census population / area) and counting it as Arab when the area's modal
religion is Muslim, Christian or Druze. The census file gives the modal religion only, not the shares, so
the share is of residents of Arab-majority 2022 areas, not of Arab residents; CBS's own 2011-to-2022 key
and the census dashboards' religion shares are fetched by pipeline/fetchers/cbs.py for the next round.
Nothing here changes the site's classification: it reports.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
import re
import statistics
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "pipeline", "reference")
SITE_DATA = os.path.join(ROOT, "site", "data")

# The copies used here, pinned by commit and SHA-256. The official URLs are what the runner fetcher
# (pipeline/fetchers/cbs.py) downloads; a file passed on the command line is identified by its hash.
SOURCES = {
    "bycode2024": {
        "title": "הלמ״ס — קובץ היישובים 2024 (bycode2024.xlsx)",
        "official": "https://www.cbs.gov.il/he/publications/doclib/2019/ishuvim/bycode2024.xlsx",
        "page": "https://www.cbs.gov.il/he/publications/Pages/2019/%D7%99%D7%99%D7%A9%D7%95%D7%91%D7%99%D7%9D-%D7%91%D7%99%D7%A9%D7%A8%D7%90%D7%9C.aspx",
        "mirror": "https://raw.githubusercontent.com/NX1X/OpenTaxMap/2add2ff20d7fa73010451368e78b4c52a57dcd9f/data/cbs/bycode2024.xlsx",
        "sha256": "c97316c60d0fc9250bfe6b0ef79e565255e033bb756e3dc3eb4ba081c7bb44b2",
        # another project recorded this hash for the official URL, retrieved 2026-10-12
        # (https://github.com/nitz-git/il-builtup-osm/blob/HEAD/config/build.json): the CBS file may
        # have been re-issued since the mirror copied it; the runner fetch settles which one is current
        "official_sha256_reported": "a021c6a151863ded624d2f674f9bbcf90ba9f3660c8d55aebe6526ff7f5d2ad0",
    },
    "bycode2023": {
        "title": "הלמ״ס — קובץ היישובים 2023, סופי (bycode2023Sofi.xlsx)",
        "official": "https://data.gov.il/dataset/d9b1e04c-426f-4e32-ba40-a1ad9d8748a7/resource/d47a54ff-87f0-44b3-b33a-f284c0c38e5a/download/bycode2023.xlsx",
        "page": "https://www.cbs.gov.il/he/publications/Pages/2019/%D7%99%D7%99%D7%A9%D7%95%D7%91%D7%99%D7%9D-%D7%91%D7%99%D7%A9%D7%A8%D7%90%D7%9C.aspx",
        "mirror": "https://raw.githubusercontent.com/mattip/population-map/61263be3b4cca02d9ec576b38d6443250a2d80c7/bycode2023Sofi.xlsx",
        "sha256": "a372c2b45e62bc77bab83eb885c73eab0985d79f53b40853946146915e11a7a9",
    },
    "census2022": {
        "title": "הלמ״ס — מפקד 2022, נתונים נבחרים ליישובים ולאזורים סטטיסטיים",
        "official": "https://data.gov.il/dataset/3bd97fde-6cc3-456d-ab63-1caad16b2b6a/resource/9a9e085f-3bc8-41df-b15f-be0daaf99e30/download/selected-data-by-localities-and-statistical-areas-2022-census.csv",
        "mirror": "https://raw.githubusercontent.com/cokobi/israel-public-transport-project/a27595834083e89d44d2fa9adee82170761a7a6d/exploration/mifkad2022.csv",
        "sha256": "85847ae55d35b77ef82a0bcc95b203ae72d5996e54706a741d5dd4a3f18707a8",
    },
    "sa2011": {
        "title": "הלמ״ס — אזורים סטטיסטיים 2011 (פוליגונים, WGS84)",
        "official": "https://www.cbs.gov.il/he/Pages/geo-layers.aspx",
        "mirror": "https://raw.githubusercontent.com/Yoavfried/israel-election-map/4bb9cb9664630a31444a6769502eec6ffea77b77/public-data/v1/geographies/statistical_areas_2011.zip",
        "sha256": "aa083e5fed9ab54f6d188daeacfffa007ffacdc76dfe2753092dfbd2cbecd26f",
    },
    "sa2022": {
        "title": "הלמ״ס — אזורים סטטיסטיים 2022 (פוליגונים, WGS84)",
        "official": "https://www.cbs.gov.il/he/Pages/geo-layers.aspx",
        "mirror": "https://raw.githubusercontent.com/Yoavfried/israel-election-map/4bb9cb9664630a31444a6769502eec6ffea77b77/public-data/v1/geographies/statistical_areas_2022.zip",
        "sha256": "ddb21bd8a8315291b5170a961b14e5e74c2b221e6f3ddaf3f7ed6f6398a42c28",
    },
}
DEFAULT_CACHE = os.path.join(ROOT, "data", "raw", "cbs")
CACHE_NAMES = {"bycode2024": "bycode2024.xlsx", "bycode2023": "bycode2023Sofi.xlsx",
               "census2022": "census2022_localities_statareas.csv",
               "sa2011": "statistical_areas_2011.zip", "sa2022": "statistical_areas_2022.zip"}

# דת יישוב, as the codes are used in the file (1,490 rows of bycode2024): the definitions are in the
# file's documentation (ishuvim/intro.pdf, fetched by the runner); the reading below is what the rows
# show and is checked in cbs_validation.json (every Arab, Druze and Circassian locality of the site's
# list is 2, the Bedouin tribes 3, the eight mixed cities and Neve Shalom 4).
RELIGION = {1: "jewish", 2: "arab", 3: "bedouin_tribe", 4: "mixed"}
ARAB_RELIGIONS = {"מוסלמים", "נוצרים", "דרוזים"}   # census modal religion counted as an Arab area
OTHER_RELIGION = "דת אחרת"                          # foreign workers' areas, Baha'i centre: not Arab

# output field -> header in the CBS file (exact, or the prefix of a year-stamped header)
COLS = [
    ("code", "סמל יישוב"), ("name", "שם יישוב"), ("name_en", "שם יישוב באנגלית"), ("translit", "תעתיק"),
    ("district_code", "סמל מחוז"), ("district", "שם מחוז"), ("subdistrict_code", "סמל נפה"),
    ("subdistrict", "שם נפה"), ("natural_region", "אזור טבעי"), ("municipal_status_code", "סמל מעמד מונציפאלי"),
    ("municipal_status", "שם מעמד מונציפאלי"), ("metropolitan", "שיוך מטרופוליני"), ("religion", "דת יישוב"),
    ("pop_total", "סך הכל אוכלוסייה"), ("israelis", "סך הכל ישראלים"), ("jews_others", "יהודים ואחרים"),
    ("arabs", "ערבים"), ("foreigners", "זרים"), ("founded", "שנת ייסוד"), ("form", "צורת יישוב שוטפת"),
    ("organization", "השתייכות ארגונית"), ("coordinates", "קואורדינטות"), ("altitude", "גובה ממוצע"),
    ("year", "שנה"), ("authority_code", "סמל רשות מקומית"), ("authority", "שם רשות מקומית"),
]
OUT_FIELDS = ["code", "name", "name_en", "district_code", "district", "subdistrict_code", "subdistrict",
              "natural_region", "municipal_status_code", "municipal_status", "authority_code", "religion",
              "group", "form", "pop_total", "israelis", "jews_others", "arabs", "foreigners", "arab_share",
              "founded", "itm_x", "itm_y", "lat", "lng", "census2022_pop", "census2022_religion"]


# ---- files ---------------------------------------------------------------------------------------

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance(path, key):
    """Where an input came from: the pinned copy when the hash matches, else an unpinned file."""
    if not path or not os.path.exists(path):
        return None
    s = SOURCES[key]
    digest = sha256(path)
    rec = {"title": s["title"], "official_url": s["official"], "file": os.path.basename(path),
           "bytes": os.path.getsize(path), "sha256": digest}
    if digest == s["sha256"]:
        rec.update(copy="mirror", url=s["mirror"])
    elif digest == s.get("official_sha256_reported"):
        rec.update(copy="official", url=s["official"])
    else:
        rec.update(copy="unpinned (not the pinned mirror; check against the runner fetch summary)")
    return rec


def fetch(cache):
    """Download the pinned copies into `cache` (refusing a hash mismatch); return {key: path}."""
    os.makedirs(cache, exist_ok=True)
    out = {}
    for key, s in SOURCES.items():
        path = os.path.join(cache, CACHE_NAMES[key])
        if not (os.path.exists(path) and sha256(path) == s["sha256"]):
            data = b""
            for attempt in range(4):        # large files through a proxy are sometimes cut off
                try:
                    req = urllib.request.Request(s["mirror"], headers={"User-Agent": "kalpi26-pipeline"})
                    with urllib.request.urlopen(req, timeout=180) as r:
                        data = r.read()
                    break
                except Exception as err:  # noqa: BLE001
                    print(f"  {key}: attempt {attempt + 1} failed ({err.__class__.__name__})", file=sys.stderr)
            if hashlib.sha256(data).hexdigest() != s["sha256"]:
                raise SystemExit(f"{key}: {s['mirror']} does not match the pinned SHA-256")
            with open(path, "wb") as f:
                f.write(data)
        out[key] = path
    return out


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def read_xlsx(path):
    """First worksheet of an .xlsx as a list of rows (standard library only), and the file's own
    last-modified stamp (docProps/core.xml)."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        first = wb.find("m:sheets/m:sheet", NS)
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == first.get(RID))
        target = target.lstrip("/")
        sheet = target if target.startswith("xl/") else "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(sheet)).iterfind("m:sheetData/m:row", NS):
            vals = {}
            for c in row.findall("m:c", NS):
                ref, t = c.get("r"), c.get("t")
                col = 0
                for ch in re.match(r"[A-Z]+", ref).group(0):
                    col = col * 26 + ord(ch) - 64
                v = c.find("m:v", NS)
                if t == "s":
                    val = shared[int(v.text)] if v is not None else None
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
                elif v is None or v.text is None:
                    val = None
                elif t in ("str", "e"):
                    val = v.text
                elif t == "b":
                    val = v.text == "1"
                else:
                    num = float(v.text)
                    val = int(num) if num.is_integer() else num
                vals[col - 1] = val
            if vals:
                rows.append([vals.get(i) for i in range(max(vals) + 1)])
        modified = None
        if "docProps/core.xml" in names:
            m = re.search(rb"<dcterms:modified[^>]*>([^<]+)<", z.read("docProps/core.xml"))
            modified = m.group(1).decode() if m else None
    return rows, modified


def read_bycode(path):
    rows, modified = read_xlsx(path)
    header = [str(h).strip() if h is not None else "" for h in rows[0]]

    def col(text):
        if text in header:
            return header.index(text)
        hits = [i for i, h in enumerate(header) if h.startswith(text)]
        return hits[0] if hits else None

    idx = {k: col(h) for k, h in COLS}
    if idx["code"] is None or idx["religion"] is None:
        raise SystemExit(f"{path}: not a CBS locality file (no סמל יישוב / דת יישוב column)")
    recs = []
    for r in rows[1:]:
        g = {k: (r[i] if i is not None and i < len(r) else None) for k, i in idx.items()}
        if not isinstance(g["code"], int):
            continue
        for k, v in g.items():
            if isinstance(v, str):
                g[k] = v.strip() or None
        recs.append(g)
    return {"header": header, "modified": modified, "sheet_rows": len(rows) - 1,
            "pop_header": header[idx["pop_total"]] if idx["pop_total"] is not None else None}, recs


def read_census(path):
    """Locality rows {code: row} and statistical-area units {(code, area): row} of the 2022 census CSV.
    CBS publishes small areas merged (StatAreaCmb "1022+1023"), so every component points to its unit."""
    loc, units = {}, {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not r.get("LocalityCode"):
                continue
            code = int(float(r["LocalityCode"]))
            rec = {"pop": int(float(r["pop_approx"] or 0)), "religion": r["ReligionHeb"].strip(),
                   "unit": (r.get("StatAreaCmb") or "").strip()}
            if not r.get("StatArea"):
                loc[code] = rec
            else:
                for part in rec["unit"].split("+"):
                    units[(code, int(part))] = rec
    return loc, units


def read_geojson_zip(path):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(".geojson"))
        return json.loads(z.read(name).decode("utf-8"))["features"]


# ---- coordinates ---------------------------------------------------------------------------------
# Israeli Transverse Mercator (EPSG:2039): GRS80, origin 31°44'03.817"N 35°12'16.261"E, k0 1.0000067,
# false easting 219,529.584, false northing 626,907.390; Israel 1993 -> WGS84 by the 7-parameter
# position-vector shift of the EPSG:2039 definition. Inverse by the Krüger series.
GRS80_A, GRS80_F = 6378137.0, 1 / 298.257222101
WGS84_F = 1 / 298.257223563
ITM_LAT0, ITM_LON0 = math.radians(31.7343936111111), math.radians(35.2045169444444)
ITM_K0, ITM_FE, ITM_FN = 1.0000067, 219529.584, 626907.390
TOWGS84 = (-24.0024, -17.1032, -17.8444, -0.33077, -1.85269, 1.66969, 5.4248)


def _tm_constants(a, f):
    n = f / (2 - f)
    A = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    alpha = (n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16, 13 * n ** 2 / 48 - 3 * n ** 3 / 5, 61 * n ** 3 / 240)
    beta = (n / 2 - 2 * n ** 2 / 3 + 37 * n ** 3 / 96, n ** 2 / 48 + n ** 3 / 15, 17 * n ** 3 / 480)
    delta = (2 * n - 2 * n ** 2 / 3 - 2 * n ** 3, 7 * n ** 2 / 3 - 8 * n ** 3 / 5, 56 * n ** 3 / 15)
    return n, A, alpha, beta, delta


def _xi_of_lat(lat, n, alpha):
    e = 2 * math.sqrt(n) / (1 + n)
    t = math.sinh(math.atanh(math.sin(lat)) - e * math.atanh(e * math.sin(lat)))
    xi1 = math.atan(t)
    return xi1 + sum(a * math.sin(2 * (j + 1) * xi1) for j, a in enumerate(alpha))


def itm_to_wgs84(x, y):
    n, A, alpha, beta, delta = _tm_constants(GRS80_A, GRS80_F)
    xi = (y - ITM_FN) / (ITM_K0 * A) + _xi_of_lat(ITM_LAT0, n, alpha)
    eta = (x - ITM_FE) / (ITM_K0 * A)
    xi1 = xi - sum(b * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j, b in enumerate(beta))
    eta1 = eta - sum(b * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j, b in enumerate(beta))
    chi = math.asin(math.sin(xi1) / math.cosh(eta1))
    lat = chi + sum(d * math.sin(2 * (j + 1) * chi) for j, d in enumerate(delta))
    lon = ITM_LON0 + math.atan2(math.sinh(eta1), math.cos(xi1))
    # Israel 1993 (GRS80) -> ECEF -> WGS84
    e2 = GRS80_F * (2 - GRS80_F)
    N = GRS80_A / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    X, Y, Z = N * math.cos(lat) * math.cos(lon), N * math.cos(lat) * math.sin(lon), N * (1 - e2) * math.sin(lat)
    dx, dy, dz, rx, ry, rz, s = TOWGS84
    rx, ry, rz = (math.radians(v / 3600) for v in (rx, ry, rz))
    m = 1 + s * 1e-6
    X2 = dx + m * (X - rz * Y + ry * Z)
    Y2 = dy + m * (rz * X + Y - rx * Z)
    Z2 = dz + m * (-ry * X + rx * Y + Z)
    e2w = WGS84_F * (2 - WGS84_F)
    p = math.hypot(X2, Y2)
    lat2 = math.atan2(Z2, p * (1 - e2w))
    for _ in range(6):
        Nw = GRS80_A / math.sqrt(1 - e2w * math.sin(lat2) ** 2)
        h = p / math.cos(lat2) - Nw
        lat2 = math.atan2(Z2, p * (1 - e2w * Nw / (Nw + h)))
    return math.degrees(lat2), math.degrees(math.atan2(Y2, X2))


def parse_itm(s):
    """CBS 'קואורדינטות': 12 digits, easting then northing in metres (ITM)."""
    s = str(s or "").strip()
    if len(s) == 12 and s.isdigit():
        return int(s[:6]), int(s[6:])
    return None


# ---- geometry ------------------------------------------------------------------------------------

def rings_of(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return [np.asarray(r, float)[:, :2] for p in polys for r in p if len(r) >= 4]


def inside(pts, rings, chunk=4000):
    """Even-odd ray casting of points (m x 2) against all rings of a (multi)polygon, vectorised."""
    res = np.zeros(len(pts), bool)
    if not len(pts):
        return res
    x, y = pts[:, 0][:, None], pts[:, 1][:, None]
    for r in rings:
        for i in range(0, len(r) - 1, chunk):
            seg = r[i:i + chunk + 1]
            x1, y1, x2, y2 = seg[:-1, 0], seg[:-1, 1], seg[1:, 0], seg[1:, 1]
            cond = (y1 > y) != (y2 > y)
            dy = np.where(y2 == y1, 1e-30, y2 - y1)
            xi = x1 + (y - y1) * (x2 - x1) / dy
            res ^= (np.count_nonzero(cond & (x < xi), axis=1) % 2).astype(bool)
    return res


def bbox(rings):
    allp = np.vstack(rings)
    return allp.min(0), allp.max(0)


def sample_points(rings, step=0.0003):
    """Grid points (~30 m) inside a polygon; a coarser interior grid for very small areas."""
    lo, hi = bbox(rings)
    gx = np.arange(lo[0] + step / 2, hi[0], step)
    gy = np.arange(lo[1] + step / 2, hi[1], step / 1.17)   # ~equal metres at 31.5°N
    if len(gx) * len(gy) < 40:
        gx, gy = np.linspace(lo[0], hi[0], 9)[1:-1], np.linspace(lo[1], hi[1], 9)[1:-1]
    X, Y = np.meshgrid(gx, gy)
    pts = np.c_[X.ravel(), Y.ravel()]
    pts = pts[inside(pts, rings)]
    return pts if len(pts) else np.vstack(rings).mean(0)[None, :]


# ---- main build ----------------------------------------------------------------------------------

def build_localities(by_path, census, loc_polys):
    meta, recs = read_bycode(by_path)
    census_loc = census[0] if census else {}
    out = []
    for g in sorted(recs, key=lambda r: r["code"]):
        rel = g["religion"] if isinstance(g["religion"], int) else None
        itm = parse_itm(g["coordinates"])
        lat = lng = None
        if itm:
            lat, lng = itm_to_wgs84(*itm)
            lat, lng = round(lat, 5), round(lng, 5)
        israelis = g["israelis"] if isinstance(g["israelis"], int) else None
        arabs = g["arabs"] if isinstance(g["arabs"], int) else 0
        c = census_loc.get(g["code"])
        out.append({
            **{k: g.get(k) for k in OUT_FIELDS if k in g},
            "religion": rel, "group": RELIGION.get(rel),
            "arab_share": round(arabs / israelis, 4) if israelis else None,
            "itm_x": itm[0] if itm else None, "itm_y": itm[1] if itm else None, "lat": lat, "lng": lng,
            "census2022_pop": c["pop"] if c else None, "census2022_religion": c["religion"] if c else None,
        })
    # Coordinates check: the converted point should fall inside the locality's CBS 2022 polygon.
    check = None
    if loc_polys:
        n_in = n_out = 0
        far = []
        for r in out:
            rings = loc_polys.get(r["code"])
            if rings is None or r["lat"] is None:
                continue
            ok = bool(inside(np.array([[r["lng"], r["lat"]]]), rings)[0])
            n_in += ok
            n_out += not ok
            if not ok:
                lo, hi = bbox(rings)
                cx, cy = (lo + hi) / 2
                d = math.hypot((r["lng"] - cx) * 94.6, (r["lat"] - cy) * 110.9)
                far.append([r["code"], r["name"], round(d, 2)])
        check = {"points_inside_polygon": n_in, "points_outside": n_out,
                 "outside_km_from_polygon_box_centre": sorted(far, key=lambda x: -x[2])[:25]}
    return meta, out, check


def classify_compare(locs, check_locs, arab_csv, core, census):
    by = {r["code"]: r for r in locs}
    seg = {}
    with open(arab_csv, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            seg[int(r["locality_code"])] = r
    core_loc = {L["code"]: L for L in core["localities"]}
    cols25 = core["party_cols"]["K25"]     # a locality's K25 row: boxes, elig, voters, valid, arab_boxes, *cols
    arab_cols = [cols25.index(p) for p in R.ARAB_LISTS["K25"] if p in cols25]

    def k25_stats(code):
        L = core_loc.get(code)
        row = L and L["el"].get("K25")
        if not row:
            return None, None
        valid = row[3]
        arab = sum(row[5 + i] for i in arab_cols)
        return row[1], round(arab / valid, 4) if valid else None

    expect = {"arab": {2, 3}, "druze": {2}, "mixed": {4}}
    # 1. the site's list against the CBS religion code
    list_rows, list_dis = [], []
    for code, a in sorted(seg.items()):
        sector = R.SEGMENTS[a["segment"]][0]
        c = by.get(code)
        rel = c["religion"] if c else None
        list_rows.append([code, a["name_he_k21_k22_csv"], a["segment"], rel, c["arab_share"] if c else None])
        if rel not in expect[sector]:
            list_dis.append({"code": code, "name": a["name_he_k21_k22_csv"], "segment": a["segment"],
                             "cbs_religion": rel, "cbs_arab_share": c["arab_share"] if c else None})
    per_segment = collections.defaultdict(collections.Counter)
    for code, name, s, rel, _ in list_rows:
        per_segment[s][str(rel)] += 1
    # 2. CBS non-Jewish / mixed localities missing from the list
    missing = []
    for c in locs:
        if c["religion"] in (2, 3, 4) and c["code"] not in seg:
            elig, share = k25_stats(c["code"])
            missing.append({"code": c["code"], "name": c["name"], "cbs_religion": c["religion"], "form": c["form"],
                            "district": c["district"], "israelis": c["israelis"], "arabs": c["arabs"],
                            "in_election_results": c["code"] in core_loc, "k25_eligible": elig})
    # 3. core.json sectors against CBS
    conf = collections.Counter()
    conf_elig = collections.Counter()
    core_dis, not_in_cbs, no_group = [], [], []
    for code, L in sorted(core_loc.items()):
        c = by.get(code)
        elig, share = k25_stats(code)
        if c is None:
            not_in_cbs.append({"code": code, "name": L["name"], "sector": L["sector"], "k25_eligible": elig,
                               "elections": sorted(L["el"])})
            continue
        if c["religion"] is None:   # in the file without a population (an institution, a new place)
            no_group.append({"code": code, "name": L["name"], "sector": L["sector"], "cbs_form": c["form"],
                             "k25_eligible": elig, "elections": sorted(L["el"])})
        key = f"{L['sector']}|{c['group']}"
        conf[key] += 1
        conf_elig[key] += elig or 0
        ok = (L["sector"] == "jewish" and c["religion"] in (1, None)) or c["religion"] in expect.get(L["sector"], set())
        if not ok:
            core_dis.append({"code": code, "name": L["name"], "sector": L["sector"], "cbs_religion": c["religion"],
                             "cbs_arab_share": c["arab_share"], "k25_eligible": elig, "k25_arab_list_share": share})
    # 4. Jewish (code 1) localities with an Arab minority: not a disagreement, the site counts them Jewish
    minority = []
    for c in locs:
        if c["religion"] == 1 and c["israelis"] and (c["arabs"] or 0) / c["israelis"] >= 0.05 and c["israelis"] >= 300:
            elig, share = k25_stats(c["code"])
            minority.append({"code": c["code"], "name": c["name"], "israelis": c["israelis"], "arabs": c["arabs"],
                             "arab_share": c["arab_share"], "k25_eligible": elig, "k25_arab_list_share": share})
    minority.sort(key=lambda r: -(r["arabs"] or 0))
    # 5. the community sub-segments against the 2022 census modal religion of the locality
    sub_dis, sub_counts = [], collections.defaultdict(collections.Counter)
    want = {"DRUZE_GALILEE_CARMEL": {"דרוזים"}, "DRUZE_GOLAN": {"דרוזים"},
            "CHRISTIAN_MAJORITY_OR_PLURALITY": {"נוצרים"}}
    if census:
        for code, a in seg.items():
            c = census[0].get(code)
            lab = c["religion"] if c else None
            sub_counts[a["segment"]][lab or "(no census row)"] += 1
            s = a["segment"]
            sector = R.SEGMENTS[s][0]
            if lab is None:
                continue
            bad = (s in want and lab not in want[s]) or (s not in want and sector == "arab" and lab not in ARAB_RELIGIONS) \
                or (s not in want and lab == "דרוזים" and s != "MIXED_DRUZE_MUSLIM_CHRISTIAN_TOWN") \
                or (s not in want and lab == "נוצרים")
            if bad:
                sub_dis.append({"code": code, "name": a["name_he_k21_k22_csv"], "segment": s,
                                "census2022_religion": lab, "census2022_pop": c["pop"]})
    # 6. the second, independent copy (earlier year) against the main one
    cross = None
    if check_locs:
        prev = {r["code"]: r for r in check_locs}
        changed = [[c["code"], c["name"], prev[c["code"]]["religion"], c["religion"]]
                   for c in locs if c["code"] in prev and prev[c["code"]]["religion"] != c["religion"]]
        cross = {"rows_main": len(locs), "rows_check": len(check_locs),
                 "only_in_main": [[c["code"], c["name"]] for c in locs if c["code"] not in prev],
                 "only_in_check": [[c["code"], c["name"]] for c in check_locs if c["code"] not in by],
                 "religion_code_changed": changed}
    rel_counts = collections.Counter(str(c["religion"]) for c in locs)
    return {
        "religion_codes": {"counts": dict(sorted(rel_counts.items())),
                           "reading": {"1": "יישוב יהודי", "2": "יישוב ערבי (כולל דרוזים וצ׳רקסים)",
                                       "3": "שבט בדואי (צורת יישוב 460, בלי נתוני אוכלוסייה)",
                                       "4": "יישוב מעורב", "None": "מקום בלי אוכלוסייה (מוסד, אזור תעשייה)"},
                           "note": "לפי הנתונים; ההגדרות הרשמיות בקובץ ההסבר intro.pdf (נמשך ב-runner)"},
        "list_vs_cbs": {"rows": len(seg), "disagreements": list_dis,
                        "per_segment_cbs_religion": {k: dict(v) for k, v in sorted(per_segment.items())},
                        "rows_detail_fields": ["code", "name", "segment", "cbs_religion", "cbs_arab_share"],
                        "rows_detail": list_rows},
        "cbs_nonjewish_not_in_list": missing,
        "core_vs_cbs": {"localities": len(core_loc), "confusion_sector_vs_cbs_group": dict(sorted(conf.items())),
                        "confusion_k25_eligible": dict(sorted(conf_elig.items())),
                        "disagreements": core_dis, "not_in_cbs_file": not_in_cbs,
                        "no_population_group_in_cbs_file": no_group},
        "jewish_localities_with_arab_minority": minority,
        "segments_vs_census2022_religion": {"counts": {k: dict(v) for k, v in sorted(sub_counts.items())},
                                            "disagreements": sub_dis},
        "second_copy_check": cross,
    }


def mixed_areas(census, sa11_path, sa22_path, ballots_dir, core, locs):
    """Arab share of the 2011 statistical areas in scope, and every polling station's class by area."""
    units = census[1]
    by = {r["code"]: r for r in locs}
    core_loc = {L["code"]: L for L in core["localities"]}
    site_b = {e: json.load(open(os.path.join(SITE_DATA, f"ballots_{e}.json"), encoding="utf-8")) for e in R.ELECTIONS}
    # scope: CBS mixed localities, plus Jewish localities with an Arab polling station (site rule) or an
    # Arab-majority 2022 area
    scope = {c["code"] for c in locs if c["religion"] == 4}
    for e, b in site_b.items():
        for row in b["rows"]:
            if row[2] % 10 == 1 and core_loc.get(row[0], {}).get("sector") in ("jewish", "mixed"):
                scope.add(row[0])
    for (code, _), u in units.items():
        if u["religion"] in ARAB_RELIGIONS and by.get(code, {}).get("religion") == 1:
            scope.add(code)
    f22 = [f for f in read_geojson_zip(sa22_path) if f["properties"]["locality_code"] in scope]
    p22 = []
    unit_area = collections.Counter()
    for f in f22:
        pr = f["properties"]
        key = (pr["locality_code"], int(pr["stat_2022"]))
        u = units.get(key)
        if u:
            unit_area[(key[0], u["unit"])] += pr.get("Shape_Area") or 0
    for f in f22:
        pr = f["properties"]
        key = (pr["locality_code"], int(pr["stat_2022"]))
        u = units.get(key)
        rings = rings_of(f["geometry"])
        dens = (u["pop"] / unit_area[(key[0], u["unit"])]) if u and unit_area[(key[0], u["unit"])] else None
        p22.append((key, rings, *bbox(rings), u, dens))
    areas = {}
    for f in read_geojson_zip(sa11_path):
        pr = f["properties"]
        code = pr["locality_code"]
        if code not in scope:
            continue
        rings = rings_of(f["geometry"])
        pts = sample_points(rings)
        lo, hi = bbox(rings)
        w = collections.Counter()
        hit_units = collections.Counter()
        labelled = 0
        for key, r2, lo2, hi2, u, dens in p22:
            if key[0] != code or (hi2 < lo).any() or (lo2 > hi).any():
                continue
            n = int(inside(pts, r2).sum())
            if not n:
                continue
            hit_units[u["unit"] if u else f"{key[1]} (no census row)"] += n
            if u is None or dens is None:
                continue
            labelled += n
            w["all"] += n * dens
            w[u["religion"]] += n * dens

        def share(*labels):
            return round(sum(w[x] for x in labels) / w["all"], 3) if w["all"] else None

        areas[int(pr["yishuv_stat"])] = {
            "code": code, "area": int(pr["stat_area_number"]), "points": int(len(pts)),
            "labelled": round(labelled / len(pts), 3),
            "arab_share": share(*ARAB_RELIGIONS),
            # a Christian-modal area outside an Arab locality may be of non-Arab Christians
            "christian_modal_share": share("נוצרים"),
            "other_religion_share": share(OTHER_RELIGION),
            "units_2022": dict(hit_units.most_common()),
        }

    def area_class(stats):
        sh = [areas[s]["arab_share"] for s in stats if s in areas and areas[s]["arab_share"] is not None]
        if not sh:
            return None, None
        m = statistics.mean(sh)
        return m >= 0.5, round(m, 3)

    # stations
    stations = {}
    summary = {}
    for e in R.ELECTIONS:
        b = site_b[e]
        cols = b["cols"]
        arab_idx = [6 + cols.index(p) for p in R.ARAB_LISTS[e] if p in cols]
        sa_of = collections.defaultdict(set)
        with open(os.path.join(ballots_dir, f"{e.lower()}.csv"), encoding="utf-8-sig") as f:
            for d in csv.DictReader(f):
                c = d["locality_code"] or d["source_locality_code"]
                if d["is_envelope"] == "True" or not c.isdigit() or int(c) not in scope:
                    continue
                if d["stat_area_yishuv_stat"]:
                    sa_of[(int(c), d["source_kalpi"])].add(int(d["stat_area_yishuv_stat"]))
        st = []
        agg = collections.defaultdict(lambda: collections.Counter())
        for row in b["rows"]:
            code, kalpi, sc, elig, voters, valid = row[:6]
            if code not in scope:
                continue
            arab_votes = sum(row[i] for i in arab_idx)
            vote_arab = sc % 10 == 1
            stats = sorted(sa_of.get((code, str(kalpi)), ()))
            area_arab, share = area_class(stats)
            st.append([code, kalpi, elig, valid, arab_votes, int(vote_arab), stats,
                       None if area_arab is None else int(area_arab), share])
            k = f"vote_{'arab' if vote_arab else 'other'}|area_{'none' if area_arab is None else 'arab' if area_arab else 'other'}"
            a = agg[code]
            a[f"{k}|stations"] += 1
            a[f"{k}|eligible"] += elig
            a[f"{k}|valid"] += valid
            a[f"{k}|arab_list_votes"] += arab_votes
        stations[e] = st
        summary[e] = {str(c): dict(sorted(v.items())) for c, v in sorted(agg.items())}
    return scope, areas, stations, summary


def station_disagreements(stations, core):
    names = {L["code"]: L["name"] for L in core["localities"]}
    out = {}
    for e, st in stations.items():
        rows = []
        for code, kalpi, elig, valid, arab_votes, vote_arab, stats, area_arab, share in st:
            if area_arab is not None and area_arab != vote_arab:
                rows.append({"code": code, "name": names.get(code), "kalpi": kalpi, "eligible": elig,
                             "arab_list_share": round(arab_votes / valid, 3) if valid else None,
                             "class_by_vote": "arab" if vote_arab else "other",
                             "class_by_area": "arab" if area_arab else "other",
                             "areas_2011": stats, "area_arab_share": share})
        out[e] = rows
    return out


def city_totals(summary):
    """Per election and locality: the Arab stations by each rule (stations, eligible, Arab-list votes)."""
    out = {}
    for e, per in summary.items():
        out[e] = {}
        for code, v in per.items():
            def tot(pred, field):
                return sum(n for k, n in v.items() if k.endswith("|" + field) and pred(k))
            rules = {"by_vote": lambda k: k.startswith("vote_arab"),
                     "by_area": lambda k: "|area_arab|" in k,
                     "by_both": lambda k: k.startswith("vote_arab") and "|area_arab|" in k}
            all_arab = tot(lambda k: True, "arab_list_votes")
            rec = {"stations": tot(lambda k: True, "stations"), "eligible": tot(lambda k: True, "eligible"),
                   "arab_list_votes": all_arab}
            for name, pred in rules.items():
                valid, arab = tot(pred, "valid"), tot(pred, "arab_list_votes")
                rec[name] = {"stations": tot(pred, "stations"), "eligible": tot(pred, "eligible"), "valid": valid,
                             "arab_list_votes": arab,
                             # how much of the city's Arab-list vote these stations hold, and how Arab they vote
                             "share_of_city_arab_list_votes": round(arab / all_arab, 3) if all_arab else None,
                             "arab_list_share_inside": round(arab / valid, 3) if valid else None}
            nodata = lambda k: "|area_none|" in k
            rec["no_area_data"] = {"stations": tot(nodata, "stations"), "eligible": tot(nodata, "eligible")}
            out[e][code] = rec
    return out


def dump_rows(path, head, fields, rows):
    """JSON with one row per line (readable diffs)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("{\n")
        for k, v in head.items():
            f.write(f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)},\n")
        f.write(f"\"fields\": {json.dumps(fields, ensure_ascii=False)},\n\"rows\": [\n")
        f.write(",\n".join(json.dumps([r.get(k) for k in fields], ensure_ascii=False) for r in rows))
        f.write("\n]\n}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fetch", action="store_true", help="download the pinned copies into --cache first")
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--bycode", help="CBS locality file (bycodeYYYY.xlsx)")
    ap.add_argument("--bycode-check", help="an earlier year's locality file, independent copy")
    ap.add_argument("--census", help="2022 census, localities and statistical areas (CSV)")
    ap.add_argument("--sa2011", help="statistical areas 2011 (GeoJSON zip)")
    ap.add_argument("--sa2022", help="statistical areas 2022 (GeoJSON zip)")
    ap.add_argument("--localities", default=os.path.join(ROOT, "data", "raw", "mirror", "geographies", "localities_2022.zip"))
    ap.add_argument("--ballots", default=os.path.join(ROOT, "data", "raw", "mirror", "ballots"))
    ap.add_argument("--out", default=REF)
    a = ap.parse_args()
    if a.fetch:
        got = fetch(a.cache)
        a.bycode = a.bycode or got["bycode2024"]
        a.bycode_check = a.bycode_check or got["bycode2023"]
        a.census = a.census or got["census2022"]
        a.sa2011 = a.sa2011 or got["sa2011"]
        a.sa2022 = a.sa2022 or got["sa2022"]
    if not a.bycode:
        raise SystemExit("--bycode (or --fetch) is required")

    census = read_census(a.census) if a.census else None
    loc_polys = None
    if a.localities and os.path.exists(a.localities):
        loc_polys = {int(f["properties"]["locality_code"]): rings_of(f["geometry"])
                     for f in read_geojson_zip(a.localities)}
    meta, locs, coord_check = build_localities(a.bycode, census, loc_polys)
    check_locs = build_localities(a.bycode_check, None, None)[1] if a.bycode_check else None
    core = json.load(open(os.path.join(SITE_DATA, "core.json"), encoding="utf-8"))
    sources = {"bycode": provenance(a.bycode, "bycode2024"),
               "bycode_check": provenance(a.bycode_check, "bycode2023"),
               "census2022": provenance(a.census, "census2022"),
               "statistical_areas_2011": provenance(a.sa2011, "sa2011"),
               "statistical_areas_2022": provenance(a.sa2022, "sa2022")}
    if sources["bycode"]:
        sources["bycode"].update(file_modified=meta["modified"], sheet_rows=meta["sheet_rows"],
                                 population_column=meta["pop_header"])
    os.makedirs(a.out, exist_ok=True)
    head = {
        "title": "קובץ היישובים של הלמ״ס",
        "source": sources["bycode"],
        "census2022": sources["census2022"],
        "notes": {
            "religion": "דת יישוב בקובץ: 1 יהודי, 2 ערבי (כולל דרוזים וצ׳רקסים), 3 שבט בדואי, 4 מעורב (לפי הנתונים; ההגדרות ב-intro.pdf)",
            "group": "religion כמילה: jewish / arab / bedouin_tribe / mixed",
            "arab_share": "ערבים / סך הכל ישראלים, בשנת הקובץ",
            "population": meta["pop_header"],
            "itm_x/itm_y": "שדה הקואורדינטות של הלמ״ס (רשת ישראל החדשה, מטרים)",
            "lat/lng": "המרה ל-WGS84 (טרנסוורס מרקטור הפוך ו-7 פרמטרים, EPSG:2039)",
            "census2022_religion": "הדת השכיחה ביישוב במפקד 2022 (לא הרכב)",
        },
    }
    dump_rows(os.path.join(a.out, "cbs_localities.json"), head, OUT_FIELDS, locs)

    report = classify_compare(locs, check_locs, os.path.join(REF, "arab_localities.csv"), core, census)
    report = {"sources": sources, "coordinates_check": coord_check, **report}
    if census and a.sa2011 and a.sa2022 and os.path.isdir(a.ballots):
        scope, areas, stations, summary = mixed_areas(census, a.sa2011, a.sa2022, a.ballots, core, locs)
        dis = station_disagreements(stations, core)
        totals = city_totals(summary)
        report["mixed_city_stations"] = {
            "rule_by_vote": f"build_data.py: median Arab-list share over the elections >= {R.ARAB_BOX_MIN_SHARE}",
            "rule_by_area": "mean Arab share of the station's 2011 statistical areas >= 0.5 (2022 census modal religion, density-weighted overlay)",
            "localities": sorted(scope),
            "totals": totals,
            "disagreements": dis,
            "disagreement_counts": {e: len(v) for e, v in dis.items()},
        }
        with open(os.path.join(a.out, "cbs_mixed_areas.json"), "w", encoding="utf-8") as f:
            f.write("{\n")
            f.write(f"\"sources\": {json.dumps({k: sources[k] for k in ('census2022', 'statistical_areas_2011', 'statistical_areas_2022')}, ensure_ascii=False)},\n")
            f.write("\"note\": \"areas: 2011 statistical area (yishuv_stat) -> Arab share estimated from the 2022 census; stations: per election [code, kalpi, eligible, valid, arab_list_votes, arab_by_vote, areas_2011, arab_by_area, area_arab_share]\",\n")
            f.write("\"areas\": {\n" + ",\n".join(f"{json.dumps(str(k))}: {json.dumps(v, ensure_ascii=False)}"
                                                  for k, v in sorted(areas.items())) + "\n},\n")
            f.write("\"stations\": {\n" + ",\n".join(
                f"{json.dumps(e)}: [\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in st) + "\n]"
                for e, st in stations.items()) + "\n}\n}\n")
    with open(os.path.join(a.out, "cbs_validation.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
        f.write("\n")

    # console summary
    lv = report["list_vs_cbs"]
    cv = report["core_vs_cbs"]
    print(f"CBS file: {len(locs)} localities ({report['religion_codes']['counts']}), source {sources['bycode']['copy']}")
    print(f"arab_localities.csv vs CBS: {lv['rows']} rows, {len(lv['disagreements'])} disagreements")
    print(f"CBS Arab/Bedouin/mixed localities not in the list: {len(report['cbs_nonjewish_not_in_list'])} "
          f"(in election results: {sum(1 for m in report['cbs_nonjewish_not_in_list'] if m['in_election_results'])})")
    print(f"core.json vs CBS: {cv['localities']} localities, {len(cv['disagreements'])} disagreements, "
          f"{len(cv['not_in_cbs_file'])} not in the CBS file")
    print(f"segments vs census 2022 religion: {len(report['segments_vs_census2022_religion']['disagreements'])} disagreements")
    if coord_check:
        print(f"coordinates: {coord_check['points_inside_polygon']} inside their polygon, {coord_check['points_outside']} outside")
    if "mixed_city_stations" in report:
        print("stations where the area rule and the vote rule differ:", report["mixed_city_stations"]["disagreement_counts"])


if __name__ == "__main__":
    main()
