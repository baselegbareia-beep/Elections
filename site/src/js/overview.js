/* ===================== overview ===================== */
function currentBlocs() {
  if (!S.coalitionBlocs) S.coalitionBlocs = Object.fromEntries(S.polls.parties.map(p => [p.id, p.bloc]));
  return S.coalitionBlocs;
}
function ensureSims() {
  if (S.sims) return S.sims;
  const av = pollAverage(latestDate());
  S.avg = av;
  S.shares = voteSharesFromAverage(av.avg);
  S.seatsNow = baderOfer({ ...S.shares }, { agreements: AGREEMENTS_2026 });
  S.sims = simulate(S.shares, currentBlocs());
  return S.sims;
}
function blocTotals(seats, blocs = currentBlocs()) {
  const t = { coal: 0, opp: 0, arab: 0 };
  S.polls.parties.forEach(p => { t[blocs[p.id]] = (t[blocs[p.id]] || 0) + (seats[p.id] || 0); });
  return t;
}

function renderOverview() {
  const root = $('#tab-overview');
  const sims = ensureSims();
  const av = S.avg, parties = S.polls.parties;
  const blocs = currentBlocs();
  const seatAvg = blocTotals(av.avg);
  const members = k => parties.filter(p => blocs[p.id] === k).map(p => p.id);
  const coalSim = simSummary(sims, members('coal'));
  const oppSim = simSummary(sims, members('opp'));
  const oppArab = simSummary(sims, [...members('opp'), ...members('arab')]);
  const last = S.polls.polls[S.polls.polls.length - 1];
  const k25 = E('K25');
  const arab25 = k25.sectors.arab_std, jew25 = k25.sectors.jewish;

  // threshold watch
  const passP = parties.map((p, i) => ({ p, prob: sims.seats.filter(s => s[i] > 0).length / sims.seats.length, avg: av.avg[p.id] }))
    .filter(x => x.prob > 0.02 && x.prob < 0.995).sort((a, b) => a.prob - b.prob);

  root.innerHTML = `
  <div class="section-head"><div>
    <span class="eyebrow">נכון ל-${new Date(last.date).toLocaleDateString('he-IL', { day: 'numeric', month: 'long', year: 'numeric' })} · ${av.n} סקרים ב-28 הימים האחרונים</span>
    <h2>מי מגיע ל-61?</h2>
    <p>ממוצע סקרים משוקלל לפי עדכניות וגודל מדגם, מתוקנן להטיית סוקרים. ממנו נגזרים ${fmt(sims.seats.length)} תרחישים של חלוקת מושבים לפי שיטת בדר-עופר ואחוז החסימה.</p>
  </div></div>
  <div class="grid">
    <div class="card c3 tile"><span class="l"><i class="swatch" style="background:var(--coal)"></i>גוש נתניהו (ממוצע)</span><span class="v num">${fmt1(seatAvg.coal)}</span><span class="d">ב-${pct(100 * coalSim.p61, 0)} מהתרחישים: 61 ומעלה</span></div>
    <div class="card c3 tile"><span class="l"><i class="swatch" style="background:var(--opp)"></i>האופוזיציה היהודית (ממוצע)</span><span class="v num">${fmt1(seatAvg.opp)}</span><span class="d">לבדה 61+: ${pct(100 * oppSim.p61, 0)} · עם הרשימות הערביות: ${pct(100 * oppArab.p61, 0)}</span></div>
    <div class="card c3 tile"><span class="l"><i class="swatch" style="background:var(--arab)"></i>הרשימה המשותפת + רע״ם</span><span class="v num">${fmt1(seatAvg.arab)}</span><span class="d">בכנסת ה-25: 10 מושבים (רע״ם 5, חד״ש-תע״ל 5)</span></div>
    <div class="card c3 tile"><span class="l">שיעור ההצבעה בחברה הערבית, 2022</span><span class="v num">${pct(100 * arab25.voters / arab25.elig)}</span><span class="d">ביישובים הערביים והדרוזיים, מול ${pct(100 * jew25.voters / jew25.elig)} ביהודים ואחרים</span></div>

    <div class="card c7">
      <h3>ממוצע הסקרים, לפי רשימה</h3>
      <p class="sub">מנדטים בממוצע המשוקלל; הקו הדק מראה את הטווח בין הסקר הנמוך לגבוה ב-28 הימים האחרונים. אזור אחוז החסימה מסומן.</p>
      <div class="chart" id="ov-bars"></div>
      <p class="foot">המקור: ${S.polls.polls.length} סקרים שפורסמו מ-6 בספטמבר 2026 ואילך (אחרי סגירת הרשימות), ללא כפילויות. החל מסוף יום שישי, 23.10, אסור לפרסם סקרים עד סגירת הקלפיות.</p>
    </div>
    <div class="card c5">
      <h3>הגושים בתרחישים</h3>
      <p class="sub">כמה מושבים מקבל גוש נתניהו ב-${fmt(sims.seats.length)} סימולציות. כל עמודה היא מספר מושבים אפשרי, גובהה הוא שכיחותו.</p>
      <div class="chart" id="ov-hist"></div>
      <div class="legend"><span><i style="background:var(--coal)"></i>61 ומעלה (רוב)</span><span><i style="background:var(--rule-strong)"></i>פחות מ-61</span></div>
      <p class="foot">מודל הדגמה. אי-הוודאות מכוילת לפי טעויות הסקרים האחרונים ב-2019–2022: תזוזה משותפת בין הגושים (סטיית תקן 2.4 נק׳ אחוז, כ-3 מושבים), זעזוע משותף להצבעה לרשימות הערביות (13%) ורעש לכל רשימה. 80% מהתרחישים: ${N(coalSim.q10)}–${N(coalSim.q90)} מושבים.</p>
    </div>

    <div class="card c7">
      <h3>הכנסת לפי הממוצע</h3>
      <p class="sub">חלוקת 120 המושבים לפי ממוצע הסקרים, אחרי אחוז החסימה וחלוקת העודפים לפי הסכמי העודפים שדווחו (ליכוד–הציונות הדתית, ישר!–הדמוקרטים, ביחד–ישראל ביתנו, רע״ם–הרשימה המשותפת).</p>
      <div class="chart" id="ov-strip"></div>
    </div>
    <div class="card c5">
      <h3>מעקב אחוז החסימה</h3>
      <p class="sub">הסיכוי של כל רשימה לעבור 3.25% בתרחישים.</p>
      <div id="ov-thr" class="tbl-wrap"></div>
    </div>

    <div class="card c12">
      <h3>שלושה דברים שכדאי לדעת</h3>
      <ul class="callout-list" style="margin-top:12px">
        <li><span class="n">1</span><p><b>השתתפות הערבים מכריעה את הגושים.</b> בין 2020 ל-2021 צנח שיעור ההצבעה בחברה הערבית מ-${pct(rate('K23', 'arab_std'))} ל-${pct(rate('K24', 'arab_std'))}. במחשבון הקואליציות אפשר לראות כמה מושבים זז הגוש כשההשתתפות משתנה.</p></li>
        <li><span class="n">2</span><p><b>קולות שהולכים לפח.</b> ב-2022 לא עברו את אחוז החסימה מרצ (${fmt(k25.parties.find(p => p.id === 'מרצ').votes)} קולות) ובל״ד (${fmt(k25.parties.find(p => p.id === 'ד').votes)}). ${passP.length ? `השנה בסכנה: ${passP.slice(0, 3).map(x => x.p.name).join(', ')}.` : ''}</p></li>
        <li><span class="n">3</span><p><b>הפילוג הערבי חזר בצורה חדשה.</b> חד״ש, תע״ל ובל״ד רצים יחד כ״הרשימה המשותפת״, ורע״ם לבדה. ועדת הבחירות פסלה את שתיהן ב-23.9.2026, ובית המשפט העליון ביטל את הפסילה פה אחד ב-2.10.2026.</p></li>
      </ul>
    </div>
  </div>`;

  drawSeatBars($('#ov-bars'), av);
  drawHistogram($('#ov-hist'), coalSim.tot);
  drawStrip($('#ov-strip'), S.seatsNow);
  $('#ov-thr').innerHTML = passP.length ? `<table class="t"><thead><tr><th>רשימה</th><th class="n">ממוצע</th><th class="n">סיכוי לעבור</th><th>הערכה</th></tr></thead><tbody>${
    passP.map(x => {
      const band = x.prob > 0.95 ? ['בטוחה', 'ok'] : x.prob > 0.68 ? ['כנראה עוברת', 'ok'] : x.prob > 0.32 ? ['על הגדר', 'no'] : ['כנראה בחוץ', 'no'];
      return `<tr><td>${slip(x.p.letters, x.p.name, party26Color(x.p))}</td><td class="n">${fmt1(x.avg)}</td><td class="n">${pct(100 * x.prob, 0)}</td><td><span class="status ${band[1]}">${band[1] === 'ok' ? ICON_OK : ICON_NO}${band[0]}</span></td></tr>`;
    }).join('')}</tbody></table>` : '<p class="empty">כל הרשימות רחוקות מהסף.</p>';
}
function rate(eid, sector) { const s = E(eid).sectors[sector]; return 100 * s.voters / s.elig; }

