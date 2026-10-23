#!/usr/bin/env python3
"""Requests to the CEC's hosts: urllib first, and a headless Chrome behind the CEC's WAF. Standard library only (the
browser is a helper process, pipeline/browser_fetch.py), so whatever cannot import numpy can still use it.

Used by the election-night feed (pipeline/live_fetch.py: request(), fetch(), probe(); its status.json) and by the file
discovery (pipeline/discover.py, for the CEC's hosts); one code path, so the two see the CEC the same way.

    python3 pipeline/cec_fetch.py --compare URL [URL ...] [--summary FILE]
        # each URL once through urllib and once through the browser (a small Range GET each): what the WAF answers to
        # each path (.github/workflows/net-check.yml); one JSON object on stdout, a Markdown table appended to FILE

Why: from 22.10.2026 bechirot.gov.il (CloudFront + AWS WAF) answers urllib with a challenge (HTTP 202 and
x-amzn-waf-action, or 405 for a CAPTCHA; an empty body), while a real browser is not challenged (the runner probes of
23.10: reports/fetch/waf_probe and reports/fetch/feed_fetch_probe on the ops-reports branch). On such an answer
request() asks the same URL through a headless Chrome (pipeline/browser_fetch.py: playwright's request context, Chrome's
own User-Agent, nothing hidden or spoofed), one browser per process. The host is then asked through the browser directly,
and through urllib again every WAF_RECHECK seconds (the challenge gone: back to urllib), so the CEC still gets one request
where it got one. NET["via"] ("fetch_via" in live_config.json): "auto" (the default) | "urllib" (never the browser) |
"browser" (only the browser).

A caller that asks from several threads (discover.py) replaces BROWSER with a BrowserPool: up to N helpers, each one
request at a time, a new one started only while all are busy, so a slow CEC does not queue every thread behind one
Chrome. A caller's pace hook runs before every request it starts, on either path (for the browser once that helper is
up, inside its lock), so a caller's own limit on requests per host holds whichever path asks, and a browser that cannot
start takes no slot (nor does a request skipped while the browser is known to be failing).
"""
import argparse
import atexit
import base64
import collections
import datetime as dt
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from zoneinfo import ZoneInfo
    IL = ZoneInfo("Asia/Jerusalem")
except Exception:                                   # a runner without tz data: IST (UTC+2) from 25.10.2026
    IL = dt.timezone(dt.timedelta(hours=2))

