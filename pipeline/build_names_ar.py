#!/usr/bin/env python3
"""Arabic locality names for the Arabic version of the page: site/data/names_ar.json (CBS locality code -> name).

    python3 pipeline/build_names_ar.py [--cache DIR] [--report FILE]

There is no single official Arabic list keyed by CBS code that the build can reach (the CBS locality file has Hebrew
and English names only), so four public lists are combined, each pinned to a commit:
  open-budgets  os-data/israel administrative-structure/entities.csv: municipalities (cities and local councils) by
                CBS code, with Arabic names (Hasadna's Open Budget project)
  gazetteer     FadiBadarni/israel-homicides data/gazetteer.json: Arab localities, Hebrew name + aliases -> Arabic
  oref          eladnava/pikud-haoref-api cities.json: the Home Front Command's alert areas, Hebrew -> Arabic
  cbs-list      GuyStep/IsraelCities IsraelCities.csv: CBS code -> Arabic; some rows are shifted against the codes,
                so a name from it is used only when it agrees with another list or spells the Hebrew name
Every candidate must spell the Hebrew name (a consonant-skeleton comparison, see consistent()), which drops shifted
rows and alert-area names of another place. Then a name more lists agree on beats a name fewer lists have, and ties go
to the list that comes first in ORDER (per sector). OVERRIDES below settles the localities the lists disagree on (each
row names the source whose spelling it keeps and why). A locality none of the lists names keeps its Hebrew name on
the page. Standard library only; the downloads are cached under --cache (default: a folder in the system temp dir).
"""
import argparse, csv, difflib, io, json, os, re, sys, tempfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = {
    'open-budgets': 'https://raw.githubusercontent.com/os-data/israel/3b214ba3ba57a465d044a4c71dd71d27cc8cfaff/archive/administrative-structure/entities.csv',
    'gazetteer': 'https://raw.githubusercontent.com/FadiBadarni/israel-homicides/6aca6776f531279e507025dee2a72da583b8572d/data/gazetteer.json',
    'oref': 'https://raw.githubusercontent.com/eladnava/pikud-haoref-api/e40da77a4aab3052fb1a4a56402ae2e26c3e3cf3/cities.json',
    'cbs-list': 'https://raw.githubusercontent.com/GuyStep/IsraelCities/be876a4277ddb4db6e65d38a27a69207e08aac72/IsraelCities.csv',
}
# whose spelling wins: for the Arab and Druze localities the gazetteer (written for the Arab society) first, for the
# others the municipal list; the Home Front Command list next and the shifted CBS-code list last
ORDER = {'arab': ['gazetteer', 'open-budgets', 'oref', 'cbs-list'], 'druze': ['gazetteer', 'open-budgets', 'oref', 'cbs-list'],
         'mixed': ['open-budgets', 'gazetteer', 'oref', 'cbs-list'], 'jewish': ['open-budgets', 'oref', 'gazetteer', 'cbs-list']}
