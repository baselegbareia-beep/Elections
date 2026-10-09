/* ===================== election day & night ===================== */
// Live mode reads live/*.json written next to the page by the election-night fetcher
// (pipeline/live_fetch.py, run by .github/workflows/live.yml). Without it (the artifact,
// or before election day) the tab replays election night 2022 from the official ballot
// results in a simulated counting order.
const SECTOR_NAME = { arab: 'יישובים ערביים', druze: 'יישובים דרוזיים', mixed: 'ערים מעורבות', haredi: 'יישובים חרדיים', jewish: 'שאר היישובים' };
const SECTOR_ORDER = ['jewish', 'haredi', 'mixed', 'druze', 'arab'];
const LIVE_POLL_MS = 60000;
S.liveIdx = null; S.livePlay = null;

async function fetchLive(name) {
  // live data exists only on the hosted site during election day and night
  try {
    const r = await fetch(`live/${name}?t=${Date.now()}`, { cache: 'no-store' });
    if (r.ok) return await r.json();
  } catch (e) { /* no live feed */ }
  return null;
}
async function loadLive() {
  // status.json always exists (a placeholder before election day), so only real feeds are requested
  const st = await fetchLive('status.json');
  const [res, turnout, history] = await Promise.all([
    st && st.has_results ? fetchLive('results.json') : null,
    st && st.has_turnout ? fetchLive('turnout.json') : null,
    S.turnoutHistory ? Promise.resolve(S.turnoutHistory) : fetchJSON('data/turnout_history.json')]);
  S.turnoutHistory = history;
  S.liveTurnout = turnout;   // null outside election day
  if (res && res.frame) return { mode: 'live', ...res };
  return { mode: 'demo', ...(await fetchJSON('data/replay_night.json')) };
}

