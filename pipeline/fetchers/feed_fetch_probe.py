#!/usr/bin/env python3
"""A runner probe through the feed's own code: does pipeline/live_fetch.py's fetch get past the CEC's WAF?

    python3 pipeline/fetchers/feed_fetch_probe.py --out DIR [--deadline 1200]

Why: since 22.10.2026 bechirot.gov.il answers urllib with an AWS WAF challenge (HTTP 202, x-amzn-waf-action), and on
23.10 the runner's own Chrome, headless with its default User-Agent, was not challenged (pipeline/fetchers/waf_probe.py,
reports/fetch/waf_probe on ops-reports). live_fetch.py now asks through such a browser when urllib is challenged
(live_fetch.request, pipeline/browser_fetch.py). This probe runs that code, not a copy of it: it imports live_fetch and
calls live_fetch.fetch, the function the feed reads the results file with, on

  media26 .../files/expb.csv and .../files/expc.csv, 6 rounds 60 s apart (12 requests, the two files 2 s apart), then
  the control media25 .../files/expc.csv (2022) once.

Each round starts the browser anew (live.yml runs a process per pass), so the browser's start is measured six times;
the WAF state between rounds is kept as the feed keeps it in state.json (a challenged host goes to the browser directly,
urllib again after live_fetch.WAF_RECHECK). Recorded per request: every attempt (urllib, browser) with its HTTP status,
x-amzn-waf-action, bytes and time, the answer's X-Cache, Server and Content-Type and first bytes, and what the feed made
of it (data accepted, or the error it would report). Until the CEC puts the 2026 files up, an answer past the WAF is
a 404 (CloudFront's error page), not a 202.

summary.md opens with the verdict, "the feed's fetch passes the WAF: yes / no / unclear", then the times and the table;
summary.json holds every record. It publishes nothing: no git, no live/ files, nothing outside --out.

The fetch contract (pipeline/fetchers/__init__.py) with the exception waf_probe.py made: live_fetch needs numpy and the
browser path needs playwright, so they are installed at run time when missing (python3 -m pip install -q; never
`playwright install`: the runner's Google Chrome is used, live_fetch.find_chrome). Never raises on one bad URL; nothing is
asked after --deadline (DEADLINE from the start; a request is bounded by the feed's own timeouts, 40 s, plus 20 s for
the browser); the summary is written after each request, each write whole; exit 0 unless the script itself crashed.

Testing against a local stand-in (pipeline/test_live.py 11k): --rewrite https://media26.bechirot.gov.il=http://127.0.0.1:8765/m26
(repeatable) asks the stand-in and keeps the real address in the records; --only-rewritten skips every other host;
--rounds, --wait, --gap and --no-install shorten and isolate it. The browser: $LIVE_CHROME and $LIVE_BROWSER_PYTHON,
as for the feed.
"""
import argparse
import datetime as dt
import importlib
import json
import os
import statistics
import subprocess
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
M26 = "https://media26.bechirot.gov.il"
EXPB, EXPC = M26 + "/files/expb.csv", M26 + "/files/expc.csv"
CONTROL = "https://media25.bechirot.gov.il/files/expc.csv"     # 2022, not behind the WAF: does this runner reach the CEC?
ROUNDS = 6
WAIT = 60.0              # seconds from one round's start to the next
GAP = 2.0                # seconds between the two files of a round (one host)
DEADLINE = 20 * 60       # seconds from the start (fetch.yml stops a fetcher at 25 minutes)
GRACE = 60               # a request under way at the deadline ends within the feed's own timeouts (40 s + 20 s)
PIP_S = 240              # pip, at most, per package
LATE = "not asked: past the deadline (--deadline)"
SKIP = "not asked: not rewritten (--only-rewritten)"


def now_iso(t=None):
    return dt.datetime.fromtimestamp(time.time() if t is None else t, dt.timezone.utc).isoformat(timespec="seconds")


def write_whole(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def importable(mod):
    return subprocess.run([sys.executable, "-c", f"import {mod}"], capture_output=True).returncode == 0


def ensure(mod, pkg, budget):
    """pkg installed for this interpreter when `mod` does not import: pip, then pip --user (a system Python)."""
    rec = {"package": pkg}
    if importable(mod):
        return {**rec, "present": True}
    t = time.time()
    for cmd in ([sys.executable, "-m", "pip", "install", "-q", pkg],
                [sys.executable, "-m", "pip", "install", "-q", "--user", "--break-system-packages", pkg]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=max(10, budget))
            rec.update(command=" ".join(cmd[1:]), rc=r.returncode, seconds=round(time.time() - t, 1),
                       stderr=r.stderr.strip()[-300:])
        except Exception as exc:
            rec.update(command=" ".join(cmd[1:]), rc=None, error=f"{exc.__class__.__name__}: {exc}"[:200])
        if rec.get("rc") == 0 and importable(mod):
            break
    import site
    for p in ([site.getusersitepackages()] if hasattr(site, "getusersitepackages") else []):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)                    # a --user install into a folder that did not exist at start
    importlib.invalidate_caches()
    rec["present"] = importable(mod)
    return rec


