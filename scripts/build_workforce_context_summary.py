from pathlib import Path
import pandas as pd
import numpy as np

OUT_DIR = Path("data/processed/workforce")
OUT_DIR.mkdir(parents=True, exist_ok=True)

rows = []


def add_row(indicator, field, value, source, geography, source_type):
    rows.append({
        "indicator": indicator,
        "field": field,
        "value": value,
        "source": source,
        "geography": geography,
        "source_type": source_type,
    })


def first_value(df, col):
    if col not in df.columns or df.empty:
        return np.nan
    return df.iloc[0].get(col, np.nan)


# ------------------------------------------------------------
# CDE ACGR: graduation + dropout
# ------------------------------------------------------------
acgr_path = Path("data/processed/cde/acgr_san_diego_official_county_2023_24.csv")

# Fallback if official county row was not extracted yet.
if not acgr_path.exists():
    fallback = Path("data/processed/cde/acgr_san_diego_county_summary_2023_24.csv")
    if fallback.exists():
        df = pd.read_csv(fallback)
        df = df.sort_values("cohort_students", ascending=False).head(1)
        acgr_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(acgr_path, index=False)
        print(f"Created fallback official ACGR file: {acgr_path}")

if acgr_path.exists():
    df = pd.read_csv(acgr_path)

    add_row(
        indicator="CDE adjusted cohort graduation rate",
        field="cde_adjusted_cohort_graduation_rate",
        value=first_value(df, "cde_adjusted_cohort_graduation_rate"),
        source="CDE ACGR 2023-24",
        geography="San Diego County",
        source_type="CDE county/school outcome",
    )

    add_row(
        indicator="CDE four-year cohort dropout rate",
        field="cde_four_year_cohort_dropout_rate",
        value=first_value(df, "cde_four_year_cohort_dropout_rate"),
        source="CDE ACGR 2023-24",
        geography="San Diego County",
        source_type="CDE county/school outcome",
    )
else:
    print("Warning: ACGR county file not found.")


# ------------------------------------------------------------
# CDE homeless students
# ------------------------------------------------------------
homeless_files = sorted(Path("data/processed/cde").glob("homeless_students_san_diego_official_county*.csv"))

if homeless_files:
    homeless_path = homeless_files[0]
    df = pd.read_csv(homeless_path)

    add_row(
        indicator="CDE cumulative enrollment",
        field="cde_cumulative_enrollment",
        value=first_value(df, "cde_cumulative_enrollment"),
        source="CDE Homeless Student Enrollment",
        geography="San Diego County",
        source_type="CDE county/school student group",
    )

    add_row(
        indicator="CDE homeless students",
        field="cde_homeless_students",
        value=first_value(df, "cde_homeless_students"),
        source="CDE Homeless Student Enrollment",
        geography="San Diego County",
        source_type="CDE county/school student group",
    )

    add_row(
        indicator="CDE homeless student rate",
        field="cde_homeless_student_rate",
        value=first_value(df, "cde_homeless_student_rate"),
        source="CDE Homeless Student Enrollment",
        geography="San Diego County",
        source_type="CDE county/school student group",
    )
else:
    print("Warning: homeless student county file not found.")


# ------------------------------------------------------------
# CDE English learners
# ------------------------------------------------------------
el_path = Path("data/processed/cde/english_learners_san_diego_official_county.csv")

if el_path.exists():
    df = pd.read_csv(el_path)

    add_row(
        indicator="CDE English learner students",
        field="english_learner_students",
        value=first_value(df, "english_learner_students"),
        source="CDE English Learners by Grade and Language",
        geography="San Diego County",
        source_type="CDE county/school student group",
    )
else:
    print("Warning: English learner county file not found.")



# ------------------------------------------------------------
# ACS PUMS youth unemployment ages 16-19
# ------------------------------------------------------------
pums_path = Path("data/processed/workforce/pums_youth_unemployment_16_19_san_diego_county.csv")

if pums_path.exists():
    df = pd.read_csv(pums_path)
    r = df.iloc[0]

    add_row(
        indicator="ACS PUMS youth unemployment rate ages 16-19",
        field="youth_unemployment_rate_16_19_pums",
        value=r.get("youth_unemployment_rate_16_19_pums"),
        source="2024 ACS 5-year PUMS",
        geography="San Diego County",
        source_type="ACS PUMS county/PUMA estimate",
    )

    add_row(
        indicator="ACS PUMS labor force participation rate ages 16-19",
        field="labor_force_participation_rate_16_19_pums",
        value=r.get("labor_force_participation_rate_16_19_pums"),
        source="2024 ACS 5-year PUMS",
        geography="San Diego County",
        source_type="ACS PUMS county/PUMA estimate",
    )
else:
    print("Warning: PUMS youth unemployment county file not found.")

# ------------------------------------------------------------
# Save combined context summary
# ------------------------------------------------------------
out = pd.DataFrame(rows)

out_path = OUT_DIR / "workforce_context_summary.csv"
out.to_csv(out_path, index=False)

print()
print(f"Saved: {out_path}")
print(out)
