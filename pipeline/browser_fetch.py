#!/usr/bin/env python3
"""The election-day feed's browser path: one headless Chrome, driven by playwright, that asks for the CEC's files when
bechirot.gov.il answers Python's urllib with an AWS WAF challenge (pipeline/live_fetch.py, request() and Browser).

    python3 pipeline/browser_fetch.py [--chrome PATH]               # the helper: JSON lines in, JSON lines out
    python3 pipeline/browser_fetch.py [--chrome PATH] --get URL     # one GET by hand: the status, the headers, the
                                                                    # size and the first bytes, as JSON

Why: from 22.10.2026 every urllib request to www., media26. and votes26.bechirot.gov.il gets HTTP 202 with
x-amzn-waf-action: challenge (CloudFront + AWS WAF), while the runner's own Google Chrome, headless, driven by
playwright with its default User-Agent, is not challenged (the probe of 23.10: pipeline/fetchers/waf_probe.py,
reports/fetch/waf_probe on the ops-reports branch).

What it is, and what it is not: Chrome as it comes, headless, with its own default User-Agent (HeadlessChrome/...), and
playwright's request context of a fresh browser context (BrowserContext.request: the browser's User-Agent and cookie jar;
gzip, deflate and br accepted and unpacked). No stealth plugin, no flag that hides automation, no other User-Agent, no
page, script or image loaded. Each request is the one GET or HEAD the feed asked for, at the feed's own pace, bounded by
its timeout, its body capped (max_bytes); nothing is retried here.

The protocol (live_fetch.Browser): first one line, {"ready": true, "version", "user_agent", "chrome", "start_s"} or
{"ready": false, "error"}; then for each line {"method", "url", "headers", "timeout_ms", "max_bytes"} on stdin, one line
{"status", "status_text", "url", "headers": [[name, value], ...], "body_b64", "bytes", "s"} or {"error"} on stdout. A
body over max_bytes is not passed on (an error, with the status and headers). It ends at the end of its stdin, closing
the browser, and also when Chrome or playwright's driver is gone (crashed, killed): that answer is
{"error", "closed": true, "sent": false} when the request never left (Chrome was already gone: alive() before each
request), "sent": true when it may have (gone during the request). live_fetch then starts a new helper, at once for the
same request when it was not sent, else at the next request; a helper that kept a dead browser would fail every later
request of a laptop's night-long loop. Whatever else writes to stdout (a library, the browser) goes to stderr, so the
protocol stays clean.
Chrome: --chrome (live_fetch passes $LIVE_CHROME or the one it found), else playwright's own Chromium when one is
installed (`playwright install chromium`, a laptop; never on the runner, which has Google Chrome).
"""
import argparse
import base64
import json
import os
import sys
import time

START_S = 45            # seconds for playwright and Chrome to start
REDIRECTS = 10          # redirects followed, as urllib's HTTPRedirectHandler


def first_line(exc):
    """An exception as one short line (playwright's messages run to a call log)."""
    lines = [ln for ln in str(exc).strip().splitlines() if ln.strip()]
    return f"{exc.__class__.__name__}: {lines[0].strip() if lines else ''}"[:300]


def start(chrome, start_s=START_S):
    """(playwright, browser, context, info), or RuntimeError with the reason in plain words."""
    t = time.time()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(f"playwright is not installed for {sys.executable} (python3 -m pip install playwright; no "
                           f"browser download is needed with Chrome on the machine): {first_line(exc)}")
    if chrome and not os.path.isfile(chrome):
        raise RuntimeError(f"no Chrome at {chrome}")
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(headless=True, timeout=start_s * 1000, **({"executable_path": chrome} if chrome else {}))
        ctx = browser.new_context()
        page = ctx.new_page()                    # about:blank: the browser's own User-Agent, nothing loaded
        ua = page.evaluate("navigator.userAgent")
        page.close()
    except Exception as exc:
        try:
            pw.stop()
        except Exception:
            pass
        raise RuntimeError((f"Chrome at {chrome} did not start" if chrome else
                            "no Chrome given and playwright's own Chromium did not start") + f": {first_line(exc)}")
    return pw, browser, ctx, {"ready": True, "version": browser.version, "user_agent": ua,
                              "chrome": chrome or "playwright's own Chromium", "start_s": round(time.time() - t, 2)}


