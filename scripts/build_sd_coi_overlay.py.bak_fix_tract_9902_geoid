from pathlib import Path
import pandas as pd
import re

def find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root")

def normalize_geoid(v):
    if pd.isna(v):
        return None
    digits = re.sub(r"\D", "", str(v))
    if not digits:
        return None
    return digits[-11:].zfill(11)

REPO_ROOT = find_repo_root(Path.cwd())
RAW = REPO_ROOT / "data" / "rawdomains" / "coi"
OUT = REPO_ROOT / "data" / "processed" / "overlays"
OUT.mkdir(parents=True, exist_ok=True)

src = RAW / "data.csv"
df = pd.read_csv(src, dtype=str)

df["tract_geoid"] = df["geoid20"].apply(normalize_geoid)
df["county_fips"] = df["county_fips"].astype(str).str.zfill(5)
df["year"] = pd.to_numeric(df["year"], errors="coerce")

# San Diego County + latest COI release year
df = df[(df["county_fips"] == "06073") & (df["year"] == 2023)].copy()

out = df[
    [
        "tract_geoid",
        "r_COI_nat", "c5_COI_nat",
        "r_ED_nat", "c5_ED_nat",
        "r_HE_nat", "c5_HE_nat",
        "r_SE_nat", "c5_SE_nat",
    ]
].copy()

# rename to cleaner frontend names
out = out.rename(columns={
    "r_COI_nat": "coi_score",
    "c5_COI_nat": "coi_level",
    "r_ED_nat": "coi_ed_score",
    "c5_ED_nat": "coi_ed_level",
    "r_HE_nat": "coi_he_score",
    "c5_HE_nat": "coi_he_level",
    "r_SE_nat": "coi_se_score",
    "c5_SE_nat": "coi_se_level",
})

# numeric conversion for score cols
for c in ["coi_score", "coi_ed_score", "coi_he_score", "coi_se_score"]:
    out[c] = pd.to_numeric(out[c], errors="coerce")

out = out.drop_duplicates("tract_geoid").copy()
out.to_csv(OUT / "sd_coi_2023.csv", index=False)

print("Saved:", OUT / "sd_coi_2023.csv")
print("Rows:", len(out))
print(out.head())