/* ===================== Arab society hub ===================== */
const ELS = ['K21', 'K22', 'K23', 'K24', 'K25'];
const sectorRate = (eid, key, sub = false) => {
  const s = sub ? E(eid).subsectors[key] : E(eid).sectors[key];
  return s && s.elig ? 100 * s.voters / s.elig : null;
};
const arabLists = eid => E(eid).parties.filter(p => p.bloc === 'arab');

function renderArab() {
  const root = $('#tab-arab');
  const k25 = E('K25');
  const a25 = k25.sectors.arab_std;
  const arabListVotes25 = sum(arabLists('K25').map(p => a25.votes[p.id] || 0));
  const totalElig = k25.eligible;
  const balad = k25.parties.find(p => p.id === 'ד');
  const av = ensureSims() && S.avg;
  root.innerHTML = `
  <div class="section-head"><div>
    <span class="eyebrow">${t('מוקד · החברה הערבית בבחירות')}</span>
    <h2>${t('החברה הערבית: השתתפות, פיצולים והכוח לקבוע')}</h2>
    <p>${t('כל הנתונים בעמוד מחושבים מתוצאות הקלפיות הרשמיות. הכותרות משתמשות בהגדרה המקובלת במחקר (המכון הישראלי לדמוקרטיה, מרכז משה דיין): סך היישובים הערביים והדרוזיים. הערים המעורבות מוצגות בנפרד, ברמת הקלפי. החישוב משחזר את הנתונים שפרסם המכון הישראלי לדמוקרטיה בהפרש של עד 0.1 נקודה.')}</p>
  </div></div>
  <div class="grid">
    <div class="card c3 tile"><span class="l">${t('בעלי זכות בחירה ביישובים ערביים ודרוזיים, 2022')}</span><span class="v num">${fmt(a25.elig)}</span><span class="d">${t('{p} מפנקס הבוחרים, ועוד {n} בקלפיות ערביות בערים מעורבות', { p: pct(100 * a25.elig / totalElig), n: fmt(k25.subsectors['arab:mixed'].elig) })}</span></div>
    <div class="card c3 tile"><span class="l">${t('פער ההצבעה מול יהודים ואחרים, 2022')}</span><span class="v num">${fmt1(sectorRate('K25', 'jewish') - sectorRate('K25', 'arab_std'))}</span><span class="d">${t('נקודות אחוז: {a} מול {b}', { a: pct(sectorRate('K25', 'arab_std')), b: pct(sectorRate('K25', 'jewish')) })}</span></div>
    <div class="card c3 tile"><span class="l">${t('הצביעו לרשימות ערביות, 2022')}</span><span class="v num">${pct(100 * arabListVotes25 / a25.valid, 0)}</span><span class="d">${t('מהקולות הכשרים ביישובים הערביים והדרוזיים (המכון למחקרי ביטחון לאומי: 85.8%)')}</span></div>
    <div class="card c3 tile"><span class="l">${t('קולות שאבדו מתחת לאחוז החסימה')}</span><span class="v num">${fmt(balad.votes)}</span><span class="d">${t('בל״ד ב-2022, {p} מהקולות. חסרו {n} קולות למעבר', { p: pct(balad.pct, 2), n: fmt(k25.threshold_votes - balad.votes) })}</span></div>

    <div class="card c7">
      <h3>${t('שיעור ההצבעה לפי מגזר')}</h3>
      <p class="sub">${t('הקו העבה (בירוק) מייצג את היישובים הערביים והדרוזיים. הפער מול יהודים ואחרים נע בין {a} ל-{b} נקודות, והוא שמכריע כמה מנדטים יקבלו הרשימות הערביות.', { a: fmt(d3.min(ELS, e => sectorRate(e, 'jewish') - sectorRate(e, 'arab_std'))), b: fmt(d3.max(ELS, e => sectorRate(e, 'jewish') - sectorRate(e, 'arab_std'))) })}</p>
      <div class="chart" id="ar-turnout"></div>
      <div class="legend"><span><i class="line" style="background:var(--arab)"></i>${t('יישובים ערביים ודרוזיים')}</span><span><i class="line" style="background:transparent;border-top:2px dashed var(--arab);height:0"></i>${t('קלפיות ערביות בערים מעורבות')}</span><span><i class="line" style="background:var(--druze)"></i>${t('דרוזים בגליל ובכרמל')}</span><span><i class="line" style="background:var(--jewish)"></i>${t('יהודים ואחרים')}</span><span><i class="line" style="background:var(--muted)"></i>${t('ארצי (רשמי)')}</span></div>
      <p class="foot">${t('יהודים ואחרים = כל שאר הקלפיות וכל המעטפות הכפולות (חיילים, נציגויות, אסירים ומאושפזים), כולל מצביעים ערבים ודרוזים שהצביעו במעטפה. לכן השיעור שם מוטה מעט כלפי מעלה, ושיעור ההצבעה ביישובים הערביים, ובמיוחד הדרוזיים, מוטה מעט כלפי מטה. פנקס הבוחרים כולל גם ישראלים השוהים בחו״ל. המכון הישראלי לדמוקרטיה פרסם: 49.2%, 59.2%, 64.8%, 44.6%, 53.2%.')}</p>
    </div>
    <div class="card c5">
      <h3>${t('מנדטי הרשימות הערביות')}</h3>
      <p class="sub">${t('כל עמודה היא מערכת בחירות. האיחוד ב-2019–2020 הביא לשיא; הפיצולים הורידו מנדטים ושלחו קולות לפח.')}</p>
      <div class="chart" id="ar-seats"></div>
    </div>

    <div class="card c12">
      <h3>${t('למי הצביעו בקלפיות הערביות')}</h3>
      <p class="sub">${t('חלוקת הקולות הכשרים בקלפיות הערביות, לפי רשימה. הרשימות היהודיות מקובצות באפור; פירוט בריחוף.')}</p>
      <div class="chart" id="ar-comp"></div>
    </div>

    <div class="card c7">
      <div class="card-head"><div><h3>${t('לפי אזור')}</h3><p class="sub">${t('השתתפות והצבעה בכל אזור. רע״ם שולטת בנגב ובקרב הבדואים בצפון; חד״ש-תע״ל בנצרת ובכפרים הנוצריים; בל״ד חזקה בוואדי עארה.')}</p></div>${seg('ar-reg-el', ELS.map(e => [e, E(e).short]), S.arabRegEl)}</div>
      <div class="chart" id="ar-regions"></div>
    </div>
    <div class="card c5">
      <h3>${t('הרשימות הערביות בסקרי 2026')}</h3>
      <p class="sub">${t('כל נקודה היא סקר. הרשימה המשותפת (חד״ש, תע״ל ובל״ד) ורע״ם רצות בנפרד; אזור אחוז החסימה מסומן.')}</p>
      <div class="chart" id="ar-polls"></div>
      <ul class="callout-list" style="margin-top:12px">
        <li><span class="n" style="font-size:16px">${t('קיץ')}</span><p>${t('חד״ש, תע״ל ובל״ד חוזרות לרוץ יחד כ״הרשימה המשותפת״, בלי רע״ם (ההסכם דווח ב-19.8).')}</p></li>
        <li><span class="n" style="font-size:16px">23.9</span><p>${t('ועדת הבחירות המרכזית פוסלת את הרשימה המשותפת ואת רע״ם (18 מול 5).')}</p></li>
        <li><span class="n" style="font-size:16px">2.10</span><p>${t('בית המשפט העליון מבטל את הפסילה פה אחד; שתי הרשימות על פתק ההצבעה.')}</p></li>
      </ul>
    </div>

    <div class="card c12">
      <div class="card-head"><div><h3>${t('לאן עברו הקולות')}</h3><p class="sub">${t('אומדן לאן עברו בעלי זכות הבחירה בקלפיות הערביות בין שתי מערכות: מצביעי כל רשימה ומי שלא הצביע, באלפים. מבוסס על קלפיות שהותאמו בין שתי המערכות.')}</p></div>${seg('ar-pair', [[0, t('אפר׳ עד ספט׳ 2019')], [1, t('ספט׳ 2019 עד 2020')], [2, t('2020 עד 2021')], [3, t('2021 עד 2022')]].filter(([i]) => arabTransfer(i)), String(S.pairIdx))}</div>
      <div class="chart" id="ar-sankey"></div>
      <p class="foot" id="ar-sankey-foot"></p>
    </div>

    <div class="card c7">
      <div class="card-head"><div><h3>${t('הערים המעורבות')}</h3><p class="sub">${t('פיצול ברמת הקלפי: קלפיות שבהן הרשימות הערביות קיבלו רוב מול שאר הקלפיות באותה עיר.')}</p></div>${seg('ar-mix-el', ELS.map(e => [e, E(e).short]), S.arabMixEl)}</div>
      <div class="tbl-wrap" id="ar-mixed"></div>
    </div>
    <div class="card c5">
      <h3>${t('הדרוזים')}</h3>
      <p class="sub">${t('כ-90% מהקולות ב-11 היישובים הדרוזיים בגליל ובכרמל הולכים לרשימות יהודיות, ובעיקר לאלה עם מועמד דרוזי במקום ריאלי.')}</p>
      <div class="chart" id="ar-druze"></div>
    </div>
  </div>`;

  drawSectorTurnout($('#ar-turnout'));
  drawArabSeats($('#ar-seats'));
  drawArabComposition($('#ar-comp'));
  drawArabRegions($('#ar-regions'));
  drawArabPolls($('#ar-polls'));
  drawSankey($('#ar-sankey'));
  drawMixed($('#ar-mixed'));
  drawDruze($('#ar-druze'));
  onSeg(root, 'ar-reg-el', v => { S.arabRegEl = v; drawArabRegions($('#ar-regions')); });
  onSeg(root, 'ar-mix-el', v => { S.arabMixEl = v; drawMixed($('#ar-mixed')); });
  onSeg(root, 'ar-pair', v => { S.pairIdx = +v; drawSankey($('#ar-sankey')); });
}

