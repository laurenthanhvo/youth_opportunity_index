from pathlib import Path
import re
import pandas as pd
import numpy as np

RAW_DIR = Path("data/raw/cde/english_learners")
OUT_DIR = Path("data/processed/cde")
OUT_DIR.mkdir(parents=True, exist_ok=True)

EL_FILES = sorted(RAW_DIR.glob("fileselsch*.txt")) or sorted(RAW_DIR.glob("*.txt"))

if not EL_FILES:
    raise FileNotFoundError(
        "No English learner .txt file found in data/raw/cde/english_learners/"
    )

EL_PATH = EL_FILES[0]


def clean_num(series):
    return (
        series.astype(str)
        .str.strip()
        .replace({"": np.nan, "*": np.nan, "nan": np.nan, "None": np.nan})
        .str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )


def clean_text(series):
    return series.astype(str).str.strip()


print(f"Reading: {EL_PATH}")

# CDE text files may contain non-UTF characters, so try common encodings.
for enc in ["utf-8", "latin1", "cp1252"]:
    try:
        df = pd.read_csv(EL_PATH, sep="\t", dtype=str, engine="python", encoding=enc)
        print(f"Loaded with encoding: {enc}")
        break
    except UnicodeDecodeError:
        continue
else:
    df = pd.read_csv(EL_PATH, sep="\t", dtype=str, engine="python", encoding="latin1")
    print("Loaded with fallback encoding: latin1")

df.columns = [re.sub(r"\s+", " ", c).strip() for c in df.columns]

print("\nColumns found:")
for c in df.columns:
    print(" -", c)

required = ["CDS", "COUNTY", "DISTRICT", "SCHOOL", "LC", "LANGUAGE", "TOTAL_EL"]
missing = [c for c in required if c not in df.columns]
if missing:
    raise KeyError(f"Missing required columns: {missing}")

df["cds"] = df["CDS"].astype(str).str.strip()
df["county_name"] = clean_text(df["COUNTY"])
df["district_name"] = clean_text(df["DISTRICT"])
df["school_name"] = clean_text(df["SCHOOL"])
df["language_code"] = clean_text(df["LC"])
df["language"] = clean_text(df["LANGUAGE"])
df["english_learner_students"] = clean_num(df["TOTAL_EL"])

# San Diego County CDS codes start with 37.
san_diego = df[
    df["cds"].str.startswith("37", na=False)
    | df["county_name"].str.contains("San Diego", case=False, na=False)
].copy()

print(f"\nSan Diego language rows: {len(san_diego):,}")

# ------------------------------------------------------------
# School-language rows
# ------------------------------------------------------------
school_language_out = san_diego[[
    "cds",
    "county_name",
    "district_name",
    "school_name",
    "language_code",
    "language",
    "english_learner_students",
]].copy()

school_language_path = OUT_DIR / "english_learners_san_diego_school_language_rows.csv"
school_language_out.to_csv(school_language_path, index=False)

# ------------------------------------------------------------
# School totals: sum across languages within each school
# ------------------------------------------------------------
school_totals = (
    san_diego
    .groupby(["cds", "county_name", "district_name", "school_name"], dropna=False, as_index=False)
    .agg(english_learner_students=("english_learner_students", "sum"))
)

school_totals["source_note"] = (
    "CDE English Learners by Grade and Language; summed across languages by school. "
    "School-based count, not resident tract estimate."
)

school_totals_path = OUT_DIR / "english_learners_san_diego_school_totals.csv"
school_totals.to_csv(school_totals_path, index=False)

# ------------------------------------------------------------
# District totals: sum across schools/languages
# ------------------------------------------------------------
district_totals = (
    san_diego
    .groupby(["county_name", "district_name"], dropna=False, as_index=False)
    .agg(english_learner_students=("english_learner_students", "sum"))
)

district_totals["source_note"] = (
    "CDE English Learners by Grade and Language; summed across schools and languages by district. "
    "School-based count, not resident tract estimate."
)

district_totals_path = OUT_DIR / "english_learners_san_diego_district_totals.csv"
district_totals.to_csv(district_totals_path, index=False)

# ------------------------------------------------------------
# County total
# ------------------------------------------------------------
county_total = pd.DataFrame([{
    "county_name": "San Diego",
    "english_learner_students": san_diego["english_learner_students"].sum(skipna=True),
    "source_note": (
        "CDE English Learners by Grade and Language; summed across San Diego County school-language rows. "
        "School-based English learner count, not resident tract estimate."
    )
}])

county_path = OUT_DIR / "english_learners_san_diego_official_county.csv"
county_total.to_csv(county_path, index=False)

print()
print(f"Saved: {school_language_path}")
print(f"Rows: {len(school_language_out):,}")

print()
print(f"Saved: {school_totals_path}")
print(f"Rows: {len(school_totals):,}")

print()
print(f"Saved: {district_totals_path}")
print(f"Rows: {len(district_totals):,}")

print()
print(f"Saved: {county_path}")
print(county_total)