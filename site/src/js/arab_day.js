/* ===================== election day: the Arab society, locality by locality ===================== */
// The CEC publishes turnout for every regular polling station at least four times on election day (chair's
// decision of 16.8.2026). The feed sums each release with pipeline/arab_turnout.py by locality, by the list that
// led there in 2022 (Ra'am, or Hadash-Ta'al + Balad: the 2026 Joint List), by region and by kind, and publishes
// turnout.json "arab" (the latest release) and "arab_history" (one compact entry per release, with every locality's
// and kind's turnout and pace). live.js mounts #lv-arab in the day section and calls drawArabDay() after every render
// and refresh tick. Without live data the section plays four synthetic releases (data/arab_day_demo.json), labelled
// as a demo; on election day before the first release, and after the day, it shows the 2022 base. Turnout only:
// nothing here turns turnout into votes, seats or threshold chances (owner's decision of 10.10.2026).
const AD = {
  base: null, idx: null, demo: null, load: null, demoLoad: null,
  sel: 2,                          // demo: the release shown (18:00)
  rows: 'lead',                    // the swarm's rows: by the 2022 leader or by region
  sort: { k: 'elig', dir: -1 }, q: '', lead: 'all', region: 'all', kind: 'all', size: 'all', watchOnly: false,
  watch: null,                     // localities pinned to the top of the table (default: the ten largest)
  seen: null,                      // live: the locality figures of the releases this browser has seen
  D: null,
};
const AD_GROUPS = ['raam', 'joint', 'other'];
const AD_REGIONS = ['negev', 'triangle', 'galilee', 'haifa', 'mixed', 'jerusalem', 'golan'];
const AD_G = {
  raam: { short: t('רע״ם'), long: t('יישובים שבהם הובילה רע״ם'), row: t('הובילה רע״ם') },
  joint: { short: t('המשותפת'), long: t('יישובים שבהם הובילה המשותפת'), row: t('הובילה המשותפת') },
  other: { short: t('אחרת'), long: t('יישובים שבהם הובילה רשימה אחרת'), row: t('הובילה רשימה אחרת') },
};
const AD_IN = { negev: t('בנגב'), triangle: t('במשולש'), galilee: t('בגליל ובעמקים'), haifa: t('בכרמל ובמחוז חיפה'), jerusalem: t('באזור ירושלים'), golan: t('ברמת הגולן'), mixed: t('בקלפיות הערביות של הערים המעורבות') };
const AD_SIZES = [['all', t('כל הגדלים')], ['l', t('20,000 בעלי זכות ומעלה')], ['m', '5,000–20,000'], ['s', t('עד 5,000')]];
const AD_BIG = 5000;               // the reads name localities of at least this many voters (small ones are noisy)
const AD_STAR = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.6l1.9 4.1 4.4.5-3.3 3 .9 4.4L8 11.4l-3.9 2.2.9-4.4-3.3-3 4.4-.5z"/></svg>';