# code -> (name, the list(s) whose spelling it is, why). Read against the --report table: the lists disagree on these,
# or the consistency check drops the right name (a CBS-list row that sits one row off, an Arabic name that is not a
# transliteration of the Hebrew one).
OVERRIDES = {
    482: ('البعينة-نجيدات', 'open-budgets+oref', 'open-budgets has البعينة only, oref البعنة النجيدات (البعنة is another village)'),
    497: ('الطيبة الزعبية', 'cbs-list', 'the valley Taibe, told apart from Tayibe in the Triangle (2730)'),
    499: ('يافة الناصرة', 'gazetteer+oref+cbs-list', 'three lists agree; open-budgets transliterates the Hebrew (يفيع)'),
    514: ('عين رافة', 'cbs-list', 'the usual spelling (oref: عين رافا)'),
    523: ('نين', 'cbs-list', 'the CBS-list rows of 523 and 3655 are swapped'),
    3655: ('نيلي', 'cbs-list', 'the CBS-list rows of 523 and 3655 are swapped'),
    524: ('الناعورة', 'cbs-list', 'with the article, as the village is called (oref: ناعورة)'),
    530: ('عيلبون', 'cbs-list', 'the usual spelling (open-budgets: علابون)'),
    540: ('الريحانية', 'cbs-list', 'with the article and taa marbuta (oref: ريحانيه)'),
    547: ('طمرة الزعبية', 'cbs-list', 'Tamra in the valley, told apart from the city of Tamra (8900)'),
    913: ('الشبلي-أم الغنم', 'cbs-list', 'the usual spelling (open-budgets: شبلي-اوم الغنم)'),
    942: ('سواعد (حميرة)', 'cbs-list', 'keeps the qualifier the CBS name has'),
    978: ('كعبية-طباش-حجاجرة', 'cbs-list', 'the usual spelling (open-budgets: كعبيا)'),
    1063: ('معلوت-ترشيحا', 'cbs-list+oref', 'the joint town, not Tarshiha alone'),
    1105: ('بوريا (نفي عوفيد)', 'cbs-list', 'the check compares the Arabic name without its brackets, so it drops this one'),
    1192: ('عرعرة النقب', 'gazetteer+oref+cbs-list', 'three lists agree'),
    1320: ('عين حوض', 'cbs-list', 'the village\'s Arabic name (oref: عين حود)'),
    1327: ('طلعة عارة', 'cbs-list', 'the council\'s Arabic name (Hebrew: מעלה עירון)'),
    3000: ('القدس', 'open-budgets+gazetteer', 'the Arabic name; it does not spell the Hebrew ירושלים, so the check drops it'),
    3400: ('الخليل', 'cbs-list', 'the Arabic name of the city'),
    5000: ('تل أبيب-يافا', 'cbs-list', 'the city\'s full name (open-budgets, gazetteer: تل أبيب)'),
}
OUT = os.path.join(ROOT, 'site', 'data', 'names_ar.json')


def fetch(name, cache):
    path = os.path.join(cache, name + os.path.splitext(SOURCES[name])[1])
    if not os.path.exists(path):
        with urllib.request.urlopen(SOURCES[name], timeout=60) as r:
            data = r.read()
        with open(path, 'wb') as f:
            f.write(data)
    with open(path, 'rb') as f:
        return f.read().decode('utf-8-sig')


# ---------- comparing a Hebrew and an Arabic spelling ----------
# Both spellings are reduced to their strong consonants in broad classes (weak letters and vowels dropped; the
# letters a transliteration swaps, such as ב/פ ~ ب/ف or כ/ק/ח ~ ك/ق/ح/خ, in one class), so the check tells a name of
# the same place from the name of another place, not one spelling from another.
HE_FINAL = str.maketrans('ךםןףץ', 'כמנפצ')
HE_CLASS = {'ב': 'B', 'פ': 'B', 'כ': 'K', 'ק': 'K', 'ח': 'K', 'ג': 'G', 'ת': 'T', 'ט': 'T', 'ד': 'D', 'ס': 'S', 'ש': 'S',
            'צ': 'S', 'ז': 'S', 'ל': 'L', 'מ': 'M', 'נ': 'N', 'ר': 'R'}
AR_CLASS = {'ب': 'B', 'ف': 'B', 'پ': 'B', 'ڤ': 'B', 'ك': 'K', 'ق': 'K', 'ح': 'K', 'خ': 'K', 'ج': 'G', 'چ': 'G', 'غ': 'G',
            'ت': 'T', 'ط': 'T', 'ث': 'T', 'ظ': 'T', 'د': 'D', 'ذ': 'D', 'ض': 'D', 'س': 'S', 'ش': 'S', 'ص': 'S', 'ز': 'S',
            'ژ': 'S', 'ل': 'L', 'م': 'M', 'ن': 'N', 'ر': 'R'}


