/* ===================== coalition builder + scenario generator ===================== */
S.scn = { arabT: 53, swing: 0 };   // slider value; 53 stands for the 53.2% baseline
const ARAB_T0 = 53.2;        // assumed Arab turnout implied by the polls (K25, Arab and Druze localities)
const ARAB_FROM_SECTOR = 0.878; // share of Arab-list votes cast in Arab boxes, K25 (computed from ballot data)

function scenarioShares(arabT = S.scn.arabT, swing = S.scn.swing) {
  ensureSims();
  if (Math.round(arabT) === Math.round(ARAB_T0)) arabT = ARAB_T0;   // the slider moves in whole points
  const base = { ...S.shares };
  const blocs = currentBlocs();
  const v = {};
  Object.keys(base).forEach(k => { v[k] = base[k]; });
  // Arab turnout: Arab-list votes scale with turnout for the part cast in the Arab sector
  S.polls.parties.forEach(p => {
    if (p.bloc === 'arab') v[p.id] = base[p.id] * (ARAB_FROM_SECTOR * arabT / ARAB_T0 + (1 - ARAB_FROM_SECTOR));
  });
  // uniform swing between the Netanyahu bloc and the Jewish opposition (points of the total vote)
  const coal = S.polls.parties.filter(p => blocs[p.id] === 'coal'), opp = S.polls.parties.filter(p => blocs[p.id] === 'opp');
  const cs = sum(coal.map(p => base[p.id])), os = sum(opp.map(p => base[p.id]));
  coal.forEach(p => { v[p.id] = Math.max(0.0005, v[p.id] + (swing / 100) * base[p.id] / cs); });
  opp.forEach(p => { v[p.id] = Math.max(0.0005, v[p.id] - (swing / 100) * base[p.id] / os); });
  return v;
}

