# app/app.py
import json
import re
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px

# Optional overlays (transit) use geopandas if available
try:
    import geopandas as gpd
    _HAS_GPD = True
except Exception:
    gpd = None
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

YOI_PATH  = DATA_DIR / "processed" / "yoi" / "yoi_components.csv"
META_PATH = DATA_DIR / "processed" / "yoi" / "yoi_indicator_meta.csv"
GEO_PATH  = DATA_DIR / "processed" / "boundaries" / "sd_tracts.geojson"

# Transit shapefiles you already have
ROUTES_SHP = DATA_DIR / "rawdomains" / "mobility" / "transit_routes_datasd" / "transit_routes_datasd.shp"
STOPS_SHP  = DATA_DIR / "rawdomains" / "mobility" / "transit_stops_datasd" / "transit_stops_datasd.shp"

INV_PATH_CANDS = [
    REPO_ROOT / "rawdomains_file_inventory.csv",
    DATA_DIR / "rawdomains_file_inventory.csv",
]
INV_PATH = next((p for p in INV_PATH_CANDS if p.exists()), None)

# -----------------------------
# Helpers
# -----------------------------
def geoid11(x) -> str:
    d = re.sub(r"\D", "", str(x))
    return d.zfill(11)[-11:] if d else ""

def is_nan(x) -> bool:
    try:
        return bool(pd.isna(x))
    except Exception:
        return False

def ramp_color(v, bins, colors):
    if v < bins[0]:
        return colors[0]
    if v < bins[1]:
        return colors[1]
    if v < bins[2]:
        return colors[2]
    if v < bins[3]:
        return colors[3]
    return colors[4]

def legend_html(map_layer: str, legend_name: str):
    if map_layer == "YOI (0–100)":
        labels = ["<20", "20–40", "40–60", "60–80", "80+"]
        colors = ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#1a9850"]
    else:
        labels = ["<0.2", "0.2–0.4", "0.4–0.6", "0.6–0.8", "0.8+"]
        colors = ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#1a9850"]

    items = "\n".join(
        f"""
        <div style="display:flex;align-items:center;margin-bottom:4px;">
          <div style="width:14px;height:14px;background:{c};margin-right:8px;border:1px solid #333;"></div>
          <div style="font-size:12px;">{lab}</div>
        </div>
        """ for c, lab in zip(colors, labels)
    )

    return f"""
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
        Click a tract to select it. Hover to see tract + population.
      </div>
    </div>
    """

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
    try:
        if gdf.crs is not None:
            gdf = gdf.to_crs(4326)
    except Exception:
        pass
    # light simplify for web
    try:
        gdf["geometry"] = gdf["geometry"].simplify(0.0002, preserve_topology=True)
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
    try:
        if gdf.crs is not None:
            gdf = gdf.to_crs(4326)
    except Exception:
        pass
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["Point", "MultiPoint"])].copy()

    # MultiPoint -> centroid
    geom = gdf.geometry
    mp = gdf.geometry.geom_type == "MultiPoint"
    geom.loc[mp] = gdf.loc[mp].geometry.centroid
    gdf["lon"] = geom.x
    gdf["lat"] = geom.y

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

geo = copy.deepcopy(boundary_raw)
for feat in geo.get("features", []):
    props = feat.setdefault("properties", {})
    props["tract_geoid"] = geoid11(props.get("tract_geoid", props.get("Tract", props.get("TRACT", ""))))

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

if "selected_geoid" not in st.session_state:
    st.session_state["selected_geoid"] = None

tract_pick = st.sidebar.selectbox(
    "Select a tract (optional)",
    ["(none)"] + sorted(yoi["tract_geoid"].dropna().unique().tolist()),
)
if tract_pick != "(none)":
    st.session_state["selected_geoid"] = tract_pick

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
    d = map_layer.replace(" score", "")
    value_col = f"{d}_score"
    legend_name = f"{d} domain score (0–1)"

val_map = dict(zip(df["tract_geoid"].astype(str), df[value_col].astype(float)))

