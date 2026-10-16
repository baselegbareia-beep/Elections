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
  // roving tabindex: only the selected tab is in the Tab order; the arrow keys move between tabs (boot)
  $$('.tab').forEach(b => { const on = b.dataset.tab === tab; b.setAttribute('aria-selected', on); b.tabIndex = on ? 0 : -1; });
  $$('[data-panel]').forEach(p => { p.hidden = p.dataset.panel !== tab; });
  if (!rendered.has(tab)) {
    const fail = err => { console.error(err); rendered.delete(tab); $(`#tab-${tab}`).innerHTML = `<p class="empty">${t('טעינת המדור נכשלה.')} <button type="button" class="slip" data-goto="${tab}">${t('ניסיון נוסף')}</button></p>`; };
    rendered.add(tab);
    try { const r = RENDER[tab](); if (r && r.catch) r.catch(fail); } catch (err) { fail(err); }
  } else if (tab === 'live' && S.liveBlocsStale && typeof redrawLiveBlocs === 'function') {
    // a coalition-calculator edit since the live tab was drawn: its blocs follow the new assignment (PAGE-6)
    try { redrawLiveBlocs(); } catch (err) { console.error(err); }
  }
  if (tab === 'live') S.liveBlocsStale = false;
  const ban = $('#ban-note');
  // every tab that shows polls, including the past exit polls and the poll-average starting point on the live tab
  // (on election day the live tab shows no polls before 22:00, so it gets no notice then)
  if (ban) {
    const on = inPollBan() && ['overview', 'polls', 'coalition', 'arab', 'accuracy', 'live'].includes(tab)
      && !(tab === 'live' && inElectionWindow());
    ban.hidden = !on; if (on) I18N.banNotice(ban);
  }
  if (push) { try { history.replaceState(null, '', '#' + (tab === 'live' && S.ops ? 'live-ops' : tab) + I18N.hashTail()); } catch (e) { /* sandboxed */ } }
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
  if (days > 1) {
    el.textContent = days;
    // Arabic counts take the plural of 3–10 and the dual of 2 ('11 يومًا', '5 أيام', 'يومان')
    if (AR_ON) el.nextElementSibling.textContent = days > 10 ? t('ימים לבחירות') : days > 2 ? AR.__days_few : AR.__days_two;
  }
  else if (days === 1) { el.textContent = t('מחר'); el.nextElementSibling.textContent = t('הבחירות'); }
  else if (days === 0) { el.textContent = t('היום'); el.nextElementSibling.textContent = t('יום הבחירות'); }
  else { el.textContent = '✓'; el.nextElementSibling.textContent = t('הבחירות התקיימו'); }
  // an Arabic word ('غدًا', 'اليوم') needs the line height the numbers do without
  if (AR_ON) el.classList.toggle('cd-word', days === 1 || days === 0);
}

async function boot() {
  I18N.chrome();   // the language switch; in Arabic, the header, the tabs and the footer
  countdown();
  try {
    const [core, polls, outline, names] = await Promise.all([
      fetchJSON('data/core.json'),
      fetchJSON('data/polls_2026.json'),
      fetchJSON('data/outline.json'),
      // Arabic locality names (a locality without one keeps its Hebrew name)
      AR_ON ? fetchJSON('data/names_ar.json').catch(err => { console.error(err); return null; }) : null,
    ]);
    if (names) I18N.loc = names.localities;
    S.core = i18nCore(core); S.polls = i18nPolls(polls); S.outline = outline;
  } catch (err) {
    $('#loading').textContent = t('טעינת הנתונים נכשלה. רעננו את הדף.');
    console.error(err); return;
  }
  $('#loading').remove();
  $$('.tab').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
  // the tab strip as a WAI-ARIA tablist: in RTL the next tab is to the left, so ArrowLeft moves forward
  const tablist = $('[role="tablist"]');
  if (tablist) tablist.addEventListener('keydown', e => {
    const tabs = $$('.tab', tablist), cur = e.target.closest('.tab');
    const i = cur ? tabs.indexOf(cur) : tabs.findIndex(b => b.dataset.tab === S.tab);
    const rtl = getComputedStyle(tablist).direction === 'rtl';
    const j = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1
      : e.key === 'ArrowLeft' ? i + (rtl ? 1 : -1) : e.key === 'ArrowRight' ? i + (rtl ? -1 : 1) : null;
    if (j == null) return;
    e.preventDefault();
    const t = tabs[(j + tabs.length) % tabs.length];
    showTab(t.dataset.tab); t.focus();
  });
  // in-page links between sections
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-goto]'); if (!a) return;
    e.preventDefault(); showTab(a.dataset.goto); window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  let h = I18N.tabHash();
  // '#live-ops': the election-day tab with the feed's own diagnostics (for the operator, PAGE-5)
  if (h === 'live-ops') { S.ops = true; h = 'live'; }
  const now = ilStamp(ilNow());
  const dflt = now >= ELECTION_DAY[0] && now < LANDING_LIVE_UNTIL ? 'live' : 'overview';
  showTab(RENDER[h] ? h : dflt, { push: false });
  // a page left open across a clock gate: the poll ban starting (Sat 24.10 00:00) or ending, and the polls closing
  // (27.10 22:00), re-run the ban notice and redraw the poll tabs, whose footnote and tense follow the clock; the
  // countdown follows the date
  const gates = () => { const t = ilStamp(ilNow()); return `${t >= POLL_BAN}|${t >= POLLS_CLOSE}`; };
  S.clockGates = gates();
  setInterval(() => {
    countdown();
    const g = gates(); if (g === S.clockGates) return;
    S.clockGates = g;
    ['overview', 'coalition'].forEach(k => rendered.delete(k));
    showTab(S.tab, { push: false });
  }, 60000);
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
