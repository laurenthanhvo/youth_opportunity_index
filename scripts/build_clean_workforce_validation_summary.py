from pathlib import Path
import pandas as pd
import numpy as np

IN_PATH = Path("data/processed/validation/workforce_validation_county_region_yoi_summary.csv")
CTX_PATH = Path("data/processed/workforce/workforce_context_summary.csv")
OUT_DIR = Path("data/processed/validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)

regions = pd.read_csv(IN_PATH)
ctx = pd.read_csv(CTX_PATH)

domain_cols = {
    "economic": "economic_score_0_100",
    "education": "education_score_0_100",
    "health": "health_score_0_100",
    "housing": "housing_score_0_100",
    "safety_env": "safety_env_score_0_100",
    "mobility_connectivity": "mobility_connectivity_score_0_100",
    "youth_supports": "youth_supports_score_0_100",
}

domain_labels = {
    "economic": "Economic",
    "education": "Education",
    "health": "Health",
    "housing": "Housing",
    "safety_env": "Safety / Env",
    "mobility_connectivity": "Mobility / Connectivity",
    "youth_supports": "Youth Supports",
}

clean_rows = []

for _, r in regions.iterrows():
    scores = {
        label: float(r[col])
        for key, col in domain_cols.items()
        if col in regions.columns and pd.notna(r[col])
        for label in [domain_labels[key]]
    }

    lowest_domain = min(scores, key=scores.get)
    strongest_domain = max(scores, key=scores.get)

    clean_rows.append({
        "county_region": r["county_region"],
        "overall_yoi_0_100": round(float(r["yoi_custom_0_100"]), 1),
        "overall_rank_low_to_high": int(r["overall_yoi_rank_low_to_high"]),
        "economic_0_100": round(float(r["economic_score_0_100"]), 1),
        "economic_rank_low_to_high": int(r["economic_rank_low_to_high"]),
        "education_0_100": round(float(r["education_score_0_100"]), 1),
        "health_0_100": round(float(r["health_score_0_100"]), 1),
        "housing_0_100": round(float(r["housing_score_0_100"]), 1),
        "safety_env_0_100": round(float(r["safety_env_score_0_100"]), 1),
        "mobility_connectivity_0_100": round(float(r["mobility_connectivity_score_0_100"]), 1),
        "youth_supports_0_100": round(float(r["youth_supports_score_0_100"]), 1),
        "lowest_domain": lowest_domain,
        "lowest_domain_score": round(scores[lowest_domain], 1),
        "strongest_domain": strongest_domain,
        "strongest_domain_score": round(scores[strongest_domain], 1),
        "youth_population_basis": round(float(r["total_population"])),
    })

clean = pd.DataFrame(clean_rows).sort_values("overall_rank_low_to_high")

clean_path = OUT_DIR / "workforce_validation_clean_county_region_summary.csv"
clean.to_csv(clean_path, index=False)

def context_value(field):
    row = ctx[ctx["field"] == field]
    if row.empty:
        return np.nan
    return float(row.iloc[0]["value"])

grad = context_value("cde_adjusted_cohort_graduation_rate")
drop = context_value("cde_four_year_cohort_dropout_rate")
homeless = context_value("cde_homeless_students")
homeless_rate = context_value("cde_homeless_student_rate")
el = context_value("english_learner_students")
unemp = context_value("youth_unemployment_rate_16_19_pums")
lfp = context_value("labor_force_participation_rate_16_19_pums")

def pct(x):
    if pd.isna(x):
        return "N/A"
    return f"{x * 100:.1f}%" if x <= 1 else f"{x:.1f}%"

def num(x):
    if pd.isna(x):
        return "N/A"
    return f"{round(x):,}"

lowest_overall = clean.iloc[0]
highest_overall = clean.sort_values("overall_rank_low_to_high", ascending=False).iloc[0]
lowest_econ = clean.sort_values("economic_0_100").iloc[0]
lowest_supports = clean.sort_values("youth_supports_0_100").iloc[0]

lines = []
lines.append("# Workforce Report Validation Draft")
lines.append("")
lines.append("## Countywide context benchmarks")
lines.append("")
lines.append(f"- CDE adjusted cohort graduation rate: **{grad:.1f}%**")
lines.append(f"- CDE four-year cohort dropout rate: **{drop:.1f}%**")
lines.append(f"- CDE homeless students: **{num(homeless)}**")
lines.append(f"- CDE homeless student rate: **{pct(homeless_rate)}**")
lines.append(f"- CDE English learner students: **{num(el)}**")
lines.append(f"- ACS PUMS youth unemployment rate, ages 16–19: **{pct(unemp)}**")
lines.append(f"- ACS PUMS labor force participation rate, ages 16–19: **{pct(lfp)}**")
lines.append("")
lines.append("## County-region YOI pattern")
lines.append("")
lines.append(f"- The lowest overall YOI region is **{lowest_overall['county_region']}** with an overall score of **{lowest_overall['overall_yoi_0_100']}/100**.")
lines.append(f"- The highest overall YOI region is **{highest_overall['county_region']}** with an overall score of **{highest_overall['overall_yoi_0_100']}/100**.")
lines.append(f"- The lowest economic-domain region is **{lowest_econ['county_region']}** with an economic score of **{lowest_econ['economic_0_100']}/100**.")
lines.append(f"- The lowest youth-supports region is **{lowest_supports['county_region']}** with a youth-supports score of **{lowest_supports['youth_supports_0_100']}/100**.")
lines.append("")
lines.append("## Clean county-region table")
lines.append("")
lines.append(clean.to_csv(index=False))
lines.append("")
lines.append("## Validation interpretation")
lines.append("")
lines.append("The dashboard should be validated directionally against the Workforce report rather than treated as an exact replication. The Workforce report combines countywide CDE indicators, ACS/PUMS labor-force indicators, and regional findings, while the dashboard computes normalized YOI scores across tracts, ZIP codes, districts, and county regions.")
lines.append("")
lines.append("The strongest validation use is therefore regional pattern alignment: whether the dashboard identifies similar areas of labor-market, education, service-access, and youth-support concern as the Workforce report. Countywide indicators such as graduation rate, dropout rate, homelessness, English learners, and PUMS youth unemployment should be used as context benchmarks, not as selected-tract values.")
lines.append("")
lines.append("## Important limitation")
lines.append("")
lines.append("The dashboard's region-level YOI scores are useful for comparing opportunity patterns, but the Workforce report metrics do not all share the same geography. CDE indicators are school/county based, PUMS unemployment is PUMA/county based, and ACS youth-population estimates are tract based. For this reason, the validation supports directional consistency, not exact one-to-one numeric agreement.")

draft_path = OUT_DIR / "workforce_validation_draft.md"
draft_path.write_text("\n".join(lines))

print(f"Saved: {clean_path}")
print(f"Saved: {draft_path}")
print()
print(clean)
