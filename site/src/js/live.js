/* ===================== election day & night ===================== */
// Live mode reads live/*.json written next to the page by the election-night fetcher
// (pipeline/live_fetch.py, run by .github/workflows/live.yml): status.json (the pass), results.json (the
// CEC file, projected), turnout.json (the day), exit_polls.json (from 22:00). Without a feed (the artifact,
// or before election day) the tab replays election night 2021 in the real counting order, and 2022 in a
// simulated one, from the official ballot results.
const SECTOR_NAME = { arab: 'יישובים ערביים', druze: 'יישובים דרוזיים', mixed: 'ערים מעורבות', haredi: 'יישובים חרדיים', jewish: 'שאר היישובים' };
// The daytime release is classified box by box (live_fetch.station_sector: Haredi boxes, Arab boxes in mixed
// cities and Jewish localities), the night projection locality by locality, so the two tables need their own labels.
const DAY_SECTOR_NAME = { arab: 'יישובים ערביים', druze: 'יישובים דרוזיים', mixed: 'קלפיות ערביות בערים מעורבות וביישובים יהודיים', haredi: 'קלפיות חרדיות', jewish: 'שאר הקלפיות' };
const SECTOR_ORDER = ['jewish', 'haredi', 'mixed', 'druze', 'arab'];
const LIVE_POLL_MS = 60000;
S.liveIdx = null; S.livePlay = null;
const pollsClosed = () => ilStamp(ilNow()) >= POLLS_CLOSE;
const hhmm = t => `${String(t.h).padStart(2, '0')}:${String(t.min).padStart(2, '0')}`;
const heList = a => a.length > 1 ? a.slice(0, -1).join(', ') + ' ו' + a[a.length - 1] : a[0] || '';

async function fetchLive(name) {
  // live data exists only on the hosted site during election day and night. The 30-second bucket in the
  // query gets past the Pages CDN cache (max-age 600) without a fresh origin hit on every tick.
  try {
    const r = await fetch(`live/${name}?v=${Math.floor(Date.now() / 30000)}`, { cache: 'no-store' });
    if (!r.ok) return { ok: false, status: r.status };
    // a host that answers a missing file with an HTML page means there is no feed, not a lost connection
    try { return { ok: true, data: await r.json() }; } catch (e) { return { ok: false, status: 404 }; }
  } catch (e) { return { ok: false, status: 0 }; }   // network error
}
async function replayDoc() {
  if (!S.replayDoc) {
    const doc = await fetchJSON('data/replay_night.json');
    if (!doc.replays) {   // older single-replay format
      doc.replays = { [doc.election || 'K25']: { ...doc, simulated_order: doc.simulated_order !== false } };
      doc.default = doc.election || 'K25';
    }
    S.replayDoc = doc;
  }
  return S.replayDoc;
}
// Nothing from the CEC file may be shown before the polls close: a results.json that is not a drill is
// ignored until 27.10 22:00 whatever the feed says or which election it names (client side of OPS-2).
const earlyResults = R => R && !R.drill && !pollsClosed();
// 2026 exit polls are shown only after the polls close (the feed withholds them too), except in a drill.
const exitHidden = () => !pollsClosed() && !((S.liveStatus || {}).drill || (S.live || {}).drill);

async function loadLive() {
  // status.json always exists on the hosted site (a placeholder before election day), so only real feeds
  // are requested; without it (404) the tab is a demo.
  const st = await fetchLive('status.json');
  if (!st.ok && ![403, 404, 410].includes(st.status)) {
    // a failed status fetch keeps the last good data; refreshBars() shows a quiet connection note
    if (!S.liveConn) S.liveConn = { since: ilNow() };
    if (S.live) return S.live;
  } else S.liveConn = null;
  const status = st.ok ? st.data : null;
  S.liveStatus = status;
  const [res, turnout, history, exits] = await Promise.all([
    status && status.has_results ? fetchLive('results.json') : null,
    status && status.has_turnout ? fetchLive('turnout.json') : null,
    S.turnoutHistory ? Promise.resolve(S.turnoutHistory) : fetchJSON('data/turnout_history.json'),
    status && status.exit_polls ? fetchLive('exit_polls.json') : null]);
  S.turnoutHistory = history;
  // a file that fails to load keeps its previous copy; one the feed no longer lists is dropped
  if (!turnout) S.liveTurnout = null; else if (turnout.ok) S.liveTurnout = turnout.data;
  if (!exits) S.liveExit = null; else if (exits.ok) S.liveExit = exits.data;
  let R = res && res.ok ? res.data : null;
  if (res && !res.ok && S.live && S.live.mode === 'live') R = S.live;
  if (R && R.frame && !earlyResults(R)) {
    // the replay file also carries the real 2021 track used for the coverage note (cached after the first load)
    try { const d = await replayDoc(); R = { ...R, accuracy: R.accuracy || d.accuracy, accuracy_real: R.accuracy_real || d.accuracy_real, accuracy_note: R.accuracy_note || d.accuracy_note }; } catch (e) { /* no backtest card */ }
    return { ...R, mode: 'live' };
  }
  const doc = await replayDoc();
  if (!S.replayKey || !doc.replays[S.replayKey]) S.replayKey = doc.default;
  return { ...doc, mode: 'demo' };
}
// What a refresh tick has to redraw for: the mode, the data itself and the clock gates; not the fetcher's own
// pass time, which changes every minute and only moves the 'נבדק' text.
function liveSig() {
  const L = S.live || {}, T = S.liveTurnout || {}, X = S.liveExit || {};
  return JSON.stringify([L.mode, L.updated_at, L.drill, L.frame && L.frame.paused, T.national, T.released, T.source, T.source_url, T.sectors,
    T.lean, T.claims, T.sectors_time, X.polls, !!S.liveConn, votingHours(), inElectionWindow(), pollsClosed()]);
}