function electionX(W, M) { return d3.scalePoint().domain(ELS).range([M.l, W - M.r]).padding(0.3); }

function drawSectorTurnout(el) {
  const W = widthOf(el), H = 310, M = { t: 30, r: 28, b: 40, l: 36 };
  const svg = svgEl(el, W, H, t('שיעור ההצבעה לפי מגזר בחמש מערכות הבחירות'));
  const x = electionX(W, M);
  const y = d3.scaleLinear().domain([30, 80]).range([H - M.b, M.t]);
  [30, 40, 50, 60, 70, 80].forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 8).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v + '%');
  });
  ELS.forEach(e => {
    svg.append('text').attr('class', 'lbl-ink').attr('x', x(e)).attr('y', H - 20).attr('text-anchor', 'middle').text(elLabel(e, W));
    if (W >= 560) svg.append('text').attr('class', 'lbl').attr('x', x(e)).attr('y', H - 5).attr('text-anchor', 'middle').text(E(e).label);
  });
  const series = [
    { k: 'arab_std', name: t('יישובים ערביים ודרוזיים'), c: 'var(--arab)', f: e => sectorRate(e, 'arab_std'), w: 3.2 },
    { k: 'mixed', name: t('קלפיות ערביות בערים מעורבות'), c: 'var(--arab)', f: e => sectorRate(e, 'arab:mixed', true), dash: '5 4' },
    { k: 'druze', name: t('דרוזים בגליל ובכרמל'), c: 'var(--druze)', f: e => sectorRate(e, 'druze:druze', true) },
    { k: 'jewish', name: t('יהודים ואחרים'), c: 'var(--jewish)', f: e => sectorRate(e, 'jewish') },
    { k: 'nat', name: t('ארצי (רשמי)'), c: 'var(--muted)', f: e => E(e).turnout, dash: '2 3' },
  ];
  series.forEach(s => {
    const pts = ELS.map(e => ({ e, v: s.f(e) }));
    svg.append('path').attr('d', d3.line().x(d => x(d.e)).y(d => y(d.v))(pts)).attr('fill', 'none').attr('stroke', s.c)
      .attr('stroke-width', s.w || 2).attr('stroke-dasharray', s.dash || null);
    svg.selectAll(null).data(pts).join('circle').attr('cx', d => x(d.e)).attr('cy', d => y(d.v)).attr('r', s.w ? 5 : 3.2)
      .attr('fill', s.dash && s.k === 'mixed' ? 'var(--surface)' : s.c).attr('stroke', s.k === 'mixed' ? s.c : 'var(--surface)').attr('stroke-width', 1.5)
      .call(sel => bindTT(sel, d => `<h4>${E(d.e).label}</h4>${ttRows(series.map(q => [q.name, pct(q.f(d.e)), cssVar(q.c.slice(4, -1))]))}`));
  });
  // value labels for the headline series, drawn last with a halo; flipped below the point when another series sits just above
  ELS.forEach(e => {
    const v = series[0].f(e);
    const clash = series.slice(1).some(q => { const qy = y(q.f(e)); return qy < y(v) && y(v) - qy < 22; });
    svg.append('text').attr('class', 'lbl-strong halo').style('font-size', '12.5px').attr('x', x(e)).attr('y', clash ? y(v) + 19 : y(v) - 11)
      .attr('text-anchor', 'middle').text(pct(v));
  });
  const ann = (e, v, text, dy) => svg.append('text').attr('class', 'lbl').attr('x', x(e)).attr('y', y(v) + dy).attr('text-anchor', 'middle').style('fill', 'var(--ink-2)').text(text);
  const nar = W < 560;
  svg.append('text').attr('class', 'lbl').attr('x', x('K23')).attr('y', y(nar ? 37 : 33)).attr('text-anchor', 'middle').style('fill', 'var(--ink-2)').text(nar ? t('משותפת') : t('רשימה משותפת אחת'));
  svg.append('text').attr('class', 'lbl').attr('x', x('K24')).attr('y', y(33)).attr('text-anchor', 'middle').style('fill', 'var(--ink-2)').text(nar ? t('פיצול') : t('הפיצול: רע״ם לבדה'));
}

