#!/usr/bin/env python3
"""Fetch the CBS list of localities with their district (מחוז) and sub-district (נפה), for the locality pages.

    python3 pipeline/fetchers/cbs_localities.py --out DIR

The build container cannot reach cbs.gov.il or data.gov.il; GitHub's runners can. Run from
.github/workflows/fetch.yml on the request {"workflow": "fetch", "what": "cbs_localities"} (docs/ELECTION_DAY.md,
"בקשות דרך ops-control"); the files land on the ops-reports branch under reports/fetch/cbs_localities/<stamp>/ and
reports/fetch/cbs_localities/latest/.

What it asks for (none of the addresses could be checked from the build container):
  * the CBS file "רשימת היישובים בישראל ונתוניהם" (bycode<year>.xlsx, newest first): one row per locality with its
    code (סמל יישוב) and its district and sub-district codes (מחוז, נפה);
  * data.gov.il's locality list (datastore resource 5c78e9fa-…, "רשימת ישובים": the sub-district code and name per
    locality), and data.gov.il's catalogue (package_search) for other locality datasets, whose datastore resources
    are fetched too (at most MAX_RESOURCES).
What it writes: DIR/files/<name> (each body as it came), DIR/districts.json ({"<code>": {"district", "district_code",
"subdistrict", "subdistrict_code"}, "source": url, "method": ...}: the CBS file's district column when it was read,
else the district of the sub-district code), DIR/summary.json and DIR/summary.md (per URL the HTTP status, type, size
and SHA-256; the columns found; how many of site/data/core.json's localities have a district). The district names
are the CBS district codes 1-7; the round that consumes this checks them against the file's own legend.
Never raises on a single URL; exit 0 unless the script itself crashed.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORE = os.path.join(ROOT, "site", "data", "core.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
BYCODE = [f"https://www.cbs.gov.il/he/publications/doclib/2019/ishuvim/bycode{y}.xlsx" for y in (2024, 2023, 2022, 2021)]
DATAGOV = "https://data.gov.il/api/3/action/"
RESOURCE = "5c78e9fa-c2e2-4771-93ff-7f400a12f7ba"   # "רשימת ישובים" (Ministry of the Interior / CBS codes)
QUERIES = ("רשימת ישובים", "יישובים", "localities")
MAX_RESOURCES = 4
TIMEOUT = 60
MAX_FILE = 40_000_000
DISTRICTS = {1: "ירושלים", 2: "הצפון", 3: "חיפה", 4: "המרכז", 5: "תל אביב", 6: "הדרום", 7: "יהודה והשומרון"}


class Fetcher:
    def __init__(self, out):
        self.files = os.path.join(out, "files")
        os.makedirs(self.files, exist_ok=True)
        self.entries = []

    def get(self, url, name, why):
        entry = {"url": url, "why": why}
        self.entries.append(entry)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "he-IL,he;q=0.9"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read(MAX_FILE + 1)
                entry.update(status=r.status, type=r.headers.get("Content-Type", ""), final=r.geturl())
        except urllib.error.HTTPError as exc:
            entry.update(status=exc.code, error=f"HTTP {exc.code}")
            return None
        except Exception as exc:   # one address failing never stops the run
            entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
            return None
        if len(body) > MAX_FILE:
            entry["error"] = "too large"
            return None
        entry.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        safe = re.sub(r"[^\w.-]+", "_", name)[:120]
        with open(os.path.join(self.files, safe), "wb") as f:
            f.write(body)
        entry["file"] = "files/" + safe
        return body


# ------------------------------------------------------------------ the CBS workbook (xlsx, read with zipfile)
def xlsx_rows(body):
    """Every sheet's rows as lists of strings: {sheet name: rows}."""
    z = zipfile.ZipFile(io.BytesIO(body))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
    book = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = {}
    for sh in book.find("m:sheets", ns):
        path = target.get(sh.get("{%s}id" % ns["r"]), "")
        path = path.lstrip("/") if path.startswith("/") else "xl/" + path   # absolute in the package, or under xl/
        if path not in z.namelist():
            continue
        rows = []
        for row in ET.fromstring(z.read(path)).iter("{%s}row" % ns["m"]):
            cells = {}
            for c in row.findall("m:c", ns):
                ref = re.match(r"([A-Z]+)", c.get("r", "A"))
                col = 0
                for ch in ref.group(1):
                    col = col * 26 + ord(ch) - 64
                v = c.find("m:v", ns)
                if c.get("t") == "s" and v is not None:
                    text = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter("{%s}t" % ns["m"]))
                else:
                    text = v.text if v is not None else ""
                cells[col - 1] = (text or "").strip()
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        out[sh.get("name")] = rows
    return out


