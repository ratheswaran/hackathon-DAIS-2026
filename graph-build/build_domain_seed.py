"""Build the India-healthcare (Medical Desert Planner) DOMAIN seed for the
find_skill knowledge graph — {nodes, edges} in the schema seed_load.py consumes.

Layered like the prior domain it replaces:
  data-semantics : Domain / GenieSpace / Table / Column   (STATIC — from dataset-schema.md)
  capability-link: Metric / Rule / SqlPattern             (from verified EDA)
  why / insight  : Finding / Question                     (from verified EDA + story spine)

Cross-layer edges wire domain -> KEPT skill nodes by their exact canonical names
(choropleth / bubble_scatter / dumbbell / ranked_bar / heatmap_matrix / forest_ci /
lorenz_gini / stat / kpi_grid ChartRecipes; compose_infographic / compose_story /
compose_deck / render_chart Tools).

Run: python build_domain_seed.py  ->  domain_seed.json
"""
from __future__ import annotations
import json, re
from pathlib import Path

CAT = "databricks_virtue_foundation_dataset_dais_2026"
SCH = "virtue_foundation_dataset"
def fqn(t): return f"{CAT}.{SCH}.{t}"
T_FAC = fqn("facilities")
T_NFHS = fqn("nfhs_5_district_health_indicators")
T_PIN = fqn("india_post_pincode_directory")

GENIE = "India Healthcare Access Space"
DOMAIN = "india-healthcare-access"

NODES: list[dict] = []
EDGES: list[dict] = []
_seen = set()

def N(ntype, name, content, **props):
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    key = f"{ntype}:{slug}"
    if key in _seen:
        return name
    _seen.add(key)
    NODES.append({"type": ntype, "name": name, "content": content.strip(),
                  "props": {k: str(v) for k, v in props.items() if v not in (None, "")}})
    return name

def E(etype, ft, fn, tt, tn, **props):
    EDGES.append({"type": etype, "from_type": ft, "from_name": fn,
                  "to_type": tt, "to_name": tn,
                  "props": {k: str(v) for k, v in props.items() if v not in (None, "")}})

# ============================================================ DATA-SEMANTICS (STATIC)
N("Domain", DOMAIN,
  "India healthcare ACCESS domain (DAIS-for-Good 2026, Virtue Foundation). The 'Medical Desert "
  "Planner': join SUPPLY (10k geocoded facilities) against DEMAND (NFHS-5 district health burden) "
  "through the India Post PIN crosswalk to find where the highest-risk gaps in care are. One Genie "
  "space backs all three tables. Honesty contract: the facility table is a ~10k SAMPLE, never a "
  "census — facility counts are dataset COVERAGE, not absolute supply; cite the source text for any "
  "facility claim; communicate uncertainty.",
  summary="India healthcare access — supply (facilities) x demand (NFHS-5 burden) x geo (PIN) to map medical deserts.")

N("GenieSpace", GENIE,
  f"Genie space over the three Virtue Foundation tables. Ask natural-language questions; it writes "
  f"Spark SQL over `{CAT}`.`{SCH}`.*. Tables: facilities (supply), nfhs_5_district_health_indicators "
  f"(demand burden), india_post_pincode_directory (PIN->district->state crosswalk). Use for ANY "
  f"question about facility supply, district health burden, or access gaps / medical deserts that "
  f"join across them. The facility<->district bridge is facilities.address_zipOrPostcode (a 6-digit "
  f"PIN) -> pincode dir (modal district per pincode) -> NFHS district_name.",
  space_id="REPLACE_WITH_SPACE_ID_ON_EVENT_DAY",
  when_to_use="India healthcare: facility supply/composition/trust, NFHS-5 district health burden, PIN geography, and medical-desert (supply x demand) joins.",
  summary="One Genie space over facilities + NFHS-5 + PIN directory.")
E("SERVED_BY", "Domain", DOMAIN, "GenieSpace", GENIE)

