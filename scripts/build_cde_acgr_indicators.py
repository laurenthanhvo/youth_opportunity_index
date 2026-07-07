from pathlib import Path
import re
import pandas as pd
import numpy as np

RAW_DIR = Path("data/raw/cde/acgr")
OUT_DIR = Path("data/processed/cde")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Use acgr24 for 2023–24.
ACGR_FILES = sorted(RAW_DIR.glob("acgr24*.txt"))

if not ACGR_FILES:
    raise FileNotFoundError(
        "Could not find acgr24.txt in data/raw/cde/acgr/. "
        "Save the CDE file there first."
    )

ACGR_PATH = ACGR_FILES[0]


def norm(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def find_col(df, exact=None, tokens=None):
    cols = list(df.columns)
    norm_map = {norm(c): c for c in cols}

    if exact:
        for name in exact:
            key = norm(name)
            if key in norm_map:
                return norm_map[key]

    if tokens:
        token_norms = [norm(t) for t in tokens]
        for c in cols:
            nc = norm(c)
            if all(t in nc for t in token_norms):
                return c

    raise KeyError(f"Could not find column. exact={exact}, tokens={tokens}")


def clean_num(series):
    return (
        series.astype(str)
        .str.strip()
        .replace({"": np.nan, "*": np.nan, "nan": np.nan, "None": np.nan})
        .pipe(pd.to_numeric, errors="coerce")
    )


print(f"Reading: {ACGR_PATH}")

df = pd.read_csv(ACGR_PATH, sep="\t", dtype=str, engine="python")
df.columns = [re.sub(r"\s+", " ", c).strip() for c in df.columns]

if len(df.columns) <= 1:
    raise ValueError(
        "The file did not parse as tab-delimited. "
        "Make sure you saved the original .txt file, not a webpage copy."
    )

academic_year_col = find_col(df, exact=["AcademicYear"])
aggregate_col = find_col(df, exact=["AggregateLevel"])
county_code_col = find_col(df, exact=["CountyCode"])
district_code_col = find_col(df, exact=["DistrictCode"])
school_code_col = find_col(df, exact=["SchoolCode"])
county_name_col = find_col(df, exact=["CountyName"])
district_name_col = find_col(df, exact=["DistrictName"])
school_name_col = find_col(df, exact=["SchoolName"])
reporting_category_col = find_col(df, exact=["ReportingCategory"])

cohort_col = find_col(df, tokens=["cohort", "students"])
grad_count_col = find_col(df, tokens=["regular", "hs", "diploma", "graduates", "count"])
grad_rate_col = find_col(df, tokens=["regular", "hs", "diploma", "graduates", "rate"])
dropout_count_col = find_col(df, tokens=["dropout", "count"])
dropout_rate_col = find_col(df, tokens=["dropout", "rate"])

# Keep San Diego County rows and total/all-student reporting category.
df["county_code_clean"] = df[county_code_col].astype(str).str.strip().str.zfill(2)
df["academic_year_clean"] = df[academic_year_col].astype(str).str.strip()
df["reporting_category_clean"] = df[reporting_category_col].astype(str).str.strip()

san_diego = df[
    (df["academic_year_clean"] == "2023-24")
    & (
        (df["county_code_clean"] == "37")
        | (df[county_name_col].astype(str).str.contains("San Diego", case=False, na=False))
    )
].copy()

print(f"San Diego rows before reporting-category filter: {len(san_diego):,}")
print("Reporting categories found:", sorted(san_diego["reporting_category_clean"].dropna().unique())[:30])

# TA is the CDE total/all-students category.
ta = san_diego[san_diego["reporting_category_clean"] == "TA"].copy()

if ta.empty:
    raise ValueError(
        "No ReportingCategory == 'TA' rows found for San Diego. "
        "Check the printed reporting categories above."
    )

out = pd.DataFrame({
    "academic_year": ta[academic_year_col].astype(str).str.strip(),
    "aggregate_level": ta[aggregate_col].astype(str).str.strip(),
    "county_code": ta[county_code_col].astype(str).str.strip(),
    "district_code": ta[district_code_col].astype(str).str.strip(),
    "school_code": ta[school_code_col].astype(str).str.strip(),
    "county_name": ta[county_name_col].astype(str).str.strip(),
    "district_name": ta[district_name_col].astype(str).str.strip(),
    "school_name": ta[school_name_col].astype(str).str.strip(),
    "reporting_category": ta[reporting_category_col].astype(str).str.strip(),

    "cohort_students": clean_num(ta[cohort_col]),
    "regular_hs_diploma_graduates_count": clean_num(ta[grad_count_col]),
    "cde_adjusted_cohort_graduation_rate": clean_num(ta[grad_rate_col]),
    "dropout_count": clean_num(ta[dropout_count_col]),
    "cde_four_year_cohort_dropout_rate": clean_num(ta[dropout_rate_col]),
})

# Save all San Diego total/all-student rows: county, district, and school.
all_out_path = OUT_DIR / "acgr_san_diego_ta_2023_24.csv"
out.to_csv(all_out_path, index=False)

# Save county-level row only.
county_summary = out[out["aggregate_level"].str.upper() == "C"].copy()

if county_summary.empty:
    print("Warning: no aggregate_level == C county row found. Saving empty county summary.")

county_out_path = OUT_DIR / "acgr_san_diego_county_summary_2023_24.csv"
county_summary.to_csv(county_out_path, index=False)

print()
print(f"Saved: {all_out_path}")
print(f"Rows: {len(out):,}")

print()
print(f"Saved: {county_out_path}")
print(f"Rows: {len(county_summary):,}")

print()
print("Preview:")
print(out.head())