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
// wall-clock date and time in Israel, as {y, m, d, h, min}
function ilNow() {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Jerusalem', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
    .formatToParts(new Date()).map(x => [x.type, x.value]));
  return { y: +p.year, m: +p.month, d: +p.day, h: +p.hour % 24, min: +p.minute };
}
const ilStamp = t => t.y * 1e8 + t.m * 1e6 + t.d * 1e4 + t.h * 100 + t.min;   // sortable yyyymmddhhmm
const POLL_BAN = 202610240000;       // Propaganda Methods Law §16ה(ח): from the end of Friday 23.10 ...
const POLLS_CLOSE = 202610272200;    // ... until the polls close on election day
const inPollBan = () => { const t = ilStamp(ilNow()); return t >= POLL_BAN && t < POLLS_CLOSE; };
const inElectionWindow = () => { const t = ilStamp(ilNow()); return t >= ELECTION_DAY[0] && t < ELECTION_DAY[1]; };
const votingHours = () => { const t = ilStamp(ilNow()); return t >= 202610270700 && t < POLLS_CLOSE; };
// Polls published before the blackout may be shown during it only with this notice (statutory wording).
const BAN_NOTICE = 'הסקרים בדף זה פורסמו לפני תחילת התקופה שבה אסור לפרסם סקרי בחירות (מסוף יום שישי, 23.10, עד סגירת הקלפיות). הסקרים אינם עדכניים, ואין ללמוד מהם על דפוסי הצבעה או עמדות של הציבור ביום הפרסום.';
const ELECTION_DAY = [202610270600, 202610281200];   // the site opens on the election-day tab

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