function drawArabSeats(el) {
  const W = widthOf(el, 480), H = 300, M = { t: 18, r: 12, b: 40, l: 12 };
  const svg = svgEl(el, W, H, t('מנדטי הרשימות הערביות בכל מערכת בחירות ולפי ממוצע הסקרים של 2026'));
  const cols = [...ELS, 'K26'];
  const x = d3.scaleBand().domain(cols).range([M.l, W - M.r]).padding(0.28);   // chronological left to right, like the other charts
  const y = d3.scaleLinear().domain([0, 16]).range([H - M.b, M.t]);
  const av = S.avg.avg;
  cols.forEach(e => {
    let stack = 0;
    const lists = e === 'K26'
      ? S.polls.parties.filter(p => p.bloc === 'arab').map(p => ({ name: p.name, seats: av[p.id], color: party26Color(p), letters: p.letters }))
      : arabLists(e).map(p => ({ name: p.name, seats: p.seats, votes: p.votes, pct: p.pct, color: famColor(p.family), letters: p.id }));
    lists.filter(l => l.seats > 0).forEach(l => {
      const y0 = y(stack), y1 = y(stack + l.seats);
      svg.append('rect').attr('x', x(e)).attr('width', x.bandwidth()).attr('y', y1 + 1).attr('height', Math.max(0, y0 - y1 - 2)).attr('rx', 3)
        .attr('fill', l.color).attr('opacity', e === 'K26' ? 0.75 : 1)
        .call(sel => bindTT(sel, () => `<h4>${esc(l.name)}</h4>${ttRows([[e === 'K26' ? t('ממוצע סקרים') : t('מנדטים'), e === 'K26' ? fmt1(l.seats) : l.seats], ...(l.votes ? [[t('קולות'), fmt(l.votes)], [t('אחוז'), pct(l.pct, 2)]] : [])])}`));
      if (y0 - y1 > 16) svg.append('text').attr('class', 'lbl').attr('x', x(e) + x.bandwidth() / 2).attr('y', (y0 + y1) / 2).attr('dy', '.35em')
        .attr('text-anchor', 'middle').style('fill', onFill(l.color, e === 'K26' ? 0.75 : 1)).style('font-weight', 600).text(e === 'K26' ? fmt1(l.seats) : l.seats);
      stack += l.seats;
    });
    svg.append('text').attr('class', 'lbl-strong').attr('x', x(e) + x.bandwidth() / 2).attr('y', y(stack) - 6).attr('text-anchor', 'middle').text(e === 'K26' ? fmt1(stack) : stack);
    svg.append('text').attr('class', 'lbl-ink').attr('x', x(e) + x.bandwidth() / 2).attr('y', H - 22).attr('text-anchor', 'middle').text(elLabel(e, W));
    const lostV = e === 'K26' ? null : arabLists(e).filter(p => p.seats === 0);
    if (lostV && lostV.length && W >= 560) svg.append('text').attr('class', 'lbl').attr('x', x(e) + x.bandwidth() / 2).attr('y', H - 7).attr('text-anchor', 'middle')
      .style('fill', 'var(--crit)').text(`${lostV.map(p => p.name).join(AR_ON ? '، ' : ', ')}: 0`);
    if (e === 'K26') svg.append('text').attr('class', 'lbl').attr('x', x(e) + x.bandwidth() / 2).attr('y', H - 7).attr('text-anchor', 'middle').text(W >= 560 ? t('ממוצע סקרים') : t('סקרים'));
  });
}