async function renderLive() {
  const root = $('#tab-live');
  if (!S.live) S.live = await loadLive();
  const L = S.live, demo = L.mode === 'demo';
  const R0 = demo ? L.replays[S.replayKey] : null;
  const waiting = demo && inElectionWindow();   // election day before the first results file: no replay
  if (demo && (S.liveIdx == null || S.liveIdx >= R0.frames.length)) S.liveIdx = Math.min(R0.simulated_order ? 5 : 6, R0.frames.length - 1);
  const exit26 = waiting && S.liveExit && (S.liveExit.polls || []).length && !exitHidden() ? exitTable(S.liveExit, null) : '';
  root.innerHTML = `
  <div class="section-head"><div>
    <span class="eyebrow">יום הבחירות · יום שלישי, 27 באוקטובר 2026 · הקלפיות פתוחות 07:00–22:00</span>
    <h2>יום הבחירות, בזמן אמת</h2>
    <p>במהלך היום: שיעור ההצבעה הרשמי של ועדת הבחירות, מול אותה שעה בבחירות הקודמות, ולראשונה גם לפי קלפי. מ-22:00: ספירת הקולות קלפי אחר קלפי, ותחזית לסיום הספירה שמשווה כל יישוב שנספר לתוצאה שלו ב-2022. התחזית אינה תוצאה רשמית.</p>
  </div></div>
  <p class="lv-notes" id="lv-notes" hidden></p>
  ${dayMarkup()}
  <h2 class="lv-h2">ליל הבחירות: ספירת הקולות</h2>
  ${waiting ? `<div class="card c12 lv-wait"><h3>${!pollsClosed() ? 'הספירה תתחיל אחרי סגירת הקלפיות, ב-22:00' : 'ממתינים לתוצאות הראשונות של ועדת הבחירות'}</h3>
    <p class="sub">ההדגמה של לילות הבחירות הקודמים מוסתרת ביום הבחירות. מדגמי הטלוויזיה מתפרסמים ב-22:00. ב-2021 הגרסה הראשונה של קובץ הקלפיות הרשמי שהכילה נתונים הופיעה ב-01:01, כשלוש שעות אחרי סגירת הקלפיות (הגרסה שלפניה, מ-23:37, הייתה ריקה); כמחצית הקולות נספרו עד 04:00–05:00 וכ-97% עד שעות הבוקר המאוחרות. המעטפות הכפולות נספרות מהלילה שאחרי, והתוצאה הסופית מתפרסמת ביום חמישי.</p></div>
    ${exit26 ? `<div class="card c12" id="lv-exit26"><h3>המדגמים של 22:00</h3>
    <p class="sub">המדגמים של ערוצי הטלוויזיה כפי שפורסמו. מדגם הוא סקר של מצביעים ביציאה מהקלפי, לא ספירה: ב-2021 וב-2022 הזיזו המדגמים 5–8 מנדטים בין רשימות וטעו בגוש ב-1–3 מנדטים. התחזית מהספירה תופיע כשיגיע הקובץ הראשון של ועדת הבחירות.</p>
    ${exit26}</div>` : ''}` : ''}
  <div ${waiting ? 'hidden' : ''}>
  <div class="live-bar ${demo ? 'demo' : 'on'}">
    ${demo ? `<span class="live-chip demo">הדגמה</span><span class="live-text">${R0.simulated_order
        ? 'ליל הבחירות 2022, משוחזר מתוצאות הקלפיות הרשמיות <b>בסדר ספירה מדומה</b>.'
        : 'ליל הבחירות 2021, <b>בסדר הספירה האמיתי</b>: הגרסאות של קובץ הקלפיות הרשמי כפי שהתעדכן במהלך הלילה.'} ב-27 באוקטובר יוצגו כאן נתוני הספירה החיים.</span>
      ${seg('lv-replay', Object.entries(L.replays).map(([k, r]) => [k, k === 'K24' ? '2021 · סדר אמיתי' : '2022 · סדר מדומה']), S.replayKey)}
      <span class="live-ctl"><button type="button" class="slip" id="lv-play" aria-label="הפעלה">▶ הפעלה</button>
      <input type="range" id="lv-step" dir="ltr" min="0" max="${R0.frames.length - 1}" step="1" value="${S.liveIdx}" aria-label="שלב בספירה">
      <b class="num lv-when" id="lv-when" aria-live="polite"></b></span>`
    : `${L.drill ? '<span class="live-chip demo">תרגול</span>' : '<span class="live-chip on">חי</span>'}<span class="live-text">${L.drill ? 'תרגול על קובץ 2022. ' : ''}<span id="lv-upd">${updatedLine('results')}</span>. מקור: <a href="${esc(L.source_url || '#')}" target="_blank" rel="noopener" dir="ltr">${esc(L.source_label || 'ועדת הבחירות המרכזית')}</a>. <span class="lv-cad">${cadence()}</span>; השעה היא שעת הנתונים.</span>`}
  </div>
  <div class="grid">
    <div class="card c12" id="lv-progress-card"></div>
    <div class="card c7">
      <div class="card-head"><div><h3 id="lv-seats-h">תחזית המנדטים לסיום הספירה</h3>
      <p class="sub" id="lv-seats-sub"></p></div></div>
      <div class="chart" id="lv-seats"></div>
    </div>
    <div class="card c5">
      <h3>המרוץ ל-61</h3>
      <p class="sub">${demo || L.drill ? 'המנדטים הצפויים לכל גוש.' : 'המנדטים הצפויים לכל גוש, לפי השיוך שבמחשבון הקואליציות.'}</p>
      <div id="lv-blocs"></div>
      <h3 style="margin-top:18px">אחוז החסימה</h3>
      <p class="sub">רשימות שעשויות להיות בצד הלא נכון של 3.25%.</p>
      <div id="lv-thr" class="tbl-wrap"></div>
    </div>
    <div class="card c12" id="lv-exit-card" hidden>
      <h3>המדגמים מול הספירה</h3>
      <p class="sub">המדגמים של ערוצי הטלוויזיה (פורסמו ב-22:00) לעומת התחזית לסיום הספירה. מדגם הוא סקר של מצביעים ביציאה מהקלפי, לא ספירה.</p>
      <div id="lv-exit"></div>
    </div>
    <div class="card c6">
      <h3>השתתפות בקלפיות שנספרו</h3>
      <p class="sub">שיעור ההצבעה בקלפיות שכבר נספרו, מול שיעור ההצבעה באותם יישובים בבחירות הקודמות. ${S.liveTurnout && S.liveTurnout.sectors
        ? 'בניגוד לפרסומי היום, זה נתון מהספירה עצמה.' : 'זה הנתון הרשמי הראשון מהספירה עצמה על ההשתתפות בחברה הערבית.'}</p>
      <div class="chart" id="lv-turnout"></div>
    </div>
    <div class="card c6">
      <h3>כמה לסמוך על התחזית</h3>
      <p class="sub">בדיקה לאחור: אותו מודל הורץ על ליל הבחירות 2021 בסדר הספירה האמיתי, ועל 2022 ו-2021 בחמישה סדרי ספירה מדומים (כולל סדר שבו היישובים הערביים והחרדיים נספרים אחרונים).</p>
      <div class="chart" id="lv-acc"></div>
    </div>
  </div>
  </div>
  <p class="foot">${demo && !waiting ? esc(R0.note || '') + ' ' : ''}השיטה: אמידה יחסית לפי שכבות (מגזר, אזור והצבעה קודמת), עם נקודת מוצא מממוצע הסקרים, וחלוקת מנדטים בבדר-עופר עם הסכמי העודפים. פירוט בלשונית "שיטה ומקורות".</p>`;
  drawDay();
  if (!waiting) drawLiveFrame();
  $$('#lv-exit26 .lv-scroll', root).forEach(scrollHint);
  refreshBars();
  drawArab();
  S.liveSigDrawn = liveSig();
  if (demo) {
    const step = $('#lv-step'), play = $('#lv-play');
    onSeg(root, 'lv-replay', v => { S.replayKey = v; S.liveIdx = null; stopPlay(); renderLive(); });
    step.addEventListener('input', () => { S.liveIdx = +step.value; stopPlay(); drawLiveFrame(); });
    play.addEventListener('click', () => {
      if (S.livePlay) { stopPlay(); return; }
      if (S.liveIdx >= R0.frames.length - 1) S.liveIdx = 0;
      play.textContent = '❚❚ עצירה'; play.setAttribute('aria-label', 'עצירה');
      S.livePlay = setInterval(() => {
        S.liveIdx = Math.min(R0.frames.length - 1, S.liveIdx + 1); step.value = S.liveIdx; drawLiveFrame();
        if (S.liveIdx >= R0.frames.length - 1) stopPlay();
      }, 1400);
    });
  }
  // One refresh timer in every mode: the day figures, the 22:00 switch from demo to live and the count all
  // arrive without a reload while the tab is open.
  if (!S.liveTimer) S.liveTimer = setInterval(liveTick, LIVE_POLL_MS);
}
async function liveTick() {
  if (S.tab !== 'live' || S.liveBusy || !S.live) return;
  S.liveBusy = true;
  try {
    const d = await loadLive();
    const switched = d.mode !== S.live.mode;
    S.live = d;
    if (switched) { S.liveIdx = null; stopPlay(); renderLive(); return; }
    if (liveSig() !== S.liveSigDrawn) {   // the data or a clock gate changed since the last draw
      if (d.mode === 'live') { drawLiveFrame(); drawDay(); S.liveSigDrawn = liveSig(); }
      else if (inElectionWindow()) { renderLive(); return; }   // the waiting card, the day cards and the 2026 exit polls
      else { drawDay(); S.liveSigDrawn = liveSig(); }
    }
    refreshBars();
    drawArab();
  } catch (e) { /* keep the last data */ } finally { S.liveBusy = false; }
}
function stopPlay() {
  clearInterval(S.livePlay); S.livePlay = null;
  const b = $('#lv-play'); if (b) { b.textContent = '▶ הפעלה'; b.setAttribute('aria-label', 'הפעלה'); }
}
function liveFrame() { const L = S.live; return L.mode === 'demo' ? L.replays[S.replayKey].frames[S.liveIdx] : L.frame; }
// The Arab-society section of the day (arab_day.js) draws into #lv-arab after every render and refresh tick,
// from S.liveTurnout.arab / arab_history or its own demo; a failure there must not take the tab down.
function drawArab() {
  if (typeof drawArabDay !== 'function') return;
  try { const r = drawArabDay(document.getElementById('lv-arab')); if (r && r.catch) r.catch(e => console.error(e)); } catch (e) { console.error(e); }
}