def ask(ctx, req):
    """One request in the browser's request context -> the answer as a JSON-able dict."""
    t = time.time()
    method = str(req.get("method") or "GET").upper()
    resp = None
    try:
        resp = ctx.request.fetch(str(req["url"]), method=method, headers=req.get("headers") or None,
                                 timeout=float(req.get("timeout_ms") or 40000), max_redirects=REDIRECTS)
        out = {"status": resp.status, "status_text": resp.status_text, "url": resp.url,
               "headers": [[h["name"], h["value"]] for h in resp.headers_array]}
        body = b"" if method == "HEAD" else resp.body()
        cap = int(req.get("max_bytes") or 0)
        out.update(bytes=len(body), s=round(time.time() - t, 3))
        if cap and len(body) > cap:
            out["error"] = f"body over {cap} bytes ({len(body)})"
        else:
            out["body_b64"] = base64.b64encode(body).decode("ascii")
        return out
    except Exception as exc:
        return {"error": first_line(exc), "s": round(time.time() - t, 3)}
    finally:
        if resp is not None:
            try:
                resp.dispose()
            except Exception:
                pass


def alive(browser, ctx):
    """"" when Chrome and playwright's driver still answer, else why not: one call to the driver and Chrome's DevTools
    (the context's cookies; nothing on the network), so a browser that died while the helper waited is known before a
    request is sent (the sync API reads Chrome's "disconnected" only during a call)."""
    try:
        ctx.cookies()
    except Exception as exc:
        return first_line(exc)
    try:
        return "" if browser.is_connected() else "Chrome disconnected"
    except Exception as exc:
        return first_line(exc)


def serve(chrome):
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)                                # anything else written to stdout goes to stderr
    sys.stdout = sys.stderr

    def send(obj):
        proto.write(json.dumps(obj) + "\n")
        proto.flush()
    try:
        pw, browser, ctx, info = start(chrome)
    except Exception as exc:
        send({"ready": False, "error": str(exc) if isinstance(exc, RuntimeError) else first_line(exc)})
        return 0
    send(info)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                req = json.loads(line)
            except ValueError as exc:
                send({"error": f"not a request: {first_line(exc)}"})
                continue
            gone = alive(browser, ctx)
            if gone:                             # gone while we waited: nothing sent; a new helper sends it
                send({"error": f"the browser is gone, the request was not sent ({gone})", "closed": True, "sent": False})
                break
            ans = ask(ctx, req)
            if ans.get("error") and "status" not in ans and alive(browser, ctx):
                ans.update(closed=True, sent=True)   # gone during the request: it may have reached the server
            send(ans)
            if ans.get("closed"):
                break
    finally:
        for close in (ctx.close, browser.close, pw.stop):
            try:
                close()
            except Exception:
                pass
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--chrome", default=os.environ.get("LIVE_CHROME") or None, help="the Chrome or Chromium to run "
                    "(default $LIVE_CHROME, else playwright's own Chromium)")
    ap.add_argument("--get", default=None, metavar="URL", help="one GET, printed as JSON (the body's first 300 bytes)")
    ap.add_argument("--timeout", type=float, default=40, help="--get: seconds")
    a = ap.parse_args(argv)
    if not a.get:
        return serve(a.chrome)
    try:
        pw, browser, ctx, info = start(a.chrome)
    except Exception as exc:
        print(json.dumps({"ready": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    try:
        ans = ask(ctx, {"method": "GET", "url": a.get, "timeout_ms": a.timeout * 1000, "max_bytes": 64 * 2 ** 20})
        body = base64.b64decode(ans.pop("body_b64", "") or "")
        print(json.dumps({**info, **ans, "head": body[:300].decode("utf-8", "replace")}, ensure_ascii=False, indent=1))
    finally:
        for close in (ctx.close, browser.close, pw.stop):
            try:
                close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
