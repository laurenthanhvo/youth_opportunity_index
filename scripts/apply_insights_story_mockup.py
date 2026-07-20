from pathlib import Path
import re
import shutil

PAGES = [Path("index.html"), Path("landing.html")]
STYLES = Path("styles.css")

MAIN_HTML = r'''
<main class="landing-shell insights-story-page">
  <section class="story-hero">
    <div class="story-hero-bg"></div>

    <div class="story-hero-inner">
      <p class="landing-eyebrow">San Diego County youth opportunity</p>
      <h1>Mapping youth opportunity gaps across San Diego County</h1>
      <p>
        The Youth Opportunity Index shows where young people may face the greatest barriers to opportunity across neighborhoods, regions, and the county.
      </p>

      <div class="landing-actions">
        <a class="landing-primary-btn" href="./map.html">
          <i class="bi bi-map"></i>
          Open interactive map
        </a>
        <a class="landing-secondary-btn" href="#local-story">
          <i class="bi bi-geo-alt"></i>
          View local areas
        </a>
      </div>
    </div>
  </section>

  <section class="story-section" id="county-story">
    <div class="story-section-intro">
      <div>
        <p class="landing-eyebrow orange">1 · Countywide pattern</p>
        <h2>Countywide opportunity at a glance</h2>
        <p id="countyLead">Loading countywide insight…</p>
      </div>

      <div id="countyFacts" class="story-fact-grid">
        <div class="landing-loading">Loading metrics…</div>
      </div>
    </div>

    <div class="county-visual-grid">
      <article class="story-card scatter-card">
        <div class="story-card-head">
          <div>
            <h3>Economic strength is strongly linked to opportunity</h3>
            <p>Each point represents one Census tract.</p>
          </div>
          <span id="scatterBadge">r = —</span>
        </div>
        <div class="scatter-canvas-wrap">
          <canvas id="mainScatterCanvas"></canvas>
        </div>
      </article>

      <article class="story-card relation-card">
        <div class="story-card-head">
          <div>
            <h3>Conditions most linked to overall opportunity</h3>
            <p>Correlation with overall YOI.</p>
          </div>
          <span>Correlation</span>
        </div>
        <div class="relation-canvas-wrap">
          <canvas id="relationBarCanvas"></canvas>
        </div>
      </article>

      <aside class="story-card meaning-card" id="scatterMeaning">
        <div class="meaning-icon">
          <i class="bi bi-info-circle"></i>
        </div>
        <h3>What this means</h3>
        <p>
          Loading relationship summary…
        </p>
      </aside>
    </div>
  </section>

  <section class="story-section region-story" id="region-story">
    <div class="region-section-grid">
      <div class="story-section-copy">
        <p class="landing-eyebrow orange">2 · Regional comparison</p>
        <h2>Opportunity varies by region</h2>
        <p id="regionLead">Loading regional insight…</p>

        <a class="story-outline-btn" href="./map.html">
          <i class="bi bi-map"></i>
          Explore regions on map
        </a>
      </div>

      <div id="regionalActionGrid" class="region-card-grid"></div>

      <article class="story-card region-chart-card">
        <div class="story-card-head">
          <div>
            <h3>Overall YOI by region</h3>
            <p>Higher scores indicate stronger opportunity conditions.</p>
          </div>
          <span>0–100</span>
        </div>
        <div class="region-chart-wrap">
          <canvas id="regionChartCanvas"></canvas>
        </div>
      </article>
    </div>
  </section>

  <section class="story-section local-story" id="local-story">
    <div class="local-section-grid">
      <div class="story-section-copy local-copy">
        <p class="landing-eyebrow orange">3 · Local focus</p>
        <h2>Zoom in on the lowest-scoring local areas</h2>
        <p id="localLead">Loading local insight…</p>

        <div class="small-note-card">
          <i class="bi bi-shield-check"></i>
          <p>These areas are starting points for closer review and local action.</p>
        </div>
      </div>

      <article class="story-card local-card">
        <div id="topNeedList" class="local-slide"></div>

        <div class="local-controls">
          <button id="localPrevBtn" type="button" aria-label="Previous area">
            <i class="bi bi-arrow-left"></i>
          </button>
          <div id="localDots" class="local-dots"></div>
          <button id="localNextBtn" type="button" aria-label="Next area">
            <i class="bi bi-arrow-right"></i>
          </button>
        </div>
      </article>

      <article class="story-card local-map-card">
        <div id="topTractsMiniMap" class="top-tracts-mini-map story-map"></div>
        <div id="topTractsMiniMapLegend" class="mini-map-legend"></div>
      </article>
    </div>

    <div class="military-note">
      <i class="bi bi-exclamation-circle"></i>
      Military and low-residential ZIP codes can have unusual population patterns, so they should be reviewed separately before priority-setting.
    </div>
  </section>

  <footer class="story-footer">
    <div class="story-footer-brand">
      <img src="./logo.png" alt="Youth Opportunity Index logo" />
      <div>
        <strong>Youth Opportunity Desert Dashboard</strong>
        <span>A project of the Data Science Alliance (DSA)</span>
      </div>
    </div>

    <div class="story-footer-links">
      <a href="./datasets.html">Data & Methods</a>
      <a href="./about.html">About</a>
      <a href="./contact.html">Contact</a>
    </div>
  </footer>

  <div class="legacy-landing-dummies" hidden>
    <div id="landingMetrics"></div>
    <div id="executiveSummary"></div>
    <div id="distributionChart"></div>
    <div id="driverBars"></div>
    <div id="correlationStatus"></div>
    <div id="chartDefinitions"></div>
    <div id="correlationCallout"></div>
    <div id="domainCorrelationCanvas"></div>
    <div id="indicatorCorrelationCanvas"></div>
    <div id="domainPairCorrelationCanvas"></div>
    <div id="scatterCorrelationCanvas"></div>
    <div id="whyDashboardMatters"></div>
    <div id="regionBars"></div>
    <div id="domainAverageBars"></div>
    <div id="youthSupportsGapList"></div>
    <div id="economicGapList"></div>
    <div id="workforceCards"></div>
    <div id="priorityCarouselTabs"></div>
  </div>
</main>
'''