/* ---------- freshness: 'עודכן' is the data time, 'נבדק' the fetcher's last pass ---------- */
function updatedLine(kind) {
  // results.updated_he: when the CEC file last changed; turnout.updated_he: the pass that published the figure
  const st = S.liveStatus || {};
  const data = kind === 'results' ? (S.live || {}).updated_he : (S.liveTurnout || {}).updated_he;
  return `עודכן ${data || '—'}${st.updated_he && st.updated_he !== data ? ` · נבדק ${st.updated_he}` : ''}`;
}
// The feed publishes into main at most every publish_every_min (8) minutes in branch mode (ARCH_V3), so the page
// changes every few minutes; with the Actions path a change reaches it within a minute or two.
function cadence() {
  const st = S.liveStatus || {};
  const fewMin = st.publish_mode ? st.publish_mode !== 'actions' : !(+st.heartbeat_s > 0 && +st.heartbeat_s <= 300);
  return fewMin ? 'הדף מתעדכן כל כמה דקות' : 'הדף בודק עדכון כל דקה';
}
function feedNotes() {
  // quiet notes above the day bar for readers: a lost connection, a feed that stopped, the CEC file not there yet.
  // The fetcher's own diagnostics (probe codes, raw errors) only with '#live-ops' in the address (PAGE-5).
  const st = S.liveStatus || {}, out = [], errs = (st.errors || []).map(String);
  const age = st.updated_at ? Math.round((Date.now() - Date.parse(st.updated_at)) / 60000) : null;
  const ago = m => m > 2880 ? `${fmt(Math.round(m / 1440))} ימים` : m > 120 ? `${fmt(Math.round(m / 60))} שעות` : `${fmt(m)} דקות`;
  // status.json is re-stamped every heartbeat_s (480 s in branch mode, where it is also published only that often)
  // and a Pages build adds a few minutes, so a feed counts as stopped after two missed heartbeats (PAGE-1)
  const beat = (+st.heartbeat_s > 0 ? +st.heartbeat_s : 300) / 60;
  if (S.liveConn) out.push(`<span class="lv-warn">אין חיבור לעדכונים מאז ${hhmm(S.liveConn.since)}${S.liveStatus ? '; מוצגים הנתונים האחרונים שהתקבלו' : ''}.</span>`);
  else if (inElectionWindow() && age != null && age > 2 * beat + 3) out.push(`<span class="lv-warn">העדכון האחרון מהמערכת התקבל ב-${esc(st.updated_he || '')} (לפני ${ago(age)}).</span>`);
  const resErr = errs.find(e => /^results:/.test(e));
  if (pollsClosed() && st.results_state === 'waiting' && resErr) {
    out.push(S.live && S.live.mode === 'live' ? 'הבדיקה האחרונה של קובץ ועדת הבחירות לא הצליחה; מוצגים הנתונים האחרונים שהתקבלו.'
      : /\b40[34]\b/.test(resErr) ? 'קובץ התוצאות של ועדת הבחירות עדיין לא פורסם.'
      : 'קובץ התוצאות של ועדת הבחירות עדיין ריק או שאי אפשר לקרוא אותו; הספירה תוצג עם הקובץ התקין הראשון.');
  }
  if (st.pages_source === 'legacy') out.push(S.ops ? '<span class="lv-ops">pages_source=legacy בלי publish_mode=branch: הפיד מפרסם לענף live-data, והאתר מוגש מהענף main; הנתונים החיים לא יגיעו לדף.</span>'
    : 'ייתכן שהנתונים כאן אינם העדכניים: הגדרת הפרסום של האתר אינה תואמת את הפיד.');
  if (S.ops) {
    const T = S.liveTurnout || {}, ops = [`publish_mode=${esc(st.publish_mode || '—')}, heartbeat_s=${esc(st.heartbeat_s ?? '—')}, results_state=${esc(st.results_state || '—')}, נבדק ${esc(st.checked_he || st.updated_he || '—')}${st.data_he ? `, נתונים ${esc(st.data_he)}` : ''}`];
    if (st.results_probe && st.results_probe.http != null) ops.push(`בדיקת קובץ התוצאות באתר הוועדה: HTTP ${esc(st.results_probe.http)} ב-${esc(st.results_probe.at_he || '')}`);
    if (T.station_error) ops.push(`קלפיות: ${esc(String(T.station_error).slice(0, 160))}`);
    errs.forEach(e => ops.push(esc(e.slice(0, 200))));
    out.push(`<span class="lv-ops">${ops.map(x => `<bdi>${x}</bdi>`).join('')}</span>`);
  }
  return out.join(' ');
}
function refreshBars() {
  const u1 = $('#lv-upd'), u2 = $('#dy-upd'), n = $('#lv-notes');
  if (u1) u1.textContent = updatedLine('results');
  if (u2) u2.textContent = updatedLine('turnout');
  $$('#tab-live .lv-cad').forEach(e => { e.textContent = cadence(); });
  if (n) { const h = feedNotes(); n.hidden = !h; n.innerHTML = h; }
  const ban = $('#ban-note'); if (ban && !ban.hidden && !inPollBan()) ban.hidden = true;   // the ban ends at 22:00 while the tab is open
}

/* ---------- the count ---------- */
// While the operator pauses the projection every drawer gets a counted-only frame: seats by the votes counted
// so far, no ranges, no chances.
function countedOnly(F) {
  const lists = F.lists.map(l => ({ ...l, seats: l.seats_counted, lo: l.seats_counted, hi: l.seats_counted, p_pass: null, votes_proj: null, pct_proj: null }));
  const blocs = {};
  ['coal', 'opp', 'arab'].forEach(b => { const s = sum(lists.filter(l => l.bloc === b).map(l => l.seats)); blocs[b] = { seats: s, lo: s, hi: s, p61: null }; });
  return { ...F, lists, blocs };
}
function drawLiveFrame() {
  const F0 = liveFrame(); if (!F0) return;
  const F = F0.paused ? countedOnly(F0) : F0;
  const when = $('#lv-when'); if (when) when.textContent = F.label || '';
  const h = $('#lv-seats-h'), sub = $('#lv-seats-sub');
  if (h) h.textContent = F.paused ? 'המנדטים לפי הקולות שנספרו' : 'תחזית המנדטים לסיום הספירה';
  if (sub) sub.textContent = F.paused ? 'התחזית מושהית. הפס: המנדטים לפי הקולות שנספרו עד עכשיו בלבד, בלי אומדן למה שטרם נספר.'
    : `הפס: המנדטים הצפויים; הקו הדק: הטווח שהמודל מסמן כ-80%; המעוין: המנדטים לפי הקולות שנספרו עד עכשיו בלבד. ${coverageNote(F.counted.share)}`;
  drawLiveProgress($('#lv-progress-card'), F);
  drawLiveSeats($('#lv-seats'), F);
  drawLiveBlocs($('#lv-blocs'), F);
  drawLiveThreshold($('#lv-thr'), F);
  drawLiveTurnout($('#lv-turnout'), F);
  drawLiveAccuracy($('#lv-acc'), F);
  drawExitPolls(F);
}
// What the model's 80% band did in the backtests at a similar stage of the count: the realised coverage, so
// the band is not read as calibrated.
const nearestPt = (arr, share) => (arr || []).filter(a => a.counted < 0.995 && !a.envelopes)
  .reduce((b, a) => !b || Math.abs(a.counted - share) < Math.abs(b.counted - share) ? a : b, null);
function coverageAt(share) {
  const A = S.live.accuracy || {}, sets = Array.isArray(A) ? { K25: A } : A;
  return { K25: nearestPt(sets.K25, share), K24: nearestPt(sets.K24, share), real: nearestPt(S.live.accuracy_real, share) };
}
function coverageNote(share) {
  const c = coverageAt(share), parts = [];
  if (c.K25) parts.push(`ב-${pct(100 * c.K25.cover80, 0)} מהרשימות (2022, סדר מדומה)`);
  if (c.K24) parts.push(`ב-${pct(100 * c.K24.cover80, 0)} (2021, סדר מדומה)`);
  if (c.real) parts.push(`ב-${pct(100 * c.real.cover80, 0)} (2021, סדר הספירה האמיתי)`);
  return parts.length ? `בבדיקות לאחור, בשלב דומה של הספירה, הטווח כלל את התוצאה הסופית ${heList(parts)}.` : '';
}
// the coalition band along the real 2021 order: share of the night's frames whose band held the final bloc
function realBlocCover() {
  const R = S.replayDoc && S.replayDoc.replays && S.replayDoc.replays.K24;
  if (!R || R.simulated_order) return null;
  const fr = R.frames.filter(f => !f.counted.envelopes && f.counted.share < 0.995), last = R.frames[R.frames.length - 1];
  if (!fr.length || !last.final) return null;
  const finalCoal = sum(last.lists.filter(l => l.bloc === 'coal').map(l => last.final[l.id] || 0));
  return fr.filter(f => f.blocs.coal.lo <= finalCoal && finalCoal <= f.blocs.coal.hi).length / fr.length;
}
// Chances come from 200 bootstrap draws: the extremes are capped and, early in the count, rounded to 5%.
function pPass(p, share) {
  if (p == null) return '—';
  if (p >= 0.995) return '>99%';
  if (p <= 0.005) return '<1%';
  // cap on the raw chance first, then keep the rounded value inside the step (0.976 early is 95%, not >99%)
  const step = share < 0.5 ? 5 : 1;
  return pct(Math.min(100 - step, Math.max(step, Math.round(100 * p / step) * step)), 0);
}