function drawArabComposition(el) {
  const W = widthOf(el), rowH = 40, M = { t: 6, r: 96, b: 6, l: 8 };
  const H = M.t + M.b + rowH * ELS.length;
  const svg = svgEl(el, W, H, t('למי הצביעו בקלפיות הערביות בכל מערכת בחירות'));
  const x = d3.scaleLinear().domain([0, 1]).range([W - M.r, M.l]);
  ELS.forEach((e, i) => {
    const s = E(e).sectors.arab, yy = M.t + i * rowH;
    const arab = arabLists(e).map(p => ({ name: p.name, v: s.votes[p.id] || 0, color: famColor(p.family), arab: true }));
    const jewishParts = E(e).parties.filter(p => p.bloc !== 'arab').map(p => ({ name: p.name, v: s.votes[p.id] || 0 }))
      .concat([{ name: t('רשימות קטנות'), v: s.votes.other || 0 }]).filter(p => p.v > 0).sort((a, b) => b.v - a.v);
    const jew = { name: t('רשימות יהודיות'), v: sum(jewishParts.map(p => p.v)), color: 'var(--rule-strong)', parts: jewishParts };
    const segs = [...arab, jew];
    let acc = 0;
    svg.append('text').attr('class', 'lbl-ink').attr('x', W - 2).attr('y', yy + rowH / 2).attr('dy', '.35em').attr('text-anchor', 'start').text(E(e).short);
    segs.forEach(sg => {
      const f = sg.v / s.valid, x0 = x(acc), x1 = x(acc + f);
      svg.append('rect').attr('x', x1 + 1).attr('y', yy + 6).attr('width', Math.max(0, x0 - x1 - 2)).attr('height', rowH - 12).attr('rx', 3).attr('fill', sg.color)
        .call(sel => bindTT(sel, () => `<h4>${esc(sg.name)} · ${E(e).short}</h4>${ttRows([[t('קולות'), fmt(sg.v)], [t('מהקולות בקלפיות הערביות'), pct(100 * f)]])}${sg.parts ? '<hr style="border:0;border-top:1px solid var(--rule)">' + ttRows(sg.parts.slice(0, 6).map(p => [p.name, fmt(p.v)])) : ''}`));
      const full = `${sg.name} ${pct(100 * f, 0)}`, short = pct(100 * f, 0);
      const txt = x0 - x1 > textWidth(full, 11.5, 600) + 16 ? full : x0 - x1 > textWidth(short, 11.5, 600) + 10 ? short : null;
      if (txt) svg.append('text').attr('class', 'lbl').attr('x', x0 - 8).attr('y', yy + rowH / 2).attr('dy', '.35em').attr('text-anchor', 'start')
        .style('fill', onFill(sg.color)).style('font-weight', 600).text(txt);
      acc += f;
    });
  });
}

