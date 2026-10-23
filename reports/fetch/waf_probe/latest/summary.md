# WAF probe: bechirot.gov.il (2026-10-23 14:40 UTC)

- **WAF challenge: yes**. x-amzn-waf-action: challenge on 8 of 10 answers from the CEC's 2026 hosts (202 with a challenge page (AwsWafIntegration, awswaf, challenge.js, gokuProps); 202 with an empty body)
- **a real browser passes: yes**. not challenged at all: www.bechirot.gov.il 404; media26.bechirot.gov.il 404; no aws-waf-token cookie
- **a browser token works for plain requests: unclear**. the browser brought no cookies
- Control: media25 (2022): answered HTTP 206 with data.

Requests of ours to the CEC's hosts: 14 (at most 25, 2 s apart per host). The feed's User-Agent: `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live`.

## 1. Plain requests (the feed's headers) and a browser's ordinary headers (urllib)

| # | headers | URL | HTTP | x-amzn-waf-action | x-cache | server | x-amz-cf-pop | content-type | length | set-cookie | body (start) | markers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | plain | https://www.bechirot.gov.il/ | 202 | challenge | Error from cloudfront | CloudFront | IAD55-P3 | text/html; charset=UTF-8 | 0 |  | (empty) |  |
| 2 | plain | https://media26.bechirot.gov.il/ | 202 | challenge | Error from cloudfront | CloudFront | IAD55-P10 | text/html; charset=UTF-8 | 0 |  | (empty) |  |
| 3 | plain | https://media26.bechirot.gov.il/files/expb.csv | 202 | challenge | Error from cloudfront | CloudFront | IAD55-P10 | text/html; charset=UTF-8 | 0 |  | (empty) |  |
| 4 | plain | https://votes26.bechirot.gov.il/ | 202 | challenge | Error from cloudfront | CloudFront | IAD89-P3 | text/html; charset=UTF-8 | 0 |  | (empty) |  |
| 5 | plain | https://media25.bechirot.gov.il/files/expc.csv | 206 | - |  |  |  | application/octet-stream | 201 | p_hosting, TS0101ef41, TS074b8af6027 | ﻿סמל ועדה,שם ישוב,סמל ישוב,בזב,מצביעים,פסולים,כשרים,אמת,אצ,ב,ג,ד,ום,ז,זך,זנ,זץ,ט |  |
| 6 | browser headers | https://www.bechirot.gov.il/ | 202 | challenge | Error from cloudfront | CloudFront | IAD55-P3 | text/html; charset=UTF-8 | 2015 |  | <!DOCTYPE html> <html lang="en"> <head> <meta charset="utf-8"> <meta name="viewp | challenge.js, awswaf, AwsWafIntegration, gokuProps, token |
| 7 | browser headers | https://media26.bechirot.gov.il/ | 202 | challenge | Error from cloudfront | CloudFront | IAD55-P10 | text/html; charset=UTF-8 | 2015 |  | <!DOCTYPE html> <html lang="en"> <head> <meta charset="utf-8"> <meta name="viewp | challenge.js, awswaf, AwsWafIntegration, gokuProps, token |
| 8 | browser headers | https://media26.bechirot.gov.il/files/expb.csv | 202 | challenge | Error from cloudfront | CloudFront | IAD55-P10 | text/html; charset=UTF-8 | 2015 |  | <!DOCTYPE html> <html lang="en"> <head> <meta charset="utf-8"> <meta name="viewp | challenge.js, awswaf, AwsWafIntegration, gokuProps, token |
| 9 | browser headers | https://votes26.bechirot.gov.il/ | 202 | challenge | Error from cloudfront | CloudFront | IAD89-P3 | text/html; charset=UTF-8 | 2015 |  | <!DOCTYPE html> <html lang="en"> <head> <meta charset="utf-8"> <meta name="viewp | challenge.js, awswaf, AwsWafIntegration, gokuProps, token |
| 10 | browser headers | https://media25.bechirot.gov.il/files/expc.csv | 206 | - |  |  |  | application/octet-stream | 201 | p_hosting, TS0101ef41, TS074b8af6027 | ﻿סמל ועדה,שם ישוב,סמל ישוב,בזב,מצביעים,פסולים,כשרים,אמת,אצ,ב,ג,ד,ום,ז,זך,זנ,זץ,ט |  |

