from pathlib import Path
import re

import pandas as pd
import geopandas as gpd


REGION_BY_PUMA = {
    # Metro San Diego
    "7308": "Metro San Diego",
    "7310": "Metro San Diego",
    "7311": "Metro San Diego",
    "7312": "Metro San Diego",
    "7315": "Metro San Diego",
    "7316": "Metro San Diego",
    "7317": "Metro San Diego",
    "7327": "Metro San Diego",

    # North County
    "7301": "North County",
    "7306": "North County",
    "7323": "North County",
    "7324": "North County",
    "7325": "North County",
    "7326": "North County",

    # South San Diego
    "7322": "South San Diego",
    "7328": "South San Diego",
    "7329": "South San Diego",
    "7330": "South San Diego",

    # East San Diego
    "7302": "East San Diego",
    "7307": "East San Diego",
    "7313": "East San Diego",
    "7314": "East San Diego",
}


EXCLUDED_TRACT_GEOIDS = {
    "06073990100",  # Census tract 9901.00, water/ocean
    "06073990200",  # Census tract 9902.00, water/ocean
}

REGION_ID_BY_NAME = {
    "Metro San Diego": "metro_san_diego",
    "North County": "north_county",
    "South San Diego": "south_san_diego",
    "East San Diego": "east_san_diego",
}


def find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root containing /data")


def normalize_geoid(v):
    if pd.isna(v):
        return None

    digits = re.sub(r"\D", "", str(v))
    if not digits:
        return None

    if digits.startswith("06073") and len(digits) >= 11:
        return digits[:11]

    if len(digits) == 10:
        digits = digits.zfill(11)
        return digits if digits.startswith("06073") else None

    if len(digits) == 11:
        return digits if digits.startswith("06073") else None

    match = re.search(r"06073\d{6}", digits)
    if match:
        return match.group(0)

    return None


def read_tract_to_region_crosswalk(path: Path) -> pd.DataFrame:
    xwalk = pd.read_csv(path, dtype=str)

    required = {"STATEFP", "COUNTYFP", "TRACTCE", "PUMA5CE"}
    missing = required - set(xwalk.columns)
    if missing:
        raise ValueError(f"Crosswalk missing columns: {missing}")

    xwalk["STATEFP"] = xwalk["STATEFP"].astype(str).str.zfill(2)
    xwalk["COUNTYFP"] = xwalk["COUNTYFP"].astype(str).str.zfill(3)
    xwalk["TRACTCE"] = xwalk["TRACTCE"].astype(str).str.zfill(6)

    # San Diego County only: CA = 06, San Diego County = 073.
    xwalk = xwalk[
        (xwalk["STATEFP"] == "06") &
        (xwalk["COUNTYFP"] == "073")
    ].copy()

    xwalk["tract_geoid"] = (
        xwalk["STATEFP"] +
        xwalk["COUNTYFP"] +
        xwalk["TRACTCE"]
    )

    # Census PUMA file may store this as 07308; report table uses 7308.
    xwalk["puma_code"] = (
        xwalk["PUMA5CE"]
        .astype(str)
        .str.replace(r"\D", "", regex=True)
        .str.zfill(5)
        .str[-4:]
    )

    xwalk["county_region"] = xwalk["puma_code"].map(REGION_BY_PUMA)
    xwalk["county_region_id"] = xwalk["county_region"].map(REGION_ID_BY_NAME)

    xwalk = xwalk.dropna(subset=["county_region", "county_region_id"]).copy()

    return xwalk[["tract_geoid", "puma_code", "county_region", "county_region_id"]]


def weighted_average(group, col, weight_col):
    values = pd.to_numeric(group[col], errors="coerce")
    weights = pd.to_numeric(group[weight_col], errors="coerce").fillna(0)

    mask = values.notna() & weights.gt(0)

    if mask.any():
        return (values[mask] * weights[mask]).sum() / weights[mask].sum()

    return values.mean()


