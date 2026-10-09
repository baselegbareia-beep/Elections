/* ===================== polls vs results, K21–K25 ===================== */
S.accEl = 'K25';
// Netanyahu camp as it was framed before each election (includes right-wing lists that then missed the threshold)
const PRE_BLOC = {
  K21: ['מחל', 'שס', 'ג', 'טב', 'כ', 'נ', 'ז', 'ל'], K22: ['מחל', 'שס', 'ג', 'טב', 'כף'], K23: ['מחל', 'שס', 'ג', 'טב', 'נץ'],
  K24: ['מחל', 'שס', 'ג', 'ט'], K25: ['מחל', 'ט', 'שס', 'ג'],
};

async function renderAccuracy() {
  const root = $('#tab-accuracy');
  root.innerHTML = '<p class="loading">טוען סקרים היסטוריים…</p>';
  if (!S.finalPolls) S.finalPolls = await fetchJSON('data/final_polls.json');
  const F = S.finalPolls;
  const fe = id => F.elections.find(e => e.id === id);
  const blocErr = id => { const e = fe(id); return sum(PRE_BLOC[id].map(k => e.avg[k] || 0)) - sum(PRE_BLOC[id].map(k => e.actual[k] || 0)); };
  const arabErr = id => { const e = fe(id); const ids = arabLists(id).map(p => p.id); return sum(ids.map(k => e.avg[k] || 0)) - sum(ids.map(k => e.actual[k] || 0)); };
  root.innerHTML = `
  <div class="section-head"><div>
    <span class="eyebrow">${sum(F.elections.map(e => e.polls.length))} סקרים אחרונים · 5 מערכות בחירות</span>
    <h2>כמה צדקו הסקרים?</h2>
    <p>הסקרים האחרונים שפורסמו בכל מערכת (בחמשת הימים שלפני יום שישי האחרון, שבו מותר לפרסם) מול התוצאה הרשמית. הטעות מחושבת על ממוצע הסקרים ולא על סקר בודד.</p>
  </div></div>
  <div class="grid">
    <div class="card c12">
      <h3>טעות ממוצעת לכל רשימה, במושבים</h3>
      <p class="sub">כמה מושבים רחוק היה ממוצע הסקרים האחרונים מהתוצאה, בממוצע לרשימה. לצדה: הטעות בגוש נתניהו כפי שהוגדר לפני הבחירות, ובסך הרשימות הערביות.</p>
      <div class="tbl-wrap"><table class="t"><thead><tr><th>בחירות</th><th class="n">סקרים</th><th class="n">טעות ממוצעת לרשימה</th><th class="n">גוש נתניהו: סקרים מול תוצאה</th><th class="n">רשימות ערביות: סקרים מול תוצאה</th><th>מה השתבש</th></tr></thead><tbody>${
        F.elections.map(e => {
          const be = blocErr(e.id), ae = arabErr(e.id);
          const sign = v => `<span class="num" style="${Math.abs(v) >= 2 ? 'color:var(--crit);font-weight:600' : ''}">${v > 0 ? '+' : v < 0 ? '−' : ''}${fmt1(Math.abs(v))}</span>`;
          return `<tr><td><b>${E(e.id).short}</b> · ${E(e.id).label}</td><td class="n">${e.polls.length}</td><td class="n"><span class="minibar" style="width:${Math.round(e.mae * 26)}px;background:var(--ink);margin-inline-end:6px"></span>${fmt1(e.mae)}</td><td class="n">${sign(be)}</td><td class="n">${sign(ae)}</td><td style="min-width:260px">${esc(LESSON[e.id])}</td></tr>`;
        }).join('')}</tbody></table></div>
      <p class="foot">ערך חיובי = הסקרים נתנו יותר מהתוצאה. גוש נתניהו כפי שהוגדר לפני הבחירות כולל רשימות ימין שבסוף לא עברו את אחוז החסימה (הימין החדש וזהות באפריל 2019, עוצמה יהודית בספטמבר 2019 וב-2020), ובאפריל 2019 גם את ישראל ביתנו. בספטמבר 2019 הסקרים הגזימו בגוש בגלל עוצמה יהודית, שנמדדה ב-4 מושבים ולא עברה; ב-2021 וב-2022 הם חסרו לו 2–4 מושבים.</p>
    </div>
    <div class="card c12">
      <div class="card-head"><div><h3>ממוצע הסקרים מול התוצאה, לפי רשימה</h3><p class="sub">עיגול חלול = ממוצע הסקרים האחרונים; עיגול מלא = התוצאה הרשמית; נקודות קטנות = סקרים בודדים.</p></div>${seg('acc-el', ELS.map(e => [e, E(e).short]), S.accEl)}</div>
      <div class="chart" id="acc-dumb"></div>
    </div>
    <div class="card c6">
      <h3>חמישה לקחים לבחירות 2026</h3>
      <ul class="callout-list" style="margin-top:10px">
        <li><span class="n">1</span><p><b>ש״ס קיבלה בכל חמש המערכות יותר ממה שחזו הסקרים</b>, בממוצע ${fmt1(-d3.mean(F.elections, e => e.error['שס']))} מושבים. זו ההטיה העקבית ביותר שנמצאה.</p></li>
        <li><span class="n">2</span><p><b>רשימה שנמדדה ב-4–6 מושבים נפלה מתחת לאחוז החסימה בשלוש מתוך חמש מערכות</b>: הימין החדש וזהות (2019), עוצמה יהודית (ספטמבר 2019) ומרצ (2022).</p></li>
        <li><span class="n">3</span><p><b>הסקרים ״נתקעים״ על 4 מושבים ליד הסף.</b> ב-2022 כל 13 הסקרים האחרונים נתנו בדיוק 4 לרע״ם ו-4 לחד״ש-תע״ל; שתיהן קיבלו 5.</p></li>
        <li><span class="n">4</span><p><b>הטעות ברשימות הערביות עוקבת אחרי שיעור ההצבעה.</b> כשההשתתפות עלתה (2019 ב׳, 2020, 2022) הסקרים חסרו להן 1–2 מושבים; כשירדה (2021) הם הגזימו.</p></li>
        <li><span class="n">5</span><p><b>גם סקרי המדגם טועים ליד הסף:</b> ב-2021 כל שלושת סקרי המדגם בערוצים השאירו את רע״ם בחוץ, והיא קיבלה 4 מושבים.</p></li>
      </ul>
    </div>
    <div class="card c6">
      <h3>מדד דיוק לפי סוקר</h3>
      <p class="sub">כמה כל סוקר היה מדויק יותר (מינוס) או פחות (פלוס) מהסוקרים האחרים באותן בחירות, בממוצע לרשימה. ההשוואה היא בתוך כל מערכת, כי אפריל 2019 הייתה קשה במיוחד לכולם.</p>
      <div class="tbl-wrap" id="acc-houses"></div>
      <p class="foot">${esc(F.source)}. מספרי המדגם לא נכללו במקורות, ולכן כל סקר מקבל משקל שווה.</p>
    </div>
  </div>`;
  onSeg(root, 'acc-el', v => { S.accEl = v; drawDumbbell(); });
  drawDumbbell(); drawHouseAccuracy();
}
const LESSON = {
  K21: 'הליכוד וכחול לבן קיבלו כ-6–7 מושבים יותר מהסקרים; הימין החדש וזהות נמדדו ב-5–6 ולא עברו.',
  K22: 'עוצמה יהודית נמדדה ב-4 ולא עברה; הרשימה המשותפת וש״ס קיבלו 2 מושבים יותר.',
  K23: 'המערכת המדויקת ביותר. הליכוד והרשימה המשותפת מעט מעל הסקרים.',
  K24: 'רשימות ליד הסף (כחול לבן, מרצ, העבודה) קיבלו יותר מהצפוי; תקווה חדשה וימינה פחות.',
  K25: 'גוש נתניהו קיבל 64 מול כ-60 בסקרים; מרצ נמדדה ב-4–5 ולא עברה.',
};

