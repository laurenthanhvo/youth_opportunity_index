# Youth Opportunity Desert Dashboard 🗺️

An interactive, data-driven web application for identifying and visualizing gaps in access to youth-supporting resources across San Diego County.

The dashboard combines youth service locations with demographic, socioeconomic, transportation, and environmental context to surface places where young people may face lower access to opportunity. It is designed to support exploration, interpretation, and discussion for community organizations, researchers, and policymakers.

Developed through the **Halıcıoğlu Data Science Institute (HDSI) Undergraduate Scholarship** at **UC San Diego**, in partnership with the **Data Science Alliance (DSA)**.

---

## What the dashboard does

The dashboard centers on a **Youth Opportunity Index (YOI)** built for San Diego County. Users can:

- view the overall index or individual domain scores
- compare places across **census tracts, ZIP codes, and supervisor districts**
- adjust **custom domain weights** and see the overall map update
- inspect **location details** and domain-level diagnostics for selected areas
- search the currently selected geography level using **search suggestions** and keyboard-friendly search behavior
- turn on contextual overlays such as **transit routes, transit stops, service locations, tract boundaries, and the Child Opportunity Index (COI)**
- use an **AI assistant** to explain the dashboard and answer dataset-backed questions
- share the current dashboard state by copying the active view link or the selected geography identifier
- navigate supporting pages for **YOI Methodology**, **About Us**, and **Contact Us**

---

## Current interface highlights

### Main dashboard panels

The left rail opens six main panels:

- **Data Controls**
  - switch between overall YOI and single-domain views
  - switch the level of comparison between census tracts, ZIP codes, and supervisor districts
  - toggle hover behavior
  - adjust custom domain weights and reset them to equal weighting

- **Overlays**
  - toggle the YOI choropleth
  - switch to the **Child Opportunity Index (COI)** overlay
  - show supervisor districts
  - show tract boundaries
  - show transit routes and stops
  - show service locations

- **Location Details**
  - updates when a user clicks a map feature
  - summarizes the selected area and supports domain-level interpretation

- **Assistant**
  - accepts free-text questions such as explanations, navigation requests, and simple analytical prompts
  - includes starter chips like showing supervisor districts, comparing with COI, or turning on service locations

- **FAQs**
  - explains how to interpret colors, overlays, geographic levels, COI vs YOI, custom weights, and likely opportunity-desert patterns

- **Share**
  - copy a link to the current dashboard state, including active layer context
  - copy the currently selected geography identifier for quick reuse in notes or outreach

### Utility controls

The dashboard also includes:

- a **top navigation header** for moving between the dashboard, methodology, about, and contact pages
- a **search** control that adapts to the selected geography level and supports suggestions
- a **home / reset view** button for returning to the default county map view
- **zoom in / zoom out** controls for map navigation

---

## Key features

- **Interactive choropleth mapping** with Leaflet
- **Warm-to-cool score palette** for easier visual interpretation of lower- to higher-opportunity places
- **Three geography levels**: census tracts, ZIP codes, and supervisor districts
- **Custom domain weighting** for recomputing overall YOI in the browser
- **Geography-aware search** with suggestions and keyboard support
- **Domain diagnostics** for selected places
- **Contextual overlays** for youth services, transit, boundaries, and COI benchmarking
- **Share utilities** for copying the current view or selected geography
- **Custom home / zoom controls** for map navigation
- **AI assistant** powered by Gemini through a FastAPI backend
- **Static information pages** for methodology, project context, and contact information

---

## Methodology summary

The Youth Opportunity Index is built at the **census tract** level and then aggregated into broader geographies for alternative views.

### Base geography

- Primary analysis unit: **San Diego County census tract**
- Core outputs:
  - `data/processed/yoi/yoi_components.csv`
  - `data/processed/yoi/yoi_indicator_meta.csv`
  - `data/processed/boundaries/sd_tracts.geojson`

### Scoring approach

1. Raw indicators are cleaned and aligned to tract GEOIDs.
2. Indicators are converted into **county-relative percentile scores**.
3. Indicators are reverse-coded when lower raw values indicate worse conditions.
4. Indicators are averaged into domain scores.
5. Domain scores are equally weighted by default to form the overall YOI.
6. The dashboard also supports **custom user-defined weights** for recomputing the overall YOI view interactively.

### Domains

The current build uses seven domains:

1. **Economic**
2. **Education**
3. **Health**
4. **Housing**
5. **Safety / Environment**
6. **Mobility / Connectivity**
7. **Youth Supports**

### Geographic views

In addition to tracts, the dashboard provides:

- **ZIP code view** built from tract outputs
- **Supervisor district view** built from tract outputs

These are generated from processed tract scores and matched to their corresponding GeoJSON layers.

### External reference layer

The **Child Opportunity Index (COI)** is included as a comparison overlay. It is not part of the YOI computation. In the current build:

- YOI is county-normalized for **2024**
- COI overlay is filtered to **San Diego County** and **2023**

Because they use different sources, frames, and normalization logic, YOI and COI are expected to differ.

---

## Data sources used in the current build

The README draft and methodology materials indicate the following high-level sources in the pipeline:

- **ACS**
- **CDC PLACES**
- **CalEnviroScreen 4.0**
- **SANDAG / ARJIS crime data**
- **Local youth service inventory**
- transit route / stop geospatial data used for overlays

For the detailed source-by-source description, see the in-app **YOI Methodology** page (`datasets.html`).

---

## Tech stack

### Frontend

- HTML5
- CSS3
- Vanilla JavaScript
- **Leaflet.js** for map rendering and GeoJSON layer management
- **D3.js** for domain profile / diagnostic visuals
- Bootstrap / Bootstrap Icons for UI support

