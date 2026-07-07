from pathlib import Path
import pandas as pd
import numpy as np
import shutil

REGION_PATH = Path("data/processed/yoi/yoi_county_region_components.csv")
VALIDATION_PATH = Path("data/processed/validation/workforce_validation_clean_county_region_summary.csv")
OUT_DIR = Path("data/processed/validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)

if not REGION_PATH.exists():
    raise FileNotFoundError(f"Missing {REGION_PATH}")

# Figure 10 Workforce report values
FIG10_EDUCATION = {
    "Metro San Diego": {
        "fig10_grad_rate": 88.0,
        "fig10_dropout_rate": 3.7,
    },
    "North County": {
        "fig10_grad_rate": 87.0,
        "fig10_dropout_rate": 8.7,
    },
    "South San Diego": {
        "fig10_grad_rate": 82.0,
        "fig10_dropout_rate": 8.7,
    },
    "East San Diego": {
        "fig10_grad_rate": 81.0,
        "fig10_dropout_rate": 11.6,
    },
}

def normalize_region_name(v):
    s = str(v).strip().lower().replace("_", " ")
    if "metro" in s:
        return "Metro San Diego"
    if "north" in s:
        return "North County"
    if "south" in s:
        return "South San Diego"
    if "east" in s:
        return "East San Diego"
    return str(v).strip()

def minmax_high_good(series):
    s = pd.to_numeric(series, errors="coerce")
    lo = s.min(skipna=True)
    hi = s.max(skipna=True)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi == lo:
        return pd.Series(np.nan, index=s.index)
    return (s - lo) / (hi - lo) * 100

def minmax_low_good(series):
    s = pd.to_numeric(series, errors="coerce")
    lo = s.min(skipna=True)
    hi = s.max(skipna=True)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi == lo:
        return pd.Series(np.nan, index=s.index)
    return (hi - s) / (hi - lo) * 100

df = pd.read_csv(REGION_PATH)

region_col = None
for c in ["county_region", "county_region_id", "region", "region_id"]:
    if c in df.columns:
        region_col = c
        break

if region_col is None:
    raise KeyError("Could not find county region column.")

df["county_region_clean"] = df[region_col].map(normalize_region_name)

df["fig10_grad_rate"] = df["county_region_clean"].map(
    lambda r: FIG10_EDUCATION.get(r, {}).get("fig10_grad_rate", np.nan)
)

df["fig10_dropout_rate"] = df["county_region_clean"].map(
    lambda r: FIG10_EDUCATION.get(r, {}).get("fig10_dropout_rate", np.nan)
)

df["fig10_grad_norm_0_100"] = minmax_high_good(df["fig10_grad_rate"])
df["fig10_dropout_inverse_norm_0_100"] = minmax_low_good(df["fig10_dropout_rate"])

df["education_workforce_aligned_score_0_100"] = (
    0.5 * df["fig10_grad_norm_0_100"] +
    0.5 * df["fig10_dropout_inverse_norm_0_100"]
)

# Also create 0–1 version in case dashboard logic expects domain-like scale somewhere.
df["education_workforce_aligned_score"] = df["education_workforce_aligned_score_0_100"] / 100

if "education_score" in df.columns:
    edu = pd.to_numeric(df["education_score"], errors="coerce")
    if edu.max(skipna=True) <= 1.01:
        edu = edu * 100
    df["education_current_score_0_100"] = edu
    df["education_gap_current_vs_workforce_aligned"] = (
        df["education_current_score_0_100"] -
        df["education_workforce_aligned_score_0_100"]
    )

df["education_workforce_aligned_rank_high_to_low"] = (
    df["education_workforce_aligned_score_0_100"]
    .rank(method="min", ascending=False)
    .astype("Int64")
)

# Backup and overwrite county-region YOI file
backup_path = REGION_PATH.with_suffix(REGION_PATH.suffix + ".bak_before_workforce_aligned_education")
if not backup_path.exists():
    shutil.copy2(REGION_PATH, backup_path)
    print(f"Backup saved: {backup_path}")

df.to_csv(REGION_PATH, index=False)
print(f"Updated: {REGION_PATH}")

comparison = df[[
    "county_region_clean",
    "fig10_grad_rate",
    "fig10_dropout_rate",
    "fig10_grad_norm_0_100",
    "fig10_dropout_inverse_norm_0_100",
    "education_workforce_aligned_score_0_100",
    "education_workforce_aligned_rank_high_to_low",
] + ([ "education_current_score_0_100", "education_gap_current_vs_workforce_aligned" ] if "education_current_score_0_100" in df.columns else [])].copy()

comparison = comparison.sort_values("education_workforce_aligned_rank_high_to_low")

comparison_path = OUT_DIR / "education_workforce_aligned_comparison.csv"
comparison.to_csv(comparison_path, index=False)

print(f"Saved: {comparison_path}")
print()
print(comparison)
