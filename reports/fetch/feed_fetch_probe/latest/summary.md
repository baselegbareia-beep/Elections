# The feed's fetch through the CEC's WAF (2026-10-23 16:20 UTC)

- **the feed's fetch passes the WAF: yes**. all 12 requests to media26 answered past the WAF (path: browser; HTTP 404): a 404 is the CEC's own answer, the 2026 files are not up yet
- urllib (the feed's first try): challenged on 1 of 1 requests to media26 (HTTP 202, x-amzn-waf-action: challenge); a challenged host is asked through the browser directly, urllib again after 600 s (live_fetch.WAF_RECHECK)
- the browser: Chrome 155.0.8059.39 at `/opt/google/chrome/chrome`, its own User-Agent `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/155.0.0.0 Safari/537.36`; started 6 times (once a round, as live.yml once a pass): 0.69–10.26 s, median 0.7 s; 12 requests through it, median 0.38 s each (the first of a round includes the start)
- control (media25, 2022): urllib, HTTP 200, 154331 bytes; data accepted: 154331 bytes

Requests of ours to the CEC's hosts: 14 (the plan: 12 to media26 through the feed's fetch, 60 s between rounds, plus the urllib tries, plus the control once).
Python 3.12.15; live_fetch: imported from pipeline/live_fetch.py; Chrome found: `/opt/google/chrome/chrome` 

pip: {"package": "numpy", "command": "-m pip install -q numpy", "rc": 0, "seconds": 3.5, "stderr": "[notice] A new release of pip is available: 26.2.1 -> 26.2.2\n[notice] To update, run: pip install --upgrade pip", "present": true}
pip: {"package": "playwright", "command": "-m pip install -q playwright", "rc": 0, "seconds": 1.9, "stderr": "[notice] A new release of pip is available: 26.2.1 -> 26.2.2\n[notice] To update, run: pip install --upgrade pip", "present": true}

| # | request | file | path (attempts) | HTTP | x-amzn-waf-action | x-cache | content-type | bytes | s | browser start s | the feed's outcome |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | round 1 | expb.csv (media26) | urllib 202 → browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 10.5 | 10.26 | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 2 | round 1 | expc.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.01 |  | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 3 | round 2 | expb.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.83 | 0.71 | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 4 | round 2 | expc.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.01 |  | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 5 | round 3 | expb.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.75 | 0.69 | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 6 | round 3 | expc.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.01 |  | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 7 | round 4 | expb.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.8 | 0.7 | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 8 | round 4 | expc.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.01 |  | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 9 | round 5 | expb.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.81 | 0.71 | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 10 | round 5 | expc.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.01 |  | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 11 | round 6 | expb.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.75 | 0.69 | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 12 | round 6 | expc.csv (media26) | browser 404 | 404 | - | Error from cloudfront | text/html | 1376 | 0.01 |  | HTTPError: HTTP Error 404: Not Found (through the browser) |
| 13 | control | expc.csv (media25) | urllib 200 | 200 | - | - | application/octet-stream | 154331 | 3.56 |  | data accepted: 154331 bytes |

First bytes of each distinct answer:

- HTTP 404 through browser: `<!DOCTYPE html> <html dir="rtl" lang="he-IL" class="no-js"> <head> <meta charset="UTF-8"> <meta name="viewport" content="width=device-width" />`
- HTTP 200 through urllib: `﻿סמל ועדה,שם ישוב,סמל ישוב,בזב,מצביעים,פסולים,כשרים,אמת,אצ,ב,ג,ד,ום,ז,זך,זנ,זץ,ט,י,יז,ינ,יץ,`

summary.json holds every record. Nothing was published.