def he_skel(s):
    s = re.sub(r'\([^)]*\)', ' ', s).translate(HE_FINAL)
    s = re.sub(r"[׳'`’]", '', s)
    s = re.sub(r'(^|[\s\-־])(אל|א)[\s\-־]', r'\1', s)          # the Arabic article written in Hebrew
    return ''.join(HE_CLASS.get(c, '') for c in s)


def ar_skel(s):
    s = re.sub(r'\([^)]*\)', ' ', s)
    s = re.sub(r'[\u064B-\u0652\u0670\u0640]', '', s)
    s = re.sub(r'(^|[\s\-–])ال', r'\1', s).replace('تس', 'ص')
    return ''.join(AR_CLASS.get(c, '') for c in s)


def consistent(he, ar):
    """does the Arabic name spell the Hebrew one? (weak letters dropped on both sides, so vowels do not count)"""
    x, y = he_skel(he), ar_skel(ar)
    if not x or not y:
        return False
    return x == y or difflib.SequenceMatcher(None, x, y).ratio() >= 0.6


def norm_ar(s):
    """for 'two lists give the same name': spelling variants of one name compare equal"""
    s = re.sub(r'[ً-ْٰـ]', '', s)
    s = re.sub('[أإآٱ]', 'ا', s).replace('ة', 'ه').replace('ى', 'ي')
    return re.sub(r'[\s\-–_]+', '', s)


def norm_he(s):
    s = re.sub(r"[׳'`’]", "'", s).replace('״', '"')
    return re.sub(r'[\s\-־]+', ' ', s).strip()


def clean_ar(s):
    """the name as the page writes it: no diacritics, the common letters for the transliteration ones (ڤ پ چ), one
    spelling of the hyphen"""
    s = re.sub(r'[\u064B-\u0652\u0670\u0640]', '', s).translate(str.maketrans('ڤپچژ', 'فبجز'))
    s = re.sub(r'\s+', ' ', s.replace('–', '-')).strip(' -')
    return re.sub(r'\s*-\s*', '-', s) if re.search(r'\S-\s|\s-\S', s) else s


# the Hebrew qualifier of a CBS name that two localities share ('אבו קורינאת (שבט)' and '(יישוב)')
QUALIFIER = {'(שבט)': ' (عشيرة)', '(יישוב)': ' (بلدة)'}


def load_sources(cache):
    by_code, by_name = {}, {}       # source -> {code: ar} / {normalized Hebrew: ar}
    rows = csv.DictReader(io.StringIO(fetch('open-budgets', cache)))
    by_code['open-budgets'] = {int(r['CODE']): r['NAME_AR'].strip() for r in rows
                               if r['DIVISION'] in ('עירייה', 'מועצה מקומית') and r['CODE'].strip().isdigit() and r['NAME_AR'].strip()}
    gz = json.loads(fetch('gazetteer', cache))
    g = {}
    for e in gz:
        if not e.get('name_ar') or not e.get('name_he'):
            continue
        for he in [e['name_he']] + list(e.get('aliases_he') or []):
            g.setdefault(norm_he(he), e['name_ar'].strip())
    by_name['gazetteer'] = g
    o = {}
    for e in json.loads(fetch('oref', cache)):
        if e.get('name_ar') and e.get('name') and e.get('id'):
            o.setdefault(norm_he(e['name']), e['name_ar'].strip())
    by_name['oref'] = o
    rows = csv.DictReader(io.StringIO(fetch('cbs-list', cache)))
    by_code['cbs-list'] = {int(r['symbol_number']): r['name_in_arabic'].strip() for r in rows
                           if r['symbol_number'].strip().isdigit() and r['name_in_arabic'].strip()}
    return by_code, by_name


def candidates(code, he, by_code, by_name, order):
    out = []
    for src in order:
        if src in by_code:
            v = by_code[src].get(code)
        else:
            v = by_name[src].get(norm_he(he)) or by_name[src].get(norm_he(re.sub(r'\s*\([^)]*\)\s*|\*', '', he)))
        if v:
            out.append((src, clean_ar(v)))
    return out