async function renderLive() {
  const root = $('#tab-live');
  if (!S.live) S.live = await loadLive();
  const L = S.live, demo = L.mode === 'demo';
  if (demo && S.liveIdx == null) S.liveIdx = Math.min(5, L.frames.length - 1);
  root.innerHTML = `
  <div class="section-head"><div>
    <span class="eyebrow">יום הבחירות · יום שלישי, 27 באוקטובר 2026 · הקלפיות פתוחות 07:00–22:00</span>
    <h2>יום הבחירות, בזמן אמת</h2>
    <p>במהלך היום: שיעור ההצבעה הרשמי של ועדת הבחירות, מול אותה שעה בבחירות הקודמות, ולראשונה גם לפי קלפי. מ-22:00: ספירת הקולות קלפי אחר קלפי, ותחזית לסיום הספירה שמשווה כל יישוב שנספר לתוצאה שלו ב-2022. התחזית אינה תוצאה רשמית.</p>
  </div></div>
  ${dayMarkup()}
  <h2 class="lv-h2">ליל הבחירות: ספירת הקולות</h2>
  <div class="live-bar ${demo ? 'demo' : 'on'}">
    ${demo ? `<span class="live-chip demo">הדגמה</span><span class="live-text">ליל הבחירות 2022, משוחזר מתוצאות הקלפיות הרשמיות <b>בסדר ספירה מדומה</b>. ב-27 באוקטובר יוצגו כאן נתוני הספירה החיים.</span>
      <span class="live-ctl"><button type="button" class="slip" id="lv-play" aria-label="הפעלה">▶ הפעלה</button>
      <input type="range" id="lv-step" dir="ltr" min="0" max="${L.frames.length - 1}" step="1" value="${S.liveIdx}" aria-label="שלב בספירה"></span>`
    : `${L.drill ? '<span class="live-chip demo">תרגול</span>' : '<span class="live-chip on">חי</span>'}<span class="live-text">${L.drill ? 'תרגול על קובץ 2022. ' : ''}עודכן ${esc(L.updated_he || '')}. מקור: <a href="${esc(L.source_url || '#')}" target="_blank" rel="noopener" dir="ltr">${esc(L.source_label || 'ועדת הבחירות המרכזית')}</a>. הדף מתעדכן כל דקה.</span>`}
  </div>
  <div class="grid">
    <div class="card c12" id="lv-progress-card"></div>
    <div class="card c7">
      <div class="card-head"><div><h3>תחזית המנדטים לסיום הספירה</h3>
      <p class="sub">הפס: המנדטים הצפויים; הקו הדק: טווח 80%; המעוין: המנדטים לפי הקולות שנספרו עד עכשיו בלבד.</p></div></div>
      <div class="chart" id="lv-seats"></div>
    </div>
    <div class="card c5">
      <h3>המרוץ ל-61</h3>
      <p class="sub">המנדטים הצפויים לכל גוש, לפי השיוך שבמחשבון הקואליציות.</p>
      <div id="lv-blocs"></div>
      <h3 style="margin-top:18px">אחוז החסימה</h3>
      <p class="sub">רשימות שעשויות להיות בצד הלא נכון של 3.25%.</p>
      <div id="lv-thr" class="tbl-wrap"></div>
    </div>
    <div class="card c6">
      <h3>השתתפות בקלפיות שנספרו</h3>
      <p class="sub">שיעור ההצבעה בקלפיות שכבר נספרו, מול שיעור ההצבעה באותם יישובים בבחירות הקודמות. זה הנתון הרשמי הראשון על ההשתתפות בחברה הערבית.</p>
      <div class="chart" id="lv-turnout"></div>
    </div>
    <div class="card c6">
      <h3>כמה לסמוך על התחזית</h3>
      <p class="sub">בדיקה לאחור: אותו מודל הורץ על ליל הבחירות 2022 ועל 2021, בארבעה סדרי ספירה מדומים (כולל סדר שבו היישובים הערביים והחרדיים נספרים אחרונים).</p>
      <div class="chart" id="lv-acc"></div>
    </div>
  </div>
  <p class="foot">${demo ? esc(L.note || '') + ' ' : ''}השיטה: אמידה יחסית לפי שכבות (מגזר, אזור והצבעה קודמת), עם נקודת מוצא מממוצע הסקרים, וחלוקת מנדטים בבדר-עופר עם הסכמי העודפים. פירוט בלשונית "שיטה ומקורות".</p>`;
  drawDay();
  drawLiveFrame();
  if (demo) {
    const step = $('#lv-step'), play = $('#lv-play');
    step.addEventListener('input', () => { S.liveIdx = +step.value; stopPlay(); drawLiveFrame(); });
    play.addEventListener('click', () => {
      if (S.livePlay) { stopPlay(); return; }
      if (S.liveIdx >= L.frames.length - 1) S.liveIdx = 0;
      play.textContent = '❚❚ עצירה';
      S.livePlay = setInterval(() => {
        S.liveIdx = Math.min(L.frames.length - 1, S.liveIdx + 1); step.value = S.liveIdx; drawLiveFrame();
        if (S.liveIdx >= L.frames.length - 1) stopPlay();
      }, 1400);
    });
  } else if (!S.liveTimer) {
    S.liveTimer = setInterval(async () => {
      if (S.tab !== 'live') return;
      try { const d = await loadLive(); if (d.mode === 'live') { S.live = d; drawLiveFrame(); } drawDay(); } catch (e) { /* keep last */ }
    }, LIVE_POLL_MS);
  }
}
function stopPlay() {
  clearInterval(S.livePlay); S.livePlay = null;
  const b = $('#lv-play'); if (b) b.textContent = '▶ הפעלה';
}
function liveFrame() { const L = S.live; return L.mode === 'demo' ? L.frames[S.liveIdx] : L.frame; }

function drawLiveFrame() {
  const F = liveFrame(); if (!F) return;
  drawLiveProgress($('#lv-progress-card'), F);
  drawLiveSeats($('#lv-seats'), F);
  drawLiveBlocs($('#lv-blocs'), F);
  drawLiveThreshold($('#lv-thr'), F);
  drawLiveTurnout($('#lv-turnout'), F);
  drawLiveAccuracy($('#lv-acc'), F);
}

