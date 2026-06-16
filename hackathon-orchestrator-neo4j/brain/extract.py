"""Concept (entity) extraction — the 'llm-wiki' knowledge layer.

We extract Concept nodes from each chunk so the graph has a semantic spine that
network analytics can run over. Extraction is DETERMINISTIC (structural regex +
curated gazetteers grounded in the corpus) so the benchmark is reproducible and
needs no API key. An LLM extraction pass (GLiNER/Claude) is a drop-in upgrade
that would densify the same Concept/CO_OCCURS layer — see docs/.

Concept kinds: table, column, chart_type, recipe, rule, genie_space,
color_token, country, keyword.
"""
from __future__ import annotations

import re
from collections import Counter

# Closed vocabularies that are genuinely fixed in this corpus -----------------
CHART_TYPES = {
    "line", "bar", "column", "pie", "donut", "area", "scatter", "bubble",
    "choropleth", "heatmap", "sankey", "dumbbell", "slope", "pyramid",
    "forest", "treemap", "waterfall", "histogram", "boxplot", "map",
    "stacked bar", "grouped bar", "small multiples", "bar race",
}
RECIPES = {
    "iceberg", "dumbbell", "bubble_scatter", "kpi_grid", "choropleth",
    "projection", "heatmap_matrix", "pyramid", "forest_ci",
    "sankey_corridors", "bar_race", "slope",
}
# India healthcare-access geography gazetteer (the hub concepts the domain revolves around)
COUNTRIES = {
    "india", "bihar", "kerala", "uttar pradesh", "maharashtra", "rajasthan",
    "tamil nadu", "karnataka", "gujarat", "madhya pradesh", "west bengal",
    "odisha", "assam", "jharkhand", "araria", "ladakh",
}
DOMAIN_KEYWORDS = {
    "facility", "facilities", "health facility", "hospital", "clinic",
    "medical desert", "zero-facility district", "access gap", "coverage",
    "district", "pincode", "postal code", "nfhs", "health burden index",
    "hbi", "anaemia", "maternal", "specialty", "self-reported",
    "urbanisation", "rural", "haversine", "nearest facility", "risk index",
    "suppression", "per-capita", "sample",
}
# Design-system vocabulary
DESIGN_KEYWORDS = {
    "palette", "typography", "colour", "color", "editorial", "annotation",
    "chart selection", "accessibility", "contrast", "qualitative palette",
    "sequential palette", "diverging palette", "gridlines", "legend",
}

_BACKTICK = re.compile(r"`([^`]+)`")
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
_RULE = re.compile(r"\bR\d{1,2}\b")
_IDENT = re.compile(r"^[a-z][a-z0-9]+(?:_[a-z0-9]+)+$")          # snake_case table/column
_GENIE = re.compile(r"\b[0-9a-f]{6,}[0-9a-f.]{6,}\b")            # long hex genie-space id
_WORD = re.compile(r"[a-zA-Z][a-zA-Z\-]+")

# Hand-tuned snake_case identifiers known to be TABLES (vs columns) in the corpus
KNOWN_TABLES = {
    "facilities", "india_post_pincode_directory",
    "nfhs_5_district_health_indicators", "sql_patterns",
    "business_context",
}

_STOP = set("""a an the of to in on for and or is are be with by from as at this that these those it its into per
each any all not no than then so such we you they our your their he she his her them us i me my mine ours
how what when where which who whom why use used using read reads always never only also more most least very
should must may can will would could do does did done has have had can't don't see note rule rules section
file files folder skill skills domain domains question questions answer user agent data chart charts column
columns table tables value values row rows null string double cast trim group order limit select where via
e.g i.e etc vs split route routes routing load loads first deeper full set sets list lists left right top""".split())


def _canon(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def extract_from_text(text: str, *, doc_kind: str = "") -> list[tuple[str, str]]:
    """Return a list of (concept_name, kind) found in this chunk's text."""
    found: dict[str, str] = {}
    low = text.lower()

    def add(name: str, kind: str):
        name = _canon(name)
        if not name or len(name) < 2:
            return
        # don't overwrite a more specific kind with 'keyword'
        if name in found and kind == "keyword":
            return
        found[name] = kind

    # Structural: backticked identifiers -> tables / columns / patterns
    for raw in _BACKTICK.findall(text):
        tok = raw.strip()
        if _GENIE.search(tok):
            add(tok, "genie_space")
        elif tok.lower() in KNOWN_TABLES:
            add(tok.lower(), "table")
        elif _IDENT.match(tok.lower()):
            add(tok.lower(), "column")
        elif _HEX.fullmatch(tok):
            add(tok.lower(), "color_token")

    for hx in _HEX.findall(text):
        add(hx.lower(), "color_token")
    for genie in _GENIE.findall(text):
        if len(genie) >= 16:
            add(genie.lower(), "genie_space")
    for rule in _RULE.findall(text):
        add(rule.upper().lower(), "rule")

    # Gazetteer matches (whole-word-ish, longest first to prefer phrases)
    for term in sorted(DOMAIN_KEYWORDS, key=len, reverse=True):
        if term in low:
            add(term, "keyword")
    for term in sorted(DESIGN_KEYWORDS, key=len, reverse=True):
        if term in low:
            add(term, "keyword")
    for term in sorted(COUNTRIES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(term)}\b", low):
            add(term, "country")
    for term in sorted(CHART_TYPES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(term)}\b", low):
            add(term, "chart_type")
    for term in RECIPES:
        if re.search(rf"\b{re.escape(term)}\b", low):
            add(term, "recipe")

    return list(found.items())


def corpus_keyphrases(chunk_texts: list[str], min_df: int = 2, top: int = 60) -> set[str]:
    """Frequency-based bigram/trigram keyphrases that recur across >= min_df chunks.

    Adds emergent domain phrases (e.g. 'access gap', 'health burden index')
    that aren't in the hand gazetteer, mirroring how the wiki surfaces salient
    terms. Returned phrases are merged into DOMAIN_KEYWORDS at ingest time.
    """
    df: Counter = Counter()
    for txt in chunk_texts:
        words = [w.lower() for w in _WORD.findall(txt)]
        words = [w for w in words if w not in _STOP and len(w) > 2]
        seen = set()
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                gram = " ".join(words[i:i + n])
                if any(g in _STOP for g in gram.split()):
                    continue
                if gram not in seen:
                    seen.add(gram)
                    df[gram] += 1
    phrases = {g for g, c in df.most_common(top * 3) if c >= min_df}
    # keep the most informative (longer, recurrent) ones
    ranked = sorted(phrases, key=lambda g: (df[g], len(g)), reverse=True)
    return set(ranked[:top])
