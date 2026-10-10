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
* The expected electorate of a locality is its baseline register times the
  national register growth times its stratum's own growth (the Haredi and
  Bedouin registers grow faster than the rest).
* Double envelopes are counted last; their size follows the baseline envelopes
  scaled by turnout and register growth (uncertain until the CEC announces the
  total), their composition the baseline envelope composition scaled by each
  list's national ratio, blended with the counted envelopes as they come in.
* Seats: Bader-Ofer with the surplus agreements. Uncertainty: bootstrap of the
  counted localities within each stratum, plus envelope noise.

backtest() replays a past election with the one before it as the baseline, in
simulated counting orders (rough sketches of a night, see counting_order), and
measures the error at each stage of the count. The noise constants came from a
sweep over both simulated backtests, 2022 and 2021 (CALIBRATED_ON); the real
2021 counting order (build_replay.py, accuracy_real) is the hold-out. The sweep
predates the LM-1..6 fixes and on the corrected model the 80% bands over-cover
(the backtests put the result inside them 93-100% of the time); the constants
are kept as they are, since too wide is the safe side with three new lists and a
four-year-old baseline.

Run: python3 pipeline/live_model.py backtest --base K24 --cur K25
     python3 pipeline/live_model.py prior      (the 2026 prior, as the page computes it)
     python3 pipeline/live_model.py growth     (register growth per stratum)
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import random
import statistics
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
    # 2021: Yesh Atid and Blue & White both come out of the 2020 Blue & White (פה); the 2020 letters כן
    # belonged to a 0.02% list, so mapping כן -> כן projected Blue & White at zero (LM-1)
    "K24": {"מחל": ["מחל"], "פה": ["פה"], "כן": ["פה"], "שס": ["שס"], "ג": ["ג"], "ל": ["ל"], "ט": ["טב"],
            "ב": ["טב"], "אמת": ["אמת"], "מרצ": ["אמת"], "ודעם": ["ודעם"], "עם": ["ודעם"], "ת": []},
    # 2026 lists (ids as in polls_2026.json) -> 2022 ballot letters
    "K26": {"Likud": ["מחל"], "Yashar": ["כן"], "Together": ["פה"], "The Democrats": ["אמת", "מרצ"],
            "Yisrael Beiteinu": ["ל"], "Shas": ["שס"], "UTJ": ["ג"], "Otzma Yehudit": ["ט"],
            "Religious Zionism": ["ט"], "Joint List": ["ום", "ד"], "Ra'am": ["עם"], "National Unity": ["כן"],
            "Amcha Yisrael": [], "Reservists": [], "Haredi Public": []},
}
AGREEMENTS = {
    "K25": [("מחל", "ט"), ("פה", "כן"), ("שס", "ג"), ("ל", "עם"), ("אמת", "מרצ"), ("ום", "ד")],
    # 2021: Likud–RZP, Yesh Atid–YB, Shas–UTJ, Labor–Meretz, Yamina–New Hope; reproduces the official seats
    "K24": [("מחל", "ט"), ("פה", "ל"), ("שס", "ג"), ("אמת", "מרצ"), ("ב", "ת")],
}
OWN_MIN = 0.2
K_LEVEL = {"N": 30000, "G": 15000, "S": 6000}   # pseudo-votes of the parent level (shrinkage)
PRIOR_SD = 0.15        # relative error of the pre-election prior per list
STRATUM_SD = 0.10      # stratum random effect, scaled by how much the stratum leans on its parent
SYS_SD = 0.07          # shared shift of the Netanyahu camp in the uncounted vote (log scale, at 0% counted)
SYS_SD_ARAB = 0.12     # shared shift of the Arab lists in the uncounted vote
THIN_WIDEN = 2.0       # extra shared error when the uncounted vote sits in strata with almost nothing counted
                       # (scaled by the national count's weight: before anything is counted the prior's own error is the whole story, LM-A)
