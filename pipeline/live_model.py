"""Election-night projection: estimate the final result from a partial count.

Method (stratified ratio-to-baseline estimator, the approach of US
election-night models adapted to Israel's single national constituency):

* Unit: locality. The CEC ballot file reports boxes; counted boxes are summed
  per locality. The previous election is the baseline.
* Strata: every baseline locality gets a stratum from its sector and past
  vote: Arab localities by region group, Druze, mixed cities, Haredi-majority
  localities, and the other Jewish localities by quintile of the
  Netanyahu-bloc share and by size. Counted localities of a stratum stand in
  for its uncounted ones.
* Turnout: current turnout relative to baseline turnout in the counted part of
  each stratum, applied to the baseline turnout of each uncounted locality.
* Vote shares: for each list, the ratio of its current share to the share of
  its predecessor lists (BASE_MAP) in the same counted localities, applied to
  the predecessor share in each uncounted locality. Lists with no predecessor
  take the stratum's current share.
* A locality that has counted at least 20% of its expected voters is
  completed from its own boxes.
* Double envelopes are counted last; their size follows the baseline envelopes
  scaled by turnout and register growth, their composition the baseline
  envelope composition scaled by each list's national ratio.
* Seats: Bader-Ofer with the surplus agreements. Uncertainty: bootstrap of the
  counted localities within each stratum, plus envelope noise.

backtest() replays a past election with the one before it as the baseline, in
simulated counting orders, and measures the error at each stage of the count.

Run: python3 pipeline/live_model.py backtest --base K24 --cur K25
"""
import argparse
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry as R  # noqa: E402
from bader_ofer import allocate  # noqa: E402
from build_data import load_election  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OTHER = "_other"       # small lists, counted in the total but never a list (see bader_ofer.allocate)

# Current list -> predecessor lists in the baseline election.
BASE_MAP = {
    "K25": {"מחל": ["מחל"], "פה": ["פה"], "ט": ["ט"], "כן": ["כן", "ת"], "שס": ["שס"], "ג": ["ג"], "ל": ["ל"],
            "עם": ["עם"], "ום": ["ודעם"], "ד": ["ודעם"], "אמת": ["אמת"], "מרצ": ["מרצ"], "ב": ["ב"]},
    "K24": {"מחל": ["מחל"], "פה": ["פה"], "כן": ["כן"], "שס": ["שס"], "ג": ["ג"], "ל": ["ל"], "ט": ["טב"],
            "ב": ["טב"], "אמת": ["אמת"], "מרצ": ["אמת"], "ודעם": ["ודעם"], "עם": ["ודעם"], "ת": []},
    # 2026 lists (ids as in polls_2026.json) -> 2022 ballot letters
    "K26": {"Likud": ["מחל"], "Yashar": ["כן"], "Together": ["פה"], "The Democrats": ["אמת", "מרצ"],
            "Yisrael Beiteinu": ["ל"], "Shas": ["שס"], "UTJ": ["ג"], "Otzma Yehudit": ["ט"],
            "Religious Zionism": ["ט"], "Joint List": ["ום", "ד"], "Ra'am": ["עם"], "National Unity": ["כן"],
            "Amcha Yisrael": [], "Reservists": [], "Haredi Public": []},
}
AGREEMENTS = {
    "K25": [("מחל", "ט"), ("פה", "כן"), ("שס", "ג"), ("ל", "עם"), ("אמת", "מרצ"), ("ום", "ד")],
    "K24": [("מחל", "ט"), ("פה", "ל"), ("כן", "ת"), ("שס", "ג"), ("אמת", "מרצ"), ("ב", "עם")],
}
OWN_MIN = 0.2
K_LEVEL = {"N": 30000, "G": 15000, "S": 6000}   # pseudo-votes of the parent level (shrinkage)
PRIOR_SD = 0.15        # relative error of the pre-election prior per list
STRATUM_SD = 0.10      # stratum random effect, scaled by how much the stratum leans on its parent
SYS_SD = 0.06          # shared shift of the Netanyahu camp in the uncounted vote (log scale, at 0% counted)
SYS_SD_ARAB = 0.12     # shared shift of the Arab lists in the uncounted vote
THIN_WIDEN = 1.5       # extra shared error when the uncounted vote sits in strata with almost nothing counted
LIST_SD = 0.08         # independent error of each list in the uncounted vote (log scale, at 0% counted)
LIST_NEW = 1.8         # multiplier for lists without a clean predecessor
ARAB_GROUP = {"negev": "arab_negev", "north_bedouin": "arab_north", "galilee": "arab_north",
              "nazareth": "arab_north", "christian": "arab_north", "wadi_ara": "arab_triangle",
              "triangle_south": "arab_triangle", "mixed_town": "arab_north", "jerusalem": "arab_other",
              "mixed": "arab_other"}


