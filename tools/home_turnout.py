#!/usr/bin/env python3
"""Election day, from a computer in Israel: record what the CEC's turnout map loads and upload it to GitHub.

The CEC's turnout map (https://mapvotes.bechirot.gov.il; also elections.govmap.gov.il) does not load from GitHub's runners, so its per-station turnout can
only be read from a computer in Israel. This script runs there until 22:15 Israel time. Every 10 minutes (and once at
start) it opens the map in the computer's own Google Chrome, headless (Chrome's own User-Agent, no stealth: what any
visitor's browser does), waits for the network to settle and 25 s more, clicks a visible turnout tab or layer if there
is one (never anything that submits or logs in), and records every answer the page receives: address, method, HTTP
status, type and size, keeping the JSON/CSV/XML/GeoJSON/protobuf answers (20 MB each at most) and the app's own
scripts (each version once). Each round goes to the branch home-capture of baselegbareia-beep/Elections as one commit
(capture/<YYYYMMDD-HHMM>/manifest.json and the files) through GitHub's REST API, and a copy stays in
./home_turnout_capture/. It never writes to main or to any other branch.

    python3 home_turnout.py            # Windows: python home_turnout.py      (docs/HOME_TURNOUT.md)

Needs Python 3.9+; installs playwright (pip --user) on its first run. The GitHub token (fine-grained, this repository
only, Contents: Read and write) is asked once and kept in memory only: never written to disk, never printed.

For tests (tools/test_home_turnout.py): HOME_TURNOUT_API (GitHub API base), HOME_TURNOUT_URL (the page),
HOME_TURNOUT_CHROME (a Chrome/Chromium executable, used when Google Chrome is not installed), HOME_TURNOUT_INTERVAL
and HOME_TURNOUT_SETTLE (seconds), HOME_TURNOUT_ROUNDS (stop after N rounds), HOME_TURNOUT_STOP (HH:MM Israel time,
or "off"), HOME_TURNOUT_OUT (the local copy's folder).
"""
import sys

if sys.version_info < (3, 9):
    sys.stderr.write("Python 3.9 or newer is needed: https://www.python.org/downloads/\n"
                     "צריך Python 3.9 ומעלה\n")
    sys.exit(1)

import base64  # noqa: E402
import getpass  # noqa: E402
import hashlib  # noqa: E402
import http.client  # noqa: E402
import importlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import site  # noqa: E402
import ssl  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402
import warnings  # noqa: E402
import zipfile  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

VERSION = "2026-10-27.2"
REPO = "baselegbareia-beep/Elections"
BRANCH = "home-capture"            # the only branch this script ever writes to
BASE = "main"                      # read once, to start home-capture from it when it does not exist yet
assert BRANCH not in ("main", "master", BASE)

API = (os.environ.get("HOME_TURNOUT_API") or "https://api.github.com").rstrip("/")
PAGE = os.environ.get("HOME_TURNOUT_URL") or "https://mapvotes.bechirot.gov.il/?c=215846.52,595399.34&z=2"
INTERVAL = float(os.environ.get("HOME_TURNOUT_INTERVAL") or 600)
SETTLE = float(os.environ.get("HOME_TURNOUT_SETTLE") or 25)
MAX_ROUNDS = int(os.environ.get("HOME_TURNOUT_ROUNDS") or 0)
STOP = os.environ.get("HOME_TURNOUT_STOP") or "22:15"
CHROME_PATH = os.environ.get("HOME_TURNOUT_CHROME") or ""
OUT = os.environ.get("HOME_TURNOUT_OUT") or os.path.join(os.getcwd(), "home_turnout_capture")

MAX_BODY = 20 * 1024 * 1024        # a data answer larger than this is listed, not kept
MAX_BLOBS = 60                     # new files per round; more go into extra.zip (GitHub limits content requests)
MAX_PENDING = 300 * 1024 * 1024    # rounds not uploaded yet, kept in memory for the next round
UA = "home-turnout/" + VERSION