## 2. A real browser

Chrome `/opt/google/chrome/chrome` 155.0.8059.39, playwright 1.64.1, headless, its own User-Agent `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/155.0.0.0 Safari/537.36` (navigator.webdriver True). 18 s.

pip: {"command": "python3 -m pip install -q playwright", "rc": 0, "seconds": 2, "user": false}

| page | navigations (HTTP, x-amzn-waf-action) | network idle | seconds | title | cookies after | visible text (start) |
|---|---|---|---|---|---|---|
| https://www.bechirot.gov.il/ | 404 | True | 2.8 | שגיאה |  | מצטערים, העמוד שחיפשת לא נמצא יתכן שהכתובת הוחלפה או הוזנה לא נכון (7) |
| https://media26.bechirot.gov.il/ | 404 | True | 1.9 | שגיאה |  | מצטערים, העמוד שחיפשת לא נמצא יתכן שהכתובת הוחלפה או הוזנה לא נכון (7) |

Cookies the browser holds (names only):

| name | domain | path | secure | httpOnly | sameSite | expires in |
|---|---|---|---|---|---|---|

The browser's requests by host: fonts.googleapis.com 2, fonts.gstatic.com 4, maintenance.gov.il 6, media26.bechirot.gov.il 1, www.bechirot.gov.il 1; images, fonts and media not fetched: 0.

In the same browser context (its cookies), `context.request.get`:

| file | HTTP | x-amzn-waf-action | x-cache | content-type | bytes | first bytes |
|---|---|---|---|---|---|---|
| https://media26.bechirot.gov.il/files/expb.csv | 404 | - | Error from cloudfront | text/html | 1376 | <!DOCTYPE html> <html dir="rtl" lang="he-IL" class="no-js"> <head> <meta charset="UTF-8"> <meta name="viewport" content="width=device-width" /> <meta name="view |
| https://media26.bechirot.gov.il/files/expc.csv | 404 | - | Error from cloudfront | text/html | 1376 | <!DOCTYPE html> <html dir="rtl" lang="he-IL" class="no-js"> <head> <meta charset="UTF-8"> <meta name="viewport" content="width=device-width" /> <meta name="view |

## 2b. The browser's cookies in plain requests (urllib GET of expb.csv)

Not asked: the browser brought no cookies


## Every answer's headers and first bytes

### 1.1 plain: https://www.bechirot.gov.il/ -> 202

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Cache-Control: no-cache

- Server: CloudFront
- Date: Fri, 23 Oct 2026 14:40:47 GMT
- Content-Length: 0
- Connection: close
- x-amzn-waf-action: challenge
- Cache-Control: no-store, max-age=0
- Content-Type: text/html; charset=UTF-8
- Access-Control-Allow-Origin: *
- Access-Control-Max-Age: 86400
- Access-Control-Allow-Methods: OPTIONS,GET,POST
- Access-Control-Expose-Headers: x-amzn-waf-action
- X-Cache: Error from cloudfront
- Via: 1.1 b64454e3c1123ac098282f1036154740.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD55-P3
- X-Amz-Cf-Id: _X7Chiu0E6jXdOIepIAGiKGkSvVn2ScfQ-tc_iFXkKnSm3ZIhzzMxQ==

### 1.2 plain: https://media26.bechirot.gov.il/ -> 202

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Cache-Control: no-cache

- Server: CloudFront
- Date: Fri, 23 Oct 2026 14:40:47 GMT
- Content-Length: 0
- Connection: close
- x-amzn-waf-action: challenge
- Cache-Control: no-store, max-age=0
- Content-Type: text/html; charset=UTF-8
- Access-Control-Allow-Origin: *
- Access-Control-Max-Age: 86400
- Access-Control-Allow-Methods: OPTIONS,GET,POST
- Access-Control-Expose-Headers: x-amzn-waf-action
- X-Cache: Error from cloudfront
- Via: 1.1 5ceb9cec7debee0553fef552eba62cc4.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD55-P10
- X-Amz-Cf-Id: q3Hlv0hGA4DnlkPvKsLCOQn8Ev6YpaltldjOrQ4c-PZYM59Kdk9Tbg==

