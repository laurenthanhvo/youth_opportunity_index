from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Expected layout:
# <repo>/
#   assistant_backend/
#     app/settings.py
#   data/
#   datasets.html
REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
BILLING_MODE = os.getenv("BILLING_MODE", "free").strip().lower()

TRACT_YOI_CSV = resolve_repo_path(
    os.getenv(
        "TRACT_YOI_CSV",
        "data/processed/yoi/yoi_components.csv",
    )
)

REGION_YOI_CSV = resolve_repo_path(
    os.getenv(
        "REGION_YOI_CSV",
        "data/processed/yoi/yoi_county_region_components.csv",
    )
)

TRACT_PUMA_CROSSWALK = resolve_repo_path(
    os.getenv(
        "TRACT_PUMA_CROSSWALK",
        "data/rawdomains/regions/2020_Census_Tract_to_2020_PUMA.txt",
    )
)

INDICATOR_META_CSV = resolve_repo_path(
    os.getenv(
        "INDICATOR_META_CSV",
        "data/processed/yoi/yoi_indicator_meta.csv",
    )
)

METHODOLOGY_FILE = resolve_repo_path(
    os.getenv("METHODOLOGY_FILE", "datasets.html")
)

FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500",
    ).split(",")
    if origin.strip()
]

# Paid Standard rates used only to estimate what the same request would cost
# after leaving the Gemini free tier.
FLASH_LITE_INPUT_USD_PER_MILLION = 0.30
FLASH_LITE_OUTPUT_USD_PER_MILLION = 2.50
