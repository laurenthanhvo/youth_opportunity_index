from __future__ import annotations

from pathlib import Path
import re
import numpy as np
import pandas as pd
import geopandas as gpd

def find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root (a parent directory containing /data).")

REPO_ROOT = find_repo_root(Path.cwd())
DATA_DIR = REPO_ROOT / "data"
RAW_DOMAINS = DATA_DIR / "rawdomains"

OUT_YOI_DIR = DATA_DIR / "processed" / "yoi"
OUT_BOUNDS_DIR = DATA_DIR / "processed" / "boundaries"
OUT_YOI_DIR.mkdir(parents=True, exist_ok=True)
OUT_BOUNDS_DIR.mkdir(parents=True, exist_ok=True)

print("Repo root:", REPO_ROOT)
print("RAW_DOMAINS:", RAW_DOMAINS)

def digits_only(x) -> str:
    return re.sub(r"\D", "", str(x))

def geoid11_from_any(x) -> str | None:
    """Extract 11-digit tract GEOID from GEO_ID / LocationName / etc."""
    if pd.isna(x):
        return None
    d = digits_only(x)
    if len(d) >= 11:
        return d[-11:]
    return None

def sd_geoid11_from_tract_like(x, county_fips="06073"):
    """
    Handles CalEnviroScreen 'Tract' values like:
      - 6073000100.0 (float)  -> 06073000100
      - 6073000100   (int)    -> 06073000100
      - already 11-digit      -> keep
    """
    if pd.isna(x):
        return None

    s = str(x).strip()

    # remove trailing ".0" if it came in as float
    if s.endswith(".0"):
        s = s[:-2]

    d = digits_only(s)

    # if 10 digits, pad to 11 (adds leading 0 for CA)
    if len(d) == 10:
        return d.zfill(11)

    # if 11 digits already, keep
    if len(d) == 11:
        return d

    # fallback: if it's tract-only, prefix SD county (rare)
    if 1 <= len(d) <= 6:
        tract6 = d.zfill(6)
        return county_fips + tract6

    return None

def sd_only(df: pd.DataFrame, geoid_col="tract_geoid") -> pd.DataFrame:
    df = df.dropna(subset=[geoid_col]).copy()
    df = df[df[geoid_col].astype(str).str.startswith("06073")].copy()
    return df

def safe_num(x):
    """Coerce Series OR DataFrame to numeric (DataFrame coerces column-wise)."""
    if isinstance(x, pd.DataFrame):
        return x.apply(pd.to_numeric, errors="coerce")
    return pd.to_numeric(x, errors="coerce")