function exitTable(E, F, past = false) {
  // F: the current frame; null before the first results file, when the 2026 lists come from the poll data
  const seatOf = (p, l) => p.seats[l.id] ?? p.seats[l.letters] ?? 0;
  let lists;
  if (F) lists = F.lists.filter(l => l.seats > 0 || E.polls.some(p => seatOf(p, l) > 0));
  else {
    lists = S.polls.parties.map(p => ({ id: p.letters, letters: p.letters, name: p.name, color: p.color, dark: p.dark }));
    const known = new Set(lists.map(l => l.letters));
    E.polls.forEach(p => Object.keys(p.seats || {}).forEach(k => { if (!known.has(k)) { known.add(k); lists.push({ id: k, letters: k, name: k, color: 'var(--muted)', dark: 'var(--muted)' }); } }));
    lists = lists.filter(l => E.polls.some(p => seatOf(p, l) > 0)).sort((a, b) => d3.mean(E.polls, p => seatOf(p, b)) - d3.mean(E.polls, p => seatOf(p, a)));
  }
  const final = F && (F.final || E.final) || null;
  const col = F ? (F.paused ? 'לפי מה שנספר' : 'תחזית עכשיו') : null;
  // §16ה(ב)–(ג) disclosure of every 2026 poll (past: the replay's 2021/2022 polls, which need none), saying
  // 'לא פורסם' for what the channel did not publish (PAGE-4); an item typed as 'לא פורסם' reads the same, and a
  // missing optional item is left out
  const num = v => typeof v === 'number' ? fmt(v) : esc(v);
  const item = (v, yes, no, always) => v == null || v === '' ? (always ? no : null) : /^לא פורס[םמ]/.test(String(v).trim()) ? no : yes(v);
  const meta = past ? [] : E.polls.map(p => `${esc(p.outlet)}: ${[
    item(p.commissioner, v => `בהזמנת ${esc(v)}`, 'המזמין לא פורסם'),
    item(p.pollster, v => `מכון ${esc(v)}`, 'המכון לא פורסם', true),
    item(p.date, v => `מועד ${esc(v)}`, 'המועד לא פורסם'),
    item(p.population, v => `אוכלוסייה: ${esc(v)}`, 'האוכלוסייה לא פורסמה'),
    item(p.n_invited, v => `${num(v)} פונים`, 'מספר הפונים לא פורסם'),
    item(p.n, v => `${num(v)} משיבים`, 'מספר המשיבים לא פורסם', true),
    item(p.moe, v => `טעות דגימה ±${esc(String(v).replace(/^[±+]/, ''))}`, 'טעות הדגימה לא פורסמה', true),
    p.revised ? `עודכן ב-${esc(p.revised)}` : null].filter(Boolean).join(', ')}`);
  // the projection and the result sit next to the list name, so at phone width the channels scroll under the
  // sticky name column and the projection stays on screen (PAGE-2)
  return `<div class="tbl-wrap lv-scroll"><table class="t sticky1"><thead><tr><th>רשימה</th>${col ? `<th class="n">${col}</th>` : ''}${final ? '<th class="n">תוצאה</th>' : ''}${E.polls.map(p => `<th class="n">${esc(p.outlet)}</th>`).join('')}</tr></thead><tbody>${
    lists.map(l => `<tr><td>${slip(l.letters, l.name, liveColor(l))}</td>${col ? `<td class="n"><b>${l.seats}</b></td>` : ''}${final ? `<td class="n">${final[l.id] ?? 0}</td>` : ''}${E.polls.map(p => `<td class="n">${seatOf(p, l)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    ${E.note ? `<p class="foot">${esc(E.note)}</p>` : ''}${meta.length ? `<p class="foot">${meta.join(' · ')}</p>` : ''}`;
}
function drawExitPolls(F) {
  const card = $('#lv-exit-card'), el = $('#lv-exit'); if (!card) return;
  const demo = S.live.mode === 'demo';
  const E = (demo ? S.live.replays[S.replayKey].exit_polls : S.liveExit) || null;
  if (!E || !(E.polls || []).length || (!demo && exitHidden())) { card.hidden = true; return; }
  card.hidden = false;
  el.innerHTML = exitTable(E, F, demo);
  $$('.lv-scroll', el).forEach(scrollHint);
}
// fade the far edge of a scrolling table while more columns lie beyond it (RTL: scrollLeft runs 0 → negative)
function scrollHint(w) {
  const upd = () => w.classList.toggle('more', w.scrollWidth - w.clientWidth - Math.abs(w.scrollLeft) > 2);
  upd(); w.addEventListener('scroll', upd, { passive: true });
}

function drawLiveProgress(el, F) {
  const c = F.counted, demo = S.live.mode === 'demo';
  // 'complete' comes only from the feed (env_status, when the operator entered the official envelope total);
  // a replay frame is complete when it carries the official result
  const complete = c.env_status ? c.env_status === 'complete' : !!(F.final && c.envelopes);
  const base = demo ? 'הבחירות הקודמות' : '2022';
  const envs = `${fmt(c.env_valid)} קולות במעטפות הכפולות (הצפי לפי ${base}: כ-${fmt(c.env_expected)}; המספר הסופי טרם פורסם)`;
  const done = complete ? 'הספירה הושלמה, כולל המעטפות הכפולות'
    : c.envelopes && c.share >= 0.995 ? `הקלפיות נספרו; נספרו ${envs}`
    : c.envelopes ? `נספרו קלפיות של ${pct(100 * c.share, 0)} מבעלי זכות הבחירה, וגם ${envs}`
    : c.share >= 0.995 ? `כל הקלפיות נספרו; המעטפות הכפולות (כ-${fmt(c.env_expected)} קולות לפי ${base}) עוד לא`
    : `נספרו קלפיות של ${pct(100 * c.share, 0)} מבעלי זכות הבחירה`;
  const sectors = SECTOR_ORDER.filter(k => F.sectors[k]);
  el.innerHTML = `<div class="lv-prog">
    <div class="lv-big"><span class="v num">${pct(100 * c.share, 0)}</span><span class="l">${esc(done)}</span></div>
    <div class="kv">
      <div><b class="num">${fmt(c.boxes)}</b><span>קלפיות נספרו</span></div>
      <div><b class="num">${fmt(c.valid)}</b><span>קולות כשרים נספרו</span></div>
      <div><b class="num">${pct(100 * c.turnout)}</b><span>הצבעה בקלפיות שנספרו</span></div>
    </div></div>
    <h3 style="margin-top:14px">איפה עוד לא נספר</h3>
    <p class="sub">כל פס הוא קבוצת יישובים ברוחב חלקה בבעלי זכות הבחירה; החלק הכהה כבר נספר, מול הפנקס של הבחירות הקודמות.</p>
    <div class="lv-remain">${sectors.map(k => {
      const s = F.sectors[k], w = Math.min(100, 100 * s.counted);   // a register that grew faster than the national rate can pass 100%
      return `<div class="lv-rem-row"><span class="lv-rem-name">${SECTOR_NAME[k]}</span><span class="lv-rem-bar"${s.counted > 1 ? ' title="נספרו יותר בעלי זכות מבפנקס הקודם: הפנקס גדל"' : ''}><i style="width:${w.toFixed(1)}%"></i></span><span class="lv-rem-v num">${pct(w, 0)}</span></div>`;
    }).join('')}</div>
    ${F.batch ? `<p class="lv-batch">העדכון האחרון הוסיף ${fmt(F.batch.stations)} קלפיות${(() => {
      const top = Object.entries(F.batch.by_sector).sort((a, b) => b[1] - a[1])[0];
      return top ? `, ${pct(100 * top[1] / F.batch.stations, 0)} מהן ב${SECTOR_NAME[top[0]] || top[0]}` : '';
    })()}. בקלפיות האלה: ${['coal', 'opp', 'arab'].filter(b => F.batch.blocs[b] != null).map(b => `${BLOC_NAME[b]} ${pct(100 * F.batch.blocs[b], 0)}`).join(' · ')}.</p>` : ''}
    ${F.paused ? `<p class="lv-paused">${ICON_NO} התחזית מושהית: ${esc(typeof F.paused === 'string' ? F.paused : '')} מוצגים רק הקולות שנספרו.</p>` : ''}
    ${F.final ? `<p class="lv-final">${ICON_OK} התוצאה הרשמית (כולל המעטפות): ${F.lists.filter(l => F.final[l.id] > 0).map(l => `${esc(l.name)} ${F.final[l.id]}`).join(' · ')}</p>` : ''}
    ${demo ? '' : '<p class="foot">המעטפות הכפולות (חיילים, נציגויות, אסירים ומאושפזים) נספרות אחרי הקלפיות הרגילות; התחזית כוללת אומדן שלהן.</p>'}`;
}

function liveColor(l) { return isDark() ? l.dark : l.color; }

function drawLiveSeats(el, F) {
  const lists = F.lists.filter(l => l.seats > 0 || l.hi > 0 || l.seats_counted > 0 || (l.p_pass || 0) > 0.02)
    .sort((a, b) => b.seats - a.seats || b.pct - a.pct);
  const W = widthOf(el), nar = W < 560, rowH = 30, M = { t: 20, r: nar ? 150 : 170, b: 18, l: 34 };
  const H = M.t + M.b + rowH * lists.length, share = F.counted.share;
  const svg = svgEl(el, W, H, F.paused ? 'המנדטים לפי הקולות שנספרו' : 'תחזית המנדטים לסיום הספירה');
  const maxV = Math.max(10, d3.max(lists, l => Math.max(l.hi, l.seats_counted)) + 1);
  const x = d3.scaleLinear().domain([0, maxV]).range([W - M.r, M.l]);
  d3.range(0, maxV + 1, maxV > 30 ? 10 : 5).forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', x(v)).attr('x2', x(v)).attr('y1', M.t - 4).attr('y2', H - M.b);
    svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 4).attr('text-anchor', 'middle').text(v);
  });
  lists.forEach((l, i) => {
    const y = M.t + i * rowH, cy = y + rowH / 2, c = liveColor(l);
    const name = fitLabel(l.name, M.r - 36, nar ? 12 : 12.5, 600);
    svg.append('text').attr('class', 'lbl-strong').style('font-size', nar ? '12px' : null).attr('x', W - 2).attr('y', cy).attr('dy', '.35em').attr('text-anchor', 'start').text(name);
    if (l.seats > 0) svg.append('rect').attr('x', x(l.seats)).attr('y', cy - 8).attr('width', x(0) - x(l.seats)).attr('height', 16).attr('rx', 3).attr('fill', c);
    if (l.hi > l.lo) svg.append('line').attr('x1', x(l.lo)).attr('x2', x(l.hi)).attr('y1', cy).attr('y2', cy).attr('stroke', 'var(--ink)').attr('stroke-width', 1.5);
    if (l.seats_counted > 0 || l.seats > 0) svg.append('path').attr('d', d3.symbol(d3.symbolDiamond, 52)()).attr('transform', `translate(${x(l.seats_counted)},${cy})`)
      .attr('fill', 'var(--surface)').attr('stroke', 'var(--ink)').attr('stroke-width', 1.5);
    // RTL text: anchor 'start' puts the right edge at x, so the number sits left of the longest mark
    svg.append('text').attr('class', 'lbl-strong').attr('x', x(Math.max(l.hi, l.seats, l.seats_counted)) - 9).attr('y', cy).attr('dy', '.35em').attr('text-anchor', 'start').text(l.seats);
    svg.append('rect').attr('x', 0).attr('y', y).attr('width', W).attr('height', rowH).attr('fill', 'transparent')
      .call(sel => bindTT(sel, () => `<h4>${esc(l.name)}</h4>${ttRows(F.paused ? [['לפי מה שנספר', l.seats_counted], ['אחוז בקולות שנספרו', pct(l.pct, 2)]] : [
        ['תחזית', `${l.seats} (טווח ${l.lo}–${l.hi})`], ['לפי מה שנספר', l.seats_counted],
        ['אחוז בקולות שנספרו', pct(l.pct, 2)], ['אחוז צפוי', pct(l.pct_proj != null ? l.pct_proj : l.pct, 2)],
        ...(l.p_pass != null && l.p_pass < 0.995 ? [['סיכוי לעבור את אחוז החסימה', pPass(l.p_pass, share)]] : [])])}`));
  });
  // the same numbers as a table, for screen readers and for copying
  el.insertAdjacentHTML('beforeend', `<details class="lv-table"><summary>הנתונים בטבלה</summary><div class="tbl-wrap"><table class="t"><thead><tr><th>רשימה</th><th class="n">${F.paused ? 'לפי הספירה' : 'תחזית'}</th>${F.paused ? '' : '<th class="n">טווח</th><th class="n">לפי הספירה</th><th class="n">אחוז צפוי</th><th class="n">סיכוי לעבור</th>'}</tr></thead><tbody>${
    lists.map(l => `<tr><td>${esc(l.name)}</td><td class="n"><b>${l.seats}</b></td>${F.paused ? '' : `<td class="n"><span class="num">${l.lo}–${l.hi}</span></td><td class="n">${l.seats_counted}</td><td class="n">${pct(l.pct_proj != null ? l.pct_proj : l.pct, 2)}</td><td class="n"><span class="num">${pPass(l.p_pass, share)}</span></td>`}</tr>`).join('')}</tbody></table></div></details>`);
}

