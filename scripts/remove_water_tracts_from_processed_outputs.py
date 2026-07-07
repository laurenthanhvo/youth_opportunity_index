from pathlib import Path
import json
import re
import shutil
import pandas as pd

EXCLUDED_TRACTS = {
    "06073009902",  # Census tract 99.02, water/harbor
    "06073990100",  # Census tract 9901.00, water/ocean
    "06073990200",  # Census tract 9902.00, water/ocean
}

def norm_geoid(v):
    if v is None:
        return ""
    digits = re.sub(r"\D", "", str(v))
    if not digits:
        return ""
    return digits.zfill(11)[-11:]

def backup(path: Path):
    bak = path.with_suffix(path.suffix + ".bak_before_water_tract_removal")
    if not bak.exists():
        shutil.copy2(path, bak)

# ------------------------------------------------------------
# 1. Patch app.js exclusion list
# ------------------------------------------------------------
app_path = Path("app.js")
if app_path.exists():
    backup(app_path)
    text = app_path.read_text()

    new_block = """const EXCLUDED_TRACT_GEOIDS = new Set([
  '06073009902', // Census tract 99.02, water/harbor
  '06073990100', // Census tract 9901.00, water/ocean
  '06073990200', // Census tract 9902.00, water/ocean
]);"""

    text = re.sub(
        r"const EXCLUDED_TRACT_GEOIDS = new Set\(\[[\s\S]*?\]\);",
        new_block,
        text,
        count=1,
    )

    app_path.write_text(text)
    print("Patched app.js exclusion list.")

# ------------------------------------------------------------
# 2. Remove rows from processed CSVs with tract GEOID columns
# ------------------------------------------------------------
for csv_path in Path("data/processed").rglob("*.csv"):
    try:
        df = pd.read_csv(csv_path, dtype=str)
    except Exception as e:
        print(f"Skipping CSV read error: {csv_path} ({e})")
        continue

    geoid_cols = [
        c for c in df.columns
        if c.lower() in {
            "tract_geoid",
            "geoid",
            "geoid20",
            "geoid10",
            "geoidfp",
            "census_tract",
        }
    ]

    if not geoid_cols:
        continue

    mask = pd.Series(False, index=df.index)

    for col in geoid_cols:
        mask = mask | df[col].map(norm_geoid).isin(EXCLUDED_TRACTS)

    removed = int(mask.sum())

    if removed > 0:
        backup(csv_path)
        df.loc[~mask].to_csv(csv_path, index=False)
        print(f"Removed {removed:,} rows from {csv_path}")

# ------------------------------------------------------------
# 3. Remove features from processed GeoJSONs with tract GEOIDs
# ------------------------------------------------------------
for geo_path in list(Path("data/processed").rglob("*.geojson")) + list(Path("data/processed").rglob("*.json")):
    try:
        obj = json.loads(geo_path.read_text())
    except Exception:
        continue

    if not isinstance(obj, dict) or obj.get("type") != "FeatureCollection":
        continue

    features = obj.get("features", [])
    if not isinstance(features, list):
        continue

    kept = []
    removed = 0

    for feature in features:
        props = feature.get("properties") or {}
        possible = [
            props.get("tract_geoid"),
            props.get("GEOID"),
            props.get("GEOID20"),
            props.get("GEOID10"),
            props.get("geoid"),
            props.get("Tract"),
            props.get("TRACT"),
            props.get("GEOIDFQ"),
        ]

        is_excluded = any(norm_geoid(v) in EXCLUDED_TRACTS for v in possible)

        if is_excluded:
            removed += 1
        else:
            kept.append(feature)

    if removed > 0:
        backup(geo_path)
        obj["features"] = kept
        geo_path.write_text(json.dumps(obj))
        print(f"Removed {removed:,} features from {geo_path}")

print()
print("Done removing water tracts:")
for g in sorted(EXCLUDED_TRACTS):
    print(" -", g)
