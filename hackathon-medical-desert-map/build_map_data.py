#!/usr/bin/env python3
"""
Build the self-contained "Medical Desert Planner — India" D3 map.

Reads our verified gap-analysis district tables + facility table (gitignored
session archive) and the DataMeet india_districts.geojson (CC-BY 2.5, lifted
from teammate Nikita's india-health-map), joins them, simplifies the geometry,
computes the national stat callouts + priority-desert ranking, and injects
everything into template.html -> india_medical_deserts.html (offline, single file).

Run:  python3 build_map_data.py
"""
import json, re, os, math, difflib
import pandas as pd
import numpy as np
from shapely.geometry import shape, mapping, Point
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
OUT  = os.path.join(REPO, "hackathon-session-2026-06-15", "gap_analysis", "out")
NIK  = "/tmp/nikita-hackathon"                      # teammate clone (for OHE specialties)
GEO  = os.path.join(HERE, "assets", "india_districts.geojson")
D3   = os.path.join(HERE, "assets", "d3.v7.min.js")
TPL  = os.path.join(HERE, "template.html")
DST  = os.path.join(HERE, "india_medical_deserts.html")

# ---------------------------------------------------------------- name joins
def norm(v):
    return re.sub(r'[^a-z0-9]+', '', str(v or '').strip().lower().replace('&', 'and'))

STATE_ALIAS = {
    'andamanandnicobarisland': 'andamanandnicobarislands',
    'arunanchalpradesh': 'arunachalpradesh',
    'dadaraandnagarhavelli': 'dadranagarhavelidamananddiu',
    'damananddiu': 'dadranagarhavelidamananddiu',
    'dadranagarhaveli': 'dadranagarhavelidamananddiu',
    'maharastra': 'maharashtra', 'orissa': 'odisha', 'pondicherry': 'puducherry',
    'uttaranchal': 'uttarakhand', 'jammuandkashmir': 'jammukashmir',
    'nctofdelhi': 'delhi', 'telengana': 'telangana',
}
# geojson(DISTRICT-norm) -> our NFHS district-norm. Verified against the NFHS-5
# district list per state; handles 2011-vs-NFHS spelling/truncation differences.
DIST_ALIAS = {
    'barddhaman': 'paschimbarddhaman', 'bauda': 'baudh', 'chamrajnagar': 'chamarajanagar',
    'dakshinbastardantewada': 'dantewada', 'eastnimar': 'khandwaeastnimar',
    'westnimar': 'khargonewestnimar', 'garhchiroli': 'gadchiroli', 'marigaon': 'morigaon',
    'virudunagar': 'virudhunagar', 'nagappattinam': 'nagapattinam',
    'pashchimmedinipur': 'paschimmedinipur', 'sripottisriramulunellore': 'sripottisriramulunello',
    'saranchhapra': 'saran', 'maharajganj': 'mahrajganj', 'kansiramnagar': 'kanshiramnagar',
    'north24parganas': 'northtwentyfourpargana', 'south24parganas': 'southtwentyfourpargana',
    'nicobar': 'nicobars', 'lawangtlai': 'lawngtlai',
}
def nstate(v):
    k = norm(v); return STATE_ALIAS.get(k, k)
def ndist(v, alias=False):
    k = norm(v); return DIST_ALIAS.get(k, k) if alias else k

# ---------------------------------------------------------------- district data
key = ["district_norm", "state_canon"]
dm = pd.read_parquet(f"{OUT}/district_master.parquet")
ri = pd.read_parquet(f"{OUT}/district_risk_index.parquet")
sd = pd.read_parquet(f"{OUT}/spatial_desert_districts.parquet")
cl = pd.read_parquet(f"{OUT}/gapD_district_clusters.parquet")

df = dm.merge(ri[key + ["RISK_INDEX","NEED","COVERAGE_GAP","EVIDENCE_GAP","DESERT_SCORE",
                        "rank_risk","MAT_NEED","high_mat_need","CONFIDENCE"]], on=key, how="left")
df = df.merge(sd[key + ["n_fac_spatial","nearest_fac_km","is_zero_text","is_true_spatial_desert"]],
              on=key, how="left")
df = df.merge(cl[key + ["cluster"]], on=key, how="left")