function drawLiveBlocs(el, F) {
  const blocs = currentBlocs(), share = F.counted.share;
  // aggregate the projection by the coalition-calculator blocs when the lists are the 2026 lists: the frame keys
  // lists by ballot letters, the calculator by poll ids (PAGE-6). The replay's past lists and a drill's 2022 file
  // keep their own blocs: their letters belong to other lists in 2026.
  const byLetters = S.live.mode === 'live' && !S.live.drill ? Object.fromEntries(S.polls.parties.map(p => [p.letters, p.id])) : {};
  const calc = l => byLetters[l.id] ? blocs[byLetters[l.id]] : null;
  const by = { coal: 0, opp: 0, arab: 0 };
  F.lists.forEach(l => { const b = calc(l) || l.bloc; by[b in by ? b : 'opp'] += l.seats; });
  // the feed's ranges and chances hold only while every list that can win a seat sits in the feed's bloc
  const same = F.lists.every(l => !(l.seats > 0 || l.hi > 0) || !calc(l) || calc(l) === l.bloc);
  const rows = ['coal', 'opp', 'arab'].map(b => ({ b, seats: by[b], lo: same ? F.blocs[b].lo : null, hi: same ? F.blocs[b].hi : null, p61: same ? F.blocs[b].p61 : null }));
  const c = coverageAt(share), real = realBlocCover();
  const cov = [c.K25 && c.K25.bloc_cover80 != null ? `ב-${pct(100 * c.K25.bloc_cover80, 0)} (2022)` : null, c.K24 && c.K24.bloc_cover80 != null ? `ב-${pct(100 * c.K24.bloc_cover80, 0)} (2021)` : null].filter(Boolean);
  const note = F.paused ? 'התחזית מושהית: הגושים לפי הקולות שנספרו בלבד.'
    : !same ? 'השיוך במחשבון הקואליציות שונה מזה שבתחזית, ולכן מוצגים המנדטים בלי טווח וסיכוי לרוב.'
    : cov.length ? `הטווח (80% לפי המודל) כלל את התוצאה של הגוש בבדיקות לאחור בשלב דומה ${heList(cov)}${real != null ? `, ולאורך ליל 2021 בסדר הספירה האמיתי ב-${pct(100 * real, 0)} מנקודות הבדיקה` : ''}.` : '';
  el.innerHTML = rows.map(r => `<div class="lv-bloc">
      <div class="lv-bloc-top"><span><i class="swatch" style="background:var(${blocVar(r.b)})"></i>${BLOC_NAME[r.b]}</span>
      <span><b class="num">${r.seats}</b>${r.lo != null && r.hi > r.lo ? ` <span class="muted num">(${r.lo}–${r.hi})</span>` : ''}</span></div>
      <div class="lv-bloc-bar"><i style="width:${(100 * r.seats / 120).toFixed(2)}%;background:var(${blocVar(r.b)})"></i><b style="right:${(100 * 61 / 120).toFixed(2)}%"></b></div>
      ${r.b !== 'arab' && r.p61 != null ? `<div class="muted lv-p61">סיכוי לרוב לבד: <b class="num">${pPass(r.p61, share)}</b></div>` : ''}
    </div>`).join('') + `<p class="foot">הקו האנכי: 61 מנדטים. ${note}</p>`;
}

function drawLiveThreshold(el, F) {
  const near = F.lists.filter(l => (l.p_pass != null && l.p_pass > 0.01 && l.p_pass < 0.99) || (l.pct > 1.5 && l.pct < 5)).sort((a, b) => b.pct - a.pct);
  if (!near.length) { el.innerHTML = '<p class="empty">אין רשימות קרובות לאחוז החסימה.</p>'; return; }
  const thr = F.counted.valid_proj ? 0.0325 * F.counted.valid_proj : null;
  const paused = !!F.paused, share = F.counted.share;
  // the chance sits next to the name so it stays on screen at phone width (the table scrolls)
  el.innerHTML = `<table class="t wrap"><thead><tr><th>רשימה</th>${paused ? '' : '<th class="n">סיכוי לעבור</th>'}<th class="n">בקולות שנספרו</th>${paused ? '' : '<th class="n hide-sm">צפי, כולל מעטפות</th><th class="n hide-sm">פער מהסף (קולות)</th>'}</tr></thead><tbody>${near.map(l => {
    const p = l.p_pass == null ? (l.seats > 0 ? 1 : 0) : l.p_pass;
    const st = p > 0.95 ? ['עוברת', 'ok'] : p > 0.6 ? ['<span class="hide-sm">כנראה </span>עוברת', 'ok'] : p > 0.4 ? ['על הגדר', 'no'] : ['<span class="hide-sm">כנראה </span>בחוץ', 'no'];
    const gap = thr && l.votes_proj != null ? l.votes_proj - thr : null;
    return `<tr><td>${slip(l.letters, l.name, liveColor(l))}</td>${paused ? '' : `<td class="n"><span class="status ${st[1]}">${st[1] === 'ok' ? ICON_OK : ICON_NO}<span class="num">${pPass(p, share)}</span></span></td>`}<td class="n">${pct(l.pct, 2)}</td>${paused ? '' : `<td class="n hide-sm">${l.pct_proj != null ? pct(l.pct_proj, 2) : '—'}</td><td class="n hide-sm" style="direction:ltr">${gap == null ? '—' : (gap >= 0 ? '+' : '−') + fmt(Math.abs(gap))}</td>`}</tr>`;
  }).join('')}</tbody></table>
  <p class="foot">ברשימות הערביות חלקן במעטפות הכפולות נמוך בהרבה מבקלפיות (ב-2022 כמחצית או פחות), ולכן הסף "האמיתי" שלהן בספירת הקלפיות הרגילות גבוה מעט מ-3.25% (ב-2021–2022 כ-3.4%).</p>`;
}