LIST_SD = 0.12         # independent error of each list in the uncounted vote (log scale, at 0% counted)
LIST_NEW = 1.8         # multiplier for lists without a clean predecessor
# Lists without a predecessor get this share of their national prior in Arab localities until those are
# counted, and correspondingly more elsewhere so that the national prior is kept (LM-D). Assumption from
# 2021: New Hope took 0.18x its national share in Arab localities but 0.95x in Druze localities, so the
# factor applies to the Arab group only (LM-3).
ARAB_NEW = 0.2
ENV_DONE = 0.97        # counted envelopes at this share of the CEC's announced total: the count is complete
ENV_BLEND_K = 150000   # pseudo-votes: the envelope mix moves from the baseline to the counted envelopes
ENV_SIZE_SD = 0.25     # relative uncertainty of the envelope total before it is announced (the total is at least what is counted, LM-C)
ENV_SHOCK = 1.0        # scale of the camp and list errors applied to the envelope mix
GROWTH_CAP = (0.95, 1.15)   # per-stratum register growth relative to the nation, K21 -> baseline
ARAB_GROUP = {"negev": "arab_negev", "north_bedouin": "arab_north", "galilee": "arab_north",
              "nazareth": "arab_north", "christian": "arab_north", "wadi_ara": "arab_triangle",
              "triangle_south": "arab_triangle", "mixed_town": "arab_north", "jerusalem": "arab_other",
              "mixed": "arab_other"}
# Register growth of each stratum relative to the national register, April 2019 -> 2022 (the closest
# analog of 2022 -> 2026), computed by stratum_growth() from data/raw/mirror and used when that
# directory is absent (the GitHub feed has only data/official): python3 pipeline/live_model.py growth
STRATUM_GROWTH = {"K25": {"arab_negev": 1.108, "arab_north": 1.016, "arab_other": 1.031, "arab_triangle": 1.03,
                          "druze": 1.009, "haredi": 1.073, "j0_big": 0.99, "j0_small": 0.989, "j0_town": 1.001,
                          "j1_big": 0.988, "j1_small": 1.005, "j1_town": 1.014, "j2_big": 0.978, "j2_small": 1.001,
                          "j2_town": 1.003, "j3_big": 0.98, "j3_small": 1.004, "j3_town": 0.997, "j4_big": 1.016,
                          "j4_small": 1.026, "j4_town": 1.015, "mixed": 0.976}}


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


def stratum_growth(base, src, from_e="K21"):
    """Register growth of each stratum between from_e and the baseline, relative to the national
    growth over the same localities, capped (GROWTH_CAP). {} when from_e cannot be loaded."""
    try:
        (_, rows), _ = load_election(src, from_e)
    except Exception:
        return {}
    old = collections.Counter()
    for r in rows:
        if not r["env"] and r["code"] is not None:
            old[r["code"]] += r["elig"]
    both = [c for c, L in base.loc.items() if old.get(c) and L["elig"]]
    nat = sum(base.loc[c]["elig"] for c in both) / max(1, sum(old[c] for c in both))
    by_s = collections.defaultdict(lambda: [0, 0])
    for c in both:
        # a few new towns (Harish grew 3.5x) would otherwise set the factor of their whole stratum
        if 1 / 1.5 <= base.loc[c]["elig"] / old[c] / nat <= 1.5:
            by_s[base.stratum[c]][0] += old[c]
            by_s[base.stratum[c]][1] += base.loc[c]["elig"]
    return {s: round(min(GROWTH_CAP[1], max(GROWTH_CAP[0], v[1] / v[0] / nat)), 3) for s, v in sorted(by_s.items()) if v[0]}


class Baseline:
    """The previous election, summed per locality, with a stratum for every locality."""

    def __init__(self, e, rows, core, src=os.path.join(ROOT, "data", "raw", "mirror")):
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
        # register growth per stratum, from the oldest mirrored election to this one (no look-ahead)
        self.growth = stratum_growth(self, src) or STRATUM_GROWTH.get(e, {})


