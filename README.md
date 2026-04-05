# Youth Opportunity Desert Dashboard 🗺️

An interactive, data-driven web application designed to identify and visualize gaps in access to youth-supporting resources across San Diego County. 

By combining information on youth service locations with demographic, socioeconomic, and transportation data, this dashboard helps reveal where young people may face limited access to opportunities. The goal is to make these disparities visible so communities, organizations, and policymakers can make informed, equitable decisions about future investments.

Developed through the **Halıcıoğlu Data Science Institute (HDSI) Undergraduate Scholarship** at **UC San Diego**, in partnership with the **Data Science Alliance (DSA)**.

## ✨ Key Features
* **Interactive Choropleth Maps:** Visualize the Youth Opportunity Index (YOI) across Census Tracts, ZIP Codes, and Supervisor Districts.
* **Customizable Indexing:** Users can adjust the weight of specific domains (e.g., Education, Health, Housing) and watch the map recalculate opportunity scores in real time.
* **AI Data Assistant:** An integrated chatbot powered by **Gemini 2.5 Flash**. The assistant utilizes Python tool-calling to dynamically query the dataset and answer specific mathematical or geographic questions on the fly (e.g., *"How many tracts have an education score below 40?"*).
* **Domain Diagnostic Profiles:** Detailed, D3.js-powered breakdown charts showing county-relative percentiles, medians, and primary desert-driving factors for selected areas.
* **Contextual Overlays:** Toggleable layers for Transit Routes, Transit Stops, Youth Service Locations, and the national Child Opportunity Index (COI) for benchmarking.

## 🛠️ Tech Stack
**Frontend:**
* HTML5, CSS3, Vanilla JavaScript
* **Leaflet.js:** Map rendering and GeoJSON layer management.
* **D3.js:** Dynamic charting and statistical distributions for domain profiles.
* **Bootstrap Icons / CSS:** UI styling and layout.

**Backend (AI Agent):**
* **Python 3 & FastAPI:** Handles REST API requests from the frontend.
* **Google GenAI SDK:** Powers the AI assistant using the `gemini-2.5-flash` model.
* **Pandas:** Keeps the processed dataset in memory, allowing the AI to execute Python functions (tool-calling) to filter, sort, and count data accurately without hallucinating.

**Data Pipeline:**
* **Pandas & GeoPandas:** Used to clean, normalize, and spatially aggregate raw data from Census tracts into ZIP codes and Supervisor Districts using area/population-weighted intersections.

## 📊 Methodology & Data Sources
The Youth Opportunity Index (YOI) is constructed by converting raw indicators into county-relative percentiles. These indicators are grouped into seven equally weighted domains:
1. **Economic:** Poverty rate, median income, unemployment, SNAP/assistance. *(Source: ACS)*
2. **Education:** High school/BA attainment, school enrollment, youth disconnection. *(Source: ACS)*
3. **Health:** Uninsured rate, disability rate, frequent mental distress. *(Sources: ACS, CDC PLACES)*
4. **Housing:** Rent burden, overcrowding, homeownership. *(Source: ACS)*
5. **Safety / Environment:** Vacancy rates, environmental burden, crime rate. *(Sources: ACS, CalEnviroScreen 4.0, SANDAG ARJIS)*
6. **Mobility / Connectivity:** Zero-vehicle households, commute times, broadband access. *(Sources: ACS, CDC PLACES)*
7. **Youth Supports:** Density of youth and mental health services. *(Source: Local Inventory)*

*(For a full breakdown of the methodology, see the `datasets.html` page in the application).*

---

## 🚀 Local Development Setup

To run this project locally, you will need to run both the frontend and the backend server simultaneously.

### 1. Clone the repository
```bash
git clone https://github.com/laurenthanhvo/youth_opportunity_index.git
cd youth_opportunity_index
```

### 2. Set up the Backend (FastAPI + Gemini)
The backend requires a Google Gemini API key to function.
```bash
# Navigate to the backend directory (if applicable) or stay in root
# Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt

# Create your environment variables file
touch .env
```
Open the `.env` file and add your Gemini API key:
```env
GEMINI_API_KEY=your_actual_api_key_here
```
Start the backend server (ensure it runs on port 8001):
```bash
uvicorn server:app --port 8001
```

### 3. Set up the Frontend
Open a new terminal window. You can serve the static frontend files using Python's built-in HTTP server or a VS Code extension like Live Server.
```bash
# From the root directory of the project:
python -m http.server 8000
```
Navigate to `http://localhost:8000` in your browser to view the dashboard!

---

## ☁️ Deployment
* **Frontend:** Hosted on GitHub Pages.
* **Backend:** Hosted as a web service on Render. The `app.js` file directs API calls to the live Render URL. 
*(Note: Because the backend is hosted on a free Render tier, the AI Assistant may take ~50 seconds to wake up if it has not been used recently).*

## 🤝 Team & Contact
* **Developer & Researcher:** Lauren Vo (lavo@ucsd.edu)
* **Research Advisor:** Shay Samat (Data Science Alliance)

If you have feedback on the dashboard, notice a data issue, or would like to suggest additional resources or indicators, please feel free to get in touch!