def pct_rank_01(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average")

def normalize(s: pd.Series, higher_is_better: bool) -> pd.Series:
    r = pct_rank_01(s)
    return r if higher_is_better else (1.0 - r)

def find_latest_table_folder(domain_dir: Path, prefix: str) -> Path | None:
    """
    Finds newest folder like: PREFIX_YYYY-MM-DD...
    Example: ACSDT5Y2024.B25070_2026-03-11T051051/
    """
    if not domain_dir.exists():
        return None
    cands = [p for p in domain_dir.iterdir() if p.is_dir() and p.name.startswith(prefix + "_")]
    if not cands:
        return None
    # sort by folder name (timestamp suffix is sortable)
    return sorted(cands, key=lambda p: p.name)[-1]

def load_census_table(domain: str, prefix: str) -> pd.DataFrame | None:
    """
    Loads the *-Data.csv from a rawdomains/<domain>/<prefix_timestamp>/ folder.
    Adds tract_geoid.
    """
    domain_dir = RAW_DOMAINS / domain
    folder = find_latest_table_folder(domain_dir, prefix)
    if folder is None:
        return None
    data_csv = next(folder.glob("*-Data.csv"), None)
    if data_csv is None:
        return None

    df = pd.read_csv(data_csv)
    # find a GEO-like column
    geo_col = None
    for cand in ["tract_geoid", "GEOID", "GEO_ID", "geo_id", "LocationName", "locationname"]:
        if cand in df.columns:
            geo_col = cand
            break
    if geo_col is None:
        geo_col = df.columns[0]

    df["tract_geoid"] = df[geo_col].apply(geoid11_from_any)
    df = sd_only(df)
    return df

def load_places_latest() -> pd.DataFrame | None:
    """
    Loads PLACES tract CSV from rawdomains/health.
    Keeps latest year and SD county if possible.
    """
    health_dir = RAW_DOMAINS / "health"
    cands = sorted(health_dir.glob("PLACES__Local_Data_for_Better_Health*_release_*.csv"))
    if not cands:
        return None
    p = cands[-1]
    df = pd.read_csv(p)
        # Prefer a real tract id column over LocationName
    loc_col = None
    for cand in ["TractFIPS", "tractfips", "GEOID", "geoid", "GEO_ID", "geo_id", "LocationID", "locationid", "LocationName", "locationname"]:
        if cand in df.columns:
            loc_col = cand
            break
    if loc_col is None:
        return None

    if str(loc_col).lower() in {"tractfips", "locationid"}:
        df["tract_geoid"] = df[loc_col].apply(sd_geoid11_from_tract_like)
    else:
        df["tract_geoid"] = df[loc_col].apply(geoid11_from_any)

    # SD county filter if exists
    if "CountyFIPS" in df.columns:
        df["CountyFIPS"] = df["CountyFIPS"].astype(str).str.zfill(5)
        df = df[df["CountyFIPS"] == "06073"].copy()
    else:
        df = sd_only(df)

    # latest year
    if "Year" in df.columns:
        df["Year"] = safe_num(df["Year"])
        df = df[df["Year"] == df["Year"].max()].copy()

    # pivot measures
    meas_col = "MeasureId" if "MeasureId" in df.columns else ("measureid" if "measureid" in df.columns else None)
    val_col = "Data_Value" if "Data_Value" in df.columns else ("data_value" if "data_value" in df.columns else None)
    if meas_col is None or val_col is None:
        return None

    df[val_col] = safe_num(df[val_col])
    wide = df.pivot_table(index="tract_geoid", columns=meas_col, values=val_col, aggfunc="mean").reset_index()
    wide.columns = ["tract_geoid"] + [f"places_{c}" for c in wide.columns if c != "tract_geoid"]
    return wide

def tract_from_sandag_tract_value(x) -> str | None:
    """
    SANDAG portal 'Census Tract' often looks like 101.10 (county tract number).
    Convert to full GEOID: 06073 + (tract*100 as 6-digit).
    Example 101.10 -> 10110 -> '010110'?? (as 6 digits) -> '06073010110'
    """
    if pd.isna(x):
        return None
    s = str(x).strip()
    # if already looks like 06073xxxxx
    d = digits_only(s)
    if len(d) == 11 and d.startswith("06073"):
        return d
    try:
        v = float(s)
        code = int(round(v * 100))  # 101.10 -> 10110
        tract6 = str(code).zfill(6)
        return "06073" + tract6
    except Exception:
        return None

def load_cibrs_and_aggregate_latest_full_year() -> pd.DataFrame | None:
    """
    Loads CIBRS crime data and returns:
      tract_geoid, crime_incidents

    Supports either:
      1) detailed incident-level files with incident/date/tract columns, or
      2) pre-aggregated tract files with:
           Census Tract
           count_distinct_incidentuid
    """
    safety_dir = RAW_DOMAINS / "safety"

    cands = sorted(safety_dir.glob("CIBRS_Group_A_Detailed_Report_Data_*.csv"))
    if not cands:
        cands = sorted(safety_dir.glob("CIBRS_Group_A_Public_Crime_Data_*.csv"))
    if not cands:
        return None

    p = cands[-1]
    print("Using CIBRS:", p)

    head = pd.read_csv(p, nrows=0)
    cols = head.columns.tolist()
    lower_map = {c.lower().strip(): c for c in cols}

    def pick(*names):
        for n in names:
            hit = lower_map.get(n.lower().strip())
            if hit is not None:
                return hit
        return None

    # Case 1: pre-aggregated tract counts
    c_tr = pick("Census Tract", "census_tract", "tract", "tract_num")
    c_cnt = pick("count_distinct_incidentuid", "crime_incidents", "incident_count", "count")

    if c_tr is not None and c_cnt is not None:
        df = pd.read_csv(p, usecols=[c_tr, c_cnt]).copy()
        df["tract_geoid"] = df[c_tr].apply(tract_from_sandag_tract_value)
        df = sd_only(df)
        df["crime_incidents"] = pd.to_numeric(df[c_cnt], errors="coerce")
        df = df.dropna(subset=["tract_geoid", "crime_incidents"]).copy()
        df = (
            df.groupby("tract_geoid", as_index=False)["crime_incidents"]
            .sum()
        )
        return df[["tract_geoid", "crime_incidents"]]

    # Case 2: detailed incident-level file
    c_inc = pick(
        "incidentuid", "incident_uid", "Incident UID", "IncidentUID",
        "incident id", "incident_id"
    )
    c_date = pick(
        "incident_date", "Incident Date", "date", "offense_date", "report_date"
    )
    c_tr = pick(
        "census_tract", "Census Tract", "tract", "tract_num", "census tract"
    )

    if c_inc is None or c_date is None or c_tr is None:
        print("CIBRS missing required columns.")
        print("Available columns:", cols)
        print("Matched incident column:", c_inc)
        print("Matched date column:", c_date)
        print("Matched tract column:", c_tr)
        print("Matched aggregated count column:", c_cnt)
        return None

    years = set()
    for chunk in pd.read_csv(p, usecols=[c_date], chunksize=200_000):
        dt = pd.to_datetime(chunk[c_date], errors="coerce")
        y = dt.dt.year.dropna().unique().tolist()
        years.update([int(v) for v in y if not pd.isna(v)])

    if not years:
        return None

    max_year = max(years)
    target_year = max_year - 1 if max_year >= 2025 else max_year
    print("CIBRS years found:", sorted(years))
    print("Using target crime year:", target_year)

    counts = {}
    for chunk in pd.read_csv(p, usecols=[c_inc, c_date, c_tr], chunksize=200_000):
        dt = pd.to_datetime(chunk[c_date], errors="coerce")
        chunk = chunk.loc[dt.dt.year == target_year].copy()
        if chunk.empty:
            continue

        chunk["tract_geoid"] = chunk[c_tr].apply(tract_from_sandag_tract_value)
        chunk = sd_only(chunk)

        g = chunk.groupby("tract_geoid")[c_inc].nunique()
        for k, v in g.items():
            counts[k] = counts.get(k, 0) + int(v)

    out = pd.DataFrame({
        "tract_geoid": list(counts.keys()),
        "crime_incidents": list(counts.values())
    })
    return out

def load_calenviroscreen_sd_geo() -> gpd.GeoDataFrame | None:
    """
    Uses the CalEnviroScreen shapefile.
    Also pulls an environmental burden indicator from percentile/score if available.
    """
    safety_dir = RAW_DOMAINS / "safety" / "calenviroscreen40shpf2021shp"
    shp = next(safety_dir.glob("*.shp"), None)
    if shp is None:
        print("CalEnviroScreen shapefile not found.")
        return None

    gdf = gpd.read_file(shp)

    tract_col = None
    for cand in ["GEOID", "geoid", "Tract", "TRACT", "CensusTract", "CENSUS_TRACT"]:
        if cand in gdf.columns:
            tract_col = cand
            break
    if tract_col is None:
        for c in gdf.columns:
            if "tract" in c.lower():
                tract_col = c
                break
    if tract_col is None:
        print("Could not find tract id column in CalEnviroScreen shapefile.")
        return None

    gdf["tract_geoid"] = gdf[tract_col].map(sd_geoid11_from_tract_like)
    gdf = gdf.dropna(subset=["tract_geoid"]).copy()
    gdf = gdf[gdf["tract_geoid"].astype(str).str.startswith("06073")].copy()

    env_col = None
    for cand in ["PolBurdP", "PolBurdSc", "CIscoreP", "CIscore", "CES4_Percentile", "CES4_Pctl", "Percentile", "CES_Pctl", "CES_SCORE", "CES4_Score"]:
        if cand in gdf.columns:
            env_col = cand
            break
    if env_col is None:
        for c in gdf.columns:
            lc = c.lower()
            if "polburd" in lc or "burd" in lc or "pctl" in lc or "percent" in lc:
                env_col = c
                break

    if env_col:
        gdf["env_burden"] = safe_num(gdf[env_col])
    else:
        gdf["env_burden"] = np.nan

    # IMPORTANT: Folium/Leaflet needs lat/lon
    if gdf.crs is not None:
        gdf = gdf.to_crs(epsg=4326)

    # optional geometry cleanup
    try:
        gdf["geometry"] = gdf["geometry"].buffer(0)
    except Exception:
        pass

    return gdf[["tract_geoid", "env_burden", "geometry"]].copy()

def pick_col(df, candidates):
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        c = cols_lower.get(cand.lower())
        if c is not None:
            return c
    return None

def first_nonempty_numeric_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            s = pd.to_numeric(df[c], errors="coerce")
            if s.notna().sum() > 0:
                return c
    return None

# 1) Use CalEnviroScreen shapefile as the base tract list + geometry
# ces_gdf = load_calenviroscreen_sd_geo()
# if ces_gdf is not None and len(ces_gdf) > 0:
#     print("Anchoring tracts from CalEnviroScreen:", ces_gdf.shape)

#     # Save geometry for dashboard
#     geo_out = OUT_BOUNDS_DIR / "sd_tracts.geojson"
#     ces_gdf[["tract_geoid", "geometry"]].to_file(geo_out, driver="GeoJSON")
#     print("Saved SD tract boundaries:", geo_out)

#     # Base tracts table (always one row per tract)
#     tracts = pd.DataFrame({
#         "tract_geoid": ces_gdf["tract_geoid"].astype(str),
#         # optional environmental field if present
#         "env_burden": pd.to_numeric(ces_gdf.get("env_burden", np.nan), errors="coerce"),
#     }).drop_duplicates("tract_geoid")

#     pop_col = None  
# else:
#     print("WARNING: CalEnviroScreen anchor not found. Falling back to GEOIDs from raw tables.")

#     # 2) Fallback: build tract list from whatever raw ACS tables exist
#     geoid_sets = []

#     for domain, prefix in [
#         ("economic", "ACSST5Y2024.S1701"),
#         ("economic", "ACSDT5Y2024.B19013"),
#         ("economic", "ACSST5Y2024.S2301"),
#         ("education", "ACSST5Y2024.S1501"),
#         ("education", "ACSST5Y2024.S1401"),
#         ("health", "ACSST5Y2024.S2701"),
#         ("housing", "ACSDT5Y2024.B25003"),
#         ("mobility", "ACSDT5Y2024.B08201"),
#     ]:
#         df_tmp = load_census_table(domain, prefix)
#         if df_tmp is not None and "tract_geoid" in df_tmp.columns:
#             geoid_sets.append(df_tmp["tract_geoid"].dropna().astype(str).unique())

#     if not geoid_sets:
#         raise FileNotFoundError(
#             "Could not find ANY tract GEOIDs to anchor the index. "
#             "Make sure CalEnviroScreen shapefile exists under data/rawdomains/safety/..."
#         )

#     all_geoids = sorted(set(np.concatenate(geoid_sets)))
#     tracts = pd.DataFrame({"tract_geoid": all_geoids})
#     pop_col = None

# 1) Use already-built boundary GeoJSON as the base tract list
anchor_geo_path = OUT_BOUNDS_DIR / "sd_tracts.geojson"

if not anchor_geo_path.exists():
    raise FileNotFoundError(
        f"Missing {anchor_geo_path}. Run: python scripts/build_sd_tracts_geojson_2025.py"
    )

anchor_gdf = gpd.read_file(anchor_geo_path)
anchor_gdf["tract_geoid"] = anchor_gdf["tract_geoid"].astype(str)

print("Anchoring tracts from boundary GeoJSON:", anchor_gdf.shape)

tracts = anchor_gdf[["tract_geoid"]].drop_duplicates("tract_geoid").copy()
tracts["env_burden"] = np.nan
pop_col = None

print("Base SD tracts:", tracts.shape)

# Add TOTAL POPULATION (ACS B01003) for per-capita rates
pop = load_census_table("economic", "ACSDT5Y2024.B01003")  # expects tract_geoid inside loader output
if pop is None or len(pop) == 0:
    print("WARNING: Could not load ACSDT5Y2024.B01003 (Total Population). Per-capita rates will be NaN.")
    tracts["total_population"] = np.nan
else:
    # Find the estimate column (usually B01003_001E)
    pop_est_col = pick_col(pop, ["B01003_001E", "b01003_001e"])
    if pop_est_col is None:
        # fallback: first estimate-like column ending with _E
        est_cols = [c for c in pop.columns if c.endswith("_E")]
        pop_est_col = est_cols[0] if est_cols else None

    if pop_est_col is None:
        print("WARNING: B01003 estimate column not found. Per-capita rates will be NaN.")
        tracts["total_population"] = np.nan
    else:
        pop_small = pop[["tract_geoid", pop_est_col]].copy()
        pop_small = pop_small.rename(columns={pop_est_col: "total_population"})
        pop_small["total_population"] = pd.to_numeric(pop_small["total_population"], errors="coerce")

        # IMPORTANT: make sure GEOID types match
        tracts["tract_geoid"] = tracts["tract_geoid"].astype(str)
        pop_small["tract_geoid"] = pop_small["tract_geoid"].astype(str)

        tracts = tracts.merge(pop_small, on="tract_geoid", how="left")
        print("Merged total_population from B01003. Coverage:",
              tracts["total_population"].notna().mean())

# Indicator extraction

indicator_meta = []

def add_indicator(df: pd.DataFrame, name: str, domain: str, series: pd.Series, higher_is_better: bool, source: str, notes: str):
    df[name] = series
    indicator_meta.append({
        "indicator": name,
        "domain": domain,
        "higher_is_better": higher_is_better,
        "source": source,
        "notes": notes,
    })

# ECONOMIC
# poverty rate (S1701) -> try common percent column; fallback to label-less heuristics
s1701 = load_census_table("economic", "ACSST5Y2024.S1701")
if s1701 is not None:
    pick = first_nonempty_numeric_col(s1701, [
        "S1701_C02_001E",
        "S1701_C03_001E",
        "S1701_C02_002E",
    ])
    poverty = safe_num(s1701[pick]) if pick else pd.Series(np.nan, index=s1701.index)
    econ = s1701[["tract_geoid"]].copy()
    econ["poverty_rate"] = poverty
    tracts = tracts.merge(econ, on="tract_geoid", how="left")
    add_indicator(tracts, "poverty_rate", "economic", tracts["poverty_rate"], False, "ACS S1701", f"column={pick}")
else:
    tracts["poverty_rate"] = np.nan

# median household income (B19013)
b19013 = load_census_table("economic", "ACSDT5Y2024.B19013")
if b19013 is not None:
    pick = "B19013_001E" if "B19013_001E" in b19013.columns else None
    if pick is None:
        est_cols = [c for c in b19013.columns if c.endswith("_001E")]
        pick = est_cols[0] if est_cols else None
    inc = safe_num(b19013[pick]) if pick else pd.Series(np.nan, index=b19013.index)
    tmp = b19013[["tract_geoid"]].copy()
    tmp["median_hh_income"] = inc
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(tracts, "median_hh_income", "economic", tracts["median_hh_income"], True, "ACS B19013", f"column={pick}")
else:
    tracts["median_hh_income"] = np.nan

# unemployment rate (S2301)
s2301 = load_census_table("economic", "ACSST5Y2024.S2301")
if s2301 is not None:
    pick = first_nonempty_numeric_col(s2301, [
        "S2301_C04_001E",
        "S2301_C02_004E",
        "S2301_C02_001E",
    ])
    unemp = safe_num(s2301[pick]) if pick else pd.Series(np.nan, index=s2301.index)
    tmp = s2301[["tract_geoid"]].copy()
    tmp["unemployment_rate"] = unemp
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(tracts, "unemployment_rate", "economic", tracts["unemployment_rate"], False, "ACS S2301", f"column={pick}")
else:
    tracts["unemployment_rate"] = np.nan

# SNAP/public assistance (S2201)
s2201 = load_census_table("economic", "ACSST5Y2024.S2201")
if s2201 is not None:
    pick = first_nonempty_numeric_col(s2201, [
        "S2201_C02_013E",
        "S2201_C02_015E",
        "S2201_C02_001E",
    ])
    snap = safe_num(s2201[pick]) if pick else pd.Series(np.nan, index=s2201.index)
    tmp = s2201[["tract_geoid"]].copy()
    tmp["snap_or_assist_rate"] = snap
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(tracts, "snap_or_assist_rate", "economic", tracts["snap_or_assist_rate"], False, "ACS S2201", f"column={pick}")
else:
    tracts["snap_or_assist_rate"] = np.nan

# EDUCATION 
s1501 = load_census_table("education", "ACSST5Y2024.S1501")
if s1501 is not None:
    hs_pick = first_nonempty_numeric_col(s1501, [
        "S1501_C02_015E", "S1501_C03_015E", "S1501_C04_015E", "S1501_C05_015E", "S1501_C06_015E",
        "S1501_C02_014E", "S1501_C03_014E", "S1501_C04_014E", "S1501_C05_014E", "S1501_C06_014E",
        "S1501_C02_013E", "S1501_C03_013E", "S1501_C04_013E", "S1501_C05_013E", "S1501_C06_013E",
    ])
    ba_pick = first_nonempty_numeric_col(s1501, [
        "S1501_C02_016E", "S1501_C03_016E", "S1501_C04_016E", "S1501_C05_016E", "S1501_C06_016E",
        "S1501_C02_015E", "S1501_C03_015E", "S1501_C04_015E", "S1501_C05_015E", "S1501_C06_015E",
        "S1501_C02_014E", "S1501_C03_014E", "S1501_C04_014E", "S1501_C05_014E", "S1501_C06_014E",
    ])

    tmp = s1501[["tract_geoid"]].copy()
    tmp["hs_plus"] = safe_num(s1501[hs_pick]) if hs_pick else np.nan
    tmp["ba_plus"] = safe_num(s1501[ba_pick]) if ba_pick else np.nan
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")

    add_indicator(tracts, "hs_plus", "education", tracts["hs_plus"], True, "ACS S1501", f"hs_col={hs_pick}")
    add_indicator(tracts, "ba_plus", "education", tracts["ba_plus"], True, "ACS S1501", f"ba_col={ba_pick}")
else:
    tracts["hs_plus"] = np.nan
    tracts["ba_plus"] = np.nan

s1401 = load_census_table("education", "ACSST5Y2024.S1401")
if s1401 is not None:
    pick = first_nonempty_numeric_col(s1401, [
        "S1401_C02_001E", "S1401_C03_001E", "S1401_C04_001E", "S1401_C05_001E", "S1401_C06_001E",
        "S1401_C02_002E", "S1401_C03_002E", "S1401_C04_002E", "S1401_C05_002E", "S1401_C06_002E",
        "S1401_C02_003E", "S1401_C03_003E", "S1401_C04_003E", "S1401_C05_003E", "S1401_C06_003E",
    ])

    tmp = s1401[["tract_geoid"]].copy()
    tmp["school_enrollment"] = safe_num(s1401[pick]) if pick else np.nan
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(tracts, "school_enrollment", "education", tracts["school_enrollment"], True, "ACS S1401", f"column={pick}")
else:
    tracts["school_enrollment"] = np.nan

b14005 = load_census_table("education", "ACSDT5Y2024.B14005")
if b14005 is not None:
    tmp = b14005[["tract_geoid"]].copy()

    total_col = "B14005_001E"
    disconnect_cols = [
        "B14005_011E", "B14005_014E", "B14005_015E",
        "B14005_025E", "B14005_028E", "B14005_029E",
    ]

    if total_col in b14005.columns and all(c in b14005.columns for c in disconnect_cols):
        total = safe_num(b14005[total_col])
        disconnected = safe_num(b14005[disconnect_cols]).sum(axis=1)

        total = total.where(total > 0, np.nan)
        tmp["youth_disconnection_proxy"] = np.where(total > 0, disconnected / total * 100.0, np.nan)
        note = (
            "share of population age 16-19 who are not enrolled in school and not working; "
            f"numerator=sum({','.join(disconnect_cols)}); denominator={total_col}"
        )
    else:
        tmp["youth_disconnection_proxy"] = np.nan
        note = "missing required B14005 columns for youth disconnection calculation"

    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(
        tracts,
        "youth_disconnection_proxy",
        "education",
        tracts["youth_disconnection_proxy"],
        False,
        "ACS B14005",
        note,
    )
else:
    tracts["youth_disconnection_proxy"] = np.nan

# HEALTH
s2701 = load_census_table("health", "ACSST5Y2024.S2701")
if s2701 is not None:
    pick = first_nonempty_numeric_col(s2701, [
        "S2701_C02_001E",
        "S2701_C02_005E",
        "S2701_C02_004E",
    ])
    tmp = s2701[["tract_geoid"]].copy()
    tmp["uninsured_rate"] = safe_num(s2701[pick]) if pick else np.nan
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(tracts, "uninsured_rate", "health", tracts["uninsured_rate"], False, "ACS S2701", f"column={pick}")
else:
    tracts["uninsured_rate"] = np.nan

s1810 = load_census_table("health", "ACSST5Y2024.S1810")
if s1810 is not None:
    pick = first_nonempty_numeric_col(s1810, [
        "S1810_C02_001E",
        "S1810_C02_002E",
        "S1810_C02_003E",
    ])
    tmp = s1810[["tract_geoid"]].copy()
    tmp["disability_rate"] = safe_num(s1810[pick]) if pick else np.nan
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(tracts, "disability_rate", "health", tracts["disability_rate"], False, "ACS S1810", f"column={pick}")
else:
    tracts["disability_rate"] = np.nan

places = load_places_latest()
if places is not None:
    tracts = tracts.merge(places, on="tract_geoid", how="left")
    # mental distress and poor physical health from PLACES
    add_indicator(tracts, "frequent_mental_distress", "health", safe_num(tracts.get("places_MHLTH")), False, "CDC PLACES", "MeasureId=MHLTH")
    add_indicator(tracts, "poor_physical_health", "health", safe_num(tracts.get("places_PHLTH")), False, "CDC PLACES", "MeasureId=PHLTH")
else:
    tracts["frequent_mental_distress"] = np.nan
    tracts["poor_physical_health"] = np.nan

# HOUSING
b25070 = load_census_table("housing", "ACSDT5Y2024.B25070")
if b25070 is not None:
    tmp = b25070[["tract_geoid"]].copy()

    total_col = "B25070_001E"
    burden_cols = ["B25070_007E", "B25070_008E", "B25070_009E", "B25070_010E"]
    not_computed_col = "B25070_011E"

    if total_col in b25070.columns and all(c in b25070.columns for c in burden_cols):
        total = safe_num(b25070[total_col])
        burden_30_plus = safe_num(b25070[burden_cols]).sum(axis=1)

        if not_computed_col in b25070.columns:
            denom = total - safe_num(b25070[not_computed_col])
            note = (
                "share of renter households with gross rent >=30% of household income; "
                f"numerator=sum({','.join(burden_cols)}); denominator={total_col}-{not_computed_col}"
            )
        else:
            denom = total
            note = (
                "share of renter households with gross rent >=30% of household income; "
                f"numerator=sum({','.join(burden_cols)}); denominator={total_col}"
            )

        denom = denom.where(denom > 0, np.nan)
        tmp["rent_burden_proxy"] = np.where(denom > 0, burden_30_plus / denom * 100.0, np.nan)
    else:
        tmp["rent_burden_proxy"] = np.nan
        note = "missing required B25070 columns for >=30% rent burden calculation"

    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(
        tracts,
        "rent_burden_proxy",
        "housing",
        tracts["rent_burden_proxy"],
        False,
        "ACS B25070",
        note,
    )
else:
    tracts["rent_burden_proxy"] = np.nan


b25014 = load_census_table("housing", "ACSDT5Y2024.B25014")
if b25014 is not None:
    tmp = b25014[["tract_geoid"]].copy()

    total_col = "B25014_001E"
    crowded_cols = [
        "B25014_005E", "B25014_006E", "B25014_007E",
        "B25014_011E", "B25014_012E", "B25014_013E",
    ]

    if total_col in b25014.columns and all(c in b25014.columns for c in crowded_cols):
        total = safe_num(b25014[total_col])
        crowded = safe_num(b25014[crowded_cols]).sum(axis=1)

        total = total.where(total > 0, np.nan)
        tmp["overcrowding_proxy"] = np.where(total > 0, crowded / total * 100.0, np.nan)
        note = (
            "share of occupied housing units with >1.0 occupants per room; "
            f"numerator=sum({','.join(crowded_cols)}); denominator={total_col}"
        )
    else:
        tmp["overcrowding_proxy"] = np.nan
        note = "missing required B25014 columns for overcrowding calculation"

    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(
        tracts,
        "overcrowding_proxy",
        "housing",
        tracts["overcrowding_proxy"],
        False,
        "ACS B25014",
        note,
    )
else:
    tracts["overcrowding_proxy"] = np.nan


b07001 = load_census_table("housing", "ACSDT5Y2024.B07001")
if b07001 is not None:
    tmp = b07001[["tract_geoid"]].copy()

    total_col = "B07001_001E"
    same_house_col = "B07001_017E"

    if total_col in b07001.columns and same_house_col in b07001.columns:
        total = safe_num(b07001[total_col])
        same_house = safe_num(b07001[same_house_col])

        moved = (total - same_house).clip(lower=0)
        total = total.where(total > 0, np.nan)

        tmp["moved_past_year_proxy"] = np.where(total > 0, moved / total * 100.0, np.nan)
        note = (
            "share of population age 1+ who lived in a different house one year ago; "
            f"formula=({total_col}-{same_house_col})/{total_col}"
        )
    else:
        tmp["moved_past_year_proxy"] = np.nan
        note = "missing required B07001 columns for residential mobility calculation"

    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(
        tracts,
        "moved_past_year_proxy",
        "housing",
        tracts["moved_past_year_proxy"],
        False,
        "ACS B07001",
        note,
    )
else:
    tracts["moved_past_year_proxy"] = np.nan


b25003 = load_census_table("housing", "ACSDT5Y2024.B25003")
if b25003 is not None:
    # homeownership: owner-occupied / occupied
    owner = "B25003_002E" if "B25003_002E" in b25003.columns else None
    occ = "B25003_001E" if "B25003_001E" in b25003.columns else None
    tmp = b25003[["tract_geoid"]].copy()
    if owner and occ:
        o = safe_num(b25003[owner])
        t = safe_num(b25003[occ])
        tmp["homeownership_rate"] = np.where(t > 0, o / t * 100.0, np.nan)
        note = f"owner={owner} / occupied={occ}"
    else:
        tmp["homeownership_rate"] = np.nan
        note = "missing B25003_002E/B25003_001E"
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(tracts, "homeownership_rate", "housing", tracts["homeownership_rate"], True, "ACS B25003", note)
else:
    tracts["homeownership_rate"] = np.nan

# SAFETY & ENVIRONMENT 
s1101 = load_census_table("safety", "ACSST5Y2024.S1101")
if s1101 is not None:
    tmp = s1101[["tract_geoid"]].copy()

    total_col = "S1101_C01_005E"
    male_single_col = "S1101_C03_005E"
    female_single_col = "S1101_C04_005E"

    if all(c in s1101.columns for c in [total_col, male_single_col, female_single_col]):
        total = safe_num(s1101[total_col])
        single_parent = safe_num(s1101[male_single_col]) + safe_num(s1101[female_single_col])

        total = total.where(total > 0, np.nan)
        tmp["single_parent_proxy"] = np.where(total > 0, single_parent / total * 100.0, np.nan)
        note = (
            "share of households with own children under 18 that are single-parent households; "
            f"numerator={male_single_col}+{female_single_col}; denominator={total_col}"
        )
    else:
        tmp["single_parent_proxy"] = np.nan
        note = "missing required S1101 columns for single-parent household calculation"

    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(
        tracts,
        "single_parent_proxy",
        "safety_env",
        tracts["single_parent_proxy"],
        False,
        "ACS S1101",
        note,
    )
else:
    tracts["single_parent_proxy"] = np.nan

b25002 = load_census_table("safety", "ACSDT5Y2024.B25002")
if b25002 is not None:
    total = "B25002_001E" if "B25002_001E" in b25002.columns else None
    vacant = "B25002_003E" if "B25002_003E" in b25002.columns else None
    tmp = b25002[["tract_geoid"]].copy()
    if total and vacant:
        t = safe_num(b25002[total])
        v = safe_num(b25002[vacant])
        tmp["vacancy_rate"] = np.where(t > 0, v / t * 100.0, np.nan)
        note = f"vacant={vacant}/total={total}"
    else:
        tmp["vacancy_rate"] = np.nan
        note = "missing B25002_001E/B25002_003E"
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(tracts, "vacancy_rate", "safety_env", tracts["vacancy_rate"], False, "ACS B25002", note)
else:
    tracts["vacancy_rate"] = np.nan

crime = load_cibrs_and_aggregate_latest_full_year()
if crime is not None:
    tracts["tract_geoid"] = tracts["tract_geoid"].astype(str)
    crime["tract_geoid"] = crime["tract_geoid"].astype(str)
    tracts = tracts.merge(crime, on="tract_geoid", how="left")
    tracts["crime_incidents"] = safe_num(tracts["crime_incidents"]).fillna(0)
    # per-1k rate (prefer total_population from ACS B01003)
    if "total_population" in tracts.columns:
        denom = safe_num(tracts["total_population"])
    elif pop_col and pop_col in tracts.columns:
        denom = safe_num(tracts[pop_col])
    else:
        denom = None

    if denom is not None:
        tracts["crime_rate_per_1k"] = np.where(
            denom > 0,
            tracts["crime_incidents"] / denom * 1000.0,
            np.nan
        )
    else:
        tracts["crime_rate_per_1k"] = np.nan

    add_indicator(tracts, "crime_rate_per_1k", "safety_env", tracts["crime_rate_per_1k"], False, "SANDAG ARJIS CIBRS", "incidents per 1k using distinct Incident UID")
else:
    tracts["crime_rate_per_1k"] = np.nan

# ces_gdf = load_calenviroscreen_sd_geo()
# if ces_gdf is not None and len(ces_gdf) > 0:
#     # save geometry for dashboard map
#     geo_out = OUT_BOUNDS_DIR / "sd_tracts.geojson"
#     ces_gdf[["tract_geoid", "geometry"]].to_file(
#     OUT_BOUNDS_DIR / "sd_tracts.geojson",
#     driver="GeoJSON"
#     )
#     print("Saved SD tract boundaries:", geo_out)

#     # IMPORTANT:
#     # If we anchored from CalEnviroScreen earlier, tracts already has env_burden.
#     # So do NOT merge env_burden again (it creates env_burden_x/env_burden_y).
#     if "env_burden" not in tracts.columns:
#         env = ces_gdf[["tract_geoid", "env_burden"]].copy()
#         env["tract_geoid"] = env["tract_geoid"].astype(str)
#         tracts["tract_geoid"] = tracts["tract_geoid"].astype(str)
#         tracts = tracts.merge(env, on="tract_geoid", how="left")

#     # ensure numeric
#     tracts["env_burden"] = pd.to_numeric(tracts["env_burden"], errors="coerce")

#     add_indicator(
#         tracts,
#         "env_burden",
#         "safety_env",
#         tracts["env_burden"],
#         False,
#         "CalEnviroScreen 4.0",
#         "CalEnviroScreen percentile/score (higher burden = worse)"
#     )
# else:
#     if "env_burden" not in tracts.columns:
#         tracts["env_burden"] = np.nan

ces_gdf = load_calenviroscreen_sd_geo()
if ces_gdf is not None and len(ces_gdf) > 0:
    # Only merge environmental burden as data.
    # Do NOT overwrite sd_tracts.geojson here.
    if "env_burden" not in tracts.columns:
        env = ces_gdf[["tract_geoid", "env_burden"]].copy()
        env["tract_geoid"] = env["tract_geoid"].astype(str)
        tracts["tract_geoid"] = tracts["tract_geoid"].astype(str)
        tracts = tracts.merge(env, on="tract_geoid", how="left")
    else:
        env = ces_gdf[["tract_geoid", "env_burden"]].copy()
        env["tract_geoid"] = env["tract_geoid"].astype(str)
        tracts["tract_geoid"] = tracts["tract_geoid"].astype(str)
        tracts = tracts.merge(env, on="tract_geoid", how="left", suffixes=("", "_ces"))
        if "env_burden_ces" in tracts.columns:
            tracts["env_burden"] = tracts["env_burden"].fillna(tracts["env_burden_ces"])
            tracts = tracts.drop(columns=["env_burden_ces"])

    tracts["env_burden"] = pd.to_numeric(tracts["env_burden"], errors="coerce")

    add_indicator(
        tracts,
        "env_burden",
        "safety_env",
        tracts["env_burden"],
        False,
        "CalEnviroScreen 4.0",
        "CalEnviroScreen percentile/score (higher burden = worse)"
    )
else:
    if "env_burden" not in tracts.columns:
        tracts["env_burden"] = np.nan

# MOBILITY & CONNECTIVITY
b08201 = load_census_table("mobility", "ACSDT5Y2024.B08201")
if b08201 is not None:
    total = "B08201_001E" if "B08201_001E" in b08201.columns else None
    nov = "B08201_002E" if "B08201_002E" in b08201.columns else None
    tmp = b08201[["tract_geoid"]].copy()
    if total and nov:
        t = safe_num(b08201[total])
        z = safe_num(b08201[nov])
        tmp["no_vehicle_rate"] = np.where(t > 0, z / t * 100.0, np.nan)
        note = f"no_vehicle={nov}/total={total}"
    else:
        tmp["no_vehicle_rate"] = np.nan
        note = "missing B08201_001E/B08201_002E"
    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(tracts, "no_vehicle_rate", "mobility_connectivity", tracts["no_vehicle_rate"], False, "ACS B08201", note)
else:
    tracts["no_vehicle_rate"] = np.nan

b08303 = load_census_table("mobility", "ACSDT5Y2024.B08303")
if b08303 is not None:
    tmp = b08303[["tract_geoid"]].copy()

    total_col = "B08303_001E"
    long_commute_cols = [
        "B08303_008E", "B08303_009E", "B08303_010E",
        "B08303_011E", "B08303_012E", "B08303_013E",
    ]

    if total_col in b08303.columns and all(c in b08303.columns for c in long_commute_cols):
        total = safe_num(b08303[total_col])
        long_commute = safe_num(b08303[long_commute_cols]).sum(axis=1)

        total = total.where(total > 0, np.nan)
        tmp["commute_time_proxy"] = np.where(total > 0, long_commute / total * 100.0, np.nan)
        note = (
            "share of workers with travel time to work >=30 minutes; "
            f"numerator=sum({','.join(long_commute_cols)}); denominator={total_col}"
        )
    else:
        tmp["commute_time_proxy"] = np.nan
        note = "missing required B08303 columns for long-commute calculation"

    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(
        tracts,
        "commute_time_proxy",
        "mobility_connectivity",
        tracts["commute_time_proxy"],
        False,
        "ACS B08303",
        note,
    )
else:
    tracts["commute_time_proxy"] = np.nan

b28002 = load_census_table("mobility", "ACSDT5Y2024.B28002")
if b28002 is not None:
    tmp = b28002[["tract_geoid"]].copy()

    total_col = "B28002_001E"
    broadband_col = "B28002_004E"

    if total_col in b28002.columns and broadband_col in b28002.columns:
        total = safe_num(b28002[total_col])
        broadband = safe_num(b28002[broadband_col])

        total = total.where(total > 0, np.nan)
        tmp["internet_sub_rate_proxy"] = np.where(total > 0, broadband / total * 100.0, np.nan)
        note = f"share of households with a broadband internet subscription; numerator={broadband_col}; denominator={total_col}"
    else:
        tmp["internet_sub_rate_proxy"] = np.nan
        note = "missing required B28002 columns for broadband subscription calculation"

    tracts = tracts.merge(tmp, on="tract_geoid", how="left")
    add_indicator(
        tracts,
        "internet_sub_rate_proxy",
        "mobility_connectivity",
        tracts["internet_sub_rate_proxy"],
        True,
        "ACS B28002",
        note,
    )
else:
    tracts["internet_sub_rate_proxy"] = np.nan

# transit access
# Keep PLACES lack transport only as a diagnostic raw field.
# Do not score it as a transit-access indicator.
if "places_LACKTRPT" in tracts.columns:
    tracts["lack_transport"] = safe_num(tracts["places_LACKTRPT"])
else:
    tracts["lack_transport"] = np.nan

# YOUTH SUPPORTS / WRAPAROUND
services_csv = RAW_DOMAINS / "youth" / "services_master.csv"

if services_csv.exists():
    svc = pd.read_csv(services_csv)

    # find tract id
    tract_col = None
    for cand in ["tract_geoid", "GEOID", "geoid", "tract"]:
        if cand in svc.columns:
            tract_col = cand
            break
    if tract_col is None:
        tract_col = svc.columns[0]

    svc["tract_geoid"] = svc[tract_col].apply(sd_geoid11_from_tract_like)
    svc = svc[svc["tract_geoid"].notna()].copy()
    svc = sd_only(svc)

    if "tract_geoid" not in svc.columns:
        raise ValueError("sd_only() removed tract_geoid. Update sd_only() to not drop columns.")

    # total services per tract
    tot = svc.groupby("tract_geoid").size().reset_index(name="service_count")

    # keyword-based diagnostics only
    text_cols = [c for c in svc.columns if svc[c].dtype == object]

    def row_text(r):
        return " ".join([str(r[c]) for c in text_cols if pd.notna(r[c])]).lower()

    svc["_text"] = svc.apply(row_text, axis=1)
    youth_kw = ["youth", "teen", "child", "children", "after school", "school", "tutoring"]
    mh_kw = ["mental", "behavioral", "therapy", "counsel", "psychi", "substance", "sud"]

    svc["is_youth"] = svc["_text"].apply(lambda t: any(k in t for k in youth_kw))
    svc["is_mental_health"] = svc["_text"].apply(lambda t: any(k in t for k in mh_kw))

    mask_y = svc["is_youth"].fillna(False).astype(bool)
    mask_mh = svc["is_mental_health"].fillna(False).astype(bool)

    youth_ct = svc.loc[mask_y].groupby("tract_geoid").size().reset_index(name="youth_service_count")
    mh_ct = svc.loc[mask_mh].groupby("tract_geoid").size().reset_index(name="mh_service_count")

    tracts = tracts.merge(tot, on="tract_geoid", how="left")
    tracts = tracts.merge(youth_ct, on="tract_geoid", how="left")
    tracts = tracts.merge(mh_ct, on="tract_geoid", how="left")

    tracts["service_count"] = safe_num(tracts["service_count"]).fillna(0)
    tracts["youth_service_count"] = safe_num(tracts["youth_service_count"]).fillna(0)
    tracts["mh_service_count"] = safe_num(tracts["mh_service_count"]).fillna(0)

    if "total_population" in tracts.columns:
        denom = safe_num(tracts["total_population"])
    elif pop_col and pop_col in tracts.columns:
        denom = safe_num(tracts[pop_col])
    else:
        denom = None

    if denom is not None:
        tracts["services_per_10k"] = np.where(
            denom > 0,
            tracts["service_count"] / denom * 10000.0,
            np.nan
        )
        tracts["youth_services_per_10k"] = np.where(
            denom > 0,
            tracts["youth_service_count"] / denom * 10000.0,
            np.nan
        )
        tracts["mh_services_per_10k"] = np.where(
            denom > 0,
            tracts["mh_service_count"] / denom * 10000.0,
            np.nan
        )
    else:
        tracts["services_per_10k"] = np.nan
        tracts["youth_services_per_10k"] = np.nan
        tracts["mh_services_per_10k"] = np.nan

    add_indicator(
        tracts,
        "service_count",
        "youth_supports",
        tracts["service_count"],
        True,
        "services_master",
        "total services per tract"
    )
    add_indicator(
        tracts,
        "services_per_10k",
        "youth_supports",
        tracts["services_per_10k"],
        True,
        "services_master + population",
        "density per 10k"
    )

else:
    for c in [
        "service_count",
        "youth_service_count",
        "mh_service_count",
        "services_per_10k",
        "youth_services_per_10k",
        "mh_services_per_10k",
    ]:
        tracts[c] = np.nan

# Build domain scores + YOI
DOMAINS = [
    "economic",
    "education",
    "health",
    "housing",
    "safety_env",
    "mobility_connectivity",
    "youth_supports",
]

# What indicators ended up present?
meta_df = pd.DataFrame(indicator_meta)
meta_path = OUT_YOI_DIR / "yoi_indicator_meta.csv"
meta_df.to_csv(meta_path, index=False)
print("Saved indicator metadata:", meta_path)

# Normalize each indicator and compute per-domain mean
norm_cols = []
for _, row in meta_df.iterrows():
    ind = row["indicator"]
    hib = bool(row["higher_is_better"])
    if ind in tracts.columns:
        tracts[f"norm_{ind}"] = normalize(safe_num(tracts[ind]), hib)
        norm_cols.append(f"norm_{ind}")

domain_scores = pd.DataFrame({"tract_geoid": tracts["tract_geoid"].astype(str)})

for d in DOMAINS:
    inds = meta_df.loc[meta_df["domain"] == d, "indicator"].tolist()
    cols = [f"norm_{i}" for i in inds if f"norm_{i}" in tracts.columns]

    if not cols:
        domain_scores[f"{d}_score"] = np.nan
        domain_scores[f"{d}_coverage"] = 0.0
    else:
        mat = tracts[cols]
        domain_scores[f"{d}_score"] = mat.mean(axis=1, skipna=True)
        domain_scores[f"{d}_coverage"] = mat.notna().mean(axis=1)

score_cols = [f"{d}_score" for d in DOMAINS]

domain_scores["yoi_domain_coverage"] = domain_scores[score_cols].notna().mean(axis=1)
domain_scores["yoi_raw_0_1"] = domain_scores[score_cols].mean(axis=1, skipna=True)
domain_scores["yoi_0_100"] = domain_scores["yoi_raw_0_1"] * 100.0

# Attach raw + normalized indicator columns so the frontend can explain each domain
indicator_cols = [c for c in meta_df["indicator"].tolist() if c in tracts.columns]
norm_indicator_cols = [f"norm_{c}" for c in indicator_cols if f"norm_{c}" in tracts.columns]

keep_raw = ["tract_geoid"]

if "total_population" in tracts.columns:
    keep_raw.append("total_population")
elif pop_col and pop_col in tracts.columns:
    keep_raw.append(pop_col)

for c in indicator_cols + norm_indicator_cols:
    if c in tracts.columns and c not in keep_raw:
        keep_raw.append(c)

for c in [
    "crime_rate_per_1k",
    "service_count",
    "youth_service_count",
    "mh_service_count",
    "services_per_10k",
    "youth_services_per_10k",
    "mh_services_per_10k",
    "lack_transport",
]:
    if c in tracts.columns and c not in keep_raw:
        keep_raw.append(c)

out = domain_scores.merge(
    tracts[keep_raw].drop_duplicates("tract_geoid"),
    on="tract_geoid",
    how="left",
)

out_path = OUT_YOI_DIR / "yoi_components.csv"
out.to_csv(out_path, index=False)
print("Saved YOI components:", out_path)
print(out.describe(include="all"))