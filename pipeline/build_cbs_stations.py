#!/usr/bin/env python3
"""Build pipeline/reference/cbs_stations_2026.json: the CBS list of the 2026 polling stations (קלפיות אוקטובר 2026),
each with its 2022 statistical area and its "stable" flag, and for the mixed cities a class source for every 2026
station number. Standard library only (build_cbs.read_xlsx), so the committed JSON is read and checked anywhere.

Input: --src DIR, the files/ folder of a pipeline/fetchers/cbs.py run as fetch.yml pushes it to the ops-reports
branch (reports/fetch/cbs/<stamp>/files; data/raw is not committed, and cbs.gov.il does not answer this container):
  kalpi_October2026_stat2022.xlsx      every 2026 station, as CBS numbers it (base integers) -> its 2022 area
  Stable_kalpi_october_2026.xlsx       the "stable" stations: no boundary, merge, split or voter move from 7.7.2022
                                       to 30.5.2026 (the Aviv register closed before K25 and before K26)
  k25_kalpi_to_stat2011.xlsx           every 2022 CBS station -> its 2011 area (places the 2022 CEC groups)
  stat2022_to_stat2011.xlsx            CBS's key from the 2022 areas to their 2011 parent area(s)
  census2022_localities_statareas.csv  the census 2022 modal religion of every 2022 area unit
  ReadMe_Kalpi_October2026_Stat2022.pdf, ReadMe_Stable_Kalpi_October2026.pdf   (digests recorded only)
  site/data/ballots_K25.json (committed; its SHA-256 is recorded: it feeds the area prior) and arab_day_2022.json
  (the ten mixed_arab codes). summary.json next to files/ gives each file's catalogue time.
Every file is pinned by SHA-256 (PINS): a file that differs stops the build unless --accept-new, which prints the
new digest (and reports the counts below instead of asserting them).
--analog adds the hold-out test of the mixed-city class rules on 2019-2022 (k21..k24_kalpi_to_stat2011.xlsx,
k25_stable_kalpi.xlsx, Stable_kalp_March2021 / March2020 / September2019.xlsx, site/data/ballots_K21..K25.json),
and keeps its table in checks.analog.

Run: python3 pipeline/build_cbs_stations.py --src <ops-reports>/reports/fetch/cbs/20261017-0154/files --analog
     (from a checkout: git worktree add /tmp/ops origin/ops-reports, then --src /tmp/ops/reports/fetch/cbs/...).
     Two runs give the same bytes; python3 pipeline/test_live.py checks the committed file without the raw files.

Output (sorted keys, compact):
  sources[]   file, role, bytes, sha256, the catalogue's modified time, the HTTP Last-Modified, the xlsx's own
              modified stamp, the ops-reports stamp;
  caveats[]   what the file cannot do (the CEC rebalances stations after July; the Arab localities missing; the
              numbering);
  stations    {code: {n, stable, areas?, nums?}}: n = the 2026 stations in the CBS file (0 for a locality only on the
              stable list), stable = the stable numbers, areas = {2022 area: numbers} for the localities divided into
              more than one area (the rest are area 1), nums = the numbers where they are not 1..n. Numbers are
              written as runs: an int, or [first, last] for consecutive ones;
  mixed       {code: {number: {a22, stable, k25, share, census}}} for the ten mixed_arab codes, every 2026 number:
              a22 its 2022 area; k25 = the number was a 2022 CEC station group (its 2022 class then decides, as today);
              share = for the others, the area prior: the eligible-weighted share of the 2022 CEC groups in
              arab_turnout.arab_boxes among the groups of its area's 2011 parent(s), a group (code, X) placed by CBS's
              2022 station X (k25_kalpi_to_stat2011; the CEC merges CBS stations into groups, so the absorbed ones are
              not placed), several parents pooled; null where no 2022 group lies there; census = the modal religion
              of its 2022 census unit (or null);
  checks      the counts, asserted for the pinned files, and the analog table (--analog).

The CBS numbers are not the CEC's: the CEC merges CBS stations and splits the merged register evenly over X.1..X.n
(K25: 4,802 CBS numbers never appear as a CEC base number), so a CEC base number X is read as CBS station X and the
stations it absorbed are not identifiable. The ReadMe adds that the CEC balances stations after July, which changes
their numbers, "so the station data in the CEC results file cannot be fully linked to this file". Hence a fallback
for a number not used in 2022, never a replacement of the 2022 classification; arab_turnout.arab_section reads
`share` only behind live_config "mixed_area_class" (off by default: the reverse analog K25->K24 is worse by 0.0014).
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arab_turnout as AT  # noqa: E402
import build_cbs as BC  # noqa: E402
import registry as R  # noqa: E402

ROOT = BC.ROOT
OUT = os.path.join(BC.REF, "cbs_stations_2026.json")
SITE_DATA = BC.SITE_DATA
STAMP_RE = re.compile(r"^\d{8}-\d{4}$")

# file -> (role, SHA-256 of the runner fetch of 16.10.2026, ops-reports reports/fetch/cbs/20261017-0154)
PINS = {
    "kalpi_October2026_stat2022.xlsx": ("stations", "d984da021eb50c9a91e63d0cc50a78af73f3e0df2f9ccc1d898fb33ec2d702c8"),
    "Stable_kalpi_october_2026.xlsx": ("stable", "da9f62f6dc2257cffda4173da2764285a45aa4c236bf3a7ffd3a53d436535126"),
    "k25_kalpi_to_stat2011.xlsx": ("prior", "2b78483f0e3f8999d346b9bc8561af36cf9ffb6838c43c9b9f726795c3bb4387"),
    "stat2022_to_stat2011.xlsx": ("prior", "9a80fee5ac4775323a53b86f1f329a8ddce24c5e2ff271ded52fd2d583eead89"),
    "census2022_localities_statareas.csv": ("census", "9d04fca6f04b40aece6bf48baf137e011a1af3acf8e673d10b639635be10a4f1"),
    "ReadMe_Kalpi_October2026_Stat2022.pdf": ("readme", "5826f717c98f284a76d979cfa3e8ac3f681f904b20324732b47c3a3b44b03120"),
    "ReadMe_Stable_Kalpi_October2026.pdf": ("readme", "890f444247723e645822198838aeaccdf6f6784c90b1fa42162b342b42f0acee"),
}
ANALOG_PINS = {
    "k21_kalpi_to_stat2011.xlsx": ("analog", "9d3bcf308de1d885a4cc3d799cea6c1d532aa563c073db1fc71cbc92b74d7056"),
    "k22_kalpi_to_stat2011.xlsx": ("analog", "6f562be2eecde50dc7e65ed9195f0702d62e33bbb11e43cd6852029566a29fa3"),
    "k23_kalpi_to_stat2011.xlsx": ("analog", "6b0f478d3c061c520f4e24bd18f92c89373a3944a264972409b5d7b82de01caf"),
    "k24_kalpi_to_stat2011.xlsx": ("analog", "cae1e105ac8c5313bbc51e487091073b1e4917df6b00ac438af6f4b4e8d96e2b"),
    "k25_stable_kalpi.xlsx": ("analog", "67c3377a930584d1dcf1686a65c1259ec6ae0c2b4254cf4647d096318f739de4"),
    "Stable_kalp_March2021.xlsx": ("analog", "cf6d1f57aa64726313076a53bba1d2df5006cacec8bc8a1a7ef0adb8d3d18ff2"),
    "Stable_kalp_March2020.xlsx": ("analog", "b981ae6fc255253f49cfbd337ae5e576d703cd58fb31848f7fbdf4baaef9d850"),
    "Stable_kalp_September2019.xlsx": ("analog", "a5626abdfd7afec62a1c3845126b3e8da0cce487f247cded81e33ab603925ce0"),
}
# what the pinned files hold (asserted; with --accept-new and another file, reported instead)
EXPECT = {"stations": 11467, "localities": 1217, "stable": 6719, "stable_localities": 1064,
          "multi_area_localities": 95, "multi_area_pairs": 2334}
# the hold-out pairs: base election -> new election, the CBS crosswalks of both, the new election's stable list
# (stable from the base's register to the new one's). K25->K24 and K25->K23 run backwards: the base is fixed at 2022
# and an earlier election plays the new one, as the live code reads 2026 against 2022.
PAIRS = [("K24", "K25", "k24_kalpi_to_stat2011.xlsx", "k25_kalpi_to_stat2011.xlsx", "k25_stable_kalpi.xlsx"),
         ("K23", "K24", "k23_kalpi_to_stat2011.xlsx", "k24_kalpi_to_stat2011.xlsx", "Stable_kalp_March2021.xlsx"),
         ("K22", "K23", "k22_kalpi_to_stat2011.xlsx", "k23_kalpi_to_stat2011.xlsx", "Stable_kalp_March2020.xlsx"),
         ("K21", "K22", "k21_kalpi_to_stat2011.xlsx", "k22_kalpi_to_stat2011.xlsx", "Stable_kalp_September2019.xlsx"),
         ("K25", "K24", "k25_kalpi_to_stat2011.xlsx", "k24_kalpi_to_stat2011.xlsx", "Stable_kalp_March2021.xlsx"),
         ("K25", "K23", "k25_kalpi_to_stat2011.xlsx", "k23_kalpi_to_stat2011.xlsx", "Stable_kalp_March2020.xlsx")]
SKIP_KEY_NAME = "מפתח"     # stat2022_to_stat2011 order 4 (Ashdod 411): the name cell reads "מפתח", not a locality
# the census modal religion (ReligionHeb) in the mixed entries, in short: 2,552 entries
RELIGION_EN = {"יהודים": "jews", "מוסלמים": "muslims", "נוצרים": "christians", "דרוזים": "druze", "דת אחרת": "other"}
ARAB_MODAL = {RELIGION_EN[r] for r in BC.ARAB_RELIGIONS}


def runs(nums):
    """Sorted numbers as runs: 1, 2, 3, 5 -> [[1, 3], 5]."""
    out = []
    for n in sorted(nums):
        if out and isinstance(out[-1], list) and out[-1][1] == n - 1:
            out[-1][1] = n
        elif out and isinstance(out[-1], int) and out[-1] == n - 1:
            out[-1] = [out[-1], n]
        else:
            out.append(n)
    return out


def unruns(rs):
    """The inverse of runs()."""
    out = []
    for x in rs:
        out.extend(range(x[0], x[1] + 1) if isinstance(x, list) else [x])
    return out


# ---- inputs --------------------------------------------------------------------------------------

def summary_of(src):
    """{file: (catalogue modified time, HTTP Last-Modified)} and the ops-reports stamp, from the fetch's summary.json
    (next to files/); the stamp is the folder's name (reports/fetch/cbs/<stamp>), else the fetch's start in Israel
    time, which is how fetch.yml names it (for a copy of latest/)."""
    parent = os.path.dirname(os.path.abspath(src))
    path = os.path.join(parent, "summary.json")
    s = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    times = {}
    for it in s.get("items") or []:
        m = re.search(r"modified (\S+?)\s*$", it.get("note") or "")
        times[os.path.basename(it.get("path") or it.get("name") or "")] = (m.group(1) if m else None, it.get("last_modified"))
    stamp = os.path.basename(parent)
    if not STAMP_RE.match(stamp):
        stamp = None
        if s.get("started"):
            t = dt.datetime.fromisoformat(s["started"].replace("Z", "+00:00")).astimezone(AT.IL)
            stamp = t.strftime("%Y%m%d-%H%M")
    return times, stamp


def check_pins(src, pins, accept_new):
    """The SHA-256 of every pinned file; a missing file or another digest stops the build (exit 2) unless accept_new."""
    got, bad, missing = {}, [], []
    for name, (_, want) in pins.items():
        path = os.path.join(src, name)
        if not os.path.isfile(path):
            missing.append(name)
            continue
        got[name] = BC.sha256(path)
        if got[name] != want:
            bad.append(name)
            print(f"{name}: SHA-256 {got[name]} (pinned {want})", file=sys.stderr)
    if missing:
        print(f"refused: not in {src}: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)
    if bad and not accept_new:
        print("refused: the files differ from the pinned ones; check them and run again with --accept-new, then pin "
              "the new digests in PINS", file=sys.stderr)
        sys.exit(2)
    return got, bad


def data_rows(rows, first_header):
    """The rows under the header row whose first cell is `first_header` (any case) whose first cell is an int: the
    reader drops empty rows, so the header, not a row number, marks where the data starts."""
    i = next(i for i, r in enumerate(rows) if r and str(r[0] or "").strip().lower() == first_header.lower())
    return [r for r in rows[i + 1:] if r and isinstance(r[0], int)]


def read_stations26(path):
    """kalpi_October2026_stat2022 (data sheet 2): {(code, number): area 2022}, asserting yishuv_stat2022 = code x 10000
    + Stat2022 on every row and one row per (code, number)."""
    rows, modified = BC.read_xlsx(path, sheet=1)
    out = {}
    for r in data_rows(rows, "SEMEL_YISHUV"):
        code, kalpi, area, ys = r[0], r[2], r[3], r[4]
        if not all(isinstance(x, int) for x in (code, kalpi, area, ys)) or ys != code * 10000 + area:
            raise SystemExit(f"kalpi_October2026_stat2022: a row that does not read as code, name, number, area, "
                             f"code x 10000 + area: {r}")
        if (code, kalpi) in out:
            raise SystemExit(f"kalpi_October2026_stat2022: station {code}/{kalpi} twice")
        out[(code, kalpi)] = area
    return out, modified


def read_stable(path):
    """A CBS stable-station list (sheet 2) -> {(code, number)}. The 2026 list's header says (שם, סמל, קלפי) but its
    columns are (code, name, number); the earlier lists are (name, code, number) as their headers say. So the columns
    are found by type: the first int is the code, the second the number."""
    rows, modified = BC.read_xlsx(path, sheet=1)
    out = set()
    for r in rows:
        ints = [x for x in r if isinstance(x, int) and not isinstance(x, bool)]
        if len(ints) == 2 and any(isinstance(x, str) and x.strip() for x in r):
            if (ints[0], ints[1]) in out:
                raise SystemExit(f"{os.path.basename(path)}: stable station {ints[0]}/{ints[1]} twice")
            out.add((ints[0], ints[1]))
    return out, modified


def read_stable_counts(path):
    """The count sheet of a CBS stable-station file (sheet 3: name, code, stable stations) -> {code: count}."""
    rows, _ = BC.read_xlsx(path, sheet=2)
    return {r[1]: r[2] for r in rows if len(r) > 2 and isinstance(r[1], int) and isinstance(r[2], int)}


def read_crosswalk(path):
    """kNN_kalpi_to_stat2011 (sheet 2): {(code, CBS station number): 2011 area}."""
    rows, modified = BC.read_xlsx(path, sheet=1)
    out = {}
    for r in data_rows(rows, "semel_yishuv"):
        out[(r[0], r[2])] = r[3]
    return out, modified


def read_parents(path):
    """stat2022_to_stat2011 (sheet 1): {(code, 2022 area): {(code 2011, 2011 area), ...}}. The codes are strings
    ('0001', '322'); the row named "מפתח" (order 4, Ashdod 411, not a mixed city) is skipped."""
    rows, modified = BC.read_xlsx(path, sheet=0)
    par, skipped = collections.defaultdict(set), 0
    for r in rows:
        if not isinstance(r[0], int):
            continue                      # the English and Hebrew headers
        if str(r[2] or "").strip() == SKIP_KEY_NAME:
            skipped += 1
            continue
        par[(int(r[1]), int(r[4]))].add((int(r[6]), int(r[9])))
    return dict(par), skipped, modified


def ballots(eid):
    with open(os.path.join(SITE_DATA, f"ballots_{eid}.json"), encoding="utf-8") as f:
        return json.load(f)


def group_of(kalpi):
    return AT.kalpi_base(AT.kalpi_id(kalpi))


# ---- the 2026 table ------------------------------------------------------------------------------

def build(src, accept_new=False, analog=False):
    pins = dict(PINS, **(ANALOG_PINS if analog else {}))
    digests, changed = check_pins(src, pins, accept_new)
    times, stamp = summary_of(src)
    st26, mod26 = read_stations26(os.path.join(src, "kalpi_October2026_stat2022.xlsx"))
    stable, mod_st = read_stable(os.path.join(src, "Stable_kalpi_october_2026.xlsx"))
    stable_counts = read_stable_counts(os.path.join(src, "Stable_kalpi_october_2026.xlsx"))
    c25, mod25 = read_crosswalk(os.path.join(src, "k25_kalpi_to_stat2011.xlsx"))
    par, skipped, mod_key = read_parents(os.path.join(src, "stat2022_to_stat2011.xlsx"))
    _, units = BC.read_census(os.path.join(src, "census2022_localities_statareas.csv"))
    modified = {"kalpi_October2026_stat2022.xlsx": mod26, "Stable_kalpi_october_2026.xlsx": mod_st,
                "k25_kalpi_to_stat2011.xlsx": mod25, "stat2022_to_stat2011.xlsx": mod_key}
    b25 = ballots("K25")
    ballots25 = os.path.join(SITE_DATA, "ballots_K25.json")
    with open(os.path.join(SITE_DATA, "arab_day_2022.json"), encoding="utf-8") as f:
        mixed_codes = sorted({x["code"] for x in json.load(f)["localities"] if x["kind"] == "mixed_arab"})
    with open(os.path.join(SITE_DATA, "core.json"), encoding="utf-8") as f:
        locsec = {x["code"]: x["sector"] for x in json.load(f)["localities"]}

    # stations by locality
    by_loc = collections.defaultdict(dict)
    for (code, k), a in st26.items():
        by_loc[code][k] = a
    stable_by = collections.defaultdict(set)
    for code, k in stable:
        stable_by[code].add(k)
    stations, pairs, multi = {}, 0, 0
    for code in sorted(set(by_loc) | set(stable_by)):
        ks = by_loc.get(code, {})
        rec = {"n": len(ks), "stable": runs(stable_by.get(code, ()))}
        areas = collections.defaultdict(list)
        for k, a in ks.items():
            areas[a].append(k)
        if len(areas) > 1:
            rec["areas"] = {str(a): runs(v) for a, v in sorted(areas.items())}
            multi += 1
            pairs += len(areas)
        elif areas and set(areas) != {1}:
            rec["areas"] = {str(a): runs(v) for a, v in areas.items()}   # one area, not area 1 (none in 2026)
        elif ks and sorted(ks) != list(range(1, len(ks) + 1)):
            rec["nums"] = runs(ks)
        stations[str(code)] = rec
    counts = {"stations": len(st26), "localities": len(by_loc), "stable": len(stable),
              "stable_localities": len(stable_by), "multi_area_localities": multi, "multi_area_pairs": pairs,
              "multi_area_stations": sum(len(by_loc[int(c)]) for c, r in stations.items() if len(r.get("areas", {})) > 1),
              "single_area_localities": sum(1 for c, ks in by_loc.items() if len(set(ks.values())) == 1),
              "not_numbered_1_to_n": sum(1 for ks in by_loc.values() if sorted(ks) != list(range(1, len(ks) + 1))),
              "stable_not_in_file": len(stable - set(st26)),
              "stable_count_sheet": [len(stable_counts), sum(stable_counts.values())],
              "stable_count_sheet_not_listed": [sum(1 for c in stable_counts if c not in stable_by),
                                                sum(n for c, n in stable_counts.items() if c not in stable_by)],
              "stable_localities_not_in_file": sorted(set(stable_by) - set(by_loc))}
    if not changed:
        for k, v in EXPECT.items():
            if counts[k] != v:
                raise SystemExit(f"{k}: {counts[k]}, expected {v} in the pinned files")
    else:
        print("counts of the new files (not asserted):", json.dumps({k: counts[k] for k in EXPECT}), file=sys.stderr)

    # coverage of the Arab and Druze localities (K25 eligible voters)
    elig25 = collections.Counter()
    for r in b25["rows"]:
        elig25[r[0]] += r[3]
    cover = {}
    for sec in ("arab", "druze"):
        codes = [c for c in elig25 if locsec.get(c) == sec]
        inn = [c for c in codes if c in by_loc]
        cover[sec] = {"localities": len(codes), "in_file": len(inn),
                      "elig_share": round(sum(elig25[c] for c in inn) / sum(elig25[c] for c in codes), 3)}

    # the area prior from the 2022 CEC groups of the mixed cities
    arab = AT.arab_boxes(b25)
    g25 = collections.Counter()
    for r in b25["rows"]:
        if r[0] in mixed_codes:
            g25[(r[0], group_of(r[1]))] += r[3]
    prior = collections.defaultdict(lambda: [0, 0])      # (code, 2011 area) -> [Arab groups' eligible, eligible]
    unplaced = 0
    for (code, x), e in g25.items():
        a11 = c25.get((code, x)) if isinstance(x, int) else None
        if a11 is None:
            unplaced += 1
            continue
        prior[(code, a11)][1] += e
        if (code, x) in arab:
            prior[(code, a11)][0] += e
    mixed, mc = {}, collections.Counter()
    none_cities = collections.Counter()
    for code in mixed_codes:
        m = {}
        for k, a22 in sorted(by_loc.get(code, {}).items()):
            unit = units.get((code, a22))
            rec = {"a22": a22, "stable": (code, k) in stable, "k25": (code, k) in g25, "share": None,
                   "census": RELIGION_EN.get(unit["religion"], unit["religion"]) if unit else None}
            if not rec["k25"]:
                ps = [prior[p] for p in sorted(par.get((code, a22), ())) if p in prior]
                den = sum(p[1] for p in ps)
                if den:
                    rec["share"] = round(sum(p[0] for p in ps) / den, 4)
            m[str(k)] = rec
            mc["numbers"] += 1
            if rec["k25"]:
                mc["k25"] += 1
                mc["k25_arab"] += (code, k) in arab
            elif rec["share"] is not None:
                mc["share"] += 1
                mc["share_arab"] += rec["share"] >= AT.ARAB_BOX_SHARE
            else:
                mc["none"] += 1
                if rec["census"] in ARAB_MODAL:
                    mc["none_arab_modal"] += 1
                    none_cities[str(code)] += 1
        mixed[str(code)] = m
    keys22 = [k for k in par if k[0] in mixed_codes]
    a26 = {(c, a) for c in mixed_codes for a in by_loc.get(c, {}).values()}
    counts["mixed"] = {**dict(mc), "none_arab_modal_by_code": dict(sorted(none_cities.items())),
                       "codes": mixed_codes, "areas22_in_key": len(keys22),
                       "areas22_in_key_with_parents_gt1": sum(1 for k in keys22 if len(par[k]) > 1),
                       "areas22_in_file": len(a26),
                       "areas22_in_file_with_parents_gt1": sum(1 for k in a26 if len(par.get(k, ())) > 1),
                       "areas22_in_file_without_parent": sum(1 for k in a26 if k not in par),
                       "groups22": len(g25), "groups22_not_placed": unplaced, "key_rows_skipped": skipped}
    counts["coverage"] = cover

    sources = []
    for name, (role, _) in sorted(pins.items()):
        path = os.path.join(src, name)
        cat, lm = times.get(name, (None, None))
        sources.append({"file": name, "role": role, "bytes": os.path.getsize(path), "sha256": digests[name],
                        "catalogue_modified": cat, "last_modified": lm, "xlsx_modified": modified.get(name),
                        "stamp": stamp})
    a = cover["arab"]
    d = cover["druze"]
    caveats = [
        "ReadMe (קובץ מעבר מקלפיות אוקטובר 2026): the file was prepared in July 2026; the CEC balances stations after "
        "that (איזון קלפיות), which changes their composition and numbers, so the station data in the CEC results file "
        "cannot be fully linked to this file.",
        f"The file covers only {a['in_file']} of the {a['localities']} Arab localities ({100 * a['elig_share']:.1f}% of "
        f"their K25 eligible voters) and {d['in_file']} of the {d['localities']} Druze localities; all nine mixed cities "
        "and almost every Jewish locality are in it. A locality missing from the file has not been abolished.",
        "Station numbers are CBS integers (no sub-stations). A CEC base number X (X, X.1, X.2 ...) is CBS station X; "
        "the CBS stations the CEC merged into a group are not identifiable from the numbers.",
        "Stable (ReadMe, Stable_kalpi_october_2026): not a collecting station, not in a non-locality (tribe, army camp), "
        "and no new boundary, merge or split, voter move or locality change from 7.7.2022 to 30.5.2026. Used as a flag "
        f"only; {counts['stable_count_sheet_not_listed'][0]} localities of its count sheet "
        f"({counts['stable_count_sheet_not_listed'][1]} stations, new settlements among them) are not on its list.",
        "census: the modal religion of the 2022 unit only (the census publishes no shares; small areas are merged "
        "units such as 122+121).",
    ]
    out = {"title": "הלמ״ס — קלפיות 2026 לפי אזור סטטיסטי 2022, קלפיות יציבות, וסיווג הקלפיות בערים המעורבות",
           "built_by": "pipeline/build_cbs_stations.py --src <ops-reports>/reports/fetch/cbs/<stamp>/files"
                       + (" --analog" if analog else ""),
           "format": "stations: {code: {n, stable, areas?, nums?}}, numbers as runs (an int or [first, last]); areas only "
                     "where a locality has more than one 2022 area (otherwise area 1); nums only where the numbers are "
                     "not 1..n. mixed: {code: {number: {a22, stable, k25, share, census}}}, census = the census modal religion "
                     "(ReligionHeb: jews יהודים, muslims מוסלמים, christians נוצרים, druze דרוזים, other דת אחרת)",
           "sources": sources, "ballots_K25_sha256": BC.sha256(ballots25), "caveats": caveats,
           "stations": stations, "mixed": mixed, "checks": counts}
    if analog:
        out["checks"]["analog"] = run_analog(src, mixed_codes, modified)
        for rec in sources:
            rec["xlsx_modified"] = modified.get(rec["file"])
    return out


# ---- the hold-out test ---------------------------------------------------------------------------

def groups(eid, codes):
    """{(code, base number): (Arab-list share >= .5, eligible, voters)} of an election's CEC station groups."""
    b = ballots(eid)
    cols = b["cols"]
    ia = [cols.index(c) for c in R.ARAB_LISTS[eid] if c in cols]
    g = collections.defaultdict(lambda: [0, 0, 0, 0])
    for r in b["rows"]:
        if r[0] not in codes:
            continue
        x = g[(r[0], group_of(r[1]))]
        x[0] += sum(r[6 + i] for i in ia)
        x[1] += r[5]
        x[2] += r[3]
        x[3] += r[4]
    return {k: (bool(v[1]) and v[0] / v[1] >= AT.ARAB_BOX_SHARE, v[2], v[3]) for k, v in g.items()}


def run_analog(src, codes, modified):
    """The mixed-city class rules on past pairs of elections, each new election's CEC groups classified from the
    base's, against the new election's own Arab-list majority (eligible-weighted over the ten mixed_arab codes):
      N         the class of the same (code, base number) in the base, else unclassified (today's rule);
      A         the area prior: the base's Arab groups' share of the eligible voters in the group's 2011 area (both
                elections' CBS crosswalks, station X for group X) >= .5;
      NS        N where the number is on the new election's CBS stable list, else A, else N;
      N_then_A  N, else A (the rule behind live_config "mixed_area_class").
    f1 (eligible-weighted precision and recall of the Arab groups; an unclassified Arab group is missed) and
    turnout_err = the turnout of the groups classed Arab - the turnout of the truly Arab ones."""
    table, ns_lost = {}, 0
    for base_e, new_e, cw_b, cw_n, st_n in PAIRS:
        gb, gn = groups(base_e, codes), groups(new_e, codes)
        cb, modified[cw_b] = read_crosswalk(os.path.join(src, cw_b))
        cn, modified[cw_n] = read_crosswalk(os.path.join(src, cw_n))
        sn, modified[st_n] = read_stable(os.path.join(src, st_n))
        prior = collections.defaultdict(lambda: [0, 0])
        for (c, n), (ar, e, _) in gb.items():
            a = cb.get((c, n))
            if a is None:
                continue
            prior[(c, a)][1] += e
            if ar:
                prior[(c, a)][0] += e

        def area(c, n):
            p = prior.get((c, cn.get((c, n))))
            return p[0] / p[1] >= AT.ARAB_BOX_SHARE if p and p[1] else None

        def num(c, n):
            return gb[(c, n)][0] if (c, n) in gb else None
        rules = {"N": num, "A": area,
                 "NS": lambda c, n: num(c, n) if ((c, n) in sn and (c, n) in gb) else
                 (area(c, n) if area(c, n) is not None else num(c, n)),
                 "N_then_A": lambda c, n: num(c, n) if (c, n) in gb else area(c, n)}
        te = sum(e for ar, e, _ in gn.values() if ar)
        tv = sum(v for ar, _, v in gn.values() if ar)
        row = {"true": {"groups": sum(1 for x in gn.values() if x[0]), "elig": te, "turnout": round(tv / te, 4)}}
        for name, f in rules.items():
            tp = fp = fn = unc = nunc = pe = pv = 0
            for (c, n), (ar, e, v) in gn.items():
                p = f(c, n)
                if p is None:
                    unc += e
                    nunc += 1
                    fn += e if ar else 0
                    continue
                if p:
                    tp += e if ar else 0
                    fp += 0 if ar else e
                    pe += e
                    pv += v
                elif ar:
                    fn += e
            prec = tp / (tp + fp) if tp + fp else 0
            rec = tp / (tp + fn) if tp + fn else 0
            row[name] = {"precision": round(prec, 3), "recall": round(rec, 3),
                         "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0,
                         "predicted_elig": pe, "turnout_err": round(pv / pe - tv / te, 4) if pe else None,
                         "unclassified_groups": nunc, "unclassified_elig": unc}
        ns_lost += row["NS"]["f1"] < row["N_then_A"]["f1"]
        table[f"{base_e}-{new_e}"] = row
    return {"pairs": table, "ns_lost_to_n_then_a": ns_lost, "of": len(PAIRS),
            "rule": "truth = the new election's own Arab-list share >= .5 per CEC group (code, base number); eligible-"
                    "weighted over the ten mixed_arab codes; K25-K24 and K25-K23 run backwards (base fixed at 2022, as "
                    "the live code reads 2026 against 2022)"}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", required=True,
                    help="the files/ folder of a CBS fetch on ops-reports (reports/fetch/cbs/<stamp>/files)")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--analog", action="store_true", help="also run the hold-out test of the mixed-city class rules")
    ap.add_argument("--accept-new", action="store_true", help="build from files whose SHA-256 differs from PINS")
    a = ap.parse_args(argv)
    out = build(a.src, accept_new=a.accept_new, analog=a.analog)
    text = dumps(out)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)
    c = out["checks"]
    print(f"{a.out}: {len(text.encode()):,} bytes; {c['stations']:,} stations in {c['localities']:,} localities, "
          f"{c['stable']:,} stable in {c['stable_localities']:,}; {c['multi_area_localities']} localities with "
          f"{c['multi_area_pairs']:,} (locality, area) pairs; mixed {json.dumps(c['mixed'], ensure_ascii=False)}")
    if a.analog:
        for k, row in c["analog"]["pairs"].items():
            print(f"  {k}: F1 N {row['N']['f1']:.3f} -> N_then_A {row['N_then_A']['f1']:.3f} (NS {row['NS']['f1']:.3f}, "
                  f"A {row['A']['f1']:.3f}); turnout error {row['N']['turnout_err']:+.4f} -> "
                  f"{row['N_then_A']['turnout_err']:+.4f}")
        print(f"  NS lost to N_then_A in {c['analog']['ns_lost_to_n_then_a']} of {c['analog']['of']}")


if __name__ == "__main__":
    main()