def as_int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def from_bycode(sheets):
    """{code: {...}} from the sheet whose header names סמל יישוב and מחוז; and the columns it found."""
    for name, rows in sheets.items():
        for i, row in enumerate(rows[:15]):
            norm = [re.sub(r"\s+", " ", c) for c in row]
            code_c = next((j for j, c in enumerate(norm) if "סמל" in c and "ישוב" in c.replace("יי", "י")), None)
            dist_c = next((j for j, c in enumerate(norm) if c.startswith("מחוז")), None)
            if code_c is None or dist_c is None:
                continue
            sub_c = next((j for j, c in enumerate(norm) if c.startswith("נפה")), None)
            out = {}
            for r in rows[i + 1:]:
                code = as_int(r[code_c]) if code_c < len(r) else None
                d = as_int(r[dist_c]) if dist_c < len(r) else None
                if code is None or d is None:
                    continue
                rec = {"district_code": d, "district": DISTRICTS.get(d, "")}
                if sub_c is not None and sub_c < len(r) and as_int(r[sub_c]) is not None:
                    rec["subdistrict_code"] = as_int(r[sub_c])
                out[str(code)] = rec
            return out, {"sheet": name, "header_row": i, "columns": [c for c in norm if c][:40]}
    return {}, {"sheets": list(sheets)}


