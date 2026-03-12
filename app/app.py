# app/app.py
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# optional overlays
try:
    import geopandas as gpd
    from folium.plugins import MarkerCluster
    _HAS_GPD = True
except Exception:
    gpd = None
    MarkerCluster = None
    _HAS_GPD = False

st.set_page_config(page_title="Youth Opportunity Index", layout="wide")

# -----------------------------
# Paths
# -----------------------------
def find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists():
            return p
    raise FileNotFoundError("Could not find repo root containing /data")

REPO_ROOT = find_repo_root(Path.cwd())
DATA_DIR = REPO_ROOT / "data"

YOI_PATH = DATA_DIR / "processed" / "yoi" / "yoi_components.csv"
META_PATH = DATA_DIR / "processed" / "yoi" / "yoi_indicator_meta.csv"
GEO_PATH = DATA_DIR / "processed" / "boundaries" / "sd_tracts.geojson"

ROUTES_SHP = DATA_DIR / "rawdomains" / "mobility" / "transit_routes_datasd" / "transit_routes_datasd.shp"
STOPS_SHP  = DATA_DIR / "rawdomains" / "mobility" / "transit_stops_datasd" / "transit_stops_datasd.shp"

INV_PATH_CANDS = [
    REPO_ROOT / "rawdomains_file_inventory.csv",
    DATA_DIR / "rawdomains_file_inventory.csv",
]
INV_PATH = next((p for p in INV_PATH_CANDS if p.exists()), None)

DOMAINS = [
    "economic",
    "education",
    "health",
    "housing",
    "safety_env",
    "mobility_connectivity",
    "youth_supports",
]

# -----------------------------
# Helpers
# -----------------------------
def normalize_geoid11(x) -> str:
    d = re.sub(r"\D", "", str(x))
    return d.zfill(11)[-11:] if d else ""

def is_nan(x) -> bool:
    try:
        return bool(pd.isna(x))
    except Exception:
        return False

def ramp_color(v, bins, colors):
    if v < bins[0]: return colors[0]
    if v < bins[1]: return colors[1]
    if v < bins[2]: return colors[2]
    if v < bins[3]: return colors[3]
    return colors[4]

def add_legend_html(map_layer: str, legend_name: str, show_routes: bool, show_stops: bool):
    # bins and labels
    if map_layer == "YOI (0–100)":
        labels = ["<20", "20–40", "40–60", "60–80", "80+"]
    else:
        labels = ["<0.2", "0.2–0.4", "0.4–0.6", "0.6–0.8", "0.8+"]

    colors = ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#1a9850"]

    items = ""
    for c, lab in zip(colors, labels):
        items += f"""
        <div style="display:flex;align-items:center;margin-bottom:4px;">
          <div style="width:14px;height:14px;background:{c};margin-right:8px;border:1px solid #333;"></div>
          <div style="font-size:12px;">{lab}</div>
        </div>
        """

    overlays = []
    if show_routes: overlays.append("Transit routes (blue)")
    if show_stops: overlays.append("Transit stops (cyan dots)")
    overlays_txt = ", ".join(overlays) if overlays else "None"

    html = f"""
    <div style="
      position: fixed;
      bottom: 24px;
      left: 24px;
      z-index: 9999;
      background: rgba(255,255,255,0.92);
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid rgba(0,0,0,0.2);
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      ">
      <div style="font-weight:600;font-size:13px;margin-bottom:6px;">{legend_name}</div>
      {items}
      <div style="font-size:11px;color:#444;margin-top:6px;">
        <div><b>Overlays:</b> {overlays_txt}</div>
        <div><b>Selected tract:</b> thick black outline</div>
      </div>
    </div>
    """
    return html

def feature_bounds(feat) -> tuple[float, float, float, float] | None:
    """Return (min_lat, min_lon, max_lat, max_lon) for a GeoJSON feature."""
    geom = feat.get("geometry", {})
    coords = geom.get("coordinates", None)
    if coords is None:
        return None

    min_lat, min_lon =  90.0,  180.0
    max_lat, max_lon = -90.0, -180.0

    def walk(c):
        nonlocal min_lat, min_lon, max_lat, max_lon
        if isinstance(c, (list, tuple)) and len(c) == 2 and all(isinstance(v, (int, float)) for v in c):
            lon, lat = c[0], c[1]
            min_lat = min(min_lat, lat)
            min_lon = min(min_lon, lon)
            max_lat = max(max_lat, lat)
            max_lon = max(max_lon, lon)
        elif isinstance(c, (list, tuple)):
            for cc in c:
                walk(cc)

    walk(coords)
    return (min_lat, min_lon, max_lat, max_lon)

