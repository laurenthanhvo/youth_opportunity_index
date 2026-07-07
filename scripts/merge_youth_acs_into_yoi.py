from pathlib import Path
import re
import shutil
import pandas as pd
import numpy as np

YOI_PATH = Path("data/processed/yoi/yoi_components.csv")
YOUTH_PATH = Path("data/processed/census/youth_acs_tract_indicators.csv")
BACKUP_PATH = Path("data/processed/yoi/yoi_components_before_youth_acs_backup.csv")


def normalize_geoid(v):
    if pd.isna(v):
        return None
    digits = re.sub(r"\D", "", str(v))
    if not digits:
        return None
    return digits.zfill(11)[-11:]


def main():
    if not YOI_PATH.exists():
        raise FileNotFoundError(f"Missing {YOI_PATH}")

    if not YOUTH_PATH.exists():
        raise FileNotFoundError(f"Missing {YOUTH_PATH}")

    yoi = pd.read_csv(YOI_PATH, dtype={"tract_geoid": str})
    youth = pd.read_csv(YOUTH_PATH, dtype={"tract_geoid": str})

    yoi["tract_geoid"] = yoi["tract_geoid"].map(normalize_geoid)
    youth["tract_geoid"] = youth["tract_geoid"].map(normalize_geoid)

    if not BACKUP_PATH.exists():
        shutil.copy2(YOI_PATH, BACKUP_PATH)
        print(f"Backup saved: {BACKUP_PATH}")

    # Preserve original total population once.
    if "total_population" in yoi.columns and "total_population_all_ages_original" not in yoi.columns:
        yoi = yoi.rename(columns={"total_population": "total_population_all_ages_original"})

    youth_cols = [
        "total_population_all_ages",
        "youth_pop_14_24",
        "youth_share_14_24",
        "youth_pop_14_21_report_aligned",
        "youth_pop_18_24_report_aligned",
        "students_14_24",
        "student_share_14_24",
        "students_14_21_report_aligned",
        "students_14_21_share_report_aligned",
        "not_in_school_youth_14_24",
        "not_in_school_youth_share_14_24",
        "not_in_school_youth_18_24_report_aligned",
        "not_in_school_youth_18_24_share_report_aligned",
    ]

    yoi = yoi.drop(columns=[c for c in youth_cols if c in yoi.columns], errors="ignore")

    youth_keep = youth[["tract_geoid"] + youth_cols].copy()
    merged = yoi.merge(youth_keep, on="tract_geoid", how="left")

    # Existing aggregation scripts usually weight by total_population.
    # Make that youth 14–24 so higher-level dashboard outputs are youth-weighted.
    merged["total_population"] = merged["youth_pop_14_24"]
    merged["population_basis"] = "Youth ages 14–24"

    missing = merged["youth_pop_14_24"].isna().sum()
    print(f"Rows: {len(merged):,}")
    print(f"Rows missing ACS youth fields: {missing:,}")

    merged.to_csv(YOI_PATH, index=False)
    print(f"Updated: {YOI_PATH}")

    print("\nAdded columns:")
    for c in youth_cols + ["total_population", "population_basis"]:
        if c in merged.columns:
            print(f" - {c}")


if __name__ == "__main__":
    main()