const adStore = {   // per-viewer conveniences only; storage can be missing or blocked
  get(k) { try { return JSON.parse(localStorage.getItem('kalpi26.' + k)); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem('kalpi26.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
// '14:00', '14:00:00' or an ISO time -> 14.0 (the first hh:mm in the string)
const adHour = t => { const m = /(\d{1,2}):(\d{2})/.exec(String(t ?? '')); return m ? +m[1] + +m[2] / 60 : null; };
const adHHMM = h => h == null ? '' : `${String(Math.floor(h)).padStart(2, '0')}:${String(Math.round((h % 1) * 60)).padStart(2, '0')}`;
const adRel = e => e && (e.as_of || e.released);   // the time the figures refer to
const adClosed = () => ilStamp(ilNow()) >= POLLS_CLOSE;
const adP = (x, d = 1) => x == null || isNaN(x) ? '—' : pct(100 * x, d);
const adSigned = (x, d = 1) => x == null || isNaN(x) ? '—' : `${x >= 0 ? '+' : '−'}${Math.abs(x).toLocaleString('he-IL', { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const adNorm = s => {
  const n = String(s || '').replace(/[׳'’`]/g, "'").replace(/[״"]/g, '"').replace(/[-־]/g, ' ').replace(/\s+/g, ' ').trim();
  // Arabic search: hamza forms, taa marbuta, alif maqsura and the diacritics do not matter
  return AR_ON ? n.replace(/[\u064B-\u0652\u0670\u0640]/g, '').replace(/[أإآٱ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي') : n;
};
const adWidth = (el, min = 120) => Math.max(min, Math.round(el.getBoundingClientRect().width || min));
// a mixed city's entry is its Arab polling stations, not the (mostly Jewish) city: named so in every sentence,
// tooltip and table row ('לוד (הקלפיות הערביות)')
const AD_MIXED = t('הקלפיות הערביות');
// the CEC's locality names carry a stray space on one side of a hyphen ('תל אביב -יפו', 'אל -עריאן'); a hyphen
// spaced on both sides is the official spelling ('שבלי - אום אל-גנם') and stays
const adClean = s => String(s || '').replace(/(\S) -(?=\S)/g, '$1-').replace(/(\S)- (?=\S)/g, '$1-');
const adCity = b => adClean(b.city || String(b.name || '').replace(/\s*\([^)]*\)\s*$/, ''));
const adName = b => b.kind === 'mixed_arab' ? `${adCity(b)} (${AD_MIXED})` : adClean(b.name);
const adNameHTML = b => b.kind === 'mixed_arab' ? `<span class="ad-nm">${esc(adCity(b))}</span> <span class="ad-nm-sub">(${AD_MIXED})</span>` : `<span class="ad-nm">${esc(adClean(b.name))}</span>`;
// 'עד 14:00'; a release stamped at or after 22:00 counts the whole day
const adUntil = h => h != null && h >= 22 ? t('עד סגירת הקלפיות') : t('עד <span class="num">{h}</span>', { h: adHHMM(h) });

function arabDayHasData() {
  const A = S.liveTurnout && S.liveTurnout.arab;
  return !!(A && Array.isArray(A.localities) && A.localities.length && A.total);
}

function adLoad(withDemo) {
  if (!AD.load) {
    AD.load = fetchJSON('data/arab_day_2022.json').then(i18nArabDay).then(b => {
      AD.base = b; AD.idx = new Map(b.localities.map(x => [x.key, x]));
      const w = adStore.get('arabWatch');
      AD.watch = new Set(Array.isArray(w) ? w.filter(k => AD.idx.has(k)) : b.localities.filter(x => x.watch).map(x => x.key));
    }).catch(err => { AD.load = null; throw err; });
  }
  if (withDemo && !AD.demoLoad) AD.demoLoad = fetchJSON('data/arab_day_demo.json').then(d => { AD.demo = d; }).catch(err => { AD.demoLoad = null; throw err; });
  return Promise.all([AD.load, withDemo ? AD.demoLoad : null]);
}

// The 2022 Arab hourly curve (percent of eligible voters; estimates during the day, the official final at 22:00):
// {arab, nat} at hour h by straight lines from 0 at 07:00, and share = the part of the day's turnout cast by h.
function adCurve(h) {
  const C = AD.base && AD.base.curve; if (!C || h == null) return null;
  const hs = [7, ...C.hours.map(adHour)], ar = [0, ...C.arab], na = [0, ...C.national], n = hs.length - 1;
  if (h >= hs[n]) return { arab: ar[n], nat: na[n], share: 1 };
  h = Math.max(7, h);
  let i = 1; while (h > hs[i]) i++;
  const w = (h - hs[i - 1]) / (hs[i] - hs[i - 1]);
  const a = ar[i - 1] + w * (ar[i] - ar[i - 1]);
  return { arab: a, nat: na[i - 1] + w * (na[i] - na[i - 1]), share: a / ar[n] };
}

/* ---------- which data: live, waiting for the first release, the demo, or after election day ---------- */
const adAfter = () => ilStamp(ilNow()) >= ELECTION_DAY[1];   // election day and night are over
function adData() {
  const T = S.liveTurnout || {};
  if (arabDayHasData()) {
    const cur = T.arab;
    let hist = (Array.isArray(T.arab_history) ? T.arab_history : []).filter(e => e && e.total).map(e => ({ ...e }));
    if (!hist.some(e => adRel(e) === adRel(cur) || e.released === cur.released)) hist.push({ ...cur });
    hist.sort((a, b) => (adHour(adRel(a)) ?? 0) - (adHour(adRel(b)) ?? 0));
    const prev = adRemember(cur, hist, T);
    return { mode: 'live', cur, hist, prev, drill: !!((S.liveStatus || {}).drill || T.drill) };
  }
  if (adAfter()) return { mode: 'after', cur: null, hist: [], prev: null };   // no demo once the day is over
  if (inElectionWindow() || !AD.demo) return { mode: 'wait', cur: null, hist: [], prev: null };
  const R = AD.demo.releases, i = Math.max(0, Math.min(AD.sel, R.length - 1));
  return { mode: 'demo', cur: R[i], hist: R.slice(0, i + 1), prev: i ? R[i - 1] : null };
}
// a release's locality figures as [{key, turnout, pace}]: the feed's history entries carry {key: [turnout, pace]}
function adLocs(L) {
  if (Array.isArray(L)) return L.filter(l => l && l.key != null);
  if (!L || typeof L !== 'object') return null;
  return Object.entries(L).map(([key, v]) => Array.isArray(v) ? { key, turnout: v[0], pace: v[1] } : { key, ...(v || {}) });
}
// The change column needs the locality figures of the release before, and the Druze panel the kinds of the earlier
// releases. The feed's arab_history carries both ("localities", "kinds"); turnout.json "arab_prev" or what this
// browser saw of the earlier releases (localStorage) fill in for a feed without them.
function adRemember(cur, hist, T) {
  const t = ilNow(), day = `${t.y}-${t.m}-${t.d}`;
  let C = AD.seen || adStore.get('arabSeen');
  if (!C || C.day !== day || typeof C.rels !== 'object') C = { day, rels: {} };
  const key = adRel(cur), tag = `${key}:${cur.total && cur.total.voters}:${cur.localities.length}`;
  if (key && C.tag !== tag) {
    C.tag = tag;
    C.rels[key] = { locs: Object.fromEntries(cur.localities.map(l => [l.key, [l.turnout, l.pace]])),
      kinds: Object.fromEntries(Object.entries(cur.kinds || {}).map(([k, v]) => [k, { turnout: v.turnout, pace: v.pace }])) };
    Object.keys(C.rels).sort((a, b) => adHour(a) - adHour(b)).slice(0, -8).forEach(k => { delete C.rels[k]; });
    adStore.set('arabSeen', C);
  }
  AD.seen = C;
  hist.forEach(e => { const c = C.rels[adRel(e)]; if (!e.kinds && c && c.kinds) e.kinds = c.kinds; });
  const h = adHour(key);
  const fromRel = e => {
    const r = adRel(e), feed = adLocs(e.localities);
    if (feed && feed.length && e !== cur && adRel(e) !== key) return { released: r, localities: feed };
    if (T.arab_prev && adRel(T.arab_prev) === r && adLocs(T.arab_prev.localities)) return { released: r, localities: adLocs(T.arab_prev.localities) };
    const c = C.rels[r];
    return c && c.locs ? { released: r, localities: adLocs(c.locs) } : null;
  };
  // the release just before this one first; failing that, the latest earlier release with locality figures
  const before = hist.filter(e => adHour(adRel(e)) != null && adHour(adRel(e)) < h);
  for (let i = before.length - 1; i >= 0; i--) { const p = fromRel(before[i]); if (p) return p; }
  if (T.arab_prev && adHour(adRel(T.arab_prev)) < h && adLocs(T.arab_prev.localities)) return { released: adRel(T.arab_prev), localities: adLocs(T.arab_prev.localities) };
  const earlier = Object.keys(C.rels).filter(k => adHour(k) < h).sort((a, b) => adHour(a) - adHour(b)).pop();
  return earlier ? { released: earlier, localities: adLocs(C.rels[earlier].locs) } : null;
}

async function drawArabDay(el) {
  if (!el) return;
  try { await adLoad(!arabDayHasData() && !inElectionWindow() && !adAfter()); } catch (err) {
    console.error(err);
    if (el.isConnected && !el.firstElementChild) el.innerHTML = `<p class="empty">${t('נתוני החברה הערבית לא נטענו. הדף ינסה שוב בעדכון הבא.')}</p>`;
    return;
  }
  if (!el.isConnected) return;
  const D = adData();
  // redraw only when the data or a clock gate changed, so a refresh tick keeps the reader's sort, search and scroll
  const sig = JSON.stringify([D.mode, adRel(D.cur), D.cur && D.cur.released, D.cur && D.cur.total && D.cur.total.voters,
    D.hist.map(adRel), D.prev && adRel(D.prev), D.drill, adClosed(), adAfter()]);
  if (el.dataset.adSig === sig && el.querySelector('.ad-grid')) return;
  el.dataset.adSig = sig;
  AD.D = D;
  const a = document.activeElement, caret = a && a.id === 'ad-q' && el.contains(a) ? a.selectionStart : null;
  el.innerHTML = adMarkup(D);
  if (D.cur) {
    adBullet($('#ad-bullet', el), D);
    adGap($('#ad-gap', el), D);
    adRegions($('#ad-regions', el), D);
    adSwarm($('#ad-swarm', el), D);
    adMap($('#ad-map', el), D);
  }
  adTableBody(el);
  adBind(el);
  if (caret != null) { const q = $('#ad-q', el); if (q) { q.focus(); try { q.setSelectionRange(caret, caret); } catch (e) { /* type=search */ } } }
}

/* ---------- markup ---------- */
function adNext(D) {
  // the CEC has not announced the hours: the gap between the releases so far, or four hours (Channel 12's report)
  if (adClosed()) return t('הקלפיות נסגרו ב-22:00.');
  const hs = D.hist.map(e => adHour(adRel(e))).filter(h => h != null);
  const last = d3.max(hs); if (last == null) return '';
  const step = hs.length > 1 ? (last - d3.min(hs)) / (hs.length - 1) : 4;
  if (last >= 21) return t('ייתכן שזה הפרסום האחרון לפני סגירת הקלפיות ב-22:00.');
  const nx = Math.min(22, Math.round((last + Math.max(1, step)) * 2) / 2);
  return t(nx >= 22 ? 'הפרסום הבא צפוי בסביבות {h}, עם סגירת הקלפיות (לפי המרווח בין הפרסומים עד עכשיו).' : 'הפרסום הבא צפוי בסביבות {h} (לפי המרווח בין הפרסומים עד עכשיו).', { h: adHHMM(nx) });
}
function adMarkup(D) {
  const B = AD.base, demo = D.mode === 'demo', wait = D.mode === 'wait', live = D.mode === 'live', after = D.mode === 'after';
  const rel = D.cur ? adHHMM(adHour(adRel(D.cur))) : '';
  const tag = demo ? `<span class="ad-tag">${t('הדגמה · נתונים מדומים')}</span>` : '';
  let bar;
  if (demo) {
    const times = AD.demo.releases.map((r, i) => [i, adHHMM(adHour(adRel(r)))]);
    bar = `<span class="live-chip demo ad-demo">${t('הדגמה')}</span><span class="live-text">${t('<b>נתונים מדומים, לא תוצאות ולא תחזית:</b> {n} פרסומים שנבנו מהמצביעים בכל קלפי ב-2022, לפי העיתוי המשוער של ההצבעה בחברה הערבית ב-2022 ועם רעש אקראי לכל יישוב. ב-27 באוקטובר יוצגו כאן נתוני ועדת הבחירות לכל קלפי, בכל פעם שיתפרסמו (הוועדה הודיעה על ארבעה פרסומים לפחות במהלך היום): שיעור ההצבעה בכל יישוב ערבי ודרוזי ובקלפיות הערביות של הערים המעורבות, מול אותן קלפיות ב-2022.', { n: fmt(times.length), c: times.length })}</span>
      <span class="ad-rel"><span class="ctl-label" id="ad-rel-l">${t('פרסום מדומה')}</span><div class="seg" role="group" aria-labelledby="ad-rel-l" id="ad-rel">${times.map(([i, t]) => `<button type="button" data-v="${i}" aria-pressed="${i === Math.min(AD.sel, times.length - 1)}">${t}</button>`).join('')}</div></span>`;
  } else if (after) {
    bar = `<span class="live-chip demo">${t('אחרי יום הבחירות')}</span><span class="live-text">${t('אין כאן נתוני הצבעה לפי קלפי מיום הבחירות (27.10). מוצגים נתוני 2022 של כל יישוב.')}</span>`;
  } else if (wait && adClosed()) {
    bar = `<span class="live-chip demo">${t('יום הבחירות')}</span><span class="live-text">${t('הקלפיות נסגרו ב-22:00, ולא הגיע לכאן פרסום של שיעור ההצבעה לפי קלפי. מוצגים נתוני 2022 של כל יישוב.')}</span>`;
  } else if (wait) {
    bar = `<span class="live-chip demo">${t('יום הבחירות')}</span><span class="live-text">${t('ממתינים לפרסום הראשון של שיעור ההצבעה לפי קלפי. ועדת הבחירות הודיעה שתפרסם אותו לפחות ארבע פעמים במהלך היום. עד אז מוצגים כאן נתוני 2022 של כל יישוב, ואפשר לסמן יישובים למעקב.')}</span>`;
  } else {
    // seen_he: when the feed first saw this release's file (turnout.json's updated_he moves with every pass); the
    // feed's he_time adds '(27.10)' on another day, which reads as one clause here, not nested parentheses
    const seen = D.cur.seen_he && String(D.cur.seen_he).slice(0, 5) !== rel ? String(D.cur.seen_he).trim() : '';
    const sm = /^(\d{1,2}:\d\d)\s*\(([^)]*)\)$/.exec(seen);
    const seenHTML = sm ? `<span class="num">${esc(sm[1])}</span>, <span class="num">${esc(sm[2])}</span>` : `<span class="num">${esc(seen)}</span>`;
    bar = `${D.drill ? `<span class="live-chip demo">${t('תרגול')}</span>` : liveChip((S.liveTurnout || {}).updated_at, t('יום הבחירות'))}<span class="live-text">${D.drill ? t('תרגול על קובץ לדוגמה. ') : ''}${t('נתוני ועדת הבחירות לכל קלפי, הפרסום של <b class="num">{r}</b>', { r: rel })}${seen ? t(' (הקובץ הגיע ב-{s})', { s: seenHTML }) : ''}. ${esc(adNext(D))}</span>`;
  }
  const head = `<h2 class="lv-h2">${t('החברה הערבית: ההצבעה יישוב אחר יישוב')}</h2>
    <p class="ad-lede">${t('שיעור ההצבעה הרשמי בכל יישוב ערבי ודרוזי ובקלפיות הערביות של הערים המעורבות, מכל פרסום של ועדת הבחירות לפי קלפי, מול אותן קלפיות ב-2022. רק השתתפות: הדף אינו מתרגם את הנתונים האלה לקולות, למנדטים או לסיכויים לעבור את אחוז החסימה.')}</p>
    <div class="live-bar ad-bar ${live ? 'on' : 'demo'}">${bar}</div>`;
  if (wait || after) return head + `<div class="grid ad-grid">${wait && !adClosed() ? adWaitCard() : ''}${adTableCard(D, tag)}</div>`;
  const T = D.cur.total;
  return head + `<div class="grid ad-grid">
    <div class="card c12">${adHeadline(D, tag)}</div>
    <div class="card c7">
      <h3>${t('רע״ם מול המשותפת: לפי הרשימה שהובילה בכל יישוב ב-2022')}${tag}</h3>
      <p class="sub">${t('שיעור ההצבעה הרשמי, בשתי קבוצות יישובים: אלה שבהם רע״ם קיבלה ב-2022 יותר קולות, ואלה שבהם חד״ש-תע״ל ובל״ד יחד (שרצות ב-2026 כרשימה המשותפת) קיבלו יותר. <b>זו השוואת השתתפות, לא תחזית קולות:</b> בכל יישוב הצביעו גם לרשימות אחרות, והנתונים אינם מראים מי מגיע לקלפי.')}</p>
      <div class="ad-vs">${['raam', 'joint'].map(g => adGroupCol(g, D)).join('')}</div>
      ${adOtherLine(D)}
      <h4 class="ad-h4">${t('הפער בקצב, פרסום אחר פרסום')}</h4>
      <p class="sub">${t('הקצב ביישובי רע״ם פחות הקצב ביישובי המשותפת, בנקודות אחוז. קצב: המצביעים עד שעת הפרסום כאחוז מכל המצביעים באותן קלפיות ב-2022.')}</p>
      <div class="chart" id="ad-gap"></div>
      ${adGroupTable(D)}
    </div>
    <div class="card c5">
      <h3>${demo ? t('מה בולט בפרסום המדומה') : t('מה בולט בפרסום הזה')}${tag}</h3>
      <ol class="callout-list ad-reads">${adReads(D).map((r, i) => `<li><span class="n num">${i + 1}</span><p>${r}</p></li>`).join('')}</ol>
      <p class="foot">${t('משפטים שהדף מחשב מהנתונים בכל פרסום, בלי עריכה. יישוב נכלל בהשוואות של "מקדים" ו"מאחר" רק אם יש בו {n} בעלי זכות בחירה לפחות.', { n: fmt(AD_BIG) })}</p>
    </div>
    <div class="card c12">
      <h3>${t('לפי אזור')}${tag}</h3>
      <p class="sub">${t('שיעור ההצבעה בכל פרסום (הקו הרציף, 2026) מול המסלול של 2022 (המקווקו): שיעור ההצבעה הסופי של האזור ב-2022, מחולק על פני היום לפי העיתוי המשוער של 2022 בחברה הערבית. נקודה מעל המקווקו: האזור מקדים את 2022. הלוח האחרון מציג את היישובים הדרוזיים יחד (בגליל, בכרמל וברמת הגולן); הם נכללים גם בלוחות האזוריים.')}</p>
      <div class="ad-sm" id="ad-regions"></div>
      <div class="legend"><span><i class="line" style="background:var(--arab)"></i>${t('2026, בכל פרסום')}</span><span><i class="ad-k-dash"></i>${t('המסלול של 2022 (אומדן)')}</span><span><i class="ad-k-ring"></i>${t('הסוף ב-2022 (רשמי)')}</span><span>${t('ציר אופקי: השעה ביום הבחירות')}</span></div>
      ${adRegionTable(D)}
    </div>
    <div class="card c7">
      <div class="card-head"><div><h3>${t('כל היישובים לפי הקצב')}${tag}</h3>
        <p class="sub">${t('כל עיגול הוא יישוב (או הקלפיות הערביות של עיר מעורבת), בגודל לפי מספר בעלי זכות הבחירה ובצבע הרשימה שהובילה בו ב-2022. ימינה: קצב גבוה יותר, כלומר מספר המצביעים עד עכשיו קרוב יותר למספר המצביעים ב-2022. הקו המקווקו: הקצב שהיה צפוי בשעה הזו לפי העיתוי של 2022 (אומדן); הקו המלא, כשהוא בטווח: 100%, כמספר המצביעים ב-2022. הציר מתמקד בטווח שבו נמצאים היישובים.')}</p></div>
        <div><span class="ctl-label" id="ad-rows-l">${t('שורות')}</span> <div class="seg" role="group" aria-labelledby="ad-rows-l" id="ad-rows">${[['lead', t('לפי הרשימה המובילה')], ['region', t('לפי אזור')]].map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${AD.rows === v}">${l}</button>`).join('')}</div></div></div>
      <div class="chart" id="ad-swarm" aria-describedby="ad-swarm-note"></div>
      <p class="ad-sr" id="ad-swarm-note">${t('כל היישובים, עם שיעור ההצבעה והקצב של כל אחד, מופיעים בטבלה שבהמשך.')}</p>
      <div class="legend"><span><i class="ad-k-dot" style="background:var(--ad-raam)"></i>${t('הובילה רע״ם')}</span><span><i class="ad-k-dot" style="background:var(--ad-joint)"></i>${t('הובילה המשותפת (חד״ש-תע״ל ובל״ד)')}</span><span><i class="ad-k-ring"></i>${t('הובילה רשימה אחרת')}</span><span>${t('גודל העיגול: בעלי זכות הבחירה')}</span></div>
      <p class="foot">${T.coverage != null && T.coverage < 0.995 ? t('הפרסום מכסה {p} מהמצביעים של 2022 ביישובים האלה; יישוב שלא דווח אינו מוצג. ', { p: adP(T.coverage, 0) }) : ''}${t('יישובים קטנים קופצים יותר מפרסום לפרסום: בקלפי אחת שינוי של עשרות מצביעים מזיז את הקצב בנקודות רבות.')}</p>
    </div>
    <div class="card c5">
      <h3>${t('על המפה')}${tag}</h3>
      <p class="sub">${t('כל יישוב (או הקלפיות הערביות של עיר מעורבת) במקומו, בגודל לפי בעלי זכות הבחירה ובצבע לפי הקצב מול 2022 באותן קלפיות (המקרא שמתחת). עיגול ריק: היישוב אינו בפרסום הזה.')}</p>
      <div class="chart ad-map" id="ad-map" aria-describedby="ad-swarm-note"></div>
      <div class="legend" id="ad-map-key"></div>
      <p class="foot" id="ad-map-foot"></p>
    </div>
    ${adTableCard(D, tag)}
  </div>`;
}

// "2022 at the same hour" for the same stations as the release (like with like: the section's 2026 figure includes the
// mixed cities' Arab stations, whose 2022 final, 46%, is below the Arab and Druze localities' 53.2%). arab_turnout.py
// gives curve22 per kind (the Arab and Druze localities and the mixed cities' Arab stations each on its own 2022
// path); the total is their mean weighted by each kind's eligible voters in the release, as its turnout is. Without
// per-kind figures (an older feed): the 2022 final of the same stations spread over the day by the 2022 Arab timing.
function adSameHour(D, m, t22) {
  const h = adHour(adRel(D.cur));
  if (h == null || h < 10 || !m) return null;
  const K = Object.values(D.cur.kinds || {}).filter(k => k && k.turnout != null);
  if (K.length && K.every(k => k.curve22 != null)) {
    if (m !== D.cur.total) return m.curve22 != null ? m.curve22 : null;
    const e = d3.sum(K, k => k.elig || 0);
    if (e) return d3.sum(K, k => k.curve22 * (k.elig || 0)) / e;
    if (m.curve22 != null) return m.curve22;
  }
  const c = adCurve(h);
  // a total curve22 other than the raw Arab-and-Druze curve was computed for these stations by a newer data module
  if (m === D.cur.total && m.curve22 != null && c && Math.abs(m.curve22 - c.arab / 100) > 5e-4) return m.curve22;
  return c && t22 != null ? t22 * c.share : null;
}
// the headline's two rows (the bullet chart and its table)
function adBulletRows(D) {
  const T = D.cur.total, h = adHour(adRel(D.cur)), c = adCurve(h);
  const t22 = T.turnout22 != null ? T.turnout22 : AD.base.total.turnout22;
  return [
    { name: t('החברה הערבית'), v: T.turnout, ref: adSameHour(D, T, t22), fin: t22, pf: T.projected_final, fill: 'var(--arab)' },
    { name: t('ארצי'), v: D.cur.national, ref: c && h >= 10 ? c.nat / 100 : null, fin: null, pf: null, fill: 'var(--muted)' },
  ].filter(r => r.v != null);
}
function adHeadline(D, tag) {
  const T = D.cur.total, h = adHour(adRel(D.cur)), c = adCurve(h), rel = adHHMM(h), PF = T.projected_final;
  const t22 = T.turnout22 != null ? T.turnout22 : AD.base.total.turnout22;
  const exp = adSameHour(D, T, t22);
  const dExp = T.turnout != null && exp != null ? 100 * (T.turnout - exp) : null;
  // the 2022 curve's own points: the published estimates, a figure reported without attribution, the official end
  const C = AD.base.curve, pts = k => C.hours.map((t, i) => [t, C.arab[i], (C.arab_kind || [])[i]]).filter(x => x[2] === k);
  const val = ([hr, v]) => t('{v}% ב-{h}', { v: fmt1(v).replace(/\.0$/, ''), h: hr }), est = pts('estimate'), rep = pts('reported');
  const curveNote = [est.length ? t('מרכז אקורד (האוניברסיטה העברית) העריך {l}', { l: heJoin(est.map(val)) }) : '',
    rep.length ? t(rep.length > 1 ? '{l} דווחו בלי ייחוס' : '{l} דווח בלי ייחוס', { l: heJoin(rep.map(val)) }) : '',
    t('השעות האחרות משוחזרות במודל, והסוף ({v}% ביישובים הערביים והדרוזיים) רשמי', { v: fmt1(C.arab[C.arab.length - 1]) })].filter(Boolean).join(AR_ON ? '؛ ' : '; ');
  // the section's 2022 figure covers the same stations as the release, the mixed cities' Arab stations included, so it
  // differs from the Arab and Druze localities' figure the overview and the Arab tab quote under the same name
  const ad22 = C.arab[C.arab.length - 1], mixedIn = !!((D.cur.kinds || {}).mixed_arab || {}).stations || D.mode === 'demo';
  const scope = t22 != null && ad22 != null && Math.abs(100 * t22 - ad22) >= 0.05
    ? ` (${mixedIn ? t('כולל הקלפיות הערביות בערים המעורבות; ביישובים הערביים והדרוזיים בלבד') : t('בקלפיות שבפרסום; בכל היישובים הערביים והדרוזיים')} <span class="num">${fmt1(ad22)}%</span>)` : '';
  const rows = adBulletRows(D);
  const tiles = [
    [adP(T.pace, 0), t('ממספר המצביעים של 2022'), t('כבר הצביעו, באותן קלפיות. 100%: כמספר המצביעים בהן ב-2022')],
    [T.ratio_to_national != null ? (+T.ratio_to_national).toFixed(2) : '—', t('יחס לשיעור הארצי'), D.cur.national != null ? t('הארצי באותו פרסום: {n}', { n: adP(D.cur.national) }) + (exp != null && c && c.nat ? t('; ב-2022 באותה שעה, באותן קלפיות, כ-{r}', { r: (exp / (c.nat / 100)).toFixed(2) }) : '') : t('השיעור הארצי לא פורסם')],
    [PF ? `${adP(PF.lo, 0)}–${adP(PF.hi, 0)}` : '—', t('טווח גס לסוף היום'), PF ? t('האמצע: {m}; ב-2022: {p}', { m: adP(PF.mid, 0), p: adP(t22) }) : t('מחושב מהפרסום של 10:00 ואילך')],
    [adP(T.coverage, 0), t('כיסוי'), t('{s} קלפיות ב-{l} מתוך {n} יישובים', { s: fmt(T.stations), l: fmt(T.localities), n: fmt(AD.base.localities.length), c: T.stations })],
  ];
  return `<h3>${t('שיעור ההצבעה בחברה הערבית')}${tag}</h3>
    <div class="ad-head">
      <div class="ad-hero">
        <span class="eyebrow">${t('הצביעו {u}', { u: adUntil(h) })}${h != null && h > 22.01 ? t(' (הפרסום של <span class="num">{r}</span>)', { r: rel }) : ''}${D.mode === 'demo' ? t(' (מדומה)') : ''}</span>
        <span class="ad-hero-v num">${T.turnout == null && T.pace != null ? adP(T.pace, 0) : adP(T.turnout)}</span>${T.turnout == null && T.pace != null ? `<span class="ad-hero-d">${t('ממספר המצביעים של 2022 באותן קלפיות (בפרסום הזה אין מספרי בעלי זכות בחירה, ולכן אין שיעור הצבעה)')}</span>` : ''}
        <span class="ad-hero-d">${dExp != null ? t('<b class="num">{d}</b> נקודות מול 2022 באותה שעה, באותן קלפיות (אומדן: {e}). ', { d: adSigned(dExp), e: adP(exp) }) : ''}${t('בסוף היום ב-2022: <b class="num">{p}</b>{s}.', { p: adP(t22), s: scope })}</span>
        <div class="chart ad-bullet" id="ad-bullet" aria-describedby="ad-bullet-tbl"></div>
        <div class="legend"><span><i style="background:var(--arab)"></i>${t('עד שעת הפרסום')}</span><span><i class="ad-k-tick"></i>${t('2022 באותה שעה')}</span><span><i class="ad-k-dash"></i>${t('2022, סוף היום')}</span>${PF ? `<span><i class="ad-k-wash"></i>${t('טווח גס לסוף היום')}</span>` : ''}</div>
        ${rows.length ? `<details class="lv-table" id="ad-bullet-tbl"><summary>${t('הנתונים בטבלה')}</summary><div class="tbl-wrap"><table class="t"><thead><tr><th>${t('שיעור ההצבעה')}</th><th class="n">${t('עד {h}', { h: rel })}</th><th class="n">${t('2022 באותה שעה')}</th><th class="n">${t('2022, סוף היום')}</th><th class="n">${t('טווח גס לסוף היום')}</th></tr></thead><tbody>${
          rows.map(r => `<tr><td>${esc(r.name)}</td><td class="n"><b>${adP(r.v)}</b></td><td class="n">${adP(r.ref)}</td><td class="n">${adP(r.fin)}</td><td class="n"><span class="num">${r.pf ? `${adP(r.pf.lo, 0)}–${adP(r.pf.hi, 0)}` : '—'}</span></td></tr>`).join('')}</tbody></table></div></details>` : ''}
      </div>
      <div class="kv ad-kv">${tiles.map(([v, l, d]) => `<div><b class="num">${v}</b><span>${l}</span><small>${d}</small></div>`).join('')}</div>
    </div>
    <p class="foot">${t('שיעור הצבעה: המצביעים עד שעת הפרסום חלקי בעלי זכות הבחירה בקלפיות שבפרסום, בלי המעטפות הכפולות. קצב: המצביעים עד עכשיו חלקי כל המצביעים באותן קלפיות ב-2022 (יישוב שמספר הקלפיות בו השתנה מושווה כיחידה אחת). "2022 באותה שעה" הוא אומדן לא רשמי לאותן קלפיות: שיעור ההצבעה הסופי שלהן ב-2022, מחולק על פני היום לפי העיתוי המשוער של 2022 ({n}). הטווח לסוף היום מניח שהעיתוי ב-2026 יהיה דומה לזה של 2022, וזו נקודת התורפה שלו: ב-2022 הגיעה כשישית מהמצביעים בחברה הערבית אחרי 20:00.', { n: curveNote })}</p>`;
}

function adGroupCol(g, D) {
  const B = AD.base, b = B.groups[g], m = D.cur.groups[g] || {}, PF = m.projected_final;
  const h = adHour(adRel(D.cur));
  return `<div class="ad-grp ${g}">
    <span class="ad-grp-h">${AD_G[g].long}<small>${t('{n} יישובים · {e} בעלי זכות ב-2022', { n: fmt(b.localities), c: b.localities, e: fmt(b.elig22) })}</small></span>
    ${m.turnout == null && m.pace != null ? `<span class="ad-grp-v num">${adP(m.pace, 0)}</span><span class="ad-grp-l">${t('ממספר המצביעים של 2022, {u}', { u: adUntil(h) })}</span>`
      : `<span class="ad-grp-v num">${adP(m.turnout)}</span><span class="ad-grp-l">${t('הצביעו {u}', { u: adUntil(h) })}</span>`}
    <dl class="ad-dl">
      <div><dt>${t('קצב מול 2022')}</dt><dd class="num">${adP(m.pace, 0)}</dd></div>
      <div><dt>${t('הסוף ב-2022')}</dt><dd class="num">${adP(m.turnout22 != null ? m.turnout22 : b.turnout22)}</dd></div>
      <div><dt>${t('טווח גס לסוף היום')}</dt><dd class="num">${PF ? `${adP(PF.lo, 0)}–${adP(PF.hi, 0)}` : '—'}</dd></div>
    </dl></div>`;
}
function adOtherLine(D) {
  const b = AD.base.groups.other, m = D.cur.groups.other;
  if (!b || !m) return '';
  return `<p class="ad-other">${t('ועוד {n} יישובים שבהם הובילה ב-2022 רשימה אחרת, רובם דרוזיים: {t}קצב <span class="num">{p}</span> מול 2022.', { n: fmt(b.localities), c: b.localities, t: m.turnout != null ? t('<b class="num">{v}</b> הצביעו, ', { v: adP(m.turnout) }) : '', p: adP(m.pace, 0) })}</p>`;
}
function adGroupTable(D) {
  const cell = (e, g) => { const m = e.groups && e.groups[g]; return m ? `<td class="n">${adP(m.turnout)}</td><td class="n">${adP(m.pace, 0)}</td>` : '<td class="n">—</td><td class="n">—</td>'; };
  return `<details class="lv-table"><summary>${t('הנתונים בטבלה')}</summary><div class="tbl-wrap"><table class="t"><thead><tr><th>${t('פרסום')}</th>${AD_GROUPS.map(g => `<th class="n">${t('{g}: הצבעה', { g: AD_G[g].short })}</th><th class="n">${t('קצב')}</th>`).join('')}<th class="n">${t('הפער בקצב')}</th></tr></thead><tbody>${
    D.hist.map(e => { const r = e.groups && e.groups.raam, j = e.groups && e.groups.joint, gap = r && j && r.pace != null && j.pace != null ? 100 * (r.pace - j.pace) : null;
      return `<tr><td class="num">${adHHMM(adHour(adRel(e)))}</td>${AD_GROUPS.map(g => cell(e, g)).join('')}<td class="n"><span class="num">${adSigned(gap)}</span></td></tr>`; }).join('')}</tbody></table></div></details>`;
}
function adRegionPanels() {
  const B = AD.base;
  return [...AD_REGIONS.filter(k => B.regions[k]).map(k => ({ k, name: B.region_names[k], n: B.regions[k].localities, t22: B.regions[k].turnout22, get: e => e.regions && e.regions[k] })),
    ...(B.kinds.druze ? [{ k: 'druze', name: t('יישובים דרוזיים (כולם)'), n: B.kinds.druze.localities, t22: B.kinds.druze.turnout22, get: e => e.kinds && e.kinds.druze }] : [])];
}
function adRegionTable(D) {
  const P = adRegionPanels();
  return `<details class="lv-table"><summary>${t('הנתונים בטבלה')}</summary><div class="tbl-wrap"><table class="t"><thead><tr><th>${t('אזור')}</th>${D.hist.map(e => `<th class="n">${adHHMM(adHour(adRel(e)))}</th>`).join('')}<th class="n">${t('קצב עכשיו')}</th><th class="n">${t('הסוף ב-2022')}</th></tr></thead><tbody>${
    P.map(p => { const now = p.get(D.cur) || {}; return `<tr><td>${esc(p.name)}</td>${D.hist.map(e => `<td class="n">${adP((p.get(e) || {}).turnout)}</td>`).join('')}<td class="n">${adP(now.pace, 0)}</td><td class="n">${adP(p.t22)}</td></tr>`; }).join('')}</tbody></table></div>
    <p class="foot">${t('שיעור ההצבעה בכל פרסום.')} ${D.mode === 'live' && D.hist.some(e => !e.kinds) ? t('ליישובים הדרוזיים יחד יש רק את הפרסומים שהדף ראה מאז שנפתח. ') : ''}</p></details>`;
}
function adWaitCard() {
  const B = AD.base;
  return `<div class="card c12"><h3>${t('מה יופיע כאן בכל פרסום')}</h3>
    <ul class="lv-list">
      <li>${t('<b>שיעור ההצבעה בחברה הערבית</b> עד שעת הפרסום, מול אותה שעה ב-2022 ומול השיעור הארצי באותו פרסום, וטווח גס לשיעור הסופי.')}</li>
      <li>${t('<b>רע״ם מול המשותפת:</b> ההשתתפות ביישובים שבהם הובילה כל אחת מהן ב-2022. ב-2022 ההצבעה בשתי הקבוצות הייתה כמעט זהה: {a} ביישובי רע״ם, {b} ביישובי חד״ש-תע״ל ובל״ד.', { a: adP(B.groups.raam.turnout22), b: adP(B.groups.joint.turnout22) })}</li>
      <li>${t('<b>לפי אזור ולפי יישוב:</b> {r} (2022), וכל אחד מ-{n} היישובים בטבלה.', { r: AD_REGIONS.filter(k => B.regions[k]).map(k => `${esc(B.region_names[k])} ${adP(B.regions[k].turnout22, 0)}`).join(' · '), n: fmt(B.localities.length) })}</li>
    </ul>
    <p class="foot">${t('הדף אינו מתרגם את שיעורי ההצבעה לקולות או למנדטים.')}</p></div>`;
}

/* ---------- the reads: short neutral sentences computed from the release ---------- */
function adAgg(rows) {
  // re-aggregates localities: turnout over their eligible voters, pace over the 2022 voters of the compared stations
  let ve = 0, e = 0, now = 0, then = 0, n = 0;
  rows.forEach(r => {
    const c = r.c; if (!c) return; n++;
    if (c.turnout != null && c.elig) { ve += c.turnout * c.elig; e += c.elig; }
    if (c.pace != null && c.coverage != null) { const th = c.coverage * r.b.voters22; then += th; now += c.pace * th; }
  });
  return { turnout: e ? ve / e : null, pace: then ? now / then : null, n, elig: e };
}
function adNames(rows, n = 3) { return heJoin(rows.slice(0, n).map(r => esc(adName(r.b)))); }
// 'א, ב וג'; the conjunction takes a maqaf before a digit or a sign ('ו-44%', 'ו-−3%'), also inside a <span>
function heJoin(a) {
  if (AR_ON) return arJoin(a);
  if (a.length < 2) return a[0] || '';
  const z = a[a.length - 1];
  return a.slice(0, -1).join(', ') + (/^(<[^>]*>)*[\d+\-−±.]/.test(z) ? ' ו-' : ' ו') + z;
}
function adReads(D) {
  const out = [], rows = adRows(D), rep = rows.filter(r => r.c && r.pace != null), G = D.cur.groups || {};
  const h = adHour(adRel(D.cur)), f = adCurve(h), big = rep.filter(r => r.b.elig22 >= AD_BIG);
  // 1. Ra'am-led vs Joint-led, and in the localities where the lead was clear
  if (G.raam && G.joint && G.raam.pace != null && G.joint.pace != null) {
    const clear = g => adAgg(rows.filter(r => r.b.leader22 === g && r.b.margin22 >= 0.25));
    const cr = clear('raam'), cj = clear('joint');
    out.push(t('ביישובים שבהם הובילה רע״ם ב-2022 כבר הצביעו <b class="num">{r}</b> ממספר המצביעים של 2022 באותן קלפיות; ביישובים שבהם הובילו חד״ש-תע״ל ובל״ד <b class="num">{j}</b>.', { r: adP(G.raam.pace, 0), j: adP(G.joint.pace, 0) }) + (
      cr.pace != null && cj.pace != null && cr.n >= 3 && cj.n >= 3 ? t(' ביישובים שבהם ההובלה הייתה של 25 נקודות ומעלה: <span class="num">{r}</span> מול <span class="num">{j}</span>.', { r: adP(cr.pace, 0), j: adP(cj.pace, 0) }) : ''));
  }
  // 2. the region where the two groups differ most
  const gaps = AD_REGIONS.map(k => {
    const r = rows.filter(x => x.b.region === k), a = adAgg(r.filter(x => x.b.leader22 === 'raam')), b = adAgg(r.filter(x => x.b.leader22 === 'joint'));
    return a.n >= 2 && b.n >= 2 && a.elig >= AD_BIG && b.elig >= AD_BIG && a.pace != null && b.pace != null ? { k, a, b, gap: a.pace - b.pace } : null;
  }).filter(Boolean).sort((x, y) => Math.abs(y.gap) - Math.abs(x.gap));
  if (gaps.length && Math.abs(gaps[0].gap) >= 0.01) {
    const g = gaps[0];
    out.push(t('הפער הגדול ביותר בין שתי הקבוצות הוא {where}: קצב של <b class="num">{a}</b> ביישובי רע״ם מול <b class="num">{b}</b> ביישובי המשותפת ({na} ו-{nb} יישובים).', { where: AD_IN[g.k], a: adP(g.a.pace, 0), b: adP(g.b.pace, 0), na: fmt(g.a.n), nb: fmt(g.b.n) }));
  }
  // 3. since the previous release
  const P = D.hist.length > 1 ? D.hist[D.hist.length - 2] : null;
  if (P && P.total && P.total.turnout != null && D.cur.total.turnout != null) {
    // the national change: from the releases themselves, else from the CEC's hourly figures at the same two hours
    const NH = (S.liveTurnout || {}).national || {}, nh = e => NH[adHHMM(adHour(adRel(e)))];
    const dn = D.cur.national != null && P.national != null ? 100 * (D.cur.national - P.national)
      : D.mode === 'live' && nh(D.cur) != null && nh(P) != null ? nh(D.cur) - nh(P) : null;
    const up = rows.filter(r => r.d != null && r.b.elig22 >= AD_BIG).sort((a, b) => b.d - a.d);
    const dt = 100 * (D.cur.total.turnout - P.total.turnout), abs = v => adSigned(Math.abs(v)).slice(1);
    out.push(t(dt >= 0 ? 'מאז הפרסום של <span class="num">{h}</span> עלה שיעור ההצבעה בחברה הערבית ב-<b class="num">{d}</b> נקודות{n}.' : 'מאז הפרסום של <span class="num">{h}</span> ירד שיעור ההצבעה בחברה הערבית ב-<b class="num">{d}</b> נקודות{n}.', {
      h: adHHMM(adHour(adRel(P))), d: abs(dt), n: dn != null ? t(' (הארצי: <span class="num">{v}</span>)', { v: adSigned(dn) }) : '' }) + (up.length ? t(' העלייה הגדולה ביותר: {a}, <span class="num">{da}</span>{b}.', { a: esc(adName(up[0].b)), da: adSigned(100 * up[0].d),
      b: up[1] ? t(', ו{n}, <span class="num">{d}</span>', { n: esc(adName(up[1].b)), d: adSigned(100 * up[1].d) }) : '' }) : ''));
  }
  // 4. ahead of and behind the 2022 timing, among the larger localities
  if (f && h >= 10 && big.length >= 4) {
    const on = r => r.on != null ? r.on : r.pace / f.share;
    const s = [...big].sort((a, b) => on(b) - on(a)), hi = s.slice(0, 2), lo = s.slice(-2).reverse();
    const nm = a => heJoin(a.map(r => esc(adName(r.b)))), by = a => heJoin(a.map(r => `<span class="num">${fmt(Math.abs(100 * (on(r) - 1)))}%</span>`).map((x, i) => i ? t('ב-{v}', { v: x }) : x));
    const rel = a => { const up = a.map(r => on(r) >= 1); return up.every(u => u === up[0]) ? t(up[0] ? 'גבוה ב-{v}' : 'נמוך ב-{v}', { v: by(a) }) : heJoin(a.map(r => `<span class="num">${adSigned(100 * (on(r) - 1), 0)}%</span>`)); };
    out.push(t('מול הקצב שהיה צפוי בשעה הזו לפי העיתוי של 2022 (אומדן), הכי מקדימים מבין היישובים הגדולים: {a}, {ra} מהצפוי; הכי מאחרים: {b}, {rb}.', { a: nm(hi), ra: rel(hi), b: nm(lo), rb: rel(lo) }));
  }
  // 5. already past the 2022 voter count
  const past = rep.filter(r => r.pace >= 1).sort((a, b) => b.b.elig22 - a.b.elig22);
  if (past.length === 1) out.push(t('יישוב אחד כבר עבר את מספר המצביעים שלו ב-2022: {l}.', { l: adNames(past) }));
  else if (past.length) out.push(t('<b class="num">{n}</b> יישובים כבר עברו את מספר המצביעים שלהם ב-2022, ביניהם {l}.', { n: fmt(past.length), c: past.length, l: adNames(past) }));
  // 6. regions furthest ahead and behind; Druze and Arab localities
  const R = D.cur.regions || {}, onR = k => R[k].on_track != null ? R[k].on_track : R[k].pace != null && f && f.share ? R[k].pace / f.share : null;
  const regs = AD_REGIONS.filter(k => R[k] && onR(k) != null && AD.base.regions[k].elig22 >= 10000).sort((a, b) => onR(b) - onR(a));
  if (regs.length >= 3 && h >= 10) {
    const K = D.cur.kinds || {};
    const a = regs[0], z = regs[regs.length - 1];
    out.push(t('לפי אזור, מול העיתוי של 2022: הכי מקדימים {a} (קצב <span class="num">{pa}</span>), והכי מאחרים {z} (<span class="num">{pz}</span>).', { a: AD_IN[a], pa: adP(R[a].pace, 0), z: AD_IN[z], pz: adP(R[z].pace, 0) }) + (K.druze && K.arab && K.druze.pace != null ? t(' ביישובים הדרוזיים: קצב <span class="num">{d}</span>, ביישובים הערביים <span class="num">{r}</span>.', { d: adP(K.druze.pace, 0), r: adP(K.arab.pace, 0) }) : ''));
  }
  // 7. localities missing from the release
  const miss = rows.filter(r => !r.c && r.b.elig22 >= 1000).sort((a, b) => b.b.elig22 - a.b.elig22);
  if (miss.length === 1) out.push(t('יישוב אחד עם 1,000 בעלי זכות ומעלה לא מופיע בפרסום הזה: {l}.', { l: adNames(miss) }));
  else if (miss.length) out.push(t('<b class="num">{n}</b> יישובים עם 1,000 בעלי זכות ומעלה לא מופיעים בפרסום הזה, ביניהם {l}.', { n: fmt(miss.length), c: miss.length, l: adNames(miss) }));
  if (!out.length) out.push(t('אין עדיין מספיק נתונים להשוואות.'));
  return out;
}

/* ---------- headline bullet: the release against 2022 at the same hour and at the end of the day ---------- */
function adBullet(el, D) {
  const h = adHour(adRel(D.cur)), rows = adBulletRows(D);
  const lg = el.nextElementSibling;
  if (lg && lg.classList.contains('legend')) lg.hidden = !rows.length;
  if (!rows.length) { el.innerHTML = ''; return; }   // a release without eligible counts: the tiles carry the pace
  const W = adWidth(el, 260), nar = W < 420, rowH = 40, M = { t: 6, r: nar ? 92 : 112, b: 22, l: 18 };
  const H = M.t + M.b + rowH * rows.length;
  const top = Math.max(0.8, d3.max(rows, r => Math.max(r.v, r.pf ? r.pf.hi : 0, r.fin || 0, r.ref || 0)) + 0.02);
  const x = d3.scaleLinear().domain([0, top]).range([W - M.r, M.l]);   // bars grow from the right, as the page reads
  const svg = svgEl(el, W, H, t('שיעור ההצבעה בחברה הערבית ובארץ עד שעת הפרסום, מול 2022'));
  d3.range(0, top + 1e-9, 0.2).forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', x(v)).attr('x2', x(v)).attr('y1', M.t).attr('y2', H - M.b);
    svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 6).attr('text-anchor', 'middle').text(pct(100 * v, 0));
  });
  rows.forEach((r, i) => {
    const cy = M.t + i * rowH + rowH / 2, bh = 16;
    svg.append('text').attr('class', 'lbl-strong').attr('x', W - 2).attr('y', cy - 4).attr('text-anchor', 'start').text(r.name);
    svg.append('text').attr('class', 'lbl-ink').style('font-weight', 700).style('font-size', '14px').attr('x', W - 2).attr('y', cy + 13).attr('text-anchor', 'start').text(adP(r.v));
    svg.append('rect').attr('x', x(top)).attr('y', cy - bh / 2).attr('width', x(0) - x(top)).attr('height', bh).attr('rx', 3).attr('fill', 'var(--surface-2)');
    if (r.pf) svg.append('rect').attr('x', x(r.pf.hi)).attr('y', cy - bh / 2).attr('width', Math.max(2, x(r.pf.lo) - x(r.pf.hi))).attr('height', bh).attr('rx', 3).attr('fill', 'var(--arab)').attr('opacity', 0.25);
    svg.append('rect').attr('x', x(r.v)).attr('y', cy - bh / 2).attr('width', Math.max(0, x(0) - x(r.v))).attr('height', bh).attr('rx', 3).attr('fill', r.fill);
    if (r.fin != null) svg.append('line').attr('x1', x(r.fin)).attr('x2', x(r.fin)).attr('y1', cy - bh / 2 - 5).attr('y2', cy + bh / 2 + 5).attr('stroke', 'var(--muted)').attr('stroke-width', 2).attr('stroke-dasharray', '3 2');
    if (r.ref != null) svg.append('line').attr('x1', x(r.ref)).attr('x2', x(r.ref)).attr('y1', cy - bh / 2 - 5).attr('y2', cy + bh / 2 + 5).attr('stroke', 'var(--ink)').attr('stroke-width', 2);
    svg.append('rect').attr('x', 0).attr('y', cy - rowH / 2).attr('width', W).attr('height', rowH).attr('fill', 'transparent')
      .call(sel => bindTT(sel, () => `<h4>${esc(r.name)} · ${t('עד {h}', { h: adHHMM(h) })}</h4>${ttRows([[t('שיעור הצבעה'), adP(r.v)], ...(r.ref != null ? [[i ? t('2022 באותה שעה') : t('2022 באותה שעה (אומדן)'), adP(r.ref)]] : []),
        ...(r.fin != null ? [[t('2022, סוף היום'), adP(r.fin)]] : []), ...(r.pf ? [[t('טווח גס לסוף היום'), `${adP(r.pf.lo, 0)}–${adP(r.pf.hi, 0)}`]] : [])])}`));
  });
}

/* ---------- Ra'am-led minus Joint-led pace, release by release ---------- */
function adGap(el, D) {
  const pts = D.hist.map(e => {
    const r = e.groups && e.groups.raam, j = e.groups && e.groups.joint;
    return r && j && r.pace != null && j.pace != null ? { t: adHHMM(adHour(adRel(e))), g: 100 * (r.pace - j.pace), r: r.pace, j: j.pace } : null;
  }).filter(Boolean);
  if (!pts.length) { el.innerHTML = `<p class="empty">${t('אין עדיין נתוני קצב לשתי הקבוצות.')}</p>`; return; }
  const W = adWidth(el, 260), rowH = 26, M = { t: 24, r: 46, b: 6, l: 6 }, H = M.t + M.b + rowH * pts.length;
  const m = Math.max(2, d3.max(pts, p => Math.abs(p.g)) * 1.5);
  const x = d3.scaleLinear().domain([-m, m]).range([M.l, W - M.r]), cx = x(0);   // Ra'am to the right, as its card
  const svg = svgEl(el, W, H, t('הפער בקצב בין יישובי רע״ם ליישובי המשותפת בכל פרסום'));
  svg.append('text').attr('class', 'lbl').attr('x', W - M.r - 2).attr('y', 12).attr('text-anchor', 'start').text(t('יישובי רע״ם מקדימים'));
  svg.append('text').attr('class', 'lbl').attr('x', M.l + 2).attr('y', 12).attr('text-anchor', 'end').text(t('יישובי המשותפת מקדימים'));
  svg.append('line').attr('x1', cx).attr('x2', cx).attr('y1', M.t - 6).attr('y2', H - M.b).attr('stroke', 'var(--ink)').attr('stroke-width', 1);
  pts.forEach((p, i) => {
    const cy = M.t + i * rowH + rowH / 2, x1 = x(p.g), pos = p.g >= 0;
    svg.append('text').attr('class', 'lbl-ink').attr('x', W - 2).attr('y', cy).attr('dy', '.35em').attr('text-anchor', 'end').style('direction', 'ltr').text(p.t);   // LTR: right edge at x
    svg.append('rect').attr('x', Math.min(cx, x1)).attr('y', cy - 7).attr('width', Math.max(1.5, Math.abs(x1 - cx))).attr('height', 14).attr('rx', 3)
      .attr('fill', pos ? 'var(--ad-raam)' : 'var(--ad-joint)');
    // numbers read left to right: 'start' is the left edge, so the label sits beyond the bar's tip on its side
    svg.append('text').attr('class', 'lbl-strong').style('direction', 'ltr').attr('x', pos ? Math.max(x1, cx) + 5 : Math.min(x1, cx) - 5).attr('y', cy).attr('dy', '.35em')
      .attr('text-anchor', pos ? 'start' : 'end').text(adSigned(p.g));
    svg.append('rect').attr('x', 0).attr('y', cy - rowH / 2).attr('width', W).attr('height', rowH).attr('fill', 'transparent')
      .call(sel => bindTT(sel, () => `<h4>${t('פרסום של {h}', { h: p.t })}</h4>${ttRows([[t('קצב ביישובי רע״ם'), adP(p.r, 1), 'var(--ad-raam)'], [t('קצב ביישובי המשותפת'), adP(p.j, 1), 'var(--ad-joint)'], [t('הפער (נקודות)'), adSigned(p.g)]])}`));
  });
}

/* ---------- regions: small multiples of turnout over the releases ---------- */
function adRegions(el, D) {
  const P = adRegionPanels(), last = D.cur;
  // the hour axis runs to 22:00, or to the latest release when one is stamped later (a file first seen after closing)
  const xMax = Math.max(22, d3.max(D.hist, e => adHour(adRel(e))) || 22);
  const yMax = Math.max(0.6, d3.max(P, p => Math.max(p.t22 || 0, d3.max(D.hist, e => (p.get(e) || {}).turnout || 0))) + 0.06);
  el.innerHTML = P.map(p => { const m = p.get(last) || {}; return `<figure class="ad-pan"><figcaption><b>${esc(p.name)}</b><span class="v num">${adP(m.turnout)}</span><span>${t('קצב <span class="num">{p}</span> · {n} יישובים', { p: adP(m.pace, 0), n: fmt(p.n), c: p.n })}</span></figcaption><div class="chart" data-k="${p.k}"></div></figure>`; }).join('');
  const c = k => adCurve(k);
  P.forEach(p => {
    const box = $(`.chart[data-k="${p.k}"]`, el), W = adWidth(box, 120), nar = W < 200, H = nar ? 112 : 128;
    const M = { t: 10, r: 8, b: 18, l: 30 };
    const svg = svgEl(box, W, H, t('{name}: שיעור ההצבעה בכל פרסום מול המסלול של 2022', { name: p.name }));
    const x = d3.scaleLinear().domain([7, xMax]).range([M.l, W - M.r]);   // time runs left to right, as on the hourly chart
    const y = d3.scaleLinear().domain([0, yMax]).range([H - M.b, M.t]);
    [0, 0.2, 0.4, 0.6].filter(v => v <= yMax).forEach(v => {
      svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
      svg.append('text').attr('class', 'lbl').attr('x', M.l - 4).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(pct(100 * v, 0));
    });
    (nar ? [10, 16, 22] : [10, 14, 18, 22]).forEach(t => svg.append('text').attr('class', 'lbl').attr('x', x(t)).attr('y', H - 4).attr('text-anchor', 'middle').text(String(t)));
    if (p.t22 != null) {
      const path = d3.range(7, 22.01, 0.25).map(t => [x(t), y(p.t22 * c(t).share)]);
      svg.append('path').attr('d', d3.line()(path)).attr('fill', 'none').attr('stroke', 'var(--muted)').attr('stroke-width', 1.5).attr('stroke-dasharray', '3 3');
      svg.append('circle').attr('cx', x(22)).attr('cy', y(p.t22)).attr('r', 3.5).attr('fill', 'var(--surface)').attr('stroke', 'var(--muted)').attr('stroke-width', 1.5);
    }
    const pts = D.hist.map(e => ({ h: adHour(adRel(e)), m: p.get(e) })).filter(d => d.h != null && d.m && d.m.turnout != null);
    if (!pts.length) return;
    svg.append('path').attr('d', d3.line()([[x(7), y(0)], ...pts.map(d => [x(d.h), y(d.m.turnout)])])).attr('fill', 'none').attr('stroke', 'var(--arab)').attr('stroke-width', 2).attr('stroke-linejoin', 'round');
    svg.selectAll(null).data(pts).join('circle').attr('cx', d => x(d.h)).attr('cy', d => y(d.m.turnout)).attr('r', 4).attr('fill', 'var(--arab)').attr('stroke', 'var(--surface)').attr('stroke-width', 2);
    const lp = pts[pts.length - 1], lx = x(lp.h), ly = y(lp.m.turnout);
    // the last value above the point (below when it is high on the chart), on its left unless that hits the axis labels
    const lt = adP(lp.m.turnout, 0), left = lx - 7 - textWidth(lt, 12.5, 600) > M.l + 2;
    svg.append('text').attr('class', 'lbl-strong halo').style('direction', 'ltr').attr('x', left ? lx - 7 : lx + 7).attr('y', ly - 9 < M.t + 8 ? ly + 16 : ly - 9)
      .attr('text-anchor', left ? 'end' : 'start').text(lt);
    svg.selectAll(null).data(pts).join('circle').attr('cx', d => x(d.h)).attr('cy', d => y(d.m.turnout)).attr('r', 12).attr('fill', 'transparent')
      .call(sel => bindTT(sel, d => `<h4>${esc(p.name)} · ${adHHMM(d.h)}</h4>${ttRows([[t('שיעור הצבעה'), adP(d.m.turnout)], [t('קצב מול 2022'), adP(d.m.pace, 0)],
        ...(p.t22 != null ? [[t('המסלול של 2022 בשעה הזו'), adP(p.t22 * c(d.h).share)], [t('הסוף ב-2022'), adP(p.t22)]] : [])])}`));
  });
}

/* ---------- every locality: a beeswarm of pace ---------- */
function adDodge(items, pad = 1) {
  // places circles along their row: the largest first, each at the smallest offset that clears the ones placed
  const placed = [];
  [...items].sort((a, b) => b.r - a.r).forEach(it => {
    const near = placed.filter(q => Math.abs(q.x - it.x) < q.r + it.r + pad);
    const cands = [0, ...near.flatMap(q => { const d = q.r + it.r + pad, dx = it.x - q.x, dy = Math.sqrt(Math.max(0, d * d - dx * dx)); return [q.y + dy, q.y - dy]; })]
      .sort((a, b) => Math.abs(a) - Math.abs(b));
    it.y = cands.find(y => near.every(q => (q.x - it.x) ** 2 + (q.y - y) ** 2 >= (q.r + it.r + pad) ** 2 - 1e-6)) ?? 0;
    placed.push(it);
  });
  return items;
}
function adSwarm(el, D) {
  const B = AD.base, h = adHour(adRel(D.cur)), f = adCurve(h);
  const rows = adRows(D).filter(r => r.pace != null);
  if (!rows.length) { el.innerHTML = `<p class="empty">${t('אין עדיין נתוני קצב.')}</p>`; return; }
  const W = adWidth(el, 280), nar = W < 560;
  const groups = AD.rows === 'lead'
    ? AD_GROUPS.map(k => ({ k, name: AD_G[k].row, test: r => r.b.leader22 === k }))
    : AD_REGIONS.filter(k => B.regions[k]).map(k => ({ k, name: B.region_names[k], test: r => r.b.region === k }));
  const M = { t: 24, r: nar ? 10 : 150, b: 24, l: 12 };
  // zoomed to the localities' spread (position carries the value, not length); 100% joins once the day is near it
  const pv = rows.map(r => r.pace), fs = f && h >= 10 && f.share < 1 ? f.share : null;
  let lo = Math.max(0, Math.floor((d3.min(pv) - 0.03) * 20) / 20), hi = Math.ceil((Math.max(d3.max(pv), fs || 0) + 0.03) * 20) / 20;
  if (fs != null) lo = Math.min(lo, Math.max(0, Math.floor((fs - 0.05) * 20) / 20));
  hi = Math.min(2, hi > 0.85 ? Math.max(hi, 1.05) : hi);
  const x = d3.scaleLinear().domain([lo, hi]).range([M.l, W - M.r]);
  const rad = d3.scaleSqrt().domain([0, d3.max(B.localities, b => b.elig22)]).range([0, nar ? 10 : 15]);
  let y0 = M.t;
  const lanes = groups.map(g => {
    const items = adDodge(rows.filter(g.test).map(r => ({ r: Math.max(2.2, rad(r.b.elig22)), x: x(r.pace), d: r })), 1);
    const ext = Math.max(12, d3.max(items, it => Math.abs(it.y) + it.r) || 0), lab = nar ? 18 : 0;
    const lane = { g, items, top: y0, cy: y0 + lab + ext + 4, h: lab + 2 * ext + 12 };
    y0 += lane.h; return lane;
  });
  const H = y0 + M.b;
  const svg = svgEl(el, W, H, AD.rows === 'lead' ? t('כל היישובים לפי הקצב מול 2022, לפי הרשימה שהובילה ב-2022') : t('כל היישובים לפי הקצב מול 2022, לפי אזור'));
  x.ticks(nar ? 4 : 8).forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', x(v)).attr('x2', x(v)).attr('y1', M.t - 4).attr('y2', H - M.b);
    const tw = textWidth(pct(100 * v, 0), 11.5) / 2 + 1;   // a tick at the very edge keeps its line, not a cut label
    if (x(v) - tw >= 0 && x(v) + tw <= W - M.r + (nar ? M.r : 0)) svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 6).attr('text-anchor', 'middle').text(pct(100 * v, 0));
  });
  if (hi >= 1) svg.append('line').attr('x1', x(1)).attr('x2', x(1)).attr('y1', M.t - 4).attr('y2', H - M.b).attr('stroke', 'var(--ink-2)').attr('stroke-width', 1.5);
  if (fs != null) {
    const fx = x(fs), txt = nar ? t('הקצב של 2022 בשעה הזו') : t('הקצב שהיה צפוי בשעה הזו לפי 2022'), tw = textWidth(txt, 11.5, 600);
    svg.append('line').attr('class', 'ref-line').attr('x1', fx).attr('x2', fx).attr('y1', M.t - 4).attr('y2', H - M.b);
    // RTL text: 'start' puts its right edge at x; keep the label inside the plot
    const lx = Math.min(W - 2, Math.max(M.l + tw, fx + tw / 2));
    svg.append('text').attr('class', 'ref-text ad-halo').attr('x', lx).attr('y', M.t - 9).attr('text-anchor', 'start').text(txt);
  }
  lanes.forEach((L, i) => {
    if (i) svg.append('line').attr('x1', nar ? 0 : M.l).attr('x2', W).attr('y1', L.top).attr('y2', L.top).attr('stroke', 'var(--rule)');
    const a = adAgg(L.items.map(it => it.d));
    const sub = t('{n} יישובים · קצב {p}', { n: fmt(L.items.length), c: L.items.length, p: adP(a.pace, 0) });
    if (nar) {
      svg.append('text').attr('class', 'lbl-strong ad-halo').attr('x', W - 2).attr('y', L.top + 14).attr('text-anchor', 'start').text(fitLabel(L.g.name, W / 2 - 8, 12.5, 600));
      svg.append('text').attr('class', 'lbl ad-halo').attr('x', 2).attr('y', L.top + 14).attr('text-anchor', 'end').text(sub);   // RTL 'end': left edge at x
    } else {
      svg.append('text').attr('class', 'lbl-strong').attr('x', W - 2).attr('y', L.cy - 4).attr('text-anchor', 'start').text(fitLabel(L.g.name, M.r - 12, 12.5, 600));
      svg.append('text').attr('class', 'lbl').attr('x', W - 2).attr('y', L.cy + 12).attr('text-anchor', 'start').text(sub);
    }
    L.items.forEach(it => { it.cx = it.x; it.cy = L.cy + it.y; });
    svg.append('g').selectAll('circle').data(L.items).join('circle').attr('cx', it => it.cx).attr('cy', it => it.cy).attr('r', it => it.r)
      .attr('fill', it => it.d.b.leader22 === 'other' ? 'var(--surface)' : `var(--ad-${it.d.b.leader22})`)
      .attr('stroke', it => it.d.b.leader22 === 'other' ? 'var(--muted)' : 'var(--surface)').attr('stroke-width', it => it.d.b.leader22 === 'other' ? 1.5 : 1);
  });
  // one hover layer: the nearest locality within reach, so small circles need no pinpoint aim
  const all = lanes.flatMap(L => L.items), dl = d3.Delaunay.from(all, it => it.cx, it => it.cy);
  const ring = svg.append('circle').attr('fill', 'none').attr('stroke', 'var(--ink)').attr('stroke-width', 2).style('display', 'none').style('pointer-events', 'none');
  const hit = svg.append('rect').attr('x', 0).attr('y', 0).attr('width', W).attr('height', H).attr('fill', 'transparent');
  const pick = ev => {
    const [px, py] = d3.pointer(ev.touches ? ev.touches[0] : ev, svg.node());
    const it = all[dl.find(px, py)];
    if (!it || Math.hypot(it.cx - px, it.cy - py) > Math.max(24, it.r + 8)) { ring.style('display', 'none'); tt.hide(); return; }
    ring.style('display', null).attr('cx', it.cx).attr('cy', it.cy).attr('r', it.r + 3);
    tt.show(adTip(it.d, h), ev.touches ? ev.touches[0] : ev);
  };
  hit.on('pointermove', pick).on('pointerdown', pick).on('pointerleave', () => { ring.style('display', 'none'); tt.hide(); });
}

function adTip(r, h) {
  const b = r.b;
  return `<h4>${esc(adName(b))}</h4>${ttRows([[t('הובילה ב-2022'), `${AD_G[b.leader22].short} (+${fmt(100 * b.margin22)})`, b.leader22 === 'other' ? 'var(--muted)' : `var(--ad-${b.leader22})`],
    ...(r.c ? [[t('הצבעה עד {h}', { h: adHHMM(h) }), adP(r.t)], [t('קצב מול 2022'), adP(r.pace, 0)]] : [[t('בפרסום הזה'), t('לא מופיע')]]), [t('הסוף ב-2022'), adP(b.turnout22)], [t('בעלי זכות'), fmt(r.elig)]])}`;
}

/* ---------- every locality on the map: pace by place ---------- */
// Two panels on one scale: the north and centre (Galilee to Jerusalem) and the Negev, which lies far to the south with
// nothing in between; Mercator from the localities' coordinates (arab_day_2022.json lat/lon) over the site's outline.
function adMap(el, D) {
  if (!el) return;
  const key = $('#ad-map-key'), foot = $('#ad-map-foot');
  const rows = adRows(D).filter(r => r.b.lat != null && r.b.lon != null);
  const noPos = AD.base.localities.filter(b => b.lat == null || b.lon == null);
  if (!rows.length || !S.outline) { el.innerHTML = `<p class="empty">${t('אין מיקומים ליישובים.')}</p>`; return; }
  const h = adHour(adRel(D.cur)), W = adWidth(el, 280), gap = 10, pad = 10, SPLIT = 31.6;
  const north = rows.filter(r => r.b.lat >= SPLIT), south = rows.filter(r => r.b.lat < SPLIT);
  const merc = d3.geoMercator().scale(1).translate([0, 0]);
  const box = rs => { const p = rs.map(r => merc([r.b.lon, r.b.lat])); return { x0: d3.min(p, q => q[0]), x1: d3.max(p, q => q[0]), y0: d3.min(p, q => q[1]), y1: d3.max(p, q => q[1]) }; };
  const bn = box(north), bs = south.length ? box(south) : null;
  // one scale k for both panels: north width + Negev width + gap + padding = W
  const wN = bn.x1 - bn.x0, wS = bs ? bs.x1 - bs.x0 : 0;
  const k = (W - 4 * pad - (bs ? gap : 0)) / (wN + wS);
  const pnW = wN * k + 2 * pad, pnH = (bn.y1 - bn.y0) * k + 2 * pad;
  const psW = bs ? wS * k + 2 * pad : 0, psH = bs ? (bs.y1 - bs.y0) * k + 2 * pad : 0;
  const H = Math.ceil(Math.max(pnH, psH));
  // the north panel on the right (east), the Negev at the bottom left (south-west), as on a map
  const panels = [{ name: t('הצפון והמרכז'), rows: north, b: bn, x: W - pnW, y: 0, w: pnW, h: pnH }];
  if (bs) panels.push({ name: t('הנגב'), rows: south, b: bs, x: 0, y: H - psH, w: psW, h: psH });
  const svg = svgEl(el, W, H, t('מפת היישובים הערביים והדרוזיים והקלפיות הערביות של הערים המעורבות, לפי הקצב מול 2022'));
  const rep = rows.filter(r => r.pace != null).map(r => r.pace).sort(d3.ascending);
  const lo = rep.length ? Math.floor(d3.quantile(rep, 0.03) * 20) / 20 : 0, hi = rep.length ? Math.max(lo + 0.05, Math.ceil(d3.quantile(rep, 0.97) * 20) / 20) : 1;
  // the site's turnout ramp (--seq-0 → --seq-1, as on the results map), from a quarter of the way in so that the
  // lowest values still stand off the land in both themes
  const ramp = d3.interpolateLab(cssVar('--seq-0'), cssVar('--seq-1'));
  const col = d3.scaleLinear().domain([lo, hi]).range([ramp(0.28), ramp(1)]).interpolate(d3.interpolateLab).clamp(true);
  const rad = d3.scaleSqrt().domain([0, d3.max(AD.base.localities, b => b.elig22)]).range([0, Math.max(7, Math.min(12, W / 34))]);
  const all = [];
  panels.forEach((P, i) => {
    const proj = d3.geoMercator().scale(k).translate([P.x + pad - P.b.x0 * k, P.y + pad - P.b.y0 * k])
      .clipExtent([[P.x, P.y], [P.x + P.w, P.y + P.h]]);
    const path = d3.geoPath(proj), g = svg.append('g');
    g.append('rect').attr('x', P.x + 0.5).attr('y', P.y + 0.5).attr('width', P.w - 1).attr('height', P.h - 1).attr('rx', 6).attr('fill', 'var(--surface)').attr('stroke', 'var(--rule)');
    g.selectAll(null).data(S.outline.features).join('path').attr('class', 'land').attr('d', path);
    const wb = S.outline.features.find(f => f.properties.id === '275');
    if (wb) g.append('path').attr('class', 'greenline').attr('d', path(wb));
    P.rows.forEach(r => { const [x, y] = proj([r.b.lon, r.b.lat]); all.push({ r, x, y, rr: Math.max(2, rad(r.b.elig22)) }); });
  });
  const dots = [...all].sort((a, b) => b.rr - a.rr);   // the largest first, so a small locality stays visible on top
  svg.append('g').selectAll('circle').data(dots).join('circle').attr('cx', d => d.x).attr('cy', d => d.y).attr('r', d => d.rr)
    .attr('fill', d => d.r.pace != null ? col(d.r.pace) : 'var(--surface)')
    .attr('stroke', d => d.r.pace != null ? 'var(--surface)' : 'var(--muted)').attr('stroke-width', d => d.r.pace != null ? 0.8 : 1.5);
  // each panel's name over the dots, in a corner without localities: the north's top left (the sea; RTL 'end': left
  // edge at x), the Negev's top right ('start': right edge at x)
  panels.forEach((P, i) => svg.append('text').attr('class', 'lbl-strong ad-halo').attr('x', i ? P.x + P.w - 7 : P.x + 7).attr('y', P.y + 16)
    .attr('text-anchor', i ? 'start' : 'end').text(P.name));
  const ring = svg.append('circle').attr('fill', 'none').attr('stroke', 'var(--ink)').attr('stroke-width', 2).style('display', 'none').style('pointer-events', 'none');
  const dl = d3.Delaunay.from(all, d => d.x, d => d.y);
  const pick = ev => {
    const [px, py] = d3.pointer(ev.touches ? ev.touches[0] : ev, svg.node()), d = all[dl.find(px, py)];
    if (!d || Math.hypot(d.x - px, d.y - py) > Math.max(16, d.rr + 6)) { ring.style('display', 'none'); tt.hide(); return; }
    ring.style('display', null).attr('cx', d.x).attr('cy', d.y).attr('r', d.rr + 3);
    tt.show(adTip(d.r, h), ev.touches ? ev.touches[0] : ev);
  };
  svg.append('rect').attr('width', W).attr('height', H).attr('fill', 'transparent')
    .on('pointermove', pick).on('pointerdown', pick).on('pointerleave', () => { ring.style('display', 'none'); tt.hide(); });
  if (key) key.innerHTML = rep.length ? `<span>${t('קצב <span class="num">{p}</span> ומטה', { p: pct(100 * lo, 0) })}</span><span class="ad-map-ramp" style="background:linear-gradient(to left, ${col(lo)}, ${col(hi)})"></span><span>${t('<span class="num">{p}</span> ומעלה', { p: pct(100 * hi, 0) })}</span><span><i class="ad-k-ring"></i>${t('לא בפרסום')}</span>` : '';
  if (foot) foot.textContent = t('הנגב מוצג בחלון נפרד, באותו קנה מידה.') + (noPos.length ? t(' {n} יישובים בדואיים בנגב, רובם שבטים ({e} בעלי זכות ב-2022), רשומים בלי מיקום ואינם על המפה; הם בטבלה.', { n: fmt(noPos.length), c: noPos.length, e: fmt(d3.sum(noPos, b => b.elig22)) }) : '');
}

/* ---------- the locality table ---------- */
function adRows(D) {
  const cur = new Map((D.cur ? D.cur.localities : []).map(l => [l.key, l]));
  const prev = D.prev ? new Map((D.prev.localities || []).map(l => [l.key, l])) : null;
  return AD.base.localities.map(b => {
    const c = cur.get(b.key) || null, p = prev && prev.get(b.key);
    return { b, c, t: c ? c.turnout : null, pace: c ? c.pace : null, on: c && c.on_track != null ? c.on_track : null,
      elig: (c && c.elig) || b.elig22, d: c && p && c.turnout != null && p.turnout != null ? c.turnout - p.turnout : null };
  });
}
const adSize = e => e >= 20000 ? 'l' : e >= 5000 ? 'm' : 's';
function adCols(D) {
  // the reading order: who, how far along now, how that compares; the 2022 facts after. Each column sorts by v.
  const rel = D.cur ? adHHMM(adHour(adRel(D.cur))) : '', prev = D.prev ? adHHMM(adHour(adRel(D.prev))) : '';
  const h = D.cur ? adHour(adRel(D.cur)) : null, f = h != null && h >= 10 ? adCurve(h) : null;
  const top = Math.max(0.8, d3.max(AD.base.localities, b => b.turnout22) || 0), lead = { raam: 0, joint: 1, other: 2 };
  const bar = (v, ref, cls, scale) => v == null ? '' : `<span class="ad-mb ${cls}" aria-hidden="true"><i style="width:${(100 * Math.min(1, v / scale)).toFixed(1)}%"></i>${ref != null ? `<b style="inset-inline-start:${(100 * Math.min(1, ref / scale)).toFixed(1)}%"></b>` : ''}</span>`;
  const cols = [
    { k: 'name', l: t('יישוב'), v: r => adNorm(adName(r.b)), dir: 1, txt: true, cell: (r, on) => `<button type="button" class="ad-star" data-key="${esc(r.b.key)}" aria-pressed="${on}" aria-label="${t('מעקב: {n}', { n: esc(adName(r.b)) })}" title="${on ? t('הסרה מהמעקב') : t('הצמדה לראש הטבלה')}">${AD_STAR}</button>${adNameHTML(r.b)}${r.b.kind === 'druze' ? `<span class="badge">${t('דרוזי')}</span>` : ''}` },
    { k: 'lead', l: t('הובילה ב-2022'), sm: t('הובילה'), v: r => lead[r.b.leader22] * 10 - r.b.margin22, dir: 1, title: t('הרשימה שקיבלה הכי הרבה קולות ב-2022 מבין רע״ם, המשותפת והרשימה הגדולה שאינה ערבית, ובכמה נקודות אחוז הקדימה את הבאה אחריה מבין השלוש'),
      cell: r => `<span class="ad-lead"${r.b.leader22 === 'other' && r.b.top_other22 ? ` title="${esc(r.b.top_other22.name)}"` : ''}><i class="ad-sw ${r.b.leader22 === 'other' ? 'other' : ''}" style="${r.b.leader22 === 'other' ? '' : `background:var(--ad-${r.b.leader22})`}"></i><span class="ad-ln">${AD_G[r.b.leader22].short}</span><span class="muted num">+${fmt(100 * r.b.margin22)}</span></span>` },
    { k: 't', l: t('הצבעה עד {h}', { h: rel }), sm: t('עד {h}', { h: rel }), v: r => r.t, dir: -1, n: true, now: true, title: t('הקו האנכי: הסוף ב-2022'), cell: r => `<span class="num">${adP(r.t)}</span>${bar(r.t, r.b.turnout22, '', top)}` },
    { k: 'pace', l: t('קצב מול 2022'), sm: t('קצב'), v: r => r.pace, dir: -1, n: true, now: true, title: t('המצביעים עד עכשיו כאחוז מהמצביעים באותן קלפיות ב-2022. הקו האנכי: הקצב שהיה צפוי בשעה הזו לפי 2022'),
      cell: r => `<span class="num">${adP(r.pace, 0)}</span>${bar(r.pace, f ? f.share : null, 'pace', 1.2)}` },
    { k: 'd', l: prev ? t('שינוי מ-{h}', { h: prev }) : t('שינוי מהפרסום הקודם'), sm: t('שינוי'), v: r => r.d, dir: -1, n: true, now: true, title: t('נקודות אחוז'), cell: r => `<span class="num">${r.d == null ? '—' : adSigned(100 * r.d)}</span>` },
    { k: 't22', l: t('הסוף ב-2022'), sm: t('סוף 2022'), v: r => r.b.turnout22, dir: -1, n: true, cell: r => adP(r.b.turnout22) },
    { k: 'elig', l: t('בעלי זכות'), v: r => r.elig, dir: -1, n: true, cell: r => fmt(r.elig) },
    { k: 'region', l: t('אזור'), v: r => AD_REGIONS.indexOf(r.b.region), dir: 1, cls: 'hide-sm', cell: r => esc(AD.base.region_names[r.b.region] || '') },
  ];
  return D.cur ? cols : cols.filter(c => !c.now);   // before the first release only the 2022 columns
}
function adTableCard(D, tag) {
  const B = AD.base, cols = adCols(D);
  const opt = (id, label, list, val) => `<select id="${id}" aria-label="${label}">${list.map(([v, l]) => `<option value="${esc(v)}"${String(v) === String(val) ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  return `<div class="card c12">
    <h3>${t('יישוב אחר יישוב')}${tag}</h3>
    <p class="sub">${D.cur ? t('הקצב: המצביעים עד שעת הפרסום כאחוז מהמצביעים באותן קלפיות ב-2022.') : D.mode === 'wait' && !adClosed() ? t('נתוני 2022 של כל יישוב; בכל פרסום יתווספו שיעור ההצבעה, הקצב והשינוי מהפרסום הקודם.') : t('נתוני 2022 של כל יישוב.')} ${t('יישובים במעקב (כוכבית) מוצמדים לראש הטבלה; ברירת המחדל היא עשרת היישובים הגדולים, והבחירה נשמרת בדפדפן הזה. לחיצה על כותרת עמודה ממיינת לפיה.')}</p>
    <div class="controls ad-ctl">
      <input type="search" id="ad-q" placeholder="${t('חיפוש יישוב')}" aria-label="${t('חיפוש יישוב')}" value="${esc(AD.q)}" autocomplete="off">
      <span class="ctl-label" id="ad-lead-l">${t('הובילה ב-2022')}</span>
      <div class="seg" role="group" aria-labelledby="ad-lead-l" id="ad-lead">${[['all', t('הכל')], ['raam', t('רע״ם')], ['joint', t('המשותפת')], ['other', t('אחרת')]].map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${AD.lead === v}">${l}</button>`).join('')}</div>
      ${opt('ad-region', t('אזור'), [['all', t('כל האזורים')], ...AD_REGIONS.filter(k => B.regions[k]).map(k => [k, B.region_names[k]])], AD.region)}
      ${opt('ad-kind', t('סוג'), [['all', t('כל הסוגים')], ...Object.keys(B.kind_names || {}).map(k => [k, B.kind_names[k]])], AD.kind)}
      ${opt('ad-size', t('גודל'), AD_SIZES, AD.size)}
      <label class="toggle"><input type="checkbox" id="ad-watch-only"${AD.watchOnly ? ' checked' : ''}>${t('רק במעקב')}</label>
    </div>
    <p class="ad-count" id="ad-count" aria-live="polite"></p>
    <div class="tbl-wrap scroll-y ad-scroll"><table class="t sticky1 ad-tbl">
      <caption class="ad-sr">${D.cur ? t('שיעור ההצבעה לפי יישוב, הפרסום של {h}, מול 2022', { h: adHHMM(adHour(adRel(D.cur))) }) : t('שיעור ההצבעה לפי יישוב, מול 2022')}</caption>
      <thead><tr>${cols.map(c => `<th${c.n ? ' class="n"' : c.cls ? ` class="${c.cls}"` : ''} aria-sort="none" data-k="${c.k}"${c.title ? ` title="${esc(c.title)}"` : ''}><button type="button" class="ad-sort" data-k="${c.k}">${c.sm ? `<span class="hide-sm">${esc(c.l)}</span><span class="ad-sm-only">${esc(c.sm)}</span>` : esc(c.l)}<i aria-hidden="true"></i></button></th>`).join('')}</tr></thead>
      <tbody id="ad-tbody"></tbody></table></div>
    <p class="foot">${D.cur ? t('יישוב שאינו מופיע בפרסום מסומן בקו. ') : ''}${D.mode === 'live' && !D.prev ? (D.hist.length > 1 ? t('השינוי מהפרסום הקודם מוצג מהפרסום השני שהדף הזה ראה. ') : t('השינוי מהפרסום הקודם יוצג מהפרסום השני. ')) : ''}${t('ההובלה ב-2022: הגדולה ביישוב מבין רע״ם, המשותפת (חד״ש-תע״ל ובל״ד יחד) והרשימה הגדולה שאינה ערבית, והפער שלה מהבאה אחריה מבין השלוש, בנקודות אחוז. הקלפיות הערביות בערים מעורבות מזוהות לפי ההצבעה בהן ב-2022.')}</p>
  </div>`;
}
function adTableBody(el) {
  const tb = $('#ad-tbody', el); if (!tb || !AD.D) return;
  const D = AD.D, cols = adCols(D), col = cols.find(c => c.k === AD.sort.k) || cols.find(c => c.k === 'elig');
  const q = adNorm(AD.q);
  const rows = adRows(D).filter(r => (AD.lead === 'all' || r.b.leader22 === AD.lead) && (AD.region === 'all' || r.b.region === AD.region)
    && (AD.kind === 'all' || r.b.kind === AD.kind) && (AD.size === 'all' || adSize(r.b.elig22) === AD.size)
    && (!AD.watchOnly || AD.watch.has(r.b.key)) && (!q || adNorm(r.b.name).includes(q) || adNorm(r.b.city).includes(q) || (r.b.name_he != null && adNorm(r.b.name_he).includes(q))));
  const dir = AD.sort.dir, w = r => AD.watch.has(r.b.key) ? 1 : 0;
  rows.sort((a, b) => {
    if (w(a) !== w(b)) return w(b) - w(a);
    const va = col.v(a), vb = col.v(b);
    if (va == null || vb == null) return va == null && vb == null ? 0 : va == null ? 1 : -1;   // empty cells last, either way
    return (col.txt ? va.localeCompare(vb, AR_ON ? 'ar' : 'he') : va - vb) * dir || b.b.elig22 - a.b.elig22;
  });
  const nPin = rows.filter(r => w(r)).length;
  tb.innerHTML = rows.map((r, i) => {
    const on = w(r) === 1;
    return `<tr class="${on ? 'hl' : ''}${on && i === nPin - 1 && nPin < rows.length ? ' ad-pin-last' : ''}">${cols.map(c => `<td${c.n ? ' class="n"' : c.cls ? ` class="${c.cls}"` : ''}>${c.cell(r, on)}</td>`).join('')}</tr>`;
  }).join('') || `<tr><td colspan="${cols.length}" class="muted">${t('אין יישובים שמתאימים לסינון.')}</td></tr>`;
  $$('th[data-k]', el).forEach(th => {
    const on = th.dataset.k === AD.sort.k;
    th.setAttribute('aria-sort', on ? (AD.sort.dir > 0 ? 'ascending' : 'descending') : 'none');
    const i = $('i', th); if (i) i.textContent = on ? (AD.sort.dir > 0 ? '▲' : '▼') : '▼';
  });
  const cnt = $('#ad-count', el);
  if (cnt) cnt.textContent = t('מוצגים {n} מתוך {m} יישובים', { n: fmt(rows.length), m: fmt(AD.base.localities.length) }) + (AD.watch.size ? t(' · {w} במעקב', { w: fmt(AD.watch.size) }) : '');
}

function adBind(el) {
  const redraw = () => { el.dataset.adSig = ''; drawArabDay(el); };
  onSeg(el, 'ad-rel', v => { AD.sel = +v; redraw(); });
  onSeg(el, 'ad-rows', v => { AD.rows = v; if (AD.D && AD.D.cur) adSwarm($('#ad-swarm', el), AD.D); });
  onSeg(el, 'ad-lead', v => { AD.lead = v; adTableBody(el); });
  const sel = (id, k) => { const s = $('#' + id, el); if (s) s.addEventListener('change', () => { AD[k] = s.value; adTableBody(el); }); };
  sel('ad-region', 'region'); sel('ad-kind', 'kind'); sel('ad-size', 'size');
  const wo = $('#ad-watch-only', el); if (wo) wo.addEventListener('change', () => { AD.watchOnly = wo.checked; adTableBody(el); });
  const q = $('#ad-q', el);
  // the text is kept at once (a redraw in between restores it); only the table waits for a pause in typing
  if (q) { let tm; q.addEventListener('input', () => { AD.q = q.value; clearTimeout(tm); tm = setTimeout(() => { if (q.isConnected) adTableBody(el); }, 120); }); }
  $$('.ad-sort', el).forEach(b => b.addEventListener('click', () => {
    const c = adCols(AD.D).find(x => x.k === b.dataset.k);
    AD.sort = AD.sort.k === c.k ? { k: c.k, dir: -AD.sort.dir } : { k: c.k, dir: c.dir };
    adTableBody(el);
    const nb = $(`.ad-sort[data-k="${c.k}"]`, el); if (nb) nb.focus();
  }));
  const tb = $('#ad-tbody', el);
  if (tb) tb.addEventListener('click', e => {
    const b = e.target.closest('.ad-star'); if (!b) return;
    const k = b.dataset.key;
    if (AD.watch.has(k)) AD.watch.delete(k); else AD.watch.add(k);
    adStore.set('arabWatch', [...AD.watch]);
    adTableBody(el);
    const nb = $(`.ad-star[data-key="${CSS.escape(k)}"]`, el); if (nb) nb.focus();
  });
}
