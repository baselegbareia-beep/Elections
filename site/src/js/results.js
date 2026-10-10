/* ===================== results explorer: national, map, locality, ballot ===================== */
S.locSel = 4000;   // Haifa: a mixed city shows the ballot-level split well
const TRIBES = 'tribes';

function mapLocalities() {
  // Negev tribal rows have no polygon; they are merged into one marker.
  if (S._mapLocs) return S._mapLocs;
  const locs = S.core.localities.filter(l => !l.tribe && l.lat != null);
  const tribes = S.core.localities.filter(l => l.tribe);
  if (tribes.length) {
    const el = {};
    ELS.forEach(e => {
      const rows = tribes.map(t => t.el[e]).filter(Boolean);
      if (!rows.length) return;
      el[e] = rows[0].map((_, i) => sum(rows.map(r => r[i])));
    });
    locs.push({ code: TRIBES, name: 'שבטים ופזורה בנגב', sector: 'arab', region: 'negev', lat: 31.22, lng: 34.93, tribe: true, ses: null, el, members: tribes.map(t => t.code) });
  }
  S._mapLocs = locs;
  return locs;
}
const findLoc = code => code === TRIBES ? mapLocalities().find(l => l.code === TRIBES) : S.core.localities.find(l => l.code === code);

function renderResults() {
  const root = $('#tab-results');
  const names = S.core.localities.map(l => l.name).concat(['שבטים ופזורה בנגב']).sort((a, b) => a.localeCompare(b, 'he'));
  root.innerHTML = `
  <div class="section-head"><div>
    <span class="eyebrow">תוצאות רשמיות · ועדת הבחירות המרכזית</span>
    <h2>חמש מערכות בחירות, עד הקלפי</h2>
    <p>בחרו מערכת בחירות, צבעו את המפה לפי מה שמעניין אתכם, ולחצו על יישוב כדי לראות את התוצאות שלו לאורך זמן ואת התוצאה בכל קלפי.</p>
  </div></div>
  <div class="controls">
    <span class="ctl-label">בחירות</span>${seg('rs-el', ELS.map(e => [e, `${E(e).short}`]), S.election)}
    <span class="ctl-label">צביעה</span>${seg('rs-mode', [['winner', 'הרשימה המובילה'], ['party', 'רשימה'], ['turnout', 'השתתפות'], ['sector', 'מגזר']], S.mapMode)}
    <select id="rs-party" aria-label="רשימה לצביעה" ${S.mapMode === 'party' ? '' : 'hidden'}></select>
    <input type="search" id="rs-search" list="rs-names" placeholder="חיפוש יישוב…" aria-label="חיפוש יישוב">
    <span id="rs-search-msg" class="ctl-label" role="status" style="color:var(--crit)"></span>
    <datalist id="rs-names">${names.map(n => `<option value="${esc(n)}"></option>`).join('')}</datalist>
  </div>
  <div class="grid">
    <div class="card c7" id="rs-national"></div>
    <div class="card c5">
      <h3 id="rs-map-title">מפת היישובים</h3>
      <p class="sub">כל עיגול הוא יישוב; שטחו לפי מספר המצביעים. להתקרבות: הכפתורים, Ctrl עם גלגלת, או שתי אצבעות.</p>
      <div class="map-wrap" id="rs-map"></div>
      <div class="legend" id="rs-legend"></div>
      <p class="foot">מיקום היישוב: מרכז הפוליגון של הלמ״ס (2022). הקו המקווקו מסמן את הקו הירוק. שבטי הנגב מוצגים כעיגול אחד.</p>
    </div>
    <div class="card c12" id="rs-loc"></div>
  </div>`;
  fillPartySelect();
  onSeg(root, 'rs-el', v => { S.election = v; fillPartySelect(); drawNational(); drawMap(); drawLocality(); });
  onSeg(root, 'rs-mode', v => { S.mapMode = v; $('#rs-party').hidden = v !== 'party'; drawMap(); });
  $('#rs-party').addEventListener('change', e => { S.mapParty = e.target.value; drawMap(); });
  const search = $('#rs-search');
  // match regardless of geresh vs apostrophe, hyphens and spacing ("אום אל פחם" finds "אום אל-פחם")
  const norm = s => s.replace(/[׳`’]/g, "'").replace(/[״“”]/g, '"').replace(/[\s\-־'"().]/g, '');
  let lastQ = '';
  const go = () => {
    const q = search.value.trim(); if (!q || q === lastQ) return; lastQ = q;
    const nq = norm(q);
    let l = nq === norm('שבטים ופזורה בנגב') ? findLoc(TRIBES)
      : S.core.localities.find(x => norm(x.name) === nq) || S.core.localities.find(x => norm(x.name).includes(nq));
    if (!l) { $('#rs-search-msg').textContent = `לא נמצא יישוב בשם ״${q}״`; return; }
    $('#rs-search-msg').textContent = '';
    S.locSel = l.tribe && l.code !== TRIBES ? TRIBES : l.code; drawMap(); drawLocality();
    $('#rs-loc').scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  search.addEventListener('change', go);
  search.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); go(); } });
  search.addEventListener('input', () => { lastQ = ''; });
  drawNational(); drawMap(); drawLocality();
}

function fillPartySelect() {
  const ev = E(S.election);
  const main = ev.parties.filter(p => p.main);
  if (!S.mapParty || !main.find(p => p.id === S.mapParty)) S.mapParty = (main.find(p => p.bloc === 'arab') || main[0]).id;
  $('#rs-party').innerHTML = main.map(p => `<option value="${esc(p.id)}" ${p.id === S.mapParty ? 'selected' : ''}>${esc(p.name)} (${esc(p.id)})</option>`).join('');
}

function drawNational() {
  const ev = E(S.election), prev = PREV[S.election] ? E(PREV[S.election]) : null;
  const prevSeats = id => (prev && prev.parties.find(p => p.id === id) || { seats: 0 }).seats;
  const change = p => {
    if (!prev || !p.pred || p.seats === 0) return '';
    if (p.pred === 'new') return '<span class="badge">חדשה</span>';
    if (p.pred === 'split') return '<span class="badge" title="הרשימה נוצרה מפיצול של רשימה קודמת">פיצול</span>';
    const before = sum(p.pred.map(prevSeats)), d = p.seats - before;
    const merged = p.pred.length > 1 ? ` title="מול ${before} מנדטים של ${esc(p.pred.map(id => partyName(prev.id, id)).join(' + '))}"` : '';
    return `<span class="num ${d > 0 ? 'delta-up' : d < 0 ? 'delta-down' : ''}"${merged}>${d > 0 ? '+' : d < 0 ? '−' : '±'}${Math.abs(d)}${p.pred.length > 1 ? '*' : ''}</span>`;
  };
  const rows = ev.parties.filter(p => p.pct >= 0.5);
  const small = ev.parties.filter(p => p.pct < 0.5);
  const wasted = sum(ev.parties.filter(p => p.seats === 0).map(p => p.votes));
  $('#rs-national').innerHTML = `
    <div class="card-head"><div><h3>${ev.label} · ${dateHe(ev.date)}</h3>
    <p class="sub">${ev.bloc_note} אחוז החסימה (3.25%): ${fmt(ev.threshold_votes)} קולות.</p></div>
    <span class="badge off">רשמי</span></div>
    <div class="chart" id="rs-strip"></div>
    <div class="tbl-wrap"><table class="t"><thead><tr><th>רשימה</th><th class="n hide-sm">קולות</th><th class="n">אחוז</th><th class="n">מנדטים</th><th class="n">שינוי</th><th class="hide-sm"></th></tr></thead><tbody>${
      rows.map(p => {
        return `<tr><td>${slip(p.id, p.name, famColor(p.family))}</td><td class="n hide-sm">${fmt(p.votes)}</td><td class="n">${pct(p.pct, 2)}</td><td class="n"><b>${p.seats || '—'}</b></td>
          <td class="n">${change(p)}</td>
          <td class="hide-sm"><span class="minibar" style="width:${Math.round(p.pct * 3)}px;background:${famColor(p.family)};opacity:${p.seats ? 1 : .4}"></span></td></tr>`;
      }).join('')}
      <tr><td><span class="slip"><span class="nm">${small.length} רשימות קטנות</span></span></td><td class="n hide-sm">${fmt(sum(small.map(p => p.votes)))}</td><td class="n">${pct(sum(small.map(p => p.pct)), 2)}</td><td class="n">—</td><td></td><td class="hide-sm"></td></tr>
    </tbody></table></div>
    <div class="kv kv3">
      <div><b class="num">${fmt(ev.eligible)}</b><span>בעלי זכות בחירה</span></div>
      <div><b class="num">${pct(ev.turnout)}</b><span>שיעור הצבעה</span></div>
      <div><b class="num">${fmt(ev.valid)}</b><span>קולות כשרים</span></div>
      <div><b class="num">${fmt(ev.boxes)}</b><span>קלפיות (בלי מעטפות)</span></div>
      <div><b class="num">${pct(100 * wasted / ev.valid)}</b><span>קולות לרשימות שלא עברו</span></div>
      <div><b class="num">${fmt(ev.envelope_voters)}</b><span>הצביעו במעטפות כפולות</span></div>
    </div>
    <p class="foot">המקור: קובץ התוצאות לפי קלפיות של ועדת הבחירות המרכזית, <a href="${esc(ev.official_url)}" target="_blank" rel="noopener" dir="ltr">${esc(ev.official_url.replace('https://', '').replace(/\/$/, ''))}</a>. סכומי הקולות זהים לטבלה הארצית הרשמית לכל רשימה. השינוי במנדטים מחושב מול הרשימה הקודמת; * = מול סך הרשימות שהתאחדו לתוכה.</p>`;
  drawSeatStrip($('#rs-strip'), ev);
}

function drawSeatStrip(el, ev) {
  const W = widthOf(el), H = 46;
  const svg = svgEl(el, W, H, `חלוקת המנדטים, ${ev.label}`);
  const ps = ev.parties.filter(p => p.seats > 0);
  const x = d3.scaleLinear().domain([0, 120]).range([W, 0]);
  let acc = 0;
  ps.forEach(p => {
    const x0 = x(acc), x1 = x(acc + p.seats);
    svg.append('rect').attr('x', x1 + 1).attr('y', 4).attr('width', Math.max(0, x0 - x1 - 2)).attr('height', 22).attr('rx', 3).attr('fill', famColor(p.family))
      .call(sel => bindTT(sel, () => `<h4>${esc(p.name)}</h4>${ttRows([['מנדטים', p.seats], ['קולות', fmt(p.votes)], ['אחוז', pct(p.pct, 2)]])}`));
    if (x0 - x1 > 20) svg.append('text').attr('class', 'lbl').attr('x', (x0 + x1) / 2).attr('y', 15).attr('dy', '.35em').attr('text-anchor', 'middle').style('fill', onFill(famColor(p.family))).style('font-weight', 600).text(p.seats);
    acc += p.seats;
  });
  svg.append('line').attr('class', 'ref-line').attr('x1', x(60.5)).attr('x2', x(60.5)).attr('y1', 0).attr('y2', 30);
  svg.append('text').attr('class', 'ref-text').attr('x', x(60.5)).attr('y', 43).attr('text-anchor', 'middle').text('61');
}

/* ---------- map ---------- */
function shareOf(loc, eid, letter) { const v = locVotes(loc, eid); return v && v.valid ? (v.votes[letter] || 0) / v.valid : null; }
function winnerOf(loc, eid) {
  const v = locVotes(loc, eid); if (!v || !v.valid) return null;
  let best = null; Object.entries(v.votes).forEach(([k, n]) => { if (k !== 'other' && (!best || n > best[1])) best = [k, n]; });
  return best && { id: best[0], share: best[1] / v.valid };
}
function sectorFill(l) {
  return { arab: 'var(--arab)', druze: 'var(--druze)', jewish: 'var(--jewish)', mixed: 'var(--jewish)' }[l.sector];
}

function drawMap() {
  const el = $('#rs-map'); const eid = S.election;
  const W = widthOf(el, 520), H = Math.min(980, Math.round(W * 1.75));
  el.innerHTML = '';
  const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img').attr('aria-label', 'מפת יישובים');
  const focus = { type: 'MultiPoint', coordinates: [[34.22, 30.8], [35.92, 33.34]] };   // north of Mitzpe Ramon; zoom out for Eilat
  const proj = d3.geoMercator().fitExtent([[8, 8], [W - 8, H - 8]], focus);
  const path = d3.geoPath(proj);
  const g = svg.append('g');
  g.selectAll('path.land').data(S.outline.features).join('path').attr('class', 'land').attr('d', path);
  // the boundary shared by the two shapes approximates the 1949 armistice line
  const wb = S.outline.features.find(f => f.properties.id === '275');
  if (wb) g.append('path').attr('class', 'greenline').attr('d', path(wb));
  const locs = mapLocalities().filter(l => l.el[eid]);
  const maxV = d3.max(locs, l => l.el[eid][2]);
  const r = d3.scaleSqrt().domain([0, maxV]).range([0, Math.min(26, W / 22)]);
  const mode = S.mapMode;
  let fill, legend = '';
  if (mode === 'winner') {
    fill = l => { const w = winnerOf(l, eid); return w ? famColor(famOf(eid, w.id)) : 'var(--muted)'; };
    const fams = new Map(); locs.forEach(l => { const w = winnerOf(l, eid); if (w) { const f = famOf(eid, w.id); fams.set(f, (fams.get(f) || 0) + 1); } });
    legend = [...fams].sort((a, b) => b[1] - a[1]).map(([f, n]) => `<span><i style="background:${famColor(f)}"></i>${esc(S.core.families[f].name)} (${n})</span>`).join('');
    $('#rs-map-title').textContent = `הרשימה המובילה בכל יישוב · ${E(eid).short}`;
  } else if (mode === 'party') {
    const pm = partyMeta(eid, S.mapParty);
    const c = famColor(pm.family);
    const vals = locs.map(l => shareOf(l, eid, S.mapParty)).filter(v => v != null).sort(d3.ascending);
    const top = Math.max(0.05, d3.quantile(vals, 0.97));
    const sc = d3.scaleLinear().domain([0, top]).range([cssVar('--surface-2'), c]).interpolate(d3.interpolateLab).clamp(true);
    fill = l => { const s = shareOf(l, eid, S.mapParty); return s == null ? 'var(--rule)' : sc(s); };
    legend = `<span>0%</span><span style="display:inline-block;width:140px;height:10px;border-radius:2px;background:linear-gradient(to left, ${sc(0)}, ${sc(top)})"></span><span>${pct(100 * top, 0)} ומעלה</span>`;
    $('#rs-map-title').textContent = `${pm.name}: שיעור הקולות ביישוב · ${E(eid).short}`;
  } else if (mode === 'turnout') {
    const sc = d3.scaleLinear().domain([40, 90]).range([cssVar('--seq-0'), cssVar('--seq-1')]).interpolate(d3.interpolateLab).clamp(true);
    fill = l => { const v = locVotes(l, eid); return v && v.elig ? sc(100 * v.voters / v.elig) : 'var(--rule)'; };
    legend = `<span>40%</span><span style="display:inline-block;width:140px;height:10px;border-radius:2px;background:linear-gradient(to left, ${sc(40)}, ${sc(90)})"></span><span>90%</span>`;
    $('#rs-map-title').textContent = `שיעור ההצבעה ביישוב · ${E(eid).short}`;
  } else {
    fill = sectorFill;
    legend = `<span><i style="background:var(--jewish)"></i>יהודי</span><span><i style="background:var(--arab)"></i>ערבי (כולל בדואי)</span><span><i style="background:var(--druze)"></i>דרוזי או צ׳רקסי</span><span><i style="background:var(--jewish);box-shadow:inset -5px 0 0 var(--arab)"></i>עיר מעורבת (החלק הערבי לפי קלפיות)</span>`;
    $('#rs-map-title').textContent = 'סיווג היישובים לפי מגזר';
  }
  $('#rs-legend').innerHTML = legend;
  const data = [...locs].sort((a, b) => b.el[eid][2] - a.el[eid][2]);
  const bub = g.selectAll('circle.bub').data(data).join('circle').attr('class', d => 'bub' + (d.code === S.locSel ? ' sel' : ''))
    .attr('cx', d => proj([d.lng, d.lat])[0]).attr('cy', d => proj([d.lng, d.lat])[1])
    .attr('r', d => Math.max(1.3, r(d.el[eid][2]))).attr('fill', fill).attr('fill-opacity', .9);
  if (mode === 'sector') {
    // overlay the Arab share of a mixed city as a pie slice
    data.filter(d => d.sector === 'mixed').forEach(d => {
      const v = locVotes(d, eid); const share = v.arabBoxes / v.boxes;
      const [cx, cy] = proj([d.lng, d.lat]); const rr = Math.max(1.3, r(d.el[eid][2]));
      g.append('path').attr('transform', `translate(${cx},${cy})`).attr('d', d3.arc()({ innerRadius: 0, outerRadius: rr, startAngle: 0, endAngle: 2 * Math.PI * share }))
        .attr('fill', 'var(--arab)').attr('pointer-events', 'none').attr('class', 'mixslice');
    });
  }
  bindTT(bub, d => locTooltip(d, eid));
  bub.on('click', (ev, d) => {
    S.locSel = d.code; g.selectAll('circle.bub').classed('sel', x => x.code === d.code); drawLocality();
    const r = $('#rs-loc').getBoundingClientRect();
    if (r.top > window.innerHeight - 160) $('#rs-loc').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  const zoom = d3.zoom().scaleExtent([1, 14])
    .filter(ev => ev.type === 'wheel' ? (ev.ctrlKey || ev.metaKey) : ev.type.startsWith('touch') ? ev.touches.length > 1 : !ev.button)
    .on('zoom', ev => {
    g.attr('transform', ev.transform);
    g.selectAll('circle.bub').attr('r', d => Math.max(1.3, r(d.el[eid][2])) / Math.sqrt(ev.transform.k)).attr('stroke-width', .6 / ev.transform.k);
    g.selectAll('path.land, path.greenline').attr('stroke-width', 0.8 / ev.transform.k);
    g.selectAll('path.mixslice').attr('opacity', ev.transform.k > 1.2 ? 0 : 1);
  });
  svg.call(zoom);
  const btns = document.createElement('div'); btns.className = 'map-btns';
  btns.innerHTML = '<button type="button" aria-label="התקרבות">+</button><button type="button" aria-label="התרחקות">−</button><button type="button" aria-label="איפוס">⟲</button>';
  el.appendChild(btns);
  const [bIn, bOut, bReset] = btns.querySelectorAll('button');
  bIn.onclick = () => svg.transition().duration(250).call(zoom.scaleBy, 1.6);
  bOut.onclick = () => svg.transition().duration(250).call(zoom.scaleBy, 1 / 1.6);
  bReset.onclick = () => svg.transition().duration(250).call(zoom.transform, d3.zoomIdentity);
}

function locTooltip(l, eid) {
  const v = locVotes(l, eid); if (!v) return '';
  const top = Object.entries(v.votes).filter(([k]) => k !== 'other').sort((a, b) => b[1] - a[1]).slice(0, 4);
  const sec = { arab: 'ערבי', jewish: 'יהודי', druze: 'דרוזי/צ׳רקסי', mixed: 'עיר מעורבת' }[l.sector];
  return `<h4>${esc(l.name)}</h4><div class="row"><span>${sec}${l.ses ? ` · אשכול ${l.ses}` : ''}</span><span class="num">${pct(100 * v.voters / v.elig)} הצבעה</span></div>${ttRows(top.map(([k, n]) => [partyName(eid, k), pct(100 * n / v.valid), famColor(famOf(eid, k))]))}`;
}

/* ---------- locality panel ---------- */
async function drawLocality() {
  const box = $('#rs-loc');
  const l = findLoc(S.locSel);
  if (!l) { box.innerHTML = '<p class="empty">בחרו יישוב במפה או בחיפוש.</p>'; return; }
  const eid = S.election, v = locVotes(l, eid);
  const sec = { arab: ['ערבי', 'arab'], jewish: ['יהודי', ''], druze: ['דרוזי/צ׳רקסי', ''], mixed: ['עיר מעורבת', ''] }[l.sector];
  const region = l.region ? (S.core.arab_regions[l.region] || S.core.druze_regions[l.region]) : null;
  const w = v ? winnerOf(l, eid) : null;
  box.innerHTML = `
    <div class="loc-head"><div><span class="eyebrow">פרופיל יישוב</span><h3>${esc(l.name)}</h3></div>
      <div class="chips"><span class="badge ${sec[1]}">${sec[0]}</span>${region && l.sector !== 'mixed' ? `<span class="badge">${esc(region)}</span>` : ''}<span class="badge off" title="תוצאות לפי קובצי הקלפיות של ועדת הבחירות המרכזית">תוצאות רשמיות</span>${l.ses ? `<span class="badge est" title="מקור משני: מדד חברתי-כלכלי של הלמ״ס">אשכול חברתי-כלכלי ${l.ses} מתוך 10 (למ״ס)</span>` : ''}</div></div>
    ${v ? `<div class="kv">
      <div><b class="num">${fmt(v.elig)}</b><span>בעלי זכות · ${E(eid).short}</span></div>
      <div><b class="num">${pct(100 * v.voters / v.elig)}</b><span>שיעור הצבעה</span></div>
      <div><b class="num">${fmt(v.boxes)}</b><span>קלפיות${v.arabBoxes ? ` (${v.arabBoxes} ערביות)` : ''}</span></div>
      <div><b>${w ? esc(partyName(eid, w.id)) : '—'}</b><span>מובילה, ${w ? pct(100 * w.share) : ''}</span></div>
    </div>` : `<p class="empty">אין נתונים ליישוב זה בבחירות ל${E(eid).label.replace(/^ה/, '')}.</p>`}
    <div class="grid" style="gap:18px">
      <div class="c6"><h3 style="font-size:var(--t-md)">ההצבעה לאורך חמש מערכות</h3><p class="sub">שיעור הקולות לפי משפחה פוליטית (קווים) ושיעור ההצבעה (טבלה).</p><div class="chart" id="loc-trend"></div><div class="tbl-wrap" id="loc-turn"></div></div>
      <div class="c6"><h3 style="font-size:var(--t-md)">תוצאות לפי קלפי · ${E(eid).short}</h3><p class="sub">לחצו על כותרת עמודה למיון.${l.sector === 'mixed' ? ' קלפיות שבהן לרשימות הערביות רוב מסומנות.' : ''}</p><div id="loc-ballots" class="tbl-wrap scroll-y"><p class="empty">טוען קלפיות…</p></div></div>
    </div>`;
  drawLocTrend($('#loc-trend'), l);
  // five columns fit a phone only with the compact election names ('4/19'); the full ones would push the first off-screen
  const lt = $('#loc-turn'), lw = lt.getBoundingClientRect().width, elName = e => lw && lw < 440 ? COMPACT[e] : E(e).short;
  lt.innerHTML = `<table class="t" dir="ltr"><thead><tr>${ELS.map(e => `<th class="n">${elName(e)}</th>`).join('')}</tr></thead><tbody><tr>${ELS.map(e => { const x = locVotes(l, e); return `<td class="n">${x ? pct(100 * x.voters / x.elig) : '—'}</td>`; }).join('')}</tr></tbody></table>`;
  let b;
  try { b = await loadBallots(eid); } catch (err) {
    console.error(err);
    if (S.locSel === l.code && S.election === eid) {
      $('#loc-ballots').innerHTML = '<p class="empty">טעינת הקלפיות נכשלה. <button type="button" class="slip" id="loc-retry">ניסיון נוסף</button></p>';
      $('#loc-retry').onclick = () => drawLocality();
    }
    return;
  }
  if (S.locSel !== l.code || S.election !== eid) return;
  drawBallotTable($('#loc-ballots'), l, b, eid);
}

function famShares(l, eid) {
  const v = locVotes(l, eid); if (!v || !v.valid) return null;
  const out = {};
  Object.entries(v.votes).forEach(([k, n]) => { const f = famOf(eid, k); out[f] = (out[f] || 0) + n / v.valid; });
  return out;
}
function drawLocTrend(el, l) {
  const W = widthOf(el, 560), H = 250, M = { t: 14, r: 120, b: 26, l: 36 };
  const svg = svgEl(el, W, H, `${l.name}: ההצבעה לפי משפחה פוליטית בחמש מערכות הבחירות`);
  const shares = Object.fromEntries(ELS.map(e => [e, famShares(l, e)]));
  const fams = new Set(); ELS.forEach(e => { if (shares[e]) Object.entries(shares[e]).forEach(([f, s]) => { if (s >= 0.08 && f !== 'other') fams.add(f); }); });
  const famList = [...fams].sort((a, b) => d3.max(ELS, e => shares[e]?.[b] || 0) - d3.max(ELS, e => shares[e]?.[a] || 0)).slice(0, 6);
  // a family is plotted only in elections where it ran, so splits and mergers do not read as 0%
  const ran = (e, f) => E(e).parties.some(p => p.family === f);
  const series = famList.map(f => ({ key: f, name: S.core.families[f].name.split(' / ')[0], color: famColor(f), w: 2.2,
    pts: ELS.map(e => ({ e, v: shares[e] && ran(e, f) ? shares[e][f] || 0 : null })) }));
  // in Arab, Druze and mixed localities the combined Arab-list vote is the continuous story
  if (l.sector !== 'jewish') {
    series.unshift({ key: 'arab-all', name: 'כל הרשימות הערביות', color: 'var(--ink)', w: 3.4,
      pts: ELS.map(e => { const v = locVotes(l, e); return { e, v: v && v.valid ? sum(E(e).parties.filter(p => p.bloc === 'arab').map(p => v.votes[p.id] || 0)) / v.valid : null }; }) });
  }
  // a dashed line for a family whose colour is close to one already drawn
  series.forEach((sr, i) => {
    const c = d3.lab(sr.color.startsWith('var(') ? cssVar(sr.color.slice(4, -1)) : sr.color);
    sr.dash = series.slice(0, i).some(o => { const k = d3.lab(o.color.startsWith('var(') ? cssVar(o.color.slice(4, -1)) : o.color); return Math.hypot(c.l - k.l, c.a - k.a, c.b - k.b) < 25; }) ? '5 3' : null;
  });
  const x = d3.scalePoint().domain(ELS).range([M.l, W - M.r]).padding(0.2);
  const maxY = Math.min(1, (d3.max(series, sr => d3.max(sr.pts, d => d.v || 0)) || 0.5) + 0.06);
  const y = d3.scaleLinear().domain([0, maxY]).range([H - M.b, M.t]);
  y.ticks(4).forEach(t => {
    svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(t)).attr('y2', y(t));
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 6).attr('y', y(t)).attr('dy', '.32em').attr('text-anchor', 'start').text(Math.round(t * 100) + '%');
  });
  ELS.forEach(e => svg.append('text').attr('class', 'lbl').attr('x', x(e)).attr('y', H - 6).attr('text-anchor', 'middle').text(elLabel(e, W)));
  const labels = [], lastE = ELS[ELS.length - 1];
  series.forEach(sr => {
    svg.append('path').attr('d', d3.line().defined(d => d.v != null).x(d => x(d.e)).y(d => y(d.v))(sr.pts)).attr('fill', 'none')
      .attr('stroke', sr.color).attr('stroke-width', sr.w).attr('stroke-dasharray', sr.dash);
    const pts = sr.pts.filter(d => d.v != null);
    svg.selectAll(null).data(pts).join('circle').attr('cx', d => x(d.e)).attr('cy', d => y(d.v)).attr('r', sr.w > 3 ? 4 : 3.5).attr('fill', sr.color).attr('stroke', 'var(--surface)')
      .call(sel => bindTT(sel, d => `<h4>${esc(sr.name)} · ${E(d.e).short}</h4>${ttRows([['שיעור הקולות', pct(100 * d.v)]])}`));
    const last = pts[pts.length - 1];
    if (last && last.e === lastE) labels.push({ f: sr.key, name: sr.name, y: y(last.v), x: x(last.e), strong: sr.w > 3 });
  });
  placeLabels(labels, 13, M.t, H - M.b).forEach(o => svg.append('text').attr('class', 'lbl-ink').attr('x', o.x + 8).attr('y', o.y).attr('dy', '.35em')
    .attr('text-anchor', 'end').style('font-size', '11.5px').style('font-weight', o.strong ? 700 : null).text(o.name));
  // series that did not run in the last election are named in a legend under the chart
  const gone = series.filter(sr => !labels.some(o => o.f === sr.key));
  if (gone.length) el.insertAdjacentHTML('beforeend', `<div class="legend">${gone.map(sr => `<span><i style="background:${sr.color}"></i>${esc(sr.name)} (עד ${E(sr.pts.filter(d => d.v != null).pop().e).short})</span>`).join('')}</div>`);
}

function drawBallotTable(el, l, b, eid) {
  const codes = l.code === TRIBES ? new Set(l.members) : new Set([l.code]);
  const rows = b.rows.filter(r => codes.has(r[0]));
  if (!rows.length) { el.innerHTML = '<p class="empty">אין קלפיות ליישוב זה בבחירות שנבחרו.</p>'; return; }
  const cols = b.cols; const off = 6;
  const tot = cols.map((c, i) => sum(rows.map(r => r[off + i])));
  const show = cols.map((c, i) => ({ c, i, t: tot[i] })).filter(x => x.c !== 'other').sort((a, z) => z.t - a.t).slice(0, 5);
  const sortKey = el.dataset.sort || 'kalpi', dir = el.dataset.dir === 'asc' ? 1 : -1;
  const keyFn = {
    kalpi: r => parseFloat(r[1]) * (l.code === TRIBES ? 1 : 1) + (l.code === TRIBES ? r[0] * 1000 : 0), elig: r => r[3],
    turnout: r => r[3] ? r[4] / r[3] : 0,
    ...Object.fromEntries(show.map(x => [x.c, r => r[5] ? r[off + x.i] / r[5] : 0])),
  }[sortKey] || (r => 0);
  const sorted = [...rows].sort((p, q) => (keyFn(p) - keyFn(q)) * (sortKey === 'kalpi' ? (el.dataset.dir === 'desc' ? -1 : 1) : dir));
  el.innerHTML = `<table class="t"><thead><tr><th data-sort="kalpi">קלפי</th><th></th><th class="n" data-sort="elig">בעלי זכות</th><th class="n" data-sort="turnout">הצבעה</th>${show.map(x => `<th class="n" data-sort="${esc(x.c)}" title="${esc(partyName(eid, x.c))}">${esc(x.c)}</th>`).join('')}</tr></thead><tbody>${
    sorted.map(r => {
      const sc = r[2] % 10, haredi = r[2] >= 10;
      const tag = (l.sector === 'mixed' || l.sector === 'jewish') && sc === 1 ? '<span class="badge arab">ערבית</span>' : haredi ? '<span class="badge haredi">חרדית</span>' : '';
      const nm = l.code === TRIBES ? (S.core.localities.find(x => x.code === r[0]) || {}).name + ' · ' : '';
      return `<tr class="${sc === 1 && l.sector === 'mixed' ? 'hl' : ''}"><td>${esc(nm)}${esc(r[1])}</td><td>${tag}</td><td class="n">${fmt(r[3])}</td><td class="n">${r[3] ? pct(100 * r[4] / r[3], 0) : '—'}</td>${
        show.map(x => { const s = r[5] ? r[off + x.i] / r[5] : 0; return `<td class="n"><span class="minibar" style="width:${Math.round(s * 34)}px;background:${famColor(famOf(eid, x.c))};margin-inline-end:4px"></span>${pct(100 * s, 0)}</td>`; }).join('')}</tr>`;
    }).join('')}</tbody></table>`;
  $$('th[data-sort]', el).forEach(th => th.addEventListener('click', () => {
    const k = th.dataset.sort;
    el.dataset.dir = el.dataset.sort === k && el.dataset.dir === 'desc' ? 'asc' : 'desc';
    el.dataset.sort = k; drawBallotTable(el, l, b, eid);
  }));
}