DATA_TYPE = re.compile(r"json|csv|xml|protobuf|mapbox-vector-tile|geo\+json|ndjson", re.I)
DATA_LOOSE = re.compile(r"text/plain|octet-stream", re.I)     # data when the app fetched it (xhr/fetch)
DATA_EXT = re.compile(r"\.(json|geojson|topojson|csv|xml|pbf|pb|proto|mvt)(\?|$)", re.I)
NOT_DATA = re.compile(r"html|javascript|css|image/|font/|video/|audio/|event-stream", re.I)
SKIP_HOSTS = re.compile(r"google-analytics|googletagmanager|doubleclick|googlesyndication|clarity\.ms|hotjar|"
                        r"facebook|sentry|newrelic|nr-data|onetrust|cookielaw", re.I)
APP_HOST = re.compile(r"(^|\.)govmap\.gov\.il$|(^|\.)bechirot\.gov\.il$|^" + re.escape(urllib.parse.urlsplit(PAGE).hostname or "-") + "$", re.I)

_SECRETS = []                      # the token, to blank out of anything printed (defence in depth)


# ----------------------------------------------------------------------------------------------------- output, time

def say(msg):
    msg = str(msg)
    for s in _SECRETS:
        msg = msg.replace(s, "***")
    print("[" + israel_now().strftime("%H:%M:%S") + "] " + msg, flush=True)


def israel_now(now=None, zoneinfo_ok=True):
    """Israel's wall clock, with or without a time-zone database (Windows has none by default)."""
    now = now or datetime.now(timezone.utc)
    if zoneinfo_ok:
        try:
            from zoneinfo import ZoneInfo
            return now.astimezone(ZoneInfo("Asia/Jerusalem"))
        except Exception:  # noqa: BLE001 - no tz database: Israel's rule below
            pass

    def last_sunday(month):
        d = datetime(now.year, month, 31, tzinfo=timezone.utc)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    start = last_sunday(3) - timedelta(days=2)        # Friday before the last Sunday of March, 02:00 IST = 00:00 UTC
    end = last_sunday(10) - timedelta(hours=1)        # last Sunday of October, 02:00 IDT = Saturday 23:00 UTC
    return now.astimezone(timezone(timedelta(hours=3 if start <= now < end else 2)))


