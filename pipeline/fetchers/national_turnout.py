"""The CEC's hourly national turnout as the news reports it (election day): headlines and flashes that quote it.

The CEC gives the national turnout of each even hour to the media about 50 minutes later, and its own map
(mapvotes) and gov.il files can follow much later. This fetcher reads news feeds (Google News searches, which
gather every outlet's headline, and outlets' own breaking-news feeds), keeps today's items that state the
national turnout ("שיעור ההצבעה עד השעה 14:00 עומד על 44.9%"), and lists each figure with the outlets that state
it and when each first did. It decides nothing: whoever applies a figure asks for two outlets that agree
(tools in docs/ELECTION_DAY.md), and an official figure (the map, a CEC file) wins over a reported one.

    python3 pipeline/fetchers/national_turnout.py --out DIR [--deadline S]

Fetch contract: pipeline/fetchers/__init__.py (standard library only).
"""
import argparse
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "Kalpi26-dashboard/1.0 (+https://github.com/baselegbareia-beep/Elections)"
GNEWS = "https://news.google.com/rss/search?hl=iw&gl=IL&ceid=IL:he&q="
FEEDS = [
    ("Google News: שיעור ההצבעה", GNEWS + urllib.parse.quote('"שיעור ההצבעה" when:1d')),
    ("Google News: אחוז ההצבעה", GNEWS + urllib.parse.quote('"אחוז ההצבעה" when:1d')),
    ("Google News: ועדת הבחירות הצבעה", GNEWS + urllib.parse.quote('ועדת הבחירות הצבעה when:1d')),
    ("ynet מבזקים", "https://www.ynet.co.il/Integration/StoryRss1854.xml"),
    ("ynet חדשות", "https://www.ynet.co.il/Integration/StoryRss2.xml"),
    ("מעריב מבזקים", "https://www.maariv.co.il/Rss/RssFeedsMivzakiChadashot"),
    ("N12", "https://rcs.mako.co.il/rss/news-israel.xml"),
    ("ישראל היום", "https://www.israelhayom.co.il/rss.xml"),
    ("סרוגים", "https://www.srugim.co.il/feed"),
    ("JDN", "https://www.jdn.co.il/feed/"),
    ("גלובס", "https://www.globes.co.il/webservice/rss/rssfeeder.asmx/FeederNode?iID=2"),
]
DEADLINE, TIMEOUT, MAX_AGE_H = 180, 20, 18
IL = dt.timezone(dt.timedelta(hours=2))          # Israel is on winter time from the last Sunday of October

KEY = re.compile(r"הצבעה|הצביעו|מצביעים")
# a sector's or a place's turnout is not the national one
OTHER = re.compile(r'צה"ל|צה״ל|חייל|בתי ה?סוהר|אסיר|ערבי|בדואי|חרדי|דרוזי|מגזר|ביישוב|ישובי|יישובי|בעיר|בערים|'
                   r"בירושלים|בתל אביב|בחיפה|בבני ברק|במחוז|בקלפי ה|בחו\"ל|נציגויות|ספינות|בבית החולים|בבתי חולים")
HOUR = re.compile(r"(?<![\d:.])([012]?\d):00(?!\d)")
PCT = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d{1,2})?)\s*(?:%|אחוז)")
SPLIT = re.compile(r"(?<!\d)[.!?](?!\d)|\n|[|•;]")


def figures(text):
    """[(HH:00, percent)] that a text states as the national turnout: per sentence, one that names the turnout,
    no sector or place, an hour (07:00-22:00) and a percent; the first percent is the figure (a comparison follows
    it: 'עומד על 44.9%, לעומת 38.9% ב-2022')."""
    out = []
    for s in SPLIT.split(html.unescape(re.sub(r"<[^>]+>", " ", text or ""))):
        if not KEY.search(s) or OTHER.search(s):
            continue
        h, p = HOUR.search(s), PCT.search(s)
        if not h or not p:
            continue
        hour, pct = int(h.group(1)), float(p.group(1))
        if 7 <= hour <= 22 and 1 <= pct <= 95 and (f"{hour:02d}:00", pct) not in out:
            out.append((f"{hour:02d}:00", pct))
    return out


