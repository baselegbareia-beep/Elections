/* ===================== polls ===================== */
S.trendParties = null;
S.pollHouse = 'all';

function dailyAverages(fromDate, toDateV) {
  // UTC days from the first to the latest poll inclusive; the last point equals the headline average
  const days = d3.utcDay.range(d3.utcDay.floor(fromDate), d3.utcDay.offset(d3.utcDay.floor(toDateV), 1));
  return days.map(d => ({ date: d, ...pollAverage(new Date(d.getTime() + 12 * 36e5)) }));
}

function renderPolls() {
  const root = $('#tab-polls');
  const { parties, polls } = S.polls;
  if (!S.trendParties) S.trendParties = new Set(['Likud', 'Yashar', 'Together', 'The Democrats', 'Joint List', "Ra'am"]);
  const houses = [...new Set(polls.map(p => p.house))];
  root.innerHTML = `
  <div class="section-head"><div>
    <span class="eyebrow">${polls.length} סקרים · ${houses.length} סוקרים · ${polls.filter(p => p.filing).length} עם קובץ דיווח רשמי לוועדת הבחירות</span>
    <h2>מגמות בסקרים</h2>
    <p>כל נקודה היא סקר שפורסם; הקו הוא הממוצע המשוקלל ביום נתון (מחצית משקל אחרי ${S.halfLife} ימים, תיקון לגודל מדגם ולסוקרים שמפרסמים הרבה). כשהמתג פעיל, הממוצע מתוקן להטיה הקבועה של כל סוקר.</p>
  </div></div>
  <div class="controls">
    <label class="toggle"><input type="checkbox" id="pl-adj" ${S.adjustHouse ? 'checked' : ''}> תיקון הטיית סוקרים</label>
    <span class="ctl-label">מחצית משקל אחרי</span>${seg('pl-hl', [['7', '7 ימים'], ['10', '10 ימים'], ['14', '14 ימים']], String(S.halfLife))}
  </div>
  <div class="grid">
    <div class="card c12">
      <h3>מנדטים לפי רשימה</h3>
      <p class="sub">בחרו רשימות להצגה. קו 27.10 מסמן את יום הבחירות; אזור אחוז החסימה בתחתית.</p>
      <div class="chips" id="pl-chips" style="margin-bottom:12px">${parties.filter(p => d3.max(polls, q => q.seats[p.id] || 0) > 0).map(p =>
        `<button type="button" class="slip" data-id="${esc(p.id)}" aria-pressed="${S.trendParties.has(p.id)}"><i class="dot" style="background:${party26Color(p)}"></i><b class="let">${esc(p.letters)}</b><span class="nm">${esc(p.name)}</span></button>`).join('')}</div>
      <div class="chart" id="pl-trend"></div>
    </div>
    <div class="card c7">
      <h3>הגושים לאורך זמן</h3>
      <p class="sub">סך המנדטים לגוש בכל סקר, והממוצע המשוקלל. את שיוך הרשימות לגושים אפשר לשנות במחשבון הקואליציות.</p>
      <div class="chart" id="pl-blocs"></div>
      <div class="legend"><span><i class="line" style="background:var(--coal)"></i>גוש נתניהו</span><span><i class="line" style="background:var(--opp)"></i>האופוזיציה</span><span><i class="line" style="background:var(--arab)"></i>הרשימות הערביות</span></div>
    </div>
    <div class="card c5">
      <h3>הטיית סוקרים</h3>
      <p class="sub">בכמה מנדטים כל סוקר נותן לרשימה יותר (סגול) או פחות (חום) מהממוצע של כל הסקרים. אצל סוקרים עם מעט סקרים ההטיה מוקטנת לכיוון אפס.</p>
      <div class="chart" id="pl-house"></div>
    </div>
    <div class="card c12">
      <h3>כל הסקרים</h3>
      <p class="sub">מהחדש לישן. ⎙ מסמן סקר שנמצא לו קובץ דיווח רשמי לוועדת הבחירות, לפי חוק הבחירות (דרכי תעמולה).</p>
      <div class="controls"><span class="ctl-label">סוקר</span><select id="pl-house-sel"><option value="all">כל הסוקרים</option>${houses.map(h => `<option value="${esc(h)}" ${S.pollHouse === h ? 'selected' : ''}>${esc(polls.find(p => p.house === h).house_he)}</option>`).join('')}</select></div>
      <div class="tbl-wrap scroll-y" id="pl-table"></div>
      <p class="foot">${esc(S.polls.source)}.</p>
    </div>
  </div>`;
  const redraw = () => { drawTrend(); drawBlocTrend(); drawHouse(); drawPollTable(); };
  $('#pl-adj').addEventListener('change', e => { S.adjustHouse = e.target.checked; invalidatePolls(); redraw(); });
  onSeg(root, 'pl-hl', v => { S.halfLife = +v; invalidatePolls(); redraw(); });
  $('#pl-chips').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    const id = b.dataset.id;
    S.trendParties.has(id) ? S.trendParties.delete(id) : S.trendParties.add(id);
    b.setAttribute('aria-pressed', S.trendParties.has(id)); drawTrend();
  });
  $('#pl-house-sel').addEventListener('change', e => { S.pollHouse = e.target.value; drawPollTable(); });
  redraw();
}

