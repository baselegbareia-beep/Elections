"""Bader-Ofer seat allocation (Knesset Elections Law, section 81).

1. Lists below the threshold (3.25% of valid votes) are removed.
2. General quota = qualifying votes / 120; each list gets floor(votes / quota).
3. Remaining seats go one at a time to the "unit" with the highest
   votes / (seats + 1). A surplus-vote agreement makes two lists one unit,
   provided both passed the threshold.
4. Seats won by an agreement unit are split between its two lists with the
   same rule (D'Hondt between the pair).
"""
from math import floor


def allocate(votes, seats=120, threshold=0.0325, agreements=()):
    """votes: {list_id: int}. agreements: iterable of (a, b) pairs.
    Returns {list_id: seats} for every list in `votes`."""
    total_valid = sum(votes.values())
    qualify = {k: v for k, v in votes.items() if v >= threshold * total_valid}
    result = {k: 0 for k in votes}
    if not qualify:
        return result

    quota = sum(qualify.values()) / seats
    for k, v in qualify.items():
        result[k] = floor(v / quota)

    # Build units: a pair only counts if both partners qualified.
    unit_of = {k: (k,) for k in qualify}
    for a, b in agreements:
        if a in qualify and b in qualify and len(unit_of[a]) == 1 and len(unit_of[b]) == 1:
            unit_of[a] = unit_of[b] = (a, b)
    units = sorted(set(unit_of.values()))

    def unit_votes(u):
        return sum(qualify[k] for k in u)

    def unit_seats(u):
        return sum(result[k] for k in u)

    remaining = seats - sum(result.values())
    unit_extra = {u: 0 for u in units}
    for _ in range(remaining):
        best = max(units, key=lambda u: (unit_votes(u) / (unit_seats(u) + unit_extra[u] + 1), unit_votes(u)))
        unit_extra[best] += 1

    for u, extra in unit_extra.items():
        if len(u) == 1:
            result[u[0]] += extra
            continue
        # Split the unit's total seats between partners by D'Hondt from zero.
        total = unit_seats(u) + extra
        split = {k: 0 for k in u}
        for _ in range(total):
            k = max(u, key=lambda x: (qualify[x] / (split[x] + 1), qualify[x]))
            split[k] += 1
        for k in u:
            result[k] = split[k]
    return result


if __name__ == "__main__":
    # K25 official national totals (votes25.bechirot.gov.il) → official seats.
    k25 = {"מחל": 1115336, "פה": 847435, "ט": 516470, "כן": 432482, "שס": 392964, "ג": 280194,
           "ל": 213687, "עם": 194047, "ום": 178735, "אמת": 175992, "מרצ": 150793, "ד": 138617,
           "ב": 56775, "other": 71215}
    print(allocate(k25))
