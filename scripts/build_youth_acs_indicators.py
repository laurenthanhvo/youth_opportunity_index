from pathlib import Path
import zipfile
import re
import pandas as pd
import numpy as np

RAW_DIR = Path("data/raw/census/acs5_2024")
OUT_DIR = Path("data/processed/census")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def read_census_zip(folder: Path) -> pd.DataFrame:
    zip_files = list(folder.glob("*.zip"))
    if not zip_files:
        raise FileNotFoundError(f"No zip file found in {folder}")

    zip_path = zip_files[0]

    with zipfile.ZipFile(zip_path, "r") as z:
        csv_names = [
            name for name in z.namelist()
            if name.endswith(".csv") and "Data" in name
        ]

        if not csv_names:
            csv_names = [name for name in z.namelist() if name.endswith(".csv")]

        if not csv_names:
            raise FileNotFoundError(f"No CSV found inside {zip_path}")

        with z.open(csv_names[0]) as f:
            df = pd.read_csv(f, dtype=str)

    # data.census.gov downloads often include a second row of labels.
    if "GEO_ID" in df.columns and len(df) and str(df.loc[0, "GEO_ID"]).strip() == "Geography":
        df = df.iloc[1:].copy()

    return df


def normalize_geoid(v):
    if pd.isna(v):
        return None
    digits = re.sub(r"\D", "", str(v))
    if not digits:
        return None
    return digits.zfill(11)[-11:]


def extract_tract_geoid(df: pd.DataFrame) -> pd.Series:
    if "GEO_ID" in df.columns:
        extracted = df["GEO_ID"].astype(str).str.extract(r"US(\d+)$")[0]
        return extracted.map(normalize_geoid)
    if "tract_geoid" in df.columns:
        return df["tract_geoid"].map(normalize_geoid)
    raise ValueError("No GEO_ID or tract_geoid column found.")


def num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        print(f"WARNING missing column: {col}")
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


# ----------------------------
# B01001: Sex by age
# ----------------------------
b01001 = read_census_zip(RAW_DIR / "B01001_youth_population")
b01001["tract_geoid"] = extract_tract_geoid(b01001)

male_10_14 = num(b01001, "B01001_005E")
male_15_17 = num(b01001, "B01001_006E")
male_18_19 = num(b01001, "B01001_007E")
male_20 = num(b01001, "B01001_008E")
male_21 = num(b01001, "B01001_009E")
male_22_24 = num(b01001, "B01001_010E")

female_10_14 = num(b01001, "B01001_029E")
female_15_17 = num(b01001, "B01001_030E")
female_18_19 = num(b01001, "B01001_031E")
female_20 = num(b01001, "B01001_032E")
female_21 = num(b01001, "B01001_033E")
female_22_24 = num(b01001, "B01001_034E")

total_population_all_ages = num(b01001, "B01001_001E")

youth_pop_14_24 = (
    0.2 * (male_10_14 + female_10_14)
    + male_15_17 + female_15_17
    + male_18_19 + female_18_19
    + male_20 + female_20
    + male_21 + female_21
    + male_22_24 + female_22_24
)

youth_pop_14_21_report_aligned = (
    0.2 * (male_10_14 + female_10_14)
    + male_15_17 + female_15_17
    + male_18_19 + female_18_19
    + male_20 + female_20
    + male_21 + female_21
)

youth_pop_18_24_report_aligned = (
    male_18_19 + female_18_19
    + male_20 + female_20
    + male_21 + female_21
    + male_22_24 + female_22_24
)

b01001_out = pd.DataFrame({
    "tract_geoid": b01001["tract_geoid"],
    "tract_name": b01001.get("NAME", ""),
    "total_population_all_ages": total_population_all_ages,
    "youth_pop_14_24": youth_pop_14_24,
    "youth_share_14_24": np.where(total_population_all_ages > 0, youth_pop_14_24 / total_population_all_ages, np.nan),
    "youth_pop_14_21_report_aligned": youth_pop_14_21_report_aligned,
    "youth_pop_18_24_report_aligned": youth_pop_18_24_report_aligned,
})


# ----------------------------
# B14003: school enrollment
# ----------------------------
b14003 = read_census_zip(RAW_DIR / "B14003_school_enrollment")
b14003["tract_geoid"] = extract_tract_geoid(b14003)