function timeScale(W, M) {
  const first = d3.utcDay.offset(toDate(S.polls.polls[0].date), -2);
  // on phones the empty run-up to election day is cut so the data gets the width
  const last = W < 560 ? d3.utcDay.offset(latestDate(), 3) : toDate('2026-10-27');
  return d3.scaleUtc().domain([first, last]).range([M.l, W - M.r]);
}
function timeAxis(svg, x, H, M, W = 800) {
  const ticks = x.ticks(d3.utcWeek.every(W < 560 ? 2 : 1));
  ticks.forEach(t => {
    svg.append('line').attr('class', 'gridline').attr('x1', x(t)).attr('x2', x(t)).attr('y1', M.t).attr('y2', H - M.b);
    svg.append('text').attr('class', 'lbl').attr('x', x(t)).attr('y', H - M.b + 16).attr('text-anchor', 'middle')
      .text(t.toLocaleDateString('he-IL', { day: 'numeric', month: 'numeric', timeZone: 'UTC' }));
  });
  if (x.domain()[1] >= toDate('2026-10-27')) {
    const ed = x(toDate('2026-10-27'));
    svg.append('line').attr('class', 'ref-line').attr('x1', ed).attr('x2', ed).attr('y1', M.t - 6).attr('y2', H - M.b);
    svg.append('text').attr('class', 'ref-text').attr('x', ed).attr('y', M.t - 10).attr('text-anchor', 'middle').text('יום הבחירות');
  }
}

function placeLabels(items, minGap, lo, hi) {
  // simple vertical relaxation so end labels do not overlap
  items.sort((a, b) => a.y - b.y);
  for (let it = 0; it < 60; it++) {
    let moved = false;
    for (let i = 1; i < items.length; i++) {
      const d = items[i].y - items[i - 1].y;
      if (d < minGap) { const s = (minGap - d) / 2; items[i].y += s; items[i - 1].y -= s; moved = true; }
    }
    items.forEach(o => { o.y = Math.max(lo, Math.min(hi, o.y)); });
    if (!moved) break;
  }
  return items;
}