CLUSTER_LABEL = {  # from gapD_cluster_profiles — planner personas
    0: "Urban / well-served",
    1: "Mixed access",
    2: "Rural underserved",
    3: "High-burden rural desert",
}

def num(x):
    if x is None: return None
    try:
        f = float(x)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 2)
    except (TypeError, ValueError):
        return None

records = {}
for _, r in df.iterrows():
    k = (nstate(r["state_ut"]), norm(r["district_name"]))
    records[k] = {
        "district": r["district_name"], "state": r["state_ut"], "region": r.get("region"),
        "HBI": num(r["HBI"]), "RISK": num(r["RISK_INDEX"]), "NEED": num(r["NEED"]),
        "COVGAP": num(r["COVERAGE_GAP"]), "DESERT": num(r["DESERT_SCORE"]),
        "MATNEED": num(r["MAT_NEED"]), "rank": int(r["rank_risk"]) if pd.notna(r["rank_risk"]) else None,
        "nfac": int(r["n_facilities"]) if pd.notna(r["n_facilities"]) else 0,
        "nearkm": num(r["nearest_fac_km"]),
        "zero": bool(r["is_zero_text"]) if pd.notna(r["is_zero_text"]) else None,
        "spdesert": bool(r["is_true_spatial_desert"]) if pd.notna(r["is_true_spatial_desert"]) else None,
        "himatneed": bool(r["high_mat_need"]) if pd.notna(r["high_mat_need"]) else None,
        "conf": r["CONFIDENCE"] if isinstance(r["CONFIDENCE"], str) else None,
        "cluster": int(r["cluster"]) if pd.notna(r["cluster"]) else None,
        "anaemia": num(r["women_anaemia"]), "instbirth": num(r["institutional_birth"]),
        "cleanfuel": num(r["clean_fuel"]), "anc4": num(r["anc4"]),
        "_sw": float(r["survey_women"]) if pd.notna(r["survey_women"]) else 1.0,
        "_lat": num(r["pin_centroid_lat"]), "_lon": num(r["pin_centroid_lon"]),
    }
print(f"district records: {len(records)}")

DISPLAY = ["district","state","region","HBI","RISK","NEED","COVGAP","DESERT","MATNEED",
           "rank","nfac","nearkm","zero","spdesert","himatneed","conf","cluster",
           "anaemia","instbirth","cleanfuel","anc4"]
MEAN_KEYS = ["HBI","RISK","NEED","COVGAP","DESERT","MATNEED","nearkm","anaemia","instbirth","cleanfuel","anc4"]

# ---------------------------------------------------------------- geojson join (resolver)
# Boundaries are DataMeet Census-2011; NFHS-5 uses ~2019 districts. Resolve each
# polygon to NFHS data via: exact+alias -> fuzzy-within-state -> district-only ->
# spatial (post-2011 split children located by pincode centroid -> 2011 parent,
# survey-women-weighted aggregate). Residual greys are honest (no NFHS counterpart).
gj = json.load(open(GEO))
feats = gj["features"]
geoms = [shape(f["geometry"]).buffer(0) for f in feats]
tree = STRtree(geoms)
bystate = {}
for (s, d) in records:
    bystate.setdefault(s, {})[d] = (s, d)

resolved = {}                                          # feature idx -> [record keys]
how = {"exact": 0, "fuzzy": 0, "distonly": 0, "spatial": 0, "grey": 0}
pending = []
for i, f in enumerate(feats):
    p = f["properties"]; ks = nstate(p.get("ST_NM")); kd = ndist(p.get("DISTRICT"), alias=True)
    if (ks, kd) in records:
        resolved[i] = [(ks, kd)]; how["exact"] += 1; continue
    m = difflib.get_close_matches(kd, list(bystate.get(ks, {}).keys()), n=1, cutoff=0.86)
    if m:
        resolved[i] = [bystate[ks][m[0]]]; how["fuzzy"] += 1; continue
    do = [k for k in records if k[1] == kd]
    if len(do) == 1:
        resolved[i] = [do[0]]; how["distonly"] += 1; continue
    pending.append(i)

