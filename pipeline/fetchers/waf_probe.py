#!/usr/bin/env python3
"""A one-off probe, not the feed: is bechirot.gov.il behind an AWS WAF challenge, does an honest browser pass it, and
does the browser's token open the results files to a plain request?

    python3 pipeline/fetchers/waf_probe.py --out DIR [--deadline 1200]

Why: from 22.10.2026, 13:38 Israel time, every address on bechirot.gov.il, www., media26. and votes26. answers the
daily discovery (pipeline/discover.py, on a GitHub runner) with HTTP 202, Content-Type text/html, Content-Length 0,
Cache-Control no-store, max-age=0, X-Cache "Error from cloudfront", Server CloudFront and an empty body, while
media25. (2022) still answers 200 with data. That looks like an AWS WAF Challenge action (a silent JavaScript
challenge: a browser that runs it gets an aws-waf-token cookie, then normal answers), but the discovery does not
record x-amzn-waf-action. The election-night feed (pipeline/live_fetch.py) reads media26 .../files/expb.csv and
expc.csv with urllib, to which a 202 with an empty body is an "empty body".

Run from .github/workflows/fetch.yml on the request {"workflow": "fetch", "what": "waf_probe"}; the report lands on the
ops-reports branch under reports/fetch/waf_probe/<YYYYMMDD-HHMM>/ and .../latest/ (summary.md first).

1. Plain requests (urllib, the feed's own User-Agent and headers, as live_fetch.fetch sends them), then the same with
   a browser's ordinary headers (Accept text/html..., Accept-Language he, Sec-Fetch-*; the same User-Agent), to
   www.bechirot.gov.il/, media26.../, media26.../files/expb.csv, votes26.../ and the control media25.../files/expc.csv
   (a Range: bytes=0-200 GET). Recorded: the status, every response header (Set-Cookie: the cookie's name only), the
   first 600 bytes of the body and whether it names challenge.js, awswaf, gokuProps, a token.
2. A real browser: playwright installed at run time (python3 -m pip install -q playwright; never `playwright install`:
   the runner's preinstalled Google Chrome is used, /usr/bin/google-chrome & co.), headless, with its own default
   User-Agent. Nothing is hidden or spoofed: the question is whether an honest browser passes. It opens
   www.bechirot.gov.il/ and media26.bechirot.gov.il/ (30 s for the network to go idle; a challenge page still at work
   gets that long to reload) and records each navigation's status and headers, the title, the first 400 characters of
   the visible text and the names of the cookies set (aws-waf-token). Images, fonts and media on the CEC's hosts are
   not fetched (aborted in the browser): the load stays small and a challenge does not use them. Then, in the same
   browser context (its cookies), GET media26 .../files/expb.csv and expc.csv; and plain urllib GETs of expb.csv with
   the browser's cookies as a Cookie header and the browser's User-Agent: at once, 60 s and 4 minutes later (one more
   at once with the feed's own User-Agent). Does a token from a browser work for the feed, and for how long?
3. Polite: at most MAX_ASKS requests of our own to the CEC's hosts (18 as planned), each host at most once every GAP
   seconds; the browser's own requests (scripts, styles, the challenge's calls) are counted and reported apart.

summary.md opens with the three verdicts ("WAF challenge", "a real browser passes", "a browser token works for plain
requests"), then the tables; summary.json holds every record. Cookie values are never written, nor the Cookie header
sent (names only). The fetch contract (pipeline/fetchers/__init__.py) holds with one exception made for this probe:
part 2 installs playwright. Part 1 is the standard library only, and when playwright cannot be installed or no Chrome
is found, the summary says so and part 1 is still there. Never raises on one bad URL; nothing is asked after --deadline
(DEADLINE, 20 minutes from the start; a body still coming is cut GRACE seconds later; the browser is stopped as late);
the summary is written after each part, each write whole; exit 0 unless the script itself crashed.

Testing against a local stand-in (pipeline/test_live.py 11j): --rewrite https://www.bechirot.gov.il=http://127.0.0.1:8765/www
(repeatable) asks the stand-in and keeps the real address in the records; --only-rewritten skips every other host;
--gap, --token-waits and --no-install shorten and isolate it; --chrome (default: $WAF_PROBE_CHROME, else the usual
places) and --browser-python (the interpreter that has playwright) point part 2 at the test's own Chromium.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zlib

# the feed's own request (pipeline/live_fetch.py UA and fetch()); pipeline/test_live.py 11j keeps the two the same
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live"
PLAIN = {"User-Agent": UA, "Cache-Control": "no-cache"}
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
}
WWW = "https://www.bechirot.gov.il/"
M26 = "https://media26.bechirot.gov.il"
V26 = "https://votes26.bechirot.gov.il"
EXPB, EXPC = M26 + "/files/expb.csv", M26 + "/files/expc.csv"
CONTROL = "https://media25.bechirot.gov.il/files/expc.csv"     # 2022: does this runner reach the CEC at all?
PART1 = [WWW, M26 + "/", EXPB, V26 + "/", CONTROL]
PAGES = [WWW, M26 + "/"]
FILES = [EXPB, EXPC]
TOKEN_WAITS = (60, 240)        # the token checks after the first one: 60 s and 4 minutes on
MAX_ASKS = 25                  # our own requests to the CEC's hosts, all parts (18 as planned)
GAP = 2.0                      # seconds between two of our requests to one host
TIMEOUT = 20
VISIT_S = 30                   # the browser: seconds for a page's network to go idle (and a challenge to reload)
HEAD = 600                     # body bytes kept, part 1
FILE_HEAD = 300                # body bytes kept, the files in part 2
TEXT_HEAD = 400                # visible text kept, the browser's pages
RAW_MAX = 65536                # body bytes read at most (then the connection is closed)
DEADLINE = 20 * 60             # seconds from the start (pipeline/fetchers/__init__.py: fetch.yml stops it at 25 minutes)
GRACE = 60                     # a body still coming at the deadline is cut this much later
PIP_S = 300                    # pip install playwright, at most
WORKER_S = 420                 # the browser part, at most (four steps of 30-60 s, a launch, the gaps)
LATE = "not asked: past the deadline (--deadline)"
MARKERS = (("challenge.js", rb"challenge\.js"), ("awswaf", rb"awswaf"), ("AwsWafIntegration", rb"AwsWafIntegration"),
           ("gokuProps", rb"gokuProps"), ("aws-waf-token", rb"aws-waf-token"), ("captcha", rb"captcha"),
           ("token", rb"token"))
CHALLENGE_MARKERS = {"challenge.js", "awswaf", "AwsWafIntegration", "gokuProps"}
# Google Chrome's own binary first (what playwright's channel "chrome" runs), then the wrappers, then Chromium
CHROMES = ("/opt/google/chrome/chrome", "google-chrome", "google-chrome-stable", "/usr/bin/google-chrome",
           "chromium", "chromium-browser", "/usr/bin/chromium", "/usr/bin/chromium-browser")


def now_iso(t=None):
    return dt.datetime.fromtimestamp(time.time() if t is None else t, dt.timezone.utc).isoformat(timespec="seconds")


def text_of(b):
    return (b or b"").decode("utf-8", "replace")


def markers(body):
    return [name for name, rx in MARKERS if re.search(rx, body or b"", re.I)]


def cookie_name(set_cookie):
    return set_cookie.split("=", 1)[0].strip()[:80]


def header_list(pairs):
    """Response headers as [name, value] pairs, in order; Set-Cookie: the cookie's name only, never its value."""
    out, names = [], []
    for k, v in pairs:
        if k.lower() == "set-cookie":
            for one in str(v).split("\n"):          # playwright joins several Set-Cookie headers with newlines
                if one.strip():
                    names.append(cookie_name(one))
                    out.append([k, cookie_name(one) + "=(value not kept)"])
        else:
            out.append([k, str(v)[:500]])
    return out, names