function drawTrend() {
  const el = $('#pl-trend'); const { polls, parties } = S.polls;
  const W = widthOf(el), H = 380, M = { t: 24, r: W < 560 ? 64 : 120, b: 28, l: 34 };
  const svg = svgEl(el, W, H);
  const x = timeScale(W, M);
  const sel = parties.filter(p => S.trendParties.has(p.id));
  const maxY = Math.max(10, d3.max(sel, p => d3.max(polls, q => q.seats[p.id] || 0)) || 10) + 2;
  const y = d3.scaleLinear().domain([0, maxY]).range([H - M.b, M.t]);
  svg.append('rect').attr('class', 'zone').attr('x', M.l).attr('width', W - M.l - M.r).attr('y', y(3.9)).attr('height', y(0) - y(3.9));
  svg.append('line').attr('class', 'ref-line').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(3.9)).attr('y2', y(3.9)).style('opacity', .5);
  svg.append('text').attr('class', 'lbl halo').attr('x', M.l + 4).attr('y', y(3.9) + 12).attr('text-anchor', 'end').text('אחוז החסימה (כ-4)');
  y.ticks(6).forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 8).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v);
  });
  timeAxis(svg, x, H, M, W);
  const series = dailyAverages(toDate(polls[0].date), latestDate());
  const labels = [];
  sel.forEach(p => {
    const c = party26Color(p);
    svg.append('g').selectAll('circle').data(polls.filter(q => q.seats[p.id] != null)).join('circle')
      .attr('cx', q => x(toDate(q.date))).attr('cy', q => y(q.seats[p.id] || 0)).attr('r', 3)
      .attr('fill', c).attr('opacity', .28)
      .call(s => bindTT(s, q => `<h4>${esc(p.name)}: ${q.seats[p.id] || 0}</h4>${ttRows([['סוקר', esc(q.house_he)], ['גוף', esc(q.outlet_he)], ['תאריך', toDate(q.date).toLocaleDateString('he-IL', { timeZone: 'UTC' })]])}`));
    const line = d3.line().x(d => x(d.date)).y(d => y(d.avg[p.id])).curve(d3.curveMonotoneX);
    svg.append('path').attr('d', line(series)).attr('fill', 'none').attr('stroke', c).attr('stroke-width', 2.5).attr('stroke-linecap', 'round');
    const last = series[series.length - 1];
    svg.append('circle').attr('cx', x(last.date)).attr('cy', y(last.avg[p.id])).attr('r', 4).attr('fill', c).attr('stroke', 'var(--surface)').attr('stroke-width', 2);
    labels.push({ p, y: y(last.avg[p.id]), v: last.avg[p.id], x: x(last.date) });
  });
  placeLabels(labels, 15, M.t, H - M.b).forEach(o => {
    svg.append('text').attr('class', 'lbl-strong').attr('x', o.x + 10).attr('y', o.y).attr('dy', '.35em').attr('text-anchor', 'end')
      .text(W < 560 ? `${o.p.letters} ${fmt1(o.v)}` : `${o.p.name} ${fmt1(o.v)}`);
  });
  // crosshair
  const cross = svg.append('line').attr('y1', M.t).attr('y2', H - M.b).attr('stroke', 'var(--ink)').attr('stroke-width', 1).attr('opacity', 0);
  svg.append('rect').attr('x', M.l).attr('y', M.t).attr('width', W - M.l - M.r).attr('height', H - M.t - M.b).attr('fill', 'transparent')
    .on('mousemove', ev => {
      const [mx] = d3.pointer(ev); const d = x.invert(mx);
      const i = d3.bisector(s => s.date).center(series, d); const s = series[i]; if (!s) return;
      cross.attr('x1', x(s.date)).attr('x2', x(s.date)).attr('opacity', .35);
      tt.show(`<h4>${s.date.toLocaleDateString('he-IL', { timeZone: 'UTC', day: 'numeric', month: 'long' })}</h4>${ttRows(sel.map(p => [p.name, fmt1(s.avg[p.id]), party26Color(p)]).sort((a, b) => parseFloat(b[1]) - parseFloat(a[1])))}`, ev);
    })
    .on('mouseleave', () => { cross.attr('opacity', 0); tt.hide(); })
    .lower();
}