matched_keys = {k for ks in resolved.values() for k in ks}
gset = set(pending)
for k, rec in records.items():
    if k in matched_keys or rec["_lat"] is None or rec["_lon"] is None:
        continue
    pt = Point(rec["_lon"], rec["_lat"])
    idx = [j for j in tree.query(pt) if j in gset and geoms[j].contains(pt)]
    if idx:
        resolved.setdefault(idx[0], []).append(k)
for i in pending:
    how["spatial" if resolved.get(i) else "grey"] += 1

def rnd(c):                                            # round coords to ~110 m
    if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
        return [round(c[0], 3), round(c[1], 3)]
    return [rnd(x) for x in c]

def build_props(keys):
    rs = [records[k] for k in keys]
    if len(rs) == 1:
        return {k2: rs[0][k2] for k2 in DISPLAY}
    w = [max(r["_sw"] or 1.0, 1.0) for r in rs]        # survey-women-weighted aggregate
    def wmean(mk):
        nu = de = 0.0
        for r, wi in zip(rs, w):
            if r[mk] is not None: nu += r[mk] * wi; de += wi
        return round(nu / de, 2) if de else None
    big = max(rs, key=lambda r: r["_sw"] or 1.0)
    ranks = [r["rank"] for r in rs if r["rank"] is not None]
    pr = {mk: wmean(mk) for mk in MEAN_KEYS}
    pr.update({
        "district": None, "state": big["state"], "region": big["region"],
        "nfac": sum(r["nfac"] for r in rs), "zero": all(r["nfac"] == 0 for r in rs),
        "spdesert": any(bool(r["spdesert"]) for r in rs),
        "himatneed": any(bool(r["himatneed"]) for r in rs),
        "rank": min(ranks) if ranks else None, "conf": big["conf"], "cluster": big["cluster"],
        "agg": [r["district"] for r in rs],
    })
    return pr

out_feats = []
for i, f in enumerate(feats):
    geom = geoms[i].simplify(0.012, preserve_topology=True)
    if geom.is_empty: continue
    gm = mapping(geom)
    props = {"DISTRICT": f["properties"].get("DISTRICT"), "ST_NM": f["properties"].get("ST_NM")}
    keys = resolved.get(i)
    if keys:
        pr = build_props(keys)
        if pr.get("district") is None: pr["district"] = f["properties"].get("DISTRICT")
        props.update(pr)
    out_feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": gm["type"], "coordinates": rnd(gm["coordinates"])}})
geojson_min = {"type": "FeatureCollection", "features": out_feats}
painted = sum(1 for f in out_feats if "district" in f["properties"])
print(f"geojson features kept: {len(out_feats)}  painted: {painted} "
      f"({painted/len(out_feats)*100:.1f}%)  resolution={how}")

# ---------------------------------------------------------------- facility points + specialties
fc = pd.read_parquet(f"{OUT}/facilities_clean.parquet")
fc = fc[fc["latitude"].notna() & fc["longitude"].notna()].copy()
# clip to India bbox (drop the handful of corrupt coords)
fc = fc[(fc["latitude"].between(6, 37.6)) & (fc["longitude"].between(67.5, 97.5))]

# curated specialty list (OHE column -> display label); combine a few
SPECS = [
    ("General Surgery",        ["generalsurgery"]),
    ("Obstetrics & Gynae",     ["obstetrics","gynecology","maternitycare","maternalfetalmedicineorperinatology"]),
    ("Paediatrics",            ["pediatrics","neonatologyperinatalmedicine","pediatricsurgery","pediatriccardiology"]),
    ("Cardiology",             ["cardiology","cardiacsurgery"]),
    ("Oncology",               ["medicaloncology","surgicaloncology"]),
    ("Ophthalmology",          ["ophthalmology","cataract","retina","glaucomaophthalmology"]),
    ("Orthopaedics",           ["orthopedicsurgery"]),
    ("Radiology / Imaging",    ["radiology","interventionalradiology","nuclearmedicine"]),
    ("Neurology / Neurosurg.", ["neurology","neurosurgery"]),
    ("Nephrology",             ["nephrology"]),
    ("Urology",                ["urology","endourology"]),
    ("Gastroenterology",       ["gastroenterology"]),
    ("Pulmonology",            ["pulmonology"]),
    ("Dermatology",            ["dermatology"]),
    ("Psychiatry",             ["psychiatry"]),
    ("Emergency Medicine",     ["emergencymedicine"]),
    ("Anaesthesia / Crit.Care",["anesthesia","criticalcaremedicine"]),
    ("Pathology / Lab",        ["pathology","clinicalpathology"]),
    ("Dentistry",              ["dentistry","generaldentistry","orthodontics"]),
    ("Internal Medicine",      ["internalmedicine","generalmedicine"]),
]
SPEC_LABELS = [s[0] for s in SPECS]