def new_unit():
    return {"elig": 0, "voters": 0, "valid": 0, "votes": collections.Counter(), "boxes": 0}


def add_row(unit, r, keep):
    unit["elig"] += r["elig"]
    unit["voters"] += r["voters"]
    unit["valid"] += r["valid"]
    unit["boxes"] += 1
    for p, n in r["votes"].items():
        unit["votes"][p if p in keep else OTHER] += n


def locality_table(rows, keep):
    """Sum ballot rows per locality; envelopes kept apart. Lists outside `keep` go to OTHER."""
    loc, env = {}, new_unit()
    for r in rows:
        add_row(env if r["env"] or r["code"] is None else loc.setdefault(r["code"], new_unit()), r, keep)
    return loc, env


class Baseline:
    """The previous election, summed per locality, with a stratum for every locality."""

    def __init__(self, e, rows, core):
        self.e = e
        self.loc, self.env = locality_table(rows, set(R.PARTIES[e]))
        meta = {l["code"]: l for l in core["localities"]}
        nb = [p for p, v in R.PARTIES[e].items() if v[2] == "nb"]
        haredi = [p for p in ("ג", "שס") if p in R.PARTIES[e]]
        jew = sorted((sum(L["votes"][p] for p in nb) / L["valid"], L["elig"], c)
                     for c, L in self.loc.items()
                     if meta.get(c, {}).get("sector", "jewish") == "jewish" and L["valid"])
        tot = sum(x[1] for x in jew) or 1
        acc, q = 0, {}
        for _, el, c in jew:
            q[c] = min(4, int(5 * acc / tot))
            acc += el
        self.stratum, self.group = {}, {}
        for c, L in self.loc.items():
            m = meta.get(c, {})
            sec = m.get("sector", "jewish")
            if sec == "arab":
                s, g = ARAB_GROUP.get(m.get("region"), "arab_other"), "arab"
            elif sec in ("druze", "mixed"):
                s = g = sec
            elif L["valid"] and sum(L["votes"][p] for p in haredi) / L["valid"] >= 0.5:
                s, g = "haredi", "jewish"
            else:
                size = "big" if L["elig"] >= 40000 else "town" if L["elig"] >= 5000 else "small"
                s, g = f"j{q.get(c, 2)}_{size}", "jewish"
            self.stratum[c], self.group[c] = s, g


def base_share(unit, preds):
    """Baseline share of the predecessor lists in a unit; None for a new list."""
    if preds is None or not unit["valid"]:
        return None
    return sum(unit["votes"].get(p, 0) for p in preds) / unit["valid"]