function drawLiveProgress(el, F) {
  const c = F.counted, demo = S.live.mode === 'demo';
  const done = c.envelopes ? 'הספירה הושלמה, כולל המעטפות הכפולות' : c.share >= 0.999 ? 'כל הקלפיות נספרו; המעטפות הכפולות עוד לא' : `נספרו קלפיות של ${pct(100 * c.share, 0)} מבעלי זכות הבחירה`;
  const sectors = SECTOR_ORDER.filter(k => F.sectors[k]);
  el.innerHTML = `<div class="lv-prog">
    <div class="lv-big"><span class="v num">${pct(100 * c.share, 0)}</span><span class="l">${esc(done)}</span></div>
    <div class="kv">
      <div><b class="num">${fmt(c.boxes)}</b><span>קלפיות נספרו</span></div>
      <div><b class="num">${fmt(c.valid)}</b><span>קולות כשרים נספרו</span></div>
      <div><b class="num">${pct(100 * c.turnout)}</b><span>הצבעה בקלפיות שנספרו</span></div>
    </div></div>
    <h3 style="margin-top:14px">איפה עוד לא נספר</h3>
    <p class="sub">כל פס הוא קבוצת יישובים ברוחב חלקה בבעלי זכות הבחירה; החלק הכהה כבר נספר.</p>
    <div class="lv-remain">${sectors.map(k => {
      const s = F.sectors[k];
      return `<div class="lv-rem-row"><span class="lv-rem-name">${SECTOR_NAME[k]}</span><span class="lv-rem-bar"><i style="width:${(100 * s.counted).toFixed(1)}%"></i></span><span class="lv-rem-v num">${pct(100 * s.counted, 0)}</span></div>`;
    }).join('')}</div>
    ${F.final ? `<p class="lv-final">${ICON_OK} התוצאה הרשמית (כולל המעטפות): ${F.lists.filter(l => F.final[l.id] > 0).map(l => `${esc(l.name)} ${F.final[l.id]}`).join(' · ')}</p>` : ''}
    ${demo ? '' : '<p class="foot">המעטפות הכפולות (חיילים, נציגויות, אסירים ומאושפזים) נספרות אחרי הקלפיות הרגילות; התחזית כוללת אומדן שלהן.</p>'}`;
}

function liveColor(l) { return isDark() ? l.dark : l.color; }

function drawLiveSeats(el, F) {
  const lists = F.lists.filter(l => l.seats > 0 || l.hi > 0 || l.seats_counted > 0 || (l.p_pass || 0) > 0.02)
    .sort((a, b) => b.seats - a.seats || b.pct - a.pct);
  const W = widthOf(el), nar = W < 560, rowH = 30, M = { t: 20, r: nar ? 112 : 170, b: 18, l: 34 };
  const H = M.t + M.b + rowH * lists.length;
  const svg = svgEl(el, W, H);
  const maxV = Math.max(10, d3.max(lists, l => Math.max(l.hi, l.seats_counted)) + 1);
  const x = d3.scaleLinear().domain([0, maxV]).range([W - M.r, M.l]);
  d3.range(0, maxV + 1, maxV > 30 ? 10 : 5).forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', x(v)).attr('x2', x(v)).attr('y1', M.t - 4).attr('y2', H - M.b);
    svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 4).attr('text-anchor', 'middle').text(v);
  });
  lists.forEach((l, i) => {
    const y = M.t + i * rowH, cy = y + rowH / 2, c = liveColor(l);
    const name = fitLabel(l.name, M.r - 40, 12.5, 600);
    svg.append('text').attr('class', 'lbl-strong').attr('x', W - 2).attr('y', cy).attr('dy', '.35em').attr('text-anchor', 'start').text(name);
    if (l.seats > 0) svg.append('rect').attr('x', x(l.seats)).attr('y', cy - 8).attr('width', x(0) - x(l.seats)).attr('height', 16).attr('rx', 3).attr('fill', c);
    if (l.hi > l.lo) svg.append('line').attr('x1', x(l.lo)).attr('x2', x(l.hi)).attr('y1', cy).attr('y2', cy).attr('stroke', 'var(--ink)').attr('stroke-width', 1.5);
    if (l.seats_counted > 0 || l.seats > 0) svg.append('path').attr('d', d3.symbol(d3.symbolDiamond, 52)()).attr('transform', `translate(${x(l.seats_counted)},${cy})`)
      .attr('fill', 'var(--surface)').attr('stroke', 'var(--ink)').attr('stroke-width', 1.5);
    // RTL text: anchor 'start' puts the right edge at x, so the number sits left of the longest mark
    svg.append('text').attr('class', 'lbl-strong').attr('x', x(Math.max(l.hi, l.seats, l.seats_counted)) - 9).attr('y', cy).attr('dy', '.35em').attr('text-anchor', 'start').text(l.seats);
    svg.append('rect').attr('x', 0).attr('y', y).attr('width', W).attr('height', rowH).attr('fill', 'transparent')
      .call(sel => bindTT(sel, () => `<h4>${esc(l.name)}</h4>${ttRows([
        ['תחזית', `${l.seats} (טווח ${l.lo}–${l.hi})`], ['לפי מה שנספר', l.seats_counted],
        ['אחוז בקולות שנספרו', pct(l.pct, 2)], ['אחוז צפוי', pct(l.pct_proj != null ? l.pct_proj : l.pct, 2)],
        ...(l.p_pass != null && l.p_pass < 0.995 ? [['סיכוי לעבור את אחוז החסימה', pct(100 * l.p_pass, 0)]] : [])])}`));
  });
}

