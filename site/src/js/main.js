/* ===================== boot ===================== */
const RENDER = {
  overview: () => renderOverview(), polls: () => renderPolls(), coalition: () => renderCoalition(),
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
    try { RENDER[tab](); } catch (err) { console.error(err); $(`#tab-${tab}`).innerHTML = `<p class="empty">שגיאה בהצגת המדור: ${esc(err.message)}</p>`; }
    rendered.add(tab);
  }
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
  if (days > 0) el.textContent = days;
  else if (days === 0) { el.textContent = 'היום'; el.nextElementSibling.textContent = 'יום הבחירות'; }
  else { el.textContent = '✓'; el.nextElementSibling.textContent = 'הבחירות התקיימו'; }
}

async function boot() {
  countdown();
  try {
    const [core, polls, outline] = await Promise.all([
      fetch('data/core.json').then(r => r.json()),
      fetch('data/polls_2026.json').then(r => r.json()),
      fetch('data/outline.json').then(r => r.json()),
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
  showTab(RENDER[h] ? h : 'overview', { push: false });
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