function drawDumbbell() {
  const el = $('#acc-dumb'); const F = S.finalPolls; const e = F.elections.find(x => x.id === S.accEl);
  const letters = Object.keys(e.actual).filter(k => (e.actual[k] || 0) > 0 || (e.avg[k] || 0) >= 2).sort((a, b) => (e.actual[b] - e.actual[a]) || (e.avg[b] - e.avg[a]));
  const W = widthOf(el), rowH = 28, M = { t: 26, r: 160, b: 24, l: 70 };
  const H = M.t + M.b + rowH * letters.length;
  const svg = svgEl(el, W, H);
  const maxV = Math.max(36, d3.max(e.polls, p => d3.max(Object.values(p.seats))) + 2);
  const x = d3.scaleLinear().domain([0, maxV]).range([W - M.r, M.l]);
  svg.append('rect').attr('class', 'zone').attr('x', x(3.9)).attr('y', M.t - 6).attr('width', x(0) - x(3.9)).attr('height', H - M.t - M.b + 6);
  d3.range(0, maxV + 1, 5).forEach(v => {
    svg.append('line').attr('class', 'gridline').attr('x1', x(v)).attr('x2', x(v)).attr('y1', M.t - 6).attr('y2', H - M.b);
    svg.append('text').attr('class', 'lbl').attr('x', x(v)).attr('y', H - 6).attr('text-anchor', 'middle').text(v);
  });
  svg.append('text').attr('class', 'lbl').attr('x', M.l - 8).attr('y', 14).attr('text-anchor', 'start').text('סקרים מול תוצאה');
  letters.forEach((k, i) => {
    const yy = M.t + i * rowH + rowH / 2;
    const fam = famOf(e.id, k), c = famColor(fam);
    svg.append('text').attr('x', W - 2).attr('y', yy).attr('dy', '.35em').attr('text-anchor', 'start').style('font', '700 15px var(--font-display)').style('fill', 'var(--ink)').text(k);
    svg.append('text').attr('class', 'lbl-ink').attr('x', W - 44).attr('y', yy).attr('dy', '.35em').attr('text-anchor', 'start').text(partyName(e.id, k));
    e.polls.forEach(p => svg.append('circle').attr('cx', x(p.seats[k] || 0)).attr('cy', yy + ((p.pollster.length * 7) % 9) - 4).attr('r', 2).attr('fill', c).attr('opacity', .3));
    const a = e.avg[k] || 0, r = e.actual[k] || 0;
    svg.append('line').attr('x1', x(a)).attr('x2', x(r)).attr('y1', yy).attr('y2', yy).attr('stroke', c).attr('stroke-width', 3).attr('opacity', .5);
    svg.append('circle').attr('cx', x(a)).attr('cy', yy).attr('r', 6).attr('fill', 'var(--surface)').attr('stroke', c).attr('stroke-width', 2.5);
    svg.append('circle').attr('cx', x(r)).attr('cy', yy).attr('r', 6).attr('fill', c);
    const err = a - r;
    svg.append('text').attr('class', 'lbl-strong').attr('x', M.l - 8).attr('y', yy).attr('dy', '.35em').attr('text-anchor', 'start').style('direction', 'ltr')
      .style('fill', Math.abs(err) >= 2 ? 'var(--crit)' : 'var(--ink)').text(`${err > 0 ? '+' : err < 0 ? '−' : ''}${fmt1(Math.abs(err))}`);
    svg.append('rect').attr('x', 0).attr('y', yy - rowH / 2).attr('width', W).attr('height', rowH).attr('fill', 'transparent')
      .call(sel => bindTT(sel, () => `<h4>${esc(partyName(e.id, k))}</h4>${ttRows([['ממוצע הסקרים', fmt1(a)], ['תוצאה רשמית', r], ['טווח הסקרים', `${d3.min(e.polls, p => p.seats[k] || 0)}–${d3.max(e.polls, p => p.seats[k] || 0)}`]])}`));
  });
}

