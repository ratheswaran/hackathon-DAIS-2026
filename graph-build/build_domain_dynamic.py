"""Dynamic domain layer for the India-healthcare (Medical Desert Planner) graph.

Authored from the SOURCE-VERIFIED EDA workflow (medical-desert-eda-mine, 36 findings,
20 confirmed / 7 corrected / 0 rejected) + DAV editorial mining + the adapted
"Care Lottery" story spine. Every number here was reproduced by an independent
verifier (corrected numbers used where the verifier disagreed).

Imported by build_domain_seed.py via `add(N, E, ctx)`. N/E append to the same
node/edge lists as the static layer, so cross-layer edges (-> GenieSpace/Table/
Column built there, and -> Tool/ChartRecipe/ChartType/DesignRule kept skill nodes)
resolve at load time by canonical (type, name).
"""
from __future__ import annotations


def add(N, E, ctx):
    T_FAC = ctx["T_FAC"]; T_NFHS = ctx["T_NFHS"]; T_PIN = ctx["T_PIN"]
    GENIE = ctx["GENIE"]; DOMAIN = ctx["DOMAIN"]

    # ---- typed helpers -----------------------------------------------------
    def M(name, content, **p): N("Metric", name, content, **p); return name
    def R(name, content, **p): N("Rule", name, content, **p); return name
    def S(name, content, **p): N("SqlPattern", name, content, **p); return name
    def F(name, content, **p): N("Finding", name, content, **p); return name
    def Q(name, content, **p): N("Question", name, content, **p); return name
    def D(name, statement): N("DesignRule", name, statement, statement=statement); return name

    # ============================================================ METRICS
    M("facilities_total", "Count of India facilities = COUNT over facilities WHERE address_country='India' (10,000 rows; 88 junk rows excluded). DEDUP first: 11 unique_id values repeat as byte-identical rows -> 9,989 DISTINCT facilities. DATASET COVERAGE, not census (FDR lists 47k+).",
      definition="In-dataset India facility count (9,989 distinct after dedup)", formula="COUNT(DISTINCT unique_id) WHERE address_country='India'", unit="facilities")
    M("private_share", "Private operator share = private / (operators excluding the literal 'null' string). 88.4% of all India rows / 94.9% of the 9,313 with a known operator. Public+government just 4.7%.",
      definition="Share of facilities operated privately", formula="COUNT_IF(operatorTypeId='private') / COUNT_IF(operatorTypeId<>'null')", unit="ratio")
    M("facility_geocoding_rate", "Share of facilities with both latitude & longitude = 99.7% (9,970/10,000); 99.64% inside India's bbox. Clean doubles — map directly, no geocoding step.",
      definition="Share of facilities with usable lat/lon", formula="AVG(latitude IS NOT NULL AND longitude IS NOT NULL)", unit="ratio")
    M("facility_supply_concentration", "Across-state Gini of facility coverage = 0.609 (top-5 states 49.8%, top-10 73.7%). Concentration of DATASET COVERAGE, not real supply.",
      definition="Gini of facilities per state", formula="gini(facilities_by_state)", unit="gini 0..1")
    M("health_burden_index", "HBI = mean of per-district percentile ranks (0=lowest burden, 50=median, 100=highest) across 10 NFHS-5 indicators: anaemia (women+child), stunting, wasting, underweight, and the inverse of institutional birth, 4+ANC, full immunization, insurance, improved sanitation. RELATIVE rank, NOT a clinical prevalence.",
      definition="Relative district health-burden composite (NFHS-5 2019-21)", formula="mean(percentile_rank(indicator_i), inverting higher-is-better)", unit="0..100 percentile composite")
    M("women_anaemia_rate", "all_w15_49_who_are_anaemic_pct. Median district 57.2%, range 14.9% (Kohima) to 93.5% (Leh/Ladakh). Over half of districts have a majority of women anaemic.",
      definition="% women 15-49 anaemic (NFHS-5)", formula="AVG over district", unit="percent")
    M("child_stunting_rate", "child_u5_who_are_stunted_height_for_age_18_pct (STRING->CAST). Median 32.8%, range 13.2% (Jagatsinghapur) to 60.6% (Pashchimi Singhbhum, also worst on underweight 62.4%).",
      definition="% under-5 stunted (NFHS-5)", formula="AVG(CAST(...))", unit="percent")
    M("institutional_birth_rate", "institutional_birth_5y_pct. Median 92.2%, range 21.4% (Mon, Nagaland) to 100% (South Goa). Care-access proxy.",
      definition="% births in a facility (NFHS-5)", formula="AVG over district", unit="percent")
    M("full_immunization_rate", "child_12_23m_fully_vaccinated... (STRING->CAST). Median 85.0%, min 45.0% (Ukhrul). Heavy suppression — 22 '*' districts + 323 parenthesized estimates: treat tail as low-confidence.",
      definition="% children 12-23m fully immunized (NFHS-5)", formula="AVG(CAST(...))", unit="percent")
    M("health_insurance_coverage", "hh_member_covered_health_insurance_pct. Range 1.2% (South Andaman) to 97.8% (Barmer) = 81.5x spread — the widest 'care lottery' indicator.",
      definition="% households with any health insurance (NFHS-5)", formula="AVG over district", unit="percent")
    M("facilities_per_district", "Count of dataset facilities resolved to an NFHS district via the PIN crosswalk. Mean 11.6, median 2, max 325 (Pune). 245 districts = 0. COVERAGE, not supply.",
      definition="In-dataset facility count per NFHS district", formula="COUNT(facility) GROUP BY resolved_district", unit="facilities")
    M("desert_score", "Desert score = high health_burden_index x low facilities_per_district. Ranks high-need + few/zero-coverage districts. Top-15 led by Araria (Bihar, 0 facilities, score 3.73).",
      definition="Composite of demand burden and supply scarcity", formula="z(health_burden_index) - z(log1p(facilities_per_district))", unit="z-composite")
    M("burden_supply_correlation", "Spearman correlation of district burden vs facility coverage = NEGATIVE, rho ~ -0.2 to -0.27 (p<1e-8). High-burden tertile averages 5.5 facilities vs ~14.6 for the rest — supply does NOT follow need.",
      definition="Correlation between health burden and facility coverage", formula="spearman(health_burden_index, facilities_per_district)", unit="rho -1..1")
    M("facility_trust_score", "Transparent additive 0-100 score over 8 corroboration signals: recent_update 25, has_doctors 20, has_website 15, has_capacity 15, has_phone 10, affiliated_staff 5, social_2plus 5, rich_desc 5. Median facility scores just 45; 50.9% below 50. Auditable analyst design, NOT learned, NOT real-world quality.",
      definition="Evidence-corroboration score per facility", formula="sum(weighted corroboration signals), max 100", unit="0..100")
    M("unverifiable_claim_rate", "Share of facilities making an advanced-capability claim (MRI/CT/ICU/cancer/cardiac/dialysis/NICU/transplant in equipment/capability text) with NO doctor count, NO capacity, AND no recent update = 1,219 (12.2% of all India, 29.9% of the 4,077 advanced-claimers).",
      definition="Advanced claims with zero hard corroboration", formula="COUNT(advanced_claim AND no_doctors AND no_capacity AND stale) / COUNT(*)", unit="ratio")

    # ============================================================ RULES (gotchas)
    R("R-india-filter", "Always filter facilities to address_country='India' (= address_countryCode='IN'); 88 of 10,088 rows are CSV-misparse junk (coordinates/JSON/free-text/'kie'/None in the country column). Leaves exactly 10,000 analyzable rows.",
      rule_id="R-FAC-1", severity="high", statement="Filter address_country='India' on facilities; 88 junk rows otherwise.",
      rationale="Misparsed CSV rows carry coordinates/JSON in the country field and pollute every facility metric.")
    R("R-facility-dedup", "facilities.unique_id is NOT unique: 11 IDs each appear twice as BYTE-IDENTICAL rows (confirmed exact dupes, also flagged by cluster_id's 11 size-2 clusters). SELECT DISTINCT unique_id (or drop_duplicates) collapses 10,000 -> 9,989 facilities. Safe — exact re-scrapes, no merge logic needed; do it before any facility COUNT or rate so totals aren't inflated by ~0.1%.",
      rule_id="R-FAC-0", severity="high", statement="facilities.unique_id repeats 11x as exact-duplicate rows — dedup (DISTINCT unique_id) to 9,989 before counting.",
      rationale="11 byte-identical re-scrapes inflate every facility count if not deduped; cluster_id confirms they are the same physical site.")
    R("R-coverage-not-census", "THE honesty contract. The facilities table is a ~10k web-discovered SAMPLE, not a census (India's FDR lists 47k+). Every facility count / desert / gap claim must be framed as in-dataset COVERAGE, never absolute supply. A zero-facility district = zero in THIS dataset (a coverage/outreach gap), NOT 'no care exists'. NO per-capita anywhere (no population column in the 3 tables). Cite the source TEXT field for any facility capability claim. Communicating this uncertainty is itself scored by the rubric.",
      rule_id="R-HONESTY", severity="critical", statement="Facility counts are dataset coverage, not supply; no per-capita; cite source text; state uncertainty.",
      rationale="Presenting a sample coverage gap as proven absence of care is the central failure mode the 'Medical Desert Planner' track tests.")
    R("R-string-null-sentinel", "Missing values in facilities are the literal string 'null' (also 'none'/'NA'/''), NOT SQL NULL. Strip these before any fill-rate, presence, or aggregation. numberDoctors looks 99.7% populated but is real for only 36.2%; capacity 25.0%; recency 35.4%. A naive COUNT(col) overstates evidence ~3x.",
      rule_id="R-FAC-2", severity="critical", statement="Treat literal 'null'/'none'/'NA'/'' as missing before counting or aggregating facility fields.",
      rationale="The dataset encodes missing as a string sentinel; SQL NULL checks miss it entirely.")
    R("R-cast-facility-numeric", "facilities numberDoctors, capacity, address_zipOrPostcode, distinct_social_media_presence_count and number_of_facts_about_the_organization are STRING-but-numeric. Strip ()/* then try_cast(... AS DOUBLE) (errors->NULL), and require value>0 before treating as evidence.",
      rule_id="R-FAC-3", severity="high", statement="CAST facility string-numeric cols (strip ()*, try_cast) and require >0 before use.",
      rationale="Aggregating a STRING column errors or sorts lexically; the sentinel 'null' also poisons casts.")
    R("R-normalize-state", "address_stateOrRegion is polluted: 234 distinct values (city names + spelling variants + junk) vs 36 real states/UTs. Normalize UPPER/strip/[^A-Z0-9 &]->space + an alias map (Tamilnadu->Tamil Nadu, Orissa->Odisha, UP/U P->Uttar Pradesh, Chattisgarh->Chhattisgarh; city names->drop) before any state rollup. 96.9% map cleanly.",
      rule_id="R-FAC-4", severity="high", statement="Normalize + alias-map address_stateOrRegion before any state-level aggregation.",
      rationale="Raw state strings double-count and scatter facilities across 234 spurious categories.")
    R("R-operatortype-null-string", "operatorTypeId contains a literal STRING 'null' (687 India rows) distinct from real NULL. Replace 'null'->missing before computing private/public share, or 'null' is counted as its own operator category.",
      rule_id="R-FAC-5", severity="medium", statement="Replace literal 'null' in operatorTypeId before computing operator shares.",
      rationale="Otherwise the missing sentinel ranks as the 3rd-largest 'operator type'.")
    R("R-drop-constant-orgtype", "organization_type is the constant 'facility' for all 10,000 India rows — no analytical signal. Do not group or facet by it.",
      rule_id="R-FAC-6", severity="low", statement="organization_type is constant 'facility' — never group by it.",
      rationale="A constant column adds noise and a useless facet.")
    R("R-claims-self-reported", "Every facility attribute (specialties, equipment, capability, procedure, description, numberDoctors, capacity) is self-reported SCRAPED free text. Never present a claim as verified fact; cite the source field name when stating a capability. A 'null' proof field = undisclosed, not proof the capability is fake (risk-to-verify, not misrepresentation).",
      rule_id="R-TRUST-1", severity="critical", statement="Facility claims are self-reported scraped text — cite the field, never assert as verified.",
      rationale="The Trust/Referral use cases require citing evidence and communicating uncertainty, not trusting scraped claims.")
    R("R-recency-date-caveat", "recency_of_page_update spans 2003-2027 and contains future-dated stamps (scrape artifacts). Parse with errors->coerce; treat a date>today as 'recent' rather than dropping it; disclose the parse rule when reporting recency-based trust.",
      rule_id="R-TRUST-2", severity="medium", statement="recency_of_page_update has future-dated scrape artifacts — coerce-parse and disclose.",
      rationale="Dropping future dates silently discards real (if odd) freshness signals.")
    R("R-nfhs-cast", "49 of 107 NFHS-5 indicator columns are stored STRING-but-numeric. Always CAST after stripping ()/* and whitespace: pd.to_numeric(s.str.replace(r'[()*]','',regex=True).str.strip(),errors='coerce') or try_cast(regexp_replace(col,'[()*]','') AS DOUBLE). Casting raw fails or zeroes out.",
      rule_id="R-NFHS-1", severity="high", statement="CAST the 49 string-numeric NFHS columns (strip ()*) before aggregating.",
      rationale="Direct aggregation of a STRING percentage column errors or sorts lexically.")
    R("R-nfhs-suppressed-star", "A '*' in any NFHS-5 cell means the estimate was suppressed (sample too small). Treat as NULL, exclude from means/counts — NEVER as zero (zero fabricates 'perfect'/'zero-burden' districts). 4,125 cells across 29 columns are suppressed.",
      rule_id="R-NFHS-2", severity="high", statement="NFHS '*' = suppressed = NULL, never zero.",
      rationale="Coercing '*' to 0 invents perfect or zero-burden districts.")
    R("R-nfhs-parenthesized-estimate", "A parenthesized value like '(29.5)' is an estimate from 25-49 unweighted cases. Strip the parens to use it, but FLAG it low-confidence and never quote it as a headline. 5,068 cells across 48 columns are parenthesized (full immunization has 323).",
      rule_id="R-NFHS-3", severity="medium", statement="NFHS '(x.x)' = low-sample estimate — usable but never a headline.",
      rationale="25-49 unweighted cases give wide confidence intervals; tail districts are unreliable.")
    R("R-nfhs5-vintage", "NFHS-5 fieldwork was 2019-21. Always label these district indicators as the 2019-21 baseline, never current-year/2024. This vintage pre-dates the facilities supply table; NFHS-6 (2023-24) is separate and not directly comparable.",
      rule_id="R-NFHS-4", severity="medium", statement="Label NFHS-5 indicators as the 2019-21 baseline, not current.",
      rationale="Mixing NFHS-5 demand with later supply or treating it as 'now' misstates the timeline.")
    R("R-hbi-relative-percentile", "health_burden_index is a RELATIVE percentile-rank composite (0=lowest burden, 50=median, 100=highest), not a prevalence. Always describe it as a relative ranking and state its 10 component indicators and the inversion of the 5 higher-is-better ones.",
      rule_id="R-NFHS-5", severity="medium", statement="HBI is a relative percentile composite — describe as ranking, list components.",
      rationale="Readers misread a 78 as '78% of people' instead of '78th-percentile burden district'.")
    R("R-demand-not-supply", "NFHS-5 indicators measure health NEED (demand) only — they say nothing about facility supply. A 'medical desert' claim REQUIRES joining high burden to LOW in-dataset facility coverage; and facility counts are dataset coverage (a ~10k sample), never a census.",
      rule_id="R-NFHS-6", severity="high", statement="NFHS = demand only; 'desert' needs the burden x low-coverage join.",
      rationale="High burden alone is need, not a desert; a desert is need unmet by supply.")
    R("R-pin-fanout-dedup", "india_post_pincode_directory is post-office grain (8.5 rows/PIN; 165,627 rows / 19,586 PINs) and 1,478 PINs (7.55%) fan out to >1 district (max 4). DEDUP to the MODAL (district, statename) per pincode before joining facilities, or facility counts inflate ~8x. Its 'NA'-string coords (7.25%) cast to NULL silently.",
      rule_id="R-PIN-1", severity="critical", statement="Dedup pincode dir to the modal (district,state) per PIN before joining; raw join fans out ~8x.",
      rationale="A raw pincode join multiplies every facility into ~8 post-office rows.")
    R("R-district-name-normalization", "Normalize district names UPPER->trim->collapse whitespace->drop non-[A-Z0-9 &] on BOTH sides of the facility<->NFHS join. Recovers 81.2% of India facilities; the ~19% miss is spelling/transliteration drift (a true spatial point-in-polygon join would recover more). 704/706 NFHS names carry trailing whitespace.",
      rule_id="R-PIN-2", severity="high", statement="Normalize (UPPER/trim/collapse) district names both sides before joining; 81.2% recovery.",
      rationale="Trailing whitespace and transliteration variants make exact-string joins silently fail.")
    R("R-district-state-collision", "Name-only district join collides 8 normalized names across states (Aurangabad=Bihar+Maharashtra, Bijapur=Chhattisgarh+Karnataka, Balrampur, Bilaspur, Chandel, Hamirpur, Pratapgarh, Raigarh). Summing on district name alone double-counts these (+85 rows). Key on (normalized state, district) or do a spatial join.",
      rule_id="R-PIN-3", severity="high", statement="Key district joins on (state, district) — 8 names collide across states.",
      rationale="Joining on district name alone double-counts the 8 cross-state homonyms.")

    # ============================================================ SQL PATTERNS
    S("facilities-clean-india-count",
      "When to use: how many facilities (and how clean) — the dataset universe.\n\n```sql\nSELECT COUNT(*) AS total,\n       COUNT_IF(address_country='India') AS india_rows,\n       COUNT_IF(address_country<>'India' OR address_country IS NULL) AS junk_rows,\n       COUNT(DISTINCT unique_id) AS distinct_ids\nFROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities;\n-- 10,088 total -> 10,000 India, 88 junk, 9,989 distinct (11 dup ids)\n```",
      question="How many facilities are in the India dataset and how clean is it?", notes="Honor R-india-filter; counts are dataset coverage (R-coverage-not-census).")
    S("facility-composition-by-type-operator",
      "When to use: facility type & operator mix.\n\n```sql\nSELECT facilityTypeId, COUNT(*) AS n\nFROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities\nWHERE address_country='India' GROUP BY facilityTypeId ORDER BY n DESC;\n-- hospital 5,637 / clinic 3,782 / dentist 490\nSELECT CASE WHEN operatorTypeId='null' THEN NULL ELSE operatorTypeId END AS operator, COUNT(*) AS n\nFROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities\nWHERE address_country='India' GROUP BY 1 ORDER BY n DESC;\n-- private 8,842 (88.4%) vs public+government 471 (4.7%)\n```",
      question="What kinds of facilities are these and who operates them?", notes="Replace literal 'null' (R-operatortype-null-string); don't facet organization_type (R-drop-constant-orgtype).")
    S("facility-supply-concentration-by-state",
      "When to use: how concentrated is facility coverage across states.\n\n```sql\n-- Normalize state upstream (R-normalize-state). Top states + share:\nSELECT address_stateOrRegion AS state, COUNT(*) AS facilities,\n       ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (), 1) AS pct\nFROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities\nWHERE address_country='India'\nGROUP BY address_stateOrRegion ORDER BY facilities DESC LIMIT 10;\n-- Maharashtra 1,575 (16.3%), Gujarat 981, UP 933, TN 802, Karnataka 529; top-5=49.8%, top-10=73.7%, Gini 0.609\n```",
      question="How concentrated is facility coverage across Indian states?", notes="Concentration of dataset coverage, not real supply (R-coverage-not-census).")
    S("nfhs-burden-cast-preamble",
      "When to use: ANY NFHS-5 indicator aggregation — the CAST/suppression preamble.\n\n```sql\n-- '*' = suppressed (NULL not 0); '(x.x)' = low-sample estimate; many cols are STRING.\nSELECT district_name, state_ut,\n       try_cast(regexp_replace(child_u5_who_are_stunted_height_for_age_18_pct,'[()*]','') AS DOUBLE) AS stunting_pct,\n       try_cast(regexp_replace(child_6_59m_who_are_anaemic_lt_11_0_g_dl_22_pct,'[()*]','') AS DOUBLE) AS child_anaemia_pct\nFROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators;\n-- try_cast returns NULL for '*'/garbage; never coerce '*' to 0\n```",
      question="How do I correctly aggregate NFHS-5 indicators given the CAST/suppression gotchas?", notes="Honors R-nfhs-cast, R-nfhs-suppressed-star, R-nfhs-parenthesized-estimate.")
    S("nfhs-worst-burden-districts",
      "When to use: which districts have the highest health need (demand side).\n\n```sql\n-- Per-indicator percentile ranks -> composite HBI (see health_burden_index). Single-indicator example:\nSELECT district_name, state_ut,\n       try_cast(regexp_replace(child_6_59m_who_are_anaemic_lt_11_0_g_dl_22_pct,'[()*]','') AS DOUBLE) AS child_anaemia\nFROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators\nWHERE child_6_59m_who_are_anaemic_lt_11_0_g_dl_22_pct <> '*'\nORDER BY child_anaemia DESC LIMIT 15;\n-- HBI top: Araria 89.7, Lakhisarai 88.0, Nalanda 86.4; 10 of 15 worst are Bihar\n```",
      question="Which districts have the highest overall health burden / greatest need?", notes="HBI is a relative percentile composite (R-hbi-relative-percentile); demand only (R-demand-not-supply).")
    S("nfhs-state-burden-rollup",
      "When to use: state-level health burden (key on TRIM district+state).\n\n```sql\nSELECT TRIM(state_ut) AS state, COUNT(*) AS districts,\n       ROUND(AVG(<district HBI>), 1) AS mean_burden\nFROM ( /* district HBI subquery */ )\nGROUP BY TRIM(state_ut) HAVING COUNT(*)>=3 ORDER BY mean_burden DESC;\n-- Bihar 78.4 (n=38) vs Kerala 16.9 (n=14): a 61.5-pt gulf (4.6x). Jharkhand 69.8, UP 61.6 worst after Bihar.\n```",
      question="Which states have the highest district health burden?", notes="Key on (TRIM state, district) — R-district-state-collision; 'Maharastra' misspelling in source.")
    S("care-lottery-spread",
      "When to use: how unequal is access across districts (the 'care lottery').\n\n```sql\nSELECT 'health_insurance' AS indicator, MIN(v) AS min_pct, MAX(v) AS max_pct, ROUND(MAX(v)/NULLIF(MIN(v),0),1) AS spread_x\nFROM (SELECT try_cast(hh_member_covered_health_insurance_pct AS DOUBLE) AS v\n      FROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators) WHERE v IS NOT NULL;\n-- insurance 1.2->97.8 (81.5x); 4+ANC 4.4->98.7 (22.4x); women anaemia 14.9->93.5 (6.3x); institutional birth 21.4->100 (4.7x)\n```",
      question="How unequal is health access across districts?", notes="Report p10-p90 alongside min-max (single extreme districts are small UTs).")
    S("facility-to-district-join",
      "When to use: the SUPPLY<->DEMAND bridge — resolve facilities to an NFHS district (THE join).\n\n```sql\nWITH pin_modal AS (  -- dedup post-office grain to modal (district,state) per PIN (R-pin-fanout-dedup)\n  SELECT pincode,\n         FIRST(district) OVER (PARTITION BY pincode ORDER BY cnt DESC) AS district,\n         FIRST(statename) OVER (PARTITION BY pincode ORDER BY cnt DESC) AS statename\n  FROM (SELECT pincode, district, statename, COUNT(*) cnt\n        FROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.india_post_pincode_directory\n        GROUP BY pincode, district, statename)),\nfac AS (\n  SELECT unique_id, CAST(regexp_extract(address_zipOrPostcode,'([0-9]{6})',1) AS INT) AS pin\n  FROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities\n  WHERE address_country='India')\nSELECT f.unique_id, upper(trim(p.district)) AS district_norm, p.statename\nFROM fac f LEFT JOIN pin_modal p ON f.pin = p.pincode;\n-- coverage: 97.7% parseable PIN -> 95.7% PIN-district -> 81.2% match an NFHS district by normalized name\n```",
      question="How do I join facilities to NFHS districts (supply to demand)?", notes="Honors R-pin-fanout-dedup, R-district-name-normalization, R-district-state-collision; join ceiling 81.2%.")
    S("zero-facility-districts",
      "When to use: the medical-desert COVERAGE GAP headline.\n\n```sql\n-- facilities resolved to district (facility-to-district-join) RIGHT JOINed to all NFHS districts\nSELECT n.district_name, n.state_ut, COUNT(f.unique_id) AS facilities\nFROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators n\nLEFT JOIN resolved_facilities f ON upper(trim(n.district_name)) = f.district_norm\nGROUP BY n.district_name, n.state_ut;\n-- ~245 of 698 districts (35%) have ZERO facilities in this dataset; mean 11.6, median 2, max 325 (Pune)\n```",
      question="How many districts have no facilities in the dataset (coverage gaps)?", notes="Zero = zero in THIS sample, not absence of care (R-coverage-not-census).")
    S("desert-score-ranking",
      "When to use: rank the priority medical-desert districts (high burden x low coverage).\n\n```sql\nSELECT district, state, burden_index, facilities,\n       (zscore(burden_index) - zscore(ln(1+facilities))) AS desert_score\nFROM district_burden_supply\nORDER BY desert_score DESC LIMIT 15;\n-- Araria(Bihar,0 fac,3.73), Pakur(JH,0), Lakhisarai(Bihar,0), Jamui(Bihar,0), Sahibganj(JH,0); 13/15 Bihar+Jharkhand, 13 zero-facility\n```",
      question="Which high-need districts should a planner prioritise as medical deserts?", notes="desert_score combines demand + supply; coverage caveat applies.")
    S("burden-supply-correlation",
      "When to use: does facility supply follow need? (the analytical twist).\n\n```sql\n-- correlate district burden vs facility coverage; tertile means\nSELECT corr(burden_index, facilities) AS pearson,  -- use spearman on ranks in code\n       AVG(CASE WHEN burden_tertile='high' THEN facilities END) AS high_burden_mean,\n       AVG(CASE WHEN burden_tertile<>'high' THEN facilities END) AS rest_mean\nFROM district_burden_supply;\n-- Spearman rho ~ -0.2 to -0.27 (p<1e-8, NEGATIVE); high-burden tertile 5.5 facilities vs ~14.6 for the rest\n```",
      question="Does facility supply follow health need across districts?", notes="Mismatch is descriptive evidence of inequity, not causal/discrimination.")
    S("coverage-concentration-gini",
      "When to use: how concentrated is facility coverage across districts.\n\n```sql\n-- Gini + top-k share of facilities-per-district\nSELECT district, facilities FROM district_facility_counts ORDER BY facilities DESC;\n-- Gini 0.821; top-10 districts (Pune 325, Ahmadabad 320, Mumbai Suburban 273, Chennai 272 ...) = 28.3%; top-50 = 63.8%\n```",
      question="How concentrated is facility coverage across districts?", notes="Concentration of dataset coverage; compounds rural/tribal gaps.")
    S("facility-trust-score",
      "When to use: score how well a facility's claims are corroborated.\n\n```sql\nWITH s AS (SELECT *,\n  CASE WHEN try_cast(numberDoctors AS DOUBLE)>0 THEN 1 ELSE 0 END AS has_doctors,\n  CASE WHEN try_cast(capacity AS DOUBLE)>0 THEN 1 ELSE 0 END AS has_capacity,\n  CASE WHEN officialWebsite NOT IN ('null','') AND officialWebsite IS NOT NULL THEN 1 ELSE 0 END AS has_website\n  FROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities WHERE address_country='India')\nSELECT unique_id, name,\n  25*recent + 20*has_doctors + 15*has_website + 15*has_capacity + 10*has_phone + 5*affiliated + 5*social2 + 5*rich_desc AS trust_score\nFROM s;\n-- median 45/100; 50.9% below 50 (hard-proof signals are thin). Strip literal 'null' first (R-string-null-sentinel).\n```",
      question="How trustworthy / well-corroborated is a facility's listing?", notes="Score = data corroboration, not care quality; auditable weights (R-claims-self-reported).")
    S("unverifiable-advanced-claims",
      "When to use: find facilities claiming advanced care they can't back up.\n\n```sql\nSELECT unique_id, name, equipment, capability\nFROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities\nWHERE address_country='India'\n  AND (lower(equipment) RLIKE '\\\\b(mri|ct scan|icu|cancer|oncolog|cardiac|cathlab|dialysis|nicu|transplant)\\\\b'\n    OR lower(capability) RLIKE '\\\\b(mri|ct|icu|cancer|cardiac|dialysis|nicu|transplant)\\\\b')\n  AND (numberDoctors='null' OR numberDoctors IS NULL)\n  AND (capacity='null' OR capacity IS NULL);\n-- 1,219 facilities (12.2% of all India, 29.9% of the 4,077 advanced-claimers) make advanced claims with zero hard proof\n```",
      question="Which facilities make advanced-care claims they cannot back up?", notes="Word-boundary regex; 'null' proof = undisclosed, treat as risk-to-verify (R-claims-self-reported).")

    # ============================================================ FINDINGS (the "why")
    F("the-care-lottery",
      "Within ONE country, a child's healthcare odds are decided by district, not by need. Health-insurance coverage ranges 1.2% to 97.8% across districts (81.5x), 4+ antenatal visits 4.4% to 98.7% (22.4x), women's anaemia 14.9% to 93.5% (6.3x), institutional birth 21.4% to 100% (4.7x). Where you're born dominates your access. The master narrative — 'same country, opposite odds.'",
      claim="District health access varies up to 81.5x within India — where you live decides your odds.",
      evidence="NFHS-5 2019-21, 706 districts: insurance 1.2->97.8% (81.5x), 4+ANC 4.4->98.7% (22.4x), women anaemia 14.9->93.5% (6.3x)",
      why="Outcomes track district of birth, not individual need — the structural 'care lottery'.",
      window="NFHS-5 2019-21, all 706 districts")
    F("medical-deserts-zero-coverage",
      "About 245 of 698 NFHS districts (35%) have ZERO facilities in this dataset — and the worst-need places are the emptiest. The five highest child-anaemia districts (Leh/Ladakh 95.5%, Sukma 91.4%, Lahul & Spiti 91.0%, Dantewada 89.9%, Tawang 89.6%) ALL have zero dataset facilities. Framed honestly as a data-COVERAGE gap, which is itself the signal: the highest-need places are invisible to data-driven planning.",
      claim="~245 of 698 districts (35%) have zero facilities in this dataset; the 5 worst child-anaemia districts all have zero.",
      evidence="PIN-crosswalk join; 244-245 zero-coverage districts; Leh/Ladakh 95.5%, Sukma 91.4%, Lahul&Spiti 91.0%, Dantewada 89.9%, Tawang 89.6% all 0 facilities",
      why="Web-scraped sample is biased to urban/private orgs, so the highest-need rural/tribal districts are absent.",
      window="facilities sample (~10k) joined to NFHS-5 districts")
    F("supply-does-not-follow-need",
      "The analytical twist: you'd expect facilities to follow burden, but they don't. Burden vs dataset facility coverage is significantly NEGATIVELY correlated (Spearman rho ~ -0.2 to -0.27, p<1e-8). The highest-burden tertile averages just 5.5 facilities/district vs ~14.6 for the rest; zero-facility share rises from 28.8% (low burden) to 40.9% (high burden). A descriptive mismatch between need and coverage — not proof of cause.",
      claim="Health burden and facility coverage are negatively correlated (rho ~ -0.2, p<1e-8): supply does not follow need.",
      evidence="Spearman rho -0.2..-0.27 (p<1e-8, n=706); high-burden tertile 5.5 facilities vs ~14.6; zero-fac share 28.8%->40.9%",
      why="Coverage concentrates in metros; the rural high-burden districts are under-sampled — inequity in who the data even sees.",
      window="district burden index vs in-dataset facility coverage")
    F("top-desert-districts-bihar-jharkhand",
      "The priority deserts cluster in Bihar and Jharkhand. The 15 highest desert-score districts (high burden, <=2 facilities) are led by Araria (Bihar; 0 facilities; child anaemia 75.8%; only 25.8% of mothers get 4+ ANC visits), Pakur, Lakhisarai, Jamui and Sahibganj — 13 of 15 are in Bihar/Jharkhand and 13 have zero dataset facilities.",
      claim="13 of the 15 worst medical-desert districts are in Bihar/Jharkhand; 13 have zero facilities.",
      evidence="desert_score top-15: Araria(Bihar,0,3.73), Pakur(JH,0), Lakhisarai(Bihar,0), Jamui(Bihar,0), Sahibganj(JH,0)...",
      why="Bihar/Jharkhand combine the highest health burden with the thinnest dataset coverage.",
      window="desert_score ranking over matched NFHS districts")
    F("the-burden-belt",
      "Need concentrates in the east-central belt. On the 10-indicator HBI, Araria (Bihar) is the single highest-burden district at 89.7/100, and 10 of the 15 worst are in Bihar; rolled to state, Bihar averages 78.4 vs Kerala 16.9 — a 61.5-point gulf (4.6x). Jharkhand (69.8) and Uttar Pradesh (61.6) follow.",
      claim="Bihar is India's highest-burden state (HBI 78.4) vs Kerala's 16.9 — a 4.6x gulf; Araria is the worst district (89.7).",
      evidence="HBI: Araria 89.7 (top of 706), 10 of 15 worst in Bihar; state means Bihar 78.4 (n=38), Jharkhand 69.8, UP 61.6, Kerala 16.9 (n=14)",
      why="Compounding deprivation (anaemia+stunting+low ANC+low insurance) clusters in the eastern Gangetic plain.",
      window="NFHS-5 2019-21 HBI, district + state rollup")
    F("the-southern-advantage",
      "The mirror image: the 15 lowest-burden districts in India are entirely in the deep south — Kanniyakumari (Tamil Nadu) lowest at HBI 9.4, then a wall of Kerala districts (Kozhikode 10.7, Pathanamthitta 11.3, Thrissur 12.0). A best-15 sweep by one region is itself the inequality story.",
      claim="The 15 lowest-burden districts are all in the deep south; Kanniyakumari is lowest (HBI 9.4).",
      evidence="HBI best-15: Kanniyakumari(TN) 9.4, Kozhikode(KL) 10.7, Pathanamthitta(KL) 11.3, Thrissur(KL) 12.0, Kasaragod 12.4...",
      why="Kerala/Tamil Nadu's decades of health-system investment show up as a southern wall at the good end.",
      window="NFHS-5 2019-21 HBI")
    F("women-anaemia-majority",
      "Anaemia among women 15-49 has a median of 57.2% — over half of all districts have a MAJORITY of women anaemic — ranging 14.9% (Kohima, Nagaland) to 93.5% (Leh/Ladakh). Child anaemia is worse (median 67.7%, max 95.5%, also Leh/Ladakh).",
      claim="The median district has 57% of women anaemic; child anaemia medians 68% and peaks at 95.5%.",
      evidence="women anaemia n=706: min 14.9 (Kohima), median 57.2, max 93.5 (Leh/Ladakh); child anaemia median 67.7, max 95.5",
      why="Anaemia is the most widespread NFHS burden — a majority-of-women crisis, not a tail problem.",
      window="NFHS-5 2019-21")
    F("child-malnutrition-stunting",
      "The median district stunts a third of its young children (32.8%), ranging 13.2% (Jagatsinghapur, Odisha) to 60.6% (Pashchimi Singhbhum, Jharkhand — also worst on underweight at 62.4%). Stunting/wasting/underweight share worst districts, so they are not independent signals.",
      claim="Under-5 stunting medians 32.8% and peaks at 60.6% (Pashchimi Singhbhum, Jharkhand).",
      evidence="stunting n=706: 13.2 (Jagatsinghapur) -> 60.6 (Pashchimi Singhbhum), median 32.8; underweight max 62.4 (same district)",
      why="Chronic child undernutrition concentrates in the same eastern tribal belt as anaemia.",
      window="NFHS-5 2019-21")
    F("private-skew-public-gap",
      "The supply we can see is overwhelmingly private. 88.4% of India facilities are private vs 4.7% public/government (an 18.8:1 ratio of known operators), and 94.2% are hospitals or clinics. A planner relying on this dataset sees mostly the private market, so public-sector gaps look worse than reality.",
      claim="88% of dataset facilities are private vs 5% public — an 18.8:1 skew that hides public supply.",
      evidence="operatorTypeId (known): private 8,842 (94.9% of 9,313 known), public+government 471; facilityTypeId hospital 56.4% + clinic 37.8%",
      why="Web-scraped discovery favours private orgs with a digital footprint, undercounting public clinics.",
      window="facilities sample, India")
    F("supply-concentration",
      "Coverage is hoarded by a handful of states and metros. The top-5 states hold 49.8% of dataset facilities (Maharashtra alone 16.3%) and the top-10 hold 73.7% (across-state Gini 0.609); across districts the Gini is 0.821, with the top-10 districts (Pune 325, Ahmadabad 320, Mumbai Suburban 273, Chennai 272...) holding 28.3% and the top-50 holding 63.8%. The northeast is nearly absent (Sikkim 4, Arunachal 3, Mizoram few).",
      claim="Top-5 states hold ~50% of dataset facilities; district coverage Gini is 0.821 (top-50 districts = 63.8%).",
      evidence="state Gini 0.609 (top-5 49.8%, Maharashtra 16.3%, top-10 73.7%); district Gini 0.821 (top-10 28.3%, top-50 63.8%)",
      why="Dataset coverage concentrates in dense urban/private markets, compounding rural/tribal blind spots.",
      window="facilities sample resolved to states/districts")
    F("claims-rich-proof-thin",
      "Facilities say a lot and prove little. Claim text is near-complete (description 100%, specialties 99.7%, capability 99.4%) but hard proof is sparse: numberDoctors real for only 36.3%, capacity 25.2%, recency 35.4% (the raw 99.7% is the literal-'null' sentinel). The median facility scores just 45/100 on the trust score; 50.9% fall below 50.",
      claim="Facility claims are ~99% present but hard proof (doctors 36%, capacity 25%) is thin; median trust 45/100.",
      evidence="present: specialties 99.7%, capability 99.4%; real-fill: numberDoctors 36.3%, capacity 25.2%, recency 35.4%; trust median 45, 50.9% below 50",
      why="The data is scraped self-report — believability, not capability; a planner must verify before acting.",
      window="facilities sample, India")
    F("unverifiable-advanced-claims",
      "1,219 facilities (12.2% of all India, 29.9% of the 4,077 making advanced-capability claims) advertise MRI/CT/ICU/cancer/cardiac/dialysis/NICU/transplant capability yet expose NO doctor count, NO bed capacity, and no recent page update. Treat as risk-to-verify, not proof of misrepresentation — but never send a patient on an unverified advanced claim.",
      claim="1,219 facilities (29.9% of advanced-claimers) advertise advanced care with zero hard corroboration.",
      evidence="advanced-claimers 4,077 (40.8%); unverifiable (claim AND no doctors AND no capacity AND stale) 1,219; 37.8% of claimers have no hard proof",
      why="Self-reported scraped claims with no corroboration are the highest patient-safety risk in a referral.",
      window="facilities sample, India; word-boundary capability regex")
    F("the-data-readiness-tax",
      "Before a planner can trust any number, the data needs work: 88 junk rows + 11 duplicate IDs in facilities; missing encoded as the string 'null' (so numberDoctors is real for 36%, not 99.7%); 49 NFHS columns are string-numeric with 26.6% of cells suppressed ('*') or low-sample estimates; 8 district names collide across states; the PIN directory fans out ~8x. None of it is optional.",
      claim="Trusting this data requires fixing string-'null' sentinels, 49 CAST columns, 26.6% suppressed cells, PIN fan-out, and 8 colliding district names.",
      evidence="facilities: 88 junk, 11 dup ids, 'null' sentinel (doctors 99.7%->36%); NFHS: 49 string cols, 9,193/34,594 cells (26.6%) suppressed/estimated; PIN: 8.5 rows/PIN, 1,478 multi-district",
      why="Every desert/trust claim is only as honest as the cleaning behind it — the 'communicate uncertainty' rubric.",
      window="all 3 tables")
    F("geocoding-ready-to-map",
      "The good news: 99.7% of facilities have clean lat/lon (99.64% inside India's bbox) and 97.7% carry a parseable 6-digit PIN, so facilities map directly with no geocoding step — the supply layer is map-ready even where the demand join needs name normalization.",
      claim="99.7% of facilities are geocoded and 97.7% have a parseable PIN — the supply layer is map-ready.",
      evidence="lat+lon present 9,970/10,000 (99.7%), 99.64% in-bbox; parseable PIN 97.7%",
      why="Clean coordinates let a planner dot-map supply against the burden choropleth immediately.",
      window="facilities sample, India")

    # ============================================================ QUESTIONS (routing)
    Q("Where are India's medical deserts (high need, low coverage)?",
      "The flagship Medical Desert Planner question. Joins NFHS burden to in-dataset facility coverage to rank high-need low-coverage districts.", intent="desert_priority_ranking")
    Q("Which districts have zero facilities in the dataset?",
      "The coverage-gap headline: ~245 of 698 NFHS districts have no facility in this sample.", intent="coverage_gap_count")
    Q("Does facility supply follow health need across India?",
      "The analytical twist: burden vs coverage correlation (negative, supply does not follow need).", intent="equity_correlation")
    Q("Which districts have the highest health burden?",
      "Demand-side ranking via the HBI composite (Araria 89.7; 10 of 15 worst in Bihar).", intent="burden_ranking")
    Q("Which states have the best and worst health outcomes?",
      "State HBI rollup: Bihar 78.4 worst vs Kerala 16.9 best.", intent="state_burden_view")
    Q("How unequal is healthcare access across India?",
      "The care-lottery spread: up to 81.5x district variation in insurance, 22.4x in 4+ANC.", intent="inequality_spread")
    Q("Where is anaemia / child malnutrition worst?",
      "Single-indicator district ranking (women anaemia median 57%, stunting peaks 60.6%).", intent="indicator_worst_districts")
    Q("Can I trust this facility's claims?",
      "Facility trust score over 8 corroboration signals; cite the source text field.", intent="facility_trust_lookup")
    Q("Which facilities claim advanced care they can't back up?",
      "Unverifiable advanced-claim filter (1,219 facilities; MRI/CT/ICU/cancer with no proof).", intent="unverifiable_claims")
    Q("How concentrated is facility coverage?",
      "Gini + top-k share across states (0.609) and districts (0.821).", intent="coverage_concentration")
    Q("What kinds of facilities are in the dataset and who runs them?",
      "Composition: hospital 56% / clinic 38%; 88% private.", intent="composition_lookup")
    Q("What must be fixed before I can trust this data?",
      "The data-readiness punch list: string-'null' sentinels, 49 CAST cols, 26.6% suppressed NFHS cells, PIN fan-out, colliding district names.", intent="data_readiness")
    Q("How do facilities map to districts?",
      "The PIN-crosswalk join methodology (facility PIN -> modal district -> NFHS).", intent="data_retrieval")
    Q("Brief me on a district",
      "District profile: burden indicators + dataset facility coverage + trust caveat.", intent="district_briefing")
    Q("Build a data story / infographic on India's medical deserts",
      "Produce the 'Care Lottery' scrollytelling/infographic spine (burden choropleth -> deserts -> lottery -> supply-vs-need -> trust -> close).", intent="deliverable_story")
    Q("Build a deck on the medical desert findings",
      "Produce a PPTX deck from the verified desert findings.", intent="deliverable_deck")
    Q("Map facility supply against district health burden",
      "Supply points (dot layer) over a demand choropleth + the supply-vs-need bubble.", intent="deliverable_map")

    # ============================================================ NEW DESIGN RULES (map/health editorial + story craft)
    # DAV-mined (geographic / health-story specific; complement the kept 138 generic DesignRules)
    D("Choropleth shows rates, not totals", "On a district map fill polygons with a RATE/PREVALENCE (e.g. % child anaemia), never a raw count or facility count — a count choropleth mostly visualises the size of the geographic unit. Use proportional symbols for any magnitude. [[choropleth-map]]")
    D("Sequential ramp for burden; diverging only at a real midpoint", "Use a single-hue SEQUENTIAL ramp for an ordered burden measure (lightness is perceptually ordered); reserve a two-hue DIVERGING ramp for measures that cross a meaningful midpoint (need-vs-supply z-score around 0). Never rainbow. [[colour-encoding]]")
    D("Facility points are a dot/proportional-symbol layer, not a fill", "Render the ~10k facilities as a POINT layer over the demand choropleth, visually distinct from the fill underneath — never conflate supply count with demand shading. [[choropleth-map]] Spatial tab")
    D("MAUP & ecological fallacy at the district grain", "Aggregating to district is a Modifiable-Areal-Unit choice: a pattern can weaken or reverse at a finer grain, and a district average does NOT describe any individual within it. State every claim as 'this district, at this grain'. [[simpsons-paradox]] [[confounding]]")
    D("Always show the denominator", "Never map or rank a facility count or a burden alone — pair it with its base geography and survey size. The 3 tables carry NO population, so frame supply as count-vs-burden, with NFHS women_15_49_interviewed only as a caveated survey-size proxy. [[choropleth-map]]")
    D("Render suppressed and estimated cells honestly", "NFHS '*' suppressed cells render as an explicit DISTINCT category (hatched 'data suppressed'), never as 0 or the lightest ramp colour; flag parenthesized '(x.x)' estimates (25-49 cases) as low-reliability. [[confidence-interval]]")
    D("Sample, not census — label coverage", "The facilities table is a ~10k SAMPLE (India has 47k+ in the FDR), so a low count is DATASET COVERAGE, not absolute scarcity. Label every desert/gap claim 'in-dataset coverage' and answer 'who is NOT in this sample?'. [[sampling-bias]]")
    D("Volume-filter rate maps to kill small-sample extremes", "A district can show an extreme burden or perfect ratio purely on a tiny sample; pair any rate map or ranked bar with a minimum-volume filter or annotate n. [[choropleth-map]] [[confidence-interval]]")
    D("Small multiples for many indicators on a shared scale", "With 100+ NFHS indicators, use small multiples / a Trellis of identically-scaled mini-maps or ranked bars (same colour breaks, same axis across panels), never one multi-hue map. [[no-unjustified-3d]] [[sensible-scales]]")
    D("Pair a burden choropleth with a companion ranked bar", "Colour saturation is rank 5/5 in the Cleveland-McGill hierarchy — readers can't decode precise values from a shade — so always pair the map (WHERE) with a ranked bar of the worst districts (HOW MUCH, position/length). [[cleveland-mcgill-encoding-hierarchy]]")
    D("State the choropleth class-binning and show breakpoints", "Class breaks change the story: quantile bins even out counts but hide magnitude; equal-interval preserves magnitude but can empty bins under skew. State which binning you used, show breakpoints in the legend, keep the same breaks across small multiples. [[sensible-scales]]")
    D("Supply-vs-need bubble needs a reference line", "On the need-vs-coverage bubble (x=burden, y=coverage) add the expected/diagonal reference line and label the high-need-low-coverage quadrant as the 'medical desert' region — the eye reads position-to-a-reference far better than a bare cloud. [[scatter-plot]]")
    D("Hunt confounders before calling a district a desert", "A low in-dataset count can be driven by data-collection coverage, urban/rural split, or private/public mix rather than true absence of care — name the lurking variable and scope the claim. [[confounding]] [[spurious-correlation]]")
    # Story-craft (from the adapted spine)
    D("Human-anchor device — carry one district through the story", "Carry ONE real district as the human anchor — Sukma, Chhattisgarh (~91% children anaemic, ZERO dataset facilities) — open on it, return to it in the desert/lottery/closing scenes, contrast against Chennai (55%, 272 facilities). The reader follows a place, not a table.")
    D("Lead the bubble scene with the expectation, then break it", "The analytical payload is the reversal: you'd expect facilities to follow burden, but they don't (rho ~ -0.2; high-burden districts average fewer facilities). State the expectation first, then break it; claim 'mismatch between need and coverage', never 'discrimination'.")
    D("Split 'claimed' vs 'proven' in the trust scene", "Visually split what facilities CLAIM (specialties/equipment ~99%) from what's PROVEN (doctors 36%, capacity 25%) so a planner never sends a patient on an unverified claim; cite the source TEXT field for any specific facility claim.")

    # ============================================================ CROSS-LAYER EDGES
    # Metric <- computed from tables / measured by SQL
    metric_table = {
        "facilities_total": [T_FAC], "private_share": [T_FAC], "facility_geocoding_rate": [T_FAC],
        "facility_supply_concentration": [T_FAC], "facility_trust_score": [T_FAC], "unverifiable_claim_rate": [T_FAC],
        "health_burden_index": [T_NFHS], "women_anaemia_rate": [T_NFHS], "child_stunting_rate": [T_NFHS],
        "institutional_birth_rate": [T_NFHS], "full_immunization_rate": [T_NFHS], "health_insurance_coverage": [T_NFHS],
        "facilities_per_district": [T_FAC, T_PIN, T_NFHS], "desert_score": [T_NFHS, T_FAC],
        "burden_supply_correlation": [T_NFHS, T_FAC],
    }
    for m, tbls in metric_table.items():
        for t in tbls:
            E("COMPUTED_FROM", "Metric", m, "Table", t)

    # SqlPattern -> ROUTES_TO Genie, QUERIES tables, HONORS rules, COMPUTES metric, VISUALIZED_BY recipe, ANSWERS question
    def wire_sql(sql, tables, rules, metric=None, charts=(), question=None):
        E("ROUTES_TO", "SqlPattern", sql, "GenieSpace", GENIE)
        for t in tables: E("QUERIES", "SqlPattern", sql, "Table", t)
        for r in rules: E("HONORS", "SqlPattern", sql, "Rule", r)
        if metric: E("COMPUTES", "SqlPattern", sql, "Metric", metric)
        for c in charts: E("VISUALIZED_BY", "SqlPattern", sql, "ChartRecipe", c)
        if question: E("ANSWERS", "SqlPattern", sql, "Question", question)

    wire_sql("facilities-clean-india-count", [T_FAC], ["R-india-filter", "R-coverage-not-census"],
             "facilities_total", ["stat", "count_up"], "What kinds of facilities are in the dataset and who runs them?")
    wire_sql("facility-composition-by-type-operator", [T_FAC], ["R-operatortype-null-string", "R-drop-constant-orgtype"],
             "private_share", ["ranked_bar", "kpi_grid"], "What kinds of facilities are in the dataset and who runs them?")
    wire_sql("facility-supply-concentration-by-state", [T_FAC], ["R-normalize-state", "R-coverage-not-census"],
             "facility_supply_concentration", ["ranked_bar_highlight", "lorenz_gini", "choropleth"], "How concentrated is facility coverage?")
    wire_sql("nfhs-burden-cast-preamble", [T_NFHS], ["R-nfhs-cast", "R-nfhs-suppressed-star", "R-nfhs-parenthesized-estimate"],
             None, [], "What must be fixed before I can trust this data?")
    wire_sql("nfhs-worst-burden-districts", [T_NFHS], ["R-nfhs-cast", "R-hbi-relative-percentile", "R-demand-not-supply"],
             "health_burden_index", ["ranked_bar_highlight", "choropleth"], "Which districts have the highest health burden?")
    wire_sql("nfhs-state-burden-rollup", [T_NFHS], ["R-district-state-collision", "R-nfhs-cast"],
             "health_burden_index", ["ranked_bar", "choropleth"], "Which states have the best and worst health outcomes?")
    wire_sql("care-lottery-spread", [T_NFHS], ["R-nfhs-cast", "R-nfhs-suppressed-star"],
             "health_insurance_coverage", ["dumbbell", "stat"], "How unequal is healthcare access across India?")
    wire_sql("facility-to-district-join", [T_FAC, T_PIN, T_NFHS], ["R-pin-fanout-dedup", "R-district-name-normalization", "R-district-state-collision"],
             "facilities_per_district", ["kpi_grid"], "How do facilities map to districts?")
    wire_sql("zero-facility-districts", [T_FAC, T_NFHS], ["R-coverage-not-census", "R-district-name-normalization"],
             "facilities_per_district", ["stat", "count_up", "choropleth"], "Which districts have zero facilities in the dataset?")
    wire_sql("desert-score-ranking", [T_NFHS, T_FAC], ["R-coverage-not-census", "R-demand-not-supply"],
             "desert_score", ["ranked_bar_highlight", "dumbbell"], "Where are India's medical deserts (high need, low coverage)?")
    wire_sql("burden-supply-correlation", [T_NFHS, T_FAC], ["R-coverage-not-census", "R-demand-not-supply"],
             "burden_supply_correlation", ["bubble_scatter", "forest_ci"], "Does facility supply follow health need across India?")
    wire_sql("coverage-concentration-gini", [T_FAC, T_NFHS], ["R-coverage-not-census"],
             "facility_supply_concentration", ["lorenz_gini", "ranked_bar_highlight"], "How concentrated is facility coverage?")
    wire_sql("facility-trust-score", [T_FAC], ["R-string-null-sentinel", "R-cast-facility-numeric", "R-claims-self-reported"],
             "facility_trust_score", ["kpi_grid", "ranked_bar"], "Can I trust this facility's claims?")
    wire_sql("unverifiable-advanced-claims", [T_FAC], ["R-claims-self-reported", "R-string-null-sentinel"],
             "unverifiable_claim_rate", ["stat", "iceberg"], "Which facilities claim advanced care they can't back up?")

    # Rules -> GOTCHA_FOR / APPLIES_TO
    fac_rules = ["R-facility-dedup", "R-india-filter", "R-string-null-sentinel", "R-cast-facility-numeric", "R-normalize-state",
                 "R-operatortype-null-string", "R-drop-constant-orgtype", "R-claims-self-reported", "R-recency-date-caveat"]
    E("APPLIES_TO", "Rule", "R-facility-dedup", "Column", f"{T_FAC}.unique_id")
    nfhs_rules = ["R-nfhs-cast", "R-nfhs-suppressed-star", "R-nfhs-parenthesized-estimate", "R-nfhs5-vintage",
                  "R-hbi-relative-percentile", "R-demand-not-supply"]
    pin_rules = ["R-pin-fanout-dedup", "R-district-name-normalization", "R-district-state-collision"]
    for r in fac_rules: E("GOTCHA_FOR", "Rule", r, "Table", T_FAC)
    for r in nfhs_rules: E("GOTCHA_FOR", "Rule", r, "Table", T_NFHS)
    for r in pin_rules: E("GOTCHA_FOR", "Rule", r, "Table", T_PIN)
    E("GOTCHA_FOR", "Rule", "R-coverage-not-census", "Domain", DOMAIN)
    E("APPLIES_TO", "Rule", "R-coverage-not-census", "Domain", DOMAIN)

    # Findings -> ABOUT metric/domain, DERIVED_FROM sql, VISUALIZED_BY recipe
    def wire_finding(f, about, sql, charts):
        for a_type, a_name in about: E("ABOUT", "Finding", f, a_type, a_name)
        for s in sql: E("DERIVED_FROM", "Finding", f, "SqlPattern", s)
        for c in charts: E("VISUALIZED_BY", "Finding", f, "ChartRecipe", c)

    wire_finding("the-care-lottery", [("Metric", "health_insurance_coverage"), ("Domain", DOMAIN)],
                 ["care-lottery-spread"], ["dumbbell", "stat"])
    wire_finding("medical-deserts-zero-coverage", [("Metric", "facilities_per_district"), ("Domain", DOMAIN)],
                 ["zero-facility-districts"], ["choropleth", "ranked_bar_highlight", "stat"])
    wire_finding("supply-does-not-follow-need", [("Metric", "burden_supply_correlation")],
                 ["burden-supply-correlation"], ["bubble_scatter"])
    wire_finding("top-desert-districts-bihar-jharkhand", [("Metric", "desert_score")],
                 ["desert-score-ranking"], ["ranked_bar_highlight", "dumbbell"])
    wire_finding("the-burden-belt", [("Metric", "health_burden_index")],
                 ["nfhs-worst-burden-districts", "nfhs-state-burden-rollup"], ["choropleth", "ranked_bar_highlight"])
    wire_finding("the-southern-advantage", [("Metric", "health_burden_index")],
                 ["nfhs-worst-burden-districts"], ["choropleth", "ranked_bar_highlight"])
    wire_finding("women-anaemia-majority", [("Metric", "women_anaemia_rate")],
                 ["nfhs-worst-burden-districts"], ["stat", "choropleth"])
    wire_finding("child-malnutrition-stunting", [("Metric", "child_stunting_rate")],
                 ["nfhs-worst-burden-districts"], ["stat", "ranked_bar"])
    wire_finding("private-skew-public-gap", [("Metric", "private_share")],
                 ["facility-composition-by-type-operator"], ["ranked_bar", "kpi_grid"])
    wire_finding("supply-concentration", [("Metric", "facility_supply_concentration")],
                 ["facility-supply-concentration-by-state", "coverage-concentration-gini"], ["lorenz_gini", "ranked_bar_highlight"])
    wire_finding("claims-rich-proof-thin", [("Metric", "facility_trust_score")],
                 ["facility-trust-score"], ["dumbbell", "ranked_bar"])
    wire_finding("unverifiable-advanced-claims", [("Metric", "unverifiable_claim_rate")],
                 ["unverifiable-advanced-claims"], ["stat", "iceberg"])
    wire_finding("the-data-readiness-tax", [("Domain", DOMAIN)],
                 ["nfhs-burden-cast-preamble", "facility-to-district-join"], ["kpi_grid", "stat"])
    wire_finding("geocoding-ready-to-map", [("Metric", "facility_geocoding_rate")],
                 ["facilities-clean-india-count"], ["stat", "kpi_grid"])

    # Questions -> SURFACES finding, ROUTES_TO genie, PRODUCED_BY tool (deliverables)
    q_finding = {
        "Where are India's medical deserts (high need, low coverage)?": "top-desert-districts-bihar-jharkhand",
        "Which districts have zero facilities in the dataset?": "medical-deserts-zero-coverage",
        "Does facility supply follow health need across India?": "supply-does-not-follow-need",
        "Which districts have the highest health burden?": "the-burden-belt",
        "Which states have the best and worst health outcomes?": "the-southern-advantage",
        "How unequal is healthcare access across India?": "the-care-lottery",
        "Where is anaemia / child malnutrition worst?": "women-anaemia-majority",
        "Can I trust this facility's claims?": "claims-rich-proof-thin",
        "Which facilities claim advanced care they can't back up?": "unverifiable-advanced-claims",
        "How concentrated is facility coverage?": "supply-concentration",
        "What kinds of facilities are in the dataset and who runs them?": "private-skew-public-gap",
        "What must be fixed before I can trust this data?": "the-data-readiness-tax",
    }
    for q, f in q_finding.items():
        E("SURFACES", "Question", q, "Finding", f)
        E("ROUTES_TO", "Question", q, "GenieSpace", GENIE)
    # data-retrieval / briefing questions route to Genie
    for q in ["How do facilities map to districts?", "Brief me on a district",
              "Map facility supply against district health burden"]:
        E("ROUTES_TO", "Question", q, "GenieSpace", GENIE)
    # deliverable questions -> the production tools
    E("PRODUCED_BY", "Question", "Build a data story / infographic on India's medical deserts", "Tool", "compose_story")
    E("PRODUCED_BY", "Question", "Build a data story / infographic on India's medical deserts", "Tool", "compose_infographic")
    E("PRODUCED_BY", "Question", "Build a deck on the medical desert findings", "Tool", "compose_deck")
    E("PRODUCED_BY", "Question", "Map facility supply against district health burden", "Tool", "render_chart")
    E("SURFACES", "Question", "Build a data story / infographic on India's medical deserts", "Finding", "the-care-lottery")
    E("SURFACES", "Question", "Build a deck on the medical desert findings", "Finding", "medical-deserts-zero-coverage")

    # New DesignRules -> STYLED_BY from the recipes they govern + APPLIES_TO domain/charttype
    E("STYLED_BY", "ChartRecipe", "choropleth", "DesignRule", "Choropleth shows rates, not totals")
    E("STYLED_BY", "ChartRecipe", "choropleth", "DesignRule", "Sequential ramp for burden; diverging only at a real midpoint")
    E("STYLED_BY", "ChartRecipe", "choropleth", "DesignRule", "Render suppressed and estimated cells honestly")
    E("STYLED_BY", "ChartRecipe", "choropleth", "DesignRule", "Pair a burden choropleth with a companion ranked bar")
    E("STYLED_BY", "ChartRecipe", "choropleth", "DesignRule", "State the choropleth class-binning and show breakpoints")
    E("STYLED_BY", "ChartRecipe", "bubble_scatter", "DesignRule", "Supply-vs-need bubble needs a reference line")
    E("STYLED_BY", "ChartRecipe", "bubble_scatter", "DesignRule", "Lead the bubble scene with the expectation, then break it")
    E("APPLIES_TO", "DesignRule", "Always show the denominator", "Domain", DOMAIN)
    E("APPLIES_TO", "DesignRule", "Sample, not census — label coverage", "Domain", DOMAIN)
    E("APPLIES_TO", "DesignRule", "MAUP & ecological fallacy at the district grain", "Domain", DOMAIN)
    E("APPLIES_TO", "DesignRule", "Hunt confounders before calling a district a desert", "Domain", DOMAIN)
    E("APPLIES_TO", "DesignRule", "Choropleth shows rates, not totals", "ChartType", "choropleth")
    E("APPLIES_TO", "DesignRule", "Facility points are a dot/proportional-symbol layer, not a fill", "ChartType", "choropleth")