# ------------------------------------------------------------------ data.gov.il (CKAN)
def from_datastore(body):
    """{code: {...}} from a datastore_search answer with a locality code and a sub-district column."""
    d = json.loads(body.decode("utf-8"))
    recs = (d.get("result") or {}).get("records") or []
    if not recs:
        return {}, {"records": 0}
    keys = list(recs[0])
    code_k = next((k for k in keys if "סמל" in k and "ישוב" in k.replace("יי", "י")), None)
    subc_k = next((k for k in keys if "סמל" in k and "נפה" in k), None)
    subn_k = next((k for k in keys if "נפה" in k and "סמל" not in k), None)
    out = {}
    if code_k:
        for r in recs:
            code = as_int(r.get(code_k))
            if code is None:
                continue
            rec = {}
            sc = as_int(r.get(subc_k)) if subc_k else None
            if sc is not None:
                rec["subdistrict_code"] = sc
                dc = sc // 10 if sc >= 10 else None
                if dc in DISTRICTS:
                    rec.update(district_code=dc, district=DISTRICTS[dc])
            if subn_k and str(r.get(subn_k) or "").strip():
                rec["subdistrict"] = str(r[subn_k]).strip()
            if rec:
                out[str(code)] = rec
    return out, {"records": len(recs), "fields": keys[:40], "code": code_k, "subdistrict_code": subc_k, "subdistrict": subn_k}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = args.out
    os.makedirs(out, exist_ok=True)
    F = Fetcher(out)
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    found = {}     # source url -> (records, info)

    for url in BYCODE:
        body = F.get(url, url.rsplit("/", 1)[-1], "CBS locality file (district per locality)")
        if not body:
            continue
        try:
            recs, info = from_bycode(xlsx_rows(body))
        except Exception as exc:
            F.entries[-1]["parse_error"] = f"{type(exc).__name__}: {exc}"[:300]
            continue
        F.entries[-1]["parsed"] = info
        if recs:
            found[url] = (recs, "CBS file: district column (מחוז)")
            break

    resources = [RESOURCE]
    for q in QUERIES:
        url = DATAGOV + "package_search?rows=20&q=" + urllib.parse.quote(q)
        body = F.get(url, f"package_search_{len(F.entries)}.json", f"data.gov.il catalogue: {q}")
        if not body:
            continue
        try:
            for pkg in json.loads(body.decode("utf-8")).get("result", {}).get("results", []):
                text = " ".join(str(pkg.get(k) or "") for k in ("title", "name", "notes"))
                if not re.search(r"ישוב|יישוב|localit", text, re.I):
                    continue
                for res in pkg.get("resources", []):
                    if res.get("datastore_active") and res.get("id") not in resources:
                        resources.append(res["id"])
        except Exception as exc:
            F.entries[-1]["parse_error"] = f"{type(exc).__name__}: {exc}"[:300]
    for rid in resources[: MAX_RESOURCES + 1]:
        url = f"{DATAGOV}datastore_search?resource_id={rid}&limit=5000"
        body = F.get(url, f"datastore_{rid}.json", "data.gov.il datastore: locality list")
        if not body:
            continue
        try:
            recs, info = from_datastore(body)
        except Exception as exc:
            F.entries[-1]["parse_error"] = f"{type(exc).__name__}: {exc}"[:300]
            continue
        F.entries[-1]["parsed"] = info
        if recs and any("district" in r for r in recs.values()):
            found[url] = (recs, "data.gov.il: sub-district code (סמל נפה), whose first digit is the district")

    # the CBS file first; data.gov.il fills in sub-district names and any code the file lacks
    merged, source, method = {}, "", ""
    for url, (recs, how) in found.items():
        if not source:
            source, method = url, how
        for code, rec in recs.items():
            m = merged.setdefault(code, {})
            for k, v in rec.items():
                m.setdefault(k, v)
    disagree = []
    if len(found) > 1:
        (u1, (a, _)), (u2, (b, _)) = list(found.items())[:2]
        disagree = [c for c in a if c in b and a[c].get("district_code") and b[c].get("district_code")
                    and a[c]["district_code"] != b[c]["district_code"]]

    cover = None
    try:
        core = json.load(open(CORE, encoding="utf-8"))
        codes = [str(l["code"]) for l in core["localities"]]
        missing = [c for c in codes if not merged.get(c, {}).get("district")]
        cover = {"localities": len(codes), "with_district": len(codes) - len(missing), "missing": missing[:60]}
    except Exception as exc:
        cover = {"error": f"core.json: {type(exc).__name__}: {exc}"[:200]}

    if merged:
        with open(os.path.join(out, "districts.json"), "w", encoding="utf-8") as f:
            json.dump({"source": source, "method": method, "fetched": started, "sources": list(found),
                       **dict(sorted(merged.items(), key=lambda kv: int(kv[0])))}, f, ensure_ascii=False, indent=0)
    summary = {"fetcher": "cbs_localities", "started": started, "requests": F.entries, "sources_used": list(found),
               "localities_with_district": len(merged), "district_disagreements": disagree[:60], "core_coverage": cover,
               "district_names": DISTRICTS}
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    lines = ["# cbs_localities", "", f"Started {started} (UTC).", "",
             "| URL | status | bytes | note |", "|---|---|---|---|"]
    for e in F.entries:
        note = e.get("error") or e.get("parse_error") or (json.dumps(e.get("parsed"), ensure_ascii=False)[:200] if e.get("parsed") else "")
        lines.append(f"| {e['url']} | {e.get('status', '-')} | {e.get('bytes', '-')} | {note.replace('|', '/')} |")
    lines += ["", f"Localities with a district: {len(merged)} (source: {source or 'none'}; {method or '-'}).",
              f"Coverage of site/data/core.json: {json.dumps(cover, ensure_ascii=False)[:600]}",
              f"District disagreements between the two sources: {len(disagree)} {disagree[:20]}", ""]
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