function drawArabRegions(el) {
  const e = S.arabRegEl, ev = E(e);
  const regs = ['negev', 'north_bedouin', 'wadi_ara', 'triangle_south', 'nazareth', 'galilee', 'christian', 'mixed_town', 'jerusalem', 'mixed'];
  const W = widthOf(el), rowH = 40, M = { t: W >= 560 ? 24 : 6, r: W >= 560 ? Math.max(168, d3.max(regs, k => textWidth(S.core.arab_regions[k] || '', 12.5, 600)) + 10) : 112, b: 8, l: W >= 560 ? 64 : Math.ceil(textWidth('100%', 22, 700)) + 12 };
  const H = M.t + M.b + rowH * regs.length;
  const svg = svgEl(el, W, H, t('השתתפות והצבעה בחברה הערבית לפי אזור, {e}', { e: ev.short }));
  const x = d3.scaleLinear().domain([0, 1]).range([W - M.r, M.l]);
  if (W >= 560) {
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 8).attr('y', 12).attr('text-anchor', 'start').text(t('השתתפות'));
    svg.append('text').attr('class', 'lbl').attr('x', W - M.r).attr('y', 12).attr('text-anchor', 'start').text(t('חלוקת הקולות הכשרים'));
  }
  regs.forEach((r, i) => {
    const s = ev.subsectors['arab:' + r]; if (!s) return;
    const yy = M.t + i * rowH;
    const name = S.core.arab_regions[r], shown = fitLabel(name, M.r - 8, 12.5, 600);
    const lt = svg.append('text').attr('class', 'lbl-strong').attr('x', W - 2).attr('y', yy + rowH / 2 - 6).attr('text-anchor', 'start').text(shown);
    if (shown !== name) lt.append('title').text(name);
    svg.append('text').attr('class', 'lbl').attr('x', W - 2).attr('y', yy + rowH / 2 + 10).attr('text-anchor', 'start').text(t('{n} בעלי זכות', { n: fmt(s.elig) }));
    const segs = [...arabLists(e).map(p => ({ name: p.name, v: s.votes[p.id] || 0, color: famColor(p.family), arab: true })),
      { name: t('רשימות יהודיות'), v: s.valid - sum(arabLists(e).map(p => s.votes[p.id] || 0)), color: 'var(--rule-strong)' }];
    let acc = 0;
    segs.forEach(sg => {
      const f = sg.v / s.valid, x0 = x(acc), x1 = x(acc + f);
      svg.append('rect').attr('x', x1 + 1).attr('y', yy + 8).attr('width', Math.max(0, x0 - x1 - 2)).attr('height', rowH - 16).attr('rx', 3).attr('fill', sg.color)
        .call(sel => bindTT(sel, () => `<h4>${esc(sg.name)} · ${S.core.arab_regions[r]}</h4>${ttRows([[t('קולות'), fmt(sg.v)], [t('שיעור'), pct(100 * f)]])}`));
      if (x0 - x1 > 46) svg.append('text').attr('class', 'lbl').attr('x', (x0 + x1) / 2).attr('y', yy + rowH / 2).attr('dy', '.35em').attr('text-anchor', 'middle')
        .style('fill', onFill(sg.color)).style('font-weight', 600).text(pct(100 * f, 0));
      acc += f;
    });
    svg.append('text').attr('class', 'lbl-big').attr('x', M.l - 8).attr('y', yy + rowH / 2).attr('dy', '.35em').attr('text-anchor', 'start').style('font-size', '22px')
      .text(pct(100 * s.voters / s.elig, 0));
  });
  // legend under the chart
  el.insertAdjacentHTML('beforeend', `<div class="legend">${arabLists(e).map(p => `<span><i style="background:${famColor(p.family)}"></i>${esc(p.name)}</span>`).join('')}<span><i style="background:var(--rule-strong)"></i>${t('רשימות יהודיות')}</span></div>`);
}

