from pathlib import Path
import re

import pandas as pd
import geopandas as gpd


# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------

INPUT_SERVICES_FILE = "youth_services_geocoded_with_census_merged.csv"
OUTPUT_GEOJSON_FILE = "service_locations.geojson"

# Set to False if you want to include Census non-exact / review-needed matches.
FILTER_REVIEW_NEEDED = True

# Keeps only rows that can be assigned to San Diego County census tracts.
KEEP_ONLY_SD_TRACTS = True


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def find_repo_root(start: Path) -> Path:
    """
    Walk upward from the current folder until we find the repo root.
    The repo root is assumed to contain a /data folder.
    """
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root containing /data")

def normalize_geoid(v):
    """
    Normalize census tract GEOIDs to 11-digit strings.

    Handles:
    - 11-digit tract GEOID: 06073008504
    - 15-digit Census block GEOID: 060730085041002
    - 10-digit CA tract artifact missing leading zero
    """
    if pd.isna(v):
        return None

    s = str(v).strip()
    if not s:
        return None

    if s.endswith(".0"):
        s = s[:-2]

    digits = re.sub(r"\D", "", s)
    if not digits:
        return None

    # If this is a San Diego County tract/block GEOID, keep the tract part.
    # Example block GEOID: 060730085041002 -> tract GEOID: 06073008504
    if digits.startswith("06073") and len(digits) >= 11:
        return digits[:11]

    # If the San Diego GEOID appears inside a longer string, extract it.
    match = re.search(r"06073\d{6}", digits)
    if match:
        return match.group(0)

    # 10-digit CA GEOID artifact; add leading zero.
    if len(digits) == 10:
        normalized = digits.zfill(11)
        if normalized.startswith("06073"):
            return normalized
        return None

    # Already 11 digits, but not San Diego County.
    if len(digits) == 11:
        if digits.startswith("06073"):
            return digits
        return None

    return None

def pick_col(cols, candidates):
    lower = {str(c).lower(): c for c in cols}
    for cand in candidates:
        hit = lower.get(str(cand).lower())
        if hit is not None:
            return hit
    return None


def clean_text(v):
    if pd.isna(v):
        return None

    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None

    return s


def first_available_text(row, cols):
    for c in cols:
        if c and c in row.index:
            val = clean_text(row[c])
            if val:
                return val
    return None


def safe_read_geojson(path: Path) -> gpd.GeoDataFrame | None:
    if not path.exists():
        print(f"Warning: missing file: {path}")
        return None

    gdf = gpd.read_file(path)

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    return gdf