SCRIPT_HTML = r'''
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
  const STORY_COLORS = {
    navy: "#072843",
    teal: "#246E7E",
    teal2: "#2B989E",
    aqua: "#7CC6BB",
    yellow: "#EEC574",
    orange: "#E59A22",
    rust: "#B6442C",
    slate: "#64748b"
  };

  let scatterChart = null;
  let relationChart = null;
  let regionChart = null;
  let miniMap = null;
  let cachedTractGeojson = null;
  let currentTopNeedTracts = [];
  let activeLocalIndex = 0;

  function formatNumber(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
    return Number(value).toLocaleString();
  }

  function pct(numerator, denominator, digits = 1) {
    const n = Number(numerator || 0);
    const d = Number(denominator || 0);
    if (!d) return "N/A";
    return `${((n / d) * 100).toFixed(digits)}%`;
  }

  function normalizeGeoid(value) {
    const digits = String(value || "").replace(/\D/g, "");
    if (!digits) return "";
    return digits.padStart(11, "0").slice(-11);
  }

  function tractLabel(item) {
    if (item.name) return item.name;
    if (item.geoid) return `Census tract ${String(item.geoid).slice(-6)}`;
    return "Census tract";
  }

  function localTitle(item, index) {
    const candidate =
      item.neighborhood ||
      item.community ||
      item.community_name ||
      item.planning_area ||
      item.display_name ||
      item.area_name;

    if (candidate && !String(candidate).toLowerCase().includes("census tract")) {
      return candidate;
    }

    return `Area ${index + 1}`;
  }

  function domainAction(domain) {
    const d = String(domain || "").toLowerCase();

    if (d.includes("economic")) return "employment, income stability, and workforce access";
    if (d.includes("youth")) return "youth services and wraparound support";
    if (d.includes("health")) return "health access and neighborhood health conditions";
    if (d.includes("housing")) return "housing affordability and stability";
    if (d.includes("mobility")) return "transportation and connectivity";
    if (d.includes("education")) return "education pathways and attainment";
    if (d.includes("safety")) return "safety and environmental conditions";

    return "the underlying indicators";
  }

  function getFeatureGeoid(feature) {
    const p = feature?.properties || {};
    return normalizeGeoid(
      p.tract_geoid ||
      p.GEOID ||
      p.GEOID20 ||
      p.geoid ||
      p.TRACT_GEOID ||
      p.TRACTCE ||
      ""
    );
  }

  function factCard(label, value, note, accent, icon) {
    return `
      <article class="story-fact-card ${accent}">
        <div class="fact-icon"><i class="bi ${icon}"></i></div>
        <span>${label}</span>
        <strong>${value}</strong>
        <p>${note}</p>
      </article>
    `;
  }

  function renderCounty(data) {
    const metrics = data.metrics || {};
    const tractShare = pct(metrics.low_opportunity_tracts, metrics.tract_count);
    const youthShare = pct(metrics.youth_in_low_opportunity_tracts, metrics.total_youth_pop_14_24);

    const lead = document.getElementById("countyLead");
    if (lead) {
      lead.innerHTML = `
        Opportunity varies widely across the county. <strong>${formatNumber(metrics.low_opportunity_tracts)}</strong>
        mapped tracts score below 40/100, representing about
        <strong>${formatNumber(metrics.youth_in_low_opportunity_tracts)}</strong> youth ages 14–24.
      `;
    }

    const facts = document.getElementById("countyFacts");
    if (facts) {
      facts.innerHTML = [
        factCard("Tracts below 40", formatNumber(metrics.low_opportunity_tracts), `${tractShare} of mapped tracts`, "orange", "bi-bar-chart-fill"),
        factCard("Youth in those areas", formatNumber(metrics.youth_in_low_opportunity_tracts), `${youthShare} of estimated youth 14–24`, "teal", "bi-people-fill"),
        factCard("Lowest overall YOI", `${metrics.lowest_overall_score ?? "N/A"}/100`, "Lowest observed tract score", "yellow", "bi-speedometer2"),
        factCard("Most common gap", metrics.bottom_quintile_main_driver || "N/A", "Most frequent weakest domain", "aqua", "bi-exclamation-triangle-fill")
      ].join("");
    }
  }

  function chooseScatter(corr) {
    return (
      (corr.scatter_plots || []).find(d => String(d.title || "").toLowerCase().includes("economic")) ||
      (corr.scatter_plots || [])[0]
    );
  }

  function renderScatter(corr) {
    const canvas = document.getElementById("mainScatterCanvas");
    const badge = document.getElementById("scatterBadge");
    const meaning = document.getElementById("scatterMeaning");

    if (!canvas || !window.Chart) return;

    const scatter = chooseScatter(corr || {});

    if (!scatter || !Array.isArray(scatter.points) || !scatter.points.length) {
      if (meaning) {
        meaning.innerHTML = `
          <div class="meaning-icon"><i class="bi bi-info-circle"></i></div>
          <h3>Relationship chart unavailable</h3>
          <p>Run <code>python scripts/build_landing_correlation_insights.py</code> to generate the scatterplot data.</p>
        `;
      }
      return;
    }

    const r = Number(scatter.r || 0);
    const strength = Math.abs(r) >= 0.7 ? "strong" : Math.abs(r) >= 0.35 ? "moderate" : "weak";
    const direction = r >= 0 ? "positive" : "negative";

    if (badge) badge.textContent = `Correlation r = ${r.toFixed(2)}`;

    if (meaning) {
      meaning.innerHTML = `
        <div class="meaning-icon"><i class="bi bi-info-circle"></i></div>
        <h3>What this means</h3>
        <p>
          The scatterplot shows a <strong>${strength} ${direction} relationship</strong> between
          ${scatter.x_label.toLowerCase()} and overall opportunity. This does not prove cause and effect,
          but it helps show which conditions move with YOI across the county.
        </p>
        <p>
          Use this as a guide for where to inspect the map and domain details more closely.
        </p>
      `;
    }

    if (scatterChart) scatterChart.destroy();

    scatterChart = new Chart(canvas, {
      type: "scatter",
      data: {
        datasets: [{
          data: scatter.points.map(point => ({
            x: Number(point.x),
            y: Number(point.y),
            name: point.name
          })),
          backgroundColor: "rgba(36, 110, 126, 0.62)",
          borderColor: STORY_COLORS.navy,
          borderWidth: 1,
          pointRadius: 2.8,
          pointHoverRadius: 5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "nearest",
          intersect: true
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: STORY_COLORS.navy,
            titleColor: "#ffffff",
            bodyColor: "#ffffff",
            displayColors: false,
            padding: 10,
            callbacks: {
              title: items => items[0]?.raw?.name || "Census tract",
              label: item => [
                `${scatter.x_label}: ${Number(item.raw.x).toFixed(1)}`,
                `${scatter.y_label}: ${Number(item.raw.y).toFixed(1)}`
              ]
            }
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: scatter.x_label,
              color: STORY_COLORS.slate,
              font: { family: "Inter", size: 12, weight: "600" }
            },
            ticks: {
              color: STORY_COLORS.slate,
              font: { family: "Inter", size: 11, weight: "500" }
            },
            grid: { color: "#d8e1e8" },
            border: { color: "#cfd9e2" }
          },
          y: {
            title: {
              display: true,
              text: scatter.y_label,
              color: STORY_COLORS.slate,
              font: { family: "Inter", size: 12, weight: "600" }
            },
            ticks: {
              color: STORY_COLORS.slate,
              font: { family: "Inter", size: 11, weight: "500" }
            },
            grid: { color: "#d8e1e8" },
            border: { color: "#cfd9e2" }
          }
        }
      }
    });
  }

  function relationRows(corr) {
    const rows = [
      ...(corr.top_positive_indicators || []),
      ...(corr.top_negative_indicators || [])
    ]
      .filter(row => {
        const label = String(row.indicator || "");
        return !/overall|yoi$|standardized yoi|score z/i.test(label);
      })
      .sort((a, b) => Math.abs(Number(b.r || 0)) - Math.abs(Number(a.r || 0)))
      .slice(0, 8);

    if (rows.length) {
      return rows.map(row => ({
        label: row.indicator,
        value: Number(row.r || 0)
      }));
    }

    return (corr.domain_to_overall || []).slice(0, 7).map(row => ({
      label: row.domain,
      value: Number(row.r || 0)
    }));
  }

  function renderRelationChart(corr) {
    const canvas = document.getElementById("relationBarCanvas");
    if (!canvas || !window.Chart) return;

    const rows = relationRows(corr || {});

    if (!rows.length) return;

    if (relationChart) relationChart.destroy();

    relationChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: rows.map(row => row.label),
        datasets: [{
          data: rows.map(row => row.value),
          backgroundColor: rows.map(row => row.value < 0 ? STORY_COLORS.orange : STORY_COLORS.teal),
          borderColor: rows.map(row => row.value < 0 ? STORY_COLORS.orange : STORY_COLORS.teal),
          borderWidth: 1,
          borderRadius: 3,
          barPercentage: 0.7,
          categoryPercentage: 0.72
        }]
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: STORY_COLORS.navy,
            titleColor: "#ffffff",
            bodyColor: "#ffffff",
            displayColors: false,
            callbacks: {
              label: item => `r = ${Number(item.raw).toFixed(2)}`
            }
          }
        },
        scales: {
          x: {
            min: -1,
            max: 1,
            title: {
              display: true,
              text: "Correlation (r)",
              color: STORY_COLORS.slate,
              font: { family: "Inter", size: 12, weight: "600" }
            },
            ticks: {
              color: STORY_COLORS.slate,
              font: { family: "Inter", size: 11, weight: "500" }
            },
            grid: {
              color: ctx => ctx.tick.value === 0 ? STORY_COLORS.navy : "#d8e1e8",
              lineWidth: ctx => ctx.tick.value === 0 ? 1.2 : 1
            },
            border: { color: "#cfd9e2" }
          },
          y: {
            ticks: {
              color: "#0f172a",
              font: { family: "Inter", size: 11, weight: "600" }
            },
            grid: { display: false },
            border: { color: "#cfd9e2" }
          }
        }
      }
    });
  }

  function regionCard(region, index) {
    const weak = region.lowest_domain || "N/A";
    const weakScore = region.lowest_domain_score ?? "N/A";

    return `
      <article class="story-region-card ${index === 0 ? "lowest" : ""}">
        <div class="region-icon">${index + 1}</div>
        <h3>${region.region}</h3>
        <div class="region-score">${region.overall_yoi ?? "N/A"}/100</div>

        <div class="region-mini-metrics">
          <span>Overall YOI</span>
          <strong>Youth 14–24: ${formatNumber(region.youth_pop_14_24)}</strong>
          <strong>Weakest domain: ${weak}</strong>
          <em>${weakScore}/100</em>
        </div>

        <p>Start by reviewing ${domainAction(weak)}.</p>
      </article>
    `;
  }

  function renderRegions(data) {
    const regions = (data.county_regions || [])
      .slice()
      .sort((a, b) => Number(a.overall_yoi || 0) - Number(b.overall_yoi || 0));

    const lead = document.getElementById("regionLead");
    if (lead && regions.length) {
      const lowest = regions[0];
      const highest = regions[regions.length - 1];

      lead.innerHTML = `
        Compare the same index at the geography used for planning and policy. 
        <strong>${lowest.region}</strong> has the lowest regional score, while
        <strong>${highest.region}</strong> has the highest.
      `;
    }

    const grid = document.getElementById("regionalActionGrid");
    if (grid) {
      grid.innerHTML = regions.map(regionCard).join("");
    }

    renderRegionChart(regions);
  }

  function renderRegionChart(regions) {
    const canvas = document.getElementById("regionChartCanvas");
    if (!canvas || !window.Chart || !regions.length) return;

    if (regionChart) regionChart.destroy();

    regionChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: regions.map(r => r.region),
        datasets: [{
          data: regions.map(r => Number(r.overall_yoi || 0)),
          backgroundColor: regions.map((_, i) => i === 0 ? STORY_COLORS.orange : STORY_COLORS.teal),
          borderRadius: 4,
          barPercentage: 0.52,
          categoryPercentage: 0.7
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: STORY_COLORS.navy,
            titleColor: "#ffffff",
            bodyColor: "#ffffff",
            displayColors: false,
            callbacks: {
              label: item => `Overall YOI: ${Number(item.raw).toFixed(1)}/100`
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            max: 100,
            ticks: {
              color: STORY_COLORS.slate,
              font: { family: "Inter", size: 11, weight: "500" }
            },
            grid: { color: "#d8e1e8" },
            border: { color: "#cfd9e2" }
          },
          x: {
            ticks: {
              color: "#0f172a",
              font: { family: "Inter", size: 10, weight: "600" },
              maxRotation: 0,
              autoSkip: false
            },
            grid: { display: false },
            border: { color: "#cfd9e2" }
          }
        }
      }
    });
  }

  function renderLocalPanel() {
    const panel = document.getElementById("topNeedList");
    const dots = document.getElementById("localDots");

    if (!panel || !currentTopNeedTracts.length) return;

    const item = currentTopNeedTracts[activeLocalIndex];
    const gap = item.lowest_domain || "N/A";

    panel.innerHTML = `
      <div class="local-card-head">
        <div>
          <span>Lowest-scoring area ${activeLocalIndex + 1}</span>
          <h3>${localTitle(item, activeLocalIndex)}</h3>
          <p>${tractLabel(item)}</p>
        </div>
        <strong>${activeLocalIndex + 1} of ${currentTopNeedTracts.length}</strong>
      </div>

      <div class="local-card-grid">
        <div>
          <span>Overall YOI</span>
          <strong>${item.overall_yoi ?? "N/A"}/100</strong>
        </div>
        <div>
          <span>Youth 14–24</span>
          <strong>${formatNumber(item.youth_pop_14_24)}</strong>
        </div>
      </div>

      <div class="local-gap-row">
        <span>Main gap</span>
        <strong>${gap}</strong>
        <em>${item.lowest_domain_score ?? "N/A"}/100</em>
      </div>

      <div class="local-review-row">
        <span>Review first</span>
        <p>${domainAction(gap)}.</p>
      </div>
    `;

    if (dots) {
      dots.innerHTML = currentTopNeedTracts.map((_, i) => `
        <button class="${i === activeLocalIndex ? "active" : ""}" data-index="${i}" type="button" aria-label="Show area ${i + 1}"></button>
      `).join("");

      dots.querySelectorAll("[data-index]").forEach(button => {
        button.addEventListener("click", () => {
          activeLocalIndex = Number(button.dataset.index);
          renderLocalPanel();
          renderTopTractsMiniMap(currentTopNeedTracts, activeLocalIndex);
        });
      });
    }
  }

  function setupLocalControls() {
    const prev = document.getElementById("localPrevBtn");
    const next = document.getElementById("localNextBtn");

    if (prev) {
      prev.onclick = () => {
        if (!currentTopNeedTracts.length) return;
        activeLocalIndex = (activeLocalIndex - 1 + currentTopNeedTracts.length) % currentTopNeedTracts.length;
        renderLocalPanel();
        renderTopTractsMiniMap(currentTopNeedTracts, activeLocalIndex);
      };
    }

    if (next) {
      next.onclick = () => {
        if (!currentTopNeedTracts.length) return;
        activeLocalIndex = (activeLocalIndex + 1) % currentTopNeedTracts.length;
        renderLocalPanel();
        renderTopTractsMiniMap(currentTopNeedTracts, activeLocalIndex);
      };
    }
  }

  async function renderTopTractsMiniMap(topTracts, selectedIndex = 0) {
    const container = document.getElementById("topTractsMiniMap");

    if (!container || !Array.isArray(topTracts) || !topTracts.length || !window.L) return;

    const selectedItem = topTracts[selectedIndex] || topTracts[0];
    const selectedGeoid = normalizeGeoid(selectedItem.geoid);
    const targetGeoids = new Set(topTracts.map(item => normalizeGeoid(item.geoid)));

    if (!cachedTractGeojson) {
      const res = await fetch("./data/processed/boundaries/sd_tracts.geojson");
      cachedTractGeojson = await res.json();
    }

    if (miniMap) {
      miniMap.remove();
      miniMap = null;
    }

    miniMap = L.map("topTractsMiniMap", {
      zoomControl: false,
      attributionControl: false,
      scrollWheelZoom: false,
      dragging: true,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      tap: false
    });

    L.control.zoom({ position: "topright" }).addTo(miniMap);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 18
    }).addTo(miniMap);

    L.geoJSON(cachedTractGeojson, {
      filter: feature => !targetGeoids.has(getFeatureGeoid(feature)),
      style: {
        color: "#aab8c2",
        weight: 0.35,
        opacity: 0.35,
        fillColor: "#dce6ea",
        fillOpacity: 0.08
      },
      interactive: false
    }).addTo(miniMap);

    L.geoJSON(cachedTractGeojson, {
      filter: feature => targetGeoids.has(getFeatureGeoid(feature)) && getFeatureGeoid(feature) !== selectedGeoid,
      style: {
        color: STORY_COLORS.teal,
        weight: 1,
        opacity: 0.8,
        fillColor: STORY_COLORS.aqua,
        fillOpacity: 0.36
      },
      interactive: false
    }).addTo(miniMap);

    const selectedLayer = L.geoJSON(cachedTractGeojson, {
      filter: feature => getFeatureGeoid(feature) === selectedGeoid,
      style: {
        color: STORY_COLORS.navy,
        weight: 2.2,
        opacity: 1,
        fillColor: STORY_COLORS.orange,
        fillOpacity: 0.86
      },
      onEachFeature: (feature, layer) => {
        layer.bindTooltip(
          `<strong>${localTitle(selectedItem, selectedIndex)}</strong><br>` +
          `${tractLabel(selectedItem)}<br>` +
          `YOI: <strong>${selectedItem.overall_yoi}/100</strong><br>` +
          `Main gap: <strong>${selectedItem.lowest_domain}</strong>`,
          {
            sticky: true,
            direction: "top",
            className: "mini-map-tooltip"
          }
        );
      }
    }).addTo(miniMap);

    const allLayer = L.geoJSON(cachedTractGeojson, {
      filter: feature => targetGeoids.has(getFeatureGeoid(feature)),
      style: { opacity: 0, fillOpacity: 0 },
      interactive: false
    });

    const allBounds = allLayer.getBounds();
    const selectedBounds = selectedLayer.getBounds();

    if (allBounds.isValid()) {
      miniMap.fitBounds(allBounds.pad(0.7));
    } else if (selectedBounds.isValid()) {
      miniMap.fitBounds(selectedBounds.pad(1.8));
    } else {
      miniMap.setView([32.82, -117.05], 10);
    }

    setTimeout(() => {
      miniMap.invalidateSize();
      if (allBounds.isValid()) miniMap.fitBounds(allBounds.pad(0.7));
    }, 150);
  }

  async function loadInsightsStory() {
    const [landingRes, corrRes] = await Promise.all([
      fetch("./data/processed/landing/landing_insights.json"),
      fetch("./data/processed/landing/landing_correlation_insights.json").catch(() => null)
    ]);

    const data = await landingRes.json();
    const corr = corrRes && corrRes.ok ? await corrRes.json() : {};

    renderCounty(data);
    renderScatter(corr);
    renderRelationChart(corr);
    renderRegions(data);

    currentTopNeedTracts = data.top_need_tracts || [];
    activeLocalIndex = 0;

    const localLead = document.getElementById("localLead");
    if (localLead && currentTopNeedTracts.length) {
      const first = currentTopNeedTracts[0];

      localLead.innerHTML = `
        Review the areas with the greatest opportunity gaps one at a time.
        The lowest-scoring area is <strong>${localTitle(first, 0)}</strong> at
        <strong>${first.overall_yoi ?? "N/A"}/100</strong>.
      `;
    }

    setupLocalControls();
    renderLocalPanel();
    renderTopTractsMiniMap(currentTopNeedTracts, activeLocalIndex);
  }

  loadInsightsStory().catch(err => {
    console.error(err);
    document.querySelector(".landing-shell")?.insertAdjacentHTML(
      "beforeend",
      "<div class='landing-loading'>Could not load insights. Run the landing data build scripts and refresh.</div>"
    );
  });
</script>
'''