# the feed's own User-Agent (live_fetch.UA); a caller passes its own (discover.py: "... kalpi26-discover"). urllib only:
# the browser always asks with Chrome's own User-Agent
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live"
MAX_BODY = 32 * 2 ** 20  # bytes: a bigger body is rejected (2022's expb.csv was 1.7 MB), by both paths
FETCH_VIA = ("auto", "urllib", "browser")   # live_config.json "fetch_via"
WAF_RECHECK = 600        # seconds: a host whose WAF challenged urllib is asked through the browser, and urllib again after this
HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_fetch.py")
# the browser path's Chrome when $LIVE_CHROME is not set (the workflows set it): Google Chrome's own binary first (the
# hosted runner's), then the wrappers and Chromium, then macOS's (a self-hosted runner or a laptop)
CHROMES = ("/opt/google/chrome/chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
BROWSER_START_S = 60     # seconds for the helper's first line (playwright and Chrome started; about a second on a runner)
BROWSER_RETRY_S = 300    # a browser that failed to start is tried again this much later (the laptop loop)


def now_il():
    return dt.datetime.now(dt.timezone.utc).astimezone(IL)


class WafError(IOError):
    """The CEC's WAF answered instead of the file, and no path got past it."""


class BrowserUnavailable(IOError):
    """The browser path cannot run here (no playwright, no Chrome, Chrome did not start)."""


class Answer:
    """One HTTP answer, from either path: status, headers (names in lower case), body, final url, path ("urllib" or
    "browser"), waf (waf_kind: "" or the WAF's action), exc (urllib's own HTTPError for a status of 400 or more)."""

    def __init__(self, status, headers, body, url, path, reason="", exc=None):
        self.status, self.body, self.url, self.path, self.reason, self.exc = status, body or b"", url, path, reason, exc
        self.headers = {}
        for k, v in (headers.items() if hasattr(headers, "items") else headers or ()):
            k = str(k).lower()
            self.headers[k] = f"{self.headers[k]}, {v}" if k in self.headers else str(v)
        self.waf = waf_kind(status, self.headers, self.body)


def waf_kind(status, headers, body):
    """The AWS WAF action when an answer is the WAF's instead of the file's, else "": x-amzn-waf-action on a 202
    (challenge) or a 405 (captcha), or CloudFront's 202 with an empty body (the header not exposed), as bechirot.gov.il
    has answered urllib since 22.10.2026. headers: names in lower case."""
    act = (headers.get("x-amzn-waf-action") or "").strip().lower()
    if act and status in (202, 405):
        return act
    cdn = " ".join(headers.get(k, "") for k in ("server", "x-cache", "via")).lower()
    if status == 202 and not (body or b"").strip() and "cloudfront" in cdn:
        return "challenge"
    return ""


def waf_text(a):
    """A WAF answer in words, for status.errors, the probe's note and discover.py's report."""
    act = a.headers.get("x-amzn-waf-action")
    return (f"WAF {a.waf} from {urllib.parse.urlsplit(a.url).netloc} through {a.path}: HTTP {a.status}"
            + (f", x-amzn-waf-action: {act}" if act else ", CloudFront, empty body"))


# NET: this process's fetching. via: "fetch_via"; hosts: the hosts whose WAF challenged urllib ({netloc: {since, ts,
# action}}; the feed keeps them in state.json "waf_hosts" between passes); log: the requests (the feed's printed line's
# "fetches", per pass); browser_error: why the browser path failed; browser_lost: why a Chrome was lost (Browser.request)
NET = {"via": "auto", "hosts": {}, "log": [], "browser_error": "", "last": None, "browser_start_s": None, "browser_lost": []}


def fetch_via(cfg, errors=None):
    """live_config.json "fetch_via": "auto" (default: urllib, the browser behind the WAF), "urllib" or "browser"."""
    v = cfg.get("fetch_via")
    if v in (None, ""):
        return "auto"
    if v in FETCH_VIA:
        return v
    if errors is not None:
        errors.append(f'config: fetch_via {v!r} is not "auto", "urllib" or "browser"; using "auto"')
    return "auto"


def _note(url, method, path, t, a=None, error="", trail=None):
    """A request in the log (NET["log"]; the feed's printed line), and in the caller's own `trail` when it keeps one."""
    rec = {"url": url, "method": method, "path": path, "http": a.status if a else 0, "waf": a.waf if a else "",
           "bytes": len(a.body) if a else 0, "s": round(time.time() - t, 2)}
    if a is not None and a.headers.get("x-amzn-waf-action"):
        rec["waf_header"] = a.headers["x-amzn-waf-action"]
    if error:
        rec["error"] = error[:200]
    NET["log"].append(rec)
    if trail is not None:
        trail.append(rec)
    if a is not None:
        NET["last"] = a                           # the last answer, whole (pipeline/fetchers/feed_fetch_probe.py)


def urllib_answer(url, method="GET", headers=None, timeout=40, ua=None, max_body=None):
    """One urllib request with the caller's User-Agent; an HTTP error is an Answer too (path "urllib"). A network error,
    or a URL that cannot be sent, raises."""
    max_body = max_body or MAX_BODY
    req = urllib.request.Request(url, headers={"User-Agent": ua or UA, **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = b"" if method == "HEAD" else r.read(max_body + 1)
            return Answer(r.status, r.headers, body, r.geturl(), "urllib", getattr(r, "reason", ""))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(65536) or b""
        except Exception:
            body = b""
        return Answer(exc.code, exc.headers or {}, body, url, "urllib", exc.reason, exc)


def request(url, method="GET", headers=None, timeout=40, ua=None, max_body=None, recheck=None, clock=None, trail=None,
            pace=None):
    """One request to the CEC: urllib first, as always; when its answer is the WAF's (waf_kind), or NET["via"] is
    "browser", the same request through the browser (BROWSER, one per process). A host whose WAF challenged urllib is
    asked through the browser directly, and through urllib again every `recheck` seconds (WAF_RECHECK; when the
    challenge is gone the host goes back to urllib), so the CEC gets one request where it got one. "urllib" never starts
    the browser. A network error raises; an HTTP answer, of any status, is returned (Answer: its path and waf). Raises
    WafError when the WAF answered urllib and the browser cannot run.
    ua: urllib's User-Agent (UA, the feed's); max_body: the body cap on both paths (MAX_BODY; a longer body comes back
    cut to max_body + 1 bytes from either path); clock: what "since" is stamped with (now_il); trail: a list that gets
    this call's attempts (NET["log"]'s records); pace(path): called before each attempt starts ("urllib", or "browser"
    once the browser is up, inside its lock): a caller's own pace per host. An exception from pace is raised as it is,
    and that attempt, never sent, is not recorded."""
    headers = dict(headers or {})
    kw = dict(ua=ua, max_body=max_body, recheck=recheck, clock=clock, trail=trail, pace=pace)
    recheck = WAF_RECHECK if recheck is None else recheck
    host = urllib.parse.urlsplit(url).netloc
    via = NET["via"]
    held = NET["hosts"].get(host)
    # a held host goes to the browser directly, unless the browser has just failed to start: urllib is all there is then
    browser_first = via == "browser" or (via == "auto" and held and time.time() - held.get("ts", 0) < recheck
                                         and not BROWSER.failing())
    first = None
    if not browser_first:
        if pace:
            pace("urllib")
        t = time.time()
        try:
            first = urllib_answer(url, method, headers, timeout, ua, max_body)
        except Exception as exc:
            _note(url, method, "urllib", t, error=f"{exc.__class__.__name__}: {exc}", trail=trail)
            raise
        _note(url, method, "urllib", t, first, trail=trail)
        if not first.waf:
            NET["hosts"].pop(host, None)          # no challenge (any more): urllib it is
            return first
        NET["hosts"][host] = {"since": (held or {}).get("since") or (clock or now_il)().isoformat(timespec="minutes"),
                              "ts": time.time(), "action": first.waf}
        if via == "urllib":
            raise WafError(f'{waf_text(first)}; "fetch_via" is "urllib" in live_config.json: the browser path is off')
        if BROWSER.failing():                     # it failed to start BROWSER_RETRY_S ago: not asked, no pace slot taken
            why = BROWSER.failed[1] if BROWSER.failed else "the browser failed to start"
            NET["browser_error"] = why
            _note(url, method, "browser", time.time(), error=why, trail=trail)
            raise WafError(f"{waf_text(first)}; the browser path is unavailable: {why}")
    t, sent = [time.time()], [False]

    def before():                                 # the browser up, holding its lock: the caller's pace, then the clock
        if pace:
            pace("browser")
        t[0], sent[0] = time.time(), True         # (the start, and the wait for other threads, are not this request's time)
    try:
        a = BROWSER.request(url, method, headers, timeout, max_body, before=before)
    except BrowserUnavailable as exc:
        NET["browser_error"] = str(exc)
        _note(url, method, "browser", t[0], error=str(exc), trail=trail)
        if first is None and via == "auto":       # a held host: ask urllib after all (the browser now counts as failing)
            return request(url, method, headers, timeout, **kw)
        why = waf_text(first) if first else '"fetch_via" is "browser" in live_config.json'
        raise WafError(f"{why}; the browser path is unavailable: {exc}")
    except Exception as exc:
        if sent[0]:                               # not when the caller's pace raised (discover.py's deadline): unsent
            _note(url, method, "browser", t[0], error=f"{exc.__class__.__name__}: {exc}", trail=trail)
        raise
    _note(url, method, "browser", t[0], a, trail=trail)
    return a


def find_chrome():
    """(path, why not): $LIVE_CHROME (the workflows set it to the runner's Chrome) or, when it is not set, Google Chrome
    or Chromium in the usual places (CHROMES). (None, why) when there is none."""
    env = os.environ.get("LIVE_CHROME", "").strip()
    if env:
        if os.path.isfile(env) and os.access(env, os.X_OK):
            return env, ""
        return None, f"LIVE_CHROME={env}: no such program"
    for c in CHROMES:
        p = c if os.path.isabs(c) else shutil.which(c)
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p, ""
    return None, "no Chrome or Chromium found (LIVE_CHROME, /opt/google/chrome/chrome, google-chrome, chromium)"


class Browser:
    """The browser path of this process: one helper (pipeline/browser_fetch.py, run by $LIVE_BROWSER_PYTHON or this
    interpreter) holding one headless Chrome, started at the first request that needs it and kept until the process ends
    (live.yml runs a process per pass: about a second to start; the laptop loop keeps one for the night; discover.py a
    BrowserPool of them for its run). Its own stdout and stderr never reach the caller's: the feed's status line stays
    the last line. One request at a time (a lock). A request is bounded by its timeout (plus 20 s;
    then the helper is stopped); a failed start is not retried for BROWSER_RETRY_S. When Chrome or playwright's driver
    is gone (crashed, killed) the helper says so ("closed") and ends, and a new one is started: at once for the same
    request when it was not sent (Chrome was gone before it), else at the next request (it may have reached the CEC:
    one request a pass, as always); "lost" counts them."""

    def __init__(self):
        self.proc, self.info, self.failed, self.starts, self.start_s, self.lost = None, None, None, 0, None, 0
        self._lines, self._err = None, collections.deque(maxlen=12)
        self._atexit = False
        self._lock = threading.Lock()

    def failing(self):
        return bool(self.failed) and time.time() - self.failed[0] < BROWSER_RETRY_S

    def _fail(self, why):
        self.failed = (time.time(), why)
        self.close()
        raise BrowserUnavailable(why)

    @staticmethod
    def _pump(stream, q):
        for line in stream:
            q.put(line)
        q.put(None)

    def _drain(self, stream):
        for line in stream:
            if line.strip():
                self._err.append(line.rstrip()[:300])

    def _read(self, timeout):
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            return None
        try:
            return json.loads(line) if line else None
        except ValueError:
            return None

    def _tail(self):
        return f" (helper: {' | '.join(list(self._err)[-3:])})"[:400] if self._err else ""

    def _start(self):
        if self.failing():
            raise BrowserUnavailable(self.failed[1])
        chrome, why = find_chrome()
        if os.environ.get("LIVE_CHROME", "").strip() and not chrome:
            self._fail(why)
        python = os.environ.get("LIVE_BROWSER_PYTHON", "").strip() or sys.executable
        self.start_s = None
        t = time.time()
        try:
            self.proc = subprocess.Popen([python, HELPER] + (["--chrome", chrome] if chrome else []),
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, encoding="utf-8", bufsize=1, start_new_session=True)
        except OSError as exc:
            self._fail(f"cannot run the browser helper with {python}: {exc}")
        self.starts += 1
        self._lines = queue.Queue()
        self._err.clear()
        threading.Thread(target=self._pump, args=(self.proc.stdout, self._lines), daemon=True).start()
        threading.Thread(target=self._drain, args=(self.proc.stderr,), daemon=True).start()
        first = self._read(BROWSER_START_S)
        if not first or not first.get("ready"):
            err = (first or {}).get("error") or f"the browser helper did not start within {BROWSER_START_S} s{self._tail()}"
            self._fail(f"{why}; {err}" if why else err)
        self.info, self.start_s = first, round(time.time() - t, 2)
        NET["browser_start_s"] = self.start_s
        if not self._atexit:
            atexit.register(self.close)
            self._atexit = True

    def request(self, url, method="GET", headers=None, timeout=40, max_body=None, before=None):
        """One request through the browser -> Answer (path "browser"; a body over max_body cut to max_body + 1 bytes,
        as urllib reads it). BrowserUnavailable when it cannot start (nothing sent, before() not called); IOError when
        the request itself failed (a timeout, a refused connection, Chrome gone during it): "no HTTP answer" in its
        words, so the page's reader note is the neutral one (site/src/js/live.js feedNotes). before(): called once,
        holding the lock, once the browser is up and before anything is sent (a caller's pace; it may raise)."""
        with self._lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()                     # first: a browser that cannot start takes no slot of the caller's pace
            if before:
                before()
            return self._request(url, method, headers, timeout, max_body or MAX_BODY)

    def _request(self, url, method, headers, timeout, max_body):
        for attempt in (1, 2):
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            msg = {"method": method, "url": url, "headers": headers or {}, "timeout_ms": int(timeout * 1000),
                   "max_bytes": max_body}
            try:
                self.proc.stdin.write(json.dumps(msg) + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError) as exc:
                self.close()
                raise IOError(f"browser: no HTTP answer, the helper is gone ({exc}){self._tail()}")
            ans = self._read(timeout + 20)
            if ans is None:
                self.close()
                raise IOError(f"browser: no HTTP answer within {timeout + 20:g} s{self._tail()}")
            if ans.get("closed"):                 # Chrome or the driver gone: the helper has ended; a new one next
                self.close()
                self.lost += 1
                NET["browser_lost"].append(str(ans.get("error"))[:200])
                if ans.get("sent") is False and attempt == 1:
                    continue                      # it never left: the same request through a new Chrome, still one
                raise IOError(f"browser: no HTTP answer, the browser is gone ({ans.get('error')}); a new one starts "
                              f"at the next request")
            if ans.get("error"):
                raise IOError(f"browser: {ans['error']}" + (f" (HTTP {ans['status']})" if ans.get("status") else
                                                            " (no HTTP answer)"))
            body = base64.b64decode(ans.get("body_b64") or "")
            return Answer(ans["status"], ans.get("headers") or [], body, ans.get("url") or url, "browser",
                          ans.get("status_text", ""))

    def close(self):
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            p.stdin.close()                       # the helper closes Chrome at the end of its input
        except Exception:
            pass
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)  # its own session: playwright's driver and Chrome go with it
            except Exception:
                p.kill()
            try:
                p.wait(timeout=5)
            except Exception:
                pass


class BrowserPool:
    """Up to `size` browser helpers (Browser) for a caller that asks from several threads, in place of BROWSER
    (discover.py: CF.BROWSER = BrowserPool(n)). A request takes an idle helper and starts another only while all are
    busy and fewer than `size` exist, so a slow CEC does not queue every thread behind one Chrome (with one, a full
    discovery run lasted the sum of the CEC's answer times). Each helper still asks one request at a time, and the
    caller's pace per host (before()) runs inside it once it is up: the CEC gets no more requests, nor faster, than the
    caller's own pace lets urllib send. A helper that fails to start is dropped and no other is started for
    BROWSER_RETRY_S; the request then waits for a running one, and is BrowserUnavailable only when none is left (nothing
    was sent). The requests waiting for a helper get one in the order they came (a queue), so a thread is never
    overtaken by the ones that keep coming back, and a caller's order (discover.py asks what matters first) holds.
    info, starts, start_s, lost, failed and failing() read as Browser's, for the reports."""

    def __init__(self, size=3):
        self.size, self.members, self.idle, self.ever, self.failed = max(1, int(size)), [], [], [], None
        self._cond, self._queue = threading.Condition(), collections.deque()

    def _may_start(self):
        return not (self.failed and time.time() - self.failed[0] < BROWSER_RETRY_S)

    def failing(self):
        with self._cond:
            return not self.members and not self._may_start()

    @property
    def info(self):
        return next((b.info for b in list(self.ever) if b.info), None)

    @property
    def start_s(self):
        return next((b.start_s for b in list(self.ever) if b.start_s is not None), None)

    @property
    def starts(self):
        return sum(b.starts for b in list(self.ever))

    @property
    def lost(self):
        return sum(b.lost for b in list(self.ever))

    def request(self, url, method="GET", headers=None, timeout=40, max_body=None, before=None):
        while True:
            with self._cond:
                me = object()
                self._queue.append(me)
                try:
                    while True:
                        if self._queue[0] is me:  # first come, first served
                            if self.idle:
                                b = self.idle.pop()   # the one used last: a new Chrome only when all are busy
                                break
                            if len(self.members) < self.size and self._may_start():
                                b = Browser()
                                self.members.append(b)
                                self.ever.append(b)
                                break
                            if not self.members:
                                raise BrowserUnavailable(self.failed[1] if self.failed else "the browser failed to start")
                        self._cond.wait()
                finally:
                    self._queue.remove(me)
                    self._cond.notify_all()       # the next in the queue looks again
            try:
                return b.request(url, method, headers, timeout, max_body, before)
            except BrowserUnavailable as exc:     # it did not start: nothing was sent
                with self._cond:
                    self.failed = (time.time(), str(exc))
                    self.members.remove(b)
                    b = None
                    self._cond.notify_all()
                    if not self.members:
                        raise
            finally:
                if b is not None:
                    with self._cond:
                        self.idle.append(b)
                        self._cond.notify_all()

    def close(self):
        with self._cond:
            members, self.members, self.idle = list(self.members), [], []
        for b in members:
            b.close()


BROWSER = Browser()


# ------------------------------------------------------------------ --compare: urllib and the browser side by side
def _row(a, t, error=""):
    if a is None:
        return {"http": 0, "error": error[:300], "s": round(time.time() - t, 2)}
    out = {"http": a.status, "waf": a.waf, "waf_header": a.headers.get("x-amzn-waf-action", ""), "bytes": len(a.body),
           "x_cache": a.headers.get("x-cache", ""), "type": a.headers.get("content-type", ""), "s": round(time.time() - t, 2)}
    return {k: v for k, v in out.items() if v != ""}


def compare(urls, timeout=25, nbytes=4096, gap=1.0):
    """Each URL through urllib (the feed's User-Agent) and then through the browser (Chrome's own), a Range GET of the
    first `nbytes` each, `gap` seconds apart: {"records": [{url, urllib, browser}], "waf_urllib": [the hosts whose WAF
    challenged urllib], "browser_past": True | False (challenged too) | None (no WAF, or no answer through the browser),
    "browser": {version, user_agent} or {error}}."""
    hdr = {"Range": f"bytes=0-{nbytes - 1}", "Cache-Control": "no-cache"}
    recs = []
    for i, url in enumerate(urls):
        if i:
            time.sleep(gap)
        rec, t = {"url": url}, time.time()
        try:
            rec["urllib"] = _row(urllib_answer(url, "GET", hdr, timeout, UA, nbytes * 4), t)
        except Exception as exc:
            rec["urllib"] = _row(None, t, f"{exc.__class__.__name__}: {exc}")
        time.sleep(gap)
        t = time.time()
        try:
            rec["browser"] = _row(BROWSER.request(url, "GET", hdr, timeout), t)
        except Exception as exc:
            rec["browser"] = _row(None, t, f"{exc.__class__.__name__}: {exc}")
        recs.append(rec)
    BROWSER.close()
    waf = sorted({urllib.parse.urlsplit(r["url"]).netloc for r in recs if r["urllib"].get("waf")})
    asked = [r["browser"] for r in recs if r["browser"].get("http")]
    return {"records": recs, "waf_urllib": waf,
            "browser_past": all(not b.get("waf") for b in asked) if waf and asked else None,
            "browser": ({k: BROWSER.info.get(k) for k in ("version", "user_agent")} if BROWSER.info and asked else
                        {"error": next((r["browser"]["error"] for r in recs if r["browser"].get("error")), "not run")})}


def compare_markdown(out, when):
    """compare()'s result for the run's summary: the verdict, the browser, a row per URL."""
    def cell(d):
        if not d.get("http"):
            return f"no answer: {d.get('error', '')[:160]}".replace("|", "/")
        return (f"{d['http']}" + (f" WAF {d['waf']}" if d.get("waf") else "") + f", {d.get('bytes', 0)} bytes, {d.get('s')} s"
                + (f", x-cache {d['x_cache']}" if d.get("x_cache") else ""))
    b, waf, past = out["browser"], out["waf_urllib"], out["browser_past"]
    verdict = ("**the browser past it: yes**" if past else "**the browser past it: no** (challenged too)" if past is False
               else f"**the browser: unavailable** ({str(b.get('error'))[:200]})" if not b.get("version")
               else "the browser: not needed")
    lines = [f"## The CEC's WAF: urllib and the browser, {when}", "",
             ("**WAF on urllib: yes** (" + ", ".join(waf) + ")" if waf else "**WAF on urllib: no**") + "; " + verdict, ""]
    if b.get("version"):
        lines += [f"Browser: Chrome {b['version']}, its own User-Agent `{b.get('user_agent')}`", ""]
    lines += ["| URL | urllib (the feed's User-Agent) | browser (Chrome's own) |", "|---|---|---|"]
    lines += [f"| {r['url']} | {cell(r['urllib'])} | {cell(r['browser'])} |" for r in out["records"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--compare", nargs="+", metavar="URL", required=True,
                    help="each URL once through urllib and once through the browser")
    ap.add_argument("--summary", help="append the Markdown table here ($GITHUB_STEP_SUMMARY)")
    ap.add_argument("--timeout", type=float, default=25)
    ap.add_argument("--bytes", type=int, default=4096, help="the Range GET's size")
    ap.add_argument("--gap", type=float, default=1.0, help="seconds between two requests")
    a = ap.parse_args(argv)
    out = compare(a.compare, a.timeout, a.bytes, a.gap)
    md = compare_markdown(out, now_il().strftime("%d.%m %H:%M") + " Israel time")
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(md)
    print(md)                                     # the run's log; then the record, the last line
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
