from pathlib import Path
import zipfile
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
            raise FileNotFoundError(f"No Data CSV found inside {zip_path}")

        with z.open(csv_names[0]) as f:
            df = pd.read_csv(f, dtype=str)

    # data.census.gov downloads often include a second row with column labels.
    # Drop it if present.
    if "GEO_ID" in df.columns and df.loc[0, "GEO_ID"] == "Geography":
        df = df.iloc[1:].copy()

    return df


def num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        print(f"Warning: missing column {col}")
        return pd.Series(0, index=df.index, dtype=float)

    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def extract_tract_geoid(df: pd.DataFrame) -> pd.Series:
    # GEO_ID usually looks like: 1400000US06073000100
    return df["GEO_ID"].astype(str).str.extract(r"US(\d+)$")[0]


# ----------------------------
# B01001: Youth population 14–24
# ----------------------------

b01001 = read_census_zip(RAW_DIR / "B01001_youth_population")

b01001["tract_geoid"] = extract_tract_geoid(b01001)

b01001_out = pd.DataFrame({
    "tract_geoid": b01001["tract_geoid"],
    "tract_name": b01001.get("NAME", ""),
    "total_population": num(b01001, "B01001_001E"),

    # Estimate age 14 as 1/5 of the 10–14 bin.
    "youth_pop_14_24": (
        0.2 * (num(b01001, "B01001_005E") + num(b01001, "B01001_029E")) +
        num(b01001, "B01001_006E") + num(b01001, "B01001_030E") +
        num(b01001, "B01001_007E") + num(b01001, "B01001_031E") +
        num(b01001, "B01001_008E") + num(b01001, "B01001_032E") +
        num(b01001, "B01001_009E") + num(b01001, "B01001_033E") +
        num(b01001, "B01001_010E") + num(b01001, "B01001_034E")
    )
})

b01001_out["youth_share_14_24"] = np.where(
    b01001_out["total_population"] > 0,
    b01001_out["youth_pop_14_24"] / b01001_out["total_population"],
    np.nan
)


# ----------------------------
# B14003: Students + not-in-school youth 14–24
# ----------------------------

b14003 = read_census_zip(RAW_DIR / "B14003_school_enrollment")
b14003["tract_geoid"] = extract_tract_geoid(b14003)

# Students = public school + private school
students_14_24 = (
    # Male public/private age 14 estimated from 10–14
    0.2 * (
        num(b14003, "B14003_006E") +  # male public 10–14
        num(b14003, "B14003_015E") +  # male private 10–14
        num(b14003, "B14003_034E") +  # female public 10–14
        num(b14003, "B14003_043E")    # female private 10–14
    )

    # 15–17
    + num(b14003, "B14003_007E") + num(b14003, "B14003_016E")
    + num(b14003, "B14003_035E") + num(b14003, "B14003_044E")

    # 18–19
    + num(b14003, "B14003_008E") + num(b14003, "B14003_017E")
    + num(b14003, "B14003_036E") + num(b14003, "B14003_045E")

    # 20–24
    + num(b14003, "B14003_009E") + num(b14003, "B14003_018E")
    + num(b14003, "B14003_037E") + num(b14003, "B14003_046E")
)

not_in_school_14_24 = (
    # age 14 estimated from 10–14
    0.2 * (
        num(b14003, "B14003_024E") +  # male not enrolled 10–14
        num(b14003, "B14003_052E")    # female not enrolled 10–14
    )

    # 15–17
    + num(b14003, "B14003_025E") + num(b14003, "B14003_053E")

    # 18–19
    + num(b14003, "B14003_026E") + num(b14003, "B14003_054E")

    # 20–24
    + num(b14003, "B14003_027E") + num(b14003, "B14003_055E")
)

b14003_out = pd.DataFrame({
    "tract_geoid": b14003["tract_geoid"],
    "students_14_24": students_14_24,
    "not_in_school_youth_14_24": not_in_school_14_24,
})


# ----------------------------
# Merge final tract youth indicators
# ----------------------------

out = b01001_out.merge(b14003_out, on="tract_geoid", how="left")

out["student_share_14_24"] = np.where(
    out["youth_pop_14_24"] > 0,
    out["students_14_24"] / out["youth_pop_14_24"],
    np.nan
)

out["not_in_school_youth_share_14_24"] = np.where(
    out["youth_pop_14_24"] > 0,
    out["not_in_school_youth_14_24"] / out["youth_pop_14_24"],
    np.nan
)

# Optional: remove rows without tract GEOID
out = out[out["tract_geoid"].notna()].copy()

out_path = OUT_DIR / "youth_acs_tract_indicators.csv"
out.to_csv(out_path, index=False)

print(f"Saved: {out_path}")
print(f"Rows: {len(out):,}")
print(out.head())