def env_total(ratio, q, sd=ENV_SIZE_SD):
    """Quantile q of the envelope total relative to its baseline estimate, N(1, sd) given that the
    total is at least `ratio` x the estimate (what is already counted, LM-C). Beyond the normal's
    reach the total is taken as what is counted."""
    nd = statistics.NormalDist(1.0, sd)
    lo = nd.cdf(ratio)
    return max(ratio, nd.inv_cdf(min(1 - 1e-9, max(1e-9, lo + (1 - lo) * q))))


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
        self.env_override = None      # expected envelope votes announced by the CEC, if any
        self.B, self.lists, self.g, self.agreements = base, list(cur_lists) + [OTHER], g, agreements
        self.prior, self.prior_t = dict(prior or {}), prior_t
        # a prior that adds up to one over the lists leaves the rest to the small lists (OTHER), in case
        # the caller dropped poll_shares()' OTHER entry when mapping list ids to letters
        if OTHER not in self.prior and self.prior and 0 <= 1 - sum(self.prior.values()) <= 0.05:
            self.prior[OTHER] = 1 - sum(self.prior.values())
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
        # share of the baseline locality vote cast in Arab localities (ARAB_NEW, LM-D)
        self.arab_share = sum(L["valid"] for c, L in base.loc.items() if base.group[c] == "arab") / nv
        # a predecessor that is not a baseline list, or has no baseline votes, would project the list at
        # zero everywhere it is not yet counted (LM-1): fail loudly instead
        for j in cur_lists:
            if self.preds[j] is None:
                continue
            bad = [p for p in self.preds[j] if p not in R.PARTIES[base.e]]
            if bad:
                raise ValueError(f"{j}: predecessor {bad} is not a {base.e} list ({sorted(R.PARTIES[base.e])})")
            if not self.base_nat[j] > 0:
                raise ValueError(f"{j}: predecessors {self.preds[j]} have no votes in the {base.e} baseline")

    def expected(self, c):
        """Expected electorate of a baseline locality now: register growth, nationally and in its stratum."""
        return self.B.loc[c]["elig"] * self.g * self.B.growth.get(self.B.stratum[c], 1.0)

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
        # New lists (no predecessor) are assumed to draw far less in Arab localities (ARAB_NEW) and
        # correspondingly more everywhere else, so that their national prior is preserved (LM-D).
        a = self.arab_share
        new = lambda f: {**prior, "r": {j: v * f if self.preds[j] is None else v for j, v in prior["r"].items()}}  # noqa: E731
        prior_arab, prior_rest = new(ARAB_NEW), new((1 - ARAB_NEW * a) / (1 - a))
        N_rest = level(st.get("N"), prior_rest, K_LEVEL["N"], 0)
        groups = {g: level(st.get("G:" + g), prior_arab if g == "arab" else prior_rest if g == "druze" else N_rest,
                           K_LEVEL["G"], STRATUM_SD) for g in sorted(set(B.group.values()))}
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

    def remainder(self, counted):
        """Uncounted voters per baseline locality (expected minus counted), scaled so that together
        they equal the register minus everything counted: once every box is in, nothing is left to
        project. The same split gives make_frame its sector shares (LM-G)."""
        rems = {}
        for c, L in self.B.loc.items():
            C = counted.get(c)
            r_ = self.expected(c) - (C["elig"] if C else 0)
            if r_ > 0 and L["elig"] and L["valid"]:
                rems[c] = r_
        counted_elig = sum(C["elig"] for C in counted.values())
        register = sum(L["elig"] for L in self.B.loc.values()) * self.g
        tot_rem = sum(rems.values())
        scale = max(0.0, register - counted_elig) / tot_rem if tot_rem > 0 else 0.0
        return {c: r * scale for c, r in rems.items()}

    def estimate(self, counted, codes, env_counted=None, rng=None, rems=None):
        """Projected votes still to come per list: (uncounted boxes part, envelopes part, envelope info).

        The envelope info is None without baseline envelopes, else {"expected": total expected,
        "mix": share per list of the envelopes still to come}, for the size draws in run().
        rems: remainder(counted), when the caller has it already."""
        B = self.B
        st = self.stats(counted, codes)
        N, strata = self.levels(st, rng)
        boxes = collections.Counter()
        if rems is None:
            rems = self.remainder(counted)
        for c, rem in rems.items():
            L, C = B.loc[c], counted.get(c)
            E = self.expected(c)
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
        # double envelopes still to come: expected total from the baseline (or the CEC's announced
        # total), minus what is counted. The count is complete only against an announced total;
        # the baseline estimate missed 2021 by a third (LM-2), so without one the total is taken as
        # at least what is counted (the median of the size draw in run(), LM-C) and the remainder
        # never closes. Their mix moves from the baseline mix (scaled by each list's national ratio)
        # to the counted envelopes' mix as those come in: the first envelope batches are not
        # representative.
        env, info = collections.Counter(), None
        have = env_counted["valid"] if env_counted else 0
        if B.env["valid"]:
            expected = self.env_override or B.env["valid"] * self.g * N["t"]
            if rng is None:
                self.env_expected = expected
            if self.env_override:
                rem = 0.0 if have >= ENV_DONE * self.env_override else max(0.0, expected - have)
            else:
                rem = expected * env_total(have / expected, 0.5) - have
            sh = {j: N["r"][j] * self.benv[j] if self.preds[j] is not None else N["r"][j] for j in self.lists}
            s = sum(sh.values()) or 1
            w = have / (have + ENV_BLEND_K)
            mix = {j: w * (env_counted["votes"].get(j, 0) / have if have else 0) + (1 - w) * sh[j] / s for j in self.lists}
            for j in self.lists:
                env[j] = rem * mix[j]
            info = {"expected": expected, "mix": mix}
        return boxes, env, info

    def seats(self, votes):
        # every list gets a key, also one with no votes in a draw (allocate() only returns the lists given)
        alloc = allocate({j: int(round(v)) for j, v in votes.items() if v > 0}, agreements=self.agreements)
        return {j: alloc.get(j, 0) for j in self.lists if j != OTHER}

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
        env_have = env_counted["valid"] if env_counted else 0
        if env_counted:
            for j in self.lists:
                have[j] += env_counted["votes"].get(j, 0)
        rems = self.remainder(counted)
        boxes, env, _ = self.estimate(counted, codes, env_counted, rems=rems)
        point = {j: have[j] + boxes[j] + env[j] for j in self.lists}
        rng = random.Random(seed)
        by_s = collections.defaultdict(list)
        for c in codes:
            by_s[self.B.stratum[c]].append(c)
        left = sum(boxes.values()) / max(1.0, sum(point.values()))   # share of the vote still projected
        # share of the uncounted electorate in strata with too little counted to stand on their own:
        # those estimates are borrowed from other places, so the shared error is widened, in step with
        # the national count's weight: with nothing counted the estimate is the prior itself, whose
        # own error (PRIOR_SD) is already in the draws (LM-A)
        st = self.stats(counted, codes)
        rem_s, thin = collections.Counter(), 0.0
        for c, r_ in rems.items():
            rem_s[self.B.stratum[c]] += r_          # only the distribution across strata matters here
        tot_rem = sum(rem_s.values()) or 1.0
        for k, v in rem_s.items():
            if st[k]["valid"] < K_LEVEL["S"]:
                thin += v / tot_rem
        w_n = st["N"]["valid"] / (st["N"]["valid"] + K_LEVEL["N"])
        scale = left ** 0.5 * (1 + THIN_WIDEN * thin * w_n)
        self.last_diag = {"left": round(left, 3), "thin": round(thin, 3), "w_n": round(w_n, 3), "scale": round(scale, 3)}
        env_done = bool(self.env_override) and env_have >= ENV_DONE * self.env_override
        sims = []
        for _ in range(n_boot):
            sample = [rng.choice(v) for v in by_s.values() for _ in v]
            b, e, info = self.estimate(counted, sample, env_counted, rng, rems=rems)
            b = self.shock(b, rng, scale)
            if info and not env_done:
                # the envelope total is uncertain until the CEC announces it (5.5%–9.7% of voters in
                # 2019–2022; the 2021 total was 37% above the baseline estimate): draw the total, and
                # what is still to come is the drawn total minus the counted envelopes. Without an
                # announced total the draw is conditional on the total being at least what is
                # counted, so the band stays open past the baseline estimate (LM-C).
                if self.env_override:
                    f_ = max(0.0, rng.gauss(1, 0.05))
                else:
                    f_ = env_total(env_have / info["expected"], rng.random())
                rem = max(0.0, info["expected"] * f_ - env_have)
                e = self.shock({j: rem * v for j, v in info["mix"].items()}, rng, ENV_SHOCK)
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