function drawLiveBlocs(el, F) {
  const blocs = currentBlocs();
  // aggregate the projection by the coalition-calculator blocs when the lists are the 2026 lists
  const by = { coal: 0, opp: 0, arab: 0 };
  F.lists.forEach(l => { const b = blocs[l.id] || l.bloc; by[b in by ? b : 'opp'] += l.seats; });
  const same = F.lists.every(l => !blocs[l.id] || blocs[l.id] === l.bloc);
  const rows = ['coal', 'opp', 'arab'].map(b => ({ b, seats: by[b], lo: same ? F.blocs[b].lo : null, hi: same ? F.blocs[b].hi : null, p61: same ? F.blocs[b].p61 : null }));
  el.innerHTML = rows.map(r => `<div class="lv-bloc">
      <div class="lv-bloc-top"><span><i class="swatch" style="background:var(${blocVar(r.b)})"></i>${BLOC_NAME[r.b]}</span>
      <span><b class="num">${r.seats}</b>${r.lo != null && r.hi > r.lo ? ` <span class="muted num">(${r.lo}–${r.hi})</span>` : ''}</span></div>
      <div class="lv-bloc-bar"><i style="width:${(100 * r.seats / 120).toFixed(2)}%;background:var(${blocVar(r.b)})"></i><b style="right:${(100 * 61 / 120).toFixed(2)}%"></b></div>
      ${r.b !== 'arab' && r.p61 != null ? `<div class="muted lv-p61">סיכוי לרוב לבד: <b class="num">${pct(100 * r.p61, 0)}</b></div>` : ''}
    </div>`).join('') + `<p class="foot">הקו האנכי: 61 מנדטים.</p>`;
}

function drawLiveThreshold(el, F) {
  const near = F.lists.filter(l => (l.p_pass != null && l.p_pass > 0.01 && l.p_pass < 0.99) || (l.pct > 1.5 && l.pct < 5)).sort((a, b) => b.pct - a.pct);
  if (!near.length) { el.innerHTML = '<p class="empty">אין רשימות קרובות לאחוז החסימה.</p>'; return; }
  el.innerHTML = `<table class="t wrap"><thead><tr><th>רשימה</th><th class="n">בקולות שנספרו</th><th class="n">סיכוי לעבור</th></tr></thead><tbody>${near.map(l => {
    const p = l.p_pass == null ? (l.seats > 0 ? 1 : 0) : l.p_pass;
    const st = p > 0.95 ? ['עוברת', 'ok'] : p > 0.6 ? ['<span class="hide-sm">כנראה </span>עוברת', 'ok'] : p > 0.4 ? ['על הגדר', 'no'] : ['<span class="hide-sm">כנראה </span>בחוץ', 'no'];
    return `<tr><td>${slip(l.letters, l.name, liveColor(l))}</td><td class="n">${pct(l.pct, 2)}</td><td class="n"><span class="status ${st[1]}">${st[1] === 'ok' ? ICON_OK : ICON_NO}${pct(100 * p, 0)}</span></td></tr>`;
  }).join('')}</tbody></table>`;
}