def items(body):
    """An RSS or Atom body -> [{title, text, published (UTC ISO), link, outlet}]."""
    root = ET.fromstring(body)
    out = []
    for it in root.iter():
        tag = it.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        get = {c.tag.rsplit("}", 1)[-1]: c for c in it}
        title = (get.get("title").text or "") if get.get("title") is not None else ""
        text = " ".join((get[k].text or "") for k in ("description", "summary", "content", "encoded") if k in get)
        when = None
        for k in ("pubDate", "published", "updated", "date"):
            if k in get and (get[k].text or "").strip():
                raw = get[k].text.strip()
                try:
                    when = email.utils.parsedate_to_datetime(raw)
                except (TypeError, ValueError):
                    try:
                        when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    except ValueError:
                        when = None
                if when is not None:
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=dt.timezone.utc)
                    break
        link = get.get("link")
        link = (link.text or link.get("href") or "") if link is not None else ""
        src = get.get("source")
        out.append({"title": title.strip(), "text": text.strip(), "link": link.strip(),
                    "published": when.astimezone(dt.timezone.utc).isoformat() if when else None,
                    "outlet": (src.text or "").strip() if src is not None else None})
    return out


def outlet_of(item, feed):
    """Google News titles end ' - <outlet>'; its <source> names the outlet too. Direct feeds are their outlet."""
    if item.get("outlet"):
        return item["outlet"]
    if feed.startswith("Google News"):
        m = re.search(r"\s[-–]\s([^-–]+)$", item["title"])
        return m.group(1).strip() if m else "?"
    return feed.split()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline", type=float, default=DEADLINE)
    a = ap.parse_args(argv)
    os.makedirs(os.path.join(a.out, "files"), exist_ok=True)
    t0, now = time.time(), dt.datetime.now(dt.timezone.utc)
    started = now.strftime("%Y-%m-%d %H:%M UTC")
    sources, found = [], []
    for i, (name, url) in enumerate(FEEDS):
        left = a.deadline - (time.time() - t0)
        entry = {"name": name, "url": url}
        sources.append(entry)
        if left <= 0:
            entry["error"] = "not asked: past the deadline"
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
            with urllib.request.urlopen(req, timeout=min(TIMEOUT, left)) as r:
                body = r.read(4_000_000)
                entry["http"] = r.status
            open(os.path.join(a.out, "files", f"{i:02d}.xml"), "wb").write(body)
            got = items(body)
        except Exception as e:  # noqa: BLE001 - a bad feed is recorded, never raised
            entry["http"] = getattr(e, "code", None)
            entry["error"] = f"{type(e).__name__}: {e}"[:300]
            continue
        entry["items"] = len(got)
        for it in got:
            when = dt.datetime.fromisoformat(it["published"]) if it["published"] else None
            if when is None or (now - when).total_seconds() > MAX_AGE_H * 3600:
                continue
            figs = figures(it["title"] + "\n" + it["text"])
            if figs:
                found.append({**it, "feed": name, "outlet": outlet_of(it, name), "figures": figs,
                              "published_il": when.astimezone(IL).strftime("%H:%M")})
    agg = {}                                      # hour -> percent -> outlet -> the earliest time it stated it
    for f in found:
        for hour, pct in f["figures"]:
            seen = agg.setdefault(hour, {}).setdefault(f"{pct:g}", {})
            if f["outlet"] not in seen or f["published"] < seen[f["outlet"]]["published"]:
                seen[f["outlet"]] = {"published": f["published"], "published_il": f["published_il"], "title": f["title"][:200]}
    summary = {"fetcher": "national_turnout", "started": started, "sources": sources, "figures": agg,
               "items": [{k: f[k] for k in ("feed", "outlet", "published", "published_il", "title", "link", "figures")} for f in found]}
    json.dump(summary, open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    md = [f"# National turnout as the news reports it ({started})", "", "| source | HTTP | items | error |", "|---|---|---|---|"]
    md += [f"| {s['name']} | {s.get('http')} | {s.get('items', '')} | {s.get('error', '')} |" for s in sources]
    md += ["", "## Figures (hour: percent - outlets, earliest Israel time)", ""]
    for hour in sorted(agg):
        for pct, outs in sorted(agg[hour].items(), key=lambda kv: -len(kv[1])):
            md.append(f"- {hour}: {pct}% - " + ", ".join(f"{o} {v['published_il']}" for o, v in sorted(outs.items(), key=lambda kv: kv[1]['published'])))
    open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(json.dumps({"sources": len(sources), "items": len(found), "hours": sorted(agg)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
