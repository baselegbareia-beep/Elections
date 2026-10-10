"""Arab-society turnout on election day, from the CEC's per-station turnout releases.

The CEC is to publish turnout per polling station at least four times on 27.10.2026 (chair's decision of
16.8.2026; hours, address and format not announced yet). For one release, arab_section() sums the
stations of Arab and Druze localities and the Arab stations of mixed cities by locality, by the list that
led there in 2022 (Ra'am, or Hadash-Ta'al + Balad, the 2026 Joint List), by region and by kind, against
the 2022 base in site/data/arab_day_2022.json (pipeline/build_arab_day.py). Turnout only: no party votes,
seats or threshold figures (owner's decision of 10.10.2026, ARCH_V3 §2). Standard library only.

Measures, for a locality or a group of localities (fractions):
  turnout   voters so far / eligible voters, over the release's stations that carry an eligible count;
  pace      voters so far / the same stations' final voters in 2022. When the release holds the whole of an
            Arab or Druze locality, the whole locality is compared, new, split and renumbered stations included
            (the CEC adds stations as the register grows). Whole means: no station without a figure, and every
            2022 station group of the locality (12, 12.1 and 12.2 share the number 12) in the release with at
            least as many stations as in 2022 - a station absent from the file is not hidden by new ones. Only
            where the stations were renumbered (fewer than half of the 2022 numbers in the release, RENUMBERED)
            do the counts decide instead: as many stations as in 2022, or the whole 2022 register. Otherwise station
            group by station group: a station by its own number; a group whose 2022 stations all have a figure
            and that gained sub-stations (a station split under its number, 12 -> 12 and 12.1) as one block,
            all of it now against all of it in 2022 (checks "split station"); in a group renumbered or merged,
            the sub-stations left on both sides as one block. A matched pair whose register grew by more than
            half or shrank by more than a third is another station ("register changed"). A station that
            cannot be placed is left out of pace and counted: a number not used in 2022 ("new station"), or
            the stations of a group that gained sub-stations while one of its stations has no figure yet
            ("unplaced station");
  coverage  share of the 2022 voters of the locality (group) whose stations the comparison covers;
  turnout22 the 2022 final turnout of those same stations;
  curve22   2022 at the same hour on those same stations: turnout22 x f(h) (from 10:00), so the total, which
            holds the Arab stations of mixed cities (2022 final 45.9%) beside the Arab and Druze localities
            (53.2%), is compared like with like;
  on_track  pace / f(h), f(h) = the 2022 Arab share of the day's turnout cast by hour h: 1.0 = on course
            for as many voters as in 2022 (the register grows about 2% a year, so 1.0 is a lower turnout);
  projected_final {lo, mid, hi} = turnout so far / f(h), with a rough 80% range.
f(h) is applied to every part of the section: the Druze localities and the Arab stations of mixed cities have no
  hourly figures of their own (the Druze timing may be closer to the national one; a judgement, documented in
  the base's note). The base carries the 2022 curve of each part in percent: curve.arab (Arab and Druze
  localities), curve.mixed_arab and curve.section (both, weighted by 2022 voters).

The 2022 Arab curve (arab_day_2022.json "curve", built by build_arab_day.build_curve):
  14:00 17%, 16:00 23%, 20:00 44%: aChord Center (Hebrew University) estimates published during the day
  (Times of Israel live blog), from sampled stations and a model; 18:00 30%: reported without attribution;
  22:00 53.2%: the official final of Arab and Druze localities; 10:00 and 12:00: the Arab/national ratio
  (0.44, 0.48, 0.52 at 14/16/18:00) carried back along its least-squares line onto the national 2022 series
  (about 5.7% and 11.3%; Hadash-Ta'al claimed 12% at noon); 19:00 along the national path from 18:00 to
  20:00. Linear between points, from 0 at 07:00. f(h) = curve(h) / 53.2: 0.32 at 14:00, 0.56 at 18:00,
  0.83 at 20:00, 0.91 at 21:00.
Uncertainty: mid = turnout / f(h) assumes 2026 keeps the 2022 Arab timing. Timing differs between
  elections (2022 ended with a late surge: a sixth of the day's Arab voters came after 20:00) and the 2022
  curve is itself an estimate, so the range takes sigma(h) = 2 x the standard deviation of
  log(final / figure at h) over the seven national series 2013-2022 (about 0.20 at 10:00, 0.08 at 14:00,
  0.06 at 20:00, 0.02 at 22:00) and lo/hi = mid x exp(-/+ 1.28 sigma), lo never below the turnout already
  reached. A judgement, not a calibrated interval: there is one election of Arab hourly data. Nothing is
  projected before 10:00. A release without eligible counts projects pace x the 2022 final turnout of the
  same stations (basis "pace", i.e. the 2022 register).
Limits: a mixed city's stations are classified by their 2022 number (the box rule of build_data.py): a new
  station there is not counted (checks.unclassified) and a renumbered one takes the class of its new number.
  The 2021 file read as a release, a hard case (its stations numbered their own way): 82 of 128 Arab
  localities compared whole, the rest station by station; pace of the Arab localities 0.808 against 0.796
  true, of the Druze localities 0.844 against 0.849 without Kisra-Sumei (a local boycott in 2022 left two of
  its stations with 37 and 67 voters, beyond the pace cap; with it 0.857 against 0.901); the Arab stations of
  mixed cities off by 3-40% per city, 8% of the section. Where the stations were renumbered, a file that
  lacks a few stations but gained new ones still passes as whole, with pace understated by the stations
  lacking. A row with more voters than eligible voters (beyond 2%) is dropped and a station group whose
  pace exceeds 2.0 is left out of pace, as in live_fetch.station_turnout. A station with a blank figure or
  0 voters is taken as not reported yet and left out (no station had 0 voters in 2022); a second row for
  the same station is dropped; all are counted in checks (rows, stations; unreadable, duplicate row, no
  figure, zero voters, more voters than eligible, unclassified, new station, split station, unplaced
  station, register changed, implausible pace).
`released` is the time the figures refer to (the CEC's cutoff, e.g. "14:00"), not the download time: 45
  minutes off at 14:00 moves the projection by about a tenth. `as_of` overrides it for the curve. A time
  after 22:00 (a file first seen after the polls closed) is read as 22:00, and as_of says so.

Also here: read_station_csv() reads a per-station CSV (expb.csv-like Hebrew headers) into rows,
history_entry() gives the compact record of a release for turnout.json["arab_history"] (with every locality
and kind, as live_fetch adds them). Checks: python3 pipeline/make_demo_turnout.py --check.
"""
import collections
import csv
import datetime as dt
import io
import json
import math
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_PATH = os.path.join(ROOT, "site", "data", "arab_day_2022.json")
BALLOTS_PATH = os.path.join(ROOT, "site", "data", "ballots_K25.json")
OPEN_H = 7.0             # polls open; the curve starts from 0 here
CLOSE_H = 22.0           # polls close; a later release time is read as 22:00
PROJECT_FROM = 10.0      # earlier releases are not projected: too little of the day has passed
ELIG_SPREAD = 1.5        # a matched station whose register changed more than this (either way) is another station
MAX_PACE = 2.0           # a station group above this is a renumbered or merged station, not a turnout
RENUMBERED = 0.5         # a locality with less than this share of its 2022 station numbers in a release was
                         # renumbered: station counts decide whether it is whole (0: never; the numbers alone)