function renderCoalition() {
  const root = $('#tab-coalition');
  ensureSims();
  const blocs = currentBlocs();
  if (!S.coalition) S.coalition = new Set(S.polls.parties.filter(p => blocs[p.id] === 'coal').map(p => p.id));
  root.innerHTML = `
  <div class="section-head"><div>
    <span class="eyebrow">בונה קואליציה · מחולל תרחישים</span>
    <h2>הדרך ל-61</h2>
    <p>לחצו על רשימות כדי להכניס או להוציא אותן מהקואליציה. המנדטים מחושבים מממוצע הסקרים בשיטת בדר-עופר עם אחוז החסימה. שני המחוונים משנים את ההנחות ומחשבים מחדש את כל 120 המושבים.</p>
  </div></div>
  <div class="grid">
    <div class="card c7">
      <div class="coal-total"><span class="big num" id="cb-total">—</span><span id="cb-status"></span></div>
      <p class="sub" id="cb-sub" style="margin-top:6px"></p>
      <div class="chart" id="cb-hemi"></div>
      <div class="chips" id="cb-chips" style="margin-top:10px"></div>
      <details class="bloc-edit" style="margin-top:14px"><summary>שיוך הרשימות לגושים</summary>
        <p class="sub" style="margin-top:6px">ברירת המחדל: מפלגות הממשלה היוצאת ועמך ישראל בגוש נתניהו, הרשימה המשותפת ורע״ם בנפרד. השינוי חל על כל הדשבורד: ממוצע הגושים, הסימולציה והגרפים.</p>
        <div id="cb-blocs" class="bloc-grid"></div>
      </details>
    </div>
    <div class="card c5">
      <h3>הרכבים מוכנים</h3>
      <p class="sub">נקודות פתיחה. השיוך לגושים הוא הנחה עריכתית ולא עובדה; ניתן לשנות כל רשימה.</p>
      <div class="chips" id="cb-presets">
        <button type="button" class="slip" data-preset="coal">גוש נתניהו</button>
        <button type="button" class="slip" data-preset="opp">אופוזיציה יהודית</button>
        <button type="button" class="slip" data-preset="opp-raam">אופוזיציה + רע״ם</button>
        <button type="button" class="slip" data-preset="opp-arab">אופוזיציה + שתי הרשימות הערביות</button>
        <button type="button" class="slip" data-preset="unity">אחדות: ליכוד, ישר!, ביחד</button>
      </div>
      <h3 style="margin-top:22px">מחולל תרחישים</h3>
      <p class="sub">מה קורה לחלוקת המנדטים כשמשתנות ההנחות.</p>
      <label class="ctl-label" for="sc-arab">שיעור ההצבעה בחברה הערבית: <b class="num" id="sc-arab-v"></b></label>
      <input type="range" id="sc-arab" dir="ltr" min="35" max="75" step="1" value="${S.scn.arabT}">
      <div class="range-ticks" dir="ltr">${(() => {
        // two staggered rows so close turnout values do not collide on narrow screens
        const ts = ['K21', 'K22', 'K23', 'K24', 'K25'].map(e => ({ e, T: rate(e, 'arab_std') })).sort((a, b) => a.T - b.T);
        return ts.map(({ e, T }, i) => `<span style="left:${(T - 35) / 40 * 100}%;top:${i % 2 ? 15 : 0}px" title="${E(e).label}: ${pct(T)}">${COMPACT[e]}</span>`).join('');
      })()}</div>
      <label class="ctl-label" for="sc-swing" style="display:block;margin-top:14px">תזוזה בין גוש נתניהו לאופוזיציה: <b class="num" id="sc-swing-v"></b></label>
      <input type="range" id="sc-swing" dir="ltr" min="-4" max="4" step="0.25" value="${S.scn.swing}">
      <div class="legend" dir="ltr" style="justify-content:space-between"><span>← לטובת האופוזיציה</span><span>לטובת גוש נתניהו →</span></div>
      <button type="button" class="slip" id="sc-reset" style="margin-top:10px">איפוס לממוצע הסקרים</button>
      <p class="foot">ההנחות: ממוצע הסקרים משקף שיעור הצבעה ערבי של ${pct(ARAB_T0)} ביישובים הערביים והדרוזיים, כמו ב-2022. ${pct(100 * ARAB_FROM_SECTOR, 1)} מקולות הרשימות הערביות ב-2022 ניתנו בקלפיות של החברה הערבית; רק החלק הזה משתנה עם שיעור ההצבעה, וההשתתפות בקלפיות הערביות בערים המעורבות נעה יחד איתו. תזוזה של נקודת אחוז = כ-1.2 מנדטים.</p>
    </div>
    <div class="card c12">
      <h3>כמה שווה כל נקודת אחוז של הצבעה ערבית?</h3>
      <p class="sub">מנדטי הקואליציה שבחרתם (קו כהה) ומנדטי הרשימות הערביות, כפונקציה של שיעור ההצבעה בחברה הערבית. הקווים האנכיים מסמנים את חמש מערכות הבחירות האחרונות.</p>
      <div class="chart" id="sc-curve"></div>
    </div>
  </div>`;
  const update = () => { drawCoalition(); drawCurve(); };
  $('#cb-chips').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    const id = b.dataset.id; S.coalition.has(id) ? S.coalition.delete(id) : S.coalition.add(id); update();
  });
  $('#cb-presets').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    const by = k => S.polls.parties.filter(p => blocs[p.id] === k).map(p => p.id);
    const P = { coal: by('coal'), opp: by('opp'), 'opp-raam': [...by('opp'), "Ra'am"], 'opp-arab': [...by('opp'), ...by('arab')], unity: ['Likud', 'Yashar', 'Together'] };
    S.coalition = new Set(P[b.dataset.preset]); update();
  });
  drawBlocEditor();
  const sa = $('#sc-arab'), ss = $('#sc-swing');
  sa.addEventListener('input', () => { S.scn.arabT = +sa.value; update(); });
  ss.addEventListener('input', () => { S.scn.swing = +ss.value; update(); });
  $('#sc-reset').addEventListener('click', () => { S.scn = { arabT: Math.round(ARAB_T0), swing: 0 }; sa.value = S.scn.arabT; ss.value = 0; update(); });
  update();
}

function drawBlocEditor() {
  const blocs = currentBlocs();
  const ps = S.polls.parties.filter(p => S.avg.avg[p.id] > 0.5);
  $('#cb-blocs').innerHTML = ps.map(p => `<div class="bloc-row"><span class="slip"><i class="dot" style="background:${party26Color(p)}"></i><b class="let">${esc(p.letters)}</b><span class="nm">${esc(p.name)}</span></span>${
    seg('bl-' + p.letters, [['coal', 'נתניהו'], ['opp', 'אופוזיציה'], ['arab', 'ערביות']], blocs[p.id])}</div>`).join('');
  ps.forEach(p => onSeg($('#cb-blocs'), 'bl-' + p.letters, v => {
    S.coalitionBlocs[p.id] = v; invalidatePolls(); ensureSims(); drawCoalition(); drawCurve();
  }));
}

function coalitionSeats() {
  const v = scenarioShares();
  return baderOfer(v, { agreements: SIM.agreements });
}