# -----------------------------
# Load (cached)
# -----------------------------
@st.cache_data
def load_yoi(path_str: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path_str, dtype={"tract_geoid": str})

@st.cache_data
def load_meta(path_str: str, mtime: float) -> pd.DataFrame:
    p = Path(path_str)
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_geojson(path_str: str, mtime: float) -> dict:
    return json.loads(Path(path_str).read_text())

@st.cache_data(show_spinner=False)
def load_routes_geojson(path_str: str, mtime: float) -> dict | None:
    if not _HAS_GPD:
        return None
    p = Path(path_str)
    if not p.exists():
        return None
    gdf = gpd.read_file(p)
    if gdf.crs is not None:
        gdf = gdf.to_crs(4326)
    # keep it visible: simplify only a little
    try:
        gdf["geometry"] = gdf["geometry"].simplify(0.00005, preserve_topology=True)
    except Exception:
        pass
    return json.loads(gdf.to_json())

@st.cache_data(show_spinner=False)
def load_stops_points(path_str: str, mtime: float) -> pd.DataFrame | None:
    if not _HAS_GPD:
        return None
    p = Path(path_str)
    if not p.exists():
        return None
    gdf = gpd.read_file(p)
    if gdf.crs is not None:
        gdf = gdf.to_crs(4326)
    gdf = gdf[gdf.geometry.notna()].copy()

    # point-like only
    gdf = gdf[gdf.geometry.geom_type.isin(["Point", "MultiPoint"])].copy()
    gdf["geom"] = gdf.geometry
    gdf.loc[gdf.geom_type == "MultiPoint", "geom"] = gdf.loc[gdf.geom_type == "MultiPoint"].geometry.centroid
    gdf["lon"] = gdf["geom"].x
    gdf["lat"] = gdf["geom"].y

    keep = ["lat", "lon"]
    for c in ["stop_id", "stop_name", "name"]:
        if c in gdf.columns:
            keep.append(c)
    return pd.DataFrame(gdf[keep])

# -----------------------------
# Sanity
# -----------------------------
if not YOI_PATH.exists():
    st.error(f"Missing: {YOI_PATH}. Run: python scripts/build_yoi_components.py")
    st.stop()
if not GEO_PATH.exists():
    st.error(f"Missing: {GEO_PATH}. Rebuild boundaries then rerun the app.")
    st.stop()

yoi = load_yoi(str(YOI_PATH), YOI_PATH.stat().st_mtime)
meta = load_meta(str(META_PATH), META_PATH.stat().st_mtime) if META_PATH.exists() else pd.DataFrame()

boundary_raw = load_geojson(str(GEO_PATH), GEO_PATH.stat().st_mtime)
if not boundary_raw.get("features"):
    st.error("Boundary GeoJSON has 0 features. Rebuild data/processed/boundaries/sd_tracts.geojson")
    st.stop()

# normalize tract ids in geojson once (don’t mutate cache)
geo = {"type": boundary_raw.get("type", "FeatureCollection"), "features": []}
for feat in boundary_raw.get("features", []):
    props = dict(feat.get("properties", {}))
    props["tract_geoid"] = normalize_geoid11(props.get("tract_geoid", props.get("Tract", props.get("TRACT", ""))))
    geo["features"].append({"type": "Feature", "properties": props, "geometry": feat.get("geometry", None)})

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.title("Controls")

st.sidebar.markdown("### Map overlays (sidebar)")
show_choropleth = st.sidebar.checkbox("YOI choropleth", value=True)
show_boundaries = st.sidebar.checkbox("Tract boundaries", value=True)
show_routes = st.sidebar.checkbox("Transit routes", value=False)
show_stops = st.sidebar.checkbox("Transit stops", value=False)

map_layer = st.sidebar.selectbox(
    "Map layer",
    ["YOI (0–100)"] + [f"{d} score" for d in DOMAINS],
)

st.sidebar.markdown("### Domain weights (sliders)")
raw_w = {d: st.sidebar.slider(d, 0.0, 1.0, 1.0, 0.05) for d in DOMAINS}
s = sum(raw_w.values())
weights = {d: (1 / len(DOMAINS) if s == 0 else raw_w[d] / s) for d in DOMAINS}
st.sidebar.caption("Weights auto-normalize to sum to 1.")

# persistent selection
if "selected_geoid" not in st.session_state:
    st.session_state["selected_geoid"] = None