# --- Tables ---
N("Table", T_FAC,
  f"Table `{T_FAC}` — 10,088 rows; 10,000 are address_country='India' (FILTER to India; 88 junk rows "
  f"are CSV-misparsed). SUPPLY side. One row per facility (unique_id; 11 dup ids + cluster_id groups). "
  f"99.7% geocoded (latitude/longitude doubles). facilityTypeId: hospital 5,637 / clinic 3,782 / "
  f"dentist 490. operatorTypeId ~88% private. Rich self-reported free-text: specialties / procedure / "
  f"equipment / capability (~98% present) — these are SCRAPED CLAIMS, not verified. Thin proof: "
  f"numberDoctors 36% / capacity 25% / yearEstablished 48% / recency_of_page_update 35%. "
  f"address_zipOrPostcode holds a 6-digit PIN (the join bridge to district).",
  fq_name=T_FAC, row_count=10088, primary_key="unique_id",
  grain="one row per facility (unique_id)",
  summary="10,000 India healthcare facilities (supply): type, operator, geocode, uneven free-text claims.")
E("HAS_TABLE", "Domain", DOMAIN, "Table", T_FAC)
E("HAS_TABLE", "GenieSpace", GENIE, "Table", T_FAC)

N("Table", T_NFHS,
  f"Table `{T_NFHS}` — 706 rows (698 distinct districts; some district names repeat across states). "
  f"DEMAND side: NFHS-5 (field period 2019-21) district fact sheets, 107 health indicators across "
  f"household conditions, maternal/reproductive health, child health & vaccination, nutrition, "
  f"anaemia, NCDs, cancer screening, tobacco/alcohol. Grain = district (district_name + state_ut). "
  f"~24 indicator columns are STRING-but-numeric (CAST before aggregating); '*' = suppressed (NULL, "
  f"not 0); '(29.5)' = estimate from 25-49 unweighted cases. Massive inequality across districts.",
  fq_name=T_NFHS, row_count=706, primary_key="district_name, state_ut",
  grain="one row per district (district_name + state_ut)",
  summary="NFHS-5 (2019-21) district health burden: anaemia, stunting, births, vaccination, insurance, NCDs.")
E("HAS_TABLE", "Domain", DOMAIN, "Table", T_NFHS)
E("HAS_TABLE", "GenieSpace", GENIE, "Table", T_NFHS)

N("Table", T_PIN,
  f"Table `{T_PIN}` — 165,627 rows. India Post PIN-code directory: the geo CROSSWALK that bridges a "
  f"facility's PIN to an NFHS district. Grain = POST OFFICE, not PIN: a single pincode fans out to "
  f"many rows and can map to >1 district — DEDUP to the MODAL district per pincode before joining "
  f"(a raw join on pincode fans rows out). 19,586 unique PINs, 750 districts, 37 states. "
  f"latitude/longitude are strings with ~12,600 'NA' — not every post office is geocoded.",
  fq_name=T_PIN, row_count=165627, primary_key="(post office row; pincode not unique)",
  grain="one row per post office",
  summary="India Post PIN->district->state crosswalk; the facility-PIN to NFHS-district bridge (dedup to modal district).")
E("HAS_TABLE", "Domain", DOMAIN, "Table", T_PIN)
E("HAS_TABLE", "GenieSpace", GENIE, "Table", T_PIN)

# --- JOINS ---
E("JOINS_ON", "Table", T_FAC, "Table", T_PIN, via="facilities.address_zipOrPostcode (6-digit PIN) = pincode")
E("JOINS_ON", "Table", T_PIN, "Table", T_NFHS, via="normalized district (modal per PIN) = nfhs district_name")

# --- Columns (key / join / gotcha) ---
def COL(table, name, dtype, notes):
    full = f"{table}.{name}"
    N("Column", full, f"Column `{name}` on `{table}` — {dtype}. {notes}",
      table=table, dtype=dtype, notes=notes)
    E("HAS_COLUMN", "Table", table, "Column", full)
    return full