function drawSeatBars(el, av) {
  const parties = [...S.polls.parties].filter(p => av.hi[p.id] > 0 || av.avg[p.id] > 0.3).sort((a, b) => av.avg[b.id] - av.avg[a.id]);
  const W = widthOf(el), rowH = 30, M = { t: 22, r: 150, b: 10, l: 40 };
  const H = M.t + M.b + rowH * parties.length;
  const svg = svgEl(el, W, H);
  const maxV = Math.max(30, d3.max(parties, p => av.hi[p.id]));
  const x = d3.scaleLinear().domain([0, maxV]).range([W - M.r, M.l]);
  const y = (i) => M.t + i * rowH;
  svg.append('rect').attr('class', 'zone').attr('x', x(3.9)).attr('y', M.t - 6).attr('width', x(0) - x(3.9)).attr('height', H - M.t - M.b + 6);
  svg.append('text').attr('class', 'lbl').attr('x', x(0)).attr('y', M.t - 10).attr('text-anchor', 'start').text('אזור אחוז החסימה');
  [0, 10, 20, 30].filter(v => v <= maxV).forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', x(v)).attr('x2', x(v)).attr('y1', M.t - 4).attr('y2', H - M.b);
    svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H).attr('text-anchor', 'middle').text(v);
  });
  const g = svg.selectAll('g.row').data(parties).join('g').attr('transform', (d, i) => `translate(0,${y(i)})`);
  // SVG text inherits the page's RTL direction: anchor 'start' = right edge.
  g.append('text').attr('x', W - 2).attr('y', rowH / 2).attr('dy', '.35em').attr('text-anchor', 'start')
    .style('font', '700 16px var(--font-display)').style('fill', 'var(--ink)').text(d => d.letters);
  g.append('text').attr('class', 'lbl-ink').attr('x', W - 42).attr('y', rowH / 2).attr('dy', '.35em').attr('text-anchor', 'start')
    .text(d => d.name);
  g.append('line').attr('x1', d => x(av.lo[d.id])).attr('x2', d => x(av.hi[d.id])).attr('y1', rowH / 2).attr('y2', rowH / 2)
    .attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5);
  g.append('rect').attr('x', d => x(av.avg[d.id])).attr('y', rowH / 2 - 7).attr('height', 14)
    .attr('width', d => Math.max(0, x(0) - x(av.avg[d.id]))).attr('rx', 3).attr('fill', d => party26Color(d));
  g.append('text').attr('class', 'lbl-strong').attr('x', d => x(av.avg[d.id]) - 6).attr('y', rowH / 2).attr('dy', '.35em').attr('text-anchor', 'start')
    .text(d => fmt1(av.avg[d.id]));
  g.append('rect').attr('x', 0).attr('y', 0).attr('width', W).attr('height', rowH).attr('fill', 'transparent')
    .call(sel => bindTT(sel, d => `<h4>${esc(d.name)} <span class="slip"><b class="let">${esc(d.letters)}</b></span></h4>${ttRows([
      ['בראשות', esc(d.leader)], ['ממוצע משוקלל', fmt1(av.avg[d.id])], ['טווח הסקרים', `${av.lo[d.id]}–${av.hi[d.id]}`], ['גוש (ברירת מחדל)', BLOC_NAME[d.bloc]]])}`));
}