function drawLiveTurnout(el, F) {
  const rows = SECTOR_ORDER.filter(k => F.sectors[k] && F.sectors[k].turnout != null).map(k => ({ k, ...F.sectors[k] }));
  if (!rows.length) { el.innerHTML = '<p class="empty">עוד לא נספרו קלפיות.</p>'; return; }
  const W = widthOf(el), nar = W < 560;
  // wide: names in a column on the right; narrow: name and value on a line above each dumbbell
  const rowH = nar ? 50 : 40, M = nar ? { t: 8, r: 18, b: 22, l: 18 } : { t: 18, r: 140, b: 22, l: 96 };
  const H = M.t + M.b + rowH * rows.length;
  const svg = svgEl(el, W, H);
  const x = d3.scaleLinear().domain([30, 90]).range([M.l, W - M.r - (nar ? 0 : 70)]);
  [30, 50, 70, 90].forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', x(v)).attr('x2', x(v)).attr('y1', M.t).attr('y2', H - M.b);
    svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 4).attr('text-anchor', 'middle').text(v + '%');
  });
  rows.forEach((r, i) => {
    const top = M.t + i * rowH, cy = nar ? top + 34 : top + rowH / 2, a = 100 * r.turnout_base, b = 100 * r.turnout, d = b - a;
    const label = `${pct(b)} (${d >= 0 ? '+' : '−'}${fmt1(Math.abs(d))})`;
    if (nar) {
      svg.append('text').attr('class', 'lbl-strong').attr('x', W - 2).attr('y', top + 12).attr('text-anchor', 'start').text(`${SECTOR_NAME[r.k]} · נספרו ${pct(100 * r.counted, 0)}`);
      svg.append('text').attr('class', 'lbl-strong').attr('x', 2).attr('y', top + 12).attr('text-anchor', 'start').style('direction', 'ltr').text(label);   // LTR: left edge at x
    } else {
      svg.append('text').attr('class', 'lbl-strong').attr('x', W - 2).attr('y', cy - 6).attr('text-anchor', 'start').text(SECTOR_NAME[r.k]);
      svg.append('text').attr('class', 'lbl').attr('x', W - 2).attr('y', cy + 10).attr('text-anchor', 'start').text(`נספרו ${pct(100 * r.counted, 0)}`);
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
  const series = [['K25', 'ליל הבחירות 2022', null], ['K24', 'ליל הבחירות 2021 (רשימות חדשות ופיצולים)', '5 4']]
    .filter(([k]) => sets[k]).map(([k, name, dash]) => ({ k, name, dash, pts: sets[k].filter(a => a.counted < 1) }));
  if (!series.length) { el.innerHTML = ''; return; }
  const W = widthOf(el), H = 230, M = { t: 18, r: 16, b: 30, l: 34 };
  const svg = svgEl(el, W, H);
  const x = d3.scaleLinear().domain([0, 1]).range([M.l, W - M.r]);
  const y = d3.scaleLinear().domain([0, Math.max(4, d3.max(series, s => d3.max(s.pts, a => a.seat_err)) + 0.5)]).range([H - M.b, M.t]);
  y.ticks(4).forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 6).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v);
  });
  [0, 0.25, 0.5, 0.75, 1].forEach(v => svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 8).attr('text-anchor', 'middle').text(pct(100 * v, 0)));
  series.forEach(s => {
    svg.append('path').attr('d', d3.line().x(a => x(a.counted)).y(a => y(a.seat_err))(s.pts)).attr('fill', 'none')
      .attr('stroke', 'var(--ink)').attr('stroke-width', 2).attr('stroke-dasharray', s.dash);
    svg.selectAll(null).data(s.pts).join('circle').attr('cx', a => x(a.counted)).attr('cy', a => y(a.seat_err)).attr('r', 4)
      .attr('fill', s.dash ? 'var(--surface)' : 'var(--ink)').attr('stroke', 'var(--ink)').attr('stroke-width', 1.5)
      .call(sel => bindTT(sel, a => `<h4>${esc(s.name)} · נספרו ${pct(100 * a.counted, 0)}</h4>${ttRows([['מנדטים שזזו בממוצע', fmt1(a.seat_err)], ['טעות בגוש נתניהו', fmt1(a.bloc_err)], ['הטווח של 80% כלל את התוצאה (רשימות)', pct(100 * a.cover80, 0)], ...(a.bloc_cover80 != null ? [['הטווח של 80% כלל את התוצאה (גוש)', pct(100 * a.bloc_cover80, 0)]] : [])])}`));
  });
  const cur = F.counted.share;
  svg.append('line').attr('class', 'ref-line').attr('x1', x(cur)).attr('x2', x(cur)).attr('y1', M.t).attr('y2', H - M.b);
  svg.append('text').attr('class', 'ref-text').attr('x', x(cur)).attr('y', M.t - 4).attr('text-anchor', 'middle').text('עכשיו');
  el.insertAdjacentHTML('beforeend', `<div class="legend">${series.map(s => `<span><i class="line" style="background:var(--ink)${s.dash ? ';opacity:.5' : ''}"></i>${esc(s.name)}</span>`).join('')}</div>
    <p class="foot">ציר אנכי: מנדטים שזזו בממוצע בין התחזית לתוצאה הסופית. ציר אופקי: שיעור בעלי זכות הבחירה בקלפיות שנספרו. ב-2026 יש כמה רשימות חדשות, ולכן הקו של 2021 הוא אמת המידה הזהירה יותר.</p>`);
}