def rewriter(pairs):
    def rw(url):
        for real, local in pairs:
            if url.startswith(real):
                return local + url[len(real):]
        return None
    return rw


def is_request(x):
    """An attempt that reached the network: an HTTP answer, a urllib error, or a browser request that failed (not a
    browser that could not start)."""
    return bool(x.get("http")) or x.get("path") == "urllib" or str(x.get("error", "")).startswith("browser:")


def text_of(b, n):
    return (b or b"")[:n].decode("utf-8", "replace")


def one(LF, real, url, label):
    """live_fetch.fetch(url) once: its attempts (live_fetch.NET["log"]), the last answer, and the feed's outcome."""
    n0, starts0 = len(LF.NET["log"]), LF.BROWSER.starts
    LF.NET["last"], LF.NET["browser_lost"] = None, []
    t = time.time()
    try:
        data = LF.fetch(url)
        outcome = {"ok": True, "text": f"data accepted: {len(data)} bytes"}
    except Exception as exc:
        outcome = {"ok": False, "text": f"{exc.__class__.__name__}: {exc}"[:400]}
    rec = {"label": label, "url": real, "at": now_iso(t), "s": round(time.time() - t, 2), "outcome": outcome,
           "attempts": [{**{k: v for k, v in x.items() if k != "url"}} for x in LF.NET["log"][n0:]]}
    last = LF.NET.get("last")
    if last is not None:
        h = last.headers
        rec.update(path=last.path, http=last.status, waf=last.waf, waf_header=h.get("x-amzn-waf-action", ""),
                   x_cache=h.get("x-cache", ""), server=h.get("server", ""), content_type=h.get("content-type", ""),
                   bytes=len(last.body), head=" ".join(text_of(last.body, 160).split()))
    if LF.BROWSER.starts > starts0 and LF.BROWSER.start_s is not None:
        rec["browser_start_s"] = LF.BROWSER.start_s
    if LF.NET.get("browser_lost"):                 # a Chrome gone during it (crashed): a new one started
        rec["browser_lost"] = LF.NET["browser_lost"]
    return rec


def verdict(S):
    """("yes" | "no" | "unclear", why) for the media26 requests."""
    asked = [r for r in S["records"] if r["url"] != CONTROL and "attempts" in r]
    if not asked:
        return "unclear", "nothing asked" + (" (the deadline)" if S.get("not_asked_past_deadline") else
                                              f" ({S.get('error') or 'see below'})")
    past = [r for r in asked if r.get("http") and not r.get("waf")]
    walled = [r for r in asked if r.get("waf") or r["outcome"]["text"].startswith("WafError")]
    paths = sorted({r.get("path") for r in past if r.get("path")})
    codes = sorted({r["http"] for r in past})
    if len(past) == len(asked):
        why = (f"all {len(asked)} requests to media26 answered past the WAF (path: {', '.join(paths)}; HTTP "
               f"{', '.join(map(str, codes))})")
        if codes == [404]:
            why += ": a 404 is the CEC's own answer, the 2026 files are not up yet"
        return "yes", why
    if walled:
        w = walled[-1]
        return "no", (f"{len(walled)} of {len(asked)} requests ended at the WAF; the last: "
                      f"{w['outcome']['text'][:300]}")
    return "unclear", (f"{len(past)} of {len(asked)} past the WAF, the others failed otherwise; the last: "
                       f"{[r for r in asked if r not in past][-1]['outcome']['text'][:300]}")


def median(xs):
    return round(statistics.median(xs), 2) if xs else None