# Enrolled = public + private school.
# B14003 has 10–14, 15–17, 18–19, 20–24 bins.
# For exact report alignment, students 14–21 is approximated:
# age 14 = 1/5 of 10–14; ages 20–21 = 2/5 of 20–24.

male_public_10_14 = num(b14003, "B14003_006E")
male_public_15_17 = num(b14003, "B14003_007E")
male_public_18_19 = num(b14003, "B14003_008E")
male_public_20_24 = num(b14003, "B14003_009E")

male_private_10_14 = num(b14003, "B14003_015E")
male_private_15_17 = num(b14003, "B14003_016E")
male_private_18_19 = num(b14003, "B14003_017E")
male_private_20_24 = num(b14003, "B14003_018E")

female_public_10_14 = num(b14003, "B14003_034E")
female_public_15_17 = num(b14003, "B14003_035E")
female_public_18_19 = num(b14003, "B14003_036E")
female_public_20_24 = num(b14003, "B14003_037E")

female_private_10_14 = num(b14003, "B14003_043E")
female_private_15_17 = num(b14003, "B14003_044E")
female_private_18_19 = num(b14003, "B14003_045E")
female_private_20_24 = num(b14003, "B14003_046E")

enrolled_10_14 = male_public_10_14 + male_private_10_14 + female_public_10_14 + female_private_10_14
enrolled_15_17 = male_public_15_17 + male_private_15_17 + female_public_15_17 + female_private_15_17
enrolled_18_19 = male_public_18_19 + male_private_18_19 + female_public_18_19 + female_private_18_19
enrolled_20_24 = male_public_20_24 + male_private_20_24 + female_public_20_24 + female_private_20_24

students_14_24 = (
    0.2 * enrolled_10_14
    + enrolled_15_17
    + enrolled_18_19
    + enrolled_20_24
)

students_14_21_report_aligned = (
    0.2 * enrolled_10_14
    + enrolled_15_17
    + enrolled_18_19
    + 0.4 * enrolled_20_24
)

not_enrolled_10_14 = num(b14003, "B14003_024E") + num(b14003, "B14003_052E")
not_enrolled_15_17 = num(b14003, "B14003_025E") + num(b14003, "B14003_053E")
not_enrolled_18_19 = num(b14003, "B14003_026E") + num(b14003, "B14003_054E")
not_enrolled_20_24 = num(b14003, "B14003_027E") + num(b14003, "B14003_055E")

not_in_school_youth_14_24 = (
    0.2 * not_enrolled_10_14
    + not_enrolled_15_17
    + not_enrolled_18_19
    + not_enrolled_20_24
)

not_in_school_youth_18_24_report_aligned = (
    not_enrolled_18_19
    + not_enrolled_20_24
)

b14003_out = pd.DataFrame({
    "tract_geoid": b14003["tract_geoid"],
    "students_14_24": students_14_24,
    "students_14_21_report_aligned": students_14_21_report_aligned,
    "not_in_school_youth_14_24": not_in_school_youth_14_24,
    "not_in_school_youth_18_24_report_aligned": not_in_school_youth_18_24_report_aligned,
})


# ----------------------------
# Final ACS tract output
# ----------------------------
out = b01001_out.merge(b14003_out, on="tract_geoid", how="left")

out["student_share_14_24"] = np.where(
    out["youth_pop_14_24"] > 0,
    out["students_14_24"] / out["youth_pop_14_24"],
    np.nan
)

out["students_14_21_share_report_aligned"] = np.where(
    out["youth_pop_14_21_report_aligned"] > 0,
    out["students_14_21_report_aligned"] / out["youth_pop_14_21_report_aligned"],
    np.nan
)

out["not_in_school_youth_share_14_24"] = np.where(
    out["youth_pop_14_24"] > 0,
    out["not_in_school_youth_14_24"] / out["youth_pop_14_24"],
    np.nan
)

out["not_in_school_youth_18_24_share_report_aligned"] = np.where(
    out["youth_pop_18_24_report_aligned"] > 0,
    out["not_in_school_youth_18_24_report_aligned"] / out["youth_pop_18_24_report_aligned"],
    np.nan
)

out = out[out["tract_geoid"].notna()].copy()

out_path = OUT_DIR / "youth_acs_tract_indicators.csv"
out.to_csv(out_path, index=False)

print(f"Saved: {out_path}")
print(f"Rows: {len(out):,}")
print(out.head())