tract_pick = st.sidebar.selectbox(
    "Select a tract (optional)",
    ["(none)"] + sorted(yoi["tract_geoid"].dropna().unique().tolist()),
)
if tract_pick != "(none)":
    st.session_state["selected_geoid"] = tract_pick

selected_geoid = st.session_state["selected_geoid"]

# -----------------------------
# Recompute YOI under weights
# -----------------------------
df = yoi.copy()
df["yoi_custom_0_1"] = 0.0
for d in DOMAINS:
    df["yoi_custom_0_1"] += df[f"{d}_score"] * weights[d]
df["yoi_custom_0_100"] = df["yoi_custom_0_1"] * 100.0

if map_layer == "YOI (0–100)":
    value_col = "yoi_custom_0_100"
    legend_name = "YOI (custom weights)"
else:
    dd = map_layer.replace(" score", "")
    value_col = f"{dd}_score"
    legend_name = f"{dd} domain score (0–1)"

val_map = dict(zip(df["tract_geoid"].astype(str), df[value_col].astype(float)))

# attach current "value" onto geojson props
for feat in geo.get("features", []):
    tg = feat["properties"].get("tract_geoid", "")
    feat["properties"]["value"] = float(val_map.get(tg, np.nan)) if tg else np.nan

# -----------------------------
# Layout
# -----------------------------
st.title("Youth Opportunity Index (San Diego County)")
tab_map, tab_data = st.tabs(["Map", "Data / Sources"])