COL(T_FAC, "unique_id", "string", "Facility primary key. 10,088 rows / 10,077 distinct -> 11 dups; see cluster_id for dedup groups.")
COL(T_FAC, "address_zipOrPostcode", "string", "Holds a 6-digit PIN. THE join bridge to district via the PIN directory. String-numeric — extract \\d{6}. 97.8% parseable.")
COL(T_FAC, "address_stateOrRegion", "string", "Free-text state — polluted (234 distinct vs 36 real). Normalize UPPER/strip before any state rollup.")
COL(T_FAC, "address_city", "string", "City; 100% present but spelling varies; weaker join key than PIN.")
COL(T_FAC, "latitude", "double", "Geocode (99.7% present). Enables point-in-polygon district assignment if boundaries are available.")
COL(T_FAC, "longitude", "double", "Geocode (99.7% present).")
COL(T_FAC, "facilityTypeId", "string", "hospital / clinic / dentist / ... (some junk values). Supply composition.")
COL(T_FAC, "operatorTypeId", "string", "private (~88%) / public (~5%) / null. Public-supply gap signal.")
COL(T_FAC, "specialties", "string", "Self-reported JSON-ish claim list (~98% present). A CLAIM, not verified — cite as source text.")
COL(T_FAC, "equipment", "string", "Self-reported equipment claim text (~98%). Search for advanced kit (MRI/CT/ICU/dialysis) — but it is a CLAIM.")
COL(T_FAC, "capability", "string", "Self-reported capability claim text (~99%). Trust must corroborate against proof fields.")
COL(T_FAC, "numberDoctors", "string", "Proof field — only 36% present; string-numeric. Sparse corroboration of claims.")
COL(T_FAC, "capacity", "string", "Proof field (beds) — only 25% present; string-numeric.")
COL(T_FAC, "recency_of_page_update", "string", "Freshness signal — only 35% present. Stale/absent => lower trust.")

COL(T_NFHS, "district_name", "string", "Join key to the PIN crosswalk (normalize UPPER/strip). 698 distinct in 706 rows.")
COL(T_NFHS, "state_ut", "string", "State/UT (36). Second half of the district grain; use for state rollups.")
COL(T_NFHS, "all_w15_49_who_are_anaemic_pct", "double", "Women 15-49 anaemic %. Headline burden indicator (range ~15-94%).")
COL(T_NFHS, "child_6_59m_who_are_anaemic_lt_11_0_g_dl_22_pct", "string", "Child 6-59m anaemic %. STRING-numeric -> CAST. Range ~25-96%.")
COL(T_NFHS, "child_u5_who_are_stunted_height_for_age_18_pct", "string", "Child under-5 stunting %. STRING-numeric -> CAST. Range ~13-61%.")
COL(T_NFHS, "institutional_birth_5y_pct", "double", "Institutional birth %. Care-access indicator (range ~21-100%).")
COL(T_NFHS, "hh_member_covered_health_insurance_pct", "double", "Household with any health insurance %. Range ~1-98%.")
COL(T_NFHS, "child_12_23m_fully_vaccinated_based_on_information_from_vax_pct", "string", "Full immunization % (12-23m). STRING-numeric -> CAST.")

COL(T_PIN, "pincode", "int64", "6-digit PIN. Join key from facility.address_zipOrPostcode. NOT unique (post-office grain) — dedup to modal district.")
COL(T_PIN, "district", "string", "District for the post office — the bridge value to NFHS district_name (after normalization).")
COL(T_PIN, "statename", "string", "State for the post office.")

# ============================================================ DYNAMIC LAYERS
# Metrics / Rules / SqlPatterns / Findings / Questions are injected from the
# verified EDA in build_domain_dynamic.py (imported below if present).
try:
    import build_domain_dynamic as dyn  # noqa
    dyn.add(N, E, dict(T_FAC=T_FAC, T_NFHS=T_NFHS, T_PIN=T_PIN, GENIE=GENIE, DOMAIN=DOMAIN))
    print("[seed] dynamic layer injected")
except ImportError:
    print("[seed] (no dynamic layer yet — static structure only)")

if __name__ == "__main__":
    from collections import Counter
    out = {"nodes": NODES, "edges": EDGES}
    Path("domain_seed.json").write_text(json.dumps(out, indent=2))
    print("[seed] nodes:", len(NODES), dict(Counter(n["type"] for n in NODES)))
    print("[seed] edges:", len(EDGES), dict(Counter(e["type"] for e in EDGES)))
    print("[seed] wrote domain_seed.json")