class Projector:
    def __init__(self, base, cur_lists, mapping, g, agreements, prior=None, prior_t=1.0, camp=None):
        """prior: expected national vote share per list before any count (poll average);
        prior_t: expected turnout relative to the baseline (1.0 = same as last time);
        camp: {list: 'coal'|'opp'|'arab'} for the shared error of the uncounted vote."""
        self.camp = dict(camp or {})
        self.B, self.lists, self.g, self.agreements = base, list(cur_lists) + [OTHER], g, agreements
        self.prior, self.prior_t = dict(prior or {}), prior_t
        self.base_vv = sum(L["valid"] for L in base.loc.values()) / max(1, sum(L["voters"] for L in base.loc.values()))
        # predecessor lists; None = new list (no predecessor), OTHER maps to the baseline's small lists
        self.preds = {j: (mapping.get(j) or None) for j in cur_lists}
        self.preds[OTHER] = [OTHER]
        # lists without a clean predecessor (new, or sharing one with another list) are harder to project
        shared = collections.Counter(p for j in cur_lists for p in (self.preds[j] or []))
        self.unstable = {j for j in cur_lists if self.preds[j] is None or any(shared[p] > 1 for p in self.preds[j])}
        self.bshare = {c: {j: base_share(L, self.preds[j]) for j in self.lists} for c, L in base.loc.items()}
        self.benv = {j: base_share(base.env, self.preds[j]) for j in self.lists}
        nv = sum(L["valid"] for L in base.loc.values())
        self.base_nat = {j: (sum(self.bshare[c][j] * L["valid"] for c, L in base.loc.items()) / nv
                             if self.preds[j] is not None else None) for j in self.lists}

    def stats(self, counted, codes):
        st = collections.defaultdict(lambda: {"v": 0.0, "ev": 0.0, "valid": 0.0, "voters": 0.0,
                                              "cur": collections.Counter(), "base": collections.Counter()})
        B = self.B
        for c in codes:
            C, L = counted[c], B.loc[c]
            if not C["elig"] or not L["elig"] or not L["valid"]:
                continue
            bt = L["voters"] / L["elig"]
            bs = self.bshare[c]
            for key in (B.stratum[c], "G:" + B.group[c], "N"):
                a = st[key]
                a["v"] += C["voters"]
                a["ev"] += C["elig"] * bt
                a["valid"] += C["valid"]
                a["voters"] += C["voters"]
                for j in self.lists:
                    a["cur"][j] += C["votes"].get(j, 0)
                    if bs[j] is not None:
                        a["base"][j] += C["valid"] * bs[j]
        return st

    def levels(self, st, rng=None):
        """Turnout ratio and per-list multipliers for the nation, each group and each stratum.

        Each level is shrunk toward its parent (stratum -> group -> nation -> pre-election prior)
        with the weight of K pseudo-votes, so a level with few counted votes leans on its parent.
        For a list with predecessors the multiplier is current share / predecessor share; for a
        new list it is the share itself. With rng, the prior and every stratum get random noise
        (one bootstrap draw)."""
        B = self.B
        jit = (lambda sd: rng.gauss(0, sd)) if rng else (lambda sd: 0.0)
        prior = {"t": self.prior_t * pow(2.718281828, jit(0.03)), "vv": self.base_vv, "r": {}}
        for j in self.lists:
            ps = self.prior.get(j)
            if self.preds[j] is not None:
                bn = self.base_nat[j]
                r0 = (ps / bn) if (ps is not None and bn > 0) else 1.0
            else:
                r0 = ps if ps is not None else 0.005
            prior["r"][j] = r0 * pow(2.718281828, jit(PRIOR_SD))

        def level(a, parent, k, sd):
            V = a["valid"] if a else 0
            out = {"t": parent["t"], "vv": parent["vv"], "r": dict(parent["r"])}
            if V > 0:
                w = V / (V + k)
                out["t"] = w * (a["v"] / a["ev"]) + (1 - w) * parent["t"]
                out["vv"] = w * (a["valid"] / a["voters"]) + (1 - w) * parent["vv"]
                for j in self.lists:
                    if self.preds[j] is not None:
                        raw = (a["cur"][j] / a["base"][j]) if a["base"][j] > 0 else parent["r"][j]
                    else:
                        raw = a["cur"][j] / a["valid"]
                    out["r"][j] = w * raw + (1 - w) * parent["r"][j]
            if sd:
                f = sd * (k / (V + k)) ** 0.5
                out["r"] = {j: v * pow(2.718281828, jit(f)) for j, v in out["r"].items()}
                out["t"] *= pow(2.718281828, jit(f / 3))
            return out

        N = level(st.get("N"), prior, K_LEVEL["N"], 0)
        # Arab and Druze localities move on their own (turnout and Arab-list splits), so with little
        # counted there they lean on the pre-election prior rather than on the Jewish majority's count.
        groups = {g: level(st.get("G:" + g), prior if g in ("arab", "druze") else N, K_LEVEL["G"], STRATUM_SD)
                  for g in set(B.group.values())}
        strata = {}
        for c in B.loc:
            s_ = B.stratum[c]
            if s_ not in strata:
                strata[s_] = level(st.get(s_), groups[B.group[c]], K_LEVEL["S"], STRATUM_SD)
        return N, strata

    def counted_votes(self, counted):
        tot = collections.Counter()
        for C in counted.values():
            for j in self.lists:
                tot[j] += C["votes"].get(j, 0)
        return tot

    def estimate(self, counted, codes, env_counted=None, rng=None):
        """Projected votes still to come per list: (uncounted boxes part, envelopes part)."""
        B = self.B
        st = self.stats(counted, codes)
        N, strata = self.levels(st, rng)
        boxes = collections.Counter()
        for c, L in B.loc.items():
            E = L["elig"] * self.g
            C = counted.get(c)
            rem = E - (C["elig"] if C else 0)
            if rem <= 0 or not L["elig"] or not L["valid"]:
                continue
            if C and C["elig"] >= OWN_MIN * E and C["valid"]:
                k = rem / C["elig"]
                for j in self.lists:
                    boxes[j] += k * C["votes"].get(j, 0)
                continue
            lv = strata[B.stratum[c]]
            valid_r = rem * (L["voters"] / L["elig"]) * lv["t"] * lv["vv"]
            sh = {j: lv["r"][j] * self.bshare[c][j] if self.preds[j] is not None else lv["r"][j] for j in self.lists}
            s = sum(sh.values()) or 1
            for j in self.lists:
                boxes[j] += valid_r * sh[j] / s
        env = collections.Counter()
        if env_counted and env_counted.get("valid"):
            for j in self.lists:
                env[j] = env_counted["votes"].get(j, 0)
        elif B.env["valid"]:
            total = B.env["valid"] * self.g * N["t"]
            sh = {j: N["r"][j] * self.benv[j] if self.preds[j] is not None else N["r"][j] for j in self.lists}
            s = sum(sh.values()) or 1
            for j in self.lists:
                env[j] = total * sh[j] / s
        return boxes, env

    def seats(self, votes):
        return allocate({j: int(round(v)) for j, v in votes.items() if v > 0}, agreements=self.agreements)

    def shock(self, part, rng, scale):
        """Shared error of everything not yet counted: the Netanyahu camp gains or loses against the
        other Jewish lists (total kept), and the Arab lists move together (turnout)."""
        dc, da = rng.gauss(0, SYS_SD * scale), rng.gauss(0, SYS_SD_ARAB * scale)
        out = {j: v * (pow(2.718281828, dc) if self.camp.get(j) == "coal" else
                       pow(2.718281828, da) if self.camp.get(j) == "arab" else 1.0)
                  * pow(2.718281828, rng.gauss(0, LIST_SD * scale * (LIST_NEW if j in self.unstable else 1.0)))
               for j, v in part.items()}
        jew = [j for j in part if self.camp.get(j) != "arab"]
        before, after = sum(part[j] for j in jew), sum(out[j] for j in jew)
        if after > 0:
            for j in jew:
                out[j] *= before / after
        return out

    def run(self, counted, env_counted=None, n_boot=100, seed=7):
        codes = [c for c in counted if c in self.B.loc]
        have = self.counted_votes(counted)
        boxes, env = self.estimate(counted, codes, env_counted)
        point = {j: have[j] + boxes[j] + env[j] for j in self.lists}
        rng = random.Random(seed)
        by_s = collections.defaultdict(list)
        for c in codes:
            by_s[self.B.stratum[c]].append(c)
        left = sum(boxes.values()) / max(1.0, sum(point.values()))   # share of the vote still projected
        # share of the uncounted electorate in strata with too little counted to stand on their own:
        # those estimates are borrowed from other places, so the shared error is widened
        st = self.stats(counted, codes)
        rem_s, thin = collections.Counter(), 0.0
        for c, L in self.B.loc.items():
            C = counted.get(c)
            r_ = max(0.0, L["elig"] * self.g - (C["elig"] if C else 0))
            rem_s[self.B.stratum[c]] += r_
        tot_rem = sum(rem_s.values()) or 1.0
        for k, v in rem_s.items():
            if st[k]["valid"] < K_LEVEL["S"]:
                thin += v / tot_rem
        scale = left ** 0.5 * (1 + THIN_WIDEN * thin)
        self.last_diag = {"left": round(left, 3), "thin": round(thin, 3), "scale": round(scale, 3)}
        sims = []
        for _ in range(n_boot):
            sample = [rng.choice(v) for v in by_s.values() for _ in v]
            b, e = self.estimate(counted, sample, env_counted, rng)
            b = self.shock(b, rng, scale)
            if not env_counted:
                e = self.shock({j: v * max(0.0, rng.gauss(1, 0.08)) for j, v in e.items()}, rng, 0.5)
            sims.append({j: have[j] + b[j] + e[j] for j in self.lists})
        return point, sims


