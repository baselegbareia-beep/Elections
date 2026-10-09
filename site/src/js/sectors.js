/* ===================== sector comparison ===================== */
const SUBS = [
  ['arab_std', 'יישובים ערביים ודרוזיים (סה״כ)', 'arab', true],
  ['arab:negev', 'בדואים בנגב', 'arab'], ['arab:north_bedouin', 'בדואים בצפון', 'arab'], ['arab:wadi_ara', 'ואדי עארה', 'arab'],
  ['arab:triangle_south', 'המשולש הדרומי', 'arab'], ['arab:nazareth', 'נצרת', 'arab'], ['arab:galilee', 'גליל, עמקים וחיפה', 'arab'],
  ['arab:christian', 'כפרים ברוב נוצרי', 'arab'], ['arab:mixed_town', 'שפרעם, מע׳אר, אבו סנאן', 'arab'], ['arab:jerusalem', 'אזור ירושלים', 'arab'],
  ['arab:mixed', 'קלפיות ערביות בערים מעורבות', 'arab'],
  ['druze:druze', 'דרוזים בגליל ובכרמל', 'druze'], ['druze:golan', 'דרוזים ברמת הגולן', 'druze'], ['druze:circassian', 'צ׳רקסים', 'druze'],
  ['jewish:haredi', 'קלפיות חרדיות (אומדן)', 'jewish'], ['jewish:general', 'שאר הקלפיות', 'jewish'],
];
const subStat = (eid, key) => key === 'arab_std' ? E(eid).sectors.arab_std : E(eid).subsectors[key];

function renderSectors() {
  const root = $('#tab-sectors');
  root.innerHTML = `
  <div class="section-head"><div>
    <span class="eyebrow">פילוח · ערבים, יהודים, דרוזים, חרדים</span>
    <h2>מי מצביע, ולמי</h2>
    <p>השוואה בין קבוצות האוכלוסייה על בסיס תוצאות הקלפיות. קבוצות שהוגדרו לפי היישוב (ערבים, דרוזים) הן מדויקות יחסית; ״קלפיות חרדיות״ מוגדרות לפי ההצבעה עצמה (יהדות התורה וש״ס מעל 70%) ולכן הן אומדן בלבד.</p>
  </div></div>
  <div class="controls"><span class="ctl-label">בחירות</span>${seg('sc-el', ELS.map(e => [e, E(e).short]), S.sectorElection)}</div>
  <div class="grid">
    <div class="card c12">
      <h3>שיעור ההצבעה לפי קבוצה</h3>
      <p class="sub">כל תא הוא שיעור ההצבעה של הקבוצה בבחירות. כהה יותר = השתתפות גבוהה יותר.</p>
      <div class="tbl-wrap" id="sc-turn"></div>
    </div>
    <div class="card c12">
      <h3>הצבעה לפי קבוצה</h3>
      <p class="sub">איזה חלק מהקולות הכשרים בכל קבוצה קיבלה כל משפחה פוליטית.</p>
      <div class="tbl-wrap" id="sc-heat"></div>
    </div>
    <div class="card c5">
      <h3>מאיפה מגיעים הקולות של כל רשימה</h3>
      <p class="sub">חלוקת הקולות של כל רשימה לפי הקבוצה שבה ניתנו.</p>
      <div class="chart" id="sc-origin"></div>
      <div class="legend"><span><i style="background:var(--arab)"></i>יישובים ערביים וקלפיות ערביות</span><span><i style="background:var(--druze)"></i>דרוזים וצ׳רקסים</span><span><i style="background:var(--jewish)"></i>יהודים ואחרים</span><span><i style="background:var(--rule-strong)"></i>מעטפות כפולות</span></div>
    </div>
    <div class="card c7">
      <h3>מעמד חברתי-כלכלי והשתתפות</h3>
      <p class="sub">כל עיגול הוא יישוב: מיקומו לפי האשכול החברתי-כלכלי של הלמ״ס (1 = הנמוך) ושיעור ההצבעה; שטחו לפי בעלי זכות הבחירה. יישובים ערביים מרוכזים באשכולות 1–4, ולכן קשה להפריד בין השפעת המגזר להשפעת המעמד.</p>
      <div class="chart" id="sc-scatter"></div>
      <div class="legend"><span><i style="background:var(--jewish)"></i>יישוב יהודי</span><span><i style="background:var(--arab)"></i>יישוב ערבי</span><span><i style="background:var(--druze)"></i>יישוב דרוזי או צ׳רקסי</span><span><i style="background:var(--muted)"></i>עיר מעורבת</span></div>
    </div>
  </div>`;
  const draw = () => { drawTurnHeat(); drawVoteHeat(); drawOrigin(); drawScatter(); };
  onSeg(root, 'sc-el', v => { S.sectorElection = v; drawVoteHeat(); drawOrigin(); drawScatter(); });
  draw();
}

