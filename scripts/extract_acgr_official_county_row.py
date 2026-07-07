from pathlib import Path
import pandas as pd

IN_PATH = Path("data/processed/cde/acgr_san_diego_county_summary_2023_24.csv")
OUT_PATH = Path("data/processed/cde/acgr_san_diego_official_county_2023_24.csv")

df = pd.read_csv(IN_PATH)

# The first aggregate-level C row is the broad San Diego County total row.
# It has the full county cohort, before CDE splits by charter/DASS subgroups.
official = df.sort_values("cohort_students", ascending=False).head(1).copy()

official["source_note"] = (
    "CDE 2023-24 Four-Year Adjusted Cohort Graduation Rate and Outcome Data; "
    "San Diego County total, ReportingCategory TA."
)

official.to_csv(OUT_PATH, index=False)

print(f"Saved: {OUT_PATH}")
print(official[[
    "academic_year",
    "county_name",
    "cohort_students",
    "cde_adjusted_cohort_graduation_rate",
    "cde_four_year_cohort_dropout_rate",
    "source_note",
]])