from __future__ import annotations

from pathlib import Path
import json

import geopandas as gpd


def find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root containing /data")


def simplify_if_possible(gdf: gpd.GeoDataFrame, tolerance: float = 0.0002) -> gpd.GeoDataFrame:
    try:
        gdf = gdf.copy()
        gdf["geometry"] = gdf["geometry"].simplify(tolerance, preserve_topology=True)
    except Exception:
        pass
    return gdf


def clean_points(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["Point", "MultiPoint"])].copy()
    try:
        mp = gdf.geometry.geom_type == "MultiPoint"
        gdf.loc[mp, "geometry"] = gdf.loc[mp, "geometry"].centroid
    except Exception:
        pass
    return gdf


def main() -> None:
    repo = find_repo_root(Path.cwd())
    data_dir = repo / "data"
    out_dir = data_dir / "processed" / "boundaries"
    out_dir.mkdir(parents=True, exist_ok=True)

    routes_shp = data_dir / "rawdomains" / "mobility" / "transit_routes_datasd" / "transit_routes_datasd.shp"
    stops_shp = data_dir / "rawdomains" / "mobility" / "transit_stops_datasd" / "transit_stops_datasd.shp"

    if not routes_shp.exists():
        raise FileNotFoundError(f"Missing routes shapefile: {routes_shp}")
    if not stops_shp.exists():
        raise FileNotFoundError(f"Missing stops shapefile: {stops_shp}")

    routes_gdf = gpd.read_file(routes_shp)
    if routes_gdf.crs is not None:
        routes_gdf = routes_gdf.to_crs(4326)
    routes_gdf = routes_gdf[routes_gdf.geometry.notna()].copy()
    routes_gdf = simplify_if_possible(routes_gdf)

    route_keep = [c for c in ["route_id", "route_name", "route_short_name", "route_long_name", "name"] if c in routes_gdf.columns]
    if not route_keep:
        route_keep = []
    routes_out = routes_gdf[route_keep + ["geometry"]].copy()
    routes_path = out_dir / "transit_routes.geojson"
    routes_out.to_file(routes_path, driver="GeoJSON")
    print(f"Wrote {routes_path}")

    stops_gdf = gpd.read_file(stops_shp)
    if stops_gdf.crs is not None:
        stops_gdf = stops_gdf.to_crs(4326)
    stops_gdf = clean_points(stops_gdf)

    stop_keep = [c for c in ["stop_id", "stop_name", "name"] if c in stops_gdf.columns]
    stops_out = stops_gdf[stop_keep + ["geometry"]].copy()
    stops_path = out_dir / "transit_stops.geojson"
    stops_out.to_file(stops_path, driver="GeoJSON")
    print(f"Wrote {stops_path}")

    # Tiny sanity check for feature counts
    for p in [routes_path, stops_path]:
        geo = json.loads(p.read_text())
        print(p.name, "features:", len(geo.get("features", [])))


if __name__ == "__main__":
    main()