def render(S):
    v, why = S.get("verdict") or ("unclear", "")
    recs = [r for r in S["records"] if "attempts" in r]
    m26 = [r for r in recs if r["url"] != CONTROL]
    ur = [x for r in m26 for x in r["attempts"] if x.get("path") == "urllib" and x.get("http")]
    ch = [x for x in ur if x.get("waf")]
    br = [x for r in m26 for x in r["attempts"] if x.get("path") == "browser" and x.get("http")]
    starts = [r["browser_start_s"] for r in recs if r.get("browser_start_s") is not None]
    B = S.get("browser") or {}
    out = [f"# The feed's fetch through the CEC's WAF ({S['started'][:16].replace('T', ' ')} UTC)", "",
           f"- **the feed's fetch passes the WAF: {v}**. {why}"]
    if ur:
        hdr = sorted({x.get("waf_header") or "-" for x in ch})
        out.append(f"- urllib (the feed's first try): challenged on {len(ch)} of {len(ur)} requests to media26"
                   + (f" (HTTP {', '.join(sorted({str(x['http']) for x in ch}))}, x-amzn-waf-action: {', '.join(hdr)})" if ch else "")
                   + f"; a challenged host is asked through the browser directly, urllib again after "
                     f"{S.get('waf_recheck_s', '?')} s (live_fetch.WAF_RECHECK)")
    else:
        out.append("- urllib (the feed's first try): no answer from media26 recorded")
    if B.get("version") or starts:
        bt = [x["s"] for x in br]
        out.append(f"- the browser: Chrome {B.get('version', '?')} at `{B.get('chrome', '?')}`, its own User-Agent "
                   f"`{B.get('user_agent', '?')}`; started {len(starts)} times (once a round, as live.yml once a pass): "
                   f"{min(starts) if starts else '-'}–{max(starts) if starts else '-'} s, median {median(starts)} s; "
                   f"{len(br)} requests through it, median {median(bt)} s each (the start not included)")
    elif S.get("browser_error"):
        out.append(f"- the browser: unavailable: {S['browser_error'][:300]}")
    ctrl = next((r for r in recs if r["url"] == CONTROL), None)
    if ctrl:
        out.append(f"- control (media25, 2022): {ctrl.get('path', '-')}, HTTP {ctrl.get('http', '-')}, "
                   f"{ctrl.get('bytes', 0)} bytes; {ctrl['outcome']['text'][:120]}")
    n_late = S.get("not_asked_past_deadline", 0)
    out += ["", f"Requests of ours to the CEC's hosts: {S['requests']} (the plan: {2 * S['rounds']} to media26 through the "
                f"feed's fetch, {S['wait']:g} s between rounds, plus the urllib tries, plus the control once)."
            + (f" Stopped at the deadline: {n_late} not asked." if n_late else ""),
            f"Python {S.get('python', '?')}; live_fetch: {S.get('live_fetch', '?')}; Chrome found: "
            f"`{S.get('chrome') or '-'}` {S.get('chrome_why') or ''}", ""]
    for p in S.get("install") or []:
        out.append(f"pip: {json.dumps(p, ensure_ascii=False)}")
    out += ["", "| # | request | file | path (attempts) | HTTP | x-amzn-waf-action | x-cache | content-type | bytes | s | "
                "browser start s | the feed's outcome |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(S["records"], 1):
        if "attempts" not in r:
            out.append(f"| {i} | {r['label']} | {r['url']} | - | - | - | - | - | - | - | - | {r.get('error', '')} |")
            continue
        att = " → ".join(f"{x.get('path')} {x.get('http') or x.get('error', '')[:40]}" for x in r["attempts"])
        out.append(f"| {i} | {r['label']} | {r['url'].rsplit('/', 1)[-1]} ({r['url'].split('/')[2].split('.')[0]}) | {att} | "
                   f"{r.get('http', '-')} | {r.get('waf_header') or '-'} | {r.get('x_cache') or '-'} | "
                   f"{r.get('content_type') or '-'} | {r.get('bytes', 0)} | {r['s']} | {r.get('browser_start_s', '')} | "
                   f"{r['outcome']['text'][:160].replace('|', '/')} |")
    heads = [r for r in recs if r.get("head")]
    if heads:
        out += ["", "First bytes of each distinct answer:", ""]
        seen = set()
        for r in heads:
            k = (r.get("http"), r["head"][:80])
            if k not in seen:
                seen.add(k)
                out.append(f"- HTTP {r.get('http')} through {r.get('path')}: `{r['head'][:160]}`")
    if S.get("crash"):
        out += ["", "## The probe crashed", "", "```", S["crash"][-2000:], "```"]
    out += ["", "summary.json holds every record. Nothing was published."]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline", type=float, default=DEADLINE, help="seconds from the start; nothing is asked after it")
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    ap.add_argument("--wait", type=float, default=WAIT, help="seconds from one round's start to the next")
    ap.add_argument("--gap", type=float, default=GAP, help="seconds between the two files of a round")
    ap.add_argument("--keep-browser", action="store_true", help="one browser for every round (the laptop loop) instead "
                                                                 "of one a round (live.yml)")
    ap.add_argument("--no-install", action="store_true", help="install nothing (numpy, playwright)")
    ap.add_argument("--rewrite", action="append", default=[], metavar="REAL=LOCAL",
                    help="ask LOCAL in place of the address prefix REAL (tests); the records keep REAL")
    ap.add_argument("--only-rewritten", action="store_true", help="ask no address that is not rewritten")
    a = ap.parse_args(argv)
    t0 = time.time()
    end = t0 + max(0.0, a.deadline)
    os.makedirs(a.out, exist_ok=True)
    pairs = [tuple(x.split("=", 1)) for x in a.rewrite if "=" in x]
    rw = rewriter(pairs)
    S = {"started": now_iso(t0), "deadline_s": a.deadline, "rounds": a.rounds, "wait": a.wait, "requests": 0,
         "not_asked_past_deadline": 0, "install": [], "records": [], "stage": "start",
         "python": sys.version.split()[0], "rewritten": dict(pairs)}

    def save():
        S["verdict"] = verdict(S)
        write_whole(os.path.join(a.out, "summary.json"), json.dumps(S, ensure_ascii=False, indent=1))
        write_whole(os.path.join(a.out, "summary.md"), render(S))

    plan = [(f"round {i + 1}", u) for i in range(a.rounds) for u in (EXPB, EXPC)] + [("control", CONTROL)]
    LF = None
    try:
        if time.time() >= end:
            for label, u in plan:
                S["records"].append({"label": label, "url": u, "error": LATE})
            S["not_asked_past_deadline"] = len(plan)
            S["stage"] = "done"
            save()
            return 0
        if not a.no_install:
            for mod, pkg in (("numpy", "numpy"), ("playwright.sync_api", "playwright")):
                S["install"].append(ensure(mod, pkg, min(PIP_S, max(10, end - time.time()))))
        sys.path.insert(0, os.path.join(ROOT, "pipeline"))
        try:
            import live_fetch as LF
            S["live_fetch"] = f"imported from {os.path.relpath(LF.__file__, ROOT)}"
        except Exception as exc:
            S["live_fetch"] = S["error"] = f"cannot import live_fetch: {exc.__class__.__name__}: {exc}"[:300]
            S["stage"] = "done"
            save()
            return 0
        S["chrome"], S["chrome_why"] = LF.find_chrome()
        S["waf_recheck_s"] = LF.WAF_RECHECK
        LF.NET.update(via="auto", hosts={}, log=[], browser_error="", last=None, browser_start_s=None, browser_lost=[])   # as a fresh feed, fetch_via "auto"
        S["stage"] = "asking"
        save()
        rnd_start = None
        for i, (label, real) in enumerate(plan):
            if label != (plan[i - 1][0] if i else None):       # a new round (or the control)
                if rnd_start is not None:
                    if not a.keep_browser:
                        LF.BROWSER.close()                       # live.yml: a new process, a new browser, every pass
                    if label.startswith("round"):
                        time.sleep(max(0.0, min(rnd_start + a.wait, end) - time.time()))
                rnd_start = time.time()
            elif a.gap:
                time.sleep(max(0.0, min(a.gap, end - time.time())))
            url = rw(real)
            if url is None:
                if a.only_rewritten:
                    S["records"].append({"label": label, "url": real, "error": SKIP})
                    continue
                url = real
            if time.time() >= end:
                S["records"].append({"label": label, "url": real, "error": LATE})
                S["not_asked_past_deadline"] += 1
                continue
            rec = one(LF, real, url, label)
            S["requests"] += sum(1 for x in rec["attempts"] if is_request(x))
            S["records"].append(rec)
            if LF.BROWSER.info:
                S["browser"] = {k: LF.BROWSER.info.get(k) for k in ("version", "user_agent", "chrome")}
            if LF.NET.get("browser_error"):
                S["browser_error"] = LF.NET["browser_error"]
            print(f"{label} {real.rsplit('/', 1)[-1]}: {[(x.get('path'), x.get('http')) for x in rec['attempts']]} "
                  f"{rec['outcome']['text'][:100]}", flush=True)
            save()
        S["stage"] = "done"
        save()
        return 0
    except Exception:
        S["crash"] = traceback.format_exc()
        save()
        raise
    finally:
        if LF is not None:
            LF.BROWSER.close()


if __name__ == "__main__":
    sys.exit(main())