def summarize(proj, point, sims, threshold=0.0325):
    lists = [j for j in proj.lists if j != OTHER]
    seats = proj.seats(point)
    sim_seats = [proj.seats(s) for s in sims]
    tot = sum(point.values())
    out = {}
    for j in lists:
        ss = sorted(x[j] for x in sim_seats) if sim_seats else [seats[j]]
        out[j] = {"votes": round(point[j]), "pct": round(100 * point[j] / tot, 2), "seats": seats[j],
                  "lo": ss[int(0.1 * (len(ss) - 1))], "hi": ss[int(0.9 * (len(ss) - 1))],
                  "p_pass": round(sum(1 for x in sim_seats if x[j] > 0) / len(sim_seats), 3) if sim_seats else None}
    return out, sim_seats


def seats_to_shares(avg):
    """Poll average seats -> national vote shares (midpoint of the seat band; 2.2% under the threshold)."""
    q = {j: a for j, a in avg.items() if a >= 1}
    units = sum(a + 0.5 for a in q.values())
    low = {j: 0.022 for j, a in avg.items() if a < 1}
    left = 1 - sum(low.values()) - 0.01
    return {**{j: left * (a + 0.5) / units for j, a in q.items()}, **low}


def final_poll_prior(e, path=os.path.join(ROOT, "site", "data", "final_polls.json")):
    """Pre-election prior for a backtest: the average of the final week's polls."""
    el = next((x for x in json.load(open(path, encoding="utf-8"))["elections"] if x["id"] == e), None)
    if not el:
        return {}
    lists = {j for p in el["polls"] for j in p["seats"]}
    avg = {j: sum(p["seats"].get(j, 0) for p in el["polls"]) / len(el["polls"]) for j in lists}
    return seats_to_shares(avg)