def add_youth_support_classification(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    type_text = df["type"].fillna("").astype(str).str.lower() if "type" in df.columns else ""
    programs_text = df["programs"].fillna("").astype(str).str.lower() if "programs" in df.columns else ""
    name_text = df["name"].fillna("").astype(str).str.lower() if "name" in df.columns else ""
    provider_text = df["provider_name"].fillna("").astype(str).str.lower() if "provider_name" in df.columns else ""

    text = type_text + " " + programs_text + " " + name_text + " " + provider_text

    excluded = text.str.contains(
        r"not youth supports|administrative|not a service site|move to health opportunity|move to health|not core youth supports",
        regex=True,
        na=False,
    )

    basic = text.str.contains(
        r"basic youth access|navigation|resource hub|teen center|youth-friendly|211|library",
        regex=True,
        na=False,
    )

    development = text.str.contains(
        r"youth development|enrichment|mentoring|leadership|after[- ]?school|teen programming|life skills|positive youth|tutoring|arts|sports",
        regex=True,
        na=False,
    )

    barrier = text.str.contains(
        r"barrier|case management|transportation|childcare|benefits|legal aid|legal|accommodation|family support|foster|immigrant|refugee|disabil|navigation",
        regex=True,
        na=False,
    )

    transition = text.str.contains(
        r"transition pathways|workforce|paid work|work experience|job coaching|job training|career|ged|dropout|alternative education|earn and learn|internship|apprentice|financial literacy|retention",
        regex=True,
        na=False,
    )

    segment = text.str.contains(
        r"foster|out[- ]?of[- ]?school|parenting youth|pregnant|disabil|lgbt|lgbtq|immigrant|refugee|justice|probation|reentry|homeless|transition[- ]?age|tay",
        regex=True,
        na=False,
    )

    df["indicator_basic_navigation"] = basic.astype(int)
    df["indicator_youth_development"] = development.astype(int)
    df["indicator_barrier_reduction"] = barrier.astype(int)
    df["indicator_transition_pathways"] = transition.astype(int)
    df["indicator_segment_specific"] = segment.astype(int)

    df["count_in_youth_supports"] = (
        ~excluded &
        (
            basic |
            development |
            barrier |
            transition |
            segment
        )
    ).astype(int)

    df["tier_num"] = 0
    df.loc[basic, "tier_num"] = df.loc[basic, "tier_num"].clip(lower=1)
    df.loc[development, "tier_num"] = df.loc[development, "tier_num"].clip(lower=2)
    df.loc[barrier, "tier_num"] = df.loc[barrier, "tier_num"].clip(lower=3)
    df.loc[transition, "tier_num"] = df.loc[transition, "tier_num"].clip(lower=4)

    df.loc[df["count_in_youth_supports"] == 0, "tier_num"] = 0

    tier_labels = {
        0: "Not counted in Youth Supports",
        1: "Tier 1: Basic Youth Access and Navigation",
        2: "Tier 2: Youth Development and Enrichment",
        3: "Tier 3: Barrier-Reduction and Targeted Support",
        4: "Tier 4: Transition Pathways and Intensive Wraparound Support",
    }

    tier_weights = {
        0: 0.0,
        1: 1.0,
        2: 1.5,
        3: 2.0,
        4: 2.5,
    }

    df["tier_label"] = df["tier_num"].map(tier_labels)
    df["tier_weight"] = df["tier_num"].map(tier_weights).fillna(0.0)

    return df


# ---------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------

def main() -> None:
    repo_root = find_repo_root(Path.cwd())

    raw_dir = repo_root / "data" / "rawdomains"
    out_dir = repo_root / "data" / "processed" / "overlays"
    out_dir.mkdir(parents=True, exist_ok=True)

    services_csv = raw_dir / "youth" / INPUT_SERVICES_FILE
    tracts_geojson = repo_root / "data" / "processed" / "boundaries" / "sd_tracts.geojson"
    yoi_csv = repo_root / "data" / "processed" / "yoi" / "yoi_components.csv"
    stops_geojson = repo_root / "data" / "processed" / "boundaries" / "transit_stops.geojson"

    out_path = out_dir / OUTPUT_GEOJSON_FILE

    print("Repo root:", repo_root)
    print("Input services CSV:", services_csv)
    print("Output GeoJSON:", out_path)

    if not services_csv.exists():
        raise FileNotFoundError(
            f"Missing {services_csv}\n\n"
            f"Put your file here:\n"
            f"  data/rawdomains/youth/{INPUT_SERVICES_FILE}"
        )

    svc = pd.read_csv(services_csv, dtype=str)
    print("Input rows:", len(svc))
    print("Input columns:", svc.columns.tolist())

    lat_col = pick_col(svc.columns, ["latitude", "lat", "y"])
    lon_col = pick_col(svc.columns, ["longitude", "lon", "lng", "x"])

    if lat_col is None or lon_col is None:
        raise ValueError(
            f"Could not find latitude/longitude columns in {services_csv.name}.\n"
            f"Expected latitude/longitude or lat/lon.\n"
            f"Columns were: {svc.columns.tolist()}"
        )

    tract_col = pick_col(svc.columns, ["tract_geoid", "census_geoid", "census_tract", "GEOID", "geoid", "tract"])
    id_col = pick_col(svc.columns, ["service_id", "id", "row_id", "original_id"])
    provider_col = pick_col(svc.columns, ["provider_name", "organization_name", "agency_name", "provider", "organization"])
    site_col = pick_col(svc.columns, ["site_name", "name", "location_name"])
    type_col = pick_col(svc.columns, ["type_of_service", "tier", "type", "category", "service_type", "organization_type"])
    programs_col = pick_col(svc.columns, ["program_or_service", "programs", "program", "services", "service", "focus_area"])
    addr_col = pick_col(svc.columns, ["address", "street_address", "addr1", "full_address"])
    city_col = pick_col(svc.columns, ["city", "municipality"])
    zip_col = pick_col(svc.columns, ["zip", "zipcode", "zip_code", "postal_code"])
    source_col = pick_col(svc.columns, ["source_url", "source", "data_source"])
    geocode_status_col = pick_col(svc.columns, ["geocode_status", "census_match_status", "match_status"])
    geocode_source_col = pick_col(svc.columns, ["geocode_source", "census_source", "match_source"])
    review_col = pick_col(svc.columns, ["geocode_review_needed", "review_needed", "needs_review"])

    if FILTER_REVIEW_NEEDED and review_col:
        before = len(svc)
        svc = svc[
            svc[review_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            .ne("yes")
        ].copy()
        print(f"Filtered geocode_review_needed == Yes: {before} -> {len(svc)} rows")

    svc["lat"] = pd.to_numeric(svc[lat_col], errors="coerce")
    svc["lon"] = pd.to_numeric(svc[lon_col], errors="coerce")

    before = len(svc)
    svc = svc.dropna(subset=["lat", "lon"]).copy()
    print(f"Dropped rows missing lat/lon: {before} -> {len(svc)} rows")

    before = len(svc)
    svc = svc[
        svc["lat"].between(32.0, 34.5) &
        svc["lon"].between(-118.7, -115.5)
    ].copy()
    print(f"Kept plausible San Diego-region coordinates: {before} -> {len(svc)} rows")

    if tract_col:
        svc["tract_geoid"] = svc[tract_col].apply(normalize_geoid)
    else:
        svc["tract_geoid"] = None

    # Treat non-San Diego or malformed tract IDs as missing so the spatial join can fix them.
    svc.loc[
        ~svc["tract_geoid"].astype(str).str.startswith("06073", na=False),
        "tract_geoid"
    ] = None

    gdf = gpd.GeoDataFrame(
        svc.copy(),
        geometry=gpd.points_from_xy(svc["lon"], svc["lat"]),
        crs="EPSG:4326"
    )

    tracts = safe_read_geojson(tracts_geojson)

    if tracts is not None and len(tracts) > 0:
        tract_geo_col = pick_col(tracts.columns, ["tract_geoid", "GEOID", "geoid"])

        if tract_geo_col is not None:
            tracts = tracts[[tract_geo_col, "geometry"]].copy()
            tracts = tracts.rename(columns={tract_geo_col: "tract_join_geoid"})
            tracts["tract_join_geoid"] = tracts["tract_join_geoid"].apply(normalize_geoid)
            tracts = tracts.to_crs(gdf.crs)

            missing_mask = gdf["tract_geoid"].isna()

            if missing_mask.any():
                joined = gpd.sjoin(
                    gdf.loc[missing_mask, ["geometry"]],
                    tracts[["tract_join_geoid", "geometry"]],
                    how="left",
                    predicate="within"
                )

                joined = joined[~joined.index.duplicated(keep="first")]
                gdf.loc[joined.index, "tract_geoid"] = joined["tract_join_geoid"]

    if KEEP_ONLY_SD_TRACTS:
        before = len(gdf)
        has_any_sd_tracts = gdf["tract_geoid"].astype(str).str.startswith("06073", na=False).any()

        if has_any_sd_tracts:
            gdf = gdf[
                gdf["tract_geoid"].astype(str).str.startswith("06073", na=False)
            ].copy()
            print(f"Kept San Diego County tract rows: {before} -> {len(gdf)} rows")

    if "total_population" in gdf.columns:
        gdf = gdf.drop(columns=["total_population"])

    if yoi_csv.exists():
        yoi = pd.read_csv(yoi_csv, dtype={"tract_geoid": str})
        yoi["tract_geoid"] = yoi["tract_geoid"].apply(normalize_geoid)

        if "total_population" in yoi.columns:
            pop = yoi[["tract_geoid", "total_population"]].drop_duplicates("tract_geoid").copy()
            gdf = gdf.merge(pop, on="tract_geoid", how="left")
        else:
            gdf["total_population"] = None
    else:
        gdf["total_population"] = None

    gdf["closest_stop_name"] = None
    gdf["closest_stop_dist_m"] = None

    stops = safe_read_geojson(stops_geojson)

    if stops is not None and len(stops) > 0 and len(gdf) > 0:
        stop_name_col = pick_col(stops.columns, ["stop_name", "name", "stop_id"])

        if stop_name_col is None:
            stops["stop_label"] = "Transit stop"
        else:
            stops["stop_label"] = stops[stop_name_col].astype(str)

        stops = stops[stops.geometry.notna()].copy()

        if len(stops) > 0:
            gdf_proj = gdf.to_crs(3310)
            stops_proj = stops.to_crs(3310)[["stop_label", "geometry"]].copy()

            nearest = gpd.sjoin_nearest(
                gdf_proj,
                stops_proj,
                how="left",
                distance_col="dist_m"
            )

            nearest = nearest[~nearest.index.duplicated(keep="first")]
            nearest = nearest.reindex(gdf.index)

            gdf["closest_stop_name"] = nearest["stop_label"].map(clean_text)

            dist = pd.to_numeric(nearest["dist_m"], errors="coerce").round()
            gdf["closest_stop_dist_m"] = dist.astype("Int64").astype(str).replace("<NA>", None)

    name_candidates = [
        site_col,
        provider_col,
        pick_col(gdf.columns, ["name"]),
        pick_col(gdf.columns, ["organization_name"]),
        pick_col(gdf.columns, ["agency_name"]),
    ]

    gdf["name"] = gdf.apply(lambda row: first_available_text(row, name_candidates), axis=1)
    gdf["type"] = gdf[type_col].map(clean_text) if type_col else None
    gdf["programs"] = gdf[programs_col].map(clean_text) if programs_col else None
    gdf["address"] = gdf[addr_col].map(clean_text) if addr_col else None
    gdf["city"] = gdf[city_col].map(clean_text) if city_col else None
    gdf["zip"] = gdf[zip_col].map(clean_text) if zip_col else None
    gdf["source"] = gdf[source_col].map(clean_text) if source_col else services_csv.name
    gdf["service_id"] = gdf[id_col].map(clean_text) if id_col else gdf.index.astype(str)
    gdf["provider_name"] = gdf[provider_col].map(clean_text) if provider_col else None
    gdf["site_name"] = gdf[site_col].map(clean_text) if site_col else None
    gdf["geocode_status"] = gdf[geocode_status_col].map(clean_text) if geocode_status_col else None
    gdf["geocode_source"] = gdf[geocode_source_col].map(clean_text) if geocode_source_col else None
    gdf["geocode_review_needed"] = gdf[review_col].map(clean_text) if review_col else None

    gdf = add_youth_support_classification(gdf)

    keep = [
        "service_id",
        "provider_name",
        "site_name",
        "name",
        "type",
        "programs",
        "address",
        "city",
        "zip",
        "lat",
        "lon",
        "tract_geoid",
        "total_population",
        "closest_stop_name",
        "closest_stop_dist_m",
        "source",
        "geocode_status",
        "geocode_source",
        "geocode_review_needed",
        "geometry",
        "tier_num",
        "tier_label",
        "tier_weight",
        "count_in_youth_supports",
        "indicator_basic_navigation",
        "indicator_youth_development",
        "indicator_barrier_reduction",
        "indicator_transition_pathways",
        "indicator_segment_specific",
    ]

    keep = [c for c in keep if c in gdf.columns]

    out = gdf[keep].copy()
    out = out.where(pd.notna(out), None)

    out.to_file(out_path, driver="GeoJSON")

    print("Saved:", out_path)
    print("Rows:", len(out))
    print(out.head())


if __name__ == "__main__":
    main()