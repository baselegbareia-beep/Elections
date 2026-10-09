"""Party, bloc and sector registry for K21–K25.

Everything here is reviewed reference data, kept separate from the vote tables:
- ballot letters (אותיות) are election-specific and never reused as stable IDs;
- a "family" links lists across elections for trend lines;
- the historical bloc is defined by a verifiable fact: whether the list
  recommended Netanyahu to the President after that election.
"""

ELECTIONS = {
    "K21": {"n": 21, "date": "2019-04-09", "label": "הכנסת ה-21", "short": "אפר׳ 2019",
            "official_url": "https://votes21.bechirot.gov.il/"},
    "K22": {"n": 22, "date": "2019-09-17", "label": "הכנסת ה-22", "short": "ספט׳ 2019",
            "official_url": "https://votes22.bechirot.gov.il/"},
    "K23": {"n": 23, "date": "2020-03-02", "label": "הכנסת ה-23", "short": "מרץ 2020",
            "official_url": "https://votes23.bechirot.gov.il/"},
    "K24": {"n": 24, "date": "2021-03-23", "label": "הכנסת ה-24", "short": "מרץ 2021",
            "official_url": "https://votes24.bechirot.gov.il/"},
    "K25": {"n": 25, "date": "2022-11-01", "label": "הכנסת ה-25", "short": "נוב׳ 2022",
            "official_url": "https://votes25.bechirot.gov.il/"},
}

# Where the national results page reports a different register total than the
# sum of the ballot-box rows, the national figure is shown as the headline.
# K22: national page 6,394,030 vs 6,391,218 summed from the boxes (69.83% vs 69.86%).
OFFICIAL_ELIGIBLE = {"K22": 6394030}

THRESHOLD = 0.0325
SEATS = 120

# Party families: one colour and one short name per political lineage.
FAMILIES = {
    "likud":   {"name": "הליכוד", "color": "#1d4ed8", "dark": "#5b8cff"},
    "bw":      {"name": "כחול לבן / המחנה הממלכתי", "color": "#4f46e5", "dark": "#8b85ff"},
    "yesh":    {"name": "יש עתיד", "color": "#0891b2", "dark": "#38bdf8"},
    "shas":    {"name": "ש״ס", "color": "#3f3f46", "dark": "#c4c4cc"},
    "utj":     {"name": "יהדות התורה", "color": "#0f172a", "dark": "#e2e8f0"},
    "rz":      {"name": "הציונות הדתית / ימינה", "color": "#b45309", "dark": "#f59e0b"},
    "otzma":   {"name": "עוצמה יהודית", "color": "#ca8a04", "dark": "#facc15"},
    "newright":{"name": "הימין החדש / ימינה", "color": "#0e7490", "dark": "#22d3ee"},
    "yb":      {"name": "ישראל ביתנו", "color": "#7c3aed", "dark": "#a78bfa"},
    "labor":   {"name": "העבודה", "color": "#dc2626", "dark": "#f87171"},
    "meretz":  {"name": "מרצ", "color": "#16a34a", "dark": "#4ade80"},
    "ra'am":   {"name": "רע״ם", "color": "#4d7c0f", "dark": "#a3e635"},
    "hadash":  {"name": "חד״ש-תע״ל", "color": "#be123c", "dark": "#fb7185"},
    "balad":   {"name": "בל״ד", "color": "#9333ea", "dark": "#d8b4fe"},
    "joint":   {"name": "הרשימה המשותפת", "color": "#047857", "dark": "#34d399"},
    "kulanu":  {"name": "כולנו", "color": "#0284c7", "dark": "#7dd3fc"},
    "newhope": {"name": "תקווה חדשה", "color": "#1e40af", "dark": "#93c5fd"},
    "gesher":  {"name": "גשר", "color": "#db2777", "dark": "#f9a8d4"},
    "zehut":   {"name": "זהות", "color": "#a16207", "dark": "#fcd34d"},
    "jhome":   {"name": "הבית היהודי", "color": "#92400e", "dark": "#fdba74"},
    "other":   {"name": "אחרות", "color": "#94a3b8", "dark": "#64748b"},
}