function drawArabPolls(el) {
  const endW = d3.max(S.polls.parties.filter(p => p.bloc === 'arab'), p => textWidth(`${p.name} 00.0`, 12.5, 600)) + 14;
  const W = widthOf(el, 480), H = 230, M = { t: 16, r: Math.min(Math.max(150, endW), W * 0.5), b: 26, l: 28 };
  const svg = svgEl(el, W, H, t('הרשימות הערביות בסקרי 2026: מנדטים לאורך זמן'));
  const { polls, parties } = S.polls;
  const x = d3.scaleUtc().domain([d3.timeDay.offset(toDate(polls[0].date), -2), d3.timeDay.offset(latestDate(), 2)]).range([M.l, W - M.r]);
  const y = d3.scaleLinear().domain([0, 12]).range([H - M.b, M.t]);
  svg.append('rect').attr('class', 'zone').attr('x', M.l).attr('width', W - M.l - M.r).attr('y', y(3.9)).attr('height', y(0) - y(3.9));
  svg.append('line').attr('class', 'ref-line').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(3.9)).attr('y2', y(3.9)).style('opacity', .5);
  svg.append('text').attr('class', 'lbl').attr('x', M.l + 4).attr('y', y(3.9) + 12).attr('text-anchor', 'end').text(t('אחוז החסימה'));
  [0, 4, 8, 12].forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 6).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v);
  });
  x.ticks(4).forEach(t => svg.append('text').attr('class', 'lbl').attr('x', x(t)).attr('y', H - 6).attr('text-anchor', 'middle').text(t.toLocaleDateString('he-IL', { day: 'numeric', month: 'numeric', timeZone: 'UTC' })));
  const series = dailyAverages(toDate(polls[0].date), latestDate());
  parties.filter(p => p.bloc === 'arab').forEach(p => {
    const c = party26Color(p);
    svg.selectAll(null).data(polls).join('circle').attr('cx', q => x(toDate(q.date))).attr('cy', q => y(q.seats[p.id] || 0)).attr('r', 3).attr('fill', c).attr('opacity', .35)
      .call(sel => bindTT(sel, q => `<h4>${esc(p.name)}: ${q.seats[p.id] || 0}</h4>${ttRows([[t('סוקר'), esc(q.house_he)], [t('גוף'), esc(q.outlet_he)]])}`));
    svg.append('path').attr('d', d3.line().x(d => x(d.date)).y(d => y(d.avg[p.id])).curve(d3.curveMonotoneX)(series)).attr('fill', 'none').attr('stroke', c).attr('stroke-width', 2.5);
    const l = series[series.length - 1];
    svg.append('text').attr('class', 'lbl-strong').attr('x', x(l.date) + 8).attr('y', y(l.avg[p.id])).attr('dy', '.35em').attr('text-anchor', 'end').text(`${p.name} ${fmt1(l.avg[p.id])}`);
  });
}

