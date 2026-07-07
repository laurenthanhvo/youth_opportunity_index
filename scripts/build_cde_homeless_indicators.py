from pathlib import Path
import re
import pandas as pd
import numpy as np

RAW_DIR = Path("data/raw/cde/homeless_students")
OUT_DIR = Path("data/processed/cde")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Use whichever homeless file is in the folder, preferring hse2425.
HSE_FILES = sorted(RAW_DIR.glob("hse2324*.txt")) or sorted(RAW_DIR.glob("hse2425*.txt")) or sorted(RAW_DIR.glob("hse*.txt"))

if not HSE_FILES:
    raise FileNotFoundError(
        "No hse*.txt file found in data/raw/cde/homeless_students/. "
        "Download hse2425.txt or hse2324.txt there first."
    )

HSE_PATH = HSE_FILES[0]


def norm(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def find_col(df, exact=None, tokens=None, required=True):
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

    if required:
        raise KeyError(f"Could not find column. exact={exact}, tokens={tokens}")

    return None


def clean_num(series):
    return (
        series.astype(str)
        .str.strip()
        .replace({"": np.nan, "*": np.nan, "nan": np.nan, "None": np.nan})
        .pipe(pd.to_numeric, errors="coerce")
    )


print(f"Reading: {HSE_PATH}")

df = pd.read_csv(HSE_PATH, sep="\t", dtype=str, engine="python", encoding="latin1")
df.columns = [re.sub(r"\s+", " ", c).strip() for c in df.columns]

if len(df.columns) <= 1:
    raise ValueError(
        "The file did not parse as tab-delimited. "
        "Make sure you saved the original .txt file, not a webpage copy."
    )

print("Columns found:")
for c in df.columns:
    print(" -", c)

academic_year_col = find_col(df, exact=["AcademicYear", "Academic Year"])
aggregate_col = find_col(df, exact=["AggregateLevel", "Aggregate Level"])
county_code_col = find_col(df, exact=["CountyCode", "County Code"])
district_code_col = find_col(df, exact=["DistrictCode", "District Code"])
school_code_col = find_col(df, exact=["SchoolCode", "School Code"])
county_name_col = find_col(df, exact=["CountyName", "County Name"])
district_name_col = find_col(df, exact=["DistrictName", "District Name"])
school_name_col = find_col(df, exact=["SchoolName", "School Name"])
reporting_category_col = find_col(df, exact=["ReportingCategory", "Reporting Category"])

charter_col = find_col(df, tokens=["charter"], required=False)
dass_col = find_col(df, tokens=["dass"], required=False)

cum_enroll_col = find_col(df, tokens=["cumulative", "enrollment"])
homeless_count_col = find_col(df, tokens=["homeless", "student", "enrollment"])

# Optional dwelling-type columns.
doubled_up_col = find_col(df, tokens=["temporarily", "doubled"], required=False)
shelters_col = find_col(df, tokens=["temporary", "shelters"], required=False)
hotels_col = find_col(df, tokens=["hotels"], required=False)
unsheltered_col = find_col(df, tokens=["unsheltered"], required=False)
missing_unknown_col = find_col(df, tokens=["missing"], required=False)

df["county_code_clean"] = df[county_code_col].astype(str).str.strip().str.zfill(2)
df["reporting_category_clean"] = df[reporting_category_col].astype(str).str.strip()
df["aggregate_level_clean"] = df[aggregate_col].astype(str).str.strip()

san_diego = df[
    (df["county_code_clean"] == "37")
    | (df[county_name_col].astype(str).str.contains("San Diego", case=False, na=False))
].copy()

print(f"\nSan Diego rows before filters: {len(san_diego):,}")
print("Aggregate levels:", sorted(san_diego["aggregate_level_clean"].dropna().unique()))
print("Reporting categories:", sorted(san_diego["reporting_category_clean"].dropna().unique())[:50])

# Use total category only.
ta = san_diego[san_diego["reporting_category_clean"] == "TA"].copy()

# For county/district aggregates, Charter=All and DASS=All are the clean unduplicated total rows.
if charter_col:
    ta = ta[
        (ta[charter_col].astype(str).str.strip().str.lower() == "all")
        | (ta["aggregate_level_clean"] == "S")
    ].copy()

if dass_col:
    ta = ta[
        (ta[dass_col].astype(str).str.strip().str.lower() == "all")
        | (ta["aggregate_level_clean"] == "S")
    ].copy()

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
    "cde_cumulative_enrollment": clean_num(ta[cum_enroll_col]),
    "cde_homeless_students": clean_num(ta[homeless_count_col]),
})

if doubled_up_col:
    out["cde_homeless_temporarily_doubled_up"] = clean_num(ta[doubled_up_col])
if shelters_col:
    out["cde_homeless_temporary_shelters"] = clean_num(ta[shelters_col])
if hotels_col:
    out["cde_homeless_hotels_motels"] = clean_num(ta[hotels_col])
if unsheltered_col:
    out["cde_homeless_temporarily_unsheltered"] = clean_num(ta[unsheltered_col])
if missing_unknown_col:
    out["cde_homeless_missing_unknown"] = clean_num(ta[missing_unknown_col])

out["cde_homeless_student_rate"] = np.where(
    out["cde_cumulative_enrollment"] > 0,
    out["cde_homeless_students"] / out["cde_cumulative_enrollment"],
    np.nan
)

# Save all San Diego total rows: county, district, school.
all_out_path = OUT_DIR / "homeless_students_san_diego_ta_2024_25.csv"
out.to_csv(all_out_path, index=False)

# Save clean county total row.
county = out[out["aggregate_level"].str.upper() == "C"].copy()

# If multiple county rows survive for some reason, choose largest cumulative enrollment.
county = county.sort_values("cde_cumulative_enrollment", ascending=False).head(1).copy()

county["source_note"] = (
    "CDE 2024-25 Homeless Student Enrollment; San Diego County total; "
    "ReportingCategory TA; school-based enrollment, not resident tract homelessness."
)

county_out_path = OUT_DIR / "homeless_students_san_diego_official_county_2024_25.csv"
county.to_csv(county_out_path, index=False)

print()
print(f"Saved: {all_out_path}")
print(f"Rows: {len(out):,}")

print()
print(f"Saved: {county_out_path}")
print(f"Rows: {len(county):,}")

print()
print("County preview:")
print(county[[
    "academic_year",
    "county_name",
    "cde_cumulative_enrollment",
    "cde_homeless_students",
    "cde_homeless_student_rate",
    "source_note",
]])