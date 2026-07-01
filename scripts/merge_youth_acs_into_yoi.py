from pathlib import Path
import re
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

    # Backup once before overwriting.
    if not BACKUP_PATH.exists():
        yoi.to_csv(BACKUP_PATH, index=False)
        print(f"Backup saved: {BACKUP_PATH}")

    # Preserve original all-age population before switching dashboard weighting to youth.
    if "total_population" in yoi.columns and "total_population_all_ages" not in yoi.columns:
        yoi = yoi.rename(columns={"total_population": "total_population_all_ages"})

    # Avoid duplicate columns if you rerun this script.
    new_cols = [
        "acs_total_population_all_ages",
        "youth_pop_14_24",
        "youth_share_14_24",
        "students_14_24",
        "student_share_14_24",
        "not_in_school_youth_14_24",
        "not_in_school_youth_share_14_24",
    ]

    yoi = yoi.drop(columns=[c for c in new_cols if c in yoi.columns], errors="ignore")

    youth_keep = youth[[
        "tract_geoid",
        "total_population",
        "youth_pop_14_24",
        "youth_share_14_24",
        "students_14_24",
        "student_share_14_24",
        "not_in_school_youth_14_24",
        "not_in_school_youth_share_14_24",
    ]].copy()

    youth_keep = youth_keep.rename(columns={
        "total_population": "acs_total_population_all_ages"
    })

    merged = yoi.merge(youth_keep, on="tract_geoid", how="left")

    # Important:
    # Existing aggregation scripts use "total_population" as the weighting column.
    # Set it to youth population so ZIP/district/region scores become youth-weighted.
    merged["total_population"] = merged["youth_pop_14_24"]

    # Optional cleaner aliases for dashboard display.
    merged["population_basis"] = "Youth ages 14–24"
    merged["youth_students_14_24"] = merged["students_14_24"]
    merged["youth_not_in_school_14_24"] = merged["not_in_school_youth_14_24"]

    missing = merged["youth_pop_14_24"].isna().sum()
    print(f"Rows in YOI: {len(merged):,}")
    print(f"Rows missing youth ACS data: {missing:,}")

    merged.to_csv(YOI_PATH, index=False)
    print(f"Updated: {YOI_PATH}")

    print()
    print("New columns added:")
    for c in [
        "total_population_all_ages",
        "total_population",
        "acs_total_population_all_ages",
        "youth_pop_14_24",
        "youth_share_14_24",
        "students_14_24",
        "student_share_14_24",
        "not_in_school_youth_14_24",
        "not_in_school_youth_share_14_24",
    ]:
        if c in merged.columns:
            print(f"  - {c}")


if __name__ == "__main__":
    main()