function drawTurnHeat() {
  const sc = d3.scaleLinear().domain([30, 80]).range([cssVar('--seq-0'), cssVar('--seq-1')]).interpolate(d3.interpolateLab).clamp(true);
  const ink = v => (v > 60) === !isDark() ? '#fff' : 'var(--ink)';
  const rows = SUBS.filter(([k]) => ELS.some(e => subStat(e, k)?.elig));
  $('#sc-turn').innerHTML = `<table class="t"><thead><tr><th>קבוצה</th><th class="n">בעלי זכות, 2022</th>${ELS.map(e => `<th class="n">${E(e).short}</th>`).join('')}<th class="n">שינוי מ-2021</th></tr></thead><tbody>${
    rows.map(([k, name, sec, bold]) => {
      const vals = ELS.map(e => { const s = subStat(e, k); return s && s.elig ? 100 * s.voters / s.elig : null; });
      const d = vals[4] != null && vals[3] != null ? vals[4] - vals[3] : null;
      return `<tr><td><span class="slip"><i class="dot" style="background:var(--${sec})"></i><span class="nm" style="${bold ? 'font-weight:700' : ''}">${esc(name)}</span></span></td><td class="n">${fmt(subStat('K25', k)?.elig)}</td>${
        vals.map(v => `<td class="n" style="background:${v == null ? 'transparent' : sc(v)};color:${v == null ? 'inherit' : ink(v)}">${pct(v)}</td>`).join('')}<td class="n">${d == null ? '' : `<span class="num ${d > 0 ? 'delta-up' : 'delta-down'}">${d > 0 ? '+' : '−'}${fmt1(Math.abs(d))}</span>`}</td></tr>`;
    }).join('')}
    <tr><td><span class="slip"><span class="nm" style="font-weight:700">ארצי (רשמי)</span></span></td><td class="n">${fmt(E('K25').eligible)}</td>${ELS.map(e => `<td class="n"><b>${pct(E(e).turnout)}</b></td>`).join('')}<td class="n"></td></tr>
  </tbody></table><p class="foot">שיעורי ההצבעה של ״שאר הקלפיות״ אינם כוללים את המעטפות הכפולות (חיילים, נציגויות ועוד), ולכן נמוכים מהשיעור האמיתי בקבוצה. הקלפיות החרדיות מוגדרות לפי ההצבעה ולכן אינן מדד בלתי תלוי.</p>`;
}

function drawVoteHeat() {
  const eid = S.sectorElection, ev = E(eid);
  const groups = [
    ['arab_std', 'ערבים ודרוזים'], ['arab:mixed', 'ערבים בערים מעורבות'], ['druze:druze', 'דרוזים'],
    ['jewish:haredi', 'קלפיות חרדיות'], ['jewish:general', 'שאר הקלפיות'], ['jewish:envelope', 'מעטפות כפולות'], ['nat', 'ארצי'],
  ];
  const stat = k => k === 'nat' ? { valid: ev.valid, votes: Object.fromEntries(ev.parties.map(p => [p.id, p.votes])) } : subStat(eid, k);
  const fams = [...new Set(ev.parties.filter(p => p.pct >= 1).map(p => p.family))];
  const share = (k, fam) => {
    const s = stat(k); if (!s || !s.valid) return null;
    return sum(ev.parties.filter(p => p.family === fam).map(p => s.votes[p.id] || 0)) / s.valid;
  };
  const sc = d3.scaleLinear().domain([0, 0.5]).range([cssVar('--surface-2'), cssVar('--seq-1')]).interpolate(d3.interpolateLab).clamp(true);
  $('#sc-heat').innerHTML = `<table class="t"><thead><tr><th>משפחה</th>${groups.map(([, n]) => `<th class="n">${n}</th>`).join('')}</tr></thead><tbody>${
    fams.map(f => `<tr><td>${slip('', S.core.families[f].name.split(' / ')[0], famColor(f))}</td>${groups.map(([k]) => {
      const v = share(k, f);
      return `<td class="n" style="background:${v == null ? 'transparent' : sc(v)};color:${v != null && v > 0.3 && !isDark() ? '#fff' : 'var(--ink)'}">${v == null ? '—' : pct(100 * v, v < 0.1 ? 1 : 0)}</td>`;
    }).join('')}</tr>`).join('')}</tbody></table>`;
}