def hget(rec, name):
    for k, v in rec.get("headers") or []:
        if k.lower() == name:
            return v
    return None


def hall(rec, name):
    """Every value of a header, joined (the summary's tables)."""
    return ", ".join(v for k, v in rec.get("headers") or [] if k.lower() == name)


def redact(headers):
    """The request headers as sent, the Cookie header as its names only."""
    out = {}
    for k, v in headers.items():
        if k.lower() == "cookie":
            v = "; ".join(cookie_name(c) + "=(value not kept)" for c in v.split(";") if c.strip())
        out[k] = v
    return out


def read_some(r, limit, cut):
    """Up to limit bytes of a body, in pieces, stopped at the monotonic time `cut`; (bytes, more_left)."""
    chunks, n = [], 0
    while n < limit:
        if time.monotonic() > cut:
            return b"".join(chunks), True
        b = r.read(min(1 << 14, limit - n))
        if not b:
            return b"".join(chunks), False
        chunks.append(b)
        n += len(b)
    return b"".join(chunks), True


def unpack(raw, enc):
    """The start of a body whose first bytes only were read: gzip and deflate unpacked as far as they go."""
    enc = (enc or "").lower()
    try:
        if "gzip" in enc or raw[:2] == b"\x1f\x8b":
            return zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, 8 * HEAD)
        if "deflate" in enc:
            try:
                return zlib.decompressobj().decompress(raw, 8 * HEAD)
            except zlib.error:
                return zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw, 8 * HEAD)
    except zlib.error:
        pass
    return raw


# ------------------------------------------------------------------ verdicts (pure: pipeline/test_live.py 11j)
def is_cec(url):
    host = urllib.parse.urlsplit(url or "").hostname or ""
    return host.endswith("bechirot.gov.il") and not host.startswith("media25.")


def challenge_of(rec):
    """What stopped an answer at the WAF: x-amzn-waf-action's value, or 'unlabelled 202' for CloudFront's 202 / 405
    without the header; None for an answer that came through (any status, a 404 or S3's AccessDenied too)."""
    action = hget(rec, "x-amzn-waf-action")
    if action:
        return action.strip().lower()
    if rec.get("status") in (202, 405) and "error from cloudfront" in (hget(rec, "x-cache") or "").lower():
        return f"unlabelled {rec['status']}"
    return None


def blocked(rec):
    """CloudFront's own 403 page (a WAF block, a geo block): not a challenge, and nothing came through."""
    head = (rec.get("body_head") or rec.get("head") or "").lower()
    return rec.get("status") == 403 and ("request blocked" in head or "could not be satisfied" in head)


def came_through(rec):
    return rec.get("status") is not None and challenge_of(rec) is None and not blocked(rec)


def fmt_s(s):
    if s is None:
        return "?"
    s = int(round(s))
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def describe(r):
    """A stopped answer in a few words: its status and what its body was."""
    page = sorted(CHALLENGE_MARKERS & set(r.get("markers") or ()))
    if page:
        return f"{r.get('status')} with a challenge page ({', '.join(page)})"
    return f"{r.get('status')} with {'a body' if r.get('body_head') else 'an empty body'}"