def aggregate_yoi_to_regions(yoi: pd.DataFrame) -> pd.DataFrame:
    yoi = yoi.copy()

    if "total_population" in yoi.columns:
        yoi["_weight"] = pd.to_numeric(yoi["total_population"], errors="coerce").fillna(0)
    else:
        yoi["_weight"] = 1.0

    numeric_cols = [
        c for c in yoi.columns
        if c not in {
            "tract_geoid",
            "puma_code",
            "county_region",
            "county_region_id",
        }
        and pd.to_numeric(yoi[c], errors="coerce").notna().any()
    ]

    rows = []

    for region_id, group in yoi.groupby("county_region_id"):
        row = {
            "county_region_id": region_id,
            "county_region": group["county_region"].iloc[0],
            "tract_count": len(group),
            "puma_codes": ", ".join(sorted(group["puma_code"].dropna().unique())),
        }

        if "total_population" in group.columns:
            row["total_population"] = pd.to_numeric(
                group["total_population"],
                errors="coerce"
            ).fillna(0).sum()

        for col in numeric_cols:
            if col in {"total_population", "_weight"}:
                continue

            row[col] = weighted_average(group, col, "_weight")

        rows.append(row)

    out = pd.DataFrame(rows)

    # Recompute custom YOI from domain scores if possible.
    domain_cols = [
        "economic_score",
        "education_score",
        "health_score",
        "housing_score",
        "safety_env_score",
        "mobility_connectivity_score",
        "youth_supports_score",
    ]

    if all(c in out.columns for c in domain_cols):
        out["yoi_custom_0_1"] = out[domain_cols].mean(axis=1)
        out["yoi_custom_0_100"] = out["yoi_custom_0_1"] * 100
        out["yoi_0_100"] = out["yoi_custom_0_100"]

    return out


def build_region_boundaries(tracts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    region_boundaries = tracts.dissolve(
        by=["county_region_id", "county_region"],
        as_index=False
    )

    # Optional: simplify slightly for browser performance.
    region_boundaries = region_boundaries.to_crs(3310)
    region_boundaries["geometry"] = region_boundaries.geometry.simplify(
        tolerance=20,
        preserve_topology=True
    )
    region_boundaries = region_boundaries.to_crs(4326)

    return region_boundaries


def main():
    repo = find_repo_root(Path.cwd())

    crosswalk_path = repo / "data/rawdomains/regions/2020_Census_Tract_to_2020_PUMA.txt"
    tracts_path = repo / "data/processed/boundaries/sd_tracts.geojson"
    yoi_path = repo / "data/processed/yoi/yoi_components.csv"

    out_overlay = repo / "data/processed/overlays/county_regions.geojson"
    out_yoi = repo / "data/processed/yoi/yoi_county_region_components.csv"

    out_overlay.parent.mkdir(parents=True, exist_ok=True)
    out_yoi.parent.mkdir(parents=True, exist_ok=True)

    if not crosswalk_path.exists():
        raise FileNotFoundError(f"Missing crosswalk: {crosswalk_path}")

    if not tracts_path.exists():
        raise FileNotFoundError(f"Missing tract boundaries: {tracts_path}")

    if not yoi_path.exists():
        raise FileNotFoundError(f"Missing YOI components: {yoi_path}")

    crosswalk = read_tract_to_region_crosswalk(crosswalk_path)

    print("San Diego tract-to-region crosswalk rows:", len(crosswalk))
    print(crosswalk.groupby(["county_region", "puma_code"]).size())

    tracts = gpd.read_file(tracts_path)
    if tracts.crs is None:
        tracts = tracts.set_crs("EPSG:4326")

    if "tract_geoid" not in tracts.columns:
        raise ValueError("sd_tracts.geojson must have tract_geoid column")

    tracts["tract_geoid"] = tracts["tract_geoid"].apply(normalize_geoid)

    # Remove ocean / water tract before dissolving into county regions.
    tracts = tracts[
        ~tracts["tract_geoid"].isin(EXCLUDED_TRACT_GEOIDS)
    ].copy()

    tracts = tracts.merge(crosswalk, on="tract_geoid", how="left")

    missing_region = tracts["county_region"].isna().sum()
    print("Tract polygons missing county region:", missing_region)

    tracts = tracts.dropna(subset=["county_region", "county_region_id"]).copy()

    region_boundaries = build_region_boundaries(tracts)
    region_boundaries.to_file(out_overlay, driver="GeoJSON")

    print("Saved:", out_overlay)
    print("County region boundary rows:", len(region_boundaries))

    yoi = pd.read_csv(yoi_path, dtype={"tract_geoid": str})
    yoi["tract_geoid"] = yoi["tract_geoid"].apply(normalize_geoid)

    # Remove ocean / water tract from county region aggregation too.
    yoi = yoi[
        ~yoi["tract_geoid"].isin(EXCLUDED_TRACT_GEOIDS)
    ].copy()

    yoi = yoi.merge(crosswalk, on="tract_geoid", how="left")

    missing_yoi_region = yoi["county_region"].isna().sum()
    print("YOI rows missing county region:", missing_yoi_region)

    yoi = yoi.dropna(subset=["county_region", "county_region_id"]).copy()

    region_yoi = aggregate_yoi_to_regions(yoi)
    region_yoi.to_csv(out_yoi, index=False)

    print("Saved:", out_yoi)
    print(region_yoi[[
        "county_region_id",
        "county_region",
        "tract_count",
        "puma_codes",
        "total_population",
        "yoi_custom_0_100",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()