function drawLiveTurnout(el, F) {
  const rows = SECTOR_ORDER.filter(k => F.sectors[k] && F.sectors[k].turnout != null).map(k => ({ k, ...F.sectors[k] }));
  if (!rows.length) { el.innerHTML = '<p class="empty">עוד לא נספרו קלפיות.</p>'; return; }
  const W = widthOf(el), nar = W < 560;
  // wide: names in a column on the right; narrow: name and value on a line above each dumbbell
  const rowH = nar ? 50 : 40, M = nar ? { t: 8, r: 18, b: 22, l: 18 } : { t: 18, r: 140, b: 22, l: 96 };
  const H = M.t + M.b + rowH * rows.length;
  const svg = svgEl(el, W, H, 'שיעור ההצבעה בקלפיות שנספרו לפי מגזר, מול הבחירות הקודמות');
  const x = d3.scaleLinear().domain([30, 90]).range([M.l, W - M.r - (nar ? 0 : 70)]);
  [30, 50, 70, 90].forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', x(v)).attr('x2', x(v)).attr('y1', M.t).attr('y2', H - M.b);
    svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 4).attr('text-anchor', 'middle').text(v + '%');
  });
  rows.forEach((r, i) => {
    const top = M.t + i * rowH, cy = nar ? top + 34 : top + rowH / 2, a = 100 * r.turnout_base, b = 100 * r.turnout, d = b - a;
    const label = `${pct(b)} (${d >= 0 ? '+' : '−'}${fmt1(Math.abs(d))})`, cnt = pct(Math.min(100, 100 * r.counted), 0);
    if (nar) {
      svg.append('text').attr('class', 'lbl-strong').attr('x', W - 2).attr('y', top + 12).attr('text-anchor', 'start').text(`${SECTOR_NAME[r.k]} · נספרו ${cnt}`);
      svg.append('text').attr('class', 'lbl-strong').attr('x', 2).attr('y', top + 12).attr('text-anchor', 'start').style('direction', 'ltr').text(label);   // LTR: left edge at x
    } else {
      svg.append('text').attr('class', 'lbl-strong').attr('x', W - 2).attr('y', cy - 6).attr('text-anchor', 'start').text(SECTOR_NAME[r.k]);
      svg.append('text').attr('class', 'lbl').attr('x', W - 2).attr('y', cy + 10).attr('text-anchor', 'start').text(`נספרו ${cnt}`);
    }
    svg.append('line').attr('x1', x(a)).attr('x2', x(b)).attr('y1', cy).attr('y2', cy).attr('stroke', 'var(--rule-strong)').attr('stroke-width', 3);
    svg.append('circle').attr('cx', x(a)).attr('cy', cy).attr('r', 5).attr('fill', 'var(--surface)').attr('stroke', 'var(--muted)').attr('stroke-width', 2);
    svg.append('circle').attr('cx', x(b)).attr('cy', cy).attr('r', 6).attr('fill', r.k === 'arab' ? 'var(--arab)' : 'var(--ink)');
    if (!nar) {
      // LTR text: 'start' = left edge at x. The label goes on the far side of the later dot.
      const right = b >= a;
      svg.append('text').attr('class', 'lbl-strong').attr('x', right ? x(b) + 10 : x(b) - 10).attr('y', cy).attr('dy', '.35em').attr('text-anchor', right ? 'start' : 'end')
        .style('direction', 'ltr').text(label);
    }
  });
  el.insertAdjacentHTML('beforeend', '<div class="legend"><span><i style="background:var(--muted)"></i>אותם יישובים, בחירות קודמות</span><span><i style="background:var(--ink)"></i>עכשיו</span></div>');
}

function drawLiveAccuracy(el, F) {
  const A = S.live.accuracy || {};
  const sets = Array.isArray(A) ? { K25: A } : A;
  const series = [['K25', '2022, סדרי ספירה מדומים', null], ['K24', '2021, סדרי ספירה מדומים', '5 4']]
    .filter(([k]) => sets[k]).map(([k, name, dash]) => ({ k, name, dash, pts: sets[k].filter(a => a.counted < 1) }));
  const real = (S.live.accuracy_real || []).filter(a => !a.envelopes && a.counted < 0.995);
  if (real.length) series.push({ k: 'real', name: '2021, סדר הספירה האמיתי', dash: '1 3', real: true, pts: real.map(a => ({ ...a, counted: a.counted })) });
  if (!series.length) { el.innerHTML = '<p class="empty">נתוני הבדיקה לאחור לא נטענו.</p>'; return; }
  const W = widthOf(el), H = 230, M = { t: 18, r: 16, b: 30, l: 34 };
  const svg = svgEl(el, W, H, 'מנדטים שזזו בין התחזית לתוצאה בבדיקות לאחור, לפי שיעור הספירה');
  const x = d3.scaleLinear().domain([0, 1]).range([M.l, W - M.r]);
  const y = d3.scaleLinear().domain([0, Math.max(4, d3.max(series, s => d3.max(s.pts, a => a.seat_err)) + 0.5)]).range([H - M.b, M.t]);
  y.ticks(4).forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 6).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v);
  });
  [0, 0.25, 0.5, 0.75, 1].forEach(v => svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 8).attr('text-anchor', 'middle').text(pct(100 * v, 0)));
  series.forEach(s => {
    svg.append('path').attr('d', d3.line().x(a => x(a.counted)).y(a => y(a.seat_err))(s.pts)).attr('fill', 'none')
      .attr('stroke', s.real ? 'var(--arab)' : 'var(--ink)').attr('stroke-width', s.real ? 2.5 : 2).attr('stroke-dasharray', s.real ? null : s.dash);
    svg.selectAll(null).data(s.pts).join('circle').attr('cx', a => x(a.counted)).attr('cy', a => y(a.seat_err)).attr('r', s.real ? 3 : 4)
      .attr('fill', s.dash && !s.real ? 'var(--surface)' : s.real ? 'var(--arab)' : 'var(--ink)').attr('stroke', s.real ? 'var(--arab)' : 'var(--ink)').attr('stroke-width', 1.5)
      .call(sel => bindTT(sel, a => `<h4>${esc(s.name)} · ${a.time ? esc(a.time) + ' · ' : ''}נספרו ${pct(100 * a.counted, 0)}</h4>${ttRows([[s.real ? 'מנדטים שזזו' : 'מנדטים שזזו בממוצע', fmt1(a.seat_err)], ['טעות בגוש נתניהו', fmt1(a.bloc_err)], ['הטווח של 80% כלל את התוצאה (רשימות)', pct(100 * a.cover80, 0)], ...(a.bloc_cover80 != null ? [['הטווח של 80% כלל את התוצאה (גוש)', pct(100 * a.bloc_cover80, 0)]] : [])])}`));
  });
  const cur = F.counted.share;
  svg.append('line').attr('class', 'ref-line').attr('x1', x(cur)).attr('x2', x(cur)).attr('y1', M.t).attr('y2', H - M.b);
  svg.append('text').attr('class', 'ref-text').attr('x', x(cur)).attr('y', M.t - 4).attr('text-anchor', 'middle').text('עכשיו');
  el.insertAdjacentHTML('beforeend', `<div class="legend">${series.map(s => `<span><i class="line" style="background:var(${s.real ? '--arab' : '--ink'})${s.dash && !s.real ? ';opacity:.5' : ''}"></i>${esc(s.name)}</span>`).join('')}</div>
    <p class="foot">ציר אנכי: מנדטים שזזו בממוצע בין התחזית לתוצאה הסופית. ציר אופקי: שיעור בעלי זכות הבחירה בקלפיות שנספרו. ${
      // the build's own statement of which backtests set the constants (build_replay ACCURACY_NOTE, LM-E)
      S.live.accuracy_note ? esc(S.live.accuracy_note) : 'הקו של 2021 בסדר הספירה האמיתי הוא הבדיקה היחידה על סדר ספירה אמיתי, והוא לא שימש לכיול המודל.'}</p>`);
}

/* ---------- election day: turnout ---------- */
const ELIGIBLE_2026 = 7340000;   // approximate register size (CEC); the live feed carries the official figure
const DAY_HOURS = ['10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00'];
const hourNum = h => +h.slice(0, 2) + (+h.slice(3, 5)) / 60;
const PAST = ['K21', 'K22', 'K23', 'K24', 'K25'];

function dayMarkup() {
  const live = !!S.liveTurnout, day = inElectionWindow(), H0 = S.turnoutHistory;
  // the 22:00 figure is the CEC's election-night estimate; its largest miss of the final count in 2015–2022
  const miss = H0 ? d3.max(['K20', 'K21', 'K22', 'K23', 'K24', 'K25'].filter(e => H0.elections[e]), e => Math.abs(H0.elections[e].final - H0.elections[e].values[6])) : 0.7;
  return `<h2 class="lv-h2">במהלך היום: שיעור ההצבעה</h2>
  <div class="live-bar ${live ? 'on' : 'demo'}">${live
    ? `<span class="live-chip on">חי</span><span class="live-text">נתוני ועדת הבחירות, <span id="dy-upd">${updatedLine('turnout')}</span>. <span class="lv-cad">${cadence()}</span>.</span>`
    : day ? '<span class="live-chip demo">יום הבחירות</span><span class="live-text">ממתינים לפרסום הראשון של ועדת הבחירות (הנתון של 10:00 מתפרסם בדרך כלל 30–65 דקות אחרי השעה). עד אז מוצגות הסדרות של הבחירות הקודמות.</span>'
    : '<span class="live-chip demo">לפני יום הבחירות</span><span class="live-text">ועדת הבחירות מפרסמת שיעור הצבעה ארצי מצטבר בשעות 10:00, 12:00, 14:00, 16:00, 18:00, 20:00 ו-22:00 (ב-2022 פורסם גם נתון ל-19:00). כאן מוצגות הסדרות של הבחירות הקודמות; ב-27 באוקטובר יתווסף אליהן הקו של 2026.</span>'}</div>
  <div class="grid">
    <div class="card c7">
      <h3>שיעור ההצבעה המצטבר, לפי שעה</h3>
      <p class="sub">אחוז מכלל בעלי זכות הבחירה שהצביעו עד כל שעה, לפי הודעות ועדת הבחירות (בדרך כלל 30–65 דקות אחרי השעה העגולה; ב-2022 פורסם גם נתון ל-19:00 ממדגם הלמ״ס). אלה אומדנים של הוועדה מדיווחי מזכירי הקלפיות וממדגם של הלמ״ס, לא ספירה: המספר של 22:00 היה ב-2015–2022 במרחק של עד ${fmt1(miss)} נקודה מהתוצאה הסופית (ב-2022: 71.3% בליל הבחירות, 70.63% בסוף).</p>
      <div class="chart" id="dy-chart"></div>
    </div>
    <div class="card c5" id="dy-now"></div>
    <div class="card c12" id="dy-sectors"></div>
  </div>
  <div id="lv-arab"></div>`;
}