def verdicts(S):
    """The three answers at the top of summary.md: (word, why) each, word yes / no / unclear."""
    v = {}
    part1 = S.get("part1") or []
    B = S.get("browser") or {}
    answers = [r for r in part1 if is_cec(r["url"]) and r.get("status") is not None]
    answers += [n for p in B.get("pages") or [] for n in (p.get("navigations") or [])[:1] if is_cec(p["url"])]
    acts = {}
    for r in answers:
        c = challenge_of(r)
        if c:
            acts[c] = acts.get(c, 0) + 1
    pages = [r for r in answers if CHALLENGE_MARKERS & set(r.get("markers") or ())]
    ctrl = [r for r in part1 if r["url"] == CONTROL]
    ctrl_ok = any(r.get("status") in (200, 206) for r in ctrl)
    asked = [r for r in part1 if not str(r.get("error", "")).startswith("not asked")]
    if not answers and not asked:
        v["waf"] = ("unclear", "nothing asked" + (f" ({part1[0]['error']})" if part1 else " yet"))
    elif not answers:
        v["waf"] = ("unclear", "no answer from www., media26. or votes26."
                    + ("" if ctrl_ok else "; the control (media25) did not answer either: the runner's network?"))
    elif acts.get("challenge"):
        kinds = sorted({describe(r) for r in answers if challenge_of(r) == "challenge"})
        v["waf"] = ("yes", f"x-amzn-waf-action: challenge on {acts['challenge']} of {len(answers)} answers from the CEC's "
                           f"2026 hosts ({'; '.join(kinds)})")
    elif acts.get("captcha"):
        v["waf"] = ("yes", f"a CAPTCHA, not a silent challenge: x-amzn-waf-action: captcha on {acts['captcha']} of "
                           f"{len(answers)} answers")
    elif pages:
        v["waf"] = ("yes", f"a challenge page ({', '.join(sorted(CHALLENGE_MARKERS & set(pages[0].get('markers'))))}) on "
                           f"{len(pages)} answers, though without x-amzn-waf-action")
    elif any(k.startswith("unlabelled") for k in acts):
        n = sum(c for k, c in acts.items() if k.startswith("unlabelled"))
        v["waf"] = ("unclear", f"{n} of {len(answers)} answers are CloudFront's 202 / 405 ('Error from cloudfront') "
                               "without x-amzn-waf-action and without a challenge page")
    elif acts:
        v["waf"] = ("unclear", f"x-amzn-waf-action: {', '.join(sorted(acts))} (neither challenge nor captcha)")
    elif any(blocked(r) for r in answers):
        v["waf"] = ("no", "blocked (CloudFront's 403 page), not challenged")
    else:
        v["waf"] = ("no", "every answer came through: " + ", ".join(sorted({str(r['status']) for r in answers})))

    if not B.get("ran"):
        v["browser"] = ("unclear", B.get("skipped") or B.get("error") or "the browser part did not run")
    else:
        pg = B.get("pages") or []
        done = [p for p in pg if p.get("navigations")]
        stuck = [p for p in done if not came_through(p["navigations"][-1])]
        chains = "; ".join(f"{urllib.parse.urlsplit(p['url']).hostname} "
                           f"{' -> '.join(str(n.get('status')) for n in p.get('navigations') or []) or p.get('error', '?')}"
                           for p in pg)
        token = "aws-waf-token set" if any(c.get("name", "").lower() == "aws-waf-token" for c in B.get("cookies") or []) \
            else "no aws-waf-token cookie"
        if stuck:
            v["browser"] = ("no", f"still stopped after {fmt_s(B.get('visit_s', VISIT_S))}: {chains} "
                                  f"({', '.join(challenge_of(p['navigations'][-1]) or 'blocked' for p in stuck)}); {token}")
        elif not done or len(done) < len(pg):
            v["browser"] = ("unclear", f"not every page answered: {chains}; {B.get('error') or ''}".strip("; "))
        else:
            first = [challenge_of(p["navigations"][0]) for p in done]
            how = "after the challenge" if any(first) else "not challenged at all"
            v["browser"] = ("yes", f"{how}: {chains}; {token}")

    T = S.get("token_checks") or []
    mine = [t for t in T if t.get("ua_kind") == "browser" and t.get("status") is not None]
    feed = [t for t in T if t.get("ua_kind") == "feed" and t.get("status") is not None]
    plain_stopped = any(challenge_of(r) for r in part1 if is_cec(r["url"]) and r.get("status") is not None)
    if not mine:
        why = S.get("token_skipped") or "; ".join(sorted({t.get("error") or "" for t in T} - {""})) or "not asked"
        v["token"] = ("unclear", why)
    elif not came_through(mine[0]):
        v["token"] = ("no", f"refused at once: HTTP {mine[0]['status']}, "
                            f"x-amzn-waf-action {hget(mine[0], 'x-amzn-waf-action') or '-'}")
    else:
        bad = [t for t in mine if not came_through(t)]
        missing = [t for t in T if t.get("ua_kind") == "browser" and t.get("status") is None]
        seen = "HTTP " + ", ".join(f"{t['status']} at {fmt_s(t['after_s'])}" for t in mine)
        if bad:
            ok_before = [t for t in mine if came_through(t) and t["after_s"] < bad[0]["after_s"]] or mine[:1]
            v["token"] = ("yes", f"for a while: it worked {fmt_s(ok_before[-1]['after_s'])} after the first check (token "
                                 f"about {fmt_s(ok_before[-1].get('token_age_s'))} old), refused "
                                 f"{fmt_s(bad[0]['after_s'])} after it (x-amzn-waf-action "
                                 f"{hget(bad[0], 'x-amzn-waf-action') or '-'}; {seen})")
        else:
            last = mine[-1]
            rest = "" if not missing else "; not made or no answer: " + "; ".join(
                f"{fmt_s(t.get('after_s'))}: {t.get('error') or '?'}" for t in missing)
            v["token"] = ("yes", f"it still worked {fmt_s(last['after_s'])} after the first check (token about "
                                 f"{fmt_s(last.get('token_age_s'))} old; {seen}){rest}")
        if not plain_stopped:
            v["token"] = (v["token"][0], v["token"][1] + "; but plain requests were not stopped either, so this proves little")
    if mine and feed:
        v["token"] = (v["token"][0], v["token"][1] + "; with the feed's own User-Agent: "
                      + ("it worked" if came_through(feed[0]) else f"refused (HTTP {feed[0]['status']})"))
    if mine and S.get("token_cookie_names") is not None:
        v["token"] = (v["token"][0], v["token"][1] + "; cookies sent: " + (", ".join(S["token_cookie_names"]) or "none")
                      + ("" if "aws-waf-token" in [n.lower() for n in S["token_cookie_names"]] else " (no aws-waf-token)"))
    if ctrl:
        c = ctrl[0]
        if c.get("status") is not None:
            said = f"answered HTTP {c['status']}" + (" with data" if c.get("body_head") else " without a body")
        else:
            said = c.get("error") or "no answer"
        v["control"] = (str(c.get("status") or "-"), "media25 (2022): " + said)
    return v


