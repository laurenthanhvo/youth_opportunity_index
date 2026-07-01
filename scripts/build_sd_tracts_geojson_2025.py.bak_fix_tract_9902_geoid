from pathlib import Path
import geopandas as gpd

def find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root")

REPO_ROOT = find_repo_root(Path.cwd())
RAW = REPO_ROOT / "data" / "rawdomains" / "boundaries_2025"
OUT = REPO_ROOT / "data" / "processed" / "boundaries"
OUT.mkdir(parents=True, exist_ok=True)

# find the shapefile
shp = next(RAW.glob("*.shp"))

gdf = gpd.read_file(shp)

# California = 06, San Diego County = 073
gdf["STATEFP"] = gdf["STATEFP"].astype(str).str.zfill(2)
gdf["COUNTYFP"] = gdf["COUNTYFP"].astype(str).str.zfill(3)

sd = gdf[(gdf["STATEFP"] == "06") & (gdf["COUNTYFP"] == "073")].copy()

# use TIGER GEOID directly
sd["tract_geoid"] = sd["GEOID"].astype(str)

# Leaflet/browser wants lat/lon
if sd.crs is not None:
    sd = sd.to_crs(epsg=4326)

sd[["tract_geoid", "geometry"]].to_file(
    OUT / "sd_tracts.geojson",
    driver="GeoJSON"
)

print("Saved:", OUT / "sd_tracts.geojson")
print("Rows:", len(sd))
print(sd[["tract_geoid"]].head())