### 1.3 plain: https://media26.bechirot.gov.il/files/expb.csv -> 202

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Cache-Control: no-cache

- Server: CloudFront
- Date: Fri, 23 Oct 2026 14:40:49 GMT
- Content-Length: 0
- Connection: close
- x-amzn-waf-action: challenge
- Cache-Control: no-store, max-age=0
- Content-Type: text/html; charset=UTF-8
- Access-Control-Allow-Origin: *
- Access-Control-Max-Age: 86400
- Access-Control-Allow-Methods: OPTIONS,GET,POST
- Access-Control-Expose-Headers: x-amzn-waf-action
- X-Cache: Error from cloudfront
- Via: 1.1 0145ea6cf3813022e500cf46dfa7f256.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD55-P10
- X-Amz-Cf-Id: HkqW_XM2a2_9zJqCcTRZfXayFwbT7Qvmi47j4AErXCoyQwruwM2X3w==

### 1.4 plain: https://votes26.bechirot.gov.il/ -> 202

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Cache-Control: no-cache

- Server: CloudFront
- Date: Fri, 23 Oct 2026 14:40:49 GMT
- Content-Length: 0
- Connection: close
- x-amzn-waf-action: challenge
- Cache-Control: no-store, max-age=0
- Content-Type: text/html; charset=UTF-8
- Access-Control-Allow-Origin: *
- Access-Control-Max-Age: 86400
- Access-Control-Allow-Methods: OPTIONS,GET,POST
- Access-Control-Expose-Headers: x-amzn-waf-action
- X-Cache: Error from cloudfront
- Via: 1.1 bdfa5ff45a012f4d008a55b929c33ce2.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD89-P3
- X-Amz-Cf-Id: WGGJCjREYpWrqkuAYGt7-eb94pz_l2bEedfaO-lrStyE3CFvFRt_Ow==

### 1.5 plain: https://media25.bechirot.gov.il/files/expc.csv -> 206

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Cache-Control: no-cache; Range: bytes=0-200

- Cache-Control: max-age=60
- Content-Type: application/octet-stream
- Last-Modified: Tue, 08 Nov 2022 15:03:32 GMT
- Accept-Ranges: bytes
- ETag: "fce3a34483f3d81:0"
- X-Frame-Options: SAMEORIGIN
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block
- Strict-Transport-Security: max-age=31536000; preload
- X-MS-InvokeApp: 1;RequireReadOnly
- Date: Fri, 23 Oct 2026 14:40:50 GMT
- Connection: close
- Content-Length: 201
- Content-Range: bytes 0-200/154331
- Set-Cookie: p_hosting=(value not kept)
- Set-Cookie: TS0101ef41=(value not kept)
- Set-Cookie: TS074b8af6027=(value not kept)

Body, first 201 bytes (markers: none):

    ﻿סמל ועדה,שם ישוב,סמל ישוב,בזב,מצביעים,פסולים,כשרים,אמת,אצ,ב,ג,ד,ום,ז,זך,זנ,זץ,ט,י,יז,ינ,יץ,יק,כן,ך,ל,מחל,מרצ,נז,ני,�

### 1.6 browser headers: https://www.bechirot.gov.il/ -> 202

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8; Accept-Language: he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7; Accept-Encoding: gzip, deflate; Upgrade-Insecure-Requests: 1; Sec-Fetch-Dest: document; Sec-Fetch-Mode: navigate; Sec-Fetch-Site: none; Sec-Fetch-User: ?1

- Server: CloudFront
- Date: Fri, 23 Oct 2026 14:40:50 GMT
- Content-Length: 2015
- Connection: close
- x-amzn-waf-action: challenge
- Cache-Control: no-store, max-age=0
- Content-Type: text/html; charset=UTF-8
- Access-Control-Allow-Origin: *
- Access-Control-Max-Age: 86400
- Access-Control-Allow-Methods: OPTIONS,GET,POST
- Access-Control-Expose-Headers: x-amzn-waf-action
- X-Cache: Error from cloudfront
- Via: 1.1 dbd83e9e27cde36e1e56c6d1ae4f5a18.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD55-P3
- X-Amz-Cf-Id: RfQX9fQWoscqek3oBy6gWhjmrj57xeqWE0GRclmohJMQ0-xEsSDACQ==