# ---------------------------------------------------------------- pre-election prior
OTHER_SHARE, CENSORED, NEVER_SEATED = 0.008, 0.022, 0.01   # as in core.js: small lists; a list a poll puts at 0


def poll_shares(polls, half_life=10.0, adjust_house=True):
    """National vote share per list from the polls, exactly as the page computes it (core.js
    pollAverage + voteSharesFromAverage, ported line by line and checked against core.js under node).

    Weights: recency (half-life in days, 28-day window) x sample size, damped per firm so one company
    cannot dominate. Seat average: house effects (each pollster's mean deviation, shrunk k/(k+3))
    removed, rescaled to 120. Shares: a list averaging under 3 seats, or put at 0 by any current poll,
    is estimated poll by poll (its filed %, else the midpoint of its seat band, else an imputed share
    below the threshold); the other lists split what is left in proportion to seats + 0.5.
    polls: {"parties": [{"id"}], "polls": [{"date", "house"|"pollster", "seats", "pct", "n"}]},
    the last poll being the latest. Returns {list: share} plus OTHER."""
    P, ids = polls["polls"], [p["id"] for p in polls["parties"]]
    house = lambda p: p.get("house") or p.get("pollster") or ""         # noqa: E731
    firm = lambda p: p.get("firm") or house(p)                           # noqa: E731
    seats = lambda p, j: p["seats"].get(j) or 0                          # noqa: E731
    filed = lambda p, j: (p.get("pct") or {}).get(j)                     # noqa: E731
    as_of = dt.date.fromisoformat(P[-1]["date"])
    age = [(as_of - dt.date.fromisoformat(p["date"])).days for p in P]
    by_firm = collections.Counter(firm(p) for p, a in zip(P, age) if 0 <= a <= 28)
    w = [0.5 ** (a / half_life) * min(1.4, max(0.7, math.sqrt((p.get("n") or 700) / 700))) / math.sqrt(by_firm[firm(p)] or 1)
         if 0 <= a <= 28 else 0.0 for p, a in zip(P, age)]
    known = [p for p, a in zip(P, age) if a >= 0]
    he = {}
    if adjust_house and known:
        mean = {j: sum(seats(p, j) for p in known) / len(known) for j in ids}
        for h in {house(p) for p in known}:
            ps = [p for p in known if house(p) == h]
            he[h] = {j: len(ps) / (len(ps) + 3) * (sum(seats(p, j) for p in ps) / len(ps) - mean[j]) for j in ids}
    tw = sum(w)
    avg = {j: (sum(wi * (seats(p, j) - he.get(house(p), {}).get(j, 0)) for p, wi in zip(P, w) if wi) / tw if tw else 0.0)
           for j in ids}
    t = sum(avg.values())
    if t > 0:
        avg = {j: max(0.0, v * 120 / t) for j, v in avg.items()}

    def mid_poll(p, s):         # midpoint of the seat band, in a poll that seated K lists
        k = sum(1 for x in p["seats"].values() if x and x > 0)
        return (1 - 0.045) * (s + 0.5) / (120 + 0.5 * k)

    def zero_share(j):          # imputed share for a poll that put the list below the threshold
        f = [filed(p, j) / 100 for p in P if not seats(p, j) > 0 and filed(p, j) is not None]
        if f:
            return sum(f) / len(f)
        return CENSORED if any(seats(p, j) > 0 for p in P) else NEVER_SEATED

    shares = {}
    by_poll = [j for j in ids if avg[j] < 3 or any(wi and not seats(p, j) > 0 for p, wi in zip(P, w))]
    for j in by_poll:
        z, sw, sv = zero_share(j), 0.0, 0.0
        for p, wi in zip(P, w):
            if not wi:
                continue
            raw = filed(p, j)
            est = raw / 100 if raw is not None else mid_poll(p, seats(p, j)) if seats(p, j) > 0 else z
            sw += wi
            sv += wi * est
        shares[j] = sv / sw if sw else z
    rest = [j for j in ids if j not in shares]
    left = 1 - OTHER_SHARE - sum(shares[j] for j in by_poll)
    units = sum(avg[j] + 0.5 for j in rest)
    for j in rest:
        shares[j] = left * (avg[j] + 0.5) / units
    shares[OTHER] = OTHER_SHARE
    return shares