/* ---------- election day: turnout ---------- */
const ELIGIBLE_2026 = 7340000;   // approximate register size (CEC); the live feed carries the official figure
const DAY_HOURS = ['10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00'];
const hourNum = h => +h.slice(0, 2) + (+h.slice(3, 5)) / 60;

function dayMarkup() {
  const live = !!S.liveTurnout;
  return `<h2 class="lv-h2">במהלך היום: שיעור ההצבעה</h2>
  <div class="live-bar ${live ? 'on' : 'demo'}">${live
    ? `<span class="live-chip on">חי</span><span class="live-text">נתוני ועדת הבחירות, עודכן ${esc(S.liveTurnout.updated_he || '')}.</span>`
    : `<span class="live-chip demo">לפני יום הבחירות</span><span class="live-text">ועדת הבחירות מפרסמת שיעור הצבעה ארצי מצטבר בשעות 10:00, 12:00, 14:00, 16:00, 18:00, 20:00 ו-22:00. כאן מוצגות הסדרות של הבחירות הקודמות; ב-27 באוקטובר יתווסף אליהן הקו של 2026.</span>`}</div>
  <div class="grid">
    <div class="card c7">
      <h3>שיעור ההצבעה המצטבר, לפי שעה</h3>
      <p class="sub">אחוז מכלל בעלי זכות הבחירה שהצביעו עד כל שעה, לפי הודעות ועדת הבחירות. הנתונים הם אומדן של הוועדה (דיווחי מזכירי קלפיות ומדגם של הלמ״ס), והמספר של 22:00 קרוב לתוצאה הסופית.</p>
      <div class="chart" id="dy-chart"></div>
    </div>
    <div class="card c5" id="dy-now"></div>
    <div class="card c12" id="dy-sectors"></div>
  </div>`;
}

function dayPoints() {
  // 2026 points from the live feed: {"10:00": 15.2, ...}
  const pts = S.liveTurnout && S.liveTurnout.national ? S.liveTurnout.national : {};
  return DAY_HOURS.filter(h => pts[h] != null).map(h => ({ h, v: +pts[h] }));
}

function drawDay() {
  const H0 = S.turnoutHistory; if (!H0 || !$('#dy-chart')) return;
  drawDayChart($('#dy-chart'), H0);
  drawDayNow($('#dy-now'), H0);
  drawDaySectors($('#dy-sectors'), H0);
}

function drawDayChart(el, H0) {
  const W = widthOf(el), nar = W < 560, H = nar ? 250 : 290, M = { t: 14, r: nar ? 72 : 84, b: 26, l: 36 };
  const svg = svgEl(el, W, H);
  const x = d3.scaleLinear().domain([7, 22]).range([M.l, W - M.r]);   // time runs left to right
  const y = d3.scaleLinear().domain([0, 80]).range([H - M.b, M.t]);
  [0, 20, 40, 60, 80].forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 6).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v + '%');
  });
  (nar ? ['07:00', '10:00', '14:00', '18:00', '22:00'] : ['07:00', ...DAY_HOURS]).forEach(h =>
    svg.append('text').attr('class', 'lbl').attr('x', x(hourNum(h))).attr('y', H - 6).attr('text-anchor', 'middle').text(h));
  const show = ['K21', 'K22', 'K23', 'K24', 'K25'];
  const live = dayPoints();
  const labels = [];
  show.forEach(e => {
    const d = H0.elections[e], hi = e === 'K25' && !live.length;
    const pts = [{ t: 7, v: 0 }, ...d.values.map((v, i) => ({ t: hourNum(DAY_HOURS[i]), v }))];
    svg.append('path').attr('d', d3.line().x(p => x(p.t)).y(p => y(p.v))(pts)).attr('fill', 'none')
      .attr('stroke', hi ? 'var(--ink-2)' : 'var(--rule-strong)').attr('stroke-width', hi ? 2.2 : 1.4);
    svg.selectAll(null).data(pts.slice(1)).join('circle').attr('cx', p => x(p.t)).attr('cy', p => y(p.v)).attr('r', hi ? 3.5 : 2.6)
      .attr('fill', hi ? 'var(--ink-2)' : 'var(--rule-strong)')
      .call(sel => bindTT(sel, p => `<h4>${esc(d.label)} · ${String(Math.floor(p.t)).padStart(2, '0')}:00</h4>${ttRows([['שיעור הצבעה מצטבר', pct(p.v)], ['תוצאה סופית', pct(d.final, 2)]])}`));
    labels.push({ y: y(d.values[6]), name: d.label, strong: hi });
  });
  if (live.length) {
    const pts = [{ t: 7, v: 0 }, ...live.map(p => ({ t: hourNum(p.h), v: p.v }))];
    svg.append('path').attr('d', d3.line().x(p => x(p.t)).y(p => y(p.v))(pts)).attr('fill', 'none').attr('stroke', 'var(--crit)').attr('stroke-width', 3);
    svg.selectAll(null).data(pts.slice(1)).join('circle').attr('cx', p => x(p.t)).attr('cy', p => y(p.v)).attr('r', 4.5).attr('fill', 'var(--crit)')
      .call(sel => bindTT(sel, p => `<h4>2026 · ${String(Math.floor(p.t)).padStart(2, '0')}:00</h4>${ttRows([['שיעור הצבעה מצטבר', pct(p.v)]])}`));
    const last = pts[pts.length - 1];
    svg.append('text').attr('class', 'lbl-strong halo').style('font-size', '13px').attr('x', x(last.t) - 8).attr('y', y(last.v) - 10).attr('text-anchor', 'start').text(`2026: ${pct(last.v)}`);
  }
  placeLabels(labels, 13, M.t, H - M.b).forEach(o => svg.append('text').attr('class', o.strong ? 'lbl-strong' : 'lbl')
    .attr('x', x(22) + 6).attr('y', o.y).attr('dy', '.35em').attr('text-anchor', 'end').text(o.name));
}