function pollBlocs(q, blocs = currentBlocs()) {
  const t = { coal: 0, opp: 0, arab: 0 };
  Object.entries(q.seats).forEach(([k, v]) => { if (blocs[k]) t[blocs[k]] += v; });
  return t;
}
function drawBlocTrend() {
  const el = $('#pl-blocs'); const { polls } = S.polls;
  const W = widthOf(el), H = 300, M = { t: 24, r: 46, b: 28, l: 34 };
  const svg = svgEl(el, W, H);
  const x = timeScale(W, M);
  const y = d3.scaleLinear().domain([0, 70]).range([H - M.b, M.t]);
  [0, 20, 40, 61].forEach(v => {
    svg.append('line').attr('class', v === 61 ? 'ref-line' : 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', v === 61 ? 'ref-text' : 'lbl').attr('x', M.l - 8).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v);
  });
  timeAxis(svg, x, H, M, W);
  const series = dailyAverages(toDate(polls[0].date), latestDate()).map(s => ({ date: s.date, ...blocTotals(s.avg) }));
  const l = series[series.length - 1], labels = [];
  ['coal', 'opp', 'arab'].forEach(b => {
    const c = blocColor(b);
    svg.append('g').selectAll('circle').data(polls).join('circle').attr('cx', q => x(toDate(q.date))).attr('cy', q => y(pollBlocs(q)[b]))
      .attr('r', 2.6).attr('fill', c).attr('opacity', .3);
    svg.append('path').attr('d', d3.line().x(d => x(d.date)).y(d => y(d[b])).curve(d3.curveMonotoneX)(series))
      .attr('fill', 'none').attr('stroke', c).attr('stroke-width', 2.5);
    labels.push({ b, y: y(l[b]), v: l[b] });
  });
  placeLabels(labels, 14, M.t, H - M.b).forEach(o => svg.append('text').attr('class', 'lbl-strong').attr('x', x(l.date) + 8)
    .attr('y', o.y).attr('dy', '.35em').attr('text-anchor', 'end').text(fmt1(o.v)));
}

function drawHouse() {
  const el = $('#pl-house'); const { polls, parties } = S.polls;
  const he = houseEffects(polls, parties);
  const houses = Object.keys(he).filter(h => he[h]._n >= 2).sort((a, b) => he[b]._n - he[a]._n);
  const cols = parties.filter(p => d3.mean(polls, q => q.seats[p.id] || 0) >= 3);
  const W = widthOf(el, 480), LW = W < 560 ? 92 : 150, cw = Math.max(14, (W - LW) / cols.length), rh = 26, M = { t: 64, l: 0 };
  const H = M.t + rh * houses.length + 6;
  const svg = svgEl(el, W, H);
  // diverging pair that is not a bloc colour: brown = fewer seats than average, violet = more
  const color = d3.scaleLinear().domain([-3, 0, 3]).range(['#b45f06', cssVar('--surface-2') || '#eee', '#5b5bd6']).interpolate(d3.interpolateLab).clamp(true);
  cols.forEach((p, j) => {
    const cx = W - LW - j * cw - cw / 2;
    svg.append('text').attr('class', 'lbl').attr('transform', `translate(${cx},${M.t - 8}) rotate(-50)`).attr('text-anchor', 'end').text(p.name);
  });
  houses.forEach((h, i) => {
    const yy = M.t + i * rh;
    const name = polls.find(p => p.house === h).house_he;
    let lab = W < 560 ? name.split(' (')[0] : `${name} (${he[h]._n})`;
    const fs = W < 560 ? 10.5 : 12.5;
    while (lab.length > 4 && textWidth(lab, fs) > LW - 8) lab = lab.slice(0, -2).trim() + '…';
    svg.append('text').attr('class', 'lbl-ink').attr('x', W - 2).attr('y', yy + rh / 2).attr('dy', '.35em').attr('text-anchor', 'start').style('font-size', fs + 'px').text(lab)
      .append('title').text(`${name} (${he[h]._n} סקרים)`);
    cols.forEach((p, j) => {
      const v = he[h][p.id];
      const cx = W - LW - (j + 1) * cw;
      svg.append('rect').attr('x', cx + 1).attr('y', yy + 1).attr('width', cw - 2).attr('height', rh - 2).attr('rx', 3).attr('fill', color(v))
        .call(s => bindTT(s, () => `<h4>${esc(name)} · ${esc(p.name)}</h4>${ttRows([['הטיה (מנדטים)', (v > 0 ? '+' : '') + fmt1(v)], ['סקרים', he[h]._n]])}`));
      if (Math.abs(v) >= 1 && cw >= 26) svg.append('text').attr('class', 'lbl').attr('x', cx + cw / 2).attr('y', yy + rh / 2).attr('dy', '.35em').attr('text-anchor', 'middle')
        .style('direction', 'ltr').style('fill', onFill(color(v))).style('font-size', '10.5px').text((v > 0 ? '+' : '−') + fmt1(Math.abs(v)));
    });
  });
}

function drawPollTable() {
  const { polls, parties } = S.polls;
  const cols = parties.filter(p => d3.max(polls, q => q.seats[p.id] || 0) > 0);
  const rows = polls.filter(p => S.pollHouse === 'all' || p.house === S.pollHouse).slice().reverse();
  $('#pl-table').innerHTML = `<table class="t"><thead><tr><th>תאריך</th><th>סוקר</th><th>גוף</th><th class="n">מדגם</th>${cols.map(p => `<th class="n" title="${esc(p.name)}">${esc(p.letters)}</th>`).join('')}<th class="n">גוש נתניהו</th><th class="n">אופוזיציה</th><th class="n">ערביות</th><th></th></tr></thead><tbody>${
    rows.map(q => { const b = pollBlocs(q); return `<tr><td>${toDate(q.date).toLocaleDateString('he-IL', { timeZone: 'UTC', day: 'numeric', month: 'numeric' })}</td><td>${esc(q.house_he)}</td><td>${esc(q.outlet_he)}</td><td class="n">${q.n ? fmt(q.n) : '—'}</td>${cols.map(p => `<td class="n">${q.seats[p.id] ?? 0}</td>`).join('')}<td class="n"><b>${b.coal}</b></td><td class="n">${b.opp}</td><td class="n">${b.arab}</td><td>${q.filing ? `<a href="${esc(q.filing)}" target="_blank" rel="noopener" title="קובץ הדיווח לוועדת הבחירות">⎙</a>` : ''}</td></tr>`; }).join('')
  }</tbody></table>`;
}
