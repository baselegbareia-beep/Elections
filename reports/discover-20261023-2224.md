## CEC file discovery, 23.10 22:24 Israel time (full, github-hosted)

- **WAF: seen** on bechirot.gov.il, media26.bechirot.gov.il, votes26.bechirot.gov.il, www.bechirot.gov.il: its challenge instead of the CEC's answer on 7 requests; a challenged host is then asked through the browser directly (urllib again every 10 minutes).
- **The browser path got past it: yes**: 329 URLs answered through Chrome 155.0.8059.39 (its own User-Agent, HeadlessChrome/155.0.0.0): HTTP 404 ×329.

453 URLs probed in 118 s, 55 answered. Control (2022 file): 200 (results-locality, 154331 bytes). How to read this: docs/FILE_DISCOVERY.md.

| live_config key | now | state | switch to | column_aliases |
|---|---|---|---|---|
| results_url | https://media26.bechirot.gov.il/files/expb.csv | answers as error (404) | — |  |
| results_url_localities | https://media26.bechirot.gov.il/files/expc.csv | answers as error (404) | — |  |
| station_turnout_url | — | not set | — |  |
| national hourly (live_input/turnout.json) | — | none found | — |  |

Other candidates (in brackets: why not suggested, or what to check):

- results_url_localities: https://media25.bechirot.gov.il/files/expc.csv (control, 2022/test)

### Since 2026-10-23T13:30:41+03:00: 4 new, 0 changed, 0 gone

|  | URL | class | what |
|---|---|---|---|
| new | https://www.gov.il/he/pages/voting-by-hour-26 | html | was 403 |
| new | https://www.gov.il/ruxitagentjs_ICA1589NPRTUVXafhlqrtux_10347260902154543.js | html | was not probed |
| new | https://www.gov.il/HomepageWebApi/client-config.js | script | was not probed |
| new | https://www.gov.il/govilCoreCloud/header-footer.js?hideSearch=true | script | was not probed |

### Files and pages with data

| class | URL | HTTP | bytes | last-modified | details |
|---|---|---|---|---|---|
| data-other | https://data.gov.il/api/3/action/help_show?name=package_show | 200 | 595 |  |  |
| data-other | https://data.gov.il/api/3/action/package_show?id=votes-knesset | 200 | 29919 |  | json 17 rows |
| results-locality | https://media25.bechirot.gov.il/files/expc.csv | 200 | 154331 | Tue, 08 Nov 2022 15:03:31 GMT | csv 1216 rows; 1215 loc, 1215 counted; letters 2022 (a test file?); 1 double-envelope rows (סמל ישוב 9999); stored: files/20261015-1201/412785ed-media25.bechirot.gov.il_expc.csv |

### Stored files (1; on the ops-reports branch under reports/, locally under the --out folder)

`git fetch origin ops-reports && git show origin/ops-reports:reports/<path> > <file>`; convert a turnout release with `python3 pipeline/discover.py --convert <file>` (docs/FILE_DISCOVERY.md §3).

| class | URL | bytes | path |
|---|---|---|---|
| results-locality | https://media25.bechirot.gov.il/files/expc.csv | 154331 | files/20261015-1201/412785ed-media25.bechirot.gov.il_expc.csv |

### Hosts

| host | IPs | probed | answered | status codes | through | WAF | hint |
|---|---|---|---|---|---|---|---|
| analytics.egov.gov.il | 147.237.12.35 | 1 | 0 | {"no answer": 1} |  |  | URLError |
| aws-e.data.gov.il | 18.165.98.102, 18.165.98.123, 18.165.98.28 | 17 | 17 | {"200": 17} | urllib 17 |  |  |
| bechirot.gov.il | 147.237.12.28 | 3 | 0 | {"404": 3} | browser 3 | 1 | CloudFront (Error from cloudfront) |
| bechirot26.bechirot.gov.il | DNS: gaierror | 1 | 0 | {"no answer": 1} | urllib 1 |  | URLError |
| cdn-votes26.bechirot.gov.il | 147.237.2.202 | 52 | 0 | {"no answer": 52} | urllib 3 |  | skipped; URLError |
| data.gov.il | 3.171.76.10, 3.171.76.125, 3.171.76.28 | 2 | 2 | {"200": 2} | urllib 2 |  |  |
| e.data.gov.il | 18.165.98.102, 18.165.98.123, 18.165.98.28 | 17 | 17 | {"200": 17} | urllib 17 |  |  |
| media25.bechirot.gov.il | 147.237.3.207 | 1 | 1 | {"200": 1} | urllib 1 |  |  |
| media26.bechirot.gov.il | 2600:9000:215a:200:1b:8951:5b80:93a1, 2600:9000:215a:2a00:1b:8951:5b80:93a1, 2600:9000:21… | 270 | 0 | {"404": 270} | browser 270 | 4 | CloudFront (Error from cloudfront) |
| openapi-gc.digital.gov.il | 34.8.107.129 | 7 | 0 | {"500": 7} | urllib 7 |  |  |
| sm.gov.il | 147.237.10.47 | 1 | 0 | {"no answer": 1} |  |  | URLError |
| votes26.bechirot.gov.il | 2600:9000:28a9:2600:3:c455:d440:93a1, 2600:9000:28a9:2c00:3:c455:d440:93a1, 2600:9000:28a… | 55 | 0 | {"404": 55} | browser 55 | 1 | CloudFront (Error from cloudfront) |
| www.bechirot.gov.il | 18.165.83.108, 18.165.83.124, 18.165.83.78 | 1 | 0 | {"404": 1} | browser 1 | 1 | CloudFront (Error from cloudfront) |
| www.gov.il | 104.18.36.14, 172.64.151.242, 2606:4700:4403::ac40:97f2 | 25 | 18 | {"200": 18, "404": 6, "403": 1} | urllib 25 |  | not found |