function dayProjection(H0, h, v) {
  // final ÷ hourly figure in 2019–2022 at the same hour gives a range for today's final turnout
  const i = DAY_HOURS.indexOf(h);
  const r = ['K21', 'K22', 'K23', 'K24', 'K25'].map(e => H0.elections[e].final / H0.elections[e].values[i]);
  return [v * d3.min(r), v * d3.max(r)];
}

function drawDayNow(el, H0) {
  const live = dayPoints();
  const K25 = H0.elections.K25;
  if (!live.length) {
    el.innerHTML = `<h3>מה יוצג כאן ביום הבחירות</h3>
      <ul class="lv-list">
        <li><b>השוואה לאותה שעה:</b> כל נתון של 2026 מול 2022 ומול שלוש הבחירות שלפניה.</li>
        <li><b>טווח לשיעור ההצבעה הסופי:</b> היחס בין התוצאה הסופית לנתון של אותה שעה נע ב-2019–2022 בין ${fmt1(d3.min(['K21', 'K22', 'K23', 'K24', 'K25'], e => H0.elections[e].ratio[4]))} ל-${fmt1(d3.max(['K21', 'K22', 'K23', 'K24', 'K25'], e => H0.elections[e].ratio[4]))} בשעה 18:00, ולכן הטווח מצטמצם לקראת הערב.</li>
        <li><b>כמה קולות יידרשו כדי לעבור את אחוז החסימה:</b> 3.25% מהקולות הכשרים הצפויים.</li>
      </ul>
      <p class="foot">לדוגמה, ב-2022: ${pct(K25.values[2])} ב-14:00, ${pct(K25.values[4])} ב-18:00, ${pct(K25.final, 2)} בסוף.</p>`;
    return;
  }
  const last = live[live.length - 1], i = DAY_HOURS.indexOf(last.h);
  const d22 = last.v - K25.values[i];
  const [lo, hi] = dayProjection(H0, last.h, last.v);
  const elig = (S.liveTurnout && S.liveTurnout.eligible) || ELIGIBLE_2026;
  const thr = v => 0.0325 * elig * v / 100 * 0.993;   // 0.993: valid votes per voter in 2022
  el.innerHTML = `<div class="kv kv3">
      <div><b class="num">${pct(last.v)}</b><span>עד ${last.h}</span></div>
      <div><b class="num" style="direction:ltr">${d22 >= 0 ? '+' : '−'}${fmt1(Math.abs(d22))}</b><span>נקודות מול 2022 באותה שעה</span></div>
      <div><b class="num">${pct(lo, 0)}–${pct(hi, 0)}</b><span>טווח לשיעור הסופי</span></div>
    </div>
    <table class="t"><thead><tr><th>שעה</th><th class="n">2026</th><th class="n">2022</th><th class="n">2021</th></tr></thead><tbody>${
      DAY_HOURS.map((h, j) => { const p = live.find(q => q.h === h); return `<tr><td>${h}</td><td class="n"><b>${p ? pct(p.v) : '—'}</b></td><td class="n">${pct(K25.values[j])}</td><td class="n">${pct(H0.elections.K24.values[j])}</td></tr>`; }).join('')}</tbody></table>
    <p class="foot">אחוז החסימה יעמוד, לפי הטווח, על כ-${fmt(thr(lo))}–${fmt(thr(hi))} קולות. הטווח מבוסס על היחס בין הנתון השעתי לתוצאה הסופית בחמש הבחירות האחרונות; ב-2022 ההצבעה הוקדמה יחסית.</p>`;
}