def stop_time():
    if STOP.lower() == "off":
        return None
    h, m = (int(x) for x in STOP.split(":"))
    now = israel_now()
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def keep_awake():
    """Windows: no sleep while this runs (macOS: run it under caffeinate, docs/HOME_TURNOUT.md)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------------------------------------------- setup

def run_shown(cmd):
    """Run a command, showing its output as it comes (pip's and playwright's progress)."""
    lines = []
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    except OSError as err:
        return 1, str(err)
    for line in p.stdout:
        lines.append(line)
        line = line.rstrip()
        if line:
            print("    " + line[:200], flush=True)
    return p.wait(), "".join(lines)


def _have_playwright():
    importlib.invalidate_caches()
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def ensure_playwright():
    if _have_playwright():
        return True
    say("מתקין את playwright (רכיב ששולט בדפדפן). רק בהפעלה הראשונה, כדקה–שתיים...")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"] + ([] if in_venv else ["--user"]) + ["playwright"]
    rc, out = run_shown(cmd)
    if rc != 0 and "No module named pip" in out:
        say("pip חסר: מתקין אותו...")
        run_shown([sys.executable, "-m", "ensurepip", "--upgrade"] + ([] if in_venv else ["--user"]))
        rc, out = run_shown(cmd)
    if rc != 0 and "externally-managed" in out:
        rc, out = run_shown(cmd + ["--break-system-packages"])
    try:
        user_site = site.getusersitepackages()
        if os.path.isdir(user_site) and user_site not in sys.path:
            site.addsitedir(user_site)
    except Exception:  # noqa: BLE001
        pass
    if _have_playwright():
        say("playwright הותקן.")
        return True
    say("ERROR | ההתקנה של playwright נכשלה. אפשר לנסות ידנית:  " + os.path.basename(sys.executable) + " -m pip install --user playwright")
    return False


def launch_browser(pw):
    """The installed Google Chrome; else the executable in HOME_TURNOUT_CHROME, Edge (Windows), or Chromium."""
    tries = [("Google Chrome", {"channel": "chrome"})]
    if CHROME_PATH:
        tries.append((CHROME_PATH, {"executable_path": CHROME_PATH}))
    if sys.platform == "win32":
        tries.append(("Microsoft Edge", {"channel": "msedge"}))
    tries.append(("Chromium", {}))
    for name, kw in tries:
        try:
            return pw.chromium.launch(headless=True, **kw), name
        except Exception:  # noqa: BLE001 - not installed: the next one
            continue
    say("Google Chrome לא נמצא במחשב. מוריד דפדפן Chromium (כ-150MB, פעם אחת בלבד)...")
    rc, _ = run_shown([sys.executable, "-m", "playwright", "install", "chromium"])
    if rc != 0:
        raise RuntimeError("ההורדה של Chromium נכשלה. התקינו Google Chrome (google.com/chrome) והפעילו שוב.")
    return pw.chromium.launch(headless=True), "Chromium"


# ------------------------------------------------------------------------------------------------------- GitHub

class ApiError(Exception):
    def __init__(self, msg, fatal=False):
        Exception.__init__(self, msg)
        self.fatal = fatal


def git_blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class GitHub:
    """GitHub's REST API with the token in memory. Writes only blobs, trees, commits and refs/heads/home-capture."""

    def __init__(self, token):
        self._token = token
        self._ctx = None
        self.known = set()                 # blob SHAs already in the repository (uploaded by this run)

    def _guard(self, method, path, body):
        if path != "/repos/" + REPO and not path.startswith("/repos/" + REPO + "/"):
            raise ApiError("internal: path outside the repository: " + path, fatal=True)
        if method == "GET":
            return
        rest = path[len("/repos/" + REPO):]
        ok = (method == "POST" and rest in ("/git/blobs", "/git/trees", "/git/commits")) or \
             (method == "POST" and rest == "/git/refs" and body.get("ref") == "refs/heads/" + BRANCH) or \
             (method == "PATCH" and rest == "/git/refs/heads/" + BRANCH)
        if not ok:
            raise ApiError("internal: refused to write " + method + " " + path, fatal=True)

    def call(self, method, path, body=None, timeout=120):
        self._guard(method, path, body)
        data = json.dumps(body).encode() if body is not None else None
        for attempt in (1, 2):
            req = urllib.request.Request(API + path, data=data, method=method, headers={
                "Authorization": "Bearer " + self._token, "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": UA,
                **({"Content-Type": "application/json"} if data is not None else {})})
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=self._ctx) as r:
                    raw = r.read()
                    j = json.loads(raw) if raw.strip() else None
                    if j is not None and not isinstance(j, dict):
                        raise ValueError("not a JSON object")
                    return r.status, j
            except urllib.error.HTTPError as e:
                try:
                    raw = e.read() or b""
                except (http.client.HTTPException, OSError):
                    raw = b""
                try:
                    j = json.loads(raw)
                except ValueError:
                    j = None
                if not isinstance(j, dict):
                    j = {"message": raw[:200].decode("utf-8", "replace")}
                return e.code, j
            except urllib.error.URLError as e:
                if attempt == 1 and isinstance(e.reason, ssl.SSLError) and self._ctx is None and self._use_certifi():
                    continue                       # macOS python.org without its certificates: certifi's bundle
                raise
            except (http.client.HTTPException, ValueError) as e:
                # a reply cut short (IncompleteRead, BadStatusLine...) or not GitHub's (a proxy's or Wi-Fi login page):
                # the same as no connection, so every caller retries it as one
                raise urllib.error.URLError("broken reply from GitHub (%s)" % e.__class__.__name__) from None
        raise urllib.error.URLError("unreachable")

    def _use_certifi(self):
        for mod in ("certifi", "pip._vendor.certifi"):
            try:
                c = importlib.import_module(mod)
                self._ctx = ssl.create_default_context(cafile=c.where())
                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def check(self):
        st, j = self.call("GET", "/repos/" + REPO)
        if st == 200:
            return
        if st == 401:
            raise ApiError("הטוקן שגוי או שפג תוקפו (GitHub ענה 401). העתיקו אותו שוב, כולו, מ-GitHub.")
        if st in (403, 404):
            raise ApiError("הטוקן לא נותן גישה למאגר " + REPO + " (GitHub ענה " + str(st) + "). ביצירת הטוקן: "
                           "Only select repositories → Elections, ו-Contents: Read and write.")
        raise ApiError("GitHub ענה " + str(st) + ": " + str((j or {}).get("message", ""))[:150])

    def ensure_branch(self):
        """The head of home-capture; created from main's head when it does not exist."""
        st, j = self.call("GET", "/repos/" + REPO + "/git/ref/heads/" + BRANCH)
        if st == 200:
            return j["object"]["sha"]
        if st != 404:
            raise ApiError("GitHub ענה " + str(st) + " על הענף " + BRANCH + ": " + str((j or {}).get("message", ""))[:150])
        st, j = self.call("GET", "/repos/" + REPO + "/git/ref/heads/" + BASE)
        if st != 200:
            raise ApiError("לא הצלחתי לקרוא את " + BASE + " (GitHub ענה " + str(st) + ")")
        st, k = self.call("POST", "/repos/" + REPO + "/git/refs", {"ref": "refs/heads/" + BRANCH, "sha": j["object"]["sha"]})
        if st == 201:
            say("נוצר הענף " + BRANCH + " במאגר.")
            return j["object"]["sha"]
        if st == 422:                          # created meanwhile
            st, j = self.call("GET", "/repos/" + REPO + "/git/ref/heads/" + BRANCH)
            if st == 200:
                return j["object"]["sha"]
        if st in (403, 404):
            raise ApiError("לטוקן אין הרשאת כתיבה (GitHub ענה " + str(st) + "). צרו טוקן עם Contents: Read and write.", fatal=True)
        raise ApiError("יצירת הענף " + BRANCH + " נכשלה (GitHub ענה " + str(st) + ")")

    def upload(self, rounds):
        """One commit on home-capture with every round's files under capture/<stamp>/. Returns (sha, files, new bytes)."""
        for attempt in (1, 2):
            head = self.ensure_branch()
            st, c = self.call("GET", "/repos/" + REPO + "/git/commits/" + head)
            if st != 200:
                raise ApiError("GitHub ענה " + str(st) + " על הקומיט האחרון בענף")
            entries, new_bytes = [], 0
            for rd in rounds:
                for path, data in sorted(rd["files"].items()):
                    sha = git_blob_sha(data)
                    if sha not in self.known:
                        st, b = self.call("POST", "/repos/" + REPO + "/git/blobs",
                                          {"content": base64.b64encode(data).decode(), "encoding": "base64"}, timeout=600)
                        if st != 201:
                            raise ApiError(self._why(st, b, "קובץ"))
                        sha = b["sha"]
                        self.known.add(sha)
                        new_bytes += len(data)
                    entries.append({"path": "capture/" + rd["stamp"] + "/" + path, "mode": "100644", "type": "blob", "sha": sha})
            st, t = self.call("POST", "/repos/" + REPO + "/git/trees", {"base_tree": c["tree"]["sha"], "tree": entries})
            if st != 201:
                raise ApiError(self._why(st, t, "עץ"))
            msg = "home capture " + ", ".join(r["stamp"] + " (round " + str(r["round"]) + ", " + str(r["data"]) + " data answers)"
                                              for r in rounds)
            st, k = self.call("POST", "/repos/" + REPO + "/git/commits", {"message": msg, "tree": t["sha"], "parents": [head]})
            if st != 201:
                raise ApiError(self._why(st, k, "קומיט"))
            st, r = self.call("PATCH", "/repos/" + REPO + "/git/refs/heads/" + BRANCH, {"sha": k["sha"], "force": False})
            if st == 200:
                return k["sha"], len(entries), new_bytes
            if st != 422 or attempt == 2:      # 422: the branch moved meanwhile: once more on its new head
                raise ApiError(self._why(st, r, "עדכון הענף"))
        raise ApiError("upload failed")

    @staticmethod
    def _why(st, j, what):
        m = str((j or {}).get("message", ""))[:150]
        if st in (403, 429) and "rate" in m.lower():
            return "GitHub מגביל קצב (" + what + "): ננסה שוב בסבב הבא"
        if st in (401, 403, 404):
            return "GitHub סירב (" + what + ", " + str(st) + "): " + m + " — האם לטוקן יש Contents: Read and write?"
        return "GitHub ענה " + str(st) + " (" + what + "): " + m