function drawCoalition() {
  const seats = coalitionSeats();
  const ids = S.polls.parties.map(p => p.id);
  const inC = id => S.coalition.has(id);
  const total = sum(ids.filter(inC).map(id => seats[id] || 0));
  const baseline = Math.round(S.scn.arabT) === Math.round(ARAB_T0) && S.scn.swing === 0;
  $('#sc-arab-v').textContent = Math.round(S.scn.arabT) === Math.round(ARAB_T0) ? pct(ARAB_T0) + ' (כמו ב-2022)' : pct(S.scn.arabT, 0);
  $('#sc-swing-v').textContent = S.scn.swing === 0 ? 'ללא' : `${fmt1(Math.abs(S.scn.swing))} נק׳ ${S.scn.swing > 0 ? 'לגוש נתניהו' : 'לאופוזיציה'}`;
  $('#cb-total').textContent = total;
  $('#cb-status').innerHTML = total >= 61 ? `<span class="status ok">${ICON_OK}רוב של ${total}</span>` : `<span class="status no">${ICON_NO}${61 - total === 1 ? 'חסר מנדט אחד לרוב' : `חסרים ${61 - total} לרוב`}</span>`;
  const sim = simSummary(S.sims, [...S.coalition]);
  $('#cb-sub').innerHTML = baseline
    ? `מנדטים לפי ממוצע הסקרים. בסימולציות, ההרכב הזה מגיע ל-61 ב-${N(pct(100 * sim.p61, 0))} מהמקרים (80% מהתרחישים: ${N(sim.q10)}–${N(sim.q90)}).`
    : `תרחיש: שיעור הצבעה ערבי ${N(pct(S.scn.arabT, 0))}${S.scn.swing ? `, תזוזה של ${N(fmt1(Math.abs(S.scn.swing)))} נק׳ ${S.scn.swing > 0 ? 'לגוש נתניהו' : 'לאופוזיציה'}` : ''}. ההסתברות מחושבת רק לממוצע עצמו.`;
  const parties = S.polls.parties.filter(p => (seats[p.id] || 0) > 0 || S.avg.avg[p.id] > 1);
  $('#cb-chips').innerHTML = parties.map(p => `<button type="button" class="slip" data-id="${esc(p.id)}" aria-pressed="${inC(p.id)}"><i class="dot" style="background:${party26Color(p)}"></i><b class="let">${esc(p.letters)}</b><span class="nm">${esc(p.name)}</span><span class="num" style="font-weight:600">${seats[p.id] || 0}</span></button>`).join('');
  drawHemicycle($('#cb-hemi'), seats);
}

function hemicycleLayout(n = 120, rows = 6) {
  // classic parliament diagram: seats spread over concentric arcs
  const radii = d3.range(rows).map(i => 0.42 + 0.58 * i / (rows - 1));
  const tot = sum(radii);
  const per = radii.map(r => Math.round(n * r / tot));
  per[rows - 1] += n - sum(per);
  const pts = [];
  radii.forEach((r, i) => {
    for (let j = 0; j < per[i]; j++) {
      const a = Math.PI * (per[i] === 1 ? 0.5 : j / (per[i] - 1));
      pts.push({ r, a, x: Math.cos(a) * r, y: Math.sin(a) * r });
    }
  });
  return pts.sort((p, q) => p.a - q.a || q.r - p.r);   // a=0 is the right-hand end
}
function drawHemicycle(el, seats) {
  const W = widthOf(el, 640), H = Math.round(W * 0.52) + 22;
  const svg = svgEl(el, W, H);
  const pts = hemicycleLayout();
  const R = W * 0.47, cx = W / 2, cy = H - 12;
  const seatR = Math.max(3, R * 0.028);
  const order = [...S.polls.parties].filter(p => seats[p.id] > 0)
    .sort((a, b) => (S.coalition.has(b.id) - S.coalition.has(a.id)) || seats[b.id] - seats[a.id]);
  const assign = [];
  order.forEach(p => { for (let i = 0; i < seats[p.id]; i++) assign.push(p); });
  svg.selectAll('circle').data(pts).join('circle')
    .attr('cx', d => cx + d.x * R).attr('cy', d => cy - d.y * R).attr('r', seatR)
    .attr('fill', (d, i) => assign[i] ? party26Color(assign[i]) : 'var(--rule)')
    .attr('opacity', (d, i) => assign[i] && S.coalition.has(assign[i].id) ? 1 : 0.22)
    .call(s => bindTT(s, (d, ev) => { const i = pts.indexOf(d); const p = assign[i]; return p ? `<h4>${esc(p.name)}</h4>${ttRows([['מנדטים', seats[p.id]], ['בקואליציה', S.coalition.has(p.id) ? 'כן' : 'לא']])}` : ''; }));
  // 61 marker between seat 60 and 61 along the angle
  const a = (pts[59].a + pts[60].a) / 2;
  svg.append('line').attr('class', 'ref-line').attr('x1', cx + Math.cos(a) * R * 0.34).attr('y1', cy - Math.sin(a) * R * 0.34)
    .attr('x2', cx + Math.cos(a) * R * 1.06).attr('y2', cy - Math.sin(a) * R * 1.06);
  svg.append('text').attr('class', 'ref-text').attr('x', cx + Math.cos(a) * R * 1.06).attr('y', cy - Math.sin(a) * R * 1.06 - 6).attr('text-anchor', 'middle').text('61');
  const total = sum([...S.coalition].map(id => seats[id] || 0));
  svg.append('text').attr('class', 'lbl-big').attr('x', cx).attr('y', cy - 8).attr('text-anchor', 'middle').style('font-size', Math.max(15, Math.min(26, W / 22)) + 'px').text(`${total} מתוך 120`);
}