### Pages and scripts that answered

| URL | HTTP | title / notes |
|---|---|---|
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/1a1c7b2b-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/22f3a195-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/3b9e911a-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/3dc36e20-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/419be3b0-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/432d3185-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/498b48e9-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/70f8bc93-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/840edb33-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/929b50c6-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/9921a347-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/b392b8ee-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/bd22cd14-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/c20cdcef-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/c3db5581-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/cc223336-… | 200 | כניסה - חשבונות Google |
| https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/f79f9ba5-… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/1a1c7b2b-e819… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/22f3a195-3a79… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/3b9e911a-2e90… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/3dc36e20-25d6… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/419be3b0-fd30… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/432d3185-545a… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/498b48e9-5af6… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/70f8bc93-8d98… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/840edb33-90ac… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/929b50c6-f455… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/9921a347-8466… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/b392b8ee-ba45… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/bd22cd14-138c… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/c20cdcef-4d42… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/c3db5581-f48d… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/cc223336-07bc… | 200 | כניסה - חשבונות Google |
| https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/f79f9ba5-fe12… | 200 | כניסה - חשבונות Google |
| https://www.gov.il/he/pages/chat-config.json | 200 |  |
| https://www.gov.il/he/pages/chat.js | 200 |  |
| https://www.gov.il/he/pages/govilCoreCloud/cdn/gaPush.js | 200 |  |
| https://www.gov.il/he/pages/govilCoreCloud/cdn/hfGaEvents.js | 200 |  |
| https://www.gov.il/he/pages/gtm.js | 200 |  |
| https://www.gov.il/he/pages/voting-by-hour | 200 |  |
| https://www.gov.il/he/pages/voting-by-hour-26 | 200 |  |
| https://www.gov.il/ruxitagentjs_ICA1589NPRTUVXafhlqrtux_10347260902154543.js | 200 | govil - אתר השירותים והמידע הממשלתי |
| https://www.gov.il/ContentpageWebApi/client-config.js | 200 |  |
| https://www.gov.il/HomepageWebApi/client-config.js | 200 |  |
| https://www.gov.il/cdn-cgi/challenge-platform/scripts/jsd/main.js | 200 |  |
| https://www.gov.il/govilCoreCloud/cdn/chat.js | 200 |  |
| https://www.gov.il/govilCoreCloud/header-footer.js | 200 |  |
| https://www.gov.il/govilCoreCloud/header-footer.js?hideSearch=true | 200 |  |
| https://www.gov.il/pages/main.984b301a425b65f0.js | 200 |  |
| https://www.gov.il/pages/polyfills.8bb0aa0801d9a987.js | 200 |  |
| https://www.gov.il/pages/runtime.29beade9a2f4cb8f.js | 200 |  |
| https://www.gov.il/pages/styles.6fd4737a39597cd8.js | 200 |  |

### Harvested from pages and scripts

