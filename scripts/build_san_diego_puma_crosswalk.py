from pathlib import Path
import geopandas as gpd
import pandas as pd

RAW_DIR = Path("data/raw/census/geography")
OUT_DIR = Path("data/processed/workforce")
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

PUMA_ZIP = RAW_DIR / "tl_2024_06_puma20.zip"
COUNTY_ZIP = RAW_DIR / "tl_2024_us_county.zip"

if not PUMA_ZIP.exists():
    raise FileNotFoundError(f"Missing {PUMA_ZIP}")

if not COUNTY_ZIP.exists():
    raise FileNotFoundError(f"Missing {COUNTY_ZIP}")

print("Reading local Census PUMA and county boundaries...")

pumas = gpd.read_file(PUMA_ZIP)
counties = gpd.read_file(COUNTY_ZIP)

print("PUMA columns:", list(pumas.columns))
print("County columns:", list(counties.columns))

sd_county = counties[
    (counties["STATEFP"].astype(str).str.zfill(2) == "06") &
    (counties["COUNTYFP"].astype(str).str.zfill(3) == "073")
].copy()

if sd_county.empty:
    raise ValueError("Could not find San Diego County in county shapefile.")

# Use projected CRS for area calculations.
pumas_proj = pumas.to_crs("EPSG:3310")
sd_proj = sd_county.to_crs("EPSG:3310")

pumas_proj["puma_area"] = pumas_proj.geometry.area

intersection = gpd.overlay(
    pumas_proj,
    sd_proj[["GEOID", "NAME", "geometry"]],
    how="intersection"
)

intersection["intersection_area"] = intersection.geometry.area
intersection["area_share_in_sd_county"] = (
    intersection["intersection_area"] / intersection["puma_area"]
)

# Keep PUMAs that materially overlap San Diego County.
sd_pumas = intersection[
    intersection["area_share_in_sd_county"] >= 0.05
].copy()

sd_pumas["state"] = "06"
sd_pumas["puma"] = sd_pumas["PUMACE20"].astype(str).str.zfill(5)
sd_pumas["puma_geoid"] = sd_pumas["GEOID20"].astype(str)

if "NAMELSAD20" in sd_pumas.columns:
    sd_pumas["puma_name"] = sd_pumas["NAMELSAD20"].astype(str)
elif "NAME20" in sd_pumas.columns:
    sd_pumas["puma_name"] = sd_pumas["NAME20"].astype(str)
else:
    sd_pumas["puma_name"] = ""

out = (
    sd_pumas[[
        "state",
        "puma",
        "puma_geoid",
        "puma_name",
        "area_share_in_sd_county",
    ]]
    .drop_duplicates()
    .sort_values("puma")
)

out_path = OUT_DIR / "san_diego_puma_crosswalk.csv"
out.to_csv(out_path, index=False)

print()
print(f"Saved: {out_path}")
print(f"Rows: {len(out)}")
print(out)