function drawCurve() {
  const el = $('#sc-curve');
  const W = widthOf(el), H = 280, M = { t: 26, r: 24, b: 34, l: 40 };
  const svg = svgEl(el, W, H);
  const Ts = d3.range(35, 75.5, 1);
  const blocs = currentBlocs();
  const arabIds = S.polls.parties.filter(p => blocs[p.id] === 'arab').map(p => p.id);
  const pts = Ts.map(T => {
    const s = baderOfer(scenarioShares(T, S.scn.swing), { agreements: SIM.agreements });
    return { T, coal: sum([...S.coalition].map(id => s[id] || 0)), arab: sum(arabIds.map(id => s[id] || 0)) };
  });
  const x = d3.scaleLinear().domain([35, 75]).range([M.l, W - M.r]);
  const y = d3.scaleLinear().domain([0, Math.max(70, d3.max(pts, p => p.coal) + 4)]).range([H - M.b, M.t]);
  [0, 20, 40, 61].forEach(v => {
    svg.append('line').attr('class', v === 61 ? 'ref-line' : 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', v === 61 ? 'ref-text' : 'lbl').attr('x', M.l - 8).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v);
  });
  [40, 50, 60, 70].forEach(v => svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 12).attr('text-anchor', 'middle').text(v + '%'));
  ['K21', 'K22', 'K23', 'K24', 'K25'].forEach(eid => {
    const T = rate(eid, 'arab_std'); const xx = x(T);
    svg.append('line').attr('x1', xx).attr('x2', xx).attr('y1', M.t).attr('y2', H - M.b).attr('stroke', 'var(--arab)').attr('stroke-dasharray', '2 3').attr('opacity', .8);
    svg.append('text').attr('class', 'lbl').attr('x', xx).attr('y', M.t - 8).attr('text-anchor', 'middle').text(W < 560 ? `ה-${E(eid).n}` : E(eid).short);
  });
  const stepLine = key => d3.line().x(d => x(d.T)).y(d => y(d[key])).curve(d3.curveStepAfter)(pts);
  svg.append('path').attr('d', stepLine('arab')).attr('fill', 'none').attr('stroke', 'var(--arab)').attr('stroke-width', 2.5);
  svg.append('path').attr('d', stepLine('coal')).attr('fill', 'none').attr('stroke', 'var(--ink)').attr('stroke-width', 2.5);
  const cur = pts.find(p => p.T === Math.round(S.scn.arabT)) || pts[18];
  svg.append('circle').attr('cx', x(cur.T)).attr('cy', y(cur.coal)).attr('r', 5).attr('fill', 'var(--marker)').attr('stroke', 'var(--ink)');
  svg.append('text').attr('class', 'lbl-strong').attr('x', x(75) - 2).attr('y', y(pts[pts.length - 1].coal) - 8).attr('text-anchor', 'start').text('הקואליציה שבחרתם');
  svg.append('text').attr('class', 'lbl-strong').attr('x', x(75) - 2).attr('y', y(pts[pts.length - 1].arab) - 8).attr('text-anchor', 'start').style('fill', 'var(--ink)').text('הרשימות הערביות');
  svg.append('rect').attr('x', M.l).attr('y', M.t).attr('width', W - M.l - M.r).attr('height', H - M.t - M.b).attr('fill', 'transparent')
    .on('mousemove', ev => { const [mx] = d3.pointer(ev); const T = Math.round(x.invert(mx)); const p = pts.find(q => q.T === T); if (!p) return;
      tt.show(`<h4>הצבעה ערבית ${T}%</h4>${ttRows([['הקואליציה שבחרתם', p.coal], ['הרשימות הערביות', p.arab, cssVar('--arab')]])}`, ev); })
    .on('mouseleave', () => tt.hide());
}
