"""The operator's request (ops/request.json on the ops-control branch), checked as Run workflow checks its inputs.

    WORKFLOW=live FIELDS='drill reset minutes runner restart' python3 ops/check_request.py ops/request.json

The session's token can push but not dispatch or cancel runs, so a push of ops/request.json to ops-control stands in
for Run workflow (docs/ELECTION_DAY.md, "בקשות דרך ops-control"). A request names one workflow; WORKFLOW is the name
of the workflow asking, FIELDS the dispatch inputs it takes. Writes run=true and each field given, normalised, to
GITHUB_OUTPUT when the request names WORKFLOW, and run=false (exit 0, quietly) when it names another one. Exit 1 with
an ::error:: line when the request does not parse, names no known workflow, has a field WORKFLOW does not take, or a
value that does not fit: the run goes red, as Run workflow would refuse it. Values cannot inject anything into
GITHUB_OUTPUT or the log.

Run by the request step of live.yml, discover.yml, net-check.yml and daily.yml (the same step in all four), and by
live.yml's loop on a later {"workflow": "live", "restart": true} request, so that a running feed stops only for a
request its successor will take (pipeline/test_live.py, 11b). Python 3.9 or later (a self-hosted runner's own).
"""
import json
import os
import re
import sys

WORKFLOWS = ("live", "discover", "net-check", "daily", "none")     # none: the placeholder on main
RUNNERS = ("ubuntu-latest", "self-hosted")    # another label would leave the run waiting for a runner, holding its group


def safe(x):          # request text in a log line: no newlines, no workflow commands
    return re.sub(r"[^\w .,:/=+()'\"\[\]-]", "?", str(x))[:80]


def fail(msg):
    print(f"::error::ops/request.json: {msg}")
    sys.exit(1)


def flag(v):
    return str(v).lower() if isinstance(v, bool) else None


def whole(v):         # whole minutes, as Run workflow's minutes (the feed's guard checks them again)
    if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 9999:
        return str(v)
    return str(int(v)) if isinstance(v, str) and re.fullmatch(r"[0-9]{1,4}", v) else None


def label(v):         # a runner label: GitHub's servers or the computer in Israel
    return v if isinstance(v, str) and v in RUNNERS else None


def mode(v):
    return v if isinstance(v, str) and v in ("auto", "full", "quick") else None


def urls(v):          # addresses for the scan: a list, or one string separated by spaces
    v = v.split() if isinstance(v, str) else v
    ok = isinstance(v, list) and 0 < len(v) <= 20 and all(
        isinstance(u, str) and re.fullmatch(r"https?://[^\s\"'`<>\\]{1,500}", u) for u in v)
    return " ".join(v) if ok else None


CHECKS = {"drill": flag, "reset": flag, "restart": flag, "minutes": whole, "runner": label, "mode": mode, "urls": urls}
WANT = {"drill": "true or false", "reset": "true or false", "restart": "true or false", "minutes": "whole minutes",
        "runner": " or ".join(RUNNERS), "mode": "auto, full or quick", "urls": "http(s) addresses"}


def main(path):
    me, fields = os.environ["WORKFLOW"], os.environ.get("FIELDS", "").split()
    try:
        with open(path, encoding="utf-8") as f:
            req = json.load(f)
    except FileNotFoundError:
        fail("not on this commit: make ops-control from origin/main (docs/ELECTION_DAY.md)")
    except (ValueError, OSError) as exc:
        fail(f"does not parse: {safe(exc)}")
    if not isinstance(req, dict):
        fail("not a JSON object")
    wf, rid = req.get("workflow"), safe(req.get("id", "-"))
    if wf not in WORKFLOWS:
        fail(f"workflow is {safe(wf)!r}, not one of {', '.join(WORKFLOWS)}")
    out = {"run": "false"}
    if wf != me:
        print(f"request {rid} is for {wf}, not {me}: nothing to do")
    else:
        extra = [safe(k) for k in req if k not in ("workflow", "id") and k not in fields]
        if extra:
            fail(f"{me} takes {', '.join(fields) or 'no fields'} (besides workflow and id), not {', '.join(extra)}")
        out["run"] = "true"
        for k in fields:
            if k in req:
                v = CHECKS[k](req[k])
                if v is None:
                    fail(f"{k}: {safe(json.dumps(req[k]))} is not a valid value ({WANT[k]})")
                out[k] = v
        said = " ".join(f"{k}={v}" for k, v in out.items() if k != "run") or "no fields"
        print(f"request {rid}: {me} {said}")
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"Request {rid} (ops/request.json on ops-control): {me} {said}\n")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.writelines(f"{k}={v}\n" for k, v in out.items())


if __name__ == "__main__":
    main(sys.argv[1])