// transfers are looked up by election pair, so a pair missing from the data drops its button instead of shifting the others
const TRANSFER_PAIRS = [['K21', 'K22'], ['K22', 'K23'], ['K23', 'K24'], ['K24', 'K25']];
function arabTransfer(i) { const [a, b] = TRANSFER_PAIRS[i] || []; return S.core.transfers.find(x => x.scope === 'arab' && x.from === a && x.to === b); }
function drawSankey(el) {
  if (!arabTransfer(S.pairIdx)) S.pairIdx = TRANSFER_PAIRS.findIndex((p, i) => arabTransfer(i));
  const tf = arabTransfer(S.pairIdx);
  if (!tf) { el.innerHTML = `<p class="empty">${t('אין אומדן מעברי קולות.')}</p>`; return; }
  const W = widthOf(el), H = 420, M = { t: 28, r: 8, b: 8, l: 8 }, nodeW = 14, gap = 8;
  const svg = svgEl(el, W, H, t('מעברי קולות בקלפיות הערביות בין שתי מערכות בחירות (אומדן)'));
  const label = (eid, id) => id === 'abstain' ? t('לא הצביעו') : id === 'other' ? t('אחרות ופסולים') : partyName(eid, id);
  const color = (eid, id) => id === 'abstain' ? 'var(--rule-strong)' : id === 'other' ? 'var(--muted)' : famColor(famOf(eid, id));
  const total = sum(tf.src_mass);
  const flows = [];
  // 90% bootstrap interval for each cell; flows whose interval is wider than 20 points are faded
  const ci = (i, j) => { const m = tf.matrix[i][j], [lo, hi] = tf.ci ? tf.ci[i][j] : [m, m]; return [Math.min(lo, m), Math.max(hi, m)]; };
  tf.src.forEach((s, i) => tf.dst.forEach((d, j) => { const v = tf.src_mass[i] * tf.matrix[i][j]; if (v / total > 0.004) { const [lo, hi] = ci(i, j), m = tf.matrix[i][j]; flows.push({ s, d, v, i, j, lo, hi, shaky: hi - lo > 0.2, pinned: m < 0.005 || m > 0.995 }); } }));
  const srcNodes = tf.src.map((id, i) => ({ id, v: sum(flows.filter(f => f.i === i).map(f => f.v)) })).filter(n => n.v > 0).sort((a, b) => b.v - a.v);
  const dstNodes = tf.dst.map((id, j) => ({ id, v: sum(flows.filter(f => f.j === j).map(f => f.v)) })).filter(n => n.v > 0).sort((a, b) => b.v - a.v);
  const tot = sum(srcNodes.map(n => n.v));
  const avail = H - M.t - M.b;
  const k = (avail - gap * (Math.max(srcNodes.length, dstNodes.length) - 1)) / tot;
  const place = (nodes) => { let yy = M.t; nodes.forEach(n => { n.y0 = yy; n.h = Math.max(1.5, n.v * k); yy += n.h + gap; n.off = 0; }); };
  place(srcNodes); place(dstNodes);
  // earlier election on the right; on wide screens labels sit outside the nodes, on phones inside with a halo
  const nodeLabel = (eid, n) => t('{name} · {n} אלף', { name: label(eid, n.id), n: fmt(n.v / 1000) });
  const narrow = W < 640;
  const gutS = narrow ? 0 : d3.max(srcNodes, n => textWidth(nodeLabel(tf.from, n))) + 12;
  const gutD = narrow ? 0 : d3.max(dstNodes, n => textWidth(nodeLabel(tf.to, n))) + 12;
  const xs = M.l + gutS, xd = W - M.r - nodeW - gutD;   // earlier election on the left: time runs left to right
  svg.append('text').attr('class', 'lbl-strong').attr('x', M.l).attr('y', 14).attr('text-anchor', 'end').text(E(tf.from).label);
  svg.append('text').attr('class', 'lbl-strong').attr('x', W - M.r).attr('y', 14).attr('text-anchor', 'start').text(E(tf.to).label);
  const byS = Object.fromEntries(srcNodes.map(n => [n.id, n])), byD = Object.fromEntries(dstNodes.map(n => [n.id, n]));
  flows.sort((a, b) => b.v - a.v).forEach(f => {
    const sN = byS[f.s], dN = byD[f.d]; if (!sN || !dN) return;
    const h = f.v * k;
    const ys = sN.y0 + sN.off + h / 2, yd = dN.y0 + dN.off + h / 2; sN.off += h; dN.off += h;
    const mid = (xs + nodeW + xd) / 2;
    svg.append('path').attr('d', `M${xs + nodeW},${ys} C${mid},${ys} ${mid},${yd} ${xd},${yd}`).attr('fill', 'none')
      .attr('stroke', color(tf.from, f.s)).attr('stroke-opacity', f.shaky ? .14 : .42).attr('stroke-width', Math.max(1, h))
      .attr('stroke-dasharray', f.shaky && h > 3 ? '6 3' : null)
      .call(sel => bindTT(sel, () => `<h4>${esc(label(tf.from, f.s))} (${E(tf.from).short})</h4>${ttRows([[t('עברו אל'), esc(label(tf.to, f.d)) + ` (${E(tf.to).short})`], [t('אומדן בעלי זכות'), fmt(f.v)], [t('מתוך מצביעי המקור'), t('{p} (טווח 90%: {lo}–{hi}%)', { p: pct(100 * tf.matrix[f.i][f.j], 0), lo: Math.round(100 * f.lo), hi: Math.round(100 * f.hi) })]])}${f.shaky ? `<p class="tt-note">${t('אומדן לא יציב: הטווח רחב מ-20 נקודות.')}</p>` : ''}${f.pinned ? `<p class="tt-note">${t('הערך נקבע על ידי האילוץ (0% או 100%), לא על ידי הנתונים.')}</p>` : ''}`));
  });
  const halo = sel => narrow ? sel.attr('class', 'lbl-ink halo') : sel;
  srcNodes.forEach(n => {
    svg.append('rect').attr('x', xs).attr('y', n.y0).attr('width', nodeW).attr('height', n.h).attr('fill', color(tf.from, n.id)).attr('rx', 2);
    if (n.h > 9) halo(svg.append('text').attr('class', 'lbl-ink').attr('x', narrow ? xs + nodeW + 4 : xs - 6).attr('y', n.y0 + n.h / 2).attr('dy', '.35em')
      .attr('text-anchor', narrow ? 'end' : 'start').text(nodeLabel(tf.from, n)));
  });
  dstNodes.forEach(n => {
    svg.append('rect').attr('x', xd).attr('y', n.y0).attr('width', nodeW).attr('height', n.h).attr('fill', color(tf.to, n.id)).attr('rx', 2);
    if (n.h > 9) halo(svg.append('text').attr('class', 'lbl-ink').attr('x', narrow ? xd - 4 : xd + nodeW + 6).attr('y', n.y0 + n.h / 2).attr('dy', '.35em')
      .attr('text-anchor', narrow ? 'start' : 'end').text(nodeLabel(tf.to, n)));
  });
  $('#ar-sankey-foot').textContent = t('אומדן סטטיסטי (רגרסיה מאולצת). קלפי מותאמת לקלפי באותו מספר רק כשמספר בעלי הזכות בה דומה ({m} זוגות); שאר הקלפיות בכל יישוב מאוחדות ליחידה אחת. היחידות מכסות {c} מבעלי הזכות. זרמים חיוורים ומקווקווים: טווח 90% (bootstrap) רחב מ-20 נקודות. ערכים של 0% או 100% נובעים מהאילוץ ולא מהנתונים. אינו מדידה של מצביעים בודדים; זרמים קטנים מ-0.4% הושמטו. קולות במעטפות כפולות אינם כלולים.', { m: fmt(tf.matched), c: pct(100 * tf.coverage, 0) });
}