function drawOrigin() {
  const el = $('#sc-origin'); const eid = S.sectorElection, ev = E(eid);
  const parties = ev.parties.filter(p => p.seats > 0 || (p.main && p.pct >= 2.5));
  const W = widthOf(el, 480), rowH = 28, M = { t: 4, r: 110, b: 4, l: 6 };
  const H = M.t + M.b + rowH * parties.length;
  const svg = svgEl(el, W, H);
  const x = d3.scaleLinear().domain([0, 1]).range([W - M.r, M.l]);
  parties.forEach((p, i) => {
    const yy = M.t + i * rowH;
    const parts = [
      ['ערבים', sum(['arab'].map(k => ev.sectors[k].votes[p.id] || 0)), 'var(--arab)'],
      ['דרוזים וצ׳רקסים', ev.sectors.druze.votes[p.id] || 0, 'var(--druze)'],
      ['יהודים ואחרים', (ev.sectors.jewish.votes[p.id] || 0) - (ev.subsectors['jewish:envelope'].votes[p.id] || 0), 'var(--jewish)'],
      ['מעטפות כפולות', ev.subsectors['jewish:envelope'].votes[p.id] || 0, 'var(--rule-strong)'],
    ];
    svg.append('text').attr('class', 'lbl-ink').attr('x', W - 2).attr('y', yy + rowH / 2).attr('dy', '.35em').attr('text-anchor', 'start').text(p.name);
    let acc = 0;
    parts.forEach(([n, v, c]) => {
      const f = v / p.votes, x0 = x(acc), x1 = x(acc + f);
      svg.append('rect').attr('x', x1 + (f > 0.004 ? 1 : 0)).attr('y', yy + 5).attr('width', Math.max(0, x0 - x1 - (f > 0.004 ? 2 : 0))).attr('height', rowH - 10).attr('rx', 2).attr('fill', c)
        .call(sel => bindTT(sel, () => `<h4>${esc(p.name)}</h4>${ttRows(parts.map(([nn, vv, cc]) => [nn, `${pct(100 * vv / p.votes)} · ${fmt(vv)}`, cssVar(cc.slice(4, -1))]))}`));
      acc += f;
    });
  });
}

function drawScatter() {
  const el = $('#sc-scatter'); const eid = S.sectorElection;
  const W = widthOf(el), H = 380, M = { t: 14, r: 20, b: 40, l: 44 };
  const svg = svgEl(el, W, H);
  const locs = S.core.localities.filter(l => l.ses && l.el[eid] && l.el[eid][1] >= 300);
  const x = d3.scaleLinear().domain([0.5, 10.5]).range([M.l, W - M.r]);
  const y = d3.scaleLinear().domain([15, 100]).range([H - M.b, M.t]);
  const r = d3.scaleSqrt().domain([0, d3.max(locs, l => l.el[eid][1])]).range([1.5, 24]);
  [20, 40, 60, 80, 100].forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', M.l).attr('x2', W - M.r).attr('y1', y(v)).attr('y2', y(v));
    svg.append('text').attr('class', 'lbl').attr('x', M.l - 8).attr('y', y(v)).attr('dy', '.32em').attr('text-anchor', 'start').text(v + '%');
  });
  d3.range(1, 11).forEach(v => svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 22).attr('text-anchor', 'middle').text(v));
  svg.append('text').attr('class', 'lbl').attr('x', (M.l + W - M.r) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text('אשכול חברתי-כלכלי של הלמ״ס, 2021 (1 = הנמוך, 10 = הגבוה)');
  const col = { arab: 'var(--arab)', druze: 'var(--druze)', jewish: 'var(--jewish)', mixed: 'var(--muted)' };
  // deterministic jitter so the dots in one cluster spread out
  const jit = l => ((l.code * 9301 + 49297) % 233280) / 233280 - 0.5;
  svg.selectAll('circle').data([...locs].sort((a, b) => b.el[eid][1] - a.el[eid][1])).join('circle')
    .attr('cx', l => x(l.ses + jit(l) * 0.7)).attr('cy', l => y(100 * l.el[eid][2] / l.el[eid][1])).attr('r', l => r(l.el[eid][1]))
    .attr('fill', l => col[l.sector]).attr('fill-opacity', .55).attr('stroke', 'var(--surface)').attr('stroke-width', .6)
    .call(sel => bindTT(sel, l => locTooltip(l, eid)))
    .on('click', (ev, l) => { S.locSel = l.code; S.election = eid; rendered.delete('results'); showTab('results'); });
}