def final_poll_prior(e, path=os.path.join(ROOT, "site", "data", "final_polls.json")):
    """Pre-election prior for a backtest: the final week's polls through the same estimate as 2026."""
    el = next((x for x in json.load(open(path, encoding="utf-8"))["elections"] if x["id"] == e), None)
    if not el:
        return {}
    polls = sorted(el["polls"], key=lambda p: p["date"])
    # lists polled but not on that election's ballot fold into OTHER
    lists = sorted({j for p in polls for j in p["seats"]} & set(R.PARTIES[e]))
    return poll_shares({"parties": [{"id": j} for j in lists], "polls": polls})


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
    elif scheme == "spread":
        # shaped like the real 2021 count (LM-5, LM-F), as a timeline: a locality opens at a start time
        # and its boxes come in at random moments over a duration, so 150-200 localities are partly
        # counted through most of the night. A third of the localities open by 11% counted and two
        # thirds by 47%; tiny localities close quickly, towns trickle for half the night, big cities
        # open late and trickle until about 80%; Haredi localities (Bnei Brak and Beit Shemesh
        # included, so the size rule comes first) open earlier. Fitted to the 2021 snapshots (four
        # seeds): Haredi 0.14/0.58/0.80 of its voters counted at 11/32/70% (real 0.20/0.55/0.93),
        # Arab and Druze 0.15/0.30/0.55 (real 0.09/0.32/0.65), Tel Aviv 0.57-0.83 at 70% (real 0.82),
        # 150-195 partly counted localities up to 70% (real 160-210). A rough sketch, like the other
        # schemes; the real 2021 order (build_replay) is the honest benchmark.
        timed = []
        for c, rs in by_loc.items():
            el, u, v = sum(r["elig"] for r in rs), rng.random(), rng.random()
            s, dur = u * u, 0.7 * v if len(rs) <= 5 else 0.5 + 0.4 * v
            if el >= 40000:
                s, dur = 0.1 + 0.4 * u, max(0.05, 0.8 + 0.1 * v - s)
            if base.stratum.get(c) == "haredi":
                s *= 0.7
            for r in rs:
                timed.append((s + dur * rng.random(), rng.random(), r))
        timed.sort(key=lambda x: x[:2])
        return [r for _, _, r in timed]
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