# OHE specialties from Nikita's processed facilities.csv, keyed by unique_id
nik_path = os.path.join(NIK, "data", "processed", "facilities.csv")
spec_by_id = {}
if os.path.exists(nik_path):
    nf = pd.read_csv(nik_path)
    ohe_cols = {c.replace("OHE_", ""): c for c in nf.columns if c.startswith("OHE_")}
    col_for = []  # list of (spec_index, [csv columns present])
    for i, (_, raw) in enumerate(SPECS):
        cols = [ohe_cols[r] for r in raw if r in ohe_cols]
        col_for.append((i, cols))
    for _, row in nf.iterrows():
        idxs = [i for i, cols in col_for if any(row.get(c, 0) == 1 for c in cols)]
        if idxs:
            spec_by_id[row["unique_id"]] = idxs
    print(f"OHE specialties parsed for {len(spec_by_id)} facilities")
else:
    print("WARN: Nikita facilities.csv not found; specialty filter will be empty")

OP = {"public": 0, "private": 1}
facs = []
for _, r in fc.iterrows():
    op = OP.get(str(r.get("operator_type")).lower(), 2)
    trust = int(r["trust_score"]) if pd.notna(r.get("trust_score")) else None
    specs = spec_by_id.get(r["unique_id"], [])
    facs.append([round(float(r["latitude"]), 3), round(float(r["longitude"]), 3),
                 op, trust, specs])
print(f"facility points: {len(facs)}")

# ---------------------------------------------------------------- national stats
valid = [v for v in records.values() if v["HBI"] is not None]
zero_fac = sum(1 for v in records.values() if v["nfac"] == 0)
sp_desert = sum(1 for v in records.values() if v["spdesert"])
himat_zero = sum(1 for v in records.values() if v["himatneed"] and v["nfac"] == 0)
near_vals = sorted([v["nearkm"] for v in records.values() if v["nearkm"] is not None])
median_near = round(near_vals[len(near_vals)//2], 1) if near_vals else None

# state-level HBI extremes
sdf = df.groupby("state_canon")["HBI"].mean().sort_values(ascending=False)
worst_state, worst_hbi = sdf.index[0], round(sdf.iloc[0], 1)
best_state, best_hbi = sdf.index[-1], round(sdf.iloc[-1], 1)
# access "lottery": ratio of risk extremes among districts with data
risks = sorted([v["RISK"] for v in records.values() if v["RISK"]])
lottery = round(risks[-1] / max(risks[0], 0.5), 0) if risks else None

stats = {
    "n_districts": len(records), "n_facilities": len(facs),
    "zero_fac": zero_fac, "sp_desert": sp_desert, "himat_zero": himat_zero,
    "median_near": median_near, "worst_state": worst_state, "worst_hbi": worst_hbi,
    "best_state": best_state, "best_hbi": best_hbi,
}
print("stats:", stats)

# priority deserts (top risk)
top = sorted([v for v in records.values() if v["RISK"]], key=lambda v: -v["RISK"])[:30]
priority = [{"district": v["district"], "state": v["state"], "RISK": v["RISK"],
             "HBI": v["HBI"], "nfac": v["nfac"], "nearkm": v["nearkm"],
             "himatneed": v["himatneed"]} for v in top]

# ---------------------------------------------------------------- assemble
DATA = {
    "geo": geojson_min, "facs": facs, "specs": SPEC_LABELS,
    "stats": stats, "priority": priority, "clusters": CLUSTER_LABEL,
}
data_js = json.dumps(DATA, separators=(",", ":"), allow_nan=False)
d3_js = open(D3).read()
tpl = open(TPL).read()
html = tpl.replace("/*__D3__*/", d3_js).replace("/*__DATA__*/", "window.MD=" + data_js + ";")
open(DST, "w").write(html)
print(f"\nWROTE {DST}  ({len(html)/1e6:.2f} MB)")