### Backend

- Python 3
- **FastAPI**
- **Pandas**
- **Google GenAI SDK**
- `python-dotenv`

### Data processing

- **Pandas**
- **GeoPandas**
- NumPy

---

## Repository / file guide

### Frontend

- `index.html` — main dashboard UI
- `app.js` — map logic, panel logic, overlays, custom weights, assistant frontend integration
- `styles.css` — visual styling for the dashboard
- `datasets.html` — methodology page
- `about.html` — project description page
- `contact.html` — contact and feedback page

### Backend

- `server.py` — FastAPI backend for the assistant, including Gemini integration and dataset-backed tool calls

### Data pipeline scripts

- `build_yoi_components.py` — builds tract-level YOI outputs and indicator metadata
- `build_yoi_zip_components.py` — builds ZIP-level YOI aggregates
- `build_yoi_supervisor_district_components.py` — builds supervisor-district YOI aggregates
- `build_sd_tracts_geojson.py` — builds tract boundaries from the baseline source
- `build_sd_tracts_geojson_2025.py` — alternate tract boundary build using the 2025 boundary source
- `build_sd_coi_overlay.py` — prepares the San Diego COI overlay file
- `filter_coi_sd_only.py` — filters COI source data to San Diego County
- `build_transit_geojson.py` — exports transit route and stop GeoJSON layers
- `build_service_locations_geojson.py` — exports the service location overlay GeoJSON

### Key processed outputs expected by the frontend

- `data/processed/yoi/yoi_components.csv`
- `data/processed/yoi/yoi_zip_components.csv`
- `data/processed/yoi/yoi_supervisor_district_components.csv`
- `data/processed/yoi/yoi_indicator_meta.csv`
- `data/processed/boundaries/sd_tracts.geojson`
- `data/processed/boundaries/sd_zip_codes.geojson`
- `data/processed/boundaries/transit_routes.geojson`
- `data/processed/boundaries/transit_stops.geojson`
- `data/processed/overlays/sd_coi_2023.csv`
- `data/processed/overlays/service_locations.geojson`
- `data/processed/overlays/supervisor_districts.geojson`

---

## Local development

This project has a static frontend and a Python backend for the AI assistant.

### 1. Clone the repository

```bash
git clone https://github.com/laurenthanhvo/youth_opportunity_index.git
cd youth_opportunity_index
````

### 2. Set up the Python environment

```bash
python -m venv .venv
source .venv/bin/activate
# On Windows: .venv\Scripts\activate
```

Install the required packages. If your repository includes a `requirements.txt`, use:

```bash
pip install -r requirements.txt
```

If not, install the packages used by the uploaded code directly:

```bash
pip install fastapi uvicorn pandas geopandas numpy python-dotenv google-genai
```

### 3. Configure environment variables

Create a `.env` file in the backend environment and add:

```env
GEMINI_API_KEY=your_actual_api_key_here
```

### 4. Start the assistant backend

```bash
uvicorn server:app --host 0.0.0.0 --port 8001
```

### 5. Serve the frontend

From the project root, serve the static files:

```bash
python -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

### 6. Important note about the assistant endpoint

The current frontend code points the assistant to a deployed Render endpoint. If you want the dashboard to use your local FastAPI server during development, update the assistant API URL in `app.js` to your local backend route.

Example local value:

```js
const ASSISTANT_API_URL = 'http://localhost:8001/api/chat';
```

---

## Backend assistant behavior

The assistant backend:

* loads the processed tract-level YOI CSV into memory
* accepts dashboard context from the frontend
* uses Gemini with a structured system prompt tailored to the dashboard
* supports both explanatory responses and simple UI actions
* can answer dataset-backed questions using Python tool calls

The current tool functions in `server.py` include:

* `get_highest_lowest_tract(metric)`
* `count_tracts_by_condition(metric, operator_str, value)`

The backend also exposes:

* `GET /api/health`
* `POST /api/chat`

---

## Deployment

Current deployment assumptions from the existing project materials:

* **Frontend:** static hosting such as GitHub Pages
* **Backend:** Render-hosted FastAPI service

If using a free Render tier, the assistant may have a cold-start delay after inactivity.

---

## Interpreting the dashboard

A few important interpretation notes built into the current dashboard:

* **YOI and COI are not the same measure** and should not be treated as directly interchangeable.
* **Census tracts** are the most detailed view.
* **ZIP codes** are broader and often easier for general audiences to recognize.
* **Supervisor districts** are larger policy-oriented geographies useful for stakeholder and planning conversations.
* **Custom weights** change the overall YOI and related diagnostics, but they do not rewrite the raw score of an individual domain layer.

---

## Project status and next steps

A large share of the originally planned functionality is already implemented in the current build:

* multiple geography levels
* custom-weighted overall YOI
* contextual overlays
* location-level interpretation panels
* an assistant workflow
* supporting methodology / about / contact pages

Because of that, the most important next phase is **refinement through stakeholder feedback**, not just adding more interface features.

Likely next steps include:

* validating whether current indicators and weights reflect on-the-ground experience
* improving clarity for non-technical audiences
* expanding or refreshing supporting data layers as new data becomes available
* refining interpretation guidance for community and policy users
* incorporating feedback from organizations, researchers, and youth-serving partners about usability and practical relevance

The longer-term goal is for the dashboard to continue evolving into a stronger planning, communication, and decision-support tool for youth opportunity across San Diego County.

---

## Team and contact

* **Project lead / developer:** Lauren Vo
* **Research guidance:** Shay Samat / Data Science Alliance

For project questions, feedback, collaboration, or suggested indicators / data layers, see the contact information in `contact.html`.
