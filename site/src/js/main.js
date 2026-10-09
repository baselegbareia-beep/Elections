/* ===================== boot ===================== */
const RENDER = {
  overview: () => renderOverview(), live: () => renderLive(), polls: () => renderPolls(), coalition: () => renderCoalition(),
  arab: () => renderArab(), results: () => renderResults(), sectors: () => renderSectors(),
  accuracy: () => renderAccuracy(), method: () => renderMethod(), plan: () => renderPlan(),
};
const rendered = new Set();

function showTab(tab, { push = true } = {}) {
  if (!RENDER[tab]) tab = 'overview';
  S.tab = tab;
  $$('.tab').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === tab));
  $$('[data-panel]').forEach(p => { p.hidden = p.dataset.panel !== tab; });
  if (!rendered.has(tab)) {
    const fail = err => { console.error(err); rendered.delete(tab); $(`#tab-${tab}`).innerHTML = `<p class="empty">טעינת המדור נכשלה. <button type="button" class="slip" data-goto="${tab}">ניסיון נוסף</button></p>`; };
    rendered.add(tab);
    try { const r = RENDER[tab](); if (r && r.catch) r.catch(fail); } catch (err) { fail(err); }
  }
  const ban = $('#ban-note');
  // every tab that shows polls, including the past exit polls and the poll-average starting point on the live tab
  if (ban) { const on = inPollBan() && ['overview', 'polls', 'coalition', 'arab', 'accuracy', 'live'].includes(tab); ban.hidden = !on; if (on) ban.textContent = BAN_NOTICE; }
  if (push) { try { history.replaceState(null, '', '#' + tab); } catch (e) { /* sandboxed */ } }
  const btn = $(`.tab[data-tab="${tab}"]`); if (btn) btn.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  tt.hide();
}
function rerenderAll() {
  rendered.clear();
  showTab(S.tab, { push: false });
}

function countdown() {
  // days until 27 Oct 2026, counted in Israel time
  const now = new Date();
  const il = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Jerusalem' }));
  const today = Date.UTC(il.getFullYear(), il.getMonth(), il.getDate());
  const days = Math.round((Date.UTC(2026, 9, 27) - today) / dayMs);
  const el = $('#cd-days');
  if (days > 1) el.textContent = days;
  else if (days === 1) { el.textContent = 'מחר'; el.nextElementSibling.textContent = 'הבחירות'; }
  else if (days === 0) { el.textContent = 'היום'; el.nextElementSibling.textContent = 'יום הבחירות'; }
  else { el.textContent = '✓'; el.nextElementSibling.textContent = 'הבחירות התקיימו'; }
}

async function boot() {
  countdown();
  try {
    const [core, polls, outline] = await Promise.all([
      fetchJSON('data/core.json'),
      fetchJSON('data/polls_2026.json'),
      fetchJSON('data/outline.json'),
    ]);
    S.core = core; S.polls = polls; S.outline = outline;
  } catch (err) {
    $('#loading').textContent = 'טעינת הנתונים נכשלה. רעננו את הדף.';
    console.error(err); return;
  }
  $('#loading').remove();
  $$('.tab').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
  // in-page links between sections
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-goto]'); if (!a) return;
    e.preventDefault(); showTab(a.dataset.goto); window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  const h = (location.hash || '').replace('#', '');
  const t = ilStamp(ilNow());
  const dflt = t >= ELECTION_DAY[0] && t < ELECTION_DAY[1] ? 'live' : 'overview';
  showTab(RENDER[h] ? h : dflt, { push: false });
  // label gutters are measured on canvas; redraw once the web fonts are in
  if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(rerenderAll);
  // redraw charts on theme or width change
  if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', rerenderAll);
  new MutationObserver(rerenderAll).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  let lastW = window.innerWidth, timer;
  window.addEventListener('resize', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { if (Math.abs(window.innerWidth - lastW) > 40) { lastW = window.innerWidth; rerenderAll(); } }, 250);
  });
}
boot();
