import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd


def find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root (a parent directory containing /data).")


def sd_geoid11_from_tract_like(x, county_fips="06073"):
    """
    Handles CES 'Tract' values like 6083002103.0 and turns them into 06073 + tract(6).
    """
    if pd.isna(x):
        return None

    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]

    digits = re.sub(r"\D", "", s)

    # Already a full 11-digit GEOID
    if len(digits) == 11:
        return digits

    # 10-digit missing leading 0 (common)
    if len(digits) == 10:
        return digits.zfill(11)

    # CES-style CA "Tract" codes often look like 6083002103 (10 digits) or 60830021030 (11 digits)
    # If we got 11+ digits, last 6 are tract, but safer: if starts with 6 and long, try:
    if len(digits) >= 10:
        # If it looks like CA+county+tract without leading zero
        if digits.startswith("6073") and len(digits) >= 10:
            return digits.zfill(11)
        # Otherwise, treat last 6 as tract code
        tract6 = digits[-6:]
        return county_fips + tract6

    # tract-only (<=6)
    if 1 <= len(digits) <= 6:
        return county_fips + digits.zfill(6)

    return None


def main():
    repo = find_repo_root(Path.cwd())
    shp = repo / "data/rawdomains/safety/calenviroscreen40shpf2021shp/CES4 Final Shapefile.shp"
    out_dir = repo / "data/processed/boundaries"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sd_tracts.geojson"

    if not shp.exists():
        raise FileNotFoundError(f"Missing shapefile: {shp}")

    gdf = gpd.read_file(shp)

    # Find tract column
    tract_col = None
    for cand in ["Tract", "TRACT", "GEOID", "geoid", "FIPS", "fips"]:
        if cand in gdf.columns:
            tract_col = cand
            break
    if tract_col is None:
        for c in gdf.columns:
            if "tract" in c.lower() or "geoid" in c.lower():
                tract_col = c
                break
    if tract_col is None:
        raise ValueError(f"Could not find tract id column. Columns: {list(gdf.columns)}")

    print("Using tract_col =", tract_col)
    print("Sample tract_col values:", gdf[tract_col].head(10).tolist())

    gdf["tract_geoid"] = gdf[tract_col].map(sd_geoid11_from_tract_like).astype("string")
    gdf = gdf[gdf["tract_geoid"].notna()].copy()
    gdf = gdf[gdf["tract_geoid"].str.startswith("06073")].copy()

    print("SD tracts:", len(gdf))
    if len(gdf) == 0:
        raise RuntimeError("0 SD tracts after filtering. Something is off with tract parsing.")

    # IMPORTANT: reproject to lat/lon for Leaflet/Folium
    if gdf.crs is None:
        print("WARNING: shapefile CRS is None. Check the .prj file. Attempting to continue.")
    else:
        gdf = gdf.to_crs(epsg=4326)

    # Fix invalid geometries
    try:
        gdf["geometry"] = gdf["geometry"].buffer(0)
    except Exception:
        pass

    # IMPORTANT: Leaflet needs EPSG:4326
    if gdf.crs is not None:
        gdf = gdf.to_crs(epsg=4326)
    else:
        pass

    gdf[["tract_geoid", "geometry"]].to_file(out_dir / "sd_tracts.geojson", driver="GeoJSON")
    print("Wrote:", out_dir / "sd_tracts.geojson")

    gdf[["tract_geoid", "geometry"]].to_file(out_path, driver="GeoJSON")
    print("Wrote:", out_path)

    # sanity check: ensure features exist
    geo = json.loads(out_path.read_text())
    print("GeoJSON feature count:", len(geo.get("features", [])))


if __name__ == "__main__":
    main()