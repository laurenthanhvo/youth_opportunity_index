from pathlib import Path
import re
import pandas as pd
import geopandas as gpd

def find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root")

def normalize_geoid(v):
    if pd.isna(v):
        return None

    s = str(v).strip()

    # common CSV float artifact like 6073006500.0
    if s.endswith(".0"):
        s = s[:-2]

    digits = re.sub(r"\D", "", s)
    if not digits:
        return None

    # 10-digit tract ids from CA need leading 0
    if len(digits) == 10:
        return digits.zfill(11)

    # already 11 digits
    if len(digits) == 11:
        return digits

    # if longer, keep the last 11
    if len(digits) > 11:
        return digits[-11:]

    return None

def pick_col(cols, candidates):
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None

def clean_text(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s if s else None

REPO_ROOT = find_repo_root(Path.cwd())
RAW = REPO_ROOT / "data" / "rawdomains"
OUT = REPO_ROOT / "data" / "processed" / "overlays"
OUT.mkdir(parents=True, exist_ok=True)

services_csv = RAW / "youth" / "services_master.csv"
tracts_geojson = REPO_ROOT / "data" / "processed" / "boundaries" / "sd_tracts.geojson"
yoi_csv = REPO_ROOT / "data" / "processed" / "yoi" / "yoi_components.csv"
stops_geojson = REPO_ROOT / "data" / "processed" / "boundaries" / "transit_stops.geojson"

if not services_csv.exists():
    raise FileNotFoundError(f"Missing {services_csv}")

svc = pd.read_csv(services_csv, dtype=str)

lat_col = pick_col(svc.columns, ["lat", "latitude", "y"])
lon_col = pick_col(svc.columns, ["lon", "lng", "longitude", "x"])
if lat_col is None or lon_col is None:
    raise ValueError(
        f"Could not find latitude/longitude columns in services_master.csv. "
        f"Columns were: {svc.columns.tolist()}"
    )

tract_col = pick_col(svc.columns, ["tract_geoid", "GEOID", "geoid", "tract"])
name_col = pick_col(svc.columns, ["name", "site_name", "provider_name", "organization_name", "agency_name"])
type_col = pick_col(svc.columns, ["type", "category", "service_type", "organization_type"])
programs_col = pick_col(svc.columns, ["programs", "program", "services", "service", "focus_area"])
addr_col = pick_col(svc.columns, ["address", "street_address", "addr1", "full_address"])
city_col = pick_col(svc.columns, ["city", "municipality"])
source_col = pick_col(svc.columns, ["source", "data_source"])

svc["lat"] = pd.to_numeric(svc[lat_col], errors="coerce")
svc["lon"] = pd.to_numeric(svc[lon_col], errors="coerce")
svc = svc.dropna(subset=["lat", "lon"]).copy()

if tract_col:
    svc["tract_geoid"] = svc[tract_col].apply(normalize_geoid)
else:
    svc["tract_geoid"] = None

print("Sample normalized tract_geoid values:")
print(svc["tract_geoid"].dropna().head(10).tolist())
print("Rows with SD tract_geoid:", svc["tract_geoid"].astype(str).str.startswith("06073", na=False).sum())

gdf = gpd.GeoDataFrame(
    svc.copy(),
    geometry=gpd.points_from_xy(svc["lon"], svc["lat"]),
    crs="EPSG:4326"
)

# Fill missing tract_geoid by spatial join to SD tract polygons
if tracts_geojson.exists():
    tracts = gpd.read_file(tracts_geojson)[["tract_geoid", "geometry"]].copy()
    tracts["tract_geoid"] = tracts["tract_geoid"].astype(str)

    missing_mask = gdf["tract_geoid"].isna()
if missing_mask.any():
    joined = gpd.sjoin(
        gdf.loc[missing_mask, ["geometry"]],
        tracts,
        how="left",
        predicate="within"
    )
    gdf.loc[joined.index, "tract_geoid"] = joined["tract_geoid"]

# keep only San Diego County services
gdf = gdf[gdf["tract_geoid"].astype(str).str.startswith("06073", na=False)].copy()

# merge tract population from YOI output if available
if yoi_csv.exists():
    yoi = pd.read_csv(yoi_csv, dtype={"tract_geoid": str})
    if "total_population" in yoi.columns:
        pop = yoi[["tract_geoid", "total_population"]].copy()
        gdf = gdf.merge(pop, on="tract_geoid", how="left")
    else:
        gdf["total_population"] = None
else:
    gdf["total_population"] = None

# nearest transit stop if available
gdf["closest_stop_name"] = None
gdf["closest_stop_dist_m"] = None

if stops_geojson.exists():
    stops = gpd.read_file(stops_geojson).copy()
    if len(stops) > 0:
        stop_name_col = pick_col(stops.columns, ["stop_name", "name", "stop_id"])
        if stop_name_col is None:
            stops["stop_label"] = "Transit stop"
        else:
            stops["stop_label"] = stops[stop_name_col].astype(str)

        gdf_proj = gdf.to_crs(3310)
        stops_proj = stops.to_crs(3310)[["stop_label", "geometry"]].copy()

        nearest = gpd.sjoin_nearest(
            gdf_proj,
            stops_proj,
            how="left",
            distance_col="dist_m"
        )

        gdf["closest_stop_name"] = nearest["stop_label"].values
        gdf["closest_stop_dist_m"] = nearest["dist_m"].round().astype("Int64").astype(str).replace("<NA>", None)

# Final display fields
gdf["name"] = gdf[name_col].map(clean_text) if name_col else None
gdf["type"] = gdf[type_col].map(clean_text) if type_col else None
gdf["programs"] = gdf[programs_col].map(clean_text) if programs_col else None
gdf["address"] = gdf[addr_col].map(clean_text) if addr_col else None
gdf["city"] = gdf[city_col].map(clean_text) if city_col else None
gdf["source"] = gdf[source_col].map(clean_text) if source_col else "services_master"

keep = [
    "name",
    "type",
    "programs",
    "address",
    "city",
    "tract_geoid",
    "total_population",
    "closest_stop_name",
    "closest_stop_dist_m",
    "source",
    "geometry",
]

out = gdf[keep].copy()
out.to_file(OUT / "service_locations.geojson", driver="GeoJSON")

print("Saved:", OUT / "service_locations.geojson")
print("Rows:", len(out))
print(out.head())