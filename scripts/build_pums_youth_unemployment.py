from pathlib import Path
import zipfile
import pandas as pd
import numpy as np

RAW_PATH = Path("data/raw/census/pums_2024/csv_pca.zip")
CROSSWALK_PATH = Path("data/processed/workforce/san_diego_puma_crosswalk.csv")
OUT_DIR = Path("data/processed/workforce")
OUT_DIR.mkdir(parents=True, exist_ok=True)

if not RAW_PATH.exists():
    raise FileNotFoundError(f"Missing {RAW_PATH}. Download csv_pca.zip first.")

if not CROSSWALK_PATH.exists():
    raise FileNotFoundError(
        f"Missing {CROSSWALK_PATH}. Run scripts/build_san_diego_puma_crosswalk.py first."
    )


def find_person_csv_in_zip(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        csvs = [n for n in names if n.lower().endswith(".csv")]
        person_csvs = [n for n in csvs if "psam_p" in n.lower()]
        if person_csvs:
            return person_csvs[0]
        if csvs:
            return csvs[0]
    raise FileNotFoundError(f"No CSV found inside {zip_path}")


def clean_puma(v):
    if pd.isna(v):
        return ""
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return digits.zfill(5)


def pick_col(cols, options, required=True):
    colset = set(cols)
    for opt in options:
        if opt in colset:
            return opt
    if required:
        raise KeyError(f"Could not find any of these columns: {options}")
    return None


def summarize(df):
    # Workforce definition:
    # youth unemployment rate =
    # unemployed civilian labor force ages 16-19 /
    # civilian labor force ages 16-19
    #
    # ESR:
    # 1 = civilian employed, at work
    # 2 = civilian employed, with job but not at work
    # 3 = unemployed
    # 4-5 = Armed Forces, excluded
    # 6 = not in labor force

    civilian_labor_force_mask = df["ESR"].isin([1, 2, 3])
    unemployed_mask = df["ESR"].eq(3)
    employed_mask = df["ESR"].isin([1, 2])
    civilian_population_mask = df["ESR"].isin([1, 2, 3, 6])

    civilian_labor_force = df.loc[civilian_labor_force_mask, "PWGTP"].sum()
    unemployed = df.loc[unemployed_mask, "PWGTP"].sum()
    employed = df.loc[employed_mask, "PWGTP"].sum()
    civilian_population = df.loc[civilian_population_mask, "PWGTP"].sum()

    return {
        "youth_16_19_civilian_population_pums": civilian_population,
        "youth_16_19_civilian_labor_force_pums": civilian_labor_force,
        "youth_16_19_employed_pums": employed,
        "youth_16_19_unemployed_pums": unemployed,
        "youth_unemployment_rate_16_19_pums": (
            unemployed / civilian_labor_force if civilian_labor_force > 0 else np.nan
        ),
        "labor_force_participation_rate_16_19_pums": (
            civilian_labor_force / civilian_population if civilian_population > 0 else np.nan
        ),
    }


print(f"Reading: {RAW_PATH}")
csv_name = find_person_csv_in_zip(RAW_PATH)
print(f"Person CSV inside zip: {csv_name}")

with zipfile.ZipFile(RAW_PATH, "r") as z:
    with z.open(csv_name) as f:
        header = pd.read_csv(f, nrows=0)
        cols = list(header.columns)

print("Available relevant columns check:")
for c in ["ST", "STATE", "PUMA", "PUMA20", "AGEP", "ESR", "PWGTP"]:
    print(f" - {c}: {'yes' if c in cols else 'no'}")

state_col = pick_col(cols, ["ST", "STATE"], required=False)
puma_col = pick_col(cols, ["PUMA", "PUMA20"], required=True)
age_col = pick_col(cols, ["AGEP"], required=True)
esr_col = pick_col(cols, ["ESR"], required=True)
weight_col = pick_col(cols, ["PWGTP"], required=True)

usecols = [puma_col, age_col, esr_col, weight_col]
if state_col:
    usecols.append(state_col)

with zipfile.ZipFile(RAW_PATH, "r") as z:
    with z.open(csv_name) as f:
        pums = pd.read_csv(f, usecols=usecols, dtype=str)

print(f"Rows read: {len(pums):,}")

# Standardize column names.
rename_map = {
    puma_col: "PUMA",
    age_col: "AGEP",
    esr_col: "ESR",
    weight_col: "PWGTP",
}
if state_col:
    rename_map[state_col] = "ST"

pums = pums.rename(columns=rename_map)

# California-only PUMS file may not include ST, so assign it manually.
if "ST" not in pums.columns:
    pums["ST"] = "06"

for col in ["AGEP", "ESR", "PWGTP"]:
    pums[col] = pd.to_numeric(pums[col], errors="coerce")

pums["ST"] = pums["ST"].astype(str).str.zfill(2)
pums["puma"] = pums["PUMA"].map(clean_puma)

# California, ages 16-19.
youth = pums[
    (pums["ST"] == "06") &
    (pums["AGEP"].between(16, 19))
].copy()

print(f"California age 16-19 PUMS records: {len(youth):,}")

crosswalk = pd.read_csv(CROSSWALK_PATH, dtype=str)
crosswalk["puma"] = crosswalk["puma"].map(clean_puma)

sd_pumas = sorted(set(crosswalk["puma"]))
sd_youth = youth[youth["puma"].isin(sd_pumas)].copy()

print(f"San Diego PUMA age 16-19 records: {len(sd_youth):,}")
print(f"San Diego PUMAs used: {sd_pumas}")

if sd_youth.empty:
    print()
    print("Crosswalk PUMAs:")
    print(crosswalk)
    print()
    print("Sample PUMAs in California youth PUMS:")
    print(sorted(youth["puma"].dropna().unique())[:50])
    raise ValueError("No San Diego youth records found. Check PUMA codes in the crosswalk.")

# PUMA-level summary.
puma_rows = []
for puma, group in sd_youth.groupby("puma"):
    row = {"puma": puma}
    row.update(summarize(group))
    puma_rows.append(row)

puma_summary = pd.DataFrame(puma_rows)

puma_summary = puma_summary.merge(
    crosswalk[["puma", "puma_name", "area_share_in_sd_county"]],
    on="puma",
    how="left"
)

puma_out_path = OUT_DIR / "pums_youth_unemployment_16_19_san_diego_puma.csv"
puma_summary.to_csv(puma_out_path, index=False)

# County-level summary.
county_row = summarize(sd_youth)
county_summary = pd.DataFrame([{
    "geography": "San Diego County",
    "source_note": (
        "2024 ACS 5-year PUMS California person file; ages 16-19; "
        "weighted by PWGTP; unemployment denominator is civilian labor force ESR 1, 2, 3."
    ),
    **county_row
}])

county_out_path = OUT_DIR / "pums_youth_unemployment_16_19_san_diego_county.csv"
county_summary.to_csv(county_out_path, index=False)

print()
print(f"Saved: {puma_out_path}")
print(puma_summary)

print()
print(f"Saved: {county_out_path}")
print(county_summary)
