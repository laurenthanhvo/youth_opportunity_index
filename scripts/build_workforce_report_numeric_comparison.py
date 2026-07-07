from pathlib import Path
import pandas as pd
import numpy as np

OUT_DIR = Path("data/processed/validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DASH_PATH = OUT_DIR / "workforce_validation_clean_county_region_summary.csv"

if not DASH_PATH.exists():
    raise FileNotFoundError(f"Missing {DASH_PATH}. Run build_clean_workforce_validation_summary.py first.")

dash = pd.read_csv(DASH_PATH)

# Workforce report values from your validation write-up.
report_population = {
    "Metro San Diego": 180692,
    "North County": 133405,
    "South San Diego": 89839,
    "East San Diego": 72778,
}

report_service_counts = {
    "Metro San Diego": {"education": 175, "employment": 154, "wraparound": 230},
    "North County": {"education": 72, "employment": 71, "wraparound": 99},
    "South San Diego": {"education": 39, "employment": 35, "wraparound": 59},
    "East San Diego": {"education": 42, "employment": 29, "wraparound": 61},
}

dashboard_service_counts = {
    "Metro San Diego": {"education": 76, "employment": 91, "wraparound": 143},
    "North County": {"education": 28, "employment": 24, "wraparound": 67},
    "South San Diego": {"education": 11, "employment": 11, "wraparound": 36},
    "East San Diego": {"education": 23, "employment": 5, "wraparound": 40},
}

rows = []

# ------------------------------------------------------------
# Population comparison
# ------------------------------------------------------------
for region, report_value in report_population.items():
    d = dash[dash["county_region"] == region].iloc[0]
    dash_value = float(d["youth_population_basis"])
    diff = dash_value - report_value
    pct_diff = diff / report_value if report_value else np.nan

    rows.append({
        "comparison_group": "Youth population / geography check",
        "metric": "Youth population ages 14-24 / dashboard population basis",
        "region": region,
        "workforce_report_value": report_value,
        "dashboard_value": round(dash_value),
        "difference": round(diff),
        "percent_difference": pct_diff,
        "alignment": "Strong match" if abs(pct_diff) <= 0.02 else "Review",
        "note": "Dashboard regional population basis closely matches Workforce report youth population."
    })

# ------------------------------------------------------------
# Regional YOI score comparison
# ------------------------------------------------------------
for _, d in dash.iterrows():
    region = d["county_region"]

    rows.append({
        "comparison_group": "YOI regional score",
        "metric": "Overall YOI",
        "region": region,
        "workforce_report_value": "",
        "dashboard_value": d["overall_yoi_0_100"],
        "difference": "",
        "percent_difference": "",
        "alignment": "Context only",
        "note": "YOI is a dashboard index, not a direct Workforce report metric."
    })

    rows.append({
        "comparison_group": "YOI economic pattern",
        "metric": "Economic score",
        "region": region,
        "workforce_report_value": "",
        "dashboard_value": d["economic_0_100"],
        "difference": "",
        "percent_difference": "",
        "alignment": (
            "Matches South distress" if region == "South San Diego" and d["economic_rank_low_to_high"] == 1
            else "Partial / context"
        ),
        "note": "Compare directionally against Workforce report unemployment and labor-force participation."
    })

    rows.append({
        "comparison_group": "YOI education pattern",
        "metric": "Education score",
        "region": region,
        "workforce_report_value": "",
        "dashboard_value": d["education_0_100"],
        "difference": "",
        "percent_difference": "",
        "alignment": (
            "Matches Metro best" if region == "Metro San Diego"
            else "Partial / review" if region in ["East San Diego", "North County"]
            else "Context"
        ),
        "note": "Workforce report identifies Metro as strongest and East as weakest by graduation/dropout. Dashboard has Metro highest but North lowest."
    })

# ------------------------------------------------------------
# Workforce narrative benchmark rows
# ------------------------------------------------------------
narrative_rows = [
    {
        "metric": "Youth unemployment rate",
        "region": "South San Diego",
        "workforce_report_value": "31%",
        "dashboard_value": "Economic score 38.0/100, lowest",
        "alignment": "Match",
        "note": "South is worst in Workforce unemployment and worst in dashboard economic score."
    },
    {
        "metric": "Youth unemployment rate",
        "region": "North County",
        "workforce_report_value": "9%",
        "dashboard_value": "Economic score 46.3/100, second-highest",
        "alignment": "Partial",
        "note": "North is best in Workforce unemployment, but current dashboard economic score is slightly below Metro."
    },
    {
        "metric": "Labor-force participation rate",
        "region": "North County",
        "workforce_report_value": "44%",
        "dashboard_value": "Economic score 46.3/100, second-highest",
        "alignment": "Partial",
        "note": "North remains relatively strong economically but is not the highest current dashboard economic score."
    },
    {
        "metric": "Labor-force participation rate",
        "region": "South San Diego",
        "workforce_report_value": "30%",
        "dashboard_value": "Economic score 38.0/100, lowest",
        "alignment": "Match",
        "note": "South is weakest in both."
    },
    {
        "metric": "High school graduation rate",
        "region": "Metro San Diego",
        "workforce_report_value": "88%",
        "dashboard_value": "Education score 58.9/100, highest",
        "alignment": "Match",
        "note": "Metro is strongest in both Workforce graduation and dashboard education score."
    },
    {
        "metric": "High school dropout rate",
        "region": "East San Diego",
        "workforce_report_value": "11.6%",
        "dashboard_value": "Education score 44.9/100, second-lowest",
        "alignment": "Partial",
        "note": "East is weak in dashboard education, but North is lower."
    },
]

for r in narrative_rows:
    rows.append({
        "comparison_group": "Figure 10 regional outcomes",
        "metric": r["metric"],
        "region": r["region"],
        "workforce_report_value": r["workforce_report_value"],
        "dashboard_value": r["dashboard_value"],
        "difference": "",
        "percent_difference": "",
        "alignment": r["alignment"],
        "note": r["note"],
    })

# ------------------------------------------------------------
# Service count comparison
# ------------------------------------------------------------
for service_type in ["education", "employment", "wraparound"]:
    report_total = sum(v[service_type] for v in report_service_counts.values())
    dash_total = sum(v[service_type] for v in dashboard_service_counts.values())

    for region in report_service_counts:
        report_value = report_service_counts[region][service_type]
        dash_value = dashboard_service_counts[region][service_type]

        report_share = report_value / report_total
        dash_share = dash_value / dash_total
        share_diff_pp = (dash_share - report_share) * 100

        rows.append({
            "comparison_group": "Figure 22 service counts",
            "metric": f"{service_type.title()} service sites",
            "region": region,
            "workforce_report_value": report_value,
            "dashboard_value": dash_value,
            "difference": dash_value - report_value,
            "percent_difference": (dash_value - report_value) / report_value if report_value else np.nan,
            "alignment": (
                "Strong share match" if abs(share_diff_pp) <= 3
                else "Review"
            ),
            "note": f"Report share {report_share*100:.1f}%; dashboard share {dash_share*100:.1f}%; share difference {share_diff_pp:+.1f} percentage points."
        })

out = pd.DataFrame(rows)

csv_path = OUT_DIR / "workforce_report_numeric_comparison.csv"
out.to_csv(csv_path, index=False)

# Human-readable summary
lines = []
lines.append("# Workforce Report Numeric Comparison")
lines.append("")
lines.append("## Key conclusion")
lines.append("")
lines.append("The current dashboard strongly matches the Workforce report on regional population scale, South San Diego economic distress, Metro as the largest hub, and wraparound-service distribution. It only partially matches the report on North County's economic strength and East San Diego's education weakness. The biggest current mismatch is that North County is now the lowest overall YOI region because of a very low Youth Supports score.")
lines.append("")
lines.append("## Comparison table")
lines.append("")
lines.append(out.to_csv(index=False))

md_path = OUT_DIR / "workforce_report_numeric_comparison.md"
md_path.write_text("\n".join(lines))

print(f"Saved: {csv_path}")
print(f"Saved: {md_path}")

print()
print("Alignment counts:")
print(out["alignment"].value_counts())

print()
print("Preview:")
print(out[["comparison_group", "metric", "region", "workforce_report_value", "dashboard_value", "alignment"]].head(30))