_IDX = {}
try:
    from zoneinfo import ZoneInfo
    IL = ZoneInfo("Asia/Jerusalem")
except Exception:                         # no tz data: Israel winter time, in force from 25.10.2026
    IL = dt.timezone(dt.timedelta(hours=2))


def hour(t):
    """'14:00', '14:00:00' or an ISO datetime (with an offset: converted to Israel time) -> 14.0; None if unreadable."""
    if t is None:
        return None
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return float(t)
    s = str(t).strip()
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        d = d.astimezone(IL) if d.tzinfo else d
        return d.hour + d.minute / 60
    except ValueError:
        pass
    try:
        hh, mm = s.split(":")[:2]
        return int(hh) + int(mm) / 60
    except ValueError:
        return None


def hhmm(h):
    if h is None:
        return None
    m = round(h * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def kalpi_base(k):
    """Station number without the sub-station suffix: '12.1' -> 12 (build_data.kalpi_base)."""
    try:
        return int(float(k))
    except (TypeError, ValueError):
        return str(k).strip()


def kalpi_id(k):
    """A station number as written in ballots_K25.json: '12', '12.0' and 12 -> '12'; '3.1' stays."""
    s = str(k).strip()
    return s.split(".")[0] if re.fullmatch(r"\d+\.0+", s) else s


def load_base(path=BASE_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _index(base, ballots_path=BALLOTS_PATH):
    """The 2022 stations of the section from ballots_K25.json: per station (locality, number) its final voters,
    eligible voters and section key, the sub-stations of each station group, and the stations of mixed cities."""
    keys = tuple(x["key"] for x in base["localities"])
    sig = (ballots_path, hash(keys))
    if sig in _IDX:
        return _IDX[sig]
    whole = {x["code"] for x in base["localities"] if x["kind"] != "mixed_arab"}
    mixed = {x["code"] for x in base["localities"] if x["kind"] == "mixed_arab"}
    with open(ballots_path, encoding="utf-8") as f:
        b25 = json.load(f)
    st22, cls, subs, known = {}, {}, collections.defaultdict(list), set()
    for row in b25["rows"]:
        code, kalpi, sc, elig, voters = row[0], kalpi_id(row[1]), row[2], row[3], row[4]
        b = kalpi_base(kalpi)
        if code in whole:
            key = str(code)
        elif code in mixed:
            known.add((code, b))
            if sc % 10 != 1:          # a mixed city's group is Arab or not as a whole (build_data box rule)
                continue
            key = f"{code}:arab"
        else:
            continue
        st22[(code, kalpi)] = (voters, elig)
        cls[(code, b)] = key
        subs[(code, b)].append(kalpi)
    groups = collections.defaultdict(set)
    for (code, b), key in cls.items():
        groups[key].add(b)
    _IDX[sig] = idx = {"whole": whole, "mixed": mixed, "st22": st22, "cls": cls, "subs": dict(subs),
                       "groups": dict(groups), "known": known}
    return idx


def _block(rows, olds):
    """(voters, eligible, 2022 voters, 2022 eligible) of release stations `rows` against 2022 stations `olds`;
    eligible None when a release station has none."""
    el = [x[2] for x in rows]
    return (sum(x[1] for x in rows), sum(el) if all(el) else None,
            sum(x[0] for x in olds), sum(x[1] for x in olds))


def _whole(code, key, stations, idx, stations22, elig22):
    """True when the release holds the whole locality, every station with a figure (`stations`: its stations with
    one; the caller checks that none is without). Where the 2022 numbering still holds (at least RENUMBERED, half,
    of the locality's 2022 station numbers are in the release), every 2022 station group (12, 12.1 and 12.2 share
    the number 12) must be there with at least as many stations as in 2022: its sub-stations by their own numbers,
    or renumbered or split under the same number. Where the stations were renumbered (fewer than half of the 2022
    numbers here; in the 2021 file, 24 of 144 Arab and Druze localities), the numbers say nothing and the counts
    decide: as many stations as in 2022, or the whole 2022 register."""
    groups = idx["groups"].get(key, ())
    have = collections.Counter(kalpi_base(k) for k, _, _ in stations)
    if sum(1 for b in groups if have[b]) >= RENUMBERED * len(groups):
        return all(have[b] >= len(idx["subs"][(code, b)]) for b in groups)
    return len(stations) >= stations22 or sum(el or 0 for _, _, el in stations) >= elig22


def _compare(code, stations, blank, idx, checks):
    """(voters now, 2022 final voters, 2022 eligible) over the stations matched to 2022, station group by station
    group (12, 12.1, 12.2 share the number 12). `stations`: the release's (number, voters, eligible) with a figure;
    `blank`: the numbers of its stations without one.
      - the group has the same sub-stations as in 2022 (some may be missing): a station by its own number;
      - every 2022 station of the group has a figure and the release adds sub-stations under the number (a station
        split): the whole group as one block, all its stations now against all of them in 2022 ("split station");
      - sub-stations renumbered or merged: a station by its own number, and the rest on both sides as one block;
      - new sub-stations while a station of the group has no figure yet: the group cannot be matched yet and its
        stations are left out ("unplaced station"); a number not used in 2022 is left out ("new station").
    A pair whose register grew by more than half or shrank by more than a third is another station ("register
    changed"); one whose pace exceeds MAX_PACE is a renumbered or merged station ("implausible pace")."""
    now = then = e22 = 0
    by_b = collections.defaultdict(list)
    for kalpi, v, el in stations:
        by_b[kalpi_base(kalpi)].append((kalpi, v, el))
    pending = collections.defaultdict(set)
    for k in blank:
        pending[kalpi_base(k)].add(k)
    for b, rows in by_b.items():
        old = idx["subs"].get((code, b))
        if not old:
            checks["new station"] += len(rows)
            continue
        mine = [r for r in rows if r[0] in old]
        new = [r for r in rows if r[0] not in old]
        pend = pending.get(b, set())
        if not new and pend <= set(old):
            pairs = [(v, el, *idx["st22"][(code, k)]) for k, v, el in mine]
        elif pend:
            checks["unplaced station"] += len(rows)
            continue
        elif len(mine) == len(old):
            pairs = [_block(rows, [idx["st22"][(code, k)] for k in old])]
            checks["split station"] += 1
        else:
            hit = {r[0] for r in mine}
            pairs = [(v, el, *idx["st22"][(code, k)]) for k, v, el in mine]
            pairs.append(_block(new, [idx["st22"][(code, k)] for k in old if k not in hit]))
        for v, el, v22, el22 in pairs:
            if not v22:
                continue
            if v > MAX_PACE * v22:
                checks["implausible pace"] += 1
                continue
            if el and el22 and not 1 / ELIG_SPREAD <= el / el22 <= ELIG_SPREAD:
                checks["register changed"] += 1     # another station under the same number
                continue
            now += v
            then += v22
            e22 += el22
    return now, then, e22


def curve_at(curve, h):
    """(2022 Arab turnout at h in percent, share of the day's final turnout cast by h, sigma) by linear interpolation."""
    hs = [OPEN_H] + [hour(x) for x in curve["hours"]]
    ar = [0.0] + list(curve["arab"])
    sg = [curve["sigma"][0]] + list(curve["sigma"])
    final = ar[-1]
    if h >= hs[-1]:
        return final, 1.0, sg[-1]
    h = max(h, OPEN_H)
    i = next(i for i in range(1, len(hs)) if h <= hs[i])
    w = (h - hs[i - 1]) / (hs[i] - hs[i - 1])
    a = ar[i - 1] + w * (ar[i] - ar[i - 1])
    return a, a / final, sg[i - 1] + w * (sg[i] - sg[i - 1])


def project(turnout, h, curve, basis="turnout"):
    """Projected final turnout {lo, mid, hi} from turnout so far at hour h, or None before PROJECT_FROM."""
    if turnout is None or h is None or h < PROJECT_FROM:
        return None
    _, f, s = curve_at(curve, h)
    if f <= 0:
        return None
    mid = turnout / f
    k = math.exp(curve.get("z", 1.2816) * s)
    return {"lo": round(min(1.0, max(turnout, mid / k)), 4), "mid": round(min(1.0, mid), 4),
            "hi": round(min(1.0, mid * k), 4), "basis": basis}


def _r(x, n):
    return round(x, n) if x is not None else None


def _measures(s, h, curve, full=True):
    """Turnout, pace and the rest from summed counts s (see the module docstring)."""
    t = s["voters_e"] / s["elig"] if s["elig"] else None
    pace = s["now"] / s["then"] if s["then"] else None
    t22 = s["then"] / s["e22"] if s["e22"] else None
    f = curve_at(curve, h)[1] if (h is not None and h >= PROJECT_FROM) else None
    out = {"voters": s["voters"], "elig": s["elig"] or None, "turnout": _r(t, 4), "pace": _r(pace, 3),
           "stations": s["stations"], "coverage": _r(s["then"] / s["v22"], 3) if s["v22"] else None,
           "on_track": _r(pace / f, 3) if (pace is not None and f) else None}
    if full:
        out["turnout22"] = _r(t22, 4)
        # 2022 at the same hour on the same stations: their 2022 final x the share of the day's turnout cast by h
        out["curve22"] = _r(f * t22, 4) if (f and t22 is not None) else None
        if t is not None:
            out["projected_final"] = project(t, h, curve)
        elif pace is not None and t22 is not None:
            out["projected_final"] = project(pace * t22, h, curve, basis="pace")
        else:
            out["projected_final"] = None
    return out


def arab_section(rows, base, national_turnout=None, released=None, as_of=None):
    """One per-station turnout release -> the Arab-society section of turnout.json.

    rows: iterable of {"code": int, "kalpi": str, "elig": int | None, "voters": int}, every station of the
      release (the national turnout is computed from all of them unless national_turnout is given);
    base: the loaded site/data/arab_day_2022.json; the 2022 per-station voters come from ballots_K25.json;
    national_turnout: the national turnout of the same release, fraction or percent (optional);
    released: the time the figures refer to, 'HH:MM' Israel time; as_of overrides it for the curve. A time after
      the polls close (22:00) is 22:00."""
    idx = _index(base)
    curve = base["curve"]
    h = hour(as_of if as_of is not None else released)
    if h is not None:
        h = min(h, CLOSE_H)
    acc = {}
    nat_v = nat_e = n_rows = 0
    checks = collections.Counter()
    seen = set()
    for r in rows:
        n_rows += 1
        try:
            code, kalpi, v = int(float(r["code"])), kalpi_id(r["kalpi"]), r.get("voters")
            elig = int(float(r["elig"])) if str(r.get("elig") or "").strip() not in ("", "-") else None
            voters = None if v is None or str(v).strip() in ("", "-") else int(float(v))
        except (KeyError, TypeError, ValueError):
            checks["unreadable"] += 1
            continue
        if (code, kalpi) in seen:
            checks["duplicate row"] += 1        # the same station twice: the first row counts
            continue
        seen.add((code, kalpi))
        key = None
        if code in idx["whole"]:
            key = str(code)
        elif code in idx["mixed"]:
            b = kalpi_base(kalpi)
            key = idx["cls"].get((code, b))
            if key is None and (code, b) not in idx["known"] and voters:
                checks["unclassified"] += 1         # a mixed-city station without a 2022 counterpart
        a = acc.setdefault(key, {"voters": 0, "voters_e": 0, "elig": 0, "stations": [], "blank": set()}) \
            if key else None
        if not voters or voters < 0:
            # a blank figure or 0 voters (no station had 0 in 2022): not reported yet; left out, not read as 0
            checks["no figure" if voters is None else "zero voters"] += 1
            if a:
                a["blank"].add(kalpi)
            continue
        if elig and voters > elig * 1.02:
            checks["more voters than eligible"] += 1
            if a:
                a["blank"].add(kalpi)           # a station without a usable figure, as a blank one
            continue
        if elig:
            nat_v += voters
            nat_e += elig
        if not a:
            continue
        a["voters"] += voters
        a["stations"].append((kalpi, voters, elig))
        if elig:
            a["voters_e"] += voters
            a["elig"] += elig
    if national_turnout is not None:
        nat = float(national_turnout)
        nat = nat / 100 if nat > 1.5 else nat
    else:
        nat = nat_v / nat_e if nat_e else None

    def zero():
        return {"voters": 0, "voters_e": 0, "elig": 0, "stations": 0, "now": 0, "then": 0, "e22": 0, "v22": 0,
                "localities": 0}
    sums = {"groups": collections.defaultdict(zero), "regions": collections.defaultdict(zero),
            "kinds": collections.defaultdict(zero)}
    total = zero()
    for x in base["localities"]:                    # 2022 voters of every entry, for coverage
        for name, k in (("groups", x["leader22"]), ("regions", x["region"]), ("kinds", x["kind"])):
            sums[name][k]["v22"] += x["voters22"]
        total["v22"] += x["voters22"]
    locs = []
    for x in base["localities"]:
        a = acc.get(x["key"])
        if not a or not a["stations"]:
            continue
        s = {k: a[k] for k in ("voters", "voters_e", "elig")}
        s["stations"] = len(a["stations"])
        whole = (x["kind"] != "mixed_arab" and not a["blank"]
                 and _whole(x["code"], x["key"], a["stations"], idx, x["stations22"], x["elig22"]))
        if whole and a["voters"] <= MAX_PACE * x["voters22"]:
            # every 2022 station of the locality is here with a figure, and none without one: the locality is
            # compared as a whole, new, split and renumbered stations included
            s.update(now=a["voters"], then=x["voters22"], e22=x["elig22"])
        else:
            s["now"], s["then"], s["e22"] = _compare(x["code"], a["stations"], a["blank"], idx, checks)
        s["v22"] = x["voters22"]
        locs.append({"key": x["key"], **_measures(s, h, curve, full=False)})
        for t in (sums["groups"][x["leader22"]], sums["regions"][x["region"]], sums["kinds"][x["kind"]], total):
            for k in ("voters", "voters_e", "elig", "stations", "now", "then", "e22"):
                t[k] += s[k]
            t["localities"] += 1

    def block(d):
        return {k: {**_measures(v, h, curve), "localities": v["localities"]} for k, v in sorted(d.items())}

    tot = {**_measures(total, h, curve), "localities": total["localities"]}
    tot["ratio_to_national"] = _r(tot["turnout"] / nat, 3) if (tot["turnout"] is not None and nat) else None
    return {"released": released, "as_of": hhmm(h), "national": _r(nat, 4),
            "localities": locs, "groups": block(sums["groups"]), "regions": block(sums["regions"]),
            "kinds": block(sums["kinds"]), "total": tot,
            "checks": {"rows": n_rows, "stations": total["stations"], **dict(checks)}}


def history_entry(sec):
    """A compact record of one release for turnout.json["arab_history"]: the time, the national turnout, the total
    (turnout, pace, curve22, projected_final), turnout and pace by group, region and kind ({key: {turnout, pace}};
    the page's Druze panel reads kinds), and every reported locality as {key: [turnout, pace]} (the page's change
    since the previous release). live_fetch.history_entry builds the same "kinds" and "localities"."""
    def pick(m):
        return {"turnout": m["turnout"], "pace": m["pace"]}
    return {"released": sec["released"], "as_of": sec["as_of"], "national": sec["national"],
            "total": {**pick(sec["total"]), "curve22": sec["total"].get("curve22"),
                      "projected_final": sec["total"]["projected_final"]},
            "groups": {k: pick(v) for k, v in sec["groups"].items()},
            "regions": {k: pick(v) for k, v in sec["regions"].items()},
            "kinds": {k: pick(v) for k, v in sec["kinds"].items()},
            "localities": {str(x["key"]): [x["turnout"], x["pace"]] for x in sec["localities"]}}


def read_station_csv(data, column_aliases=None):
    """A per-station turnout CSV (bytes or text) -> arab_section rows. Columns are found by their Hebrew names as in
    expb.csv (סמל ישוב, קלפי, בזב, מצביעים) or common variants; a file with a turnout percentage instead of a
    voter count gives voters = percentage x eligible. column_aliases maps another header to one of those names."""
    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            data = data.decode("cp1255", "replace")
    rd = csv.reader(io.StringIO(data.lstrip("\ufeff")))
    aliases = column_aliases or {}
    header = [aliases.get(h.strip(), h.strip()) for h in next(rd)]

    def col(*names):
        return next((header.index(n) for n in names if n in header), None)
    ic = col("סמל ישוב", "סמל יישוב", "קוד ישוב", "קוד יישוב")
    ik = col("קלפי", "מספר קלפי", "מס' קלפי", "מס קלפי", "סמל קלפי")
    ie = col("בזב", "בז\"ב", "בעלי זכות בחירה", "בעלי זכות")
    iv = col("מצביעים", "הצביעו", "מספר מצביעים", "מצביעים עד כה")
    ip = col("אחוז הצבעה", "שיעור הצבעה", "אחוז")
    if ic is None or ik is None or (iv is None and (ip is None or ie is None)):
        raise ValueError(f"unknown columns: {header[:12]}")
    need = max(i for i in (ic, ik, ie, iv, ip) if i is not None)
    rows = []
    for rec in rd:
        if len(rec) <= need:
            continue
        elig = rec[ie].strip() if ie is not None else None
        voters = rec[iv].strip() if iv is not None else None
        if iv is None:
            try:
                voters = round(float(rec[ip].strip().rstrip("%")) / 100 * float(elig))
            except ValueError:
                voters = None
        rows.append({"code": rec[ic].strip(), "kalpi": rec[ik].strip(), "elig": elig, "voters": voters})
    return rows