# bloc: "nb" = recommended Netanyahu after the election, "arab" = Arab-led list,
# "opp" = other seat-winning lists, "out" = Jewish-led lists that missed the threshold.
PARTIES = {
    "K21": {
        "מחל": ("הליכוד", "likud", "nb"), "פה": ("כחול לבן", "bw", "opp"), "שס": ("ש״ס", "shas", "nb"),
        "ג": ("יהדות התורה", "utj", "nb"), "ום": ("חד״ש-תע״ל", "hadash", "arab"), "אמת": ("העבודה", "labor", "opp"),
        "ל": ("ישראל ביתנו", "yb", "nb"), "טב": ("איחוד מפלגות הימין", "rz", "nb"), "מרצ": ("מרצ", "meretz", "opp"),
        "כ": ("כולנו", "kulanu", "nb"), "דעם": ("רע״ם-בל״ד", "ra'am", "arab"), "נ": ("הימין החדש", "newright", "out"),
        "ז": ("זהות", "zehut", "out"), "נר": ("גשר", "gesher", "out"),
    },
    "K22": {
        "פה": ("כחול לבן", "bw", "opp"), "מחל": ("הליכוד", "likud", "nb"), "ודעם": ("הרשימה המשותפת", "joint", "arab"),
        "שס": ("ש״ס", "shas", "nb"), "ל": ("ישראל ביתנו", "yb", "opp"), "ג": ("יהדות התורה", "utj", "nb"),
        "טב": ("ימינה", "rz", "nb"), "אמת": ("העבודה-גשר", "labor", "opp"), "מרצ": ("המחנה הדמוקרטי", "meretz", "opp"),
        "כף": ("עוצמה יהודית", "otzma", "out"),
    },
    "K23": {
        "מחל": ("הליכוד", "likud", "nb"), "פה": ("כחול לבן", "bw", "opp"), "ודעם": ("הרשימה המשותפת", "joint", "arab"),
        "שס": ("ש״ס", "shas", "nb"), "ג": ("יהדות התורה", "utj", "nb"), "אמת": ("העבודה-גשר-מרצ", "labor", "opp"),
        "ל": ("ישראל ביתנו", "yb", "opp"), "טב": ("ימינה", "rz", "nb"),
    },
    "K24": {
        "מחל": ("הליכוד", "likud", "nb"), "פה": ("יש עתיד", "yesh", "opp"), "שס": ("ש״ס", "shas", "nb"),
        "כן": ("כחול לבן", "bw", "opp"), "ב": ("ימינה", "newright", "opp"), "אמת": ("העבודה", "labor", "opp"),
        "ג": ("יהדות התורה", "utj", "nb"), "ל": ("ישראל ביתנו", "yb", "opp"), "ט": ("הציונות הדתית", "rz", "nb"),
        "ודעם": ("הרשימה המשותפת", "joint", "arab"), "ת": ("תקווה חדשה", "newhope", "opp"), "מרצ": ("מרצ", "meretz", "opp"),
        "עם": ("רע״ם", "ra'am", "arab"),
    },
    "K25": {
        "מחל": ("הליכוד", "likud", "nb"), "פה": ("יש עתיד", "yesh", "opp"), "ט": ("הציונות הדתית", "rz", "nb"),
        "כן": ("המחנה הממלכתי", "bw", "opp"), "שס": ("ש״ס", "shas", "nb"), "ג": ("יהדות התורה", "utj", "nb"),
        "ל": ("ישראל ביתנו", "yb", "opp"), "עם": ("רע״ם", "ra'am", "arab"), "ום": ("חד״ש-תע״ל", "hadash", "arab"),
        "אמת": ("העבודה", "labor", "opp"), "מרצ": ("מרצ", "meretz", "out"), "ד": ("בל״ד", "balad", "arab"),
        "ב": ("הבית היהודי", "jhome", "out"),
    },
}

# Predecessors of each list in the previous election, for the seat-change column:
# a list of letters (merger when longer than one), "new", or "split".
PRED = {
    "K22": {"פה": ["פה"], "מחל": ["מחל", "כ"], "ודעם": ["ום", "דעם"], "שס": ["שס"], "ל": ["ל"], "ג": ["ג"],
            "טב": ["טב", "נ"], "אמת": ["אמת", "נר"], "מרצ": ["מרצ"], "כף": "new"},
    "K23": {"מחל": ["מחל"], "פה": ["פה"], "ודעם": ["ודעם"], "שס": ["שס"], "ג": ["ג"], "אמת": ["אמת", "מרצ"],
            "ל": ["ל"], "טב": ["טב"]},
    "K24": {"מחל": ["מחל"], "פה": "split", "כן": "split", "שס": ["שס"], "ב": "split", "ט": "split",
            "אמת": "split", "מרצ": "split", "ג": ["ג"], "ל": ["ל"], "ודעם": "split", "עם": "split", "ת": "new"},
    "K25": {"מחל": ["מחל"], "פה": ["פה"], "ט": ["ט"], "כן": ["כן", "ת"], "שס": ["שס"], "ג": ["ג"], "ל": ["ל"],
            "עם": ["עם"], "ום": "split", "ד": "split", "אמת": ["אמת"], "מרצ": ["מרצ"], "ב": "split"},
}

