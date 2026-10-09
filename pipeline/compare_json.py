"""Print the paths at which two JSON files differ (used to compare a rebuild with the committed data).

Run: python3 pipeline/compare_json.py OLD.json NEW.json [--max 40]
"""
import argparse
import json


def walk(a, b, path, out, limit):
    if len(out) >= limit:
        return
    if type(a) is not type(b):
        out.append((path, a, b))
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            walk(a.get(k, "<missing>"), b.get(k, "<missing>"), f"{path}.{k}", out, limit)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append((f"{path}[len]", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", out, limit)
    elif a != b:
        out.append((path, a, b))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--max", type=int, default=40)
    a = ap.parse_args()
    out = []
    walk(json.load(open(a.old, encoding="utf-8")), json.load(open(a.new, encoding="utf-8")), "$", out, a.max)
    for p, x, y in out:
        print(f"{p}: {str(x)[:120]!s}  ->  {str(y)[:120]!s}")
    print(f"{len(out)} difference(s) shown (limit {a.max})")
