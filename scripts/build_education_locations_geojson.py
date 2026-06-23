from pathlib import Path
import re

import pandas as pd
import geopandas as gpd


def find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root containing /data")


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


def normalize_geoid(v):
    if pd.isna(v):
        return None

    digits = re.sub(r"\D", "", str(v))
    if not digits:
        return None

    if digits.startswith("06073") and len(digits) >= 11:
        return digits[:11]

    match = re.search(r"06073\d{6}", digits)
    if match:
        return match.group(0)

    if len(digits) == 10:
        digits = digits.zfill(11)
        return digits if digits.startswith("06073") else None

    if len(digits) == 11:
        return digits if digits.startswith("06073") else None

    return None


def force_point_geometry(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf[gdf.geometry.notna()].copy()

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    non_point = ~gdf.geometry.geom_type.isin(["Point", "MultiPoint"])
    if non_point.any():
        gdf_proj = gdf.to_crs(3310)
        gdf_proj.loc[non_point, "geometry"] = gdf_proj.loc[non_point, "geometry"].centroid
        gdf = gdf_proj.to_crs(4326)

    multi = gdf.geometry.geom_type == "MultiPoint"
    if multi.any():
        gdf_proj = gdf.to_crs(3310)
        gdf_proj.loc[multi, "geometry"] = gdf_proj.loc[multi, "geometry"].centroid
        gdf = gdf_proj.to_crs(4326)

    return gdf


def assign_tracts(points: gpd.GeoDataFrame, tracts_path: Path) -> gpd.GeoDataFrame:
    if not tracts_path.exists():
        raise FileNotFoundError(f"Missing tract GeoJSON: {tracts_path}")

    tracts = gpd.read_file(tracts_path)
    tract_col = pick_col(tracts.columns, ["tract_geoid", "GEOID", "geoid"])

    if tract_col is None:
        raise ValueError(f"Could not find tract GEOID column in {tracts_path}")

    tracts = tracts[[tract_col, "geometry"]].copy()
    tracts = tracts.rename(columns={tract_col: "tract_geoid"})
    tracts["tract_geoid"] = tracts["tract_geoid"].apply(normalize_geoid)

    if tracts.crs is None:
        tracts = tracts.set_crs("EPSG:4326")

    points = points.to_crs("EPSG:4326")
    tracts = tracts.to_crs(points.crs)

    joined = gpd.sjoin(
        points,
        tracts[["tract_geoid", "geometry"]],
        how="left",
        predicate="within",
    )

    joined = joined.drop(columns=["index_right"], errors="ignore")
    joined = joined[~joined.index.duplicated(keep="first")].copy()

    joined = joined[
        joined["tract_geoid"].astype(str).str.startswith("06073", na=False)
    ].copy()

    return joined


def build_school_locations(repo: Path, tracts_path: Path) -> gpd.GeoDataFrame:
    src = repo / "data/rawdomains/education/cde_school_sites/cde_school_sites_2425.geojson"

    if not src.exists():
        raise FileNotFoundError(f"Missing K-12 school source: {src}")

    gdf = gpd.read_file(src)

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    gdf = force_point_geometry(gdf)

    county_col = pick_col(gdf.columns, ["county", "county_name", "County", "CountyName"])
    if county_col:
        county_text = gdf[county_col].fillna("").astype(str).str.lower()
        gdf = gdf[county_text.str.contains("san diego", na=False)].copy()

    name_col = pick_col(gdf.columns, ["School", "school", "SchoolName", "school_name", "name", "Name"])
    district_col = pick_col(gdf.columns, ["District", "district", "DistrictName", "district_name"])
    type_col = pick_col(gdf.columns, ["SchoolType", "school_type", "Type", "type", "EdOpsCode", "SOC"])
    address_col = pick_col(gdf.columns, ["Street", "street", "Address", "address", "StreetAbr"])
    city_col = pick_col(gdf.columns, ["City", "city"])
    zip_col = pick_col(gdf.columns, ["Zip", "zip", "ZipCode", "zipcode"])

    gdf["name"] = gdf[name_col].map(clean_text) if name_col else "K-12 School"
    gdf["district"] = gdf[district_col].map(clean_text) if district_col else None
    gdf["type"] = gdf[type_col].map(clean_text) if type_col else "K-12 School"
    gdf["address"] = gdf[address_col].map(clean_text) if address_col else None
    gdf["city"] = gdf[city_col].map(clean_text) if city_col else None
    gdf["zip"] = gdf[zip_col].map(clean_text) if zip_col else None
    gdf["education_site_type"] = "K-12 School"
    gdf["source"] = "CDE California Public Schools / School Sites 2024-25"

    gdf = assign_tracts(gdf, tracts_path)

    keep = [
        "name",
        "district",
        "type",
        "education_site_type",
        "address",
        "city",
        "zip",
        "tract_geoid",
        "source",
        "geometry",
    ]

    return gdf[[c for c in keep if c in gdf.columns]].copy()


def build_college_locations(repo: Path, tracts_path: Path) -> gpd.GeoDataFrame:
    src = repo / "data/rawdomains/education/nces_postsecondary/EDGE_GEOCODE_POSTSECSCH_2425.TXT"

    if not src.exists():
        raise FileNotFoundError(f"Missing postsecondary source: {src}")

    # NCES EDGE TXT has no header row, so manually assign columns.
    nces_cols = [
        "unitid",
        "name",
        "address",
        "city",
        "state",
        "zip",
        "state_fips",
        "county_fips",
        "county_name",
        "locale",
        "latitude",
        "longitude",
        "cbsa_code",
        "cbsa_name",
        "degree_granting",
        "csa_code",
        "csa_name",
        "necta_code",
        "county_subdivision",
        "school_district",
        "school_year",
    ]

    df = pd.read_csv(
        src,
        dtype=str,
        header=None,
        names=nces_cols,
        sep="|",
        engine="python",
    )

    print("Read postsecondary TXT columns:", df.columns.tolist())
    print(df[["name", "city", "state", "latitude", "longitude"]].head())

    # Filter to California / San Diego County before geometry.
    df["state"] = df["state"].astype(str).str.strip()
    df["county_fips"] = df["county_fips"].astype(str).str.strip().str.zfill(5)

    df = df[
        (df["state"] == "CA") &
        (df["county_fips"] == "06073")
    ].copy()

    print("San Diego County postsecondary rows before coordinate cleanup:", len(df))

    df["lat"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["lon"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"]).copy()

    df = df[
        df["lat"].between(32.0, 34.5) &
        df["lon"].between(-118.7, -115.5)
    ].copy()

    print("San Diego County postsecondary rows after coordinate cleanup:", len(df))

    gdf = gpd.GeoDataFrame(
        df.copy(),
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326",
    )

    gdf["name"] = gdf["name"].map(clean_text)
    gdf["district"] = None
    gdf["type"] = "College / University"
    gdf["address"] = gdf["address"].map(clean_text)
    gdf["city"] = gdf["city"].map(clean_text)
    gdf["zip"] = gdf["zip"].map(clean_text)
    gdf["education_site_type"] = "College / University"
    gdf["source"] = "NCES EDGE / IPEDS Postsecondary School Locations 2024-25"

    gdf = assign_tracts(gdf, tracts_path)

    keep = [
        "unitid",
        "name",
        "district",
        "type",
        "education_site_type",
        "address",
        "city",
        "state",
        "zip",
        "lat",
        "lon",
        "tract_geoid",
        "source",
        "geometry",
    ]

    return gdf[[c for c in keep if c in gdf.columns]].copy()


def main():
    repo = find_repo_root(Path.cwd())

    out_dir = repo / "data/processed/overlays"
    out_dir.mkdir(parents=True, exist_ok=True)

    tracts_path = repo / "data/processed/boundaries/sd_tracts.geojson"

    schools = build_school_locations(repo, tracts_path)
    colleges = build_college_locations(repo, tracts_path)

    school_out = out_dir / "school_locations.geojson"
    college_out = out_dir / "college_locations.geojson"

    schools.to_file(school_out, driver="GeoJSON")
    colleges.to_file(college_out, driver="GeoJSON")

    print("Saved:", school_out)
    print("K-12 school rows:", len(schools))

    print("Saved:", college_out)
    print("College/university rows:", len(colleges))

    print("\nSchool sample:")
    print(schools.head())

    print("\nCollege sample:")
    print(colleges.head())


if __name__ == "__main__":
    main()