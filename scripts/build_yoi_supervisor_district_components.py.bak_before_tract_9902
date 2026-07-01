from pathlib import Path
import re
import numpy as np
import pandas as pd
import geopandas as gpd

TRACT_CSV = Path("data/processed/yoi/yoi_components.csv")
TRACT_GEOJSON = Path("data/processed/boundaries/sd_tracts.geojson")
DISTRICT_GEOJSON = Path("data/processed/overlays/supervisor_districts.geojson")
OUT_CSV = Path("data/processed/yoi/yoi_supervisor_district_components.csv")

TRACT_ID_COL = "tract_geoid"
POP_COL = "total_population"

OVERALL_INPUT_CANDIDATES = ["yoi_custom_0_100", "yoi_0_100"]

DOMAIN_SCORE_COLS = [
    "economic_score",
    "education_score",
    "health_score",
    "housing_score",
    "safety_env_score",
    "mobility_connectivity_score",
    "youth_supports_score",
]

DISTRICT_FIELD_CANDIDATES = [
    "distno", "DISTNO", "district", "District", "DISTRICT", "id", "ID"
]

OCEAN_TRACT_IDS = {
    "06073990100",
    "990100",
    "9901.00",
}

PROJECTED_CRS = "EPSG:3310"


def normalize_tract(v):
    if pd.isna(v):
        return None
    digits = re.sub(r"\D", "", str(v))
    if not digits:
        return None
    return digits.zfill(11)[-11:]


def normalize_district(v):
    if pd.isna(v):
        return None
    digits = re.sub(r"\D", "", str(v))
    return digits if digits else str(v).strip()


def find_district_field(gdf):
    for c in DISTRICT_FIELD_CANDIDATES:
        if c in gdf.columns:
            return c
    raise ValueError(
        f"Could not find supervisor district field. Looked for {DISTRICT_FIELD_CANDIDATES}. "
        f"Found columns: {list(gdf.columns)}"
    )


def weighted_mean(values, weights):
    mask = (~pd.isna(values)) & (~pd.isna(weights)) & (weights > 0)
    if mask.sum() == 0:
        return np.nan
    v = values[mask].astype(float)
    w = weights[mask].astype(float)
    return np.average(v, weights=w)


def main():
    if not TRACT_CSV.exists():
        raise FileNotFoundError(f"Missing {TRACT_CSV}")
    if not TRACT_GEOJSON.exists():
        raise FileNotFoundError(f"Missing {TRACT_GEOJSON}")
    if not DISTRICT_GEOJSON.exists():
        raise FileNotFoundError(f"Missing {DISTRICT_GEOJSON}")

    tract_scores = pd.read_csv(TRACT_CSV)

    overall_input_col = next(
        (c for c in OVERALL_INPUT_CANDIDATES if c in tract_scores.columns),
        None,
    )

    required = [TRACT_ID_COL, POP_COL] + DOMAIN_SCORE_COLS
    missing = [c for c in required if c not in tract_scores.columns]
    if missing:
        raise ValueError(
            f"Your tract CSV is missing required columns: {missing}\n"
            f"Available columns: {list(tract_scores.columns)}"
        )

    if overall_input_col is None:
        raise ValueError(
            f"Your tract CSV is missing an overall YOI column. "
            f"Expected one of: {OVERALL_INPUT_CANDIDATES}\n"
            f"Available columns: {list(tract_scores.columns)}"
        )

    tract_scores[TRACT_ID_COL] = tract_scores[TRACT_ID_COL].map(normalize_tract)
    tract_scores = tract_scores[~tract_scores[TRACT_ID_COL].isin({None, ""})].copy()

    ocean_ids = {normalize_tract(x) for x in OCEAN_TRACT_IDS if x is not None}
    tract_scores = tract_scores[~tract_scores[TRACT_ID_COL].isin(ocean_ids)].copy()

    tracts = gpd.read_file(TRACT_GEOJSON)
    if TRACT_ID_COL not in tracts.columns:
        raise ValueError(
            f"{TRACT_GEOJSON} must contain '{TRACT_ID_COL}'. "
            f"Found columns: {list(tracts.columns)}"
        )

    tracts[TRACT_ID_COL] = tracts[TRACT_ID_COL].map(normalize_tract)
    tracts = tracts[~tracts[TRACT_ID_COL].isin({None, ""})].copy()
    tracts = tracts[~tracts[TRACT_ID_COL].isin(ocean_ids)].copy()

    value_cols_for_merge = [
    c for c in tract_scores.columns
    if c not in {TRACT_ID_COL, POP_COL}
    and pd.api.types.is_numeric_dtype(tract_scores[c])
]
    tracts = tracts[[TRACT_ID_COL, "geometry"]].merge(
    tract_scores[[TRACT_ID_COL, POP_COL] + value_cols_for_merge],
    on=TRACT_ID_COL,
    how="inner",
    )

    districts = gpd.read_file(DISTRICT_GEOJSON)
    district_field = find_district_field(districts)
    districts["distno"] = districts[district_field].map(normalize_district)
    districts = districts[~districts["distno"].isin({None, ""})].copy()
    districts = districts[["distno", "geometry"]].copy()

    tracts = tracts.to_crs(PROJECTED_CRS)
    districts = districts.to_crs(PROJECTED_CRS)

    tracts["tract_area"] = tracts.geometry.area

    inter = gpd.overlay(
    tracts[[TRACT_ID_COL, POP_COL] + value_cols_for_merge + ["tract_area", "geometry"]],
    districts[["distno", "geometry"]],
    how="intersection",
    keep_geom_type=False,
    )

    if inter.empty:
        raise ValueError("Tract/supervisor-district intersection produced no rows.")

    inter["intersect_area"] = inter.geometry.area
    inter["area_share"] = inter["intersect_area"] / inter["tract_area"]
    inter["weighted_pop"] = inter[POP_COL].fillna(0) * inter["area_share"]

    rows = []
    for distno, g in inter.groupby("distno", dropna=True):
        total_pop = g["weighted_pop"].sum()

        row = {
            "distno": distno,
            "total_population": round(total_pop, 2),
        }

        use_weights = g["weighted_pop"].values
        fallback_weights = g["area_share"].values

        for col in value_cols_for_merge:
            val = weighted_mean(g[col].values, use_weights)
            if pd.isna(val):
                val = weighted_mean(g[col].values, fallback_weights)
            row[col] = val

        rows.append(row)

    out = pd.DataFrame(rows).sort_values("distno").reset_index(drop=True)

    if overall_input_col != "yoi_custom_0_100":
        out["yoi_custom_0_100"] = out[overall_input_col]
    if overall_input_col != "yoi_0_100":
        out["yoi_0_100"] = out[overall_input_col]

    preferred_order = [
    "distno",
    "total_population",
    "yoi_custom_0_100",
    "yoi_0_100",
    "economic_score",
    "education_score",
    "health_score",
    "housing_score",
    "safety_env_score",
    "mobility_connectivity_score",
    "youth_supports_score",
]

    remaining_cols = [c for c in out.columns if c not in preferred_order]
    out = out[[c for c in preferred_order if c in out.columns] + remaining_cols]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    print(f"Wrote {OUT_CSV}")
    print(out.head())


if __name__ == "__main__":
    main()