# ---------------------------------------------------------------- backtest
def counting_order(rows, scheme, rng, base):
    boxes = [r for r in rows if not r["env"] and r["code"] is not None]
    if scheme == "random":
        rng.shuffle(boxes)
        return boxes
    by_loc = collections.defaultdict(list)
    for r in boxes:
        by_loc[r["code"]].append(r)
    locs = list(by_loc)
    rng.shuffle(locs)
    if scheme == "small_first":
        locs.sort(key=lambda c: sum(r["elig"] for r in by_loc[c]) * rng.uniform(0.3, 3))
    elif scheme == "arab_haredi_late":
        late = {c for c in locs if base.group.get(c) in ("arab", "druze") or base.stratum.get(c) == "haredi"}
        locs = [c for c in locs if c not in late] + [c for c in locs if c in late]
    out = []
    # localities report box by box, interleaved with the next few localities
    window = collections.deque()
    for c in locs:
        window.append(list(by_loc[c]))
        while len(window) > 4 or (c == locs[-1] and window):
            k = rng.randrange(len(window))
            out.append(window[k].pop())
            if not window[k]:
                del window[k]
    return out


def backtest(base_e, cur_e, src, core, schemes, n_orders, n_boot, checkpoints, seed=11):
    (_, base_rows), _ = load_election(src, base_e)
    (cur_cols, cur_rows), _ = load_election(src, cur_e)
    B = Baseline(base_e, base_rows, core)
    main = list(R.PARTIES[cur_e])
    keep = set(main)
    official = {p["id"]: p["seats"] for p in next(e for e in core["elections"] if e["id"] == cur_e)["parties"]}
    final_valid = {p["id"]: p["votes"] for p in next(e for e in core["elections"] if e["id"] == cur_e)["parties"]}
    nb = [p for p, v in R.PARTIES[cur_e].items() if v[2] == "nb"]
    base_elig = sum(L["elig"] for L in B.loc.values())
    cur_elig = sum(r["elig"] for r in cur_rows if not r["env"] and r["code"] is not None)
    g = cur_elig / base_elig      # live: published register size / baseline register
    camp = {p: ("coal" if v[2] == "nb" else "arab" if v[2] == "arab" else "opp") for p, v in R.PARTIES[cur_e].items()}
    proj = Projector(B, main, BASE_MAP[cur_e], g, AGREEMENTS[cur_e], prior=final_poll_prior(cur_e), camp=camp)
    rng = random.Random(seed)
    near = [p for p in main if 0.02 <= final_valid.get(p, 0) / sum(final_valid.values()) <= 0.045]
    results = []
    for scheme in schemes:
        for k in range(n_orders):
            order = counting_order(cur_rows, scheme, rng, B)
            total = sum(r["elig"] for r in order)
            counted, done, ci = {}, 0, 0
            for r in order:
                add_row(counted.setdefault(r["code"], new_unit()), r, keep)
                done += r["elig"]
                while ci < len(checkpoints) and done >= checkpoints[ci] * total - 1e-6:
                    point, sims = proj.run(counted, n_boot=n_boot, seed=k * 100 + ci)
                    summ, sim_seats = summarize(proj, point, sims)
                    err = sum(abs(summ[p]["seats"] - official.get(p, 0)) for p in main)
                    bloc = sum(summ[p]["seats"] for p in nb) - sum(official.get(p, 0) for p in nb)
                    cover = sum(1 for p in main if summ[p]["lo"] <= official.get(p, 0) <= summ[p]["hi"]) / len(main)
                    calls = {p: (summ[p]["p_pass"], official.get(p, 0) > 0) for p in near}
                    nb_sims = sorted(sum(s_[p] for p in nb) for s_ in sim_seats) or [0]
                    nb_true = sum(official.get(p, 0) for p in nb)
                    bloc_cover = nb_sims[int(0.1 * (len(nb_sims) - 1))] <= nb_true <= nb_sims[int(0.9 * (len(nb_sims) - 1))]
                    results.append({"scheme": scheme, "order": k, "counted": checkpoints[ci], "seat_abs_err": err,
                                    "bloc_err": bloc, "cover80": round(cover, 3), "bloc_cover": bloc_cover, "near": calls})
                    ci += 1
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["backtest"])
    ap.add_argument("--base", default="K24")
    ap.add_argument("--cur", default="K25")
    ap.add_argument("--src", default=os.path.join(ROOT, "data", "raw", "mirror"))
    ap.add_argument("--core", default=os.path.join(ROOT, "site", "data", "core.json"))
    ap.add_argument("--orders", type=int, default=6)
    ap.add_argument("--boot", type=int, default=40)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    core = json.load(open(a.core, encoding="utf-8"))
    cps = [0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 0.9, 1.0]
    res = backtest(a.base, a.cur, a.src, core, ["random", "locality", "small_first", "arab_haredi_late"],
                   a.orders, a.boot, cps)
    agg = collections.defaultdict(list)
    for r in res:
        agg[(r["scheme"], r["counted"])].append(r)
    print(f"backtest {a.base} -> {a.cur}: mean |seat error| summed over lists, bloc error, 80% band coverage")
    for (sc, cp), rs in sorted(agg.items()):
        n = len(rs)
        print(f"{sc:18s} {cp:5.2f}  seats {sum(r['seat_abs_err'] for r in rs) / n:5.1f}  "
              f"bloc {sum(abs(r['bloc_err']) for r in rs) / n:4.1f}  cover {sum(r['cover80'] for r in rs) / n:.2f}  "
              f"bloc80 {sum(r['bloc_cover'] for r in rs) / n:.2f}  "
              + " ".join(f"{p}:{sum(r['near'][p][0] or 0 for r in rs) / n:.2f}{'✓' if rs[0]['near'][p][1] else '✗'}"
                         for p in rs[0]["near"]))
    if a.out:
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------- frames for the page
def make_frame(proj, counted, env_counted, meta, n_boot=200, seed=7, final=None):
    """One snapshot of the count for the dashboard: what is counted, and the projection.

    meta: {list: {name, letters, color, dark, bloc}} with bloc 'coal'|'opp'|'arab';
    final: official seats to show once the count is complete (replay only)."""
    blocs = {j: m.get("bloc", "opp") for j, m in meta.items()}
    B = proj.B
    point, sims = proj.run(counted, env_counted, n_boot=n_boot, seed=seed)
    summ, sim_seats = summarize(proj, point, sims)
    lists = [j for j in proj.lists if j != OTHER]
    cv = collections.Counter()
    tot = {"elig": 0, "voters": 0, "valid": 0, "boxes": 0}
    for C in counted.values():
        for k in tot:
            tot[k] += C[k]
        for j, n in C["votes"].items():
            cv[j] += n
    if env_counted:
        for j, n in env_counted["votes"].items():
            cv[j] += n
        tot["valid"] += env_counted["valid"]
    expected = sum(L["elig"] for L in B.loc.values()) * proj.g
    counted_seats = proj.seats(cv) if tot["valid"] else {j: 0 for j in lists}
    # turnout in the counted part, against the same localities last time
    groups = collections.defaultdict(lambda: {"elig": 0, "voters": 0, "base_t": 0.0, "exp": 0.0})
    for c, L in B.loc.items():
        gname = "haredi" if B.stratum[c] == "haredi" else B.group[c]
        groups[gname]["exp"] += L["elig"] * proj.g
        C = counted.get(c)
        if C and L["elig"]:
            groups[gname]["elig"] += C["elig"]
            groups[gname]["voters"] += C["voters"]
            groups[gname]["base_t"] += C["elig"] * L["voters"] / L["elig"]
    sect = {k: {"counted": round(v["elig"] / v["exp"], 3) if v["exp"] else 0,
                "turnout": round(v["voters"] / v["elig"], 4) if v["elig"] else None,
                "turnout_base": round(v["base_t"] / v["elig"], 4) if v["elig"] else None}
            for k, v in groups.items()}
    bloc_tot = collections.defaultdict(list)
    for s in sim_seats:
        agg = collections.Counter()
        for j in lists:
            agg[blocs.get(j, "opp")] += s[j]
        for b in ("coal", "opp", "arab"):
            bloc_tot[b].append(agg[b])
    pt = collections.Counter()
    for j in lists:
        pt[blocs.get(j, "opp")] += summ[j]["seats"]
    out = {
        "counted": {"share": round(min(1.0, tot["elig"] / expected), 4) if expected else 0, "boxes": tot["boxes"],
                    "elig": tot["elig"], "voters": tot["voters"], "valid": tot["valid"],
                    "turnout": round(tot["voters"] / tot["elig"], 4) if tot["elig"] else None,
                    "envelopes": bool(env_counted)},
        "lists": [{"id": j, "name": meta.get(j, {}).get("name", j), "letters": meta.get(j, {}).get("letters", ""),
                   "color": meta.get(j, {}).get("color", "#94a3b8"), "dark": meta.get(j, {}).get("dark", "#64748b"),
                   "bloc": blocs.get(j, "opp"),
                   "votes": cv[j], "pct": round(100 * cv[j] / tot["valid"], 2) if tot["valid"] else 0,
                   "seats_counted": counted_seats.get(j, 0), "votes_proj": summ[j]["votes"], "pct_proj": summ[j]["pct"],
                   "seats": summ[j]["seats"], "lo": summ[j]["lo"], "hi": summ[j]["hi"], "p_pass": summ[j]["p_pass"]}
                  for j in lists],
        "blocs": {b: {"seats": pt[b],
                      "lo": sorted(v)[int(0.1 * (len(v) - 1))] if v else pt[b],
                      "hi": sorted(v)[int(0.9 * (len(v) - 1))] if v else pt[b],
                      "p61": round(sum(1 for x in v if x >= 61) / len(v), 3) if v else None}
                  for b, v in ((b, bloc_tot[b]) for b in ("coal", "opp", "arab"))},
        "sectors": sect,
    }
    if final:
        out["final"] = final
    return out