function drawHistogram(el, totals) {
  const W = widthOf(el, 480), H = 230, M = { t: 18, r: 12, b: 30, l: 12 };
  const svg = svgEl(el, W, H);
  const counts = d3.rollup(totals, v => v.length, d => d);
  const xs = d3.range(d3.min(totals), d3.max(totals) + 1);
  const x = d3.scaleBand().domain(xs).range([W - M.r, M.l]).padding(0.12);  // RTL: fewer seats on the right
  const y = d3.scaleLinear().domain([0, d3.max(xs, v => counts.get(v) || 0)]).range([H - M.b, M.t]);
  svg.selectAll('rect').data(xs).join('rect')
    .attr('x', d => x(d)).attr('width', x.bandwidth()).attr('y', d => y(counts.get(d) || 0))
    .attr('height', d => H - M.b - y(counts.get(d) || 0)).attr('rx', Math.min(3, x.bandwidth() / 3))
    .attr('fill', d => d >= 61 ? 'var(--coal)' : 'var(--rule-strong)')
    .call(sel => bindTT(sel, d => `<h4>${d} מושבים</h4>${ttRows([['תרחישים', fmt(counts.get(d) || 0)], ['שיעור', pct(100 * (counts.get(d) || 0) / totals.length)]])}`));
  const x61 = x(61) !== undefined ? x(61) + x.bandwidth() + (x.step() * x.padding()) / 2 : null;
  if (x61 != null) {
    svg.append('line').attr('class', 'ref-line').attr('x1', x61).attr('x2', x61).attr('y1', M.t - 6).attr('y2', H - M.b);
    svg.append('text').attr('class', 'ref-text').attr('x', x61).attr('y', M.t - 9).attr('text-anchor', 'middle').text('רוב: 61');
  }
  xs.filter(v => v % 5 === 0).forEach(v => svg.append('text').attr('class', 'lbl').attr('x', x(v) + x.bandwidth() / 2).attr('y', H - 10).attr('text-anchor', 'middle').text(v));
}