- https://data.gov.il/api/3/action/package_show?id=votes-knesset: 36 links, 0 scripts
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/1a1c7b2b-e819-4ba9-b159-d68e3566c58b/download/-21-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/22f3a195-3a79-436c-be23-cb606bc7b398/download/-22-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/3b9e911a-2e90-4587-b209-84171664056b/download/-23-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/3dc36e20-25d6-4496-ba6a-71d9bc917349/download/-23-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/419be3b0-fd30-455a-afc0-034ec36be990/download/-24-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/432d3185-545a-41d9-8c72-d10ee515919c/download/expbkalpi.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/498b48e9-5af6-474d-b7a4-5ac1e21d3a08/download/-16-2003.xls
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/70f8bc93-8d98-4c20-ad7c-768af713f1c5/download/-17-.xls
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/840edb33-90ac-4176-8ad9-4cdcb8e5caa5/download/-18-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/929b50c6-f455-4be2-b438-ec6af01421f2/download/expc-5.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/9921a347-8466-4ef4-81f9-22523c5c4632/download/-24-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/b392b8ee-ba45-4ea0-bfed-f03a1a36e99c/download/-25-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/bd22cd14-138c-4917-931a-ef628c2a5a30/download/-22-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/c20cdcef-4d42-4241-a41b-6ca7ae51002d/download/expcity.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/c3db5581-f48d-45fc-b221-e7635e940c41/download/expbkal20.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/cc223336-07bc-485d-b160-62df92967c0a/download/-25-.csv
  - https://aws-e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/f79f9ba5-fe12-4b90-96cc-916f1b7c1c34/download/-21-.csv
  - https://data.gov.il/api/3/action/help_show?name=package_show
  - https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/1a1c7b2b-e819-4ba9-b159-d68e3566c58b/download/-21-.csv
  - https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/22f3a195-3a79-436c-be23-cb606bc7b398/download/-22-.csv
  - https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/3b9e911a-2e90-4587-b209-84171664056b/download/-23-.csv
  - https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/3dc36e20-25d6-4496-ba6a-71d9bc917349/download/-23-.csv
  - https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/419be3b0-fd30-455a-afc0-034ec36be990/download/-24-.csv
  - https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/432d3185-545a-41d9-8c72-d10ee515919c/download/expbkalpi.csv
  - https://e.data.gov.il/dataset/26f9fa06-fcd7-4173-8df5-65797b63e857/resource/498b48e9-5af6-474d-b7a4-5ac1e21d3a08/download/-16-2003.xls
- https://www.gov.il/govilCoreCloud/cdn/chat.js: 9 links, 1 scripts
  - https://www.gov.il/api/
  - https://www.gov.il/api/GetChatConfig
  - https://www.gov.il/he/pages/chat-config.json
  - fragment: `tring(0,n.lastIndexOf("/")+1))?t:""}function q(){return V().replace(/\/cdn\/$/,"/api/")}function K(){try{var e=window.__GOVIL_CHAT_CONFIG__;return W(e)?JSON.parse(JS`
  - fragment: `=window.govilHeaderFooterRunConfig)?void 0:n.clientId,l=r?r.replace(/\/+$/,"")+"/api/GetChatConfig":q()+"GetChatConfig",i={},a&&(i["x-client-id"]=a),e.next=1,fetch(l`
- https://www.gov.il/govilCoreCloud/header-footer.js: 22 links, 6 scripts
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetHeaderMoreData
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=ar
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=en
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=es
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=fr
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=he
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=ru
  - https://sm.gov.il/trends.json
  - fragment: `MoreDataUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetHeaderMoreData", "analyticsString": "https://analytics.egov.gov.il/an`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=he", "hasIcon": null, "title": "שירו`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=en", "hasIcon": null, "title": "Serv`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=ar", "hasIcon": null, "title": "خدما`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=ru", "hasIcon": null, "title": "Услу`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=es", "hasIcon": null, "title": "Serv`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=fr", "hasIcon": null, "title": "Serv`
- https://www.gov.il/pages/main.984b301a425b65f0.js: 1 links, 0 scripts
  - fragment: `:e.contentPageWebApi,o=null==(a=window.govilRunConfig)?void 0:a.clientId,i='${l}/api/content-pages/${n}?culture=${A}'+(r.chapterIndex?'&chapterIndex=${r.chapterIndex`
  - fragment: `Options:n,shareLabel:r})=>{const[a,l,i]=d();if((0,o().useEffect)(()=>{e&&l('${e}/api/GetSharePageList?culture=he',!1,void 0,t)},[]),null==a\|\|!a.length\|\|i)return null`
- https://www.gov.il/HomepageWebApi/client-config.js: 2 links, 0 scripts
  - https://www.gov.il/api/homepage/get
  - fragment: `window['govilRunConfig'] = {"headerFooterUrl":"/","homePageUrl":"/api/homepage/get","homePageWebApi":"/HomepageWebApi/","showNewSearch":"True","assets`
