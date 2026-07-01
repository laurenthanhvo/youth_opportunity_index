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


EXCLUDED_TRACT_GEOIDS = {"06073990100"}


# Workforce report Figure 22 benchmark totals.
# These are "number of sites offering service category", not necessarily unique physical sites.
REPORT_SERVICE_BENCHMARKS = {
    "Metro San Diego": {
        "report_education_service_sites": 175,
        "report_employment_service_sites": 154,
        "report_wraparound_service_sites": 230,
    },
    "North County": {
        "report_education_service_sites": 72,
        "report_employment_service_sites": 71,
        "report_wraparound_service_sites": 99,
    },
    "South San Diego": {
        "report_education_service_sites": 39,
        "report_employment_service_sites": 35,
        "report_wraparound_service_sites": 59,
    },
    "East San Diego": {
        "report_education_service_sites": 42,
        "report_employment_service_sites": 29,
        "report_wraparound_service_sites": 61,
    },
}


# Workforce report Figure 10 benchmark outcomes.
REPORT_OUTCOME_BENCHMARKS = {
    "Metro San Diego": {
        "report_youth_population_14_24": 180692,
        "report_high_school_graduation_rate": 88,
        "report_high_school_dropout_rate": 3.7,
        "report_youth_unemployment_rate": 15,
        "report_labor_force_participation_rate": 35,
    },
    "North County": {
        "report_youth_population_14_24": 133405,
        "report_high_school_graduation_rate": 87,
        "report_high_school_dropout_rate": 8.7,
        "report_youth_unemployment_rate": 9,
        "report_labor_force_participation_rate": 44,
    },
    "South San Diego": {
        "report_youth_population_14_24": 89839,
        "report_high_school_graduation_rate": 82,
        "report_high_school_dropout_rate": 8.7,
        "report_youth_unemployment_rate": 31,
        "report_labor_force_participation_rate": 30,
    },
    "East San Diego": {
        "report_youth_population_14_24": 72778,
        "report_high_school_graduation_rate": 81,
        "report_high_school_dropout_rate": 11.6,
        "report_youth_unemployment_rate": 18,
        "report_labor_force_participation_rate": 34,
    },
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


def load_tract_to_region(repo: Path) -> pd.DataFrame:
    crosswalk_path = repo / "data/rawdomains/regions/2020_Census_Tract_to_2020_PUMA.txt"

    xwalk = pd.read_csv(crosswalk_path, dtype=str)

    xwalk["STATEFP"] = xwalk["STATEFP"].astype(str).str.zfill(2)
    xwalk["COUNTYFP"] = xwalk["COUNTYFP"].astype(str).str.zfill(3)
    xwalk["TRACTCE"] = xwalk["TRACTCE"].astype(str).str.zfill(6)

    xwalk = xwalk[
        (xwalk["STATEFP"] == "06") &
        (xwalk["COUNTYFP"] == "073")
    ].copy()

    xwalk["tract_geoid"] = (
        xwalk["STATEFP"] +
        xwalk["COUNTYFP"] +
        xwalk["TRACTCE"]
    )

    xwalk["puma_code"] = (
        xwalk["PUMA5CE"]
        .astype(str)
        .str.replace(r"\D", "", regex=True)
        .str.zfill(5)
        .str[-4:]
    )

    xwalk["county_region"] = xwalk["puma_code"].map(REGION_BY_PUMA)

    xwalk = xwalk[
        ~xwalk["tract_geoid"].isin(EXCLUDED_TRACT_GEOIDS)
    ].copy()

    xwalk = xwalk.dropna(subset=["county_region"]).copy()

    return xwalk[["tract_geoid", "puma_code", "county_region"]]


def classify_service_category(row):
    text = " ".join(
        str(row.get(c, ""))
        for c in ["programs", "name", "provider_name", "site_name"]
    ).lower()

    education_keywords = [
        "tutor", "tutoring", "study skills", "instruction",
        "dropout", "dropout prevention", "dropout recovery",
        "alternative secondary", "school", "academic",
        "college", "postsecondary", "post-secondary",
        "college preparation", "college prep",
        "educational testing", "testing assistance",
        "books", "school supplies", "supplies",
        "fees", "scholarship", "scholarships",
        "leadership", "leadership development",
    ]

    employment_keywords = [
        "employment", "workforce", "job", "career",
        "career readiness", "work readiness",
        "internship", "internships",
        "work experience", "paid work", "unpaid work",
        "occupational", "skills training", "job training",
        "workforce preparation", "labor market",
        "entrepreneurship", "financial literacy",
        "work attire", "uniform", "tools",
        "employment fees", "training fees",
        "reasonable accommodations",
        "integrated education",
    ]

    wraparound_keywords = [
        "housing", "shelter", "mental health", "counseling",
        "drug", "alcohol", "health care", "healthcare",
        "referral", "referrals", "community services",
        "transportation", "child care", "childcare",
        "dependent care", "benefits", "needs-related",
        "legal", "legal aid", "case management",
        "food", "basic needs", "family services",
        "family support", "parenting", "pregnancy",
        "mentoring", "mentor", "life skills",
        "arts", "sports", "recreation", "enrichment",
        "youth development", "civic engagement",
        "cultural", "creative youth development",
    ]

    return {
        "dashboard_education_service_sites": any(k in text for k in education_keywords),
        "dashboard_employment_service_sites": any(k in text for k in employment_keywords),
        "dashboard_wraparound_service_sites": any(k in text for k in wraparound_keywords),
    }

def add_share_columns(df: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("dashboard_education_service_sites", "report_education_service_sites"),
        ("dashboard_employment_service_sites", "report_employment_service_sites"),
        ("dashboard_wraparound_service_sites", "report_wraparound_service_sites"),
    ]

    for dash_col, report_col in pairs:
        dash_share_col = dash_col.replace("dashboard_", "dashboard_share_")
        report_share_col = report_col.replace("report_", "report_share_")
        share_diff_col = dash_col.replace("dashboard_", "share_diff_")

        df[dash_share_col] = df[dash_col] / df[dash_col].sum() * 100
        df[report_share_col] = df[report_col] / df[report_col].sum() * 100
        df[share_diff_col] = df[dash_share_col] - df[report_share_col]

    return df

def aggregate_dashboard_services(repo: Path, tract_region: pd.DataFrame) -> pd.DataFrame:
    service_path = repo / "data/processed/overlays/service_locations.geojson"

    if not service_path.exists():
        raise FileNotFoundError(f"Missing service layer: {service_path}")

    services = gpd.read_file(service_path)

    services["tract_geoid"] = services["tract_geoid"].apply(normalize_geoid)
    services = services[
        ~services["tract_geoid"].isin(EXCLUDED_TRACT_GEOIDS)
    ].copy()

    services = services.merge(tract_region, on="tract_geoid", how="left")

    missing = services["county_region"].isna().sum()
    print("Service rows missing county region:", missing)

    services = services.dropna(subset=["county_region"]).copy()

    # Unique physical service locations.
    unique_counts = (
        services
        .groupby("county_region")
        .size()
        .reset_index(name="dashboard_unique_service_locations")
    )

    # Approximate category counts from text fields.
    # This is only comparable if your service categories align with the report.
    category_flags = services.apply(classify_service_category, axis=1, result_type="expand")
    services = pd.concat([services.reset_index(drop=True), category_flags], axis=1)
    audit_path = repo / "data/processed/validation/service_category_audit.csv"
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    audit_cols = [
        "county_region",
        "name",
        "provider_name",
        "site_name",
        "type",
        "programs",
        "dashboard_education_service_sites",
        "dashboard_employment_service_sites",
        "dashboard_wraparound_service_sites",
    ]

    audit_cols = [c for c in audit_cols if c in services.columns]

    services[audit_cols].to_csv(audit_path, index=False)
    print("Saved service category audit:", audit_path)

    category_counts = (
        services
        .groupby("county_region")[
            [
                "dashboard_education_service_sites",
                "dashboard_employment_service_sites",
                "dashboard_wraparound_service_sites",
            ]
        ]
        .sum()
        .reset_index()
    )

    return unique_counts.merge(category_counts, on="county_region", how="outer")


def aggregate_dashboard_yoi(repo: Path) -> pd.DataFrame:
    yoi_region_path = repo / "data/processed/yoi/yoi_county_region_components.csv"

    if not yoi_region_path.exists():
        raise FileNotFoundError(f"Missing county region YOI file: {yoi_region_path}")

    yoi = pd.read_csv(yoi_region_path)

    # Make sure region name column exists.
    if "county_region" not in yoi.columns:
        raise ValueError("yoi_county_region_components.csv must contain county_region")

    keep_cols = [
        "county_region",
        "total_population",
        "economic_score",
        "education_score",
        "health_score",
        "housing_score",
        "safety_env_score",
        "mobility_connectivity_score",
        "youth_supports_score",
        "yoi_custom_0_100",
    ]

    keep_cols = [c for c in keep_cols if c in yoi.columns]

    yoi = yoi[keep_cols].copy()
    yoi = yoi.rename(columns={
        "total_population": "dashboard_total_population",
        "yoi_custom_0_100": "dashboard_yoi_0_100",
    })

    return yoi


def add_report_benchmarks(df: pd.DataFrame) -> pd.DataFrame:
    report_rows = []

    for region in ["Metro San Diego", "North County", "South San Diego", "East San Diego"]:
        row = {"county_region": region}
        row.update(REPORT_SERVICE_BENCHMARKS.get(region, {}))
        row.update(REPORT_OUTCOME_BENCHMARKS.get(region, {}))
        report_rows.append(row)

    report_df = pd.DataFrame(report_rows)

    return df.merge(report_df, on="county_region", how="outer")


def add_difference_columns(df: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("dashboard_education_service_sites", "report_education_service_sites"),
        ("dashboard_employment_service_sites", "report_employment_service_sites"),
        ("dashboard_wraparound_service_sites", "report_wraparound_service_sites"),
    ]

    for dash_col, report_col in pairs:
        if dash_col in df.columns and report_col in df.columns:
            diff_col = dash_col.replace("dashboard_", "diff_")
            pct_col = dash_col.replace("dashboard_", "pct_diff_")

            df[diff_col] = pd.to_numeric(df[dash_col], errors="coerce") - pd.to_numeric(df[report_col], errors="coerce")
            df[pct_col] = df[diff_col] / pd.to_numeric(df[report_col], errors="coerce") * 100

    return df


def main():
    repo = find_repo_root(Path.cwd())

    out_dir = repo / "data/processed/validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    tract_region = load_tract_to_region(repo)

    services_by_region = aggregate_dashboard_services(repo, tract_region)
    yoi_by_region = aggregate_dashboard_yoi(repo)

    validation = yoi_by_region.merge(
        services_by_region,
        on="county_region",
        how="outer",
    )

    validation = add_report_benchmarks(validation)
    validation = add_difference_columns(validation)
    validation = add_share_columns(validation)

    out_path = out_dir / "workforce_report_region_validation.csv"
    validation.to_csv(out_path, index=False)

    print("Saved:", out_path)
    print()
    print(validation.to_string(index=False))

def add_share_columns(df: pd.DataFrame) -> pd.DataFrame:
    service_pairs = [
        ("dashboard_education_service_sites", "report_education_service_sites"),
        ("dashboard_employment_service_sites", "report_employment_service_sites"),
        ("dashboard_wraparound_service_sites", "report_wraparound_service_sites"),
    ]

    for dash_col, report_col in service_pairs:
        if dash_col in df.columns and report_col in df.columns:
            dash_share_col = dash_col.replace("dashboard_", "dashboard_share_")
            report_share_col = report_col.replace("report_", "report_share_")
            share_diff_col = dash_col.replace("dashboard_", "share_diff_")

            df[dash_share_col] = df[dash_col] / df[dash_col].sum() * 100
            df[report_share_col] = df[report_col] / df[report_col].sum() * 100
            df[share_diff_col] = df[dash_share_col] - df[report_share_col]

    return df

if __name__ == "__main__":
    main()