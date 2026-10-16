#!/usr/bin/env python3
"""The Arabic version's dictionaries (site/src/js/i18n.js) against the Hebrew sources.

    python3 pipeline/check_i18n.py [-v]

The Hebrew text is the key into AR, so a Hebrew string edited anywhere falls back to Hebrew on the Arabic page
without an error. This exits 1, listing each problem, when:
  1. a t('…') literal in site/src/js has no AR entry, or its entry has other {placeholders} or other tags, or the
     call does not pass a value the key names (or the Arabic function uses); a key built with + is reported too
     (t() takes a literal, a ?: or ||/&& of literals, or a data value);
  2. an AR or AR_PARTY key is in none of the Hebrew sources: the string literals of site/src/js (outside the
     dictionaries), the strings of site/data/*.json and site/live/*.json, the text of site/src/index.html, the
     strings of pipeline/live_fetch.py and pipeline/live_model.py (the feed's labels). The Hebrew was changed or
     removed, and the entry is stale;
  3. a t() literal of I18N.chrome (the header and the footer, copied from site/src/index.html) is no longer in
     site/src/index.html, or a tab label there has no AR entry;
  4. a string the page puts through t() as its data file loads (DATA_T below, which follows i18nCore, i18nPolls,
     i18nFinalPolls, i18nArabDay, i18nReplay and i18nTurnoutHistory) has no AR entry;
  5. a 2026 list's leader in site/data/polls_2026.json is not the Hebrew name AR_LEADER has for that list, or
     AR_LEADER has a list the data does not, or a 2026 list's name has no AR_PARTY entry;
  6. a pollster, a channel or whoever commissioned a poll (polls_2026.json, final_polls.json, the replay's exit
     polls) has no Arabic form in AR_ORG, as tOrg() reads it;
  7. a dictionary has a key twice (the later one silently wins in JS).
Standard library only: the JS is read with a small tokenizer (strings, template literals, regex literals,
comments), enough for the page's own code. Usable from another script: problems() returns the list.
"""
import argparse, ast, glob, html.parser, json, os, re, sys
from collections import namedtuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(ROOT, 'site', 'src', 'js')
HEB = re.compile('[֐-׿]')
DICTS = ('AR_PARTY', 'AR_LEADER', 'AR_ORG', 'AR')
FEED_PY = ('live_fetch.py', 'live_model.py')

# ---------- a JS tokenizer ----------
Tok = namedtuple('Tok', 'kind value pos')    # kind: str tpl tpl_head tpl_mid tpl_tail regex num id p
PUNCT = sorted(['>>>=', '...', '===', '!==', '**=', '<<=', '>>=', '>>>', '&&=', '||=', '??=', '=>', '==', '!=', '<=',
                '>=', '&&', '||', '??', '?.', '++', '--', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '**', '<<',
                '>>'], key=len, reverse=True)
REGEX_AFTER = {'return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'new', 'delete', 'void', 'throw', 'instanceof',
               'yield', 'await'}
