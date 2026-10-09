/* ===================== core: data, helpers, models ===================== */
'use strict';
const S = {               // app state
  tab: 'overview',
  core: null, polls: null, outline: null, ballots: {},
  election: 'K25',
  mapMode: 'winner', mapParty: null, locality: null,
  adjustHouse: true, halfLife: 10,
  coalition: null, pairIdx: 3, sectorElection: 'K25', arabRegEl: 'K25', arabMixEl: 'K25',
  sims: null,
};
const HE = new Intl.NumberFormat('he-IL');
const fmt = n => n == null || isNaN(n) ? '—' : HE.format(Math.round(n));
const fmt1 = n => n == null || isNaN(n) ? '—' : (Math.round(n * 10) / 10).toLocaleString('he-IL', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const pct = (n, d = 1) => n == null || isNaN(n) ? '—' : n.toLocaleString('he-IL', { minimumFractionDigits: d, maximumFractionDigits: d }) + '%';
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const N = s => `<span class="num">${s}</span>`;
const sum = a => a.reduce((x, y) => x + y, 0);

function isDark() {
  const t = document.documentElement.getAttribute('data-theme');
  if (t) return t === 'dark';
  return window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
}
const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim() ||
  getComputedStyle(document.body).getPropertyValue(name).trim();

/* ---------- colours ---------- */
function famColor(fam) {
  const f = S.core.families[fam] || S.core.families.other;
  return isDark() ? f.dark : f.color;
}
function party26Color(p) { return isDark() ? p.dark : p.color; }
const blocVar = b => ({ coal: '--coal', nb: '--coal', opp: '--opp', arab: '--arab', out: '--muted', other: '--muted' }[b] || '--muted');
const blocColor = b => cssVar(blocVar(b));
const BLOC_NAME = { coal: 'גוש נתניהו', opp: 'האופוזיציה', arab: 'הרשימות הערביות', other: 'אחרות' };

/* ---------- tooltip ---------- */
const tt = {
  el: null,
  show(html, ev) {
    if (!this.el) this.el = $('#tt');
    this.el.innerHTML = html; this.el.classList.add('on'); this.move(ev);
  },
  move(ev) {
    if (!this.el || !ev) return;
    const x = ev.touches ? ev.touches[0].clientX : ev.clientX, y = ev.touches ? ev.touches[0].clientY : ev.clientY;
    const r = this.el.getBoundingClientRect(), W = window.innerWidth, H = window.innerHeight;
    let left = x - r.width - 14; if (left < 8) left = Math.min(x + 14, W - r.width - 8);
    let top = y + 14; if (top + r.height > H - 8) top = Math.max(8, y - r.height - 14);
    this.el.style.left = left + 'px'; this.el.style.top = top + 'px';
  },
  hide() { if (this.el) this.el.classList.remove('on'); },
};
function ttRows(rows) {
  return rows.map(([k, v, c]) => `<div class="row"><span>${c ? `<i class="k" style="background:${c}"></i>` : ''}${esc(k)}</span><span class="num">${v}</span></div>`).join('');
}
function bindTT(sel, html) {
  sel.on('mouseenter', (ev, d) => tt.show(html(d, ev), ev))
     .on('mousemove', ev => tt.move(ev))
     .on('mouseleave', () => tt.hide())
     .on('touchstart', (ev, d) => { tt.show(html(d, ev), ev); }, { passive: true });
}
document.addEventListener('scroll', () => tt.hide(), { passive: true });

/* ---------- ui bits ---------- */
function slip(letters, name, color, extra = '') {
  return `<span class="slip" ${extra}><i class="dot" style="background:${color}"></i>${letters ? `<b class="let">${esc(letters)}</b>` : ''}<span class="nm">${esc(name)}</span></span>`;
}
function seg(id, options, value) {
  return `<div class="seg" role="group" id="${id}">${options.map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${String(v) === String(value)}">${l}</button>`).join('')}</div>`;
}
function onSeg(root, id, cb) {
  const el = $('#' + id, root); if (!el) return;
  el.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    $$('button', el).forEach(x => x.setAttribute('aria-pressed', x === b));
    cb(b.dataset.v);
  });
}
const ICON_OK = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
const ICON_NO = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="2"/></svg>';

function svgEl(container, w, h) {
  container.innerHTML = '';
  return d3.select(container).append('svg').attr('viewBox', `0 0 ${w} ${h}`).attr('role', 'img');
}
// Text width in px for gutter sizing (canvas measure, same UI font).
const _ctx = document.createElement('canvas').getContext('2d');
function textWidth(str, size = 12.5, weight = 400) {
  _ctx.font = `${weight} ${size}px "IBM Plex Sans Hebrew", "Arial Hebrew", sans-serif`;
  return _ctx.measureText(String(str)).width;
}
function widthOf(el, fallback = 800) { return Math.max(300, Math.round(el.getBoundingClientRect().width || fallback)); }

/* ---------- Bader-Ofer (same rules as pipeline/bader_ofer.py) ---------- */
function baderOfer(votes, { seats = 120, threshold = 0.0325, agreements = [] } = {}) {
  const ids = Object.keys(votes);
  const total = sum(ids.map(k => votes[k]));
  const q = ids.filter(k => votes[k] >= threshold * total);
  const res = Object.fromEntries(ids.map(k => [k, 0]));
  if (!q.length) return res;
  const quota = sum(q.map(k => votes[k])) / seats;
  q.forEach(k => { res[k] = Math.floor(votes[k] / quota); });
  const unitOf = {}; q.forEach(k => { unitOf[k] = [k]; });
  agreements.forEach(([a, b]) => {
    if (unitOf[a] && unitOf[b] && unitOf[a].length === 1 && unitOf[b].length === 1) unitOf[a] = unitOf[b] = [a, b];
  });
  const units = [...new Set(q.map(k => unitOf[k]))];
  const uv = u => sum(u.map(k => votes[k]));
  const extra = new Map(units.map(u => [u, 0]));
  let rem = seats - sum(Object.values(res));
  while (rem-- > 0) {
    let best = null, bestQ = -1;
    for (const u of units) {
      const s = sum(u.map(k => res[k])) + extra.get(u);
      const qq = uv(u) / (s + 1);
      if (qq > bestQ || (qq === bestQ && uv(u) > uv(best))) { best = u; bestQ = qq; }
    }
    extra.set(best, extra.get(best) + 1);
  }
  for (const u of units) {
    if (u.length === 1) { res[u[0]] += extra.get(u); continue; }
    const tot = sum(u.map(k => res[k])) + extra.get(u);
    const split = Object.fromEntries(u.map(k => [k, 0]));
    for (let i = 0; i < tot; i++) {
      const k = u.reduce((a, b) => (votes[b] / (split[b] + 1) > votes[a] / (split[a] + 1) ? b : a));
      split[k]++;
    }
    u.forEach(k => { res[k] = split[k]; });
  }
  return res;
}

/* ---------- poll average ---------- */
const dayMs = 864e5;
const toDate = s => new Date(s + 'T12:00:00Z');
function pollWeights(polls, asOf, halfLife) {
  // recency × sample size; prolific pollsters are damped so one house cannot dominate
  const byHouse = d3.rollup(polls.filter(p => toDate(p.date) <= asOf && (asOf - toDate(p.date)) / dayMs <= 28), v => v.length, p => p.house);
  return polls.map(p => {
    const age = (asOf - toDate(p.date)) / dayMs;
    if (age < 0 || age > 28) return 0;
    const rec = Math.pow(0.5, age / halfLife);
    const n = p.n || 700;
    const size = Math.min(1.4, Math.max(0.7, Math.sqrt(n / 700)));
    const k = byHouse.get(p.house) || 1;
    return rec * size / Math.sqrt(k);
  });
}
function houseEffects(polls, parties) {
  // Average deviation of each pollster from the all-poll mean, shrunk toward 0 for small counts.
  const ids = parties.map(p => p.id);
  const mean = Object.fromEntries(ids.map(id => [id, d3.mean(polls, p => p.seats[id] || 0)]));
  const out = {};
  d3.group(polls, p => p.house).forEach((ps, house) => {
    const k = ps.length, shrink = k / (k + 3);
    out[house] = Object.fromEntries(ids.map(id => [id, shrink * (d3.mean(ps, p => p.seats[id] || 0) - mean[id])]));
    out[house]._n = k;
  });
  return out;
}
function pollAverage(asOf, { adjust = S.adjustHouse, halfLife = S.halfLife } = {}) {
  const { polls, parties } = S.polls;
  const w = pollWeights(polls, asOf, halfLife);
  // house effects use only polls published by asOf, so the trend line has no look-ahead
  const known = polls.filter(p => toDate(p.date) <= asOf);
  const heKnown = adjust && known.length ? houseEffects(known, parties) : null;
  const he = heKnown && Object.fromEntries(polls.map(p => [p.house, heKnown[p.house] || Object.fromEntries(parties.map(pt => [pt.id, 0]))]));
  const tw = sum(w);
  const avg = {}, lo = {}, hi = {};
  parties.forEach(pt => {
    let s = 0; const vals = [];
    polls.forEach((p, i) => {
      if (!w[i]) return;
      const v = (p.seats[pt.id] || 0) - (he ? he[p.house][pt.id] : 0);
      s += w[i] * v; vals.push(p.seats[pt.id] || 0);
    });
    avg[pt.id] = tw ? s / tw : 0;
    lo[pt.id] = d3.min(vals); hi[pt.id] = d3.max(vals);
  });
  // keep the seat average on a 120 scale after the house correction
  const t = sum(Object.values(avg));
  if (t > 0) Object.keys(avg).forEach(k => { avg[k] = Math.max(0, avg[k] * 120 / t); });
  return { avg, lo, hi, n: w.filter(Boolean).length };
}
function latestDate() { return toDate(S.polls.polls[S.polls.polls.length - 1].date); }

/* Seats → vote shares. Seat counts are rounded results of D'Hondt, so the
   midpoint inverse v = (1 − w)(s + 0.5) / (120 + 0.5K) fits official K21–K25
   results better than s/120 (RMSE 0.26 vs 0.37 points). A list averaging under
   3 seats is a mix of "0" (below threshold, not 0%) and 4–5 seat polls: each
   poll in the averaging window contributes its raw % from the CEC filing when
   there is one, else the seat-implied share, or 2.2% for a poll that put the
   list below the threshold. Same recency weights as the seat average. */
const WASTED = 0.045, CENSORED = 0.022;
function voteSharesFromAverage(avg) {
  const shares = {};
  const K = S.polls.parties.filter(p => avg[p.id] >= 3).length;
  const mid = s => (1 - WASTED) * (s + 0.5) / (120 + 0.5 * K);
  const w = pollWeights(S.polls.polls, latestDate(), S.halfLife);
  S.shareBasis = {};
  S.polls.parties.forEach(p => {
    if (avg[p.id] >= 3) { shares[p.id] = mid(avg[p.id]); return; }
    let sw = 0, sv = 0, filings = 0, n = 0;
    S.polls.polls.forEach((q, i) => {
      if (!w[i]) return;
      const raw = q.pct && q.pct[p.id] != null ? q.pct[p.id] / 100 : null;
      const est = raw != null ? raw : (q.seats[p.id] || 0) > 0 ? mid(q.seats[p.id]) : CENSORED;
      sw += w[i]; sv += w[i] * est; n++; if (raw != null) filings++;
    });
    shares[p.id] = sw ? sv / sw : CENSORED;
    S.shareBasis[p.id] = { polls: n, filings };
  });
  shares._other = Math.max(0.005, 1 - sum(Object.values(shares)));
  return shares;
}

/* ---------- Monte Carlo ---------- */
function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function gauss(rnd) { let u = 0, v = 0; while (u === 0) u = rnd(); while (v === 0) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
// Uncertainty calibrated on final-poll errors K21–K25 (Netanyahu-bloc RMSE ≈ 2.1 seats in the final week,
// Arab lists ≈ 1.7 seats), widened for the ~2.5 weeks left before election day.
// Surplus-vote agreements reported in the media (Sep–Oct 2026). The CEC publishes the official list after the 16 Oct filing deadline.
const AGREEMENTS_2026 = [['Likud', 'Religious Zionism'], ['Yashar', 'The Democrats'], ['Together', 'Yisrael Beiteinu'], ["Ra'am", 'Joint List']];
const SIM = { n: 4000, blocSd: 0.024, arabSd: 0.13, partySd: 0.10, addSd: 0.004, agreements: AGREEMENTS_2026 };
function simulate(shares, blocOf, opts = {}) {
  const o = { ...SIM, ...opts };
  const rnd = mulberry32(20261027);
  const ids = S.polls.parties.map(p => p.id);
  const out = { seats: [], ids };
  for (let i = 0; i < o.n; i++) {
    const swing = gauss(rnd) * o.blocSd;            // coalition vs opposition, shared by all lists in the bloc
    const arab = Math.exp(gauss(rnd) * o.arabSd);   // Arab turnout shock, shared by the Arab lists
    const v = {};
    ids.forEach(id => {
      let x = shares[id];
      const b = blocOf[id];
      if (b === 'coal') x *= 1 + swing / 0.45;
      else if (b === 'opp') x *= 1 - swing / 0.42;
      if (b === 'arab') x *= arab;
      x = x * Math.exp(gauss(rnd) * o.partySd) + gauss(rnd) * o.addSd;
      v[id] = Math.max(0.0005, x);
    });
    v._other = shares._other;
    const seats = baderOfer(v, { agreements: o.agreements });
    out.seats.push(ids.map(id => seats[id]));
  }
  return out;
}
function simSummary(sim, members) {
  const idx = members.map(id => sim.ids.indexOf(id)).filter(i => i >= 0);
  const tot = sim.seats.map(s => sum(idx.map(i => s[i])));
  return { p61: tot.filter(t => t >= 61).length / tot.length, tot, median: d3.median(tot),
           q10: d3.quantile([...tot].sort(d3.ascending), 0.1), q90: d3.quantile([...tot].sort(d3.ascending), 0.9) };
}

/* ---------- historical helpers ---------- */
const E = id => S.core.elections.find(e => e.id === id);
const PREV = { K22: 'K21', K23: 'K22', K24: 'K23', K25: 'K24' };
const COMPACT = { K21: '4/19', K22: '9/19', K23: '3/20', K24: '3/21', K25: '11/22', K26: '10/26' };
const elLabel = (eid, W) => (W < 560 ? COMPACT[eid] : (eid === 'K26' ? '2026' : E(eid).short));
function partyMeta(eid, letter) {
  const el = E(eid); return el.parties.find(p => p.id === letter);
}
function famOf(eid, letter) {
  if (letter === 'other') return 'other';
  const p = partyMeta(eid, letter); return p ? p.family : 'other';
}
function partyName(eid, letter) {
  if (letter === 'other') return 'אחרות';
  const p = partyMeta(eid, letter); return p ? p.name : letter;
}
function locVotes(loc, eid) {
  const row = loc.el[eid]; if (!row) return null;
  const cols = S.core.party_cols[eid];
  const [boxes, elig, voters, valid, arabBoxes, ...v] = row;
  return { boxes, elig, voters, valid, arabBoxes, votes: Object.fromEntries(cols.map((c, i) => [c, v[i]])) };
}
async function loadBallots(eid) {
  if (!S.ballots[eid]) {
    S.ballots[eid] = fetchJSON(`data/ballots_${eid}.json`).catch(err => { delete S.ballots[eid]; throw err; });
  }
  return S.ballots[eid];
}
function fetchJSON(url) {
  return fetch(url).then(r => { if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json(); });
}
// Every tab that reads the poll average, the simulation or the bloc assignment.
function invalidatePolls() {
  S.sims = null;
  ['overview', 'polls', 'coalition', 'arab', 'method'].forEach(t => { if (t !== S.tab) rendered.delete(t); });
}
// Date-only strings ('2022-11-01') are calendar dates: format them in UTC so no viewer sees the previous day.
const dateHe = (s, opts = { day: 'numeric', month: 'long', year: 'numeric' }) => toDate(s).toLocaleDateString('he-IL', { ...opts, timeZone: 'UTC' });
