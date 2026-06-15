# Databricks notebook source
# MAGIC %md
# MAGIC # Load World Bank reference tables (host_population, host_gdp)
# MAGIC
# MAGIC One-time loader for the two **external reference tables** the per-capita
# MAGIC burden and GDP-vs-burden data-stories need. The 8 UNHCR tables carry no
# MAGIC host-country population or GDP, so these World Bank references (CC BY 4.0,
# MAGIC ISO3-keyed) are joined on `iso`. See the population domain skill,
# MAGIC `business_context.md` -> "External reference tables (R16)".
# MAGIC
# MAGIC **Run this once in the hackathon workspace** (Free Edition, `workspace.hackathon`).
# MAGIC It is idempotent: `CREATE OR REPLACE TABLE`.
# MAGIC
# MAGIC Source: World Bank `SP.POP.TOTL` (population) + `NY.GDP.PCAP.CD` (GDP/capita).
# MAGIC The bundled CSVs at `deployment/ref/` are the snapshot pulled by
# MAGIC `hackathon/notes/story/ref/build_host_*.py`. Latest-available-year per country.

# COMMAND ----------

import os
from pathlib import Path

import pandas as pd

# Resolve the bundled-CSV directory. Default assumes this notebook was deployed to
# /Workspace/Users/<you>/hackathon/orchestrator/deployment/ (deploy.sh rsyncs it).
# Override with the REF_DIR widget if you put the CSVs on a Volume instead.
dbutils.widgets.text("REF_DIR", "", "Directory holding host_population.csv + host_gdp.csv (blank = colocated ./ref)")
dbutils.widgets.text("CATALOG", "workspace", "Target catalog")
dbutils.widgets.text("SCHEMA", "hackathon", "Target schema")

_ref_dir = dbutils.widgets.get("REF_DIR").strip()
CATALOG = dbutils.widgets.get("CATALOG").strip() or "workspace"
SCHEMA = dbutils.widgets.get("SCHEMA").strip() or "hackathon"

if not _ref_dir:
    # Co-located ./ref next to this notebook. In a Databricks notebook __file__ is
    # undefined, so fall back to the conventional deployed path.
    try:
        _here = Path(__file__).resolve().parent  # works when run as a module/script
    except NameError:
        _user = (
            spark.sql("SELECT current_user() AS u").collect()[0]["u"]  # noqa: F821
        )
        _here = Path(f"/Workspace/Users/{_user}/hackathon/orchestrator/deployment")
    _ref_dir = str(_here / "ref")

print(f"[load_reference_tables] ref_dir={_ref_dir}  target={CATALOG}.{SCHEMA}")

# COMMAND ----------

# host_population — World Bank SP.POP.TOTL. CSV cols: iso3,country,population,pop_year,source
pop_pd = pd.read_csv(os.path.join(_ref_dir, "host_population.csv"))
pop_pd = pop_pd.rename(columns={"iso3": "iso"})
pop_pd["population"] = pd.to_numeric(pop_pd["population"], errors="coerce").astype("Int64")
pop_pd["pop_year"] = pd.to_numeric(pop_pd["pop_year"], errors="coerce").astype("Int64")

pop_sdf = spark.createDataFrame(pop_pd[["iso", "country", "population", "pop_year", "source"]])  # noqa: F821
(
    pop_sdf.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{SCHEMA}.host_population")
)
print(f"  wrote {CATALOG}.{SCHEMA}.host_population: {pop_sdf.count()} rows")

# COMMAND ----------

# host_gdp — World Bank NY.GDP.PCAP.CD. CSV cols: iso3,country,gdp_pc_usd,gdp_year,source
gdp_pd = pd.read_csv(os.path.join(_ref_dir, "host_gdp.csv"))
gdp_pd = gdp_pd.rename(columns={"iso3": "iso"})
gdp_pd["gdp_pc_usd"] = pd.to_numeric(gdp_pd["gdp_pc_usd"], errors="coerce")
gdp_pd["gdp_year"] = pd.to_numeric(gdp_pd["gdp_year"], errors="coerce").astype("Int64")

gdp_sdf = spark.createDataFrame(gdp_pd[["iso", "country", "gdp_pc_usd", "gdp_year", "source"]])  # noqa: F821
(
    gdp_sdf.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.{SCHEMA}.host_gdp")
)
print(f"  wrote {CATALOG}.{SCHEMA}.host_gdp: {gdp_sdf.count()} rows")

# COMMAND ----------

# MAGIC %md ### Verify — a sample per-capita burden join (Lebanon should top the list)

# COMMAND ----------

# Best-effort sanity check. Needs the UNHCR `population` + `countries` tables to
# already exist; if they don't yet, the two reference tables above are still loaded
# fine, so warn instead of failing the job.
try:
    spark.sql(  # noqa: F821
        f"""
        WITH hosted AS (
          SELECT coa_iso, SUM(refugees) AS hosted
          FROM {CATALOG}.{SCHEMA}.population
          WHERE year = 2024 AND coo_iso <> coa_iso
            AND coa_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
          GROUP BY coa_iso
        )
        SELECT c.name AS host, h.hosted, r.population, r.pop_year,
               ROUND(h.hosted * 1000.0 / NULLIF(r.population, 0), 1) AS refugees_per_1000
        FROM hosted h
        JOIN {CATALOG}.{SCHEMA}.host_population r ON r.iso = h.coa_iso
        JOIN {CATALOG}.{SCHEMA}.countries c       ON c.iso = h.coa_iso
        WHERE h.hosted >= 10000
        ORDER BY refugees_per_1000 DESC
        LIMIT 10
        """
    ).show(truncate=False)
except Exception as e:  # noqa: BLE001
    print(
        f"[verify] skipped sample join ({type(e).__name__}: {e}). "
        "Reference tables host_population + host_gdp were still written."
    )

# COMMAND ----------

try:
    dbutils.notebook.exit("host_population + host_gdp loaded OK")
except Exception:
    print("DONE: host_population + host_gdp loaded OK")
