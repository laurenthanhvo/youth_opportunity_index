"""
Compare San Diego Youth Opportunity Index results with and without
military-installation ZIP codes.

Run from the project root:

    python scripts/compare_with_without_military.py

Outputs:
    data/processed/military_sensitivity/
        military_zip_rows.csv
        military_tract_assignments.csv
        yoi_zip_components_no_military.csv
        yoi_components_no_military.csv
        overall_comparison.csv
        metric_comparison.csv
        military_area_summary.csv

Important:
This script analyzes already-processed scores. It does not recompute the
underlying normalization. See the printed warning after execution.
"""

from __future__ import annotations

from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

TRACT_CSV = ROOT / "data/processed/yoi/yoi_components.csv"
ZIP_CSV = ROOT / "data/processed/yoi/yoi_zip_components.csv"

TRACT_GEOJSON = ROOT / "data/processed/boundaries/sd_tracts.geojson"
ZIP_GEOJSON = ROOT / "data/processed/boundaries/sd_zip_codes.geojson"

OUTPUT_DIR = ROOT / "data/processed/military_sensitivity"


# Project-defined military ZIP exclusion list.
MILITARY_ZIPS = {
    "92055",  # Marine Corps Base Camp Pendleton
    "92135",  # Naval Base Point Loma
    "92136",  # Naval Base San Diego
    "92140",  # Marine Corps Recruit Depot San Diego
    "92145",  # Marine Corps Air Station Miramar
    "92153",  # Naval Base Coronado / NAS North Island
}


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def normalize_zip(value: object) -> str:
    """Convert a ZIP-like value into a five-character ZIP string."""
    if pd.isna(value):
        return ""

    digits = "".join(character for character in str(value) if character.isdigit())

    if not digits:
        return ""

    return digits[:5].zfill(5)


def normalize_geoid(value: object) -> str:
    """Convert a tract GEOID-like value into an 11-character GEOID."""
    if pd.isna(value):
        return ""

    digits = "".join(character for character in str(value) if character.isdigit())

    if not digits:
        return ""

    return digits[-11:].zfill(11)


def find_column(
    dataframe: pd.DataFrame,
    candidates: list[str],
    description: str,
) -> str:
    """Return the first matching column name."""
    lower_to_original = {
        column.lower(): column
        for column in dataframe.columns
    }

    for candidate in candidates:
        if candidate.lower() in lower_to_original:
            return lower_to_original[candidate.lower()]

    raise KeyError(
        f"Could not find the {description} column.\n"
        f"Tried: {candidates}\n"
        f"Available columns: {list(dataframe.columns)}"
    )


def numeric_metric_columns(dataframe: pd.DataFrame) -> list[str]:
    """
    Select useful numeric score columns.

    Raw population counts are intentionally excluded from the primary
    metric comparison.
    """
    preferred_patterns = (
        "_score",
        "yoi_",
        "_rate",
        "_share",
        "_pct",
        "_percent",
    )

    excluded_patterns = (
        "geoid",
        "zip",
        "population",
        "_pop",
        "count",
        "rank",
        "percentile",
    )

    columns: list[str] = []

    for column in dataframe.columns:
        lower = column.lower()

        if any(pattern in lower for pattern in excluded_patterns):
            continue

        if not any(pattern in lower for pattern in preferred_patterns):
            continue

        converted = pd.to_numeric(dataframe[column], errors="coerce")

        if converted.notna().any():
            columns.append(column)

    return columns


def summarize_distribution(
    dataframe: pd.DataFrame,
    metric: str,
    version: str,
    geography: str,
) -> dict[str, object]:
    """Calculate distribution statistics for one metric."""
    values = pd.to_numeric(dataframe[metric], errors="coerce").dropna()

    return {
        "geography": geography,
        "version": version,
        "metric": metric,
        "n_areas": len(values),
        "mean": values.mean() if len(values) else np.nan,
        "median": values.median() if len(values) else np.nan,
        "minimum": values.min() if len(values) else np.nan,
        "maximum": values.max() if len(values) else np.nan,
        "standard_deviation": values.std() if len(values) > 1 else np.nan,
    }


def compare_metrics(
    all_rows: pd.DataFrame,
    nonmilitary_rows: pd.DataFrame,
    geography: str,
) -> pd.DataFrame:
    """Compare each numeric metric before and after exclusion."""
    metrics = numeric_metric_columns(all_rows)
    records: list[dict[str, object]] = []

    for metric in metrics:
        with_military = summarize_distribution(
            all_rows,
            metric,
            "with_military",
            geography,
        )
        without_military = summarize_distribution(
            nonmilitary_rows,
            metric,
            "without_military",
            geography,
        )

        records.extend([with_military, without_military])

    long_table = pd.DataFrame(records)

    if long_table.empty:
        return long_table

    wide = long_table.pivot(
        index=["geography", "metric"],
        columns="version",
        values=[
            "n_areas",
            "mean",
            "median",
            "minimum",
            "maximum",
            "standard_deviation",
        ],
    )

    wide.columns = [
        f"{statistic}_{version}"
        for statistic, version in wide.columns
    ]
    wide = wide.reset_index()

    for statistic in (
        "mean",
        "median",
        "minimum",
        "maximum",
        "standard_deviation",
    ):
        with_column = f"{statistic}_with_military"
        without_column = f"{statistic}_without_military"

        if with_column in wide and without_column in wide:
            wide[f"{statistic}_change"] = (
                wide[without_column] - wide[with_column]
            )

    return wide