function dayPoints() {
  // 2026 points from the live feed: {"10:00": 15.2, ...}; a 19:00 figure (2022 had one) is drawn too
  const pts = S.liveTurnout && S.liveTurnout.national ? S.liveTurnout.national : {};
  return Object.keys(pts).filter(h => /^\d\d:\d\d$/.test(h) && pts[h] != null && hourNum(h) > 7 && hourNum(h) <= 22)
    .sort((a, b) => hourNum(a) - hourNum(b)).map(h => ({ h, v: +pts[h] }));
}
// when the CEC released the figure for hour h (turnout.json released: {"10:00": "10:40"}), as the operator typed it
function releasedAt(h) {
  const r = S.liveTurnout && S.liveTurnout.released, v = r && typeof r === 'object' ? r[h] : null;
  return v != null && /^\d{1,2}:\d\d$/.test(String(v).trim()) ? String(v).trim() : null;
}
// a past election's figure at hour h: the published value, the 19:00 extra, or a straight line between hours
function hourValue(d, h) {
  if (d.extra && d.extra[h] != null) return d.extra[h];
  const i = DAY_HOURS.indexOf(h); if (i >= 0) return d.values[i];
  const t = hourNum(h), ts = [7, ...DAY_HOURS.map(hourNum)], vs = [0, ...d.values];
  for (let k = 1; k < ts.length; k++) if (t <= ts[k]) return vs[k - 1] + (vs[k] - vs[k - 1]) * (t - ts[k - 1]) / (ts[k] - ts[k - 1]);
  return d.values[6];
}

function drawDay() {
  const H0 = S.turnoutHistory; if (!H0 || !$('#dy-chart')) return;
  drawDayChart($('#dy-chart'), H0);
  drawDayNow($('#dy-now'), H0);
  drawDaySectors($('#dy-sectors'), H0);
}

function drawDayChart(el, H0) {
  const W = widthOf(el), nar = W < 560, H = nar ? 250 : 290, M = { t: 14, r: nar ? 72 : 84, b: 26, l: 36 };
  const svg = svgEl(el, W, H, 'שיעור ההצבעה המצטבר לפי שעה, 2019–2022 ו-2026');
  const x = d3.scaleLinear().domain([7, 22]).range([M.l, W - M.r]);   // time runs left to right
  const y = d3.scaleLinear().domain([0, 80]).range([H - M.b, M.t]);
  [0, 20, 40, 60, 80].forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 6).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v + '%');
  });
  (nar ? ['07:00', '10:00', '14:00', '18:00', '22:00'] : ['07:00', ...DAY_HOURS]).forEach(h =>
    svg.append('text').attr('class', 'lbl').attr('x', x(hourNum(h))).attr('y', H - 6).attr('text-anchor', 'middle').text(h));
  const live = dayPoints();
  const labels = [];
  PAST.forEach(e => {
    const d = H0.elections[e], hi = e === 'K25' && !live.length;
    const pts = [{ t: 7, v: 0 }, ...d.values.map((v, i) => ({ t: hourNum(DAY_HOURS[i]), v }))];
    svg.append('path').attr('d', d3.line().x(p => x(p.t)).y(p => y(p.v))(pts)).attr('fill', 'none')
      .attr('stroke', hi ? 'var(--ink-2)' : 'var(--rule-strong)').attr('stroke-width', hi ? 2.2 : 1.4);
    svg.selectAll(null).data(pts.slice(1)).join('circle').attr('cx', p => x(p.t)).attr('cy', p => y(p.v)).attr('r', hi ? 3.5 : 2.6)
      .attr('fill', hi ? 'var(--ink-2)' : 'var(--rule-strong)')
      .call(sel => bindTT(sel, p => `<h4>${esc(d.label)} · ${String(Math.floor(p.t)).padStart(2, '0')}:00</h4>${ttRows([['שיעור הצבעה מצטבר', pct(p.v)], ['תוצאה סופית', pct(d.final, 2)],
        ...(p.t === 22 && d.note22 ? [['הנתון של 22:00', 'ההודעה של ליל הבחירות']] : [])])}`));
    labels.push({ y: y(d.values[6]), name: d.label, strong: hi });
  });
  if (live.length) {
    const pts = [{ t: 7, v: 0 }, ...live.map(p => ({ t: hourNum(p.h), v: p.v }))];
    svg.append('path').attr('d', d3.line().x(p => x(p.t)).y(p => y(p.v))(pts)).attr('fill', 'none').attr('stroke', 'var(--crit)').attr('stroke-width', 3);
    svg.selectAll(null).data(pts.slice(1)).join('circle').attr('cx', p => x(p.t)).attr('cy', p => y(p.v)).attr('r', 4.5).attr('fill', 'var(--crit)')
      .call(sel => bindTT(sel, p => { const h = live.find(q => hourNum(q.h) === p.t).h, rel = releasedAt(h);
        return `<h4>2026 · ${h}</h4>${ttRows([['שיעור הצבעה מצטבר', pct(p.v)], ...(rel ? [['פורסם', rel]] : [])])}`; }));
    // LTR label so '2026: x%' reads in order; early in the day it sits right of the point (clear of the axis),
    // later to its left; below the point when the point is near the top
    const last = pts[pts.length - 1], lx = x(last.t), toRight = lx - M.l < 70;
    const ly = y(last.v) - 10 < M.t + 10 ? y(last.v) + 18 : y(last.v) - 10;
    svg.append('text').attr('class', 'lbl-strong halo').style('font-size', '13px').style('direction', 'ltr')
      .attr('x', toRight ? lx + 8 : lx - 8).attr('y', ly).attr('text-anchor', toRight ? 'start' : 'end').text(`2026: ${pct(last.v)}`);
  }
  placeLabels(labels, 13, M.t, H - M.b).forEach(o => svg.append('text').attr('class', o.strong ? 'lbl-strong' : 'lbl')
    .attr('x', x(22) + 6).attr('y', o.y).attr('dy', '.35em').attr('text-anchor', 'end').text(o.name));
}

function dayProjection(H0, h, v) {
  // final ÷ figure at the same hour in 2019–2022 gives a range for today's final turnout
  const r = PAST.map(e => H0.elections[e].final / hourValue(H0.elections[e], h));
  return [v * d3.min(r), v * d3.max(r)];
}