function drawHouseAccuracy() {
  const F = S.finalPolls; const acc = new Map();
  F.elections.forEach(e => {
    const keys = Object.keys(e.actual);
    const maes = e.polls.map(p => d3.mean(keys, k => Math.abs((p.seats[k] || 0) - (e.actual[k] || 0))));
    const base = d3.mean(maes);
    e.polls.forEach((p, i) => {
      const key = p.pollster_he;
      if (!acc.has(key)) acc.set(key, { n: 0, rel: 0, raw: 0, els: new Set() });
      const a = acc.get(key); a.n++; a.rel += maes[i] - base; a.raw += maes[i]; a.els.add(E(e.id).short);
    });
  });
  const rows = [...acc].map(([k, v]) => ({ k, n: v.n, rel: v.rel / v.n, raw: v.raw / v.n, els: [...v.els] })).filter(r => r.n >= 2).sort((a, b) => a.rel - b.rel);
  const sgn = v => `${v > 0 ? '+' : v < 0 ? '−' : ''}${fmt1(Math.abs(v))}`;
  $('#acc-houses').innerHTML = `<table class="t"><thead><tr><th>סוקר</th><th class="n">סקרים</th><th class="n">מול הסוקרים האחרים</th><th class="n">טעות ממוצעת לרשימה</th><th>מערכות</th></tr></thead><tbody>${
    rows.map(r => `<tr><td>${esc(r.k)}</td><td class="n">${r.n}</td><td class="n"><b class="num">${sgn(r.rel)}</b></td><td class="n">${fmt1(r.raw)}</td><td>${r.els.join(', ')}</td></tr>`).join('')}</tbody></table>`;
}