# -----------------------------
# MAP TAB
# -----------------------------
with tab_map:
    left, right = st.columns([2.2, 1], gap="large")

    # decide map viewport: zoom to selected tract if we have it
    center = [32.8, -117.1]
    zoom = 10
    if selected_geoid:
        sel_feat = next((f for f in geo["features"] if f["properties"].get("tract_geoid") == str(selected_geoid)), None)
        if sel_feat:
            b = feature_bounds(sel_feat)
            if b:
                min_lat, min_lon, max_lat, max_lon = b
                center = [(min_lat + max_lat) / 2.0, (min_lon + max_lon) / 2.0]
                zoom = 12  # fit_bounds also below; zoom is just a fallback

    with left:
        m = folium.Map(location=center, zoom_start=zoom, tiles="cartodbpositron")

        # always keep a clickable tract layer (even if choropleth is off)
        # so clicking still works + we can highlight selection.
        def style_clickable(feature):
            tg = feature.get("properties", {}).get("tract_geoid", "")
            base = {"fillOpacity": 0.0, "weight": 0.0, "color": "#00000000"}  # invisible
            if show_boundaries:
                base = {"fillOpacity": 0.0, "weight": 0.9, "color": "#666"}
            # selected outline is handled by separate layer below
            return base

        clickable = folium.GeoJson(
            geo,
            name="tracts_clickable",
            style_function=style_clickable,
            tooltip=folium.GeoJsonTooltip(
                fields=["tract_geoid"],
                aliases=["Tract GEOID"],
                sticky=False,
            ),
            # popup ONLY tract_geoid so st_folium parsing is easy
            popup=folium.GeoJsonPopup(fields=["tract_geoid"], aliases=["tract_geoid"]),
        )
        clickable.add_to(m)

        # choropleth layer (optional)
        if show_choropleth:
            def style_choro(feature):
                v = feature.get("properties", {}).get("value", np.nan)
                if v is None or is_nan(v):
                    return {"fillOpacity": 0.05, "weight": 0.0, "color": "#00000000", "fillColor": "#ffffff"}

                if map_layer == "YOI (0–100)":
                    bins = [20, 40, 60, 80]
                else:
                    bins = [0.2, 0.4, 0.6, 0.8]
                colors = ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#1a9850"]
                fill = ramp_color(float(v), bins, colors)
                return {"fillColor": fill, "fillOpacity": 0.70, "weight": 0.0, "color": "#00000000"}

            folium.GeoJson(
                geo,
                name="choropleth",
                style_function=style_choro,
                tooltip=folium.GeoJsonTooltip(
                    fields=["tract_geoid", "value"],
                    aliases=["Tract GEOID", legend_name],
                    localize=True,
                    sticky=False,
                ),
            ).add_to(m)

        # selected tract overlay (always on top)
        if selected_geoid:
            sel_feat = next((f for f in geo["features"] if f["properties"].get("tract_geoid") == str(selected_geoid)), None)
            if sel_feat:
                folium.GeoJson(
                    sel_feat,
                    name="selected_tract",
                    style_function=lambda f: {
                        "fillOpacity": 0.0,
                        "weight": 3.5,
                        "color": "#000000",
                    },
                ).add_to(m)

                # tighten view to selected tract
                b = feature_bounds(sel_feat)
                if b:
                    min_lat, min_lon, max_lat, max_lon = b
                    m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

        # transit routes (optional)
        if show_routes:
            if ROUTES_SHP.exists() and _HAS_GPD:
                routes_geo = load_routes_geojson(str(ROUTES_SHP), ROUTES_SHP.stat().st_mtime)
                if routes_geo and routes_geo.get("features"):
                    folium.GeoJson(
                        routes_geo,
                        name="Transit routes",
                        style_function=lambda f: {"color": "#0047FF", "weight": 5, "opacity": 1.0},
                    ).add_to(m)
            else:
                st.warning("Transit routes require geopandas + the routes shapefile.")

        # transit stops (optional)
        if show_stops:
            if STOPS_SHP.exists() and _HAS_GPD and MarkerCluster is not None:
                stops_df = load_stops_points(str(STOPS_SHP), STOPS_SHP.stat().st_mtime)
                if stops_df is not None and len(stops_df) > 0:
                    cluster = MarkerCluster(name="Transit stops")
                    for _, r in stops_df.iterrows():
                        lat, lon = float(r["lat"]), float(r["lon"])
                        label = None
                        for c in ["stop_name", "name", "stop_id"]:
                            if c in stops_df.columns and pd.notna(r.get(c)):
                                label = str(r.get(c))
                                break
                        folium.CircleMarker(
                            location=(lat, lon),
                            radius=3,
                            weight=1,
                            color="#0b0f19",
                            fill=True,
                            fill_color="#00E5FF",
                            fill_opacity=0.9,
                            tooltip=label if label else None,
                        ).add_to(cluster)
                    cluster.add_to(m)
            else:
                st.warning("Transit stops require geopandas + the stops shapefile.")

        # legend
        m.get_root().html.add_child(
            folium.Element(add_legend_html(map_layer, legend_name, show_routes, show_stops))
        )

        # IMPORTANT:
        # Only return popup to avoid reruns on pan/zoom. :contentReference[oaicite:1]{index=1}
        out = st_folium(
            m,
            height=650,
            width=1100,
            returned_objects=["last_object_clicked_popup"],
            key="sd_map",
        )

        clicked = None
        if out:
            raw = out.get("last_object_clicked_popup") or ""
            clicked = normalize_geoid11(raw)

        if clicked and clicked != st.session_state["selected_geoid"]:
            st.session_state["selected_geoid"] = clicked
            st.rerun()

    with right:
        st.subheader("Selected tract")
        selected_geoid = st.session_state["selected_geoid"]

        if not selected_geoid or selected_geoid not in set(df["tract_geoid"].astype(str)):
            st.caption("Click a tract on the map or choose one from the sidebar.")
        else:
            row = df[df["tract_geoid"].astype(str) == str(selected_geoid)].iloc[0]
            st.write(f"**Tract:** {selected_geoid}")
            st.metric("YOI (custom, 0–100)", f"{row['yoi_custom_0_100']:.1f}")

            st.markdown("### Domain breakdown (0–1)")
            dom_table = pd.DataFrame({
                "domain": DOMAINS,
                "score": [row[f"{d}_score"] for d in DOMAINS],
                "weight": [weights[d] for d in DOMAINS],
                "weighted": [row[f"{d}_score"] * weights[d] for d in DOMAINS],
            })
            st.dataframe(dom_table, width="stretch")

            st.markdown("### Notes")
            st.caption("Scores are percentile-normalized indicators aggregated within domains, then weighted across domains.")

# -----------------------------
# DATA / SOURCES TAB
# -----------------------------
with tab_data:
    st.subheader("Indicator metadata (what your index is using)")
    if meta is None or meta.empty:
        st.info("No indicator metadata found yet. Run scripts/build_yoi_components.py first.")
    else:
        st.dataframe(meta, width="stretch")

    st.subheader("Raw data inventory")
    if INV_PATH is None:
        st.info("Could not find rawdomains_file_inventory.csv in repo root or /data.")
    else:
        inv = pd.read_csv(INV_PATH)
        st.caption(str(INV_PATH))
        if "domain_folder" in inv.columns:
            domain = st.selectbox("Filter domain", ["(all)"] + sorted(inv["domain_folder"].unique().tolist()))
            if domain != "(all)":
                inv = inv[inv["domain_folder"] == domain].copy()
        st.dataframe(inv, width="stretch")