function drawDaySectors(el, H0) {
  const T = S.liveTurnout;
  const ach = H0.arab_estimates && H0.arab_estimates.K25;
  if (!T || !T.sectors) {
    el.innerHTML = `<h3>שיעור ההצבעה לפי מגזר</h3>
      <p class="sub">לפי החלטת יו״ר ועדת הבחירות (16.8.2026), הוועדה תפרסם לראשונה את שיעור ההצבעה בכל קלפי רגילה, לפחות ארבע פעמים במהלך היום. אם הנתונים יפורסמו, הדף יחבר כל קלפי למגזר שלה (יישובים ערביים, דרוזיים, חרדיים, קלפיות ערביות בערים מעורבות ושאר הקלפיות) ויציג לכל מגזר את שיעור ההצבעה ואת היחס לשיעור הארצי באותה שעה.</p>
      <div class="lv-note"><b>למה היחס ולא המספר עצמו:</b> בחברה הערבית מצביעים מאוחר יותר ביום. ב-2022 העריך מרכז אקורד (האוניברסיטה העברית) ${ach ? `${ach.points['14:00']}% ב-14:00, ${ach.points['18:00']}% ב-18:00 ו-${ach.points['20:00']}% ב-20:00` : ''}, והתוצאה הסופית ביישובים הערביים והדרוזיים הייתה ${ach ? pct(ach.final) : '53.2%'}. מי שהיה מקרין את הסוף לפי העקומה הארצית היה מגיע לכ-37%.</div>
      <p class="foot">נתונים ממפלגות או מגופים אחרים יוצגו בנפרד ויסומנו כלא רשמיים. עד 22:00 הדף אינו מתרגם שיעורי הצבעה למנדטים.</p>`;
    return;
  }
  const rows = Object.entries(T.sectors).map(([k, v]) => ({ k, ...v }));
  el.innerHTML = `<h3>שיעור ההצבעה לפי מגזר${T.sectors_time ? `, עד ${esc(T.sectors_time)}` : ''}</h3>
    <p class="sub">מנתוני ועדת הבחירות לכל קלפי רגילה (בלי מעטפות כפולות). היחס לארצי: שיעור ההצבעה במגזר חלקי שיעור ההצבעה בכל הקלפיות הרגילות באותו פרסום.</p>
    <div class="tbl-wrap"><table class="t"><thead><tr><th>מגזר</th><th class="n">שיעור הצבעה</th><th class="n">יחס לארצי</th><th class="n hide-sm">קלפיות שדיווחו</th><th class="n hide-sm">סופי 2022</th></tr></thead><tbody>${
      rows.map(r => `<tr><td>${esc(SECTOR_NAME[r.k] || r.k)}</td><td class="n"><b>${pct(100 * r.turnout)}</b></td><td class="n">${r.ratio != null ? r.ratio.toFixed(2) : '—'}</td><td class="n hide-sm">${pct(100 * r.coverage, 0)}</td><td class="n hide-sm">${r.final_2022 != null ? pct(100 * r.final_2022) : '—'}</td></tr>`).join('')}</tbody></table></div>
    ${(T.claims || []).length ? `<h3 style="margin-top:14px">דיווחים לא רשמיים</h3><ul class="lv-list">${T.claims.map(c => `<li><b>${esc(c.time)}</b> · ${esc(c.source)}: ${esc(c.text)}</li>`).join('')}</ul>` : ''}
    <p class="foot">עד 22:00 הדף אינו מתרגם שיעורי הצבעה למנדטים.</p>`;
}