# ------------------------------------------------------------------ the probe
class Probe:
    def __init__(self, out, rewrite=(), only_rewritten=False, deadline=DEADLINE, gap=GAP, timeout=TIMEOUT):
        self.out, self.rewrite, self.only = out, list(rewrite), only_rewritten
        self.deadline, self.gap, self.timeout = deadline, gap, timeout
        self.stop_at = time.monotonic() + deadline
        self.cut_at = self.stop_at + GRACE
        self.last = {}                   # real host -> monotonic time of our last request to it
        self.asked, self.not_asked = 0, 0
        self.saved = 0

    def late(self):
        return time.monotonic() >= self.stop_at

    def left(self, cap):
        return max(1.0, min(cap, self.cut_at - time.monotonic()))

    def target(self, url):
        for a, b in self.rewrite:
            if url.startswith(a):
                return b + url[len(a):]
        return None if self.only else url

    def logical(self, url):
        for a, b in self.rewrite:
            if url and url.startswith(b):
                return a + url[len(b):]
        return url

    def wait_turn(self, host):
        t = self.last.get(host)
        if t is not None and t + self.gap > time.monotonic():
            time.sleep(t + self.gap - time.monotonic())

    def touch_all(self, hosts):
        now = time.monotonic()
        for h in hosts:
            self.last[h] = now

    def quiet(self):
        """Wait until no host had a request of ours in the last GAP seconds (before the browser starts)."""
        if self.last:
            time.sleep(max(0.0, max(self.last.values()) + self.gap - time.monotonic()))

    def skip(self, rec, why):
        rec["error"] = why
        if why == LATE:
            self.not_asked += 1
        return rec

    def get(self, url, headers, label, head=HEAD, raw_max=RAW_MAX):
        """One request of ours with urllib: a record, never an exception."""
        rec = {"label": label, "url": url, "sent": redact(headers)}
        if self.late():
            return self.skip(rec, LATE)
        if self.asked >= MAX_ASKS:
            return self.skip(rec, f"not asked: {MAX_ASKS} requests already (MAX_ASKS)")
        target = self.target(url)
        if target is None:
            return self.skip(rec, "not asked: --only-rewritten")
        host = urllib.parse.urlsplit(url).hostname or ""
        self.wait_turn(host)
        if self.late():
            return self.skip(rec, LATE)
        self.asked += 1
        self.last[host] = time.monotonic()
        t = time.time()
        rec["at"] = now_iso(t)
        hdrs, raw, more = None, b"", False
        try:
            req = urllib.request.Request(target, headers=headers)
            with urllib.request.urlopen(req, timeout=self.left(self.timeout)) as r:
                rec["status"], hdrs = r.status, r.headers
                if self.logical(r.geturl()) != url:
                    rec["final_url"] = self.logical(r.geturl())
                raw, more = read_some(r, raw_max, self.cut_at)
        except urllib.error.HTTPError as exc:
            rec["status"], hdrs = exc.code, exc.headers
            try:
                raw, more = read_some(exc, raw_max, self.cut_at)
            except Exception as e2:                        # the error body is a bonus, never the record's end
                rec["body_error"] = f"{e2.__class__.__name__}: {str(e2)[:120]}"
        except Exception as exc:                            # refused, DNS, TLS, a timeout: this URL's finding
            rec["error"] = f"{exc.__class__.__name__}: {str(getattr(exc, 'reason', exc))[:200]}"
        rec["ms"] = round(1000 * (time.time() - t))
        if hdrs is not None:
            rec["headers"], rec["set_cookie_names"] = header_list(hdrs.items())
        body = unpack(raw, hdrs.get("Content-Encoding") if hdrs is not None else "")
        rec["body_read"] = len(raw)
        if more:
            rec["body_more"] = True
        rec["body_head"], rec["head_bytes"] = text_of(body[:head]), len(body[:head])
        rec["markers"] = markers(body)
        return rec

    def save_head(self, rec, rel, n):
        """The first bytes of an answer as a file under DIR/files (the record keeps them as text too)."""
        if not rec.get("body_head"):
            return
        path = os.path.join(self.out, "files", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(rec["body_head"][:n])
        rec["saved"] = "files/" + rel
        self.saved += 1


def slug(url):
    p = urllib.parse.urlsplit(url)
    return re.sub(r"[^A-Za-z0-9.]+", "_", (p.hostname or "") + p.path).strip("_")[:80]


def part1(P):
    recs = []
    for kind, hdr in (("plain", PLAIN), ("browser headers", BROWSER_HEADERS)):
        for url in PART1:
            h = dict(hdr)
            if url == CONTROL:
                h["Range"] = "bytes=0-200"
            rec = P.get(url, h, kind)
            rec["kind"] = kind
            recs.append(rec)
            P.save_head(rec, f"part1/{len(recs):02d}-{kind.split()[0]}-{slug(url)}.head", HEAD)
    return recs


def find_chrome(given):
    if given:
        return (given if os.path.isfile(given) and os.access(given, os.X_OK) else None), [given]
    looked = []
    for c in CHROMES:
        looked.append(c)
        p = c if os.path.isabs(c) else shutil.which(c)
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p, looked
    return None, looked


def run_capped(cmd, timeout):
    """A command in its own process group, killed whole (Chrome too) at the timeout: (rc, stdout, stderr, timed_out)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        o, e = p.communicate(timeout=timeout)
        return p.returncode, o, e, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        o, e = p.communicate()
        return p.returncode, o, e, True


def playwright_version(py):
    try:
        rc, o, e, _ = run_capped([py, "-c", "import playwright.sync_api\nfrom importlib.metadata import version\n"
                                            "print(version('playwright'))"], 90)
    except OSError as exc:
        return None, f"{exc.__class__.__name__}: {exc}"[:200]
    if rc == 0 and o.strip():
        return o.decode("utf-8", "replace").strip()[:40], None
    return None, (e.decode("utf-8", "replace").strip().splitlines() or ["no output"])[-1][:200]


def pip_install(py, P):
    rec = {"command": "python3 -m pip install -q playwright"}
    for extra in ([], ["--user"]):
        left = P.stop_at - time.monotonic()
        if left <= 5:
            rec["error"] = "not run: past the deadline (--deadline)"
            return rec
        t = time.time()
        try:
            rc, o, e, timed_out = run_capped([py, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                                              "--no-input", *extra, "playwright"], min(PIP_S, left))
        except OSError as exc:
            rec["error"] = f"{exc.__class__.__name__}: {exc}"[:200]
            return rec
        err = e.decode("utf-8", "replace")
        rec.update(rc=rc, seconds=round(time.time() - t), user=bool(extra))
        if timed_out:
            rec["error"] = f"stopped after {min(PIP_S, left):.0f} s"
            return rec
        if rc == 0:
            rec.pop("error", None)
            return rec
        rec["error"] = (err.strip().splitlines() or ["?"])[-1][:300]
        if "externally-managed" not in err:
            return rec
    return rec


def part2(P, a, S):
    """The browser (a worker process: the interpreter with playwright), then the token checks with urllib."""
    B = S["browser"] = {"ran": False}
    S["token_checks"] = []
    if P.late():
        B["skipped"] = "not run: past the deadline (--deadline)"
        P.not_asked += len(PAGES) + len(FILES)
        return None
    chrome, looked = find_chrome(a.chrome)
    if not chrome:
        B["skipped"] = "no Chrome or Chromium found (looked for " + ", ".join(looked) + ")"
        return None
    B["chrome"] = chrome
    py = a.browser_python or sys.executable
    version, err = playwright_version(py)
    if version is None and not a.no_install:
        B["install"] = pip_install(py, P)
        version, err = playwright_version(py)
    if version is None:
        B["skipped"] = f"playwright could not be {'imported (--no-install)' if a.no_install else 'installed or imported'}: {err}"
        return None
    B["playwright"], B["visit_s"] = version, a.visit
    P.quiet()
    if P.late():
        B["skipped"] = "not run: past the deadline (--deadline)"
        P.not_asked += len(PAGES) + len(FILES)
        return None
    tmp = tempfile.mkdtemp(prefix="waf-probe-")        # the worker's answer holds cookie values: never under DIR
    try:
        job = {"chrome": chrome, "gap": P.gap, "visit_s": a.visit, "result": os.path.join(tmp, "result.json"),
               "stop_at": time.time() + (P.stop_at - time.monotonic()), "rewrite": P.rewrite,
               "pages": [[u, P.target(u)] for u in PAGES], "files": [[u, P.target(u)] for u in FILES]}
        with open(os.path.join(tmp, "job.json"), "w", encoding="utf-8") as f:
            json.dump(job, f)
        cap = max(5.0, min(WORKER_S, P.stop_at - time.monotonic() + GRACE))
        t = time.time()
        try:
            rc, _, e, timed_out = run_capped([py, os.path.abspath(__file__), "--browser-worker",
                                              os.path.join(tmp, "job.json")], cap)
        except OSError as exc:
            rc, e, timed_out = None, str(exc).encode(), False
        P.touch_all({urllib.parse.urlsplit(u).hostname for u in PAGES + FILES})
        B["seconds"] = round(time.time() - t)
        try:
            with open(job["result"], encoding="utf-8") as f:
                R = json.load(f)
        except (OSError, ValueError):
            R = {}
        if timed_out:
            B["error"] = f"the browser part was stopped after {cap:.0f} s"
        elif rc != 0:
            B["error"] = f"the browser worker exited {rc}: " + " | ".join(
                e.decode("utf-8", "replace").strip().splitlines()[-3:])[:400]
        if R.get("error"):
            B["error"] = (B.get("error", "") + "; " if B.get("error") else "") + R["error"]
        B["ran"] = bool(R.get("browser_version"))
        for k in ("browser_version", "user_agent", "webdriver", "pages", "files", "requests_by_host", "aborted",
                  "challenge_requests"):
            if k in R:
                B[k] = R[k]
        P.asked += sum(1 for x in (R.get("pages") or []) + (R.get("files") or []) if x.get("asked"))
        P.not_asked += sum(1 for x in (R.get("pages") or []) + (R.get("files") or []) if x.get("error") == LATE)
        cookies = R.get("cookies") or []
        B["cookies"] = [{"name": c.get("name"), "domain": c.get("domain"), "path": c.get("path"),
                         "secure": c.get("secure"), "httpOnly": c.get("httpOnly"), "sameSite": c.get("sameSite"),
                         "expires_in_s": round(c["expires"] - time.time()) if (c.get("expires") or -1) > 0 else "session"}
                        for c in cookies]
        for i, x in enumerate(B.get("files") or []):
            P.save_head(x, f"browser/{i + 1:02d}-{slug(x['url'])}.head", FILE_HEAD)
        return {"cookies": cookies, "ua": R.get("user_agent"), "token_seen_at": R.get("token_seen_at")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cookie_applies(c, url):
    p = urllib.parse.urlsplit(url)
    host, path = (p.hostname or "").lower(), p.path or "/"
    dom = (c.get("domain") or "").lower().lstrip(".")
    if not dom or not (host == dom or host.endswith("." + dom)):
        return False
    if c.get("secure") and p.scheme != "https":
        return False
    return path.startswith(c.get("path") or "/")


def token_checks(P, S, got, waits, write):
    """expb.csv with urllib and the browser's cookies: at once (the browser's UA, then the feed's), then `waits`
    seconds after the first check (the browser's UA)."""
    T = S["token_checks"]
    plan = [(0, "browser"), (0, "feed")] + [(w, "browser") for w in waits]
    if not got or not got.get("cookies"):
        S["token_skipped"] = "the browser brought no cookies" if got else "the browser part did not run"
        return
    target = P.target(EXPB) or EXPB
    sent = [c for c in got["cookies"] if cookie_applies(c, target)]
    jar = "; ".join(f"{c['name']}={c['value']}" for c in sent)
    if not jar:
        S["token_skipped"] = "none of the browser's cookies applies to " + EXPB
        return
    S["token_cookie_names"] = [c["name"] for c in sent]
    ua = got.get("ua") or UA
    first = None
    for after, kind in plan:
        if first is not None and after:
            wake = first + after
            if wake > P.stop_at:
                T.append(P.skip({"label": f"after {after} s", "url": EXPB, "ua_kind": kind, "after_s": after}, LATE))
                continue
            write("waiting for the token check " + fmt_s(after) + " after the first")
            time.sleep(max(0.0, wake - time.monotonic()))
        hdr = {"User-Agent": ua if kind == "browser" else UA, "Cache-Control": "no-cache", "Cookie": jar}
        t0 = time.monotonic()
        rec = P.get(EXPB, hdr, f"cookies, {'the browser' if kind == 'browser' else 'the feed'}'s UA", head=FILE_HEAD,
                    raw_max=4096)
        first = t0 if first is None else first          # the later checks count from the first one's start
        rec.update(ua_kind=kind, after_s=round(t0 - first))
        if got.get("token_seen_at") and rec.get("at"):
            rec["token_age_s"] = round(time.time() - got["token_seen_at"])
        T.append(rec)
        P.save_head(rec, f"token/{len(T):02d}-{kind}.head", FILE_HEAD)


# ------------------------------------------------------------------ the browser worker (a separate process)
def browser_worker(job_path):
    """Runs under the interpreter that has playwright; writes its answer (cookie values too) to job['result'], outside
    DIR, after every step. Prints nothing of the pages."""
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    R = {"started": now_iso(), "pages": [], "files": [], "requests_by_host": {}, "aborted": 0, "challenge_requests": []}
    rw = [tuple(x) for x in job.get("rewrite") or []]

    def logical(url):
        for a, b in rw:
            if url and url.startswith(b):
                return a + url[len(b):]
        return url

    def save():
        tmp = job["result"] + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(R, f, ensure_ascii=False)
        os.replace(tmp, job["result"])

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        R["error"] = f"playwright: {exc.__class__.__name__}: {exc}"[:300]
        save()
        return 0
    stop_at, gap, visit_s = job["stop_at"], job["gap"], job["visit_s"]
    own = {urllib.parse.urlsplit(t).netloc for _, t in job["pages"] + job["files"] if t}

    def cec(url):          # a CEC host, by its real name (a stand-in's address in tests)
        return urllib.parse.urlsplit(url).netloc in own or \
            (urllib.parse.urlsplit(logical(url)).hostname or "").endswith("bechirot.gov.il")

    def waf_names(seq):
        return header_list(seq)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(executable_path=job["chrome"], headless=True)
        except Exception as exc:
            R["error"] = f"Chrome did not start: {exc.__class__.__name__}: {(str(exc).splitlines() or [''])[0][:300]}"
            save()
            return 0
        R["browser_version"] = browser.version
        context = browser.new_context()

        def on_route(route):
            try:
                req = route.request
                if req.resource_type in ("image", "font", "media") and cec(req.url):
                    R["aborted"] += 1
                    route.abort()
                else:
                    route.continue_()
            except Exception:
                pass

        def on_request(req):
            try:
                u = urllib.parse.urlsplit(logical(req.url))
                h = u.hostname or "?"
                R["requests_by_host"][h] = R["requests_by_host"].get(h, 0) + 1
                if "awswaf" in h or "challenge" in u.path.lower() or u.path.lower().endswith(("/verify", "/inputs")):
                    if len(R["challenge_requests"]) < 40:
                        R["challenge_requests"].append({"method": req.method, "url": f"{u.scheme}://{h}{u.path}",
                                                        "type": req.resource_type})
            except Exception:
                pass

        context.route("**/*", on_route)
        context.on("request", on_request)
        page = context.new_page()
        try:
            R["user_agent"] = page.evaluate("() => navigator.userAgent")
            R["webdriver"] = page.evaluate("() => navigator.webdriver")
        except Exception as exc:
            R["error"] = f"navigator: {exc.__class__.__name__}"
        save()

        def nav_record(r):
            try:
                pairs = [(h["name"], h["value"]) for h in r.headers_array()]
            except Exception:
                pairs = list((r.headers or {}).items())
            hl, names = waf_names(pairs)
            return {"status": r.status, "url": logical(r.url), "headers": hl, "set_cookie_names": names}

        def stopped(r):
            try:
                return r.status in (202, 405) or "x-amzn-waf-action" in (r.headers or {})
            except Exception:
                return False

        def retry(fn, default):
            for i in range(3):
                try:
                    return fn()
                except Exception:
                    time.sleep(1)
            return default

        for i, (real, target) in enumerate(job["pages"]):
            rec = {"url": real}
            R["pages"].append(rec)
            if not target:
                rec["error"] = "not asked: --only-rewritten"
                continue
            if i:
                time.sleep(gap)
            if time.time() >= stop_at:
                rec["error"] = LATE
                continue
            navs = []

            def on_response(r, navs=navs):
                try:
                    if r.request.is_navigation_request() and r.frame == page.main_frame:
                        navs.append(r)
                except Exception:
                    pass
            page.on("response", on_response)
            rec["asked"] = True
            t_end = time.time() + visit_s
            try:
                page.goto(target, wait_until="load", timeout=visit_s * 1000)
            except Exception as exc:
                rec["goto_error"] = f"{exc.__class__.__name__}: {(str(exc).splitlines() or [''])[0][:200]}"
            idle = False
            while time.time() < t_end:
                try:
                    page.wait_for_load_state("networkidle", timeout=max(1, t_end - time.time()) * 1000)
                    idle = True
                except Exception:
                    idle = False
                    break
                if navs and stopped(navs[-1]):     # still the challenge page: its script may still be at work
                    page.wait_for_timeout(1000)
                    continue
                break
            page.remove_listener("response", on_response)
            rec["network_idle"] = idle
            rec["seconds"] = round(visit_s - (t_end - time.time()), 1)
            try:                                   # what the page shows now; a failure here is this page's note
                rec["navigations"] = [nav_record(r) for r in navs]
                rec["final_url"] = logical(page.url)
                rec["title"] = (retry(lambda: page.title(), "") or "")[:200]
                rec["text"] = re.sub(r"\s+", " ", retry(lambda: page.evaluate(
                    "() => document.body ? document.body.innerText : ''"), "") or "").strip()[:TEXT_HEAD]
                html = (retry(lambda: page.content(), "") or "").encode("utf-8", "replace")
                rec["html_bytes"], rec["markers"] = len(html), markers(html)
                cookies = context.cookies()
                rec["cookie_names"] = sorted({c["name"] for c in cookies})
                if "token_seen_at" not in R and any(c["name"].lower() == "aws-waf-token" for c in cookies):
                    R["token_seen_at"] = time.time()
                R["cookies"] = cookies
            except Exception as exc:
                rec["error"] = f"{exc.__class__.__name__}: {(str(exc).splitlines() or [''])[0][:200]}"
            save()

        for real, target in job["files"]:
            rec = {"url": real}
            R["files"].append(rec)
            if not target:
                rec["error"] = "not asked: --only-rewritten"
                continue
            time.sleep(gap)
            if time.time() >= stop_at:
                rec["error"] = LATE
                continue
            rec["asked"], t = True, time.time()
            try:
                r = context.request.get(target, timeout=30000, fail_on_status_code=False)
                rec["status"] = r.status
                rec["headers"], rec["set_cookie_names"] = waf_names([(h["name"], h["value"]) for h in r.headers_array])
                body = r.body()
                rec["bytes"], rec["body_head"], rec["markers"] = len(body), text_of(body[:FILE_HEAD]), markers(body[:RAW_MAX])
                rec["head_bytes"] = len(body[:FILE_HEAD])
                r.dispose()
                R["cookies"] = context.cookies()
            except Exception as exc:
                rec["error"] = f"{exc.__class__.__name__}: {(str(exc).splitlines() or [''])[0][:200]}"
            rec["ms"] = round(1000 * (time.time() - t))
            save()
        try:
            browser.close()
        except Exception:
            pass
    R["finished"] = now_iso()
    save()
    return 0


# ------------------------------------------------------------------ the summary
def cell(x, n=120):
    return re.sub(r"\s+", " ", str(x if x is not None else "")).replace("|", "/").replace("`", "'")[:n]


def block(text, n):
    lines = (text or "")[:n].splitlines() or [""]
    return ["    " + re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "?", ln) for ln in lines[:40]]


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def markdown(S, V):
    L = [f"# WAF probe: bechirot.gov.il ({S['started'][:16].replace('T', ' ')} UTC)", ""]
    for key, label in (("waf", "WAF challenge"), ("browser", "a real browser passes"),
                       ("token", "a browser token works for plain requests")):
        word, why = V[key]
        L.append(f"- **{label}: {word}**. {cell(why, 700)}")
    if "control" in V:
        L.append(f"- Control: {cell(V['control'][1], 200)}.")
    L.append("")
    if S.get("stage") != "done":
        L += [f"**Partial:** written {S.get('stage')}; the run had not finished (if this is the last copy, it was stopped "
              "there).", ""]
    if S.get("not_asked_past_deadline"):
        L += [f"**Stopped at the deadline** ({S['deadline_s']:.0f} s from the start): {S['not_asked_past_deadline']} "
              "requests not asked (`not asked: past the deadline` below); what came before is here.", ""]
    if S.get("crashed"):
        L += ["**Crashed:** " + cell(S["crashed"], 400), ""]
    L += [f"Requests of ours to the CEC's hosts: {S['requests']} (at most {MAX_ASKS}, {S['gap_s']:g} s apart per host). "
          f"The feed's User-Agent: `{cell(UA, 200)}`.", "",
          "## 1. Plain requests (the feed's headers) and a browser's ordinary headers (urllib)", "",
          "| # | headers | URL | HTTP | x-amzn-waf-action | x-cache | server | x-amz-cf-pop | content-type | length | set-cookie "
          "| body (start) | markers |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(S.get("part1") or [], 1):
        L.append(f"| {i} | {cell(r.get('kind'))} | {cell(r['url'])} | {cell(r.get('status') or r.get('error'))} | "
                 f"{cell(hget(r, 'x-amzn-waf-action') or '-')} | {cell(hall(r, 'x-cache'))} | {cell(hall(r, 'server'))} | "
                 f"{cell(hall(r, 'x-amz-cf-pop'))} | {cell(hget(r, 'content-type'))} | {cell(hget(r, 'content-length'))} | "
                 f"{cell(', '.join(r.get('set_cookie_names') or []))} | {cell(r.get('body_head'), 80) or '(empty)'} | "
                 f"{cell(', '.join(r.get('markers') or []))} |")
    B = S.get("browser") or {}
    L += ["", "## 2. A real browser", ""]
    if not B.get("ran"):
        L += [f"Not run: {cell(B.get('skipped') or B.get('error') or '?', 400)}", ""]
        if B.get("install"):
            L += [f"pip: {cell(json.dumps(B['install'], ensure_ascii=False), 400)}", ""]
    else:
        L += [f"Chrome `{cell(B.get('chrome'))}` {cell(B.get('browser_version'))}, playwright {cell(B.get('playwright'))}, "
              f"headless, its own User-Agent `{cell(B.get('user_agent'), 200)}` (navigator.webdriver "
              f"{cell(B.get('webdriver'))}). {B.get('seconds')} s.", ""]
        if B.get("install"):
            L += [f"pip: {cell(json.dumps(B['install'], ensure_ascii=False), 300)}", ""]
        if B.get("error"):
            L += [f"Error: {cell(B['error'], 400)}", ""]
        L += ["| page | navigations (HTTP, x-amzn-waf-action) | network idle | seconds | title | cookies after | visible text (start) |",
              "|---|---|---|---|---|---|---|"]
        for p in B.get("pages") or []:
            chain = " -> ".join(f"{n.get('status')}{' (' + hget(n, 'x-amzn-waf-action') + ')' if hget(n, 'x-amzn-waf-action') else ''}"
                                for n in p.get("navigations") or []) or cell(p.get("error") or p.get("goto_error"))
            L.append(f"| {cell(p['url'])} | {cell(chain, 200)} | {cell(p.get('network_idle'))} | {cell(p.get('seconds'))} | "
                     f"{cell(p.get('title'), 100)} | {cell(', '.join(p.get('cookie_names') or []))} | "
                     f"{cell(p.get('text'), TEXT_HEAD)} |")
        L += ["", "Cookies the browser holds (names only):", "", "| name | domain | path | secure | httpOnly | sameSite | expires in |",
              "|---|---|---|---|---|---|---|"]
        for c in B.get("cookies") or []:
            L.append(f"| {cell(c['name'])} | {cell(c['domain'])} | {cell(c['path'])} | {cell(c['secure'])} | "
                     f"{cell(c['httpOnly'])} | {cell(c['sameSite'])} | {cell(c['expires_in_s'])} |")
        L += ["", "The browser's requests by host: " + cell(", ".join(f"{h} {n}" for h, n in sorted(
              (B.get("requests_by_host") or {}).items())), 600)
              + f"; images, fonts and media not fetched: {B.get('aborted', 0)}."]
        if B.get("challenge_requests"):
            L += ["", "The challenge's own requests (no query strings):", ""]
            L += [f"- {cell(x['method'])} {cell(x['url'], 200)} ({cell(x['type'])})" for x in B["challenge_requests"]]
        L += ["", "In the same browser context (its cookies), `context.request.get`:", "",
              "| file | HTTP | x-amzn-waf-action | x-cache | content-type | bytes | first bytes |", "|---|---|---|---|---|---|---|"]
        for x in B.get("files") or []:
            L.append(f"| {cell(x['url'])} | {cell(x.get('status') or x.get('error'))} | {cell(hget(x, 'x-amzn-waf-action') or '-')} | "
                     f"{cell(hget(x, 'x-cache'))} | {cell(hget(x, 'content-type'))} | {cell(x.get('bytes'))} | "
                     f"{cell(x.get('body_head'), 160) or '(empty)'} |")
    L += ["", "## 2b. The browser's cookies in plain requests (urllib GET of expb.csv)", ""]
    if S.get("token_skipped"):
        L += [f"Not asked: {cell(S['token_skipped'], 300)}", ""]
    else:
        L += ["| check | after the first | token age | User-Agent | HTTP | x-amzn-waf-action | x-cache | first bytes |",
              "|---|---|---|---|---|---|---|---|"]
        for t in S.get("token_checks") or []:
            L.append(f"| {cell(t.get('label'))} | {fmt_s(t.get('after_s'))} | {fmt_s(t.get('token_age_s'))} | "
                     f"{cell(t.get('ua_kind'))} | {cell(t.get('status') or t.get('error'))} | "
                     f"{cell(hget(t, 'x-amzn-waf-action') or '-')} | {cell(hget(t, 'x-cache'))} | "
                     f"{cell(t.get('body_head'), 120) or '(empty)'} |")
    L += ["", "## Every answer's headers and first bytes", ""]
    rows = [(f"1.{i} {r.get('kind')}", r) for i, r in enumerate(S.get("part1") or [], 1)]
    rows += [(f"2 browser page, navigation {j}", n) for p in B.get("pages") or [] for j, n in enumerate(p.get("navigations") or [], 1)]
    rows += [("2 browser context.request", x) for x in B.get("files") or []]
    rows += [(f"2b {t.get('label')}", t) for t in S.get("token_checks") or []]
    for label, r in rows:
        L += [f"### {cell(label)}: {cell(r.get('url'), 200)} -> {cell(r.get('status') or r.get('error'))}", ""]
        if r.get("sent"):
            L.append("Sent: " + cell("; ".join(f"{k}: {v}" for k, v in r["sent"].items()), 600))
            L.append("")
        L += [f"- {cell(k, 80)}: {cell(v, 300)}" for k, v in r.get("headers") or []]
        if r.get("body_head"):
            n = r.get("head_bytes") or len(r["body_head"].encode("utf-8"))
            L += ["", f"Body, first {n} bytes (markers: {cell(', '.join(r.get('markers') or []) or 'none')}):", ""]
            L += block(r["body_head"], HEAD)
        L.append("")
    L += ["summary.json holds every record. Cookie values are never kept.", ""]
    return "\n".join(L)


def write_summary(out, S, P, stage):
    S["stage"], S["written"] = stage, now_iso()
    S["finished"] = S["written"] if stage == "done" else None
    S["requests"], S["not_asked_past_deadline"], S["past_deadline"] = P.asked, P.not_asked, P.late()
    S["files_saved"] = P.saved
    V = verdicts(S)
    S["verdicts"] = {k: {"answer": w, "why": why} for k, (w, why) in V.items()}
    write_atomic(os.path.join(out, "summary.json"), json.dumps(S, ensure_ascii=False, indent=1))
    write_atomic(os.path.join(out, "summary.md"), markdown(S, V))
    print(f"waf_probe ({stage}): " + "; ".join(f"{k} {w}" for k, (w, _) in V.items() if k != "control"), flush=True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["--browser-worker"] and len(argv) == 2:
        return browser_worker(argv[1])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline", type=float, default=DEADLINE,
                    help="seconds from the start after which nothing is asked (default 1200: fetch.yml stops it at 1500)")
    ap.add_argument("--rewrite", action="append", default=[], metavar="FROM=TO", help="ask TO... for FROM... (tests)")
    ap.add_argument("--only-rewritten", action="store_true")
    ap.add_argument("--gap", type=float, default=GAP, help="seconds between two requests of ours to one host")
    ap.add_argument("--timeout", type=float, default=TIMEOUT)
    ap.add_argument("--visit", type=float, default=VISIT_S, help="the browser: seconds per page for the network to go idle")
    ap.add_argument("--token-waits", default=",".join(str(w) for w in TOKEN_WAITS),
                    help="seconds after the first token check for the later ones (default 60,240)")
    ap.add_argument("--chrome", default=os.environ.get("WAF_PROBE_CHROME") or None,
                    help="the browser's executable (default: $WAF_PROBE_CHROME, else google-chrome & co.)")
    ap.add_argument("--browser-python", default=None, help="the interpreter for the browser part (default: this one)")
    ap.add_argument("--no-install", action="store_true", help="never pip install playwright (tests)")
    a = ap.parse_args(argv)
    rewrite = []
    for r in a.rewrite:
        src, _, dst = r.partition("=")
        if not dst:
            ap.error(f"--rewrite {r}: FROM=TO")
        rewrite.append((src.rstrip("/"), dst.rstrip("/")))
    waits = tuple(float(w) for w in a.token_waits.split(",") if w.strip())
    os.makedirs(a.out, exist_ok=True)
    P = Probe(a.out, rewrite, a.only_rewritten, a.deadline, a.gap, a.timeout)
    S = {"fetcher": "waf_probe", "started": now_iso(), "deadline_s": a.deadline, "gap_s": a.gap,
         "token_waits_s": list(waits), "feed_user_agent": UA, "python": sys.version.split()[0],
         "part1": [], "browser": {"ran": False, "skipped": "not reached"}, "token_checks": []}
    stage = "at the start"
    try:
        write_summary(a.out, S, P, stage)
        S["part1"] = part1(P)
        stage = "after part 1"
        write_summary(a.out, S, P, stage)
        got = part2(P, a, S)
        stage = "after the browser"
        write_summary(a.out, S, P, stage)
        token_checks(P, S, got, waits, lambda st: write_summary(a.out, S, P, st))
        stage = "done"
    except Exception as exc:                               # the script's own fault: recorded, then exit 1
        S["crashed"] = f"{exc.__class__.__name__}: {exc} | " + traceback.format_exc()[-1500:]
        write_summary(a.out, S, P, stage + " (crashed)")
        print(traceback.format_exc(), file=sys.stderr)
        return 1
    write_summary(a.out, S, P, "done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