SCHEMES = ["random", "locality", "small_first", "arab_haredi_late", "spread"]
# The noise constants came from a sweep over both simulated backtests (so both read 'calibration' in
# build_replay's accuracy_roles); the real 2021 counting order (accuracy_real) is the hold-out. The
# sweep was not redone after the LM-1..6 fixes: the bands now over-cover, which is kept on purpose
# (see the module docstring).
CALIBRATED_ON = ("K25", "K24")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["backtest", "prior", "growth"])
    ap.add_argument("--base", default="K24")
    ap.add_argument("--cur", default="K25")
    ap.add_argument("--src", default=os.path.join(ROOT, "data", "raw", "mirror"))
    ap.add_argument("--core", default=os.path.join(ROOT, "site", "data", "core.json"))
    ap.add_argument("--orders", type=int, default=6)
    ap.add_argument("--boot", type=int, default=40)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    core = json.load(open(a.core, encoding="utf-8"))
    if a.cmd == "prior":
        polls = json.load(open(os.path.join(ROOT, "site", "data", "polls_2026.json"), encoding="utf-8"))
        print(json.dumps(poll_shares(polls), ensure_ascii=False, indent=1))
        return
    if a.cmd == "growth":
        (_, rows), _ = load_election(a.src, a.base)
        print(json.dumps({a.base: stratum_growth(Baseline(a.base, rows, core, a.src), a.src)}, ensure_ascii=False))
        return
    cps = [0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 0.9, 1.0]
    res = backtest(a.base, a.cur, a.src, core, SCHEMES, a.orders, a.boot, cps)
    agg = collections.defaultdict(list)
    for r in res:
        agg[(r["scheme"], r["counted"])].append(r)
    role = "calibration" if a.cur in CALIBRATED_ON else "hold-out"
    print(f"backtest {a.base} -> {a.cur} ({role}): mean |seat error| summed over lists, bloc error, 80% band coverage")
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
    # turnout in the counted part, against the same localities last time; the share counted is
    # against the sector's counted voters plus its part of what the projection still expects
    # nationally (the register minus everything counted, split as in Projector.remainder), so the
    # sectors add up to the register and all reach 100% with the headline share (LM-G); still an
    # estimate, so capped at 1
    rems = proj.remainder(counted)
    groups = collections.defaultdict(lambda: {"elig": 0, "voters": 0, "base_t": 0.0, "exp": 0.0})
    for c, L in B.loc.items():
        gname = "haredi" if B.stratum[c] == "haredi" else B.group[c]
        C = counted.get(c)
        groups[gname]["exp"] += (C["elig"] if C else 0) + rems.get(c, 0.0)
        if C and L["elig"]:
            groups[gname]["elig"] += C["elig"]
            groups[gname]["voters"] += C["voters"]
            groups[gname]["base_t"] += C["elig"] * L["voters"] / L["elig"]
    sect = {k: {"counted": round(min(1.0, v["elig"] / v["exp"]), 3) if v["exp"] else 0,
                "turnout": round(v["voters"] / v["elig"], 4) if v["elig"] else None,
                "turnout_base": round(v["base_t"] / v["elig"], 4) if v["elig"] else None}
            for k, v in groups.items()}
    # envelopes: "complete" only against a total the operator entered from the CEC's announcement
    env_have = env_counted["valid"] if env_counted else 0
    env_status = ("complete" if proj.env_override and env_have >= ENV_DONE * proj.env_override
                  else "partial" if env_have else "none")
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
                    "envelopes": bool(env_counted),
                    "env_valid": env_have, "env_status": env_status,
                    "env_override": proj.env_override or None,
                    "valid_proj": round(sum(point.values())),
                    "env_expected": round(getattr(proj, "env_expected", 0))},
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