function svgEl(container, w, h, name) {
  // name: the accessible name of the chart (role=img without one is announced as an unnamed image)
  container.innerHTML = '';
  const svg = d3.select(container).append('svg').attr('viewBox', `0 0 ${w} ${h}`).attr('role', 'img');
  return name ? svg.attr('aria-label', name) : svg;
}
// text colour for a label on a filled mark: whichever of ink and white has the higher WCAG contrast,
// with the fill blended over the surface when the mark is translucent
function onFill(c, alpha = 1) {
  const raw = String(c).startsWith('var(') ? cssVar(String(c).slice(4, -1)) : c;
  let k = d3.rgb(raw);
  if (!k || isNaN(k.r)) return 'var(--ink)';
  if (alpha < 1) {
    const b = d3.rgb(cssVar('--surface') || '#ffffff');
    k = d3.rgb(k.r * alpha + b.r * (1 - alpha), k.g * alpha + b.g * (1 - alpha), k.b * alpha + b.b * (1 - alpha));
  }
  const lin = v => ((v /= 255) <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  const L = 0.2126 * lin(k.r) + 0.7152 * lin(k.g) + 0.0722 * lin(k.b);
  return (L + 0.05) / 0.0565 >= 1.05 / (L + 0.05) ? '#0c1320' : '#ffffff';
}
// Text width in px for gutter sizing (canvas measure, same UI font).
const _ctx = document.createElement('canvas').getContext('2d');
function textWidth(str, size = 12.5, weight = 400) {
  _ctx.font = `${weight} ${size}px "IBM Plex Sans Hebrew", "Arial Hebrew", sans-serif`;
  return _ctx.measureText(String(str)).width;
}
// shorten a label with an ellipsis so it fits maxW pixels
function fitLabel(str, maxW, size = 12.5, weight = 400) {
  let s = String(str);
  if (textWidth(s, size, weight) <= maxW) return s;
  while (s.length > 3 && textWidth(s + '…', size, weight) > maxW) s = s.slice(0, -1);
  return s.trim() + '…';
}
function widthOf(el, fallback = 800) { return Math.max(300, Math.round(el.getBoundingClientRect().width || fallback)); }

/* ---------- Bader-Ofer (same rules as pipeline/bader_ofer.py) ---------- */
function baderOfer(votes, { seats = 120, threshold = 0.0325, agreements = [] } = {}) {
  const ids = Object.keys(votes);
  const total = sum(ids.map(k => votes[k]));
  const q = ids.filter(k => k[0] !== '_' && votes[k] >= threshold * total);   // '_other' = small lists not polled
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
  // recency × sample size; prolific firms are damped so one company cannot dominate
  const firm = p => p.firm || p.house;
  const byHouse = d3.rollup(polls.filter(p => toDate(p.date) <= asOf && (asOf - toDate(p.date)) / dayMs <= 28), v => v.length, firm);
  return polls.map(p => {
    const age = (asOf - toDate(p.date)) / dayMs;
    if (age < 0 || age > 28) return 0;
    const rec = Math.pow(0.5, age / halfLife);
    const n = p.n || 700;
    const size = Math.min(1.4, Math.max(0.7, Math.sqrt(n / 700)));
    const k = byHouse.get(firm(p)) || 1;
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

/* Seats → vote shares. Seat counts are rounded results of D'Hondt, so a list
   is placed at the midpoint of its seat band, s + 0.5 (better than s/120 on
   K21–K25: RMSE 0.26 vs 0.37 points). A list that any poll in the window puts
   at 0 seats is estimated poll by poll instead, so its estimate does not jump
   when its average crosses 3 seats: each poll gives its raw % from the CEC
   filing when there is one, else the seat-implied share, else an imputed share
   below the threshold. Same recency weights as the seat average. The shares
   add up to 100%: the lists estimated poll by poll and the small lists that
   pollsters do not ask about (OTHER_SHARE) are fixed first, and the remaining
   lists split the rest in proportion to s + 0.5. */
const OTHER_SHARE = 0.008, CENSORED = 0.022, NEVER_SEATED = 0.01;
function voteSharesFromAverage(avg) {
  const { parties, polls } = S.polls;
  const w = pollWeights(polls, latestDate(), S.halfLife);
  const inWin = polls.map((q, i) => w[i] > 0);
  const midPoll = (q, s) => {
    const K = Object.values(q.seats).filter(x => x > 0).length;
    return (1 - 0.045) * (s + 0.5) / (120 + 0.5 * K);
  };
  // imputed share for a poll that put the list below the threshold and has no filing
  const zeroShare = id => {
    const filed = polls.filter(q => !(q.seats[id] > 0) && q.pct && q.pct[id] != null).map(q => q.pct[id] / 100);
    if (filed.length) return d3.mean(filed);                       // the list's own filed % in zero-seat polls
    return polls.some(q => q.seats[id] > 0) ? CENSORED : NEVER_SEATED;
  };
  const shares = {};
  S.shareBasis = {};
  const byPoll = parties.filter(p => avg[p.id] < 3 || polls.some((q, i) => inWin[i] && !(q.seats[p.id] > 0)));
  byPoll.forEach(p => {
    const z = zeroShare(p.id);
    let sw = 0, sv = 0, filings = 0, n = 0;
    polls.forEach((q, i) => {
      if (!w[i]) return;
      const raw = q.pct && q.pct[p.id] != null ? q.pct[p.id] / 100 : null;
      const est = raw != null ? raw : (q.seats[p.id] || 0) > 0 ? midPoll(q, q.seats[p.id]) : z;
      sw += w[i]; sv += w[i] * est; n++; if (raw != null) filings++;
    });
    shares[p.id] = sw ? sv / sw : z;
    S.shareBasis[p.id] = { polls: n, filings, zero: z };
  });
  const rest = parties.filter(p => !(p.id in shares));
  const left = 1 - OTHER_SHARE - sum(byPoll.map(p => shares[p.id]));
  const units = sum(rest.map(p => avg[p.id] + 0.5));
  rest.forEach(p => { shares[p.id] = left * (avg[p.id] + 0.5) / units; });
  shares._other = OTHER_SHARE;    // counted in the total, never a list (see baderOfer)
  return shares;
}

/* ---------- Monte Carlo ---------- */
function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function gauss(rnd) { let u = 0, v = 0; while (u === 0) u = rnd(); while (v === 0) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
// Surplus-vote agreements reported in the media (Sep–Oct 2026). The CEC publishes the official list after the 16 Oct filing deadline.
const AGREEMENTS_2026 = [['Likud', 'Religious Zionism'], ['Yashar', 'The Democrats'], ['Together', 'Yisrael Beiteinu'], ["Ra'am", 'Joint List']];
/* Final-week poll average vs result, K21–K25 (final_polls.json): Netanyahu-bloc RMSE 2.4 seats,
   Arab lists 1.55 seats. With about 2.5 weeks left the spread is widened by half, to about 3.6 and
   2.3 seats; the factor is an assumption (no averages from 2.5 weeks out are in the data). The bloc spread comes only from the swing between the two Jewish camps and the
   Arab-turnout shock; list-level noise moves votes inside a camp and does not widen the blocs. */
const SIM = { n: 4000, blocSd: 0.023, arabSd: 0.14, partySd: 0.12, addSd: 0.004, agreements: AGREEMENTS_2026 };
const SIM_TARGET = { coal: 3.6, arab: 2.3 };
function simulate(shares, opts = {}) {
  const o = { ...SIM, ...opts };
  const rnd = mulberry32(20261027);
  const parties = S.polls.parties, ids = parties.map(p => p.id);
  // shocks follow the camps in the data, not the editable coalition blocs
  const camp = Object.fromEntries(parties.map(p => [p.id, p.bloc]));
  const camps = [...new Set(Object.values(camp))];
  const members = Object.fromEntries(camps.map(c => [c, ids.filter(id => camp[id] === c)]));
  const cs = sum(members.coal.map(id => shares[id])), os = sum(members.opp.map(id => shares[id]));
  const out = { seats: [], ids };
  for (let i = 0; i < o.n; i++) {
    const swing = gauss(rnd) * o.blocSd;            // points of the total vote, from the opposition to the Netanyahu camp
    const arab = Math.exp(gauss(rnd) * o.arabSd);   // Arab turnout shock, shared by the Arab lists
    const v = {};
    camps.forEach(c => {
      const m = members[c];
      const base = m.map(id => {
        let x = shares[id];
        if (c === 'coal') x *= 1 + swing / cs;
        else if (c === 'opp') x *= 1 - swing / os;
        else if (c === 'arab') x *= arab;
        return Math.max(0.0005, x);
      });
      const noisy = base.map(x => Math.max(0.0005, x * Math.exp(gauss(rnd) * o.partySd) + gauss(rnd) * o.addSd));
      const k = sum(base) / sum(noisy);              // list noise redistributes votes within the camp
      m.forEach((id, j) => { v[id] = noisy[j] * k; });
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