IDENT = re.compile(r'[A-Za-z_$\u0080-￿][\w$\u0080-￿]*')
NUM = re.compile(r'0[xXbBoO][\da-fA-F_]+n?|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?n?')
ESC = {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f', 'v': '\v', '0': '\0'}


def unescape(src, j):
    """the character(s) an escape at src[j] ('\\') stands for, and where the escape ends"""
    d = src[j + 1]
    if d == 'x':
        return chr(int(src[j + 2:j + 4], 16)), j + 4
    if d == 'u':
        if src[j + 2] == '{':
            k = src.index('}', j)
            return chr(int(src[j + 3:k], 16)), k + 1
        return chr(int(src[j + 2:j + 6], 16)), j + 6
    if src.startswith('\r\n', j + 1):
        return '', j + 3
    if d in '\n\r  ':          # a line continuation
        return '', j + 2
    return ESC.get(d, d), j + 2


def tokenize(src):
    toks, i, n = [], 0, len(src)
    subst = []          # one entry per open ${…}: the depth of { inside it

    def regex_ok():
        if not toks:
            return True
        k, v = toks[-1].kind, toks[-1].value
        if k == 'id':
            return v in REGEX_AFTER
        if k == 'p':
            return v not in (')', ']', '}')
        return k in ('tpl_head', 'tpl_mid')

    while i < n:
        c = src[i]
        if c.isspace() or c == '﻿':
            i += 1
        elif src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
        elif src.startswith('/*', i):
            i = src.index('*/', i + 2) + 2
        elif c in '\'"':
            j, buf = i + 1, []
            while src[j] != c:
                if src[j] == '\\':
                    s, j = unescape(src, j)
                    buf.append(s)
                else:
                    buf.append(src[j])
                    j += 1
            toks.append(Tok('str', ''.join(buf), i))
            i = j + 1
        elif c == '`' or (c == '}' and subst and subst[-1] == 0):
            head = c == '`'
            if not head:
                subst.pop()
            j, buf = i + 1, []
            while True:
                if src[j] == '\\':
                    s, j = unescape(src, j)
                    buf.append(s)
                elif src[j] == '`':
                    kind, j = ('tpl' if head else 'tpl_tail'), j + 1
                    break
                elif src.startswith('${', j):
                    kind, j = ('tpl_head' if head else 'tpl_mid'), j + 2
                    subst.append(0)
                    break
                else:
                    buf.append(src[j])
                    j += 1
            toks.append(Tok(kind, ''.join(buf), i))
            i = j
        elif c == '/' and regex_ok():
            j, cls = i + 1, False
            while src[j] != '/' or cls:
                if src[j] == '\\':
                    j += 1
                elif src[j] == '[':
                    cls = True
                elif src[j] == ']':
                    cls = False
                elif src[j] == '\n':
                    raise SyntaxError(f'unterminated regex at {i}')
                j += 1
            j += 1
            while j < n and src[j].isalpha():
                j += 1
            toks.append(Tok('regex', src[i:j], i))
            i = j
        elif c.isdigit() or (c == '.' and src[i + 1:i + 2].isdigit()):
            m = NUM.match(src, i)
            toks.append(Tok('num', m.group(), i))
            i = m.end()
        elif IDENT.match(src, i):
            m = IDENT.match(src, i)
            toks.append(Tok('id', m.group(), i))
            i = m.end()
        else:
            p = next((q for q in PUNCT if src.startswith(q, i)), c)
            if subst and p == '{':
                subst[-1] += 1
            elif subst and p == '}':
                subst[-1] -= 1
            toks.append(Tok('p', p, i))
            i += len(p)
    return toks


def depth_step(tk):
    if tk.kind == 'p':
        return 1 if tk.value in ('(', '[', '{') else -1 if tk.value in (')', ']', '}') else 0
    return 1 if tk.kind == 'tpl_head' else -1 if tk.kind == 'tpl_tail' else 0


def closing(toks, i):
    """the index of the token that closes the bracket at toks[i]"""
    d = 0
    for j in range(i, len(toks)):
        d += depth_step(toks[j])
        if d == 0:
            return j
    raise SyntaxError(f'unclosed bracket at {toks[i].pos}')


def is_p(tk, *vals):
    return tk.kind == 'p' and tk.value in vals


# ---------- the dictionaries of i18n.js ----------
Entry = namedtuple('Entry', 'key value line')    # value: a string, [he, ar] (AR_LEADER) or ('fn', {names used})


def read_dicts(src, toks):
    """{name: [Entry]} and the token ranges the dictionaries take"""
    dicts, spans = {}, []
    for i in range(len(toks) - 3):
        if not (toks[i].value == 'const' and toks[i + 1].kind == 'id' and toks[i + 1].value in DICTS
                and is_p(toks[i + 2], '=') and is_p(toks[i + 3], '{')):
            continue
        end = closing(toks, i + 3)
        spans.append((i, end))
        out, j = [], i + 4
        while j < end:
            k = toks[j]
            if not is_p(toks[j + 1], ':'):
                raise SyntaxError(f'{toks[i + 1].value}: an entry that is not key: value at line {line_of(src, k.pos)}')
            v0 = v1 = j + 2
            d = 0
            while v1 < end and not (d == 0 and is_p(toks[v1], ',')):
                d += depth_step(toks[v1])
                v1 += 1
            val = toks[v0:v1]
            if len(val) == 1 and val[0].kind == 'str':
                value = val[0].value
            elif any(is_p(x, '=>') for x in val):
                param = val[0].value if val[0].kind == 'id' else val[1].value
                value = ('fn', {val[x + 2].value for x in range(len(val) - 2)
                                if val[x].kind == 'id' and val[x].value == param and is_p(val[x + 1], '.')})
            elif is_p(val[0], '[') and [x.kind for x in val[1:-1:2]] == ['str'] * ((len(val) - 1) // 2):
                value = [x.value for x in val[1:-1:2]]
            else:
                raise SyntaxError(f'{toks[i + 1].value}: an unexpected value at line {line_of(src, k.pos)}')
            out.append(Entry(k.value, value, line_of(src, k.pos)))
            j = v1 + 1
        dicts[toks[i + 1].value] = out
    return dicts, spans


def line_of(src, pos):
    return src.count('\n', 0, pos) + 1


# ---------- t() and its keys ----------
OPENS = ('(', '?', ':', '||', '&&', '??')       # a key literal follows one of these inside t( … )
CLOSES = (',', ')', ':', '||', '&&', '??')


def passed(toks, j):
    """the names an object literal at toks[j] (t()'s second argument) passes; None when it is not a plain one"""
    if not is_p(toks[j], '{'):
        return None
    end, d, names = closing(toks, j), 0, set()
    for k in range(j, end):
        x = toks[k]
        if d == 1 and x.kind in ('id', 'str') and (k == j + 1 or is_p(toks[k - 1], ',')) and is_p(toks[k + 1], ':', ',', '}'):
            names.add(x.value)
        elif d == 1 and is_p(x, '...', '['):
            return None
        d += depth_step(x)
    return names


def t_keys(toks, skip=()):
    """(token index, key, built, the names passed) for each Hebrew literal t() is called with: the first argument,
    or a branch of a ?: or ||/&& that is; built marks a literal joined with + into the key; the names are None when
    the values are not an object literal"""
    for i in range(len(toks) - 1):
        tk = toks[i]
        if not (tk.kind == 'id' and tk.value == 't' and is_p(toks[i + 1], '(')) or any(a <= i <= b for a, b in skip):
            continue
        if i and (is_p(toks[i - 1], '.', '?.') or toks[i - 1].value == 'function'):
            continue
        j, d, found = i + 2, 0, []
        while not (d == 0 and is_p(toks[j], ',', ')')):
            x = toks[j]
            if d == 0 and x.kind == 'str' and HEB.search(x.value):
                prev, nxt = toks[j - 1], toks[j + 1]
                if is_p(prev, '+') or is_p(nxt, '+'):
                    found.append((j, x.value, True))
                elif (is_p(prev, *OPENS) and (j > i + 2 or prev.value == '(')) and is_p(nxt, *CLOSES):
                    found.append((j, x.value, False))
            d += depth_step(x)
            j += 1
        names = passed(toks, j + 1) if is_p(toks[j], ',') else set()
        for k, key, built in found:
            yield k, key, built, names


PH = re.compile(r'\{(\w+)\}')
TAG = re.compile(r'</?([a-zA-Z][a-zA-Z0-9]*)')


def placeholders(s):
    return set(PH.findall(s))


def tags(s):
    return sorted(x.lower() for x in TAG.findall(s))


# ---------- the Hebrew sources ----------
def json_strings(x, out):
    if isinstance(x, str):
        out.add(x)
    elif isinstance(x, dict):
        for k, v in x.items():
            out.add(k)
            json_strings(v, out)
    elif isinstance(x, list):
        for v in x:
            json_strings(v, out)
    return out


def py_strings(path):
    tree = ast.parse(open(path, encoding='utf-8').read())
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


class Html(html.parser.HTMLParser):
    """the text of each element (its own text nodes, joined and trimmed), the attribute values, and the labels of
    the tabs and their pills"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts, self.tabs, self.stack = set(), [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.texts.update(v for v in a.values() if v)
        cls = (a.get('class') or '').split()
        if tag not in ('br', 'meta', 'link', 'img', 'input', 'hr'):
            self.stack.append([tag, 'tab' in cls or 'pill' in cls, []])

    def handle_endtag(self, tag):
        while self.stack:
            t_, tab, buf = self.stack.pop()
            s = ''.join(buf).strip()
            if s:
                self.texts.add(s)
                if tab and HEB.search(s):
                    self.tabs.append(s)
            if t_ == tag:
                break

    def handle_data(self, data):
        if self.stack:
            self.stack[-1][2].append(data)


def load(name):
    with open(os.path.join(ROOT, 'site', 'data', name), encoding='utf-8') as f:
        return json.load(f)


def vals(d):
    return list((d or {}).values())


def data_t():
    """(file, string) for every string the page puts through t() as its data file loads (i18n.js i18nCore,
    i18nPolls, i18nFinalPolls, i18nArabDay, i18nReplay, i18nTurnoutHistory)"""
    out = []
    core = load('core.json')
    for e in core['elections']:
        out += [('core.json', e.get(k)) for k in ('label', 'short', 'bloc_note')]
    out += [('core.json', f.get('name')) for f in vals(core.get('families'))]
    out += [('core.json', s.get(k)) for s in vals(core.get('sectors')) for k in ('name', 'desc')]
    out += [('core.json', v) for k in ('arab_regions', 'druze_regions') for v in vals(core.get(k))]
    out.append(('polls_2026.json', load('polls_2026.json').get('source')))
    out.append(('final_polls.json', load('final_polls.json').get('source')))
    ad = load('arab_day_2022.json')
    out += [('arab_day_2022.json', v) for k in ('region_names', 'kind_names', 'group_names', 'group_short', 'sub_names')
            for v in vals(ad.get(k))]
    rp = load('replay_night.json')
    out += [('replay_night.json', rp.get(k)) for k in ('note', 'accuracy_note')]
    for R in vals(rp.get('replays')):
        out += [('replay_night.json', R.get(k)) for k in ('label', 'note')]
        out.append(('replay_night.json', (R.get('exit_polls') or {}).get('note')))
        # i18nFrames: 'נספרו 30%' is looked up as 'נספרו {n}%'
        out += [('replay_night.json', re.sub(r'^נספרו (\d+)%$', 'נספרו {n}%', F['label'])) for F in R.get('frames') or []
                if F and F.get('label')]
    out += [('turnout_history.json', e.get('label')) for e in vals(load('turnout_history.json').get('elections'))]
    return [(f, s) for f, s in out if isinstance(s, str) and HEB.search(s)]


def orgs():
    """(file, name) for every pollster, channel and commissioner the page puts through tOrg()"""
    out = []
    for q in load('polls_2026.json')['polls']:
        out += [('polls_2026.json', q.get(k)) for k in ('house_he', 'outlet_he', 'pollster_he')]
    out += [('final_polls.json', q.get('pollster_he')) for e in load('final_polls.json')['elections'] for q in e['polls']]
    for R in vals(load('replay_night.json').get('replays')):
        out += [('replay_night.json', p.get(k)) for p in (R.get('exit_polls') or {}).get('polls') or []
                for k in ('outlet', 'pollster', 'commissioner')]
    return sorted({(f, s) for f, s in out if isinstance(s, str) and HEB.search(s)})


def org_known(s, org):
    """does tOrg() give s an Arabic form: the name itself, or each Hebrew part of 'X (Y)', 'X + Y', 'X / Y'"""
    s = s.strip()
    if s in org or not HEB.search(s):
        return True
    m = re.match(r'^(.+?)\s*\((.+)\)$', s)
    if m:
        return all(org_known(x, org) for x in m.groups())
    parts = re.split(r'\s+[+/]\s+', s)
    return len(parts) > 1 and all(org_known(x, org) for x in parts)


# ---------- the check ----------
def problems(verbose=False):
    out = []
    files = sorted(glob.glob(os.path.join(JS_DIR, '*.js')))
    srcs = {os.path.basename(f): open(f, encoding='utf-8').read() for f in files}
    toks = {f: tokenize(s) for f, s in srcs.items()}
    dicts, spans = read_dicts(srcs['i18n.js'], toks['i18n.js'])
    missing_d = [d for d in DICTS if d not in dicts]
    if missing_d:
        return [f'i18n.js: no dictionary {", ".join(missing_d)}']
    for name, entries in dicts.items():
        seen = {}
        for e in entries:
            if e.key in seen:
                out.append(f'i18n.js:{e.line}: {name} has the key twice (also line {seen[e.key]}): {e.key[:80]}')
            seen.setdefault(e.key, e.line)
    AR = {e.key: e.value for e in dicts['AR']}
    AR_PARTY = {e.key: e.value for e in dicts['AR_PARTY']}
    AR_LEADER = {e.key: e.value for e in dicts['AR_LEADER']}
    AR_ORG = {e.key: e.value for e in dicts['AR_ORG']}

    # 1. the t() literals
    keys, n_calls = {}, 0
    for f, tk in toks.items():
        for j, key, built, names in t_keys(tk, spans if f == 'i18n.js' else ()):
            where = f'{f}:{line_of(srcs[f], tk[j].pos)}'
            if built:
                out.append(f'{where}: a t() key built with +: {key[:80]}')
                continue
            n_calls += 1
            keys.setdefault(key, []).append((where, names))
    for key, calls in keys.items():
        a, where, ph = AR.get(key), calls[0][0], placeholders(key)
        for w, names in calls:
            # a value the Hebrew names and the call does not pass is printed as {name} on the page
            if names is not None and not ph <= names:
                out.append(f'{w}: t() is not given {sorted(ph - names)}: {key[:80]}')
        if a is None:
            out.append(f'{where}: no AR entry for {key[:100]}')
        elif isinstance(a, tuple):
            # an Arabic sentence built by a function may use a value the Hebrew does not show (a raw count)
            for w, names in calls:
                if names is not None and not a[1] <= ph | names:
                    out.append(f'{w}: the AR function uses {sorted(a[1] - ph - names)}, which t() is not given: {key[:80]}')
        else:
            if placeholders(a) != ph:
                out.append(f'{where}: placeholders {sorted(ph)} in the key, {sorted(placeholders(a))} in AR: {key[:80]}')
            if tags(a) != tags(key):
                out.append(f'{where}: tags {tags(key)} in the key, {tags(a)} in AR: {key[:80]}')

    # 2. every key in a Hebrew source
    corpus = set()
    for f, tk in toks.items():
        skip = spans if f == 'i18n.js' else ()
        corpus.update(x.value for j, x in enumerate(tk) if x.kind == 'str' and not any(a <= j <= b for a, b in skip))
    for path in glob.glob(os.path.join(ROOT, 'site', 'data', '*.json')) + glob.glob(os.path.join(ROOT, 'site', 'live', '*.json')):
        if os.path.basename(path) != 'names_ar.json':
            json_strings(json.load(open(path, encoding='utf-8')), corpus)
    for name in FEED_PY:
        corpus |= py_strings(os.path.join(ROOT, 'pipeline', name))
    tpl = open(os.path.join(ROOT, 'site', 'src', 'index.html'), encoding='utf-8').read()
    page = Html()
    page.feed(tpl)
    corpus |= page.texts
    for name, d in (('AR', AR), ('AR_PARTY', AR_PARTY)):
        line = {e.key: e.line for e in dicts[name]}
        for key in d:
            if not key.startswith('__') and key not in corpus:
                out.append(f'i18n.js:{line[key]}: {name} key in no Hebrew source (changed or removed?): {key[:100]}')

    # 3. the page chrome: I18N.chrome's strings are copies of the template's, and the tabs are read from it
    tk = toks['i18n.js']
    at = next((i for i in range(len(tk) - 4) if [x.value for x in tk[i:i + 4]] == ['I18N', '.', 'chrome', '=']), None)
    if at is None:
        out.append('i18n.js: no I18N.chrome')
    else:
        body = next(i for i in range(at, len(tk)) if is_p(tk[i], '{'))
        end = closing(tk, body)
        for j, key, _, _ in t_keys(tk[:end + 1]):
            if j > body and key not in tpl:
                out.append(f'i18n.js:{line_of(srcs["i18n.js"], tk[j].pos)}: I18N.chrome text not in site/src/index.html: {key[:80]}')
    out += [f'index.html: no AR entry for the tab label {s}' for s in page.tabs if s not in AR]

    # 4. the data files' strings that go through t()
    for f, s in sorted(set(data_t())):
        if s not in AR:
            out.append(f'{f}: no AR entry for {s[:100]}')

    # 5. the 2026 leaders, by list id
    parties = load('polls_2026.json')['parties']
    for p in parties:
        a = AR_LEADER.get(p['id'])
        if not a:
            out.append(f"AR_LEADER has no entry for {p['id']} ({p['leader']})")
        elif a[0] != p['leader'].strip():
            out.append(f"AR_LEADER['{p['id']}'] is {a[0]}, the poll data has {p['leader']}: update the Hebrew and the Arabic")
    out += [f'AR_LEADER has {k}, not a 2026 list in polls_2026.json' for k in sorted(set(AR_LEADER) - {p['id'] for p in parties})]
    out += [f"polls_2026.json: no AR_PARTY entry for the list {p['name']}" for p in parties if p['name'] not in AR_PARTY]

    # 6. pollsters and channels
    org_names = orgs()
    out += [f'{f}: no AR_ORG form for {s}' for f, s in org_names if not org_known(s, AR_ORG)]

    if verbose:
        print(f'check_i18n: {len(files)} JS files, {n_calls} t() literals ({len(keys)} keys); AR {len(AR)}, AR_PARTY '
              f'{len(AR_PARTY)}, AR_LEADER {len(AR_LEADER)}, AR_ORG {len(AR_ORG)} entries; {len(data_t())} data strings, '
              f'{len(org_names)} organisation names, {len(page.tabs)} tab labels')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()
    out = problems(a.verbose)
    for line in out:
        print(' ', line)
    print(f'check_i18n: {len(out)} problem(s)')
    return 1 if out else 0


if __name__ == '__main__':
    sys.exit(main())