Body, first 600 bytes (markers: challenge.js, awswaf, AwsWafIntegration, gokuProps, token):

    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title></title>
        <style>
            body {
                font-family: "Arial";
            }
        </style>
        <script type="text/javascript">
        window.awsWafCookieDomainList = [];
        window.gokuProps = {
    "key":"AQIDAHjcYu/GjX+QlghicBgQ/7bFaQZ+m5FKCMDnO+vTbNg96AGMNXqb+vVP2S5HDawg0LFAAAAAfjB8BgkqhkiG9w0BBwagbzBtAgEAMGgGCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQMw+dRS3o0mWTGKdplAgEQgDupJ44uBpsKm4akV3bM2Qp3g4Ce8qeUOqpDEONfL20/caZ70yIgmTrn7iw2LE+RQeNniwpzqxfVVX0TnQ==

### 1.7 browser headers: https://media26.bechirot.gov.il/ -> 202

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8; Accept-Language: he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7; Accept-Encoding: gzip, deflate; Upgrade-Insecure-Requests: 1; Sec-Fetch-Dest: document; Sec-Fetch-Mode: navigate; Sec-Fetch-Site: none; Sec-Fetch-User: ?1

- Server: CloudFront
- Date: Fri, 23 Oct 2026 14:40:51 GMT
- Content-Length: 2015
- Connection: close
- x-amzn-waf-action: challenge
- Cache-Control: no-store, max-age=0
- Content-Type: text/html; charset=UTF-8
- Access-Control-Allow-Origin: *
- Access-Control-Max-Age: 86400
- Access-Control-Allow-Methods: OPTIONS,GET,POST
- Access-Control-Expose-Headers: x-amzn-waf-action
- X-Cache: Error from cloudfront
- Via: 1.1 dd02f81d770406d1d5f9d2e199b1cd1a.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD55-P10
- X-Amz-Cf-Id: D_faQoEsjTWOQsGh3Jg1d3RQtHSSN2h9bBbyLcgEzD-5ylN_2nrRGA==

Body, first 600 bytes (markers: challenge.js, awswaf, AwsWafIntegration, gokuProps, token):

    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title></title>
        <style>
            body {
                font-family: "Arial";
            }
        </style>
        <script type="text/javascript">
        window.awsWafCookieDomainList = [];
        window.gokuProps = {
    "key":"AQIDAHjcYu/GjX+QlghicBgQ/7bFaQZ+m5FKCMDnO+vTbNg96AGMNXqb+vVP2S5HDawg0LFAAAAAfjB8BgkqhkiG9w0BBwagbzBtAgEAMGgGCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQMw+dRS3o0mWTGKdplAgEQgDupJ44uBpsKm4akV3bM2Qp3g4Ce8qeUOqpDEONfL20/caZ70yIgmTrn7iw2LE+RQeNniwpzqxfVVX0TnQ==

### 1.8 browser headers: https://media26.bechirot.gov.il/files/expb.csv -> 202

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8; Accept-Language: he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7; Accept-Encoding: gzip, deflate; Upgrade-Insecure-Requests: 1; Sec-Fetch-Dest: document; Sec-Fetch-Mode: navigate; Sec-Fetch-Site: none; Sec-Fetch-User: ?1

- Server: CloudFront
- Date: Fri, 23 Oct 2026 14:40:53 GMT
- Content-Length: 2015
- Connection: close
- x-amzn-waf-action: challenge
- Cache-Control: no-store, max-age=0
- Content-Type: text/html; charset=UTF-8
- Access-Control-Allow-Origin: *
- Access-Control-Max-Age: 86400
- Access-Control-Allow-Methods: OPTIONS,GET,POST
- Access-Control-Expose-Headers: x-amzn-waf-action
- X-Cache: Error from cloudfront
- Via: 1.1 dd02f81d770406d1d5f9d2e199b1cd1a.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD55-P10
- X-Amz-Cf-Id: BE6_PMDa4_fXRNhW43_MBbG9zIY04thglDQVzCqVQl66DR4Ulxszng==

Body, first 600 bytes (markers: challenge.js, awswaf, AwsWafIntegration, gokuProps, token):

    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title></title>
        <style>
            body {
                font-family: "Arial";
            }
        </style>
        <script type="text/javascript">
        window.awsWafCookieDomainList = [];
        window.gokuProps = {
    "key":"AQIDAHjcYu/GjX+QlghicBgQ/7bFaQZ+m5FKCMDnO+vTbNg96AGMNXqb+vVP2S5HDawg0LFAAAAAfjB8BgkqhkiG9w0BBwagbzBtAgEAMGgGCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQMw+dRS3o0mWTGKdplAgEQgDupJ44uBpsKm4akV3bM2Qp3g4Ce8qeUOqpDEONfL20/caZ70yIgmTrn7iw2LE+RQeNniwpzqxfVVX0TnQ==

### 1.9 browser headers: https://votes26.bechirot.gov.il/ -> 202

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8; Accept-Language: he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7; Accept-Encoding: gzip, deflate; Upgrade-Insecure-Requests: 1; Sec-Fetch-Dest: document; Sec-Fetch-Mode: navigate; Sec-Fetch-Site: none; Sec-Fetch-User: ?1

- Server: CloudFront
- Date: Fri, 23 Oct 2026 14:40:53 GMT
- Content-Length: 2015
- Connection: close
- x-amzn-waf-action: challenge
- Cache-Control: no-store, max-age=0
- Content-Type: text/html; charset=UTF-8
- Access-Control-Allow-Origin: *
- Access-Control-Max-Age: 86400
- Access-Control-Allow-Methods: OPTIONS,GET,POST
- Access-Control-Expose-Headers: x-amzn-waf-action
- X-Cache: Error from cloudfront
- Via: 1.1 199ce2cf78973c1314623ce9dcb5a03e.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD89-P3
- X-Amz-Cf-Id: m54ZS5nnPRXA6DxLI6K2dEPJDJCI46lEb-XwkkO1t3O7mov_iHdRXA==

Body, first 600 bytes (markers: challenge.js, awswaf, AwsWafIntegration, gokuProps, token):

    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title></title>
        <style>
            body {
                font-family: "Arial";
            }
        </style>
        <script type="text/javascript">
        window.awsWafCookieDomainList = [];
        window.gokuProps = {
    "key":"AQIDAHjcYu/GjX+QlghicBgQ/7bFaQZ+m5FKCMDnO+vTbNg96AG5ZUj4wUI4guVxsT4ewdAfAAAAfjB8BgkqhkiG9w0BBwagbzBtAgEAMGgGCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQMeX/+hTrgUTBhxXSDAgEQgDtY5nzj5njAUjFCT9bxnyvw8+YVpTpso7OG1gsCAxRgjZJYrxt4h6Xy6+ORqgrrxc9jGPLWXfs7xw6VIA==

### 1.10 browser headers: https://media25.bechirot.gov.il/files/expc.csv -> 206

Sent: User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 kalpi26-live; Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8; Accept-Language: he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7; Accept-Encoding: gzip, deflate; Upgrade-Insecure-Requests: 1; Sec-Fetch-Dest: document; Sec-Fetch-Mode: navigate; Sec-Fetch-Site: none; Sec-Fetch-User: ?1; Range: bytes=0-200

- Cache-Control: max-age=60
- Content-Type: application/octet-stream
- Last-Modified: Tue, 08 Nov 2022 15:03:32 GMT
- Accept-Ranges: bytes
- ETag: "fce3a34483f3d81:0"
- X-Frame-Options: SAMEORIGIN
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block
- Strict-Transport-Security: max-age=31536000; preload
- X-MS-InvokeApp: 1;RequireReadOnly
- Date: Fri, 23 Oct 2026 14:40:54 GMT
- Connection: close
- Content-Length: 201
- Content-Range: bytes 0-200/154331
- Set-Cookie: p_hosting=(value not kept)
- Set-Cookie: TS0101ef41=(value not kept)
- Set-Cookie: TS074b8af6027=(value not kept)

Body, first 201 bytes (markers: none):

    ﻿סמל ועדה,שם ישוב,סמל ישוב,בזב,מצביעים,פסולים,כשרים,אמת,אצ,ב,ג,ד,ום,ז,זך,זנ,זץ,ט,י,יז,ינ,יץ,יק,כן,ך,ל,מחל,מרצ,נז,ני,�

### 2 browser page, navigation 1: https://www.bechirot.gov.il/ -> 404

- age: 18598
- content-encoding: gzip
- content-type: text/html
- date: Fri, 23 Oct 2026 09:31:06 GMT
- etag: W/"c12244887df7032cb7079a3b8e46dcde"
- last-modified: Thu, 04 Apr 2024 13:53:01 GMT
- server: AmazonS3
- vary: Accept-Encoding
- via: 1.1 b64454e3c1123ac098282f1036154740.cloudfront.net (CloudFront)
- x-amz-cf-id: WHgWqwoJyGYSB7e_1bNKtcPw88CCgJLVZ2o0LA72R7Jbfw-JVbl8zw==
- x-amz-cf-pop: IAD55-P3
- x-amz-server-side-encryption: AES256
- x-cache: Error from cloudfront

### 2 browser page, navigation 1: https://media26.bechirot.gov.il/ -> 404

- age: 12445
- content-encoding: gzip
- content-type: text/html
- date: Fri, 23 Oct 2026 11:13:44 GMT
- etag: W/"c12244887df7032cb7079a3b8e46dcde"
- last-modified: Thu, 04 Apr 2024 13:53:01 GMT
- server: AmazonS3
- vary: Accept-Encoding
- via: 1.1 5ceb9cec7debee0553fef552eba62cc4.cloudfront.net (CloudFront)
- x-amz-cf-id: AAeqglc2nt-Ige8xJloE1l_UW-e3npYkKO9kwzkb9VmL9pe9-tuweQ==
- x-amz-cf-pop: IAD55-P10
- x-amz-server-side-encryption: AES256
- x-cache: Error from cloudfront

### 2 browser context.request: https://media26.bechirot.gov.il/files/expb.csv -> 404

- Content-Type: text/html
- Transfer-Encoding: chunked
- Connection: keep-alive
- Server: AmazonS3
- Last-Modified: Thu, 04 Apr 2024 13:53:01 GMT
- Content-Encoding: gzip
- x-amz-server-side-encryption: AES256
- Date: Fri, 23 Oct 2026 11:13:44 GMT
- ETag: W/"c12244887df7032cb7079a3b8e46dcde"
- Vary: Accept-Encoding
- X-Cache: Error from cloudfront
- Via: 1.1 dd02f81d770406d1d5f9d2e199b1cd1a.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD55-P10
- X-Amz-Cf-Id: DQJPQ0rRT5wHcL2lw_w4v4wsBwgDwwvOyRbwcvvid0AXMWYfy1IdsQ==
- Age: 12449

Body, first 300 bytes (markers: none):

    <!DOCTYPE html>
    <html dir="rtl" lang="he-IL" class="no-js">
        <head>
    		<meta charset="UTF-8">
    		<meta name="viewport" content="width=device-width" />
        	<meta name="viewport" content="initial-scale=1, maximum-scale=1, user-scalable=no" />
            <link rel="preconnect" href="https://fonts.

### 2 browser context.request: https://media26.bechirot.gov.il/files/expc.csv -> 404

- Content-Type: text/html
- Transfer-Encoding: chunked
- Connection: keep-alive
- Server: AmazonS3
- Last-Modified: Thu, 04 Apr 2024 13:53:01 GMT
- Content-Encoding: gzip
- x-amz-server-side-encryption: AES256
- Date: Fri, 23 Oct 2026 11:13:44 GMT
- ETag: W/"c12244887df7032cb7079a3b8e46dcde"
- Vary: Accept-Encoding
- X-Cache: Error from cloudfront
- Via: 1.1 dd02f81d770406d1d5f9d2e199b1cd1a.cloudfront.net (CloudFront)
- X-Amz-Cf-Pop: IAD55-P10
- X-Amz-Cf-Id: B5pEhJl90Jk44sEPu13SX-SpqXF4o_1fjw4fo-3q2m4Tqk9KRW0GJw==
- Age: 12451

Body, first 300 bytes (markers: none):

    <!DOCTYPE html>
    <html dir="rtl" lang="he-IL" class="no-js">
        <head>
    		<meta charset="UTF-8">
    		<meta name="viewport" content="width=device-width" />
        	<meta name="viewport" content="initial-scale=1, maximum-scale=1, user-scalable=no" />
            <link rel="preconnect" href="https://fonts.

summary.json holds every record. Cookie values are never kept.