- https://www.gov.il/govilCoreCloud/header-footer.js?hideSearch=true: 22 links, 6 scripts
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetHeaderMoreData
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=ar
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=en
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=es
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=fr
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=he
  - https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=ru
  - https://sm.gov.il/trends.json
  - fragment: `MoreDataUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetHeaderMoreData", "analyticsString": "https://analytics.egov.gov.il/an`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=he", "hasIcon": null, "title": "שירו`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=en", "hasIcon": null, "title": "Serv`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=ar", "hasIcon": null, "title": "خدما`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=ru", "hasIcon": null, "title": "Услу`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=es", "hasIcon": null, "title": "Serv`
  - fragment: `navItemsUrl": "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture=fr", "hasIcon": null, "title": "Serv`

<details><summary>398 URLs that did not answer with data</summary>

| URL | HTTP | why |
|---|---|---|
| https://analytics.egov.gov.il/analytics.js | 0 | URLError: <urlopen error [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] sslv3 alert handshake failu… |
| https://bechirot.gov.il/ | 404 | CloudFront (Error from cloudfront) |
| https://bechirot.gov.il/robots.txt | 404 | CloudFront (Error from cloudfront) |
| https://bechirot.gov.il/sitemap.xml | 404 | CloudFront (Error from cloudfront) |
| https://bechirot26.bechirot.gov.il/election/about/Pages/Hours_section_turnout.aspx | 0 | URLError: <urlopen error [Errno -2] Name or service not known> |
| https://cdn-votes26.bechirot.gov.il/ | 0 | URLError: <urlopen error timed out> |
| https://cdn-votes26.bechirot.gov.il/api | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/api/ballots | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/api/results | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/api/turnout | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/data | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/ | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/achuz.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/achuz_hatzbaa.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/ahuz.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/ahuz_hatzbaa.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/ballot_turnout.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/ballots.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/ballots_turnout.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/expb.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/expc.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/hatzbaa.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/hourly.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/hours.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/kalpi.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/kalpi_turnout.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/kalpiot.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/kalpiot_turnout.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/participation.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/percent.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/percent_kalpi.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/percentage.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/shiur_hatzbaa.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/station_turnout.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/stations.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout26.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout_26.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout_ballot.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout_ballots.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout_by_ballot.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout_by_kalpi.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout_kalpi.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout_kalpiot.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout_station.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/turnout_stations.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/vote_percent.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/votes_percent.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/voting_percent.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/voting_percentage.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/files/votingpercentage.csv | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/percent | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/robots.txt | 0 | URLError: <urlopen error timed out> |
| https://cdn-votes26.bechirot.gov.il/sitemap.xml | 0 | URLError: <urlopen error timed out> |
| https://cdn-votes26.bechirot.gov.il/turnout | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/voting-percentage | 0 | skipped: the host did not answer 3 times in this run |
| https://cdn-votes26.bechirot.gov.il/votingpercentage | 0 | skipped: the host did not answer 3 times in this run |
| https://media26.bechirot.gov.il/ | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/?list-type=2 | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/?prefix=files/ | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/achuz.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/achuz_hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/ahuz.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/ahuz_hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/ballot_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/ballots.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/ballots_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/expb.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/expc.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/achuz.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/achuz.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/achuz.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/achuz_hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/achuz_hatzbaa.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/achuz_hatzbaa.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ahuz.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ahuz.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ahuz.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ahuz_hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ahuz_hatzbaa.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ahuz_hatzbaa.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ballot_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ballot_turnout.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ballot_turnout.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ballots.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ballots.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ballots.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ballots_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ballots_turnout.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/ballots_turnout.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/double_envelopes.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/envelopes.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expa.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expb.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expb.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expb.txt | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expb.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expb.zip | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expb_env.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expb_maatafot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expc.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expc.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expc.txt | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expc.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expc.zip | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expd.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expe.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expf.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expg.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/exph.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expi.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expj.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expk.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expl.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expm.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expn.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expo.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expp.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expq.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expr.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/exps.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expt.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expu.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expv.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expw.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expx.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expy.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/expz.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/hatzbaa.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/hatzbaa.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/hourly.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/hourly.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/hourly.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/hours.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/hours.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/hours.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_10.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1000.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_11.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1100.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_12.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1200.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_13.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1300.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_14.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1400.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_15.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1500.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_16.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1600.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_17.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1700.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_18.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1800.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_19.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_1900.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_20.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_2000.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_22.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpi_turnout_2200.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpiot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpiot.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpiot.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpiot_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpiot_turnout.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kalpiot_turnout.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/kfulot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/maatafot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/maatafot_kfulot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/participation.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/participation.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/participation.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/percent.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/percent.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/percent_kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/percent_kalpi.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/percent_kalpi.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/percentage.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/percentage.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/percentage.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/shiur_hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/shiur_hatzbaa.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/shiur_hatzbaa.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/soldiers.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/station_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/station_turnout.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/station_turnout.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/stations.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/stations.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/stations.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout26.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout26.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout26.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_10.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1000.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_11.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1100.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_12.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1200.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_13.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1300.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_14.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1400.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_15.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1500.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_16.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1600.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_17.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1700.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_18.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1800.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_19.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_1900.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_20.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_2000.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_22.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_2200.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_26.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_26.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_26.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_ballot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_ballot.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_ballot.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_ballots.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_ballots.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_ballots.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_by_ballot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_by_ballot.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_by_ballot.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_by_kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_by_kalpi.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_by_kalpi.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_10.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1000.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_11.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1100.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_12.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1200.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_13.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1300.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_14.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1400.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_15.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1500.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_16.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1600.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_17.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1700.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_18.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1800.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_19.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_1900.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_20.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_2000.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_22.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpi_2200.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpiot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpiot.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_kalpiot.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_station.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_station.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_station.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_stations.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_stations.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/turnout_stations.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/vote_percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/vote_percent.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/vote_percent.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/votes_percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/votes_percent.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/votes_percent.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/voting_percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/voting_percent.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/voting_percent.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/voting_percentage.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/voting_percentage.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/voting_percentage.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/votingpercentage.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/votingpercentage.json | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/files/votingpercentage.xlsx | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/hourly.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/hours.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/kalpi_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/kalpiot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/kalpiot_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/participation.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/percent_kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/percentage.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/robots.txt | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/shiur_hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/sitemap.xml | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/station_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/stations.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout26.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout_26.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout_ballot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout_ballots.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout_by_ballot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout_by_kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout_kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout_kalpiot.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout_station.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/turnout_stations.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/vote_percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/votes_percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/voting_percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/voting_percentage.csv | 404 | CloudFront (Error from cloudfront) |
| https://media26.bechirot.gov.il/votingpercentage.csv | 404 | CloudFront (Error from cloudfront) |
| https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetHeaderMoreData | 500 |  |
| https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture… | 500 |  |
| https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture… | 500 |  |
| https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture… | 500 |  |
| https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture… | 500 |  |
| https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture… | 500 |  |
| https://openapi-gc.digital.gov.il/pub/cio/govil/rest/corecloud/v1/api/GetServices?culture… | 500 |  |
| https://sm.gov.il/trends.json | 0 | URLError: <urlopen error [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] sslv3 alert handshake failu… |
| https://votes26.bechirot.gov.il/ | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/api | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/api/ballots | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/api/results | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/api/turnout | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/ballotresults | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/cityresults | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/data | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/ | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/achuz.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/achuz_hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/ahuz.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/ahuz_hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/ballot_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/ballots.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/ballots_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/expb.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/expc.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/hourly.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/hours.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/kalpi_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/kalpiot.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/kalpiot_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/participation.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/percent_kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/percentage.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/shiur_hatzbaa.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/station_turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/stations.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout26.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout_26.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout_ballot.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout_ballots.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout_by_ballot.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout_by_kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout_kalpi.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout_kalpiot.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout_station.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/turnout_stations.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/vote_percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/votes_percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/voting_percent.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/voting_percentage.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/files/votingpercentage.csv | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/nationalresults | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/percent | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/robots.txt | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/sitemap.xml | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/turnout | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/voting-percentage | 404 | CloudFront (Error from cloudfront) |
| https://votes26.bechirot.gov.il/votingpercentage | 404 | CloudFront (Error from cloudfront) |
| https://www.bechirot.gov.il/ | 404 | CloudFront (Error from cloudfront) |
| https://www.gov.il/api/ | 404 | not found |
| https://www.gov.il/api/GetChatConfig | 404 | not found |
| https://www.gov.il/api/homepage/get | 404 | not found |
| https://www.gov.il/govil-home-page/main.d61bc6df1199ea1f.js | 404 | not found |
| https://www.gov.il/govil-home-page/polyfills.8bb0aa0801d9a987.js | 404 | not found |
| https://www.gov.il/govil-home-page/runtime.c59f98b8efd4db6a.js | 403 |  |
| https://www.gov.il/govil-home-page/styles.6fd4737a39597cd8.js | 404 | not found |

</details>