def spelled_anywhere(he, index):
    """a name from any row of the CBS-code list or the alert-area list whose consonants are exactly the Hebrew name's
    (recovers a CBS-list name that sits on a neighbouring row); used only when it is the one such name"""
    k = he_skel(he)
    if len(k) < 3:
        return None
    hits = {norm_ar(v): v for v in index.get(k, [])}
    return next(iter(hits.values())) if len(hits) == 1 else None


def orth(v):
    """prefer the fuller orthography of one name: the taa marbuta and the hamza forms ('رأس' over 'راس')"""
    return v.count('ة') + sum(v.count(c) for c in 'أإآئؤ')


def choose(he, cands, order):
    ok = [(s, v) for s, v in cands if consistent(he, v)]
    if not ok:
        return None, None, 'no consistent name'
    groups = {}
    for s, v in ok:
        groups.setdefault(norm_ar(v), []).append((s, v))
    # the name most lists give, ties to the list that comes first; within it the fuller spelling, then the order
    best = max(groups.values(), key=lambda g: (len(g), -min(order.index(s) for s, _ in g)))
    s, v = max(best, key=lambda sv: (orth(sv[1]), -order.index(sv[0])))
    note = '' if len(groups) == 1 else 'lists disagree'
    return v, '+'.join(sorted({x for x, _ in best}, key=order.index)), note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default=os.path.join(tempfile.gettempdir(), 'kalpi26_names_ar'))
    ap.add_argument('--report', help='write a TSV of every locality and its candidates')
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    by_code, by_name = load_sources(a.cache)
    core = json.load(open(os.path.join(ROOT, 'site', 'data', 'core.json'), encoding='utf-8'))
    index = {}
    for v in list(by_code['cbs-list'].values()) + list(by_name['oref'].values()):
        index.setdefault(ar_skel(clean_ar(v)), []).append(clean_ar(v))
    names, src_of, report, counts = {}, {}, [], {}
    for l in core['localities']:
        code, he, order = l['code'], l['name'], ORDER[l['sector']]
        cands = candidates(code, he, by_code, by_name, order)
        v, s, note = choose(he, cands, order)
        if not v:
            w = spelled_anywhere(he, index)
            if w:
                v, s, note = w, 'spelling-match', 'matched by spelling in cbs-list/oref'
        if code in OVERRIDES:
            v, s, note = OVERRIDES[code][0], 'override:' + OVERRIDES[code][1], OVERRIDES[code][2]
        for q, w in QUALIFIER.items():
            if v and q in he and '(' not in v:
                v += w
        if v:
            names[str(code)] = v
            src_of[str(code)] = s
        counts[(l['sector'], bool(v))] = counts.get((l['sector'], bool(v)), 0) + 1
        report.append([str(code), he, l['sector'], v or '', s or '', note] + [f'{x}={y}' for x, y in cands])
    if a.report:
        with open(a.report, 'w', encoding='utf-8', newline='') as f:
            csv.writer(f, delimiter='\t').writerows(report)
    doc = {
        'generated': 'pipeline/build_names_ar.py',
        'note': 'Arabic locality names by CBS locality code, combined from four public lists (see sources); a locality '
                'missing here keeps its Hebrew name on the page.',
        'sources': SOURCES,
        'overrides': 'OVERRIDES in pipeline/build_names_ar.py (source_of marks them "override:<list>")',
        'localities': dict(sorted(names.items(), key=lambda kv: int(kv[0]))),
        'source_of': dict(sorted(src_of.items(), key=lambda kv: int(kv[0]))),
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    tot = {sec: (counts.get((sec, True), 0), counts.get((sec, True), 0) + counts.get((sec, False), 0)) for sec in ('arab', 'druze', 'mixed', 'jewish')}
    print('names_ar.json:', len(names), 'of', len(core['localities']), 'localities;',
          ', '.join(f'{k} {v[0]}/{v[1]}' for k, v in tot.items()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