def ask_token():
    warnings.simplefilter("ignore", getpass.GetPassWarning)
    print()
    print("נדרש טוקן של GitHub (Fine-grained token, רק למאגר Elections, Contents: Read and write).")
    print("הוא נשמר בזיכרון בלבד: לא נכתב לקובץ ולא מוצג. בהדבקה לא יופיעו תווים, זה תקין.")
    for _ in range(3):
        try:
            token = getpass.getpass("הדביקו את הטוקן ולחצו Enter: ").strip()
        except EOFError:
            token = ""
        if not token:
            say("לא הודבק טוקן.")
            continue
        _SECRETS.append(token)
        gh = GitHub(token)
        try:
            gh.check()
            say("TOKEN OK | הטוקן תקין: יש גישה למאגר " + REPO + ".")
            return gh
        except ApiError as err:
            say("TOKEN REFUSED | " + str(err))
        except Exception as err:  # noqa: BLE001 - no connection, a cut reply, a proxy's page: ask again
            say("NO CONNECTION | אין חיבור תקין ל-GitHub (" + str(err)[:80] + "). בדקו את החיבור לאינטרנט ונסו שוב.")
    return None


# ------------------------------------------------------------------------------------------------------- capture

FIND_CONTROLS = r"""() => {
  const KEY = /אחוז(?:י)?\s*(?:ה)?הצבעה|שיעור\s*(?:ה)?הצבעה|השתתפות|turnout/i;
  const BAD = /התחבר|התנתק|כניסה|הרשמ|הירשמ|שלח|סיסמ|log\s*-?in|log\s*-?out|sign\s*-?in|sign\s*-?up|submit|password|register/i;
  const CLICK = 'a,button,[role=tab],[role=button],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],' +
                '[role=checkbox],[role=switch],[role=option],[role=treeitem],label,li,summary,' +
                'input[type=checkbox],input[type=radio],[onclick]';
  const out = [], seen = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (out.length >= 4) break;
    const own = [el.getAttribute('aria-label'), el.getAttribute('title'),
                 el.childElementCount === 0 ? el.textContent : ''].filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
    if (!own || own.length > 60 || !KEY.test(own) || BAD.test(own)) continue;
    let t = el.closest(CLICK) || el;
    if ((t.innerText || '').length > 200) t = el;
    if (seen.has(t)) continue;
    const r = t.getBoundingClientRect(), st = getComputedStyle(t);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none') continue;
    const tag = t.tagName.toLowerCase(), type = (t.getAttribute('type') || '').toLowerCase();
    if (type === 'submit' || type === 'password' || type === 'image' ||
        (tag === 'input' && type !== 'checkbox' && type !== 'radio')) continue;
    const form = t.closest('form');
    if (form && ((tag === 'button' && type !== 'button') || form.querySelector('input[type=password]'))) continue;
    if (BAD.test(t.innerText || '')) continue;
    if (tag === 'a') {
      const h = t.getAttribute('href') || '';
      if (h && !h.startsWith('#') && !h.startsWith('javascript:')) {
        try { if (new URL(h, location.href).origin !== location.origin) continue; } catch (e) { continue; }
      }
    }
    seen.add(t);
    t.setAttribute('data-home-turnout', String(out.length));
    out.push({i: out.length, text: own.slice(0, 60), tag: tag});
  }
  return out;
}"""