function drawDayNow(el, H0) {
  const live = dayPoints();
  const K25 = H0.elections.K25, K24 = H0.elections.K24;
  if (!live.length) {
    el.innerHTML = `<h3>מה יוצג כאן ביום הבחירות</h3>
      <ul class="lv-list">
        <li><b>השוואה לאותה שעה:</b> כל נתון של 2026 מול 2022 ומול שלוש הבחירות שלפניה.</li>
        <li><b>טווח לשיעור ההצבעה הסופי:</b> היחס בין התוצאה הסופית לנתון של אותה שעה נע ב-2019–2022 בין ${fmt1(d3.min(PAST, e => H0.elections[e].ratio[4]))} ל-${fmt1(d3.max(PAST, e => H0.elections[e].ratio[4]))} בשעה 18:00, ולכן הטווח מצטמצם לקראת הערב.</li>
        <li><b>כמה קולות יידרשו כדי לעבור את אחוז החסימה:</b> 3.25% מהקולות הכשרים הצפויים.</li>
      </ul>
      <p class="foot">לדוגמה, ב-2022: ${pct(K25.values[2])} ב-14:00, ${pct(K25.values[4])} ב-18:00, ${pct(K25.final, 2)} בסוף.</p>`;
    return;
  }
  const last = live[live.length - 1];
  const d22 = last.v - hourValue(K25, last.h);
  const [lo, hi] = dayProjection(H0, last.h, last.v);
  const elig = (S.liveTurnout && S.liveTurnout.eligible) || ELIGIBLE_2026;
  const thr = v => 0.0325 * elig * v / 100 * 0.993;   // 0.993: valid votes per voter in 2022
  const hours = [...new Set([...DAY_HOURS, ...live.map(p => p.h)])].sort((a, b) => hourNum(a) - hourNum(b));
  const past = (d, h) => DAY_HOURS.includes(h) ? pct(d.values[DAY_HOURS.indexOf(h)]) : d.extra && d.extra[h] != null ? pct(d.extra[h]) : '—';
  el.innerHTML = `<div class="kv kv3">
      <div><b class="num">${pct(last.v)}</b><span>עד ${last.h}</span></div>
      <div><b class="num" style="direction:ltr">${d22 >= 0 ? '+' : '−'}${fmt1(Math.abs(d22))}</b><span>נקודות מול 2022 באותה שעה</span></div>
      <div><b class="num">${pct(lo, 0)}–${pct(hi, 0)}</b><span>טווח לשיעור הסופי</span></div>
    </div>
    <table class="t"><thead><tr><th>שעה</th><th class="n">2026</th><th class="n">2022</th><th class="n">2021</th></tr></thead><tbody>${
      hours.map(h => { const p = live.find(q => q.h === h), rel = p && releasedAt(h);
        return `<tr><td>${h}${rel ? `<span class="lv-rel">פורסם ${rel}</span>` : ''}</td><td class="n"><b>${p ? pct(p.v) : '—'}</b></td><td class="n">${past(K25, h)}</td><td class="n">${past(K24, h)}</td></tr>`; }).join('')}</tbody></table>
    <p class="foot">אחוז החסימה יעמוד, לפי הטווח, על כ-<span class="num">${fmt(thr(lo))}–${fmt(thr(hi))}</span> קולות. הטווח מבוסס על היחס בין הנתון השעתי לתוצאה הסופית בחמש הבחירות האחרונות; ב-2022 ההצבעה הוקדמה יחסית. הנתונים השעתיים הם אומדנים: ב-2022 הנתון של 22:00 היה גבוה מהתוצאה הסופית ב-0.7 נקודה.${sourceLink()}</p>`;
}
// the CEC statement the operator recorded with the figures (turnout.json source_url / source)
function sourceLink() {
  const T = S.liveTurnout || {}, url = String(T.source_url || '').trim();
  if (!/^https?:\/\/\S+$/i.test(url)) return '';
  return ` מקור: <a href="${esc(url)}" target="_blank" rel="noopener">${esc(T.source || 'הודעת ועדת הבחירות')}</a>.`;
}

function drawDaySectors(el, H0) {
  const T = S.liveTurnout;
  const ach = H0.arab_estimates && H0.arab_estimates.K25, K25 = H0.elections.K25;
  const closed = pollsClosed();
  const noSeats = closed ? 'במהלך היום הדף לא תרגם שיעורי הצבעה למנדטים.' : 'עד 22:00 הדף אינו מתרגם שיעורי הצבעה למנדטים.';
  if (!T || !T.sectors) {
    // the national curve projected from each aChord figure, so the 37% is anchored to its hour
    const proj = h => ach && ach.points[h] != null ? Math.round(ach.points[h] * K25.final / hourValue(K25, h)) : null;
    el.innerHTML = `<h3>שיעור ההצבעה לפי מגזר</h3>
      <p class="sub">לפי החלטת יו״ר ועדת הבחירות (16.8.2026), הוועדה תפרסם לראשונה את שיעור ההצבעה בכל קלפי רגילה, לפחות ארבע פעמים במהלך היום. בג״ץ (17.9.2026) ביטל את ההיתר לדיווח מזוהה על מצביעים, והפרסום המצרפי לפי קלפי נותר על כנו (לפי חדשות 12: כל ארבע שעות); השעות, הכתובת והפורמט טרם פורסמו. אם הנתונים יפורסמו, הדף יחבר כל קלפי למגזר שלה (יישובים ערביים, דרוזיים, קלפיות חרדיות, קלפיות ערביות בערים מעורבות וביישובים יהודיים, ושאר הקלפיות) ויציג לכל מגזר את שיעור ההצבעה ואת היחס לשיעור הארצי באותה שעה.</p>
      <div class="lv-note"><b>למה היחס ולא המספר עצמו:</b> בחברה הערבית מצביעים מאוחר יותר ביום. ב-2022 דיווח טיימס אוף ישראל על אומדני מרכז אקורד (האוניברסיטה העברית) לשיעור ההצבעה בחברה הערבית${ach ? `: ${ach.points['14:00']}% ב-14:00, ${ach.points['16:00']}% ב-16:00 ו-${ach.points['20:00']}% ב-20:00 (נתון של ${ach.points['18:00']}% ב-18:00 יוחס שם למכון מחקר שלא נקב בשמו)` : ''}, והתוצאה הסופית ביישובים הערביים והדרוזיים הייתה ${ach ? pct(ach.final) : '53.2%'}. מי שהיה מקרין את הסוף לפי העקומה הארצית היה מגיע מהנתון של 20:00 לכ-${proj('20:00') ?? 47}%${proj('18:00') ? `, ומהנתון של 18:00 לכ-${proj('18:00')}%` : ''}.</div>
      <p class="foot">נתונים ממפלגות או מגופים אחרים יוצגו בנפרד ויסומנו כלא רשמיים. ${noSeats}</p>`;
    return;
  }
  const rows = SECTOR_ORDER.filter(k => T.sectors[k]).map(k => ({ k, ...T.sectors[k] }));
  // the 2022-weighted pace by bloc is published by the feed only after 22:00 (or when the operator switches
  // lean_during_voting on, pending the CEC legal adviser), so it is shown exactly when it is present
  const L = T.lean || {};
  const exc = Object.entries(T.sectors_excluded || {}).filter(([, n]) => n);
  el.innerHTML = `<h3>שיעור ההצבעה לפי מגזר${T.sectors_time ? `, עד ${esc(T.sectors_time)}` : ''}</h3>
    <p class="sub">מנתוני ועדת הבחירות לכל קלפי רגילה (בלי מעטפות כפולות). הסיווג הוא לפי קלפי: קלפיות חרדיות וקלפיות ערביות בערים מעורבות וביישובים יהודיים מזוהות לפי ההצבעה ב-2022. <b>קצב</b>: כמה הצביעו עד עכשיו, ביחס לכל מי שהצביע באותן קלפיות ב-2022. <b>יחס לארצי</b>: שיעור ההצבעה במגזר חלקי השיעור בכל הקלפיות באותו פרסום. בחברה הערבית מצביעים מאוחר יותר, ולכן הקצב שלה נמוך במהלך היום גם כשההשתתפות הסופית דומה.</p>
    <div class="tbl-wrap"><table class="t"><thead><tr><th>מגזר</th><th class="n">שיעור הצבעה</th><th class="n">קצב מול 2022</th><th class="n">יחס לארצי</th><th class="n hide-sm">סופי 2022</th><th class="n hide-sm">קלפיות</th></tr></thead><tbody>${
      rows.map(r => `<tr><td>${esc(DAY_SECTOR_NAME[r.k] || r.k)}</td><td class="n"><b>${r.turnout != null ? pct(100 * r.turnout) : '—'}</b></td><td class="n">${r.pace != null ? pct(100 * r.pace, 0) : '—'}</td><td class="n">${r.ratio != null ? r.ratio.toFixed(2) : '—'}</td><td class="n hide-sm">${r.final_2022 != null ? pct(100 * r.final_2022) : '—'}</td><td class="n hide-sm">${fmt(r.stations)}</td></tr>`).join('')}</tbody></table></div>
    ${Object.keys(L).length ? `<h3 style="margin-top:14px">מי מגיע לקלפי, לפי ההצבעה ב-2022</h3>
      <p class="sub">הקצב בכל קלפי, משוקלל לפי מספר הקולות שקיבל כל גוש באותה קלפי ב-2022. מספר גבוה יותר: הקלפיות שבהן הגוש היה חזק מגיעות מהר יותר לרמת ההצבעה של 2022. זה אומדן אקולוגי, לא מדידה של מצביעים, ואינו מתורגם למנדטים.</p>
      <div class="lv-lean">${['coal', 'opp', 'arab'].filter(b => L[b] != null).map(b => `<div><span><i class="swatch" style="background:var(${blocVar(b)})"></i>${b === 'coal' ? 'קלפיות של גוש נתניהו' : b === 'opp' ? 'קלפיות של האופוזיציה היהודית' : 'קלפיות של הרשימות הערביות'}</span><b class="num">${pct(100 * L[b], 0)}</b></div>`).join('')}</div>` : ''}
    ${exc.length ? `<p class="foot">לא נכללו בחישוב הקצב: ${exc.map(([k, n]) => `${fmt(n)} (${esc({ 'no 2022 match': 'אין קלפי מקבילה ב-2022', 'implausible pace': 'קצב לא סביר', 'more voters than eligible': 'יותר מצביעים מבעלי זכות', unreadable: 'שורה לא קריאה' }[k] || k)})`).join(', ')}.</p>` : ''}
    ${(T.claims || []).length && closed ? `<h3 style="margin-top:14px">דיווחים לא רשמיים</h3><ul class="lv-list">${T.claims.map(c => `<li><b>${esc(c.time)}</b> · ${esc(c.source)}: ${esc(c.text)}</li>`).join('')}</ul>` : ''}
    <p class="foot">${noSeats}</p>`;
}