# ---------------------------------------------------------------------
# Spatial ZIP assignment
# ---------------------------------------------------------------------

def assign_tracts_to_zips(
    tract_geojson: Path,
    zip_geojson: Path,
) -> pd.DataFrame:
    """
    Assign each tract to a ZIP polygon using its representative point.

    Representative points are preferred over centroids because they are
    guaranteed to fall inside the tract geometry.
    """
    tracts = gpd.read_file(tract_geojson)
    zip_polygons = gpd.read_file(zip_geojson)

    tract_geoid_column = find_column(
        tracts,
        [
            "tract_geoid",
            "GEOID",
            "geoid",
            "GEOID20",
            "TRACT",
        ],
        "tract GEOID",
    )

    zip_column = find_column(
        zip_polygons,
        [
            "zip",
            "ZIP",
            "zip_code",
            "ZIPCODE",
            "ZCTA5CE20",
            "GEOID20",
            "GEOID",
        ],
        "ZIP",
    )

    if tracts.crs is None:
        raise ValueError("The tract GeoJSON has no coordinate reference system.")

    if zip_polygons.crs is None:
        raise ValueError("The ZIP GeoJSON has no coordinate reference system.")

    if tracts.crs != zip_polygons.crs:
        zip_polygons = zip_polygons.to_crs(tracts.crs)

    tract_points = tracts[
        [tract_geoid_column, "geometry"]
    ].copy()

    tract_points["tract_geoid"] = tract_points[
        tract_geoid_column
    ].map(normalize_geoid)

    tract_points["geometry"] = tract_points.geometry.representative_point()

    zip_polygons = zip_polygons[
        [zip_column, "geometry"]
    ].copy()

    zip_polygons["zip"] = zip_polygons[zip_column].map(normalize_zip)

    joined = gpd.sjoin(
        tract_points[["tract_geoid", "geometry"]],
        zip_polygons[["zip", "geometry"]],
        how="left",
        predicate="within",
    )

    # In case overlapping ZIP polygons produce duplicates, retain one row
    # for each tract.
    joined = (
        joined
        .drop(columns=["index_right"], errors="ignore")
        .drop_duplicates(subset=["tract_geoid"])
    )

    joined["is_military_zip"] = joined["zip"].isin(MILITARY_ZIPS)

    return pd.DataFrame(
        joined.drop(columns="geometry")
    )


# ---------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------