CSS = r'''
/* ============================================================
   Storytelling Insights Page — final mockup implementation
   ============================================================ */

body.landing-page,
body.pro-landing {
  background: #ffffff !important;
  overflow: auto !important;
}

.storytelling-hidden,
.snapshot-hero-card,
.hero-summary-v3,
.story-progress,
.priority-carousel-tabs,
.local-carousel-tabs,
#executiveSummary,
#distributionChart,
#driverBars {
  display: none !important;
}

.pro-landing .landing-shell.insights-story-page {
  width: 100% !important;
  max-width: none !important;
  margin: 0 !important;
  padding: 0 !important;
  background: #ffffff !important;
}

.insights-story-page .story-hero {
  position: relative;
  overflow: hidden;
  padding: 74px max(54px, calc((100vw - 1160px) / 2)) 70px;
  border-bottom: 1px solid #d8e1e8;
  background:
    radial-gradient(circle at 86% 52%, rgba(238, 197, 116, 0.30), transparent 23%),
    radial-gradient(circle at 78% 58%, rgba(124, 198, 187, 0.34), transparent 28%),
    linear-gradient(180deg, #ffffff 0%, #f8fbfc 100%);
}

.insights-story-page .story-hero-bg {
  position: absolute;
  inset: auto 0 -80px auto;
  width: 62%;
  height: 360px;
  pointer-events: none;
  opacity: 0.76;
  background:
    repeating-radial-gradient(ellipse at center, rgba(36,110,126,0.20) 0 1px, transparent 1px 13px);
  transform: rotate(-9deg) skewX(-14deg);
  border-radius: 50%;
  filter: blur(0.2px);
}

.insights-story-page .story-hero-inner {
  position: relative;
  z-index: 1;
  max-width: 980px;
}

.insights-story-page .story-hero h1 {
  max-width: 980px;
  margin: 0 0 22px;
  color: #0f172a;
  font-size: clamp(3.2rem, 6vw, 5.7rem);
  line-height: 0.96;
  letter-spacing: -0.07em;
  font-weight: 720;
}

.insights-story-page .story-hero p:not(.landing-eyebrow) {
  max-width: 720px;
  margin: 0 0 28px;
  color: #52637a;
  font-size: 1.08rem;
  line-height: 1.62;
}

.insights-story-page .landing-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.insights-story-page .landing-primary-btn,
.insights-story-page .landing-secondary-btn,
.insights-story-page .story-outline-btn {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  min-height: 46px;
  padding: 0 18px;
  border-radius: 6px;
  font-weight: 700;
  text-decoration: none;
}

.insights-story-page .landing-primary-btn {
  background: #072843;
  color: #ffffff;
  border: 1px solid #072843;
}

.insights-story-page .landing-secondary-btn,
.insights-story-page .story-outline-btn {
  background: #ffffff;
  color: #246e7e;
  border: 1px solid #b8d3d8;
}

.insights-story-page .story-section {
  padding: 48px max(54px, calc((100vw - 1160px) / 2));
  border-bottom: 1px solid #edf2f4;
}

.insights-story-page .story-section-intro {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 42px;
  align-items: start;
  margin-bottom: 22px;
}

.insights-story-page .story-section-copy h2,
.insights-story-page .story-section-intro h2,
.insights-story-page .section-head-clean h2 {
  margin: 0 0 12px;
  color: #0f172a;
  font-size: clamp(2rem, 3.4vw, 3.2rem);
  line-height: 1.04;
  letter-spacing: -0.055em;
  font-weight: 680;
}

.insights-story-page .story-section-copy p,
.insights-story-page .story-section-intro p:not(.landing-eyebrow) {
  margin: 0;
  color: #52637a;
  font-size: 0.98rem;
  line-height: 1.58;
}

.insights-story-page .landing-eyebrow {
  margin: 0 0 10px;
  color: #246e7e !important;
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.insights-story-page .landing-eyebrow.orange {
  color: #e59a22 !important;
}

.story-fact-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.story-fact-card {
  min-height: 158px;
  padding: 18px;
  background: #ffffff;
  border: 1px solid #d8e1e8;
  border-radius: 8px;
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.035);
}

.story-fact-card.orange { border-top: 4px solid #e59a22; }
.story-fact-card.teal { border-top: 4px solid #246e7e; }
.story-fact-card.yellow { border-top: 4px solid #eec574; }
.story-fact-card.aqua { border-top: 4px solid #7cc6bb; }

.story-fact-card .fact-icon {
  height: 28px;
  margin-bottom: 10px;
  color: #246e7e;
  font-size: 1.45rem;
}

.story-fact-card.orange .fact-icon,
.story-fact-card.yellow .fact-icon {
  color: #e59a22;
}

.story-fact-card span,
.story-region-card span,
.local-card-head span,
.local-card-grid span,
.local-gap-row span,
.local-review-row span {
  display: block;
  color: #64748b;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  line-height: 1.22;
  text-transform: uppercase;
}

.story-fact-card strong {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  font-size: 1.6rem;
  line-height: 1.04;
  font-weight: 720;
  letter-spacing: -0.045em;
}

.story-fact-card p {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 0.8rem;
  line-height: 1.38;
}

.county-visual-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(330px, 0.85fr) 290px;
  gap: 18px;
  align-items: stretch;
}

.story-card {
  background: #ffffff;
  border: 1px solid #d8e1e8;
  border-radius: 8px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.scatter-card,
.relation-card,
.meaning-card {
  padding: 22px;
  min-height: 360px;
}

.story-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.story-card-head h3 {
  margin: 0;
  color: #0f172a;
  font-size: 1rem;
  line-height: 1.22;
  font-weight: 720;
  letter-spacing: -0.03em;
}

.story-card-head p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 0.82rem;
  line-height: 1.45;
}

.story-card-head span {
  flex: 0 0 auto;
  padding: 6px 9px;
  background: #fff7df;
  border: 1px solid #eed188;
  border-radius: 6px;
  color: #8a5b00;
  font-size: 0.72rem;
  font-weight: 750;
}

.scatter-canvas-wrap,
.relation-canvas-wrap,
.region-chart-wrap {
  position: relative;
  height: 295px;
}

.scatter-canvas-wrap canvas,
.relation-canvas-wrap canvas,
.region-chart-wrap canvas {
  width: 100% !important;
  height: 100% !important;
}

.meaning-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: linear-gradient(180deg, #f8fbfc, #eef7f8);
}

.meaning-icon {
  width: 36px;
  height: 36px;
  margin-bottom: 16px;
  display: grid;
  place-items: center;
  border: 1px solid #b8d3d8;
  border-radius: 999px;
  color: #246e7e;
  font-size: 1.2rem;
}

.meaning-card h3 {
  margin: 0 0 12px;
  color: #0f172a;
  font-size: 1.25rem;
  line-height: 1.18;
  letter-spacing: -0.035em;
}

.meaning-card p {
  margin: 0 0 12px;
  color: #52637a;
  font-size: 0.92rem;
  line-height: 1.55;
}

.region-section-grid {
  display: grid;
  grid-template-columns: 220px repeat(4, minmax(0, 1fr)) 280px;
  gap: 14px;
  align-items: stretch;
}

.region-card-grid {
  display: contents;
}

.story-region-card {
  min-height: 260px;
  padding: 18px;
  border: 1px solid #d8e1e8;
  border-top: 4px solid #7cc6bb;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.035);
}

.story-region-card.lowest {
  border-top-color: #e59a22;
}

.region-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  margin-bottom: 12px;
  border-radius: 999px;
  background: #eef7f8;
  color: #246e7e;
  font-weight: 800;
}

.story-region-card.lowest .region-icon {
  background: #fff7df;
  color: #8a5b00;
}

.story-region-card h3 {
  margin: 0 0 8px;
  color: #0f172a;
  font-size: 1rem;
  line-height: 1.18;
  font-weight: 720;
  letter-spacing: -0.03em;
}

.region-score {
  color: #246e7e;
  font-size: 1.25rem;
  font-weight: 760;
  margin-bottom: 16px;
}

.region-mini-metrics {
  display: grid;
  gap: 5px;
  margin-bottom: 14px;
}

.region-mini-metrics strong {
  color: #0f172a;
  font-size: 0.78rem;
  line-height: 1.35;
}

.region-mini-metrics em {
  color: #246e7e;
  font-size: 0.78rem;
  font-style: normal;
  font-weight: 750;
}

.story-region-card p {
  margin: 0;
  color: #52637a;
  font-size: 0.78rem;
  line-height: 1.45;
}

.region-chart-card {
  padding: 18px;
}

.region-chart-wrap {
  height: 215px;
}

.story-outline-btn {
  margin-top: 22px;
  width: max-content;
}

.local-section-grid {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) minmax(430px, 0.95fr);
  gap: 20px;
  align-items: stretch;
}

.small-note-card {
  margin-top: 38px;
  padding: 18px;
  border: 1px solid #d8e1e8;
  border-radius: 8px;
  background: #f8fbfc;
  color: #52637a;
  font-size: 0.9rem;
  line-height: 1.5;
}

.small-note-card i {
  color: #246e7e;
  font-size: 1.3rem;
  margin-bottom: 8px;
  display: inline-block;
}

.local-card {
  overflow: hidden;
}

.local-card-head {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 24px;
  background: linear-gradient(135deg, rgba(238,197,116,0.32), rgba(124,198,187,0.20));
  border-bottom: 1px solid #d8e1e8;
}

.local-card-head h3 {
  margin: 8px 0 4px;
  color: #0f172a;
  font-size: 1.9rem;
  line-height: 1;
  letter-spacing: -0.05em;
  font-weight: 700;
}

.local-card-head p {
  margin: 0;
  color: #52637a;
  font-size: 0.92rem;
}

.local-card-head > strong {
  height: max-content;
  padding: 6px 10px;
  border: 1px solid #eed188;
  border-radius: 6px;
  color: #8a5b00;
  background: #fff7df;
  font-size: 0.78rem;
}

.local-card-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid #d8e1e8;
}

.local-card-grid > div,
.local-gap-row,
.local-review-row {
  padding: 18px 24px;
}

.local-card-grid > div:first-child {
  border-right: 1px solid #d8e1e8;
}

.local-card-grid strong,
.local-gap-row strong {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  font-size: 1.35rem;
  font-weight: 720;
  letter-spacing: -0.035em;
}

.local-gap-row {
  border-bottom: 1px solid #d8e1e8;
}

.local-gap-row em {
  display: block;
  margin-top: 4px;
  color: #e59a22;
  font-style: normal;
  font-size: 0.9rem;
  font-weight: 750;
}

.local-review-row p {
  margin: 8px 0 0;
  color: #52637a;
  font-size: 0.92rem;
  line-height: 1.45;
}

.local-controls {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 14px;
  align-items: center;
  padding: 16px 24px;
}

.local-controls button {
  width: 42px;
  height: 38px;
  border: 1px solid #d8e1e8;
  border-radius: 6px;
  background: #ffffff;
  color: #0f172a;
  cursor: pointer;
}

.local-controls button:hover {
  border-color: #eec574;
  background: #fff7df;
}

.local-dots {
  display: flex;
  justify-content: center;
  gap: 7px;
}

.local-dots button {
  width: 9px;
  height: 9px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: #cbd5e1;
  cursor: pointer;
}

.local-dots button.active {
  width: 24px;
  background: #e59a22;
}

.local-map-card {
  padding: 0;
  overflow: hidden;
}

.story-map {
  height: 100%;
  min-height: 430px;
}

#topTractsMiniMapLegend {
  display: none !important;
}

.military-note {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  padding: 12px 16px;
  border: 1px solid #f0d59b;
  border-left: 4px solid #e59a22;
  border-radius: 6px;
  background: #fffaf0;
  color: #52637a;
  font-size: 0.88rem;
}

.military-note i {
  color: #e59a22;
}

.story-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  padding: 24px max(54px, calc((100vw - 1160px) / 2));
  border-top: 1px solid #d8e1e8;
  background: #fbfcfd;
}

.story-footer-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.story-footer-brand img {
  width: 38px;
  height: 38px;
  object-fit: contain;
}

.story-footer-brand strong {
  display: block;
  color: #0f172a;
  font-size: 0.95rem;
}

.story-footer-brand span {
  display: block;
  margin-top: 3px;
  color: #64748b;
  font-size: 0.82rem;
}

.story-footer-links {
  display: flex;
  gap: 18px;
}

.story-footer-links a {
  color: #52637a;
  text-decoration: none;
  font-size: 0.86rem;
  font-weight: 600;
}

@media (max-width: 1200px) {
  .insights-story-page .story-section-intro,
  .county-visual-grid,
  .region-section-grid,
  .local-section-grid {
    grid-template-columns: 1fr;
  }

  .story-fact-grid,
  .region-card-grid,
  .regions-clean {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .story-map {
    height: 440px;
  }
}

@media (max-width: 720px) {
  .insights-story-page .story-hero,
  .insights-story-page .story-section,
  .story-footer {
    padding-left: 22px;
    padding-right: 22px;
  }

  .insights-story-page .story-hero h1 {
    font-size: clamp(2.8rem, 14vw, 4.5rem);
  }

  .story-fact-grid,
  .region-card-grid,
  .local-card-grid {
    grid-template-columns: 1fr;
  }

  .local-card-grid > div:first-child {
    border-right: 0;
    border-bottom: 1px solid #d8e1e8;
  }

  .story-footer {
    flex-direction: column;
    align-items: flex-start;
  }
}
'''