# Lists that recommended Netanyahu (nb) per election — for the bloc note in the UI.
BLOC_NOTE = {
    "K21": "65 ח״כים המליצו על נתניהו (כולל ישראל ביתנו).",
    "K22": "55 ח״כים המליצו על נתניהו; ישראל ביתנו לא המליצה על איש.",
    "K23": "58 ח״כים המליצו על נתניהו.",
    "K24": "52 ח״כים המליצו על נתניהו; ימינה המליצה על בנט, רע״ם לא המליצה.",
    "K25": "64 ח״כים המליצו על נתניהו.",
}

# Lists counted as "Arab-led lists" when classifying ballots by vote composition.
ARAB_LISTS = {e: [l for l, p in ps.items() if p[2] == "arab"] for e, ps in PARTIES.items()}

# --- Sector classification -------------------------------------------------
# Arab and Druze localities come from pipeline/reference/arab_localities.csv
# (CBS locality code -> segment). The list was built by rule: every locality
# where the Joint List won >= 50% in K23 (its peak-unity election), plus the
# Druze-majority villages, the Golan Druze villages, Ghajar and the Circassian
# villages, minus the 8 mixed cities and Neve Shalom. Over K21-K25 it
# reproduces the Arab-turnout figures published by the Israel Democracy
# Institute (49.2 / 59.2 / 64.8 / 44.6 / 53.2). In production it is replaced
# by the CBS locality file's population-group field (see docs/DATA_SOURCES.md).
SEGMENTS = {
    # segment: (sector, sub-sector key)
    "NEGEV_BEDOUIN": ("arab", "negev"),
    "NORTH_BEDOUIN": ("arab", "north_bedouin"),
    "TRIANGLE_NORTH_WADI_ARA": ("arab", "wadi_ara"),
    "TRIANGLE_SOUTH": ("arab", "triangle_south"),
    "NAZARETH": ("arab", "nazareth"),
    "GALILEE_HAIFA_OTHER_ARAB": ("arab", "galilee"),
    "CHRISTIAN_MAJORITY_OR_PLURALITY": ("arab", "christian"),
    "MIXED_DRUZE_MUSLIM_CHRISTIAN_TOWN": ("arab", "mixed_town"),
    "JERUSALEM_AREA_ARAB": ("arab", "jerusalem"),
    "DRUZE_GALILEE_CARMEL": ("druze", "druze"),
    "DRUZE_GOLAN": ("druze", "golan"),
    "ALAWITE_GHAJAR": ("druze", "ghajar"),
    "CIRCASSIAN_EXCLUDED": ("druze", "circassian"),
    "MIXED_CITY": ("mixed", None),
    "MIXED_SMALL_COMMUNITY_EXCLUDED": ("mixed", None),
}
# Segments that make up the standard "Arab and Druze localities" aggregate.
STANDARD_SEGMENTS = {k for k, v in SEGMENTS.items() if v[0] in ("arab", "druze") and k != "CIRCASSIAN_EXCLUDED"}

MIXED_NAMES = {
    4000: "חיפה", 5000: "תל אביב-יפו", 7000: "לוד", 8500: "רמלה", 7600: "עכו",
    1063: "מעלות-תרשיחא", 1061: "נוף הגליל", 3000: "ירושלים", 1259: "נווה שלום",
}

ARAB_FALLBACK_MIN_SHARE = 0.50   # an unlisted locality with this mean Arab-list share is flagged and treated as Arab
ARAB_BOX_MIN_SHARE = 0.50        # box-level rule inside mixed cities and Jewish localities
HAREDI_BOX_MIN_SHARE = 0.70      # (UTJ + Shas) share for a "Haredi box"; vote-derived, labelled as such

SECTORS = {
    "arab":   {"name": "ערבים", "desc": "יישובים ערביים (כולל בדואים) וקלפיות ערביות בערים מעורבות"},
    "druze":  {"name": "דרוזים וצ׳רקסים", "desc": "יישובים דרוזיים בגליל, בכרמל ובגולן, ע׳ג׳ר, כפר כמא וריחאנייה"},
    "jewish": {"name": "יהודים ואחרים", "desc": "יתר הקלפיות, כולל מעטפות כפולות (חיילים, נציגויות ועוד)"},
}
ARAB_REGIONS = {
    "negev": "בדואים בנגב",
    "north_bedouin": "בדואים בצפון",
    "wadi_ara": "ואדי עארה",
    "triangle_south": "המשולש הדרומי",
    "nazareth": "נצרת",
    "galilee": "גליל, עמקים וחיפה",
    "christian": "כפרים ברוב נוצרי",
    "mixed_town": "שפרעם, מע׳אר, אבו סנאן",
    "jerusalem": "אזור ירושלים",
    "mixed": "קלפיות ערביות בערים מעורבות",
}
DRUZE_REGIONS = {
    "druze": "דרוזים בגליל ובכרמל",
    "golan": "דרוזים ברמת הגולן",
    "ghajar": "ע׳ג׳ר",
    "circassian": "צ׳רקסים",
}
