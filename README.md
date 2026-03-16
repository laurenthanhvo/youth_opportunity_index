# Youth Opportunity Index Explorer

An interactive map-based dashboard for exploring a **Youth Opportunity Index (YOI)** across **San Diego County census tracts**.

The project includes:

- a **static GitHub Pages frontend** built with **HTML, CSS, JavaScript, Leaflet, D3, and Bootstrap**
- a set of **Python build scripts** that preprocess raw data into browser-friendly CSV and GeoJSON files
- a legacy **Streamlit prototype** kept in the repo for reference

## Features

- tract-level choropleth map for overall YOI
- domain-level map layers:
  - Economic
  - Education
  - Health
  - Housing
  - Safety / Environment
  - Mobility / Connectivity
  - Youth Supports
- custom domain-weight sliders that recompute the overall YOI
- search by tract GEOID
- clickable tract popups and location details panel
- optional overlays for:
  - Child Opportunity Index (COI)
  - transit routes
  - transit stops
  - service locations

## Tech Stack

### Frontend
- HTML
- CSS
- JavaScript
- [Leaflet](https://leafletjs.com/) for mapping
- [D3.js](https://d3js.org/) for charts
- [Bootstrap](https://getbootstrap.com/) + Bootstrap Icons

### Data / Build Pipeline
- Python
- pandas
- geopandas

## Repository Structure

```text
.
├── index.html                  # GitHub Pages entry point
├── app.js                      # Main frontend logic
├── styles.css                  # Frontend styling
├── app/
│   └── app.py                  # Legacy Streamlit app
├── data/
│   ├── rawdomains/             # Raw source datasets
│   └── processed/
│       ├── boundaries/         # Built tract / transit GeoJSON outputs
│       ├── overlays/           # Built COI / service overlay outputs
│       └── yoi/                # Built YOI CSV outputs
├── scripts/
│   ├── build_yoi_components.py
│   ├── build_sd_tracts_geojson.py
│   ├── build_sd_tracts_geojson_2025.py
│   ├── build_sd_coi_overlay.py
│   ├── build_transit_geojson.py
│   └── build_service_locations_geojson.py
└── notebooks/
    └── script.ipynb