def patch_page(path: Path):
    html = path.read_text()

    backup = path.with_suffix(path.suffix + ".bak_story_mockup_exact")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"Backup saved: {backup}")

    if "cdn.jsdelivr.net/npm/chart.js" not in html:
        html = html.replace("</head>", '  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>\n</head>')

    if "unpkg.com/leaflet@1.9.4/dist/leaflet.css" not in html:
        html = html.replace("</head>", '  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">\n</head>')

    main_match = re.search(r'<main[^>]*class="[^"]*landing-shell[^"]*"[^>]*>', html)
    if not main_match:
        raise RuntimeError(f"Could not find landing-shell main in {path}")

    body_close = html.rfind("</body>")
    if body_close == -1:
        raise RuntimeError(f"Could not find </body> in {path}")

    html = html[:main_match.start()] + MAIN_HTML + "\n\n" + SCRIPT_HTML + "\n" + html[body_close:]

    path.write_text(html)
    print(f"Updated {path}")

for page in PAGES:
    if page.exists():
        patch_page(page)
    else:
        print(f"Skipping missing file: {page}")

if not STYLES.exists():
    raise FileNotFoundError("styles.css not found")

backup = STYLES.with_suffix(STYLES.suffix + ".bak_story_mockup_exact")
if not backup.exists():
    shutil.copy2(STYLES, backup)
    print(f"Backup saved: {backup}")

css = STYLES.read_text()

# Remove older insights-only blocks so they do not fight the new layout.
markers = [
    "FINAL Insights page cleanup",
    "Insights clean final pass",
    "Insights page v3 cleanup",
    "Insights page v3 cleanup override",
    "Insights page v2: concise storytelling layout",
    "Insights page: 3-section county",
    "Landing page correlation insight charts",
    "Landing page chart definitions"
]

for marker in markers:
    pattern = re.compile(
        r'\n/\* ={20,}\s*\n\s*' + re.escape(marker) + r'[\s\S]*?(?=\n/\* ={20,}|\Z)',
        re.MULTILINE
    )
    css, n = pattern.subn("\n", css)
    if n:
        print(f"Removed old CSS block: {marker}")

css = css.rstrip() + "\n\n" + CSS + "\n"
STYLES.write_text(css)
print("Done.")