def slug(url, n, ctype):
    u = urllib.parse.urlsplit(url)
    path = u.path or "/"
    ext = os.path.splitext(path)[1].lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", ext or ""):
        ext = next((e for k, e in (("geo+json", ".geojson"), ("json", ".json"), ("csv", ".csv"), ("xml", ".xml"),
                                   ("protobuf", ".pbf"), ("vector-tile", ".pbf"), ("javascript", ".js"),
                                   ("html", ".html"), ("text/plain", ".txt")) if k in ctype.lower()), ".bin")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (u.hostname or "") + os.path.splitext(path)[0] + ("_" + u.query if u.query else ""))
    return "%03d-%s%s" % (n, stem.strip("_")[-80:], ext)


def capture_round(browser, n, stamp, seen_code):
    """Open the map once; returns the round: its files (path -> bytes) and counts."""
    rows, files, notes, clicked, ws_frames = [], {}, [], [], {}
    ctx = browser.new_context(locale="he-IL", timezone_id="Asia/Jerusalem", viewport={"width": 1440, "height": 900},
                              service_workers="block")

    def on_response(r):
        try:
            req = r.request
            host = urllib.parse.urlsplit(r.url).hostname or ""
            headers = r.headers or {}
            ctype = headers.get("content-type", "")
            kind = req.resource_type
            row = {"n": len(rows) + 1, "url": r.url, "method": req.method, "status": r.status, "type": ctype[:80],
                   "kind": kind, "bytes": int(headers["content-length"]) if headers.get("content-length", "").isdigit() else None}
            rows.append(row)
            if req.method == "POST" and kind in ("xhr", "fetch"):
                row["post"] = (req.post_data or "")[:2000]
            for h in ("last-modified", "etag"):
                if headers.get(h):
                    row[h] = headers[h][:80]
            if SKIP_HOSTS.search(host) or r.status in (204, 301, 302, 303, 304, 307, 308):
                return
            is_data = (not NOT_DATA.search(ctype) or DATA_TYPE.search(ctype)) and (
                DATA_TYPE.search(ctype) or DATA_EXT.search(r.url) or
                (kind in ("xhr", "fetch") and (DATA_LOOSE.search(ctype) or not ctype)))
            is_code = APP_HOST.search(host) and (kind == "script" or kind == "document") and r.status == 200
            if not (is_data or is_code):
                return
            if row["bytes"] is not None and row["bytes"] > MAX_BODY:
                row["file"] = "not kept: larger than 20 MB"
                return
            body = r.body()
            row["bytes"] = len(body)
            row["sha256"] = hashlib.sha256(body).hexdigest()
            if not body or len(body) > MAX_BODY:
                row["file"] = None if not body else "not kept: larger than 20 MB"
                return
            if is_data:
                row["file"] = "data/" + slug(r.url, row["n"], ctype)
                row["first"] = body[:200].decode("utf-8", "replace")
            else:                                  # the app's code / page: each version once per run
                if row["sha256"] in seen_code:
                    row["file"] = "same as " + seen_code[row["sha256"]]
                    return
                row["file"] = "code/" + slug(r.url, row["n"], ctype)
                seen_code[row["sha256"]] = "capture/" + stamp + "/" + row["file"]
            files[row["file"]] = body
        except Exception as err:  # noqa: BLE001 - one bad answer never stops the round
            if rows:
                rows[-1]["error"] = (err.__class__.__name__ + ": " + str(err))[:200]

    def on_websocket(ws):
        frames = ws_frames.setdefault(ws.url, [])

        def keep(payload):
            if sum(len(f) for f in frames) < 5 * 1024 * 1024:
                frames.append(payload if isinstance(payload, str) else base64.b64encode(payload).decode())
        ws.on("framereceived", keep)

    ctx.on("response", on_response)
    page = ctx.new_page()
    page.on("websocket", on_websocket)
    title, text, shot = "", "", None
    try:
        resp = page.goto(PAGE, wait_until="domcontentloaded", timeout=60000)
        notes.append("opened %s: HTTP %s" % (PAGE, resp.status if resp else "-"))
        try:
            page.wait_for_load_state("networkidle", timeout=45000)
        except Exception:  # noqa: BLE001 - a map that keeps polling never idles
            notes.append("no network idle in 45 s")
        page.wait_for_timeout(SETTLE * 1000)
        try:
            controls = page.evaluate(FIND_CONTROLS) or []
        except Exception as err:  # noqa: BLE001
            controls = []
            notes.append("looking for a turnout control failed: " + str(err)[:150])
        for c in controls:
            before = len(rows)
            try:
                page.locator('[data-home-turnout="%d"]' % c["i"]).first.click(timeout=5000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(min(SETTLE, 8) * 1000)
                clicked.append({"text": c["text"], "tag": c["tag"], "new_answers": len(rows) - before})
            except Exception as err:  # noqa: BLE001
                clicked.append({"text": c["text"], "tag": c["tag"], "error": str(err).split("\n")[0][:150]})
        title = page.title()
        text = page.inner_text("body")[:6000]
        shot = page.screenshot(type="jpeg", quality=60)
    except Exception as err:  # noqa: BLE001 - the round is still recorded
        notes.append("the page failed: " + err.__class__.__name__ + ": " + str(err).split("\n")[0][:300])
    finally:
        try:
            ctx.close()
        except Exception:  # noqa: BLE001
            pass
    if shot:
        files["screenshot.jpg"] = shot
    for k, (url, frames) in enumerate(ws_frames.items()):
        if frames:
            files["data/websocket-%d.jsonl" % (k + 1)] = "\n".join(json.dumps({"url": url, "frame": f}, ensure_ascii=False)
                                                                   for f in frames).encode("utf-8")
    data_files = [p for p in files if p.startswith("data/")]
    manifest = {"script": VERSION, "round": n, "stamp": stamp, "page": PAGE, "browser": browser.version,
                "israel_time": israel_now().strftime("%Y-%m-%d %H:%M:%S"),
                "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "title": title, "visible_text": text, "clicked": clicked, "notes": notes,
                "answers": len(rows), "data_answers": len(data_files), "responses": rows}
    return {"round": n, "stamp": stamp, "files": files, "manifest": manifest, "data": len(data_files),
            "answers": len(rows), "clicked": clicked, "notes": notes, "title": title, "text_len": len(text)}


def pack(rd, known):
    """Files for the commit: up to MAX_BLOBS new ones as they are, the rest in extra.zip; manifest.json last."""
    files, extra, new = {}, {}, set()
    order = sorted(rd["files"], key=lambda p: (not re.search(r"\.(json|geojson|csv|xml|txt|jsonl)$", p),
                                               not p.startswith("data/"), p))
    for p in order:
        b = rd["files"][p]
        sha = git_blob_sha(b)
        if sha in known or sha in new:                 # already in the repository / in this round: no new request
            files[p] = b
        elif len(new) < MAX_BLOBS:
            new.add(sha)
            files[p] = b
        else:
            extra[p] = b
    if extra:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p, b in extra.items():
                z.writestr(p, b)
        files["extra.zip"] = buf.getvalue()
        rd["manifest"]["in_extra_zip"] = sorted(extra)
    files["manifest.json"] = json.dumps(rd["manifest"], ensure_ascii=False, indent=1).encode("utf-8")
    return files


def save_local(rd):
    try:
        base = os.path.join(OUT, rd["stamp"])
        for p, b in list(rd["files"].items()) + [("manifest.json", json.dumps(rd["manifest"], ensure_ascii=False, indent=1).encode())]:
            dest = os.path.join(base, *p.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(b)
    except OSError as err:
        say("לא נשמר עותק מקומי: " + str(err)[:150])


# ------------------------------------------------------------------------------------------------------- main

def human(n):
    if not n:
        return "0"
    return "%.1fMB" % (n / 1048576) if n >= 1048576 else "%dKB" % max(1, n // 1024)


def run():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    print("=" * 64)
    print("איסוף אחוזי ההצבעה ממפת ועדת הבחירות (גרסה %s)" % VERSION)
    print("רץ עד 22:15. לעצירה: Ctrl+C.")
    print("=" * 64)
    keep_awake()
    if not ensure_playwright():
        return 1
    from playwright.sync_api import sync_playwright
    stop = stop_time()
    if stop and israel_now() >= stop:
        say("AFTER %s | השעה כבר אחרי %s (שעון ישראל): אין מה לאסוף." % (STOP, STOP))
        return 0
    with sync_playwright() as pw:
        try:
            browser, bname = launch_browser(pw)
        except Exception as err:  # noqa: BLE001
            say("ERROR | הדפדפן לא נפתח: " + str(err).split("\n")[0][:300])
            return 1
        say("BROWSER OK | הדפדפן מוכן: %s %s" % (bname if bname != CHROME_PATH else "Chrome", browser.version))
        gh = ask_token()
        if gh is None:
            say("NO TOKEN | לא התקבל טוקן תקין. סוגר. אפשר להפעיל שוב באותה פקודה.")
            return 1
        try:
            gh.ensure_branch()
        except ApiError as err:
            say(("ERROR | " if err.fatal else "") + str(err))
            if err.fatal:
                return 1
        except Exception as err:  # noqa: BLE001 - a dropped connection, a cut reply: the first round tries again
            say("NO CONNECTION | אין חיבור תקין ל-GitHub כרגע (%s): ננסה שוב בסבב הראשון." % str(err)[:80])
        pending, seen_code, n, last_base = [], {}, 0, ""
        while True:
            now = israel_now()
            if stop and now >= stop:
                say("STOP %s | השעה %s: מסיים." % (STOP, STOP))
                break
            n += 1
            t0 = time.monotonic()
            base = now.strftime("%Y%m%d-%H%M")
            stamp = base if base != last_base else "%s-r%d" % (base, n)     # two rounds in one minute (tests)
            last_base = base
            say("round %d: opening the map | סבב %d: פותח את המפה..." % (n, n))
            try:
                if not browser.is_connected():
                    browser, bname = launch_browser(pw)
                rd = capture_round(browser, n, stamp, seen_code)
            except Exception as err:  # noqa: BLE001 - never stop the loop
                say("round %d: FAILED | סבב %d נכשל: %s" % (n, n, str(err).split("\n")[0][:200]))
                rd = None
            if rd:
                try:
                    click = "; נלחץ: " + ", ".join("'%s'" % c["text"] for c in rd["clicked"]) if rd["clicked"] else ""
                    say("round %d: %d answers, %d data | סבב %d: %d תשובות מהאתר, מתוכן %d תשובות נתונים "
                        "(JSON/CSV/XML/GeoJSON/protobuf)%s." % (n, rd["answers"], rd["data"], n, rd["answers"], rd["data"], click))
                    if not rd["text_len"] and not rd["data"]:
                        say("EMPTY | המפה לא הציגה כלום בסבב הזה. " + "; ".join(rd["notes"])[:200])
                    save_local(rd)
                    rd["files"] = pack(rd, gh.known)
                    pending.append(rd)
                    while sum(sum(len(b) for b in r["files"].values()) for r in pending) > MAX_PENDING and len(pending) > 1:
                        pending.pop(0)
                except Exception as err:  # noqa: BLE001 - never stop the loop
                    say("round %d: FAILED | סבב %d לא נשמר: %s" % (n, n, str(err).split("\n")[0][:200]))
            if pending:
                try:
                    sha, nfiles, nbytes = gh.upload(pending)
                    say("UPLOADED %s | הועלה ל-GitHub (ענף %s): %s, %d קבצים, %s חדשים, קומיט %s."
                        % (sha[:7], BRANCH, ", ".join("capture/" + r["stamp"] for r in pending), nfiles, human(nbytes), sha[:7]))
                    pending = []
                except ApiError as err:
                    say("NOT UPLOADED | לא הועלה: %s. נשמר במחשב (%s), ננסה שוב בסבב הבא." % (err, OUT))
                    if err.fatal:
                        return 1
                except Exception as err:  # noqa: BLE001 - a dropped connection, a cut or garbled reply: next round
                    say("NOT UPLOADED | לא הועלה (אין חיבור תקין ל-GitHub: %s). נשמר במחשב, ננסה שוב בסבב הבא."
                        % str(err)[:80])
            if MAX_ROUNDS and n >= MAX_ROUNDS:
                break
            nxt = t0 + INTERVAL
            at = (israel_now() + timedelta(seconds=max(0, nxt - time.monotonic()))).strftime("%H:%M")
            say("next round %s | הסבב הבא בעוד %d דקות (%s)." % (at, round(INTERVAL / 60), at))
            while time.monotonic() < nxt and not (stop and israel_now() >= stop):
                time.sleep(min(5.0, max(0.1, nxt - time.monotonic())))
        try:
            browser.close()
        except Exception:  # noqa: BLE001
            pass
    if pending:
        say("NOT UPLOADED | נשארו סבבים שלא הועלו; הם שמורים במחשב בתיקייה " + OUT)
    say("DONE | הסתיים. תודה!")
    return 0


def main():
    try:
        return run()
    except Exception:  # noqa: BLE001 - last resort: a readable message, then the details (the token blanked)
        say("ERROR | תקלה לא צפויה, הסקריפט נעצר. אפשר להפעיל שוב באותה פקודה.\n" + traceback.format_exc()[-2000:])
        return 1
    except KeyboardInterrupt:
        print()
        say("STOPPED | נעצר (Ctrl+C). מה שהועלה נשאר בענף %s, ועותק נמצא בתיקייה %s." % (BRANCH, OUT))
        sys.stdout.flush()
        os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