def main() -> None:
    required_files = [
        TRACT_CSV,
        ZIP_CSV,
        TRACT_GEOJSON,
        ZIP_GEOJSON,
    ]

    missing_files = [path for path in required_files if not path.exists()]

    if missing_files:
        print("The following required files were not found:", file=sys.stderr)

        for path in missing_files:
            print(f"  - {path.relative_to(ROOT)}", file=sys.stderr)

        print(
            "\nRun the scripts that build your current processed YOI files first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tract_rows = pd.read_csv(
        TRACT_CSV,
        dtype={"tract_geoid": str},
        low_memory=False,
    )
    zip_rows = pd.read_csv(
        ZIP_CSV,
        dtype=str,
        low_memory=False,
    )

    tract_geoid_column = find_column(
        tract_rows,
        ["tract_geoid", "GEOID", "geoid"],
        "tract GEOID",
    )
    zip_column = find_column(
        zip_rows,
        ["zip", "ZIP", "zcta", "zip_code"],
        "ZIP",
    )

    tract_rows["tract_geoid"] = tract_rows[
        tract_geoid_column
    ].map(normalize_geoid)

    zip_rows["zip"] = zip_rows[zip_column].map(normalize_zip)

    # Restore numeric columns in the ZIP data after reading ZIP as text.
    for column in zip_rows.columns:
        if column == "zip":
            continue

        converted = pd.to_numeric(zip_rows[column], errors="coerce")

        if converted.notna().sum() > 0:
            zip_rows[column] = converted

    # -------------------------------------------------------------
    # ZIP-level removal
    # -------------------------------------------------------------

    zip_rows["is_military_zip"] = zip_rows["zip"].isin(MILITARY_ZIPS)

    military_zip_rows = zip_rows.loc[
        zip_rows["is_military_zip"]
    ].copy()

    nonmilitary_zip_rows = zip_rows.loc[
        ~zip_rows["is_military_zip"]
    ].copy()

    # -------------------------------------------------------------
    # Tract-level removal
    # -------------------------------------------------------------

    tract_zip_assignments = assign_tracts_to_zips(
        TRACT_GEOJSON,
        ZIP_GEOJSON,
    )

    tract_rows = tract_rows.merge(
        tract_zip_assignments,
        on="tract_geoid",
        how="left",
        validate="one_to_one",
    )

    tract_rows["is_military_zip"] = (
        tract_rows["is_military_zip"]
        .fillna(False)
        .astype(bool)
    )

    military_tract_rows = tract_rows.loc[
        tract_rows["is_military_zip"]
    ].copy()

    nonmilitary_tract_rows = tract_rows.loc[
        ~tract_rows["is_military_zip"]
    ].copy()

    # -------------------------------------------------------------
    # Comparisons
    # -------------------------------------------------------------

    zip_comparison = compare_metrics(
        zip_rows,
        nonmilitary_zip_rows,
        geography="ZIP code",
    )

    tract_comparison = compare_metrics(
        tract_rows,
        nonmilitary_tract_rows,
        geography="Census tract",
    )

    metric_comparison = pd.concat(
        [tract_comparison, zip_comparison],
        ignore_index=True,
    )

    overall_candidates = [
        "yoi_0_100",
        "yoi_custom_0_100",
        "yoi_raw_0_1",
    ]

    overall_metrics = [
        metric
        for metric in overall_candidates
        if metric in tract_rows.columns or metric in zip_rows.columns
    ]

    overall_comparison = metric_comparison.loc[
        metric_comparison["metric"].isin(overall_metrics)
    ].copy()

    military_area_summary = pd.DataFrame(
        [
            {
                "geography": "ZIP code",
                "all_area_count": len(zip_rows),
                "military_area_count": len(military_zip_rows),
                "remaining_area_count": len(nonmilitary_zip_rows),
                "removed_share": (
                    len(military_zip_rows) / len(zip_rows)
                    if len(zip_rows)
                    else np.nan
                ),
            },
            {
                "geography": "Census tract",
                "all_area_count": len(tract_rows),
                "military_area_count": len(military_tract_rows),
                "remaining_area_count": len(nonmilitary_tract_rows),
                "removed_share": (
                    len(military_tract_rows) / len(tract_rows)
                    if len(tract_rows)
                    else np.nan
                ),
            },
        ]
    )

    # -------------------------------------------------------------
    # Save outputs
    # -------------------------------------------------------------

    military_zip_rows.to_csv(
        OUTPUT_DIR / "military_zip_rows.csv",
        index=False,
    )

    tract_zip_assignments.to_csv(
        OUTPUT_DIR / "military_tract_assignments.csv",
        index=False,
    )

    nonmilitary_zip_rows.drop(
        columns=["is_military_zip"],
        errors="ignore",
    ).to_csv(
        OUTPUT_DIR / "yoi_zip_components_no_military.csv",
        index=False,
    )

    nonmilitary_tract_rows.drop(
        columns=["zip", "is_military_zip"],
        errors="ignore",
    ).to_csv(
        OUTPUT_DIR / "yoi_components_no_military.csv",
        index=False,
    )

    metric_comparison.to_csv(
        OUTPUT_DIR / "metric_comparison.csv",
        index=False,
    )

    overall_comparison.to_csv(
        OUTPUT_DIR / "overall_comparison.csv",
        index=False,
    )

    military_area_summary.to_csv(
        OUTPUT_DIR / "military_area_summary.csv",
        index=False,
    )

    # -------------------------------------------------------------
    # Console report
    # -------------------------------------------------------------

    print("\nMilitary ZIPs requested for exclusion:")
    print(", ".join(sorted(MILITARY_ZIPS)))

    print("\nMilitary ZIPs found in the processed ZIP CSV:")
    found_zips = sorted(military_zip_rows["zip"].dropna().unique())
    print(", ".join(found_zips) if found_zips else "None")

    missing_zips = sorted(MILITARY_ZIPS - set(found_zips))

    if missing_zips:
        print("\nListed military ZIPs not present in the ZIP CSV:")
        print(", ".join(missing_zips))
        print(
            "This may mean the ZIP boundary file uses Census ZCTAs and does "
            "not include ZIPs used only for mail delivery."
        )

    print("\nRemoval counts:")
    print(military_area_summary.to_string(index=False))

    if not overall_comparison.empty:
        print("\nOverall YOI comparison:")
        display_columns = [
            column
            for column in [
                "geography",
                "metric",
                "n_areas_with_military",
                "n_areas_without_military",
                "mean_with_military",
                "mean_without_military",
                "mean_change",
                "median_with_military",
                "median_without_military",
                "median_change",
            ]
            if column in overall_comparison.columns
        ]

        print(
            overall_comparison[display_columns]
            .round(4)
            .to_string(index=False)
        )

    print(f"\nSaved outputs to:\n  {OUTPUT_DIR.relative_to(ROOT)}")

    print(
        "\nIMPORTANT:\n"
        "These files compare and filter your existing processed scores. "
        "They do not rebuild indicator normalization after excluding military "
        "areas. If your indicators were county-normalized, the final publication "
        "version should exclude military areas before normalization and then "
        "rerun your YOI processing pipeline."
    )


if __name__ == "__main__":
    main()