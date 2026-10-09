"""Check and publish the hourly turnout history for the election-day tab.

Reads pipeline/reference/turnout_hourly.json (official CEC hourly series,
curated with sources) and writes site/data/turnout_history.json, adding for
every election the ratio final / hourly figure that the page uses to project
the end-of-day turnout.

Run: python3 pipeline/build_turnout.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ref = json.load(open(os.path.join(ROOT, "pipeline", "reference", "turnout_hourly.json"), encoding="utf-8"))
    hours = ref["hours"]
    for e, d in ref["elections"].items():
        v = d["values"]
        assert len(v) == len(hours), e
        assert all(a < b for a, b in zip(v, v[1:])), f"{e}: cumulative turnout must rise through the day"
        assert abs(v[-1] - d["final"]) < 1.5, f"{e}: 22:00 figure far from the final"
        if "voters" in d:
            assert all(a < b for a, b in zip(d["voters"], d["voters"][1:])), e
        d["ratio"] = [round(d["final"] / x, 4) for x in v]
    out = os.path.join(ROOT, "site", "data", "turnout_history.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(ref, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out}: {len(ref['elections'])} elections")


if __name__ == "__main__":
    main()
