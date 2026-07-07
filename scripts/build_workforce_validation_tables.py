from pathlib import Path
import pandas as pd
import numpy as np

OUT_DIR = Path("data/processed/validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)

REGION_PATH = Path("data/processed/yoi/yoi_county_region_components.csv")
CONTEXT_PATH = Path("data/processed/workforce/workforce_context_summary.csv")

if not REGION_PATH.exists():
    raise FileNotFoundError(f"Missing {REGION_PATH}")

if not CONTEXT_PATH.exists():
    raise FileNotFoundError(f"Missing {CONTEXT_PATH}")

regions = pd.read_csv(REGION_PATH)
context = pd.read_csv(CONTEXT_PATH)

def pick_col(df, options):
    for c in options:
        if c in df.columns:
            return c
    return None

region_col = pick_col(regions, ["county_region", "county_region_id", "region", "region_id"])
if region_col is None:
    raise KeyError("Could not find county region column.")

score_cols = [
    c for c in [
        "yoi_custom_0_100",
        "economic_score",
        "education_score",
        "health_score",
        "housing_score",
        "safety_env_score",
        "mobility_connectivity_score",
        "youth_supports_score",
        "youth_pop_14_24",
        "students_14_24",
        "not_in_school_youth_14_24",
        "students_14_21_report_aligned",
        "not_in_school_youth_18_24_report_aligned",
        "total_population",
    ]
    if c in regions.columns
]

summary = regions[[region_col] + score_cols].copy()
summary = summary.rename(columns={region_col: "county_region"})

# Convert scores to 0-100 display versions where needed.
for c in summary.columns:
    if c.endswith("_score"):
        vals = pd.to_numeric(summary[c], errors="coerce")
        if vals.max(skipna=True) <= 1.01:
            summary[c.replace("_score", "_score_0_100")] = vals * 100

if "yoi_custom_0_100" in summary.columns:
    summary["overall_yoi_rank_low_to_high"] = (
        pd.to_numeric(summary["yoi_custom_0_100"], errors="coerce")
        .rank(method="min", ascending=True)
        .astype("Int64")
    )

if "economic_score" in summary.columns:
    economic_vals = pd.to_numeric(summary["economic_score"], errors="coerce")
    if economic_vals.max(skipna=True) <= 1.01:
        economic_vals = economic_vals * 100
    summary["economic_rank_low_to_high"] = economic_vals.rank(method="min", ascending=True).astype("Int64")

if "education_score" in summary.columns:
    education_vals = pd.to_numeric(summary["education_score"], errors="coerce")
    if education_vals.max(skipna=True) <= 1.01:
        education_vals = education_vals * 100
    summary["education_rank_low_to_high"] = education_vals.rank(method="min", ascending=True).astype("Int64")

if "youth_supports_score" in summary.columns:
    supports_vals = pd.to_numeric(summary["youth_supports_score"], errors="coerce")
    if supports_vals.max(skipna=True) <= 1.01:
        supports_vals = supports_vals * 100
    summary["youth_supports_rank_low_to_high"] = supports_vals.rank(method="min", ascending=True).astype("Int64")

summary_path = OUT_DIR / "workforce_validation_county_region_yoi_summary.csv"
summary.to_csv(summary_path, index=False)

context_path = OUT_DIR / "workforce_validation_countywide_context.csv"
context.to_csv(context_path, index=False)

# Build a lightweight narrative input file.
lines = []
lines.append("# Workforce Report Validation Inputs")
lines.append("")
lines.append("## Countywide context indicators")
for _, r in context.iterrows():
    lines.append(f"- {r['indicator']}: {r['value']} ({r['source']}; {r['source_type']})")

lines.append("")
lines.append("## Dashboard county-region YOI summary")
lines.append(summary.to_csv(index=False))

lines.append("")
lines.append("## Validation framing")
lines.append("- Treat this as directional validation, not exact one-to-one replication.")
lines.append("- The Workforce report uses county, regional, and PUMA-level evidence.")
lines.append("- The dashboard uses tract/ZIP/district/region YOI scores, so the strongest comparison is regional pattern alignment.")
lines.append("- Main validation question: do the dashboard's lowest-opportunity regions/domains line up with the Workforce report's South/East distress, North relative labor-market strength, and Metro service/demand hub pattern?")

md_path = OUT_DIR / "workforce_validation_notes.md"
md_path.write_text("\n".join(lines))

print(f"Saved: {summary_path}")
print(f"Saved: {context_path}")
print(f"Saved: {md_path}")
print()
print(summary)