function drawStrip(el, seats) {
  // 120 squares in reading order (right to left), grouped by bloc, each square a seat
  const parties = S.polls.parties.filter(p => seats[p.id] > 0);
  const blocs = currentBlocs();
  const order = ['coal', 'opp', 'arab'];
  parties.sort((a, b) => order.indexOf(blocs[a.id]) - order.indexOf(blocs[b.id]) || seats[b.id] - seats[a.id]);
  const W = widthOf(el), cols = 30, gap = 3, size = Math.min(22, (W - gap * (cols - 1)) / cols), H = 4 * (size + gap) + 70;
  const svg = svgEl(el, W, H);
  const cells = [];
  parties.forEach(p => { for (let i = 0; i < seats[p.id]; i++) cells.push(p); });
  svg.selectAll('rect.seat').data(cells).join('rect').attr('class', 'seat')
    .attr('x', (d, i) => W - (Math.floor(i / 4) + 1) * (size + gap) + gap)
    .attr('y', (d, i) => (i % 4) * (size + gap))
    .attr('width', size).attr('height', size).attr('rx', 3)
    .attr('fill', d => party26Color(d))
    .call(sel => bindTT(sel, d => `<h4>${esc(d.name)}</h4>${ttRows([['מושבים', seats[d.id]], ['גוש', BLOC_NAME[blocs[d.id]]]])}`));
  // 61 marker after the 61st seat
  const mx = W - 15 * (size + gap) + gap / 2;   // 60 seats to the right of this line
  svg.append('line').attr('class', 'ref-line').attr('x1', mx).attr('x2', mx).attr('y1', -4).attr('y2', 4 * (size + gap) + 4);
  svg.append('text').attr('class', 'ref-text').attr('x', mx).attr('y', 4 * (size + gap) + 15).attr('text-anchor', 'middle').text('61');
  // labels under the strip for each bloc
  let start = 0;
  order.forEach(b => {
    const n = sum(parties.filter(p => blocs[p.id] === b).map(p => seats[p.id]));
    if (!n) { return; }
    const xa = W - Math.floor(start / 4) * (size + gap), xb = W - Math.ceil((start + n) / 4) * (size + gap) + gap;
    svg.append('line').attr('x1', xa).attr('x2', xb).attr('y1', 4 * (size + gap) + 30).attr('y2', 4 * (size + gap) + 30).attr('stroke', blocColor(b)).attr('stroke-width', 3);
    const short = { coal: 'גוש נתניהו', opp: 'אופוזיציה', arab: 'ערביות' }[b];
    const label = `${W < 560 ? short : BLOC_NAME[b]} · ${n}`;
    const mid = Math.max(40, Math.min(W - 40, (xa + xb) / 2));
    svg.append('text').attr('class', 'lbl-strong').attr('x', mid).attr('y', 4 * (size + gap) + 50).attr('text-anchor', 'middle').text(label);
    start += n;
  });
}
