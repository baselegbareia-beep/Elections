#!/usr/bin/env python3
"""Offline test of tools/home_turnout.py: a stand-in map page and a stand-in GitHub API on localhost.

    HOME_TURNOUT_PYTHON=/path/to/venv/python HOME_TURNOUT_CHROME=/path/to/chrome python3 tools/test_home_turnout.py

The python must have playwright; the Chrome defaults to the newest Chromium under /opt/pw-browsers. Checks: a wrong
token is refused in Hebrew and asked again; two rounds become two commits on home-capture (created from main, the
second on top of the first), each with capture/<stamp>/manifest.json and the data answers (JSON, CSV, a POST answer,
and the GeoJSON the turnout tab loads when clicked); nothing that logs in or submits is clicked; the app's script is
kept once; main is only read, never written; the token appears in no output, no file and no uploaded content.
"""
import base64
import glob
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "home_turnout.py")
REPO = "baselegbareia-beep/Elections"
TOKEN = "github_pat_TEST" + hashlib.sha256(os.urandom(16)).hexdigest()[:40]

INDEX = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><title>מפת הבחירות (בדיקה)</title>
<script type="module" src="/assets/index-abc123.js"></script></head>
<body><div id="app">טוען...</div>
<form action="/api/login" method="post"><input type="password" name="p"><button>הצג אחוזי הצבעה</button></form>
</body></html>"""
APP_JS = """const TURNOUT = "/api/turnout.json";
fetch(TURNOUT).then(r => r.json()).then(j => {
  document.getElementById('app').innerHTML = '<div role="tablist"><span role="tab" id="t">אחוזי הצבעה</span>' +
    ' <button id="lg">כניסה לאחוזי הצבעה</button></div><p>עדכון: ' + j.hour + '</p>';
  document.getElementById('t').onclick = () => fetch('/api/layer.geojson').then(r => r.json());
  document.getElementById('lg').onclick = () => fetch('/api/login', {method: 'POST'});
});
fetch('/data/stations.csv').then(r => r.text());
fetch('/api/query', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({layer: 'turnout'})});
"""


def serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


class Site(BaseHTTPRequestHandler):
    hits, rounds = [], [0]

    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        body = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        Site.hits.append(("GET", self.path))
        if self.path == "/":
            Site.rounds[0] += 1
            return self._send(200, "text/html; charset=utf-8", INDEX)
        if self.path == "/assets/index-abc123.js":
            return self._send(200, "application/javascript", APP_JS)
        if self.path == "/api/turnout.json":
            return self._send(200, "application/json", json.dumps({"hour": "10:00", "round": Site.rounds[0], "stations": 3}))
        if self.path == "/data/stations.csv":
            return self._send(200, "text/csv; charset=utf-8", "סמל ישוב,קלפי,בזב,מצביעים\n3000,1.0,700,%d\n" % (100 + Site.rounds[0]))
        if self.path == "/api/layer.geojson":
            return self._send(200, "application/geo+json", json.dumps({"type": "FeatureCollection", "features": []}))
        return self._send(404, "text/plain", "no")

    def do_POST(self):
        Site.hits.append(("POST", self.path))
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/api/query":
            return self._send(200, "application/json", json.dumps({"layer": "turnout", "rows": [1, 2]}))
        return self._send(403, "text/plain", "no")


def blob_sha(b):
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()


class Api(BaseHTTPRequestHandler):
    log, raw = [], []
    refs = {"main": "c0"}
    commits = {"c0": {"tree": "t0", "parents": [], "message": "main"}}
    trees = {"t0": {"README.md": "b0"}}
    blobs = {"b0": b"readme"}

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        Api.raw.append(raw)
        body = json.loads(raw) if raw else None
        Api.log.append({"method": method, "path": self.path, "body": body,
                        "auth": self.headers.get("Authorization") == "Bearer " + TOKEN})
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send(401, {"message": "Bad credentials"})
        pre = "/repos/" + REPO
        p = self.path
        if method == "GET" and p == pre:
            return self._send(200, {"full_name": REPO})
        if method == "GET" and p.startswith(pre + "/git/ref/heads/"):
            b = p[len(pre + "/git/ref/heads/"):]
            return self._send(200, {"object": {"sha": Api.refs[b]}}) if b in Api.refs else self._send(404, {"message": "Not Found"})
        if method == "POST" and p == pre + "/git/refs":
            b = body["ref"][len("refs/heads/"):]
            if b in Api.refs:
                return self._send(422, {"message": "Reference already exists"})
            Api.refs[b] = body["sha"]
            return self._send(201, {"ref": body["ref"]})
        if method == "GET" and p.startswith(pre + "/git/commits/"):
            sha = p.rsplit("/", 1)[1]
            c = Api.commits[sha]
            return self._send(200, {"sha": sha, "tree": {"sha": c["tree"]}, "parents": [{"sha": x} for x in c["parents"]]})
        if method == "POST" and p == pre + "/git/blobs":
            data = base64.b64decode(body["content"])
            sha = blob_sha(data)
            Api.blobs[sha] = data
            return self._send(201, {"sha": sha})
        if method == "POST" and p == pre + "/git/trees":
            t = dict(Api.trees[body["base_tree"]])
            for e in body["tree"]:
                assert e["sha"] in Api.blobs, e
                t[e["path"]] = e["sha"]
            sha = "t" + hashlib.sha1(json.dumps(t, sort_keys=True).encode()).hexdigest()[:12]
            Api.trees[sha] = t
            return self._send(201, {"sha": sha})
        if method == "POST" and p == pre + "/git/commits":
            assert body["tree"] in Api.trees and all(x in Api.commits for x in body["parents"])
            sha = "c" + hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]
            Api.commits[sha] = {"tree": body["tree"], "parents": body["parents"], "message": body["message"]}
            return self._send(201, {"sha": sha})
        if method == "PATCH" and p.startswith(pre + "/git/refs/heads/"):
            b = p[len(pre + "/git/refs/heads/"):]
            if b not in Api.refs or Api.refs[b] not in Api.commits[body["sha"]]["parents"]:
                return self._send(422, {"message": "Update is not a fast forward"})
            Api.refs[b] = body["sha"]
            return self._send(200, {"object": {"sha": body["sha"]}})
        return self._send(404, {"message": "Not Found"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PATCH(self):
        self._handle("PATCH")


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        check.failed += 1


check.failed = 0


def test_israel_clock():
    spec = importlib.util.spec_from_file_location("home_turnout", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    for when, off in ((datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc), 2), (datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc), 3),
                      (datetime(2026, 10, 24, 22, 59, tzinfo=timezone.utc), 3), (datetime(2026, 10, 24, 23, 0, tzinfo=timezone.utc), 2),
                      (datetime(2026, 3, 26, 23, 59, tzinfo=timezone.utc), 2), (datetime(2026, 3, 27, 0, 0, tzinfo=timezone.utc), 3)):
        got = m.israel_now(when, zoneinfo_ok=False).utcoffset().total_seconds() / 3600
        check(got == off, "Israel clock without a tz database: %s -> UTC+%d" % (when.isoformat(), got))


def main():
    py = os.environ.get("HOME_TURNOUT_PYTHON") or sys.executable
    chrome = os.environ.get("HOME_TURNOUT_CHROME") or (sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")) or [""])[-1]
    if subprocess.run([py, "-c", "import playwright.sync_api"], capture_output=True).returncode != 0:
        print("skipped: %s has no playwright (HOME_TURNOUT_PYTHON)" % py)
        return 0
    test_israel_clock()
    site, site_url = serve(Site)
    api, api_url = serve(Api)
    work = tempfile.mkdtemp(prefix="home_turnout_test_")
    env = dict(os.environ, HOME_TURNOUT_API=api_url, HOME_TURNOUT_URL=site_url + "/", HOME_TURNOUT_CHROME=chrome,
               HOME_TURNOUT_INTERVAL="3", HOME_TURNOUT_SETTLE="1", HOME_TURNOUT_ROUNDS="2", HOME_TURNOUT_STOP="off",
               PYTHONIOENCODING="utf-8")
    p = subprocess.run([py, SCRIPT], input="wrong-token\n" + TOKEN + "\n", capture_output=True, text=True, env=env,
                       cwd=work, timeout=600, start_new_session=True)     # no terminal: getpass reads stdin
    out = p.stdout + p.stderr
    print(out)
    site.shutdown()
    api.shutdown()

    check(p.returncode == 0, "exit code 0 (got %s)" % p.returncode)
    check("הטוקן שגוי" in out, "a wrong token is refused in Hebrew and asked again")
    check(out.count("הועלה ל-GitHub") == 2, "two rounds reported as uploaded")
    writes = [r for r in Api.log if r["method"] != "GET"]
    check(all(r["auth"] for r in Api.log[1:]), "every call after the wrong token carries the right one")
    check(not any("main" in r["path"] or "main" in str((r["body"] or {}).get("ref", "")) for r in writes), "no write addresses main")
    check(Api.refs["main"] == "c0", "main unchanged")
    check(sum(1 for r in Api.log if r["path"].endswith("/git/ref/heads/main")) == 1, "main read once (to create home-capture)")
    check({r["path"].split(REPO)[1] for r in writes} <= {"/git/refs", "/git/blobs", "/git/trees", "/git/commits",
                                                         "/git/refs/heads/home-capture"}, "writes only blobs/trees/commits/home-capture")
    patches = [r for r in writes if r["method"] == "PATCH"]
    check(len(patches) == 2, "two commits on home-capture (got %d)" % len(patches))
    head = Api.refs.get("home-capture")
    c2 = Api.commits.get(head, {})
    c1 = Api.commits.get((c2.get("parents") or [None])[0], {})
    check(bool(c1) and c1.get("parents") == ["c0"], "the first commit sits on main's head, the second on the first")
    tree = Api.trees.get(c2.get("tree"), {})
    stamps = sorted({k.split("/")[1] for k in tree if k.startswith("capture/")})
    check(len(stamps) == 2, "two round folders: %s" % stamps)
    for i, s in enumerate(stamps):
        files = [k for k in tree if k.startswith("capture/" + s + "/")]
        man = json.loads(Api.blobs[tree["capture/%s/manifest.json" % s]]) if "capture/%s/manifest.json" % s in tree else {}
        check(bool(man), "round %d: manifest.json" % (i + 1))
        names = " ".join(files)
        for want in ("turnout.json", "stations.csv", "api_query.json", "layer.geojson", "screenshot.jpg"):
            check(want in names, "round %d: %s kept" % (i + 1, want))
        check(any("index-abc123.js" in f for f in files) == (i == 0), "round %d: the app's script kept %s" % (i + 1, "once" if i == 0 else "only once"))
        check([c["text"] for c in man.get("clicked", [])] == ["אחוזי הצבעה"], "round %d: clicked only the turnout tab: %s" % (i + 1, man.get("clicked")))
        rows = man.get("responses", [])
        check(any(r["method"] == "POST" and r.get("post") for r in rows), "round %d: the POST and its body listed" % (i + 1))
        check(all({"url", "method", "status", "type", "bytes"} <= set(r) for r in rows), "round %d: every answer has url/method/status/type/bytes" % (i + 1))
    csvs = [Api.blobs[v] for k, v in tree.items() if k.endswith("stations.csv")]
    check(len(set(csvs)) == 2, "each round's own data")
    check(("POST", "/api/login") not in Site.hits, "nothing that logs in or submits was clicked")
    leaks = [r for r in Api.raw if TOKEN.encode() in r] + [k for k, v in Api.blobs.items() if TOKEN.encode() in v]
    for root, _, fs in os.walk(work):
        for f in fs:
            with open(os.path.join(root, f), "rb") as fh:
                if TOKEN.encode() in fh.read():
                    leaks.append(os.path.join(root, f))
    check(TOKEN not in out and TOKEN[:20] not in out, "the token is not in the output")
    check(not leaks, "the token is in no file and no uploaded content %s" % leaks[:3])
    check(len(glob.glob(os.path.join(work, "home_turnout_capture", "*", "manifest.json"))) == 2, "a local copy of both rounds")
    print("\n%s" % ("ALL PASSED" if not check.failed else "%d FAILED" % check.failed))
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