# Population: pick best available column (don’t assume total_population exists)
POP_CANDS = ["total_population", "population", "pop_total", "B01003_001E"]
pop_col = next((c for c in POP_CANDS if c in df.columns), None)
pop_map = dict(zip(df["tract_geoid"].astype(str), df[pop_col].astype(float))) if pop_col else {}

# attach props used by tooltip/popup/styling
for feat in geo.get("features", []):
    props = feat.setdefault("properties", {})
    tg = props.get("tract_geoid", "")
    props["value"] = float(val_map.get(tg, np.nan)) if tg else np.nan
    props["population"] = float(pop_map.get(tg, np.nan)) if pop_col and tg in pop_map else np.nan

# -----------------------------
# Layout
# -----------------------------
st.title("Youth Opportunity Index (San Diego County)")
tab_map, tab_data = st.tabs(["Map", "Data / Sources"])

# -----------------------------
# MAP
# -----------------------------
with tab_map:
    left, right = st.columns([2.2, 1], gap="large")

    with left:
        m = folium.Map(location=[32.8, -116.9], zoom_start=10, tiles="cartodbpositron")

        selected_geoid = st.session_state["selected_geoid"]

        # Single polygon layer controls BOTH fill + outlines
        def style_fn(feature):
            props = feature.get("properties", {})
            tg = props.get("tract_geoid", "")
            v = props.get("value", np.nan)

            # boundaries
            weight = 0.9 if show_boundaries else 0.0
            color = "#666" if show_boundaries else "#00000000"

            # fill
            if not show_choropleth:
                fill_opacity = 0.0
                fill_color = "#ffffff"
            else:
                if v is None or is_nan(v):
                    fill_opacity = 0.05
                    fill_color = "#ffffff"
                else:
                    if map_layer == "YOI (0–100)":
                        bins = [20, 40, 60, 80]
                    else:
                        bins = [0.2, 0.4, 0.6, 0.8]
                    colors = ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#1a9850"]
                    fill_color = ramp_color(float(v), bins, colors)
                    fill_opacity = 0.70

            # base style
            style = {
                "fillColor": fill_color,
                "fillOpacity": fill_opacity,
                "weight": weight,
                "color": color,
            }

            # selection outline
            if selected_geoid and tg == str(selected_geoid):
                style.update({"color": "#000000", "weight": 4.0, "fillOpacity": max(fill_opacity, 0.85)})

            return style

        # Tooltip fields must exist in properties; we always set population (NaN ok)
        tooltip = folium.GeoJsonTooltip(
            fields=["tract_geoid", "population", "value"],
            aliases=["Tract GEOID", "Population", legend_name],
            localize=True,
            sticky=False,
        )

        popup = folium.GeoJsonPopup(
            fields=["tract_geoid"],
            aliases=["Tract GEOID"],
            localize=False,
        )

        tracts_layer = folium.GeoJson(
            geo,
            name="tracts",
            style_function=style_fn,
            highlight_function=lambda f: {"weight": 2.0, "color": "#111"},
            tooltip=tooltip,
            popup=popup,
        )
        tracts_layer.add_to(m)
        # Zoom behavior:
        # - if a tract is selected, zoom to that tract
        # - otherwise just keep the default initial map view
        if selected_geoid:
            selected_feature = next(
                (
                    f for f in geo.get("features", [])
                    if str(f.get("properties", {}).get("tract_geoid", "")) == str(selected_geoid)
                ),
                None,
            )
            if selected_feature is not None:
                selected_layer = folium.GeoJson(selected_feature)
                m.fit_bounds(selected_layer.get_bounds())

        # Transit overlays (bold + visible)
        if show_routes:
            if _HAS_GPD and ROUTES_SHP.exists():
                routes_geo = load_routes_geojson(str(ROUTES_SHP), ROUTES_SHP.stat().st_mtime)
                if routes_geo and routes_geo.get("features"):
                    folium.GeoJson(
                        routes_geo,
                        name="routes",
                        style_function=lambda f: {"color": "#7592d1", "weight": 3, "opacity": 1.0},
                    ).add_to(m)
            else:
                st.warning("Transit routes overlay requires geopandas and the routes shapefile.")

        if show_stops:
            if _HAS_GPD and STOPS_SHP.exists():
                from folium.plugins import MarkerCluster
                stops_df = load_stops_points(str(STOPS_SHP), STOPS_SHP.stat().st_mtime)
                if stops_df is not None and len(stops_df) > 0:
                    cluster = MarkerCluster(name="stops")
                    for _, r in stops_df.iterrows():
                        lat, lon = float(r["lat"]), float(r["lon"])
                        label = None
                        for c in ["stop_name", "name", "stop_id"]:
                            if c in stops_df.columns and pd.notna(r.get(c)):
                                label = str(r.get(c))
                                break
                        folium.CircleMarker(
                            location=(lat, lon),
                            radius=5,
                            weight=2,
                            color="#000000",
                            fill=True,
                            fill_color="#00c2ff",
                            fill_opacity=0.9,
                            tooltip=label if label else None,
                        ).add_to(cluster)
                    cluster.add_to(m)
            else:
                st.warning("Transit stops overlay requires geopandas and the stops shapefile.")

        # Legend
        m.get_root().html.add_child(folium.Element(legend_html(map_layer, legend_name)))

        # IMPORTANT: prevent rerun on pan/zoom by only returning click-related objects
        out = st_folium(
            m,
            height=650,
            width=1100,
            key="map",
            returned_objects=["last_object_clicked_popup"],
        )

        # Click-to-select (extract 11-digit GEOID from popup)
        clicked_geoid = None
        if out:
            raw = str(out.get("last_object_clicked_popup") or "")
            m_geoid = re.search(r"\b06073\d{6}\b", raw)
            if m_geoid:
                clicked_geoid = m_geoid.group(0)

        if clicked_geoid and clicked_geoid != st.session_state["selected_geoid"]:
            st.session_state["selected_geoid"] = clicked_geoid
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
                "score": [float(row[f"{d}_score"]) for d in DOMAINS],
                "weight": [float(weights[d]) for d in DOMAINS],
                "weighted": [float(row[f"{d}_score"] * weights[d]) for d in DOMAINS],
            })

            # nicer labels
            label_map = {
                "economic": "Economic",
                "education": "Education",
                "health": "Health",
                "housing": "Housing",
                "safety_env": "Safety / Env",
                "mobility_connectivity": "Mobility / Conn",
                "youth_supports": "Youth Supports",
            }
            dom_table["label"] = dom_table["domain"].map(label_map)

            # sort so the largest bar is on top
            dom_table = dom_table.sort_values("weighted", ascending=True).reset_index(drop=True)

            fig = px.bar(
                dom_table,
                x="weighted",
                y="label",
                orientation="h",
                custom_data=["domain", "score", "weight", "weighted"],
                text="weighted",
            )

            fig.update_traces(
                texttemplate="%{x:.3f}",
                textposition="outside",
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Raw score: %{customdata[1]:.3f}<br>"
                    "Weight: %{customdata[2]:.3f}<br>"
                    "Weighted contribution: %{customdata[3]:.3f}"
                    "<extra></extra>"
                ),
            )

            fig.update_layout(
                height=320,
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title="Weighted contribution",
                yaxis_title="",
                showlegend=False,
            )

            chart_event = st.plotly_chart(
                fig,
                use_container_width=True,
                key=f"domain_chart_{selected_geoid}",
                on_select="rerun",
            )

            # optional: clicking a bar selects a domain and switches the map layer
            if chart_event and chart_event.selection and chart_event.selection.get("points"):
                point = chart_event.selection["points"][0]
                clicked_domain = dom_table.iloc[point["point_index"]]["domain"]
                st.session_state["clicked_domain"] = clicked_domain
                st.caption(f"Selected domain: {label_map.get(clicked_domain, clicked_domain)}")

            # optional: keep the exact table below the chart
            with st.expander("Show exact values"):
                st.dataframe(dom_table[["label", "score", "weight", "weighted"]], width="stretch")

            if pop_col and pop_col in row.index:
                st.caption(f"Population source column in yoi_components.csv: `{pop_col}`")

# -----------------------------
# DATA / SOURCES
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