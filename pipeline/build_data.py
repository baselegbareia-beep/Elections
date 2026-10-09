"""Build the dashboard data layer from official ballot-level results (K21–K25).

Input  : ballot-level CSVs (one row per kalpi / sub-kalpi, incl. the national
         envelope row), CBS locality polygons for coordinates, and the reviewed
         registry in registry.py.
Output : site/data/core.json and site/data/ballots_K2x.json.

Run    : python3 pipeline/build_data.py --src <dir with ballots/ and metadata/>
         (see pipeline/fetch_sources.py for where the files come from).

Every number shown on the dashboard is a sum of official CEC vote counts.
Derived quantities (sector splits, vote-transfer estimates) are labelled as
estimates in the UI and their rules are documented in docs/METHODOLOGY.md.
"""
import argparse
import collections
import statistics
import csv
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import registry as R  # noqa: E402
from bader_ofer import allocate  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SES_MIN_ELIG = 5000
# Large localities that are not local authorities: the SES file gives them their
# regional council's cluster (Hof HaCarmel, Mateh Yehuda, Mateh Binyamin), not their own.
SES_NOT_OWN = {"עתלית", "קיסריה", "צור הדסה", "כוכב יעקב"}


def read_ballots(src, e):
    path = os.path.join(src, "ballots", f"{e.lower()}.csv")
    with open(path, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames
        party_cols = fields[fields.index("is_envelope") + 1: fields.index("geography_assignment_status")]
        rows = []
        for d in rd:
            votes = {p: int(d[p] or 0) for p in party_cols}
            valid = int(d["valid_votes"])
            if sum(votes.values()) != valid:
                raise ValueError(f"{e} row {d['source_row_uid']}: party votes do not sum to valid votes")
            code = d["locality_code"] or d["source_locality_code"]
            rows.append({
                "env": d["is_envelope"] == "True",
                "code": int(code) if code and code.isdigit() else None,
                # non-geographic special boxes (army bases, prisons) carry a placeholder name
                "name": (d["locality_name"] if d["locality_name"] and not d["locality_name"].startswith("special:")
                         else d["source_locality_name"]).strip(),
                "kalpi": d["source_kalpi"],
                "elig": int(float(d["eligible_voters"] or 0)),
                "voters": int(d["actual_voters"]),
                "valid": valid,
                "invalid": int(d["invalid_votes"]),
                "votes": votes,
            })
    return party_cols, rows


OFFICIAL_META = {"סמל ועדה", "ברזל", "שם ישוב", "סמל ישוב", "קלפי", "מספר קלפי", "ריכוז", "שופט",
                 "בזב", "מצביעים", "פסולים", "כשרים", "ת. עדכון", "סמל קלפי", ""}
ENVELOPE_CODES = {"9999", "99999"}


def read_expb(path):
    """Read an official CEC ballot file (expb.csv) as published at
    media2X.bechirot.gov.il/files/expb.csv: cp1255 for K21–K24, UTF-8 with BOM
    from K25. Returns the same structure as read_ballots()."""
    raw = open(path, "rb").read()
    text = raw.decode("utf-8-sig") if raw.startswith(b"\xef\xbb\xbf") else raw.decode("cp1255")
    rd = csv.reader(text.splitlines())
    header = [h.strip() for h in next(rd)]
    party_cols = [h for h in header if h not in OFFICIAL_META]
    kalpi_col = "קלפי" if "קלפי" in header else "מספר קלפי"
    rows = []
    for rec in rd:
        if not rec or len(rec) < len(party_cols):
            continue
        d = dict(zip(header, rec))
        votes = {p: int(float(d[p] or 0)) for p in party_cols}
        valid = int(float(d["כשרים"] or 0))
        if sum(votes.values()) != valid:
            raise ValueError(f"{path}: row {rec[:5]} party votes do not sum to valid votes")
        code = d["סמל ישוב"].strip()
        voters = int(float(d["מצביעים"] or 0))
        rows.append({
            "env": code in ENVELOPE_CODES, "code": None if code in ENVELOPE_CODES else int(code),
            "name": d["שם ישוב"].strip(), "kalpi": d[kalpi_col].strip(),
            "elig": int(float(d["בזב"] or 0)), "voters": voters, "valid": valid,
            "invalid": int(float(d["פסולים"] or 0)), "votes": votes,
        })
    return party_cols, rows


def read_official(src):
    """Official national totals per list (parties.csv) and official seats."""
    totals = collections.defaultdict(dict)
    names = collections.defaultdict(dict)
    with open(os.path.join(src, "metadata", "parties.csv"), encoding="utf-8-sig") as f:
        for d in csv.DictReader(f):
            totals[d["election"]][d["source_column"]] = int(d["total_votes"])
            names[d["election"]][d["source_column"]] = d["list_name_he"]
    seats = collections.defaultdict(dict)
    mandates = os.path.join(src, "..", "election_mandates.csv")
    if os.path.exists(mandates):
        with open(mandates, encoding="utf-8-sig") as f:
            for d in csv.DictReader(f):
                seats[d["election"]][d["source_column"]] = int(d["mandates"])
    return totals, names, seats


def polygon_centroids(geojson_path):
    """Area-weighted centroid of each locality's largest polygon (WGS84)."""
    out = {}
    if not os.path.exists(geojson_path):
        return out
    if geojson_path.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(geojson_path) as z:
            name = next(n for n in z.namelist() if n.endswith(".geojson"))
            gj = json.loads(z.read(name).decode("utf-8"))
    else:
        with open(geojson_path, encoding="utf-8") as f:
            gj = json.load(f)
    for ft in gj["features"]:
        g = ft["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        best = None
        for poly in polys:
            ring = poly[0]
            a = cx = cy = 0.0
            for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
                c = x0 * y1 - x1 * y0
                a += c
                cx += (x0 + x1) * c
                cy += (y0 + y1) * c
            if a == 0:
                continue
            a *= 0.5
            cand = (abs(a), cx / (6 * a), cy / (6 * a))
            if best is None or cand[0] > best[0]:
                best = cand
        if best:
            out[int(ft["properties"]["locality_code"])] = (round(best[2], 4), round(best[1], 4))
    return out


def read_segments():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference", "arab_localities.csv")
    with open(path, encoding="utf-8-sig") as f:
        return {int(r["locality_code"]): r["segment"] for r in csv.DictReader(f)}


def norm_name(s):
    return "".join(ch for ch in s if ch.isalnum()).replace("וו", "ו").replace("יי", "י")


def build(src, polygons, ses_path, out_dir):
    totals, official_names, official_seats = read_official(src)
    centroids = polygon_centroids(polygons)
    ses = {}
    if ses_path and os.path.exists(ses_path):
        for r in json.load(open(ses_path, encoding="utf-8")):
            ses[norm_name(r["name"])] = r["cluster"]

    data = {}
    for e in R.ELECTIONS:
        official = next((p for p in (os.path.join(src, "official", f"{e.lower()}_expb.csv"),
                                     os.path.join(src, "..", "official", f"{e.lower()}_expb.csv"))
                         if os.path.exists(p)), "")
        data[e] = read_expb(official) if os.path.exists(official) else read_ballots(src, e)

    # ---- 1. Locality classification -------------------------------------
    segments = read_segments()
    arab_share = collections.defaultdict(lambda: [0, 0])
    loc_name = {}
    for e, (_, rows) in data.items():
        for r in rows:
            if r["env"] or r["code"] is None:
                continue
            loc_name[r["code"]] = r["name"]
            arab_share[r["code"]][0] += sum(r["votes"].get(p, 0) for p in R.ARAB_LISTS[e])
            arab_share[r["code"]][1] += r["valid"]
    loc_sector, loc_sub, loc_std = {}, {}, set()
    unlisted = []
    for code in arab_share:
        seg = segments.get(code)
        if seg:
            sector, subkey = R.SEGMENTS[seg]
            loc_sector[code], loc_sub[code] = sector, subkey
            if seg in R.STANDARD_SEGMENTS:
                loc_std.add(code)
        else:
            a, v = arab_share[code]
            if v and a / v >= R.ARAB_FALLBACK_MIN_SHARE:
                unlisted.append((code, loc_name[code], round(a / v, 3)))
                loc_sector[code], loc_sub[code] = "arab", "galilee"
                loc_std.add(code)
            else:
                loc_sector[code] = "jewish"
    tribal_point = (31.22, 34.93)

    # Vote-based box classes (Arab boxes in mixed cities and Jewish localities,
    # Haredi boxes) are fixed once per box across all five elections, so the
    # set does not change with each election's own vote: a box (locality, base
    # box number; sub-boxes merged) is Arab if the median Arab-list share over
    # the elections it appears in is >= ARAB_BOX_MIN_SHARE; same for Haredi.
    box_votes = collections.defaultdict(list)
    for e in R.ELECTIONS:
        acc = collections.defaultdict(lambda: [0, 0, 0])
        for r in data[e][1]:
            if r["env"] or r["code"] is None or loc_sector.get(r["code"], "jewish") in ("arab", "druze"):
                continue
            a = acc[(r["code"], kalpi_base(r["kalpi"]))]
            a[0] += sum(r["votes"].get(p, 0) for p in R.ARAB_LISTS[e])
            a[1] += r["votes"].get("ג", 0) + r["votes"].get("שס", 0)
            a[2] += r["valid"]
        for k, (ar, hd, v) in acc.items():
            if v:
                box_votes[k].append((ar / v, hd / v))
    box_class = {}
    for k, xs in box_votes.items():
        arab = statistics.median(x[0] for x in xs) >= R.ARAB_BOX_MIN_SHARE
        haredi = statistics.median(x[1] for x in xs) >= R.HAREDI_BOX_MIN_SHARE
        box_class[k] = "arab" if arab else "haredi" if haredi else "general"

    def box_sector(e, r):
        """Return (sector, sub) for one ballot row."""
        if r["env"]:
            return "jewish", "envelope"
        ls = loc_sector.get(r["code"], "jewish")
        if ls in ("arab", "druze"):
            return ls, loc_sub[r["code"]]
        c = box_class.get((r["code"], kalpi_base(r["kalpi"])), "general")
        return ("arab", "mixed") if c == "arab" else ("jewish", c)

    # ---- 2. National results, validation, sectors -------------------------
    report = []
    elections_out = []
    ballots_out = {}
    loc_out = {}
    for e, meta in R.ELECTIONS.items():
        party_cols, rows = data[e]
        reg = R.PARTIES[e]
        cols = list(reg.keys())  # main lists, registry order = official ranking

        nat = collections.Counter()
        tot = collections.Counter()
        for r in rows:
            for p, v in r["votes"].items():
                nat[p] += v
            for k in ("elig", "voters", "valid", "invalid"):
                tot[k] += r[k]

        # Reconcile against the official national table.
        mism = {p: (nat[p], totals[e].get(p)) for p in party_cols
                if totals[e].get(p) is not None and nat[p] != totals[e][p]}
        report.append(f"{e}: rows={len(rows)} valid={tot['valid']:,} lists={len(party_cols)} "
                      f"national-total mismatches={len(mism)}")
        if mism:
            report.append(f"   MISMATCH {mism}")

        computed = allocate({p: nat[p] for p in party_cols if nat[p] > 0},
                            seats=R.SEATS, threshold=R.THRESHOLD)
        off = official_seats.get(e, {})
        seat_diff = {p: (computed.get(p, 0), off.get(p, 0)) for p in sorted(set(computed) | set(off))
                     if computed.get(p, 0) != off.get(p, 0)}
        report.append(f"   Bader-Ofer without surplus agreements vs official seats: "
                      f"{'identical' if not seat_diff else seat_diff}")

        parties = []
        for p in sorted(party_cols, key=lambda x: -nat[x]):
            if nat[p] == 0:
                continue
            name, fam, bloc = reg.get(p, (official_names[e].get(p, p), "other", "out"))
            parties.append({
                "id": p, "name": name, "full": official_names[e].get(p, ""), "family": fam, "bloc": bloc,
                "votes": nat[p], "pct": round(100 * nat[p] / tot["valid"], 3),
                "seats": off.get(p, computed.get(p, 0)), "main": p in reg,
                "pred": R.PRED.get(e, {}).get(p),
            })

        # Sectors
        sec = {s: {"elig": 0, "voters": 0, "valid": 0, "boxes": 0, "votes": collections.Counter()}
               for s in ("arab", "druze", "jewish", "arab_std")}
        sub = collections.defaultdict(lambda: {"elig": 0, "voters": 0, "valid": 0, "boxes": 0,
                                               "votes": collections.Counter()})
        mixed_split = collections.defaultdict(lambda: {"arab": [0, 0, 0, collections.Counter()],
                                                       "jewish": [0, 0, 0, collections.Counter()]})
        box_rows = []
        loc_idx = {}
        for r in rows:
            s, sb = box_sector(e, r)
            targets = [sec[s], sub[f"{s}:{sb}"]]
            if not r["env"] and r["code"] in loc_std:
                targets.append(sec["arab_std"])   # IDI-comparable: Arab + Druze localities
            for target in targets:
                target["elig"] += r["elig"]
                target["voters"] += r["voters"]
                target["valid"] += r["valid"]
                target["boxes"] += 1
                for p, v in r["votes"].items():
                    if v:
                        target["votes"][p if p in reg else "other"] += v
            if r["code"] in R.MIXED_NAMES:
                m = mixed_split[r["code"]]["arab" if s == "arab" else "jewish"]
                m[0] += r["elig"]; m[1] += r["voters"]; m[2] += r["valid"]
                for p, v in r["votes"].items():
                    if v:
                        m[3][p if p in reg else "other"] += v

            if r["env"] or r["code"] is None:
                continue
            # locality aggregation
            L = loc_out.setdefault(r["code"], {"code": r["code"], "name": r["name"], "el": {}})
            L["name"] = r["name"] if e == "K25" or "name" not in L else L["name"]
            agg = L["el"].setdefault(e, {"boxes": 0, "elig": 0, "voters": 0, "valid": 0,
                                         "votes": collections.Counter(), "arab_boxes": 0})
            agg["boxes"] += 1
            agg["elig"] += r["elig"]; agg["voters"] += r["voters"]; agg["valid"] += r["valid"]
            if s == "arab" and loc_sector.get(r["code"]) in ("mixed", "jewish"):
                agg["arab_boxes"] += 1
            for p, v in r["votes"].items():
                if v:
                    agg["votes"][p if p in reg else "other"] += v
            # ballot row: [loc, kalpi, sectorCode, elig, voters, valid, *cols, other]
            other = sum(v for p, v in r["votes"].items() if p not in reg)
            sc = {"arab": 1, "druze": 2, "jewish": 0}[s] + (10 if sb == "haredi" else 0)
            box_rows.append([r["code"], r["kalpi"], sc, r["elig"], r["voters"], r["valid"]]
                            + [r["votes"].get(p, 0) for p in cols] + [other])
        ballots_out[e] = {"election": e, "cols": cols + ["other"],
                          "fields": ["loc", "kalpi", "sector", "elig", "voters", "valid"],
                          "rows": box_rows}

        def pack(d):
            return {"elig": d["elig"], "voters": d["voters"], "valid": d["valid"], "boxes": d["boxes"],
                    "votes": dict(d["votes"])}

        env_voters = sum(r["voters"] for r in rows if r["env"])
        elections_out.append({
            "id": e, **meta,
            "eligible": R.OFFICIAL_ELIGIBLE.get(e, tot["elig"]), "eligible_boxes": tot["elig"],
            "voters": tot["voters"], "valid": tot["valid"], "invalid": tot["invalid"],
            "turnout": round(100 * tot["voters"] / R.OFFICIAL_ELIGIBLE.get(e, tot["elig"]), 2),
            "threshold_votes": math.ceil(R.THRESHOLD * tot["valid"]),
            "envelope_voters": env_voters,
            "boxes": sum(1 for r in rows if not r["env"]),
            "cols": cols + ["other"],
            "parties": parties,
            "bloc_note": R.BLOC_NOTE[e],
            "sectors": {k: pack(v) for k, v in sec.items()},
            "subsectors": {k: pack(v) for k, v in sub.items()},
            "mixed": {str(code): {side: {"elig": v[0], "voters": v[1], "valid": v[2], "votes": dict(v[3])}
                                  for side, v in d.items()} for code, d in mixed_split.items()},
            "seats_check": "identical" if not seat_diff else {k: list(v) for k, v in seat_diff.items()},
            "reconcile": {"lists": sum(1 for p in party_cols if totals[e].get(p) is not None), "mismatches": len(mism)},
        })

    # ---- 3. Locality table ------------------------------------------------
    localities = []
    for code, L in sorted(loc_out.items()):
        lat, lng = centroids.get(code, (None, None))
        tribe = "שבט" in L["name"] and lat is None
        if tribe:
            lat, lng = tribal_point
        ls = loc_sector.get(code, "jewish")
        rec = {
            "code": code, "name": L["name"], "sector": ls,
            "region": loc_sub.get(code) if ls in ("arab", "druze") else ("mixed" if ls == "mixed" else None),
            "lat": lat, "lng": lng, "tribe": tribe,
            # The SES file falls back to the regional council's cluster for small localities,
            # so a cluster is attached only where the locality is large enough to have its own.
            "ses": ses.get(norm_name(L["name"]))
            if max(a["elig"] for a in L["el"].values()) >= SES_MIN_ELIG and L["name"] not in SES_NOT_OWN else None,
            "el": {},
        }
        for e, agg in L["el"].items():
            cols = R.PARTIES[e]
            rec["el"][e] = [agg["boxes"], agg["elig"], agg["voters"], agg["valid"], agg["arab_boxes"]] + \
                [agg["votes"].get(p, 0) for p in cols] + [agg["votes"].get("other", 0)]
        localities.append(rec)

    if unlisted:
        report.append(f"WARNING: localities with Arab-list majority missing from reference list: {unlisted}")
    for e in elections_out:
        st = e["sectors"]["arab_std"]
        arab_lists = sum(st["votes"].get(p, 0) for p in R.ARAB_LISTS[e["id"]])
        report.append(f"{e['id']}: Arab+Druze localities turnout {100 * st['voters'] / st['elig']:.1f}% "
                      f"(elig {st['elig']:,}); Arab-list share {100 * arab_lists / st['valid']:.1f}%")

    # ---- 4. Vote-transfer estimates between consecutive elections ---------
    transfers = []
    pairs = list(zip(list(R.ELECTIONS)[:-1], list(R.ELECTIONS)[1:]))
    for a, b in pairs:
        for scope in ("all", "arab"):
            t = estimate_transfer(a, b, data, box_sector, scope)
            if t:
                transfers.append(t)
                report.append(f"transfer {a}->{b} [{scope}]: box pairs={t['matched']} units={t['units']} "
                              f"coverage={t['coverage']:.0%} rmse={t['rmse']:.4f}")

    core = {
        "meta": {
            "title": "דשבורד הבחירות לכנסת",
            "next_election": {"date": "2026-10-27", "label": "הכנסת ה-26"},
            "sources": {
                "results": "ועדת הבחירות המרכזית — קובצי תוצאות לפי קלפיות (expb) לכנסות 21–25",
                "results_urls": {e: m["official_url"] for e, m in R.ELECTIONS.items()},
                "coordinates": "הלמ״ס — גבולות יישובים 2022 (מרכז הפוליגון)",
                "ses": "הלמ״ס — מדד חברתי-כלכלי 2021, אשכול 1–10",
            },
            "rules": {
                "arab_fallback_min_share": R.ARAB_FALLBACK_MIN_SHARE,
                "arab_box_min_share": R.ARAB_BOX_MIN_SHARE,
                "haredi_box_min_share": R.HAREDI_BOX_MIN_SHARE,
            },
        },
        "families": R.FAMILIES,
        "sectors": R.SECTORS,
        "arab_regions": R.ARAB_REGIONS,
        "druze_regions": R.DRUZE_REGIONS,
        "mixed_cities": {str(k): v for k, v in R.MIXED_NAMES.items()},
        "party_cols": {e: list(p.keys()) + ["other"] for e, p in R.PARTIES.items()},
        "elections": elections_out,
        "localities": localities,
        "transfers": transfers,
        "report": report,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "core.json"), "w", encoding="utf-8") as f:
        json.dump(core, f, ensure_ascii=False, separators=(",", ":"))
    for e, b in ballots_out.items():
        with open(os.path.join(out_dir, f"ballots_{e}.json"), "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False, separators=(",", ":"))
    return report


def kalpi_base(k):
    try:
        return int(float(k))
    except ValueError:
        return k


def estimate_transfer(a, b, data, box_sector, scope, boot=40, seed=20261027):
    """Constrained least squares on matched units:
    minimise sum_i w_i * || x_i M - y_i ||^2, rows of M on the simplex.
    x_i, y_i are shares of *eligible voters* (incl. 'did not vote'), so the
    matrix answers: of 100 voters of list A, how many voted B next time.

    Units: a ballot box (locality, base number; sub-boxes merged) is paired
    with the same box next time only when its eligible voters agree within
    -20%/+25%; box numbers were reassigned in 2021 (station.box), so a pair
    that changed size is not the same place. The rest of each locality forms
    one more unit on each side. Intervals come from a bootstrap over units."""
    def group(e, rows):
        main = list(R.PARTIES[e])
        out = {}
        for r in rows:
            if r["env"] or r["code"] is None or r["elig"] <= 0:
                continue
            sec, _ = box_sector(e, r)
            if scope == "arab" and sec != "arab":
                continue
            key = (r["code"], kalpi_base(r["kalpi"]))
            vec = [r["votes"].get(p, 0) for p in main]
            vec.append(r["valid"] - sum(vec) + r["invalid"])          # other lists + invalid
            vec.append(max(0, r["elig"] - r["voters"]))                # did not vote
            elig, acc = out.get(key, (0, [0] * len(vec)))
            out[key] = (elig + r["elig"], [x + y for x, y in zip(acc, vec)])
        return main + ["other", "abstain"], out

    ca, A = group(a, data[a][1])
    cb, B = group(b, data[b][1])
    ok = lambda ea, eb: 0.8 <= eb / ea <= 1.25
    pairs = [k for k in A if k in B and ok(A[k][0], B[k][0])]
    units = [(A[k][0], A[k][1], B[k][0], B[k][1]) for k in pairs]
    used = set(pairs)
    rest = {}
    for side, D in ((0, A), (1, B)):
        for k, (el, vec) in D.items():
            if k in used:
                continue
            r = rest.setdefault(k[0], [[0, None], [0, None]])[side]
            r[0] += el
            r[1] = vec if r[1] is None else [x + y for x, y in zip(r[1], vec)]
    for code, ((ea, va), (eb, vb)) in rest.items():
        if ea > 0 and eb > 0 and ok(ea, eb):
            units.append((ea, va, eb, vb))
    if len(units) < 200:
        return None
    eA = np.array([u[0] for u in units], float)
    X = np.array([np.array(u[1]) / u[0] for u in units])
    Y = np.array([np.array(u[3]) / u[2] for u in units])
    w = (eA + np.array([u[2] for u in units], float)) / 2
    coverage = float(eA.sum() / sum(v[0] for v in A.values()))
    # Drop source / destination columns that are essentially empty in this scope.
    weight_a = (X * eA[:, None]).sum(0)
    keep_a = [i for i in range(len(ca)) if weight_a[i] > 0.002 * weight_a.sum()]
    weight_b = (Y * w[:, None]).sum(0)
    keep_b = [j for j in range(len(cb)) if weight_b[j] > 0.002 * weight_b.sum()]
    X = X[:, keep_a]
    Y = Y[:, keep_b]

    def fit(idx, M0=None, steps=4000):
        Xw = X[idx] * np.sqrt(w[idx])[:, None]
        Yw = Y[idx] * np.sqrt(w[idx])[:, None]
        XtX, XtY = Xw.T @ Xw, Xw.T @ Yw
        L = np.linalg.eigvalsh(XtX).max()
        M = np.full((X.shape[1], Y.shape[1]), 1.0 / Y.shape[1]) if M0 is None else M0.copy()
        for _ in range(steps):
            M = project_rows_to_simplex(M - (XtX @ M - XtY) / L)
        return M, Xw, Yw

    allidx = np.arange(len(units))
    M, Xw, Yw = fit(allidx)
    resid = Xw @ M - Yw
    rmse = float(np.sqrt((resid ** 2).sum() / w.sum()))
    rng = np.random.default_rng(seed)
    draws = np.array([fit(rng.integers(0, len(units), len(units)), M, 1500)[0] for _ in range(boot)])
    lo, hi = np.percentile(draws, 5, axis=0), np.percentile(draws, 95, axis=0)
    return {
        "from": a, "to": b, "scope": scope, "matched": len(pairs), "units": len(units),
        "coverage": round(coverage, 3),
        "src": [ca[i] for i in keep_a], "dst": [cb[j] for j in keep_b],
        # real source-election votes in the matched units
        "src_mass": [round(float(v)) for v in (X * eA[:, None]).sum(0)],
        "matrix": [[round(float(v), 4) for v in row] for row in M],
        "ci": [[[round(float(l), 3), round(float(h), 3)] for l, h in zip(rl, rh)] for rl, rh in zip(lo, hi)],
        "rmse": rmse,
    }


def project_rows_to_simplex(M):
    """Euclidean projection of each row onto the probability simplex (vectorised)."""
    U = -np.sort(-M, axis=1)
    css = np.cumsum(U, axis=1)
    k = np.arange(1, M.shape[1] + 1)
    rho = M.shape[1] - 1 - np.argmax((U * k > css - 1)[:, ::-1], axis=1)
    theta = (css[np.arange(M.shape[0]), rho] - 1) / (rho + 1.0)
    return np.maximum(M - theta[:, None], 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="dir containing ballots/kXX.csv and metadata/parties.csv")
    ap.add_argument("--polygons", default="", help="CBS localities_2022 .geojson or .zip")
    ap.add_argument("--ses", default="", help="CBS socioeconomic clusters JSON [{name, cluster}]")
    ap.add_argument("--out", default=os.path.join(ROOT, "site", "data"))
    args = ap.parse_args()
    for line in build(args.src, args.polygons, args.ses, args.out):
        print(line)