function drawMixed(el) {
  const e = S.arabMixEl, ev = E(e);
  const rows = Object.entries(ev.mixed).map(([code, d]) => {
    const a = d.arab, j = d.jewish;
    const aLists = arabLists(e).map(p => p.id);
    return { name: S.core.mixed_cities[code], a, j, share: a.valid ? sum(aLists.map(id => a.votes[id] || 0)) / a.valid : null,
             jShare: j.valid ? sum(aLists.map(id => j.votes[id] || 0)) / j.valid : null };
  }).filter(r => r.a.elig > 0).sort((p, q) => q.a.elig - p.a.elig);
  el.innerHTML = `<table class="t wrap"><thead><tr><th>${t('עיר')}</th><th class="n hide-sm">${t('בעלי זכות (קלפיות ערביות)')}</th><th class="n">${t('השתתפות, קלפיות ערביות')}</th><th class="n hide-sm">${t('השתתפות, שאר הקלפיות')}</th><th class="n">${t('רשימות ערביות*')}</th></tr></thead><tbody>${
    rows.map(r => `<tr><td>${esc(r.name)}</td><td class="n hide-sm">${fmt(r.a.elig)}</td><td class="n">${pct(100 * r.a.voters / r.a.elig)}</td><td class="n hide-sm">${r.j.elig ? pct(100 * r.j.voters / r.j.elig) : '—'}</td><td class="n">${r.share != null ? pct(100 * r.share, 0) : '—'}</td></tr>`).join('')}</tbody></table><p class="foot">${t('* שיעור הקולות לרשימות הערביות בקלפיות הערביות של העיר. בירושלים רוב התושבים הערבים אינם אזרחים ולכן אינם בפנקס הבוחרים.')}</p>`;
}

function drawDruze(el) {
  const W = widthOf(el, 480), rowH = 34, M = { t: 4, r: 70, b: 4, l: 4 };
  const H = M.t + M.b + rowH * ELS.length;
  const svg = svgEl(el, W, H, t('הצבעה ביישובים הדרוזיים בכל מערכת בחירות'));
  const x = d3.scaleLinear().domain([0, 1]).range([W - M.r, M.l]);
  const famsSeen = new Map();
  ELS.forEach((e, i) => {
    const s = E(e).subsectors['druze:druze'], yy = M.t + i * rowH;
    svg.append('text').attr('class', 'lbl-ink').attr('x', W - 2).attr('y', yy + rowH / 2).attr('dy', '.35em').attr('text-anchor', 'start').text(E(e).short);
    const parts = E(e).parties.map(p => ({ name: p.name, fam: p.family, v: s.votes[p.id] || 0 })).filter(p => p.v / s.valid >= 0.04).sort((a, b) => b.v - a.v);
    parts.push({ name: t('אחרות'), fam: 'other', v: s.valid - sum(parts.map(p => p.v)) });
    let acc = 0;
    parts.forEach(p => {
      const f = p.v / s.valid, x0 = x(acc), x1 = x(acc + f);
      famsSeen.set(p.fam, S.core.families[p.fam].name);
      svg.append('rect').attr('x', x1 + 1).attr('y', yy + 5).attr('width', Math.max(0, x0 - x1 - 2)).attr('height', rowH - 10).attr('rx', 3).attr('fill', famColor(p.fam))
        .call(sel => bindTT(sel, () => `<h4>${esc(p.name)} · ${E(e).short}</h4>${ttRows([[t('קולות'), fmt(p.v)], [t('שיעור'), pct(100 * f)]])}`));
      if (x0 - x1 > 34) svg.append('text').attr('class', 'lbl').attr('x', (x0 + x1) / 2).attr('y', yy + rowH / 2).attr('dy', '.35em').attr('text-anchor', 'middle').style('fill', onFill(famColor(p.fam))).style('font-weight', 600).text(pct(100 * f, 0));
      acc += f;
    });
  });
  el.insertAdjacentHTML('beforeend', `<div class="legend">${[...famsSeen].map(([f, n]) => `<span><i style="background:${famColor(f)}"></i>${esc(n)}</span>`).join('')}</div>`);
}
