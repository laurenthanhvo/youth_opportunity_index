const DOMAINS = [
  'economic', 'education', 'health', 'housing',
  'safety_env', 'mobility_connectivity', 'youth_supports',
];

const DOMAIN_LABELS = {
  economic: 'Economic',
  education: 'Education',
  health: 'Health',
  housing: 'Housing',
  safety_env: 'Safety / Env',
  mobility_connectivity: 'Mobility / Connectivity',
  youth_supports: 'Youth Supports',
};

const BLUES = ['#eaf3fb', '#b6d3e9', '#6da3c9', '#275c81', '#0a2f4a'];

const state = {
  rawYoi: [],
  tractMap: new Map(),
  geojson: null,
  routesGeojson: null,
  stopsGeojson: null,
  meta: [],
  selectedGeoid: null,
  activePanel: 'controls',
  mapLayer: 'YOI (0–100)',
  scoreMode: 'level',
  showChoro: true,
  showBounds: true,
  showRoutes: false,
  showStops: false,
  showHover: true,
  rawWeights: Object.fromEntries(DOMAINS.map(d => [d, 1])),
  normalizedWeights: Object.fromEntries(DOMAINS.map(d => [d, 1 / DOMAINS.length])),
  hasInitialFit: false,
  coiRows: [],
  coiMap: new Map(),
  showCoiOverlay: false,
  servicesGeojson: null,
  showServices: false,
  supervisorDistrictsGeojson: null,
  showSupervisorDistricts: false,
};

let tractLayer = null;
let routesLayer = null;
let routesHaloLayer = null;
let stopsLayer = null;
let legendControl = null;
let chartTooltip = null;
let popupRef = null;
let serviceLayer = null;
let supervisorDistrictsLayer = null;

const map = L.map('map', { zoomControl: true, preferCanvas: true, attributionControl: true }).setView([32.87, -116.96], 10);

map.getContainer().style.opacity = '0';
map.getContainer().style.transition = 'opacity 120ms ease';
// base map without labels
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; OpenStreetMap &copy; CARTO',
  maxZoom: 19,
}).addTo(map);

// pane for labels above polygons
map.createPane('labels');
map.getPane('labels').style.zIndex = 650;
map.getPane('labels').style.pointerEvents = 'none';

// label-only tiles on top
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', {
  pane: 'labels',
  maxZoom: 19,
}).addTo(map);

function normalizeGeoid(v) {
  if (v == null) return '';
  const digits = String(v).replace(/\D/g, '');
  if (!digits) return '';
  return digits.padStart(11, '0').slice(-11);
}

function isFiniteNumber(v) {
  return Number.isFinite(+v);
}

function coerceCsvRows(rows) {
  return rows.map(row => {
    const out = {};
    Object.entries(row).forEach(([k, v]) => {
      if (k === 'tract_geoid') out[k] = normalizeGeoid(v);
      else if (v == null || String(v).trim() === '') out[k] = null;
      else if (!Number.isNaN(Number(v))) out[k] = Number(v);
      else out[k] = v;
    });
    return out;
  });
}

function featureCount(obj) {
  return obj?.features?.length || 0;
}

function activeMetricKey() {
  if (state.mapLayer === 'YOI (0–100)') return 'yoi_custom_0_100';
  const d = state.mapLayer.replace(/ score$/, '');
  return `${d}_score`;
}

function activeLayerTitle() {
  if (state.mapLayer === 'YOI (0–100)') return 'Overall YOI';
  return `${DOMAIN_LABELS[state.mapLayer.replace(/ score$/, '')] || state.mapLayer} Domain`;
}

function metricDomain() {
  return state.mapLayer === 'YOI (0–100)' ? [0, 100] : [0, 1];
}

function levelBins() {
  const [min, max] = metricDomain();
  const step = (max - min) / 5;
  return [min + step, min + 2 * step, min + 3 * step, min + 4 * step];
}

function currentBins() {
  return levelBins();
}

function currentLegendLabels() {
  if (state.scoreMode === 'score') {
    return ['0', '20', '40', '60', '80', '100'];
  }
  return ['Very Low', 'Low', 'Moderate', 'High', 'Very High'];
}

function valueToCategory(v) {
  if (!isFiniteNumber(v)) return 'N/A';
  const bins = levelBins();
  if (v < bins[0]) return 'Very Low';
  if (v < bins[1]) return 'Low';
  if (v < bins[2]) return 'Moderate';
  if (v < bins[3]) return 'High';
  return 'Very High';
}

function scoreDisplayValue(v) {
  if (!isFiniteNumber(v)) return 'N/A';
  if (state.mapLayer === 'YOI (0–100)') return `${Math.round(v)}/100`;
  return `${Math.round(v * 100)}/100`;
}

function tractLabelFromGeoid(geoid) {
  const t = normalizeGeoid(geoid).slice(5);
  if (!t) return 'Census tract';
  const num = `${parseInt(t.slice(0, 4), 10)}.${t.slice(4)}`.replace(/\.00$/, '.00');
  return `Census tract ${num}`;
}

function tractSuffixFromGeoid(geoid) {
  const g = normalizeGeoid(geoid);
  return g ? g.slice(5) : '';
}

function geoidFromSearchQuery(query) {
  const raw = String(query || '').trim();
  if (!raw) return '';

  const digits = raw.replace(/\D/g, '');
  if (!digits) return '';

  if (digits.length >= 11) return normalizeGeoid(digits);

  if (digits.length <= 6) return '';

  // tract-only search like 20801 or 208.01 -> county tract GEOID suffix
  const tractSuffix = digits.padStart(6, '0').slice(-6);
  return `06073${tractSuffix}`;
}

function searchFeature(query) {
  const geoFeatures = state.geojson?.features || [];
  if (!geoFeatures.length) return null;

  const normalized = geoidFromSearchQuery(query);
  if (normalized) {
    const exact = geoFeatures.find(f => normalizeGeoid(f.properties?.tract_geoid) === normalized);
    if (exact) return exact;

    const suffix = tractSuffixFromGeoid(normalized);
    const suffixMatch = geoFeatures.find(f => tractSuffixFromGeoid(f.properties?.tract_geoid) === suffix);
    if (suffixMatch) return suffixMatch;
  }

  const lowered = String(query || '').trim().toLowerCase();
  if (!lowered) return null;

  return geoFeatures.find(f => tractLabelFromGeoid(f.properties?.tract_geoid).toLowerCase().includes(lowered));
}

function setSearchStatus(message, isError = false) {
  const input = document.getElementById('searchInput');
  if (!input) return;
  input.setCustomValidity(isError ? message : '');
  input.title = message || '';
  if (isError && typeof input.reportValidity === 'function') input.reportValidity();
}

function runSearch() {
  const input = document.getElementById('searchInput');
  if (!input) return;
  const query = input.value;

  if (!String(query || '').trim()) {
    if (state.selectedGeoid) {
      const feature = searchFeature(state.selectedGeoid);
      if (feature) {
        map.fitBounds(L.geoJSON(feature).getBounds().pad(0.8));
        setSearchStatus('Zoomed to selected tract.');
      }
    }
    return;
  }

  const feature = searchFeature(query);
  if (!feature) {
    setSearchStatus('No matching tract found. Try an 11-digit GEOID or tract number like 208.01.', true);
    return;
  }

  const geoid = normalizeGeoid(feature.properties?.tract_geoid);
  state.selectedGeoid = geoid;
  updateAll(true);
  setPanel('location');
  map.fitBounds(L.geoJSON(feature).getBounds().pad(0.8));
  setSearchStatus(`Found ${tractLabelFromGeoid(geoid)}.`);

  const row = state.tractMap.get(geoid);
  if (popupRef) popupRef.remove();
  popupRef = L.popup({ closeButton: false, autoPan: false, offset: [0, -4] })
    .setLatLng(L.geoJSON(feature).getBounds().getCenter())
    .setContent(popupHtml(row, geoid))
    .openOn(map);
}

function normalizeWeights() {
  const total = DOMAINS.reduce((sum, d) => sum + (+state.rawWeights[d] || 0), 0);
  state.normalizedWeights = Object.fromEntries(
    DOMAINS.map(d => [d, total > 0 ? (+state.rawWeights[d] || 0) / total : 1 / DOMAINS.length])
  );
}

function updateWeightsUi() {
  normalizeWeights();

  DOMAINS.forEach(d => {
    const raw = +state.rawWeights[d] || 0;
    const pct = ((+state.normalizedWeights[d] || 0) * 100).toFixed(1);
    const label = document.getElementById(`weight_${d}`);
    const slider = document.getElementById(`slider_${d}`);
    if (label) label.textContent = `${pct}%`;
    if (slider) slider.title = `Raw slider: ${raw.toFixed(2)} | Normalized weight: ${pct}%`;
  });

  const summaryEl = document.getElementById('weightsSummary');
  if (summaryEl) {
    const values = DOMAINS.map(d => +state.rawWeights[d] || 0);
    const allEqual = values.every(v => Math.abs(v - values[0]) < 1e-9);
    if (allEqual) {
      summaryEl.textContent = `All sliders are equal, so each domain currently contributes ${(100 / DOMAINS.length).toFixed(1)}%.`;
    } else {
      summaryEl.textContent = 'Slider values are auto-normalized so the domain weights always sum to 100%.';
    }
  }

  const impactEl = document.getElementById('weightsImpactNote');
  if (impactEl) {
    if (state.mapLayer === 'YOI (0–100)') {
      impactEl.textContent = 'You are viewing Overall Youth Opportunity, so slider changes recolor the map immediately.';
    } else {
      impactEl.textContent = `You are viewing ${activeLayerTitle()}. Slider changes affect Overall YOI and the Domain Profile, but not this single-domain map.`;
    }
  }
}

function recomputeCustomScores() {
  normalizeWeights();
  state.rawYoi.forEach(row => {
    let total = 0;
    DOMAINS.forEach(d => { total += (+row[`${d}_score`] || 0) * state.normalizedWeights[d]; });
    row.yoi_custom_0_1 = total;
    row.yoi_custom_0_100 = total * 100;
  });
  state.tractMap = new Map(state.rawYoi.map(r => [normalizeGeoid(r.tract_geoid), r]));
}

function percentileForRow(row) {
  const ranked = [...state.rawYoi].sort((a, b) => (+b.yoi_custom_0_100 || 0) - (+a.yoi_custom_0_100 || 0));
  const idx = ranked.findIndex(r => normalizeGeoid(r.tract_geoid) === normalizeGeoid(row.tract_geoid));
  if (idx < 0) return { rank: null, total: ranked.length, percentile: null };
  const rank = idx + 1;
  const pct = Math.round((1 - idx / ranked.length) * 100);
  return { rank, total: ranked.length, percentile: pct };
}

function currentValue(row) {
  const metric = activeMetricKey();
  return row ? +row[metric] : NaN;
}

function currentCoiRow(geoid) {
  return state.coiMap.get(normalizeGeoid(geoid)) || null;
}

function currentCoiValue(geoid) {
  const row = currentCoiRow(geoid);
  return row ? +row.coi_score : NaN;
}

function currentCoiCategory(geoid) {
  const row = currentCoiRow(geoid);
  return row ? row.coi_level : 'N/A';
}

function activeOverlayMode() {
  if (state.showCoiOverlay) return 'coi';
  if (state.showChoro) return 'yoi';
  return 'none';
}

function hasThematicOverlay() {
  return activeOverlayMode() !== 'none';
}

function setThematicOverlayMode(mode) {
  if (mode === 'coi') {
    state.showCoiOverlay = true;
    state.showChoro = false;
  } else if (mode === 'none') {
    state.showCoiOverlay = false;
    state.showChoro = false;
  } else {
    state.showCoiOverlay = false;
    state.showChoro = true;
  }
}

function syncOverlayControls() {
  const choroToggle = document.getElementById('toggleChoro');
  const coiToggle = document.getElementById('toggleCoiOverlay');
  if (choroToggle) choroToggle.checked = !!state.showChoro;
  if (coiToggle) coiToggle.checked = !!state.showCoiOverlay;

  document.querySelectorAll('#overlayQuickToggle .seg-btn').forEach(btn => {
    const isActive = btn.dataset.overlayMode === activeOverlayMode();
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
}

function overlayMetricDomain() {
  if (state.showCoiOverlay) return [0, 100];
  return metricDomain();
}

function overlayLevelBins() {
  const [min, max] = overlayMetricDomain();
  const step = (max - min) / 5;
  return [min + step, min + 2 * step, min + 3 * step, min + 4 * step];
}

function valueToCategoryWithBins(v, bins) {
  if (!isFiniteNumber(v)) return 'N/A';
  if (v < bins[0]) return 'Very Low';
  if (v < bins[1]) return 'Low';
  if (v < bins[2]) return 'Moderate';
  if (v < bins[3]) return 'High';
  return 'Very High';
}

function overlayValueToCategory(v, geoid) {
  if (state.showCoiOverlay) {
    const category = currentCoiCategory(geoid);
    if (category && category !== 'N/A') return category;
  }
  return valueToCategoryWithBins(v, overlayLevelBins());
}

function overlayScoreDisplayValue(v) {
  if (!isFiniteNumber(v)) return 'N/A';
  if (state.showCoiOverlay) return `${Math.round(v)}/100`;
  return scoreDisplayValue(v);
}

function overlayScorePercent(v) {
  if (!isFiniteNumber(v)) return 0;
  const [min, max] = overlayMetricDomain();
  return Math.max(0, Math.min(100, ((v - min) / (max - min || 1)) * 100));
}

function overlayLayerTitle() {
  return state.showCoiOverlay ? 'Child Opportunity Index' : activeLayerTitle();
}

function overlayContextLabel() {
  return state.showCoiOverlay ? 'Compared to nation' : 'Compared to county';
}

function thematicValueForGeoid(geoid, row = null) {
  const tractRow = row || state.tractMap.get(normalizeGeoid(geoid));
  return state.showCoiOverlay ? currentCoiValue(geoid) : currentValue(tractRow);
}

function colorForValue(v) {
  if (!isFiniteNumber(v)) return '#eef2f7';

  if (state.scoreMode === 'score') {
    const [min, max] = overlayMetricDomain();
    const t = Math.max(0, Math.min(1, (v - min) / (max - min || 1)));
    return d3.interpolateRgbBasis(BLUES)(t);
  }

  const bins = overlayLevelBins();
  if (v < bins[0]) return BLUES[0];
  if (v < bins[1]) return BLUES[1];
  if (v < bins[2]) return BLUES[2];
  if (v < bins[3]) return BLUES[3];
  return BLUES[4];
}


function styleFeature(feature) {
  const geoid = normalizeGeoid(feature.properties?.tract_geoid);
  const row = state.tractMap.get(geoid);
  const value = thematicValueForGeoid(geoid, row);
  const isSelected = geoid === normalizeGeoid(state.selectedGeoid);
  const showFill = hasThematicOverlay();
  return {
    color: isSelected ? '#ffffff' : (state.showBounds ? 'rgba(27,51,75,0.34)' : 'transparent'),
    weight: isSelected ? 3.2 : (state.showBounds ? 0.6 : 0),
    fillColor: showFill ? colorForValue(value) : '#ffffff',
    fillOpacity: showFill ? 0.92 : 0.02,
  };
}


function popupHtml(row, geoid) {
  const value = thematicValueForGeoid(geoid, row);
  const badge = state.scoreMode === 'score'
    ? overlayScoreDisplayValue(value)
    : overlayValueToCategory(value, geoid);
  const scoreWidth = overlayScorePercent(value);
  return `
    <div class="popup-card">
      <div class="popup-title">${tractLabelFromGeoid(geoid)}</div>
      <div class="popup-subtitle">San Diego-Chula Vista-Carlsbad, CA</div>
      <div class="popup-note">Click census tract for details</div>
      <div class="popup-divider"></div>
      <div class="popup-row">
        <div>
          <div class="popup-label">${overlayLayerTitle()}</div>
          <div class="popup-context">${overlayContextLabel()}</div>
        </div>
        <div class="popup-badge ${state.scoreMode === 'score' ? 'score-badge' : ''}">${badge}</div>
      </div>
      ${state.scoreMode === 'score' && isFiniteNumber(value) ? `<div class="popup-score-track"><div class="popup-score-fill" style="width:${scoreWidth}%"></div></div>` : ''}
    </div>`;
}


function serviceDisplay(v, fallback = 'N/A') {
  if (v == null) return fallback;
  const s = String(v).trim();
  return s ? s : fallback;
}

function servicePopupHtml(props) {
  const closestStop = props.closest_stop_name
    ? `${props.closest_stop_name}${props.closest_stop_dist_m ? ` (${props.closest_stop_dist_m} m)` : ''}`
    : 'N/A';

  const tractPop = props.total_population != null && props.total_population !== ''
    ? Number(props.total_population).toLocaleString()
    : 'N/A';

  return `
    <div class="popup-card service-popup-card">
      <div class="popup-title">${serviceDisplay(props.name, 'Service Location')}</div>
      <div class="service-popup-list">
        <div><strong>Type:</strong> ${serviceDisplay(props.type)}</div>
        <div><strong>Programs:</strong> ${serviceDisplay(props.programs)}</div>
        <div><strong>Address:</strong> ${serviceDisplay(props.address)}</div>
        <div><strong>City:</strong> ${serviceDisplay(props.city)}</div>
        <div><strong>Tract:</strong> ${serviceDisplay(props.tract_geoid)}</div>
        <div><strong>Tract population:</strong> ${tractPop}</div>
        <div><strong>Closest transit stop:</strong> ${closestStop}</div>
        <div><strong>Source:</strong> ${serviceDisplay(props.source, 'services_master')}</div>
      </div>
    </div>
  `;
}

function updateLegendCard() {
  const legendCard = document.querySelector('.legend-card');
  const titleEl = document.querySelector('.legend-title');
  const subtitleEl = document.getElementById('legendSubtitle');
  const scale = document.getElementById('legendScale');
  const labels = document.getElementById('legendLabels');

  if (!hasThematicOverlay()) {
    legendCard?.classList.add('inactive');
    titleEl.textContent = 'Map overlay is off';
    subtitleEl.textContent = 'Turn on YOI Choropleth or Child Opportunity Index in Overlays to restore tract shading.';
    scale.classList.remove('continuous');
    labels.classList.remove('continuous');
    scale.innerHTML = '';
    labels.innerHTML = '';
    return;
  }

  legendCard?.classList.remove('inactive');

  titleEl.textContent = state.showCoiOverlay
    ? (state.scoreMode === 'score' ? 'Child Opportunity Scores' : 'Child Opportunity Levels')
    : (state.scoreMode === 'score' ? 'Youth Opportunity Scores' : 'Youth Opportunity Levels');

  subtitleEl.textContent = state.showCoiOverlay
    ? 'Child Opportunity Index by Census Tract, nationally normalized for 2023'
    : `${activeLayerTitle()} by Census Tract, county-normalized for 2024`;

  if (state.scoreMode === 'score') {
    scale.classList.add('continuous');
    labels.classList.add('continuous');
    scale.innerHTML = '<div class="legend-gradient"></div>';
    labels.innerHTML = currentLegendLabels().map(v => `<div>${v}</div>`).join('');
  } else {
    scale.classList.remove('continuous');
    labels.classList.remove('continuous');
    scale.innerHTML = BLUES.map(() => '<div class="legend-step"></div>').join('');
    labels.innerHTML = currentLegendLabels().map(v => `<div>${v}</div>`).join('');
  }
}


function updateMapStatus() {
  document.getElementById('mapStatusPill').textContent = `${state.rawYoi.length.toLocaleString()} tracts loaded`;
}

function renderMap() {
  if (!state.geojson) return;

  if (tractLayer) tractLayer.remove();
  tractLayer = L.geoJSON(state.geojson, {
    style: styleFeature,
    onEachFeature: (feature, layer) => {
      const geoid = normalizeGeoid(feature.properties.tract_geoid);
      const row = state.tractMap.get(geoid);
      const value = thematicValueForGeoid(geoid, row);
      const tooltipLabel = state.showCoiOverlay ? 'Child Opportunity Index' : activeLayerTitle();
      const tooltipValue = state.scoreMode === 'score'
        ? overlayScoreDisplayValue(value)
        : overlayValueToCategory(value, geoid);

      if (state.showHover) {
        layer.bindTooltip(
          `<strong>${tractLabelFromGeoid(geoid)}</strong><br>${tooltipLabel}: ${tooltipValue}`,
          { sticky: false, opacity: 0.94 }
        );
      }

      layer.on({
        mouseover: e => {
          if (normalizeGeoid(state.selectedGeoid) !== geoid) {
            e.target.setStyle({ color: '#ffffff', weight: 1.8 });
          }
        },
        mouseout: e => {
          tractLayer.resetStyle(e.target);
        },
        click: e => {
          state.selectedGeoid = geoid;
          updateAll(true);

          if (popupRef) popupRef.remove();
          popupRef = L.popup({ closeButton: false, autoPan: false, offset: [0, -4] })
            .setLatLng(e.latlng)
            .setContent(popupHtml(row, geoid))
            .openOn(map);
        },
      });
    },
  }).addTo(map);

  if (routesHaloLayer) routesHaloLayer.remove();
  routesHaloLayer = null;

  if (routesLayer) routesLayer.remove();
  routesLayer = null;

  if (state.showRoutes && state.routesGeojson && featureCount(state.routesGeojson) > 0) {
    routesHaloLayer = L.geoJSON(state.routesGeojson, {
      interactive: false,
      style: {
        color: '#ffffff',
        weight: 7.2,
        opacity: 0.9,
        lineCap: 'round',
        lineJoin: 'round',
      },
    }).addTo(map);

    routesLayer = L.geoJSON(state.routesGeojson, {
      style: {
        color: '#0b5b96',
        weight: 4.4,
        opacity: 0.98,
        lineCap: 'round',
        lineJoin: 'round',
      },
    }).addTo(map);
  }

  if (stopsLayer) stopsLayer.remove();
  stopsLayer = null;
  if (state.showStops && state.stopsGeojson && featureCount(state.stopsGeojson) > 0) {
    stopsLayer = L.geoJSON(state.stopsGeojson, {
      pointToLayer: (_, latlng) => L.circleMarker(latlng, {
        radius: 4,
        weight: 1.4,
        color: '#1e6394',
        fillColor: '#e8f2ff',
        fillOpacity: 0.95,
      }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties || {};
        layer.bindTooltip(String(p.stop_name || p.name || p.stop_id || 'Transit stop'));
      },
    }).addTo(map);
  }

  if (serviceLayer) serviceLayer.remove();
  serviceLayer = null;
  if (state.showServices && state.servicesGeojson && featureCount(state.servicesGeojson) > 0) {
    serviceLayer = L.geoJSON(state.servicesGeojson, {
      pointToLayer: (_, latlng) => L.circleMarker(latlng, {
        radius: 5,
        weight: 2,
        color: '#0b5b96',
        fillColor: '#f59e0b',
        fillOpacity: 0.96,
      }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties || {};

        if (state.showHover && p.name) {
          layer.bindTooltip(String(p.name), {
            direction: 'top',
            offset: [0, -6],
            opacity: 0.96,
          });
        }

        layer.bindPopup(servicePopupHtml(p), {
          closeButton: false,
          autoPan: true,
          offset: [0, -4],
        });
      },
    }).addTo(map);
  }

  if (supervisorDistrictsLayer) supervisorDistrictsLayer.remove();
  supervisorDistrictsLayer = null;
  if (state.showSupervisorDistricts && state.supervisorDistrictsGeojson && featureCount(state.supervisorDistrictsGeojson) > 0) {
    supervisorDistrictsLayer = L.geoJSON(state.supervisorDistrictsGeojson, {
      style: {
        color: '#275c81',
        weight: 2.4,
        opacity: 0.95,
        fillOpacity: 0,
      },
      onEachFeature: (feature, layer) => {
        const p = feature.properties || {};
        const districtNo = p.distno ?? p.DISTNO ?? p.district ?? p.District ?? 'N/A';
        const supervisor = p.supervisor || p.SUPERVISOR || p.name || p.NAME || 'N/A';
        const website = p.website || p.WEBSITE || '';

        if (state.showHover) {
          layer.bindTooltip(`<strong>Supervisor District ${districtNo}</strong><br>${supervisor}`, {
            sticky: false,
            opacity: 0.94,
          });
        }

        layer.bindPopup(`
          <div class="popup-card">
            <div class="popup-title">Supervisor District ${districtNo}</div>
            <div class="service-popup-list">
              <div><strong>Supervisor:</strong> ${supervisor}</div>
              ${p.phone || p.PHONE ? `<div><strong>Phone:</strong> ${p.phone || p.PHONE}</div>` : ''}
              ${website ? `<div><strong>Website:</strong> ${website}</div>` : ''}
            </div>
          </div>
        `, {
          closeButton: false,
          autoPan: true,
          offset: [0, -4],
        });
      },
    }).addTo(map);
  }

  updateLegendCard();
}

function domainRows(row) {
  return DOMAINS.map(d => ({
    key: d,
    label: DOMAIN_LABELS[d],
    score: +row[`${d}_score`] || 0,
    weight: +state.normalizedWeights[d] || 0,
    weighted: (+row[`${d}_score`] || 0) * (+state.normalizedWeights[d] || 0),
  }));
}

function renderLocationDetails() {
  const el = document.getElementById('locationDetails');
  if (!state.selectedGeoid) {
    el.innerHTML = '<div class="helper-text">Select a tract on the map to view detailed information here.</div>';
    return;
  }
  const row = state.tractMap.get(normalizeGeoid(state.selectedGeoid));
  if (!row) {
    el.innerHTML = '<div class="helper-text">Selected tract was not found in the processed CSV.</div>';
    return;
  }

  const popMissing = row.total_population == null;
  const pop = popMissing ? 'N/A' : Number(row.total_population).toLocaleString();
  const { rank, total, percentile } = percentileForRow(row);
  const rows = domainRows(row).sort((a,b)=>b.score-a.score);
  const best = rows[0];
  const worst = rows[rows.length-1];

  el.innerHTML = `
    <div class="location-header">
      <div class="loc-tract">${tractLabelFromGeoid(row.tract_geoid)}</div>
      <div class="loc-sub">San Diego-Chula Vista-Carlsbad, CA</div>
      ${popMissing ? '<div class="warning-badge">Population unavailable</div>' : ''}
    </div>

    <div class="loc-metric-grid">
      <div class="loc-metric"><div class="loc-metric-label">Overall YOI</div><div class="loc-metric-value">${(+row.yoi_custom_0_100).toFixed(1)}</div></div>
      <div class="loc-metric"><div class="loc-metric-label">Population</div><div class="loc-metric-value">${pop}</div></div>
      <div class="loc-metric"><div class="loc-metric-label">Rank</div><div class="loc-metric-value">${rank ? `${rank}/${total}` : 'N/A'}</div></div>
      <div class="loc-metric"><div class="loc-metric-label">Percentile</div><div class="loc-metric-value">${percentile ? `${percentile}th` : 'N/A'}</div></div>
      <div class="loc-metric"><div class="loc-metric-label">Best domain</div><div class="loc-metric-value">${best.label}</div></div>
      <div class="loc-metric"><div class="loc-metric-label">Lowest domain</div><div class="loc-metric-value">${worst.label}</div></div>
    </div>

    <div class="control-label">Child Opportunity Levels and Scores</div>
    <div class="domain-list">
      ${rows.map(d => `
        <div class="domain-row">
          <div class="domain-row-head"><span>${d.label}</span><span>${(d.score * 100).toFixed(0)}/100</span></div>
          <div class="domain-bar"><div class="domain-bar-fill" style="width:${d.score * 100}%"></div></div>
        </div>`).join('')}
    </div>`;
}

function ensureChartTooltip() {
  if (!chartTooltip) chartTooltip = d3.select('body').append('div').attr('class', 'chart-tooltip');
}

function renderProfileChart() {
  const wrap = d3.select('#profileChart');
  wrap.selectAll('*').remove();
  const row = state.selectedGeoid ? state.tractMap.get(normalizeGeoid(state.selectedGeoid)) : null;
  if (!row) {
    wrap.append('div').attr('class', 'helper-text').text('Select a tract on the map to view its weighted domain contribution.');
    return;
  }
  ensureChartTooltip();

  const data = domainRows(row).sort((a,b)=>a.weighted-b.weighted);
  const margin = { top: 10, right: 54, bottom: 26, left: 128 };
  const width = 268;
  const barH = 34;
  const height = margin.top + margin.bottom + data.length * barH;

  const svg = wrap.append('svg').attr('viewBox', `0 0 ${width} ${height}`).style('width', '100%').style('height', 'auto');
  const x = d3.scaleLinear().domain([0, Math.max(d3.max(data, d => d.weighted) || 0.12, 0.12) * 1.15]).range([margin.left, width - margin.right]);
  const y = d3.scaleBand().domain(data.map(d => d.label)).range([margin.top, height - margin.bottom]).padding(0.22);

  svg.append('g')
    .attr('transform', `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(x).ticks(4).tickFormat(d3.format('.2f')))
    .call(g => g.select('.domain').remove())
    .call(g => g.selectAll('text').attr('fill', '#64748b').style('font-size', '11px'))
    .call(g => g.selectAll('line').attr('stroke', 'rgba(148,163,184,0.35)'));

  svg.append('g')
    .attr('transform', `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).tickSize(0))
    .call(g => g.select('.domain').remove())
    .call(g => g.selectAll('text').attr('class', 'bar-label'));

  svg.selectAll('.bar')
    .data(data, d => d.key)
    .join('rect')
    .attr('x', x(0))
    .attr('y', d => y(d.label))
    .attr('height', y.bandwidth())
    .attr('rx', 4)
    .attr('fill', '#5a8bb1')
    .attr('width', 0)
    .transition().duration(350)
    .attr('width', d => x(d.weighted) - x(0));

  svg.selectAll('.bar-hit')
    .data(data, d => d.key)
    .join('rect')
    .attr('x', x(0))
    .attr('y', d => y(d.label))
    .attr('height', y.bandwidth())
    .attr('width', d => Math.max(2, x(d.weighted) - x(0)))
    .attr('fill', 'transparent')
    .style('cursor', 'pointer')
    .on('mousemove', (event, d) => {
      chartTooltip.style('opacity', 1)
        .html(`<strong>${d.label}</strong><br>Raw score: ${(d.score * 100).toFixed(0)}/100<br>Weight: ${(d.weight * 100).toFixed(1)}%<br>Contribution: ${d.weighted.toFixed(3)}`)
        .style('left', `${event.pageX + 12}px`)
        .style('top', `${event.pageY - 28}px`);
    })
    .on('mouseout', () => chartTooltip.style('opacity', 0))
    .on('click', (_, d) => {
      state.mapLayer = `${d.key} score`;
      document.getElementById('mapLayerSelect').value = state.mapLayer;
      updateAll();
    });

  svg.selectAll('.bar-value')
    .data(data)
    .join('text')
    .attr('class', 'bar-value')
    .attr('x', d => x(d.weighted) + 6)
    .attr('y', d => y(d.label) + y.bandwidth()/2 + 4)
    .text(d => d.weighted.toFixed(3));
}

function updateFeatureProperties() {
  if (!state.geojson?.features) return;
  state.geojson.features.forEach(f => {
    const geoid = normalizeGeoid(f.properties?.tract_geoid ?? f.properties?.GEOID ?? f.properties?.geoid);
    f.properties = { ...(f.properties || {}), tract_geoid: geoid };
  });
}

function renderPanelContent() {
  renderLocationDetails();
  renderProfileChart();
}

function setPanel(panelName) {
  state.activePanel = panelName;
  document.querySelectorAll('.rail-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.panel === panelName));
  document.querySelectorAll('.panel-view').forEach(view => view.classList.toggle('active', view.id === `panel-${panelName}`));
  const titleMap = {
    controls: ['Data Controls', 'Adjust the map and comparison view.'],
    overlays: ['Overlays', 'Turn map layers on and off.'],
    profile: ['Domain Profile', 'Weighted domain contribution for the current tract.'],
    location: ['Location Details', 'Inspect the selected census tract in detail.'],
    faqs: ['Frequently asked questions', 'Helpful context for interpreting the dashboard.'],
    share: ['Share', 'Copy the current state of the explorer.'],
  };
  document.getElementById('drawerTitle').textContent = titleMap[panelName][0];
  document.getElementById('drawerSubtitle').textContent = titleMap[panelName][1];
  document.getElementById('drawerPanel').classList.remove('collapsed');
}

function updateTransitAvailabilityNote() {
  const msgs = [];
  if (!state.routesGeojson || featureCount(state.routesGeojson) === 0) msgs.push('Transit routes GeoJSON not found');
  if (!state.stopsGeojson || featureCount(state.stopsGeojson) === 0) msgs.push('Transit stops GeoJSON not found');
  document.getElementById('transitAvailabilityNote').textContent = msgs.length ? `${msgs.join(' · ')}. Run the Python transit export script if needed.` : 'Transit route and stop overlays are available.';
}

function updateAll(reRenderMap = true) {
  recomputeCustomScores();
  updateWeightsUi();
  updateFeatureProperties();
  updateMapStatus();
  syncOverlayControls();
  renderPanelContent();
  if (reRenderMap) renderMap();
  updateLegendCard();
}

function buildLayerSelect() {
  const select = document.getElementById('mapLayerSelect');
  select.innerHTML = ['YOI (0–100)', ...DOMAINS.map(d => `${d} score`)].map(v => `<option value="${v}">${v === 'YOI (0–100)' ? 'Overall Youth Opportunity' : DOMAIN_LABELS[v.replace(/ score$/, '')] + ' Domain'}</option>`).join('');
  select.value = state.mapLayer;
  select.addEventListener('change', e => { state.mapLayer = e.target.value; updateAll(); });
}

function buildWeightSliders() {
  const wrap = document.getElementById('weightSliders');
  wrap.innerHTML = '';
  DOMAINS.forEach(d => {
    const row = document.createElement('div');
    row.className = 'weight-row';
    row.innerHTML = `
      <div class="weight-head"><span>${DOMAIN_LABELS[d]}</span><span id="weight_${d}">14.3%</span></div>
      <input id="slider_${d}" type="range" min="0" max="1" step="0.05" value="1">
    `;
    wrap.appendChild(row);
    row.querySelector('input').addEventListener('input', e => {
      state.rawWeights[d] = +e.target.value;
      updateAll();
    });
  });
  document.getElementById('resetWeights').addEventListener('click', () => {
    DOMAINS.forEach(d => {
      state.rawWeights[d] = 1;
      document.getElementById(`slider_${d}`).value = 1;
    });
    updateAll();
  });
}

function bindControls() {
  document.getElementById('toggleChoro').addEventListener('change', e => {
    state.showChoro = e.target.checked;
    syncOverlayControls();
    updateAll();
  });
  document.getElementById('toggleBounds').addEventListener('change', e => { state.showBounds = e.target.checked; updateAll(); });
  document.getElementById('toggleRoutes').addEventListener('change', e => { state.showRoutes = e.target.checked; updateAll(); });
  document.getElementById('toggleStops').addEventListener('change', e => { state.showStops = e.target.checked; updateAll(); });
  document.getElementById('hoverToggle').addEventListener('change', e => { state.showHover = e.target.checked; updateAll(); });

  document.querySelectorAll('#overlayQuickToggle .seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      setThematicOverlayMode(btn.dataset.overlayMode);
      syncOverlayControls();
      updateAll();
    });
  });
  document.querySelectorAll('#scoreModeGroup .seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#scoreModeGroup .seg-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.scoreMode = btn.dataset.mode;
      updateAll();
    });
  });
  document.querySelectorAll('.rail-btn').forEach(btn => btn.addEventListener('click', () => setPanel(btn.dataset.panel)));
  document.getElementById('closeDrawerBtn').addEventListener('click', () => document.getElementById('drawerPanel').classList.toggle('collapsed'));
  document.querySelectorAll('.faq-btn').forEach(btn => btn.addEventListener('click', () => btn.parentElement.classList.toggle('open')));
  document.getElementById('copyLinkBtn').addEventListener('click', async () => {
    const url = new URL(window.location.href);
    if (state.selectedGeoid) url.searchParams.set('tract', state.selectedGeoid);
    url.searchParams.set('layer', state.mapLayer);
    await navigator.clipboard.writeText(url.toString());
    document.getElementById('shareStatus').textContent = 'Current view link copied.';
  });
  document.getElementById('copySelectedBtn').addEventListener('click', async () => {
    const geoid = state.selectedGeoid || '';
    if (!geoid) {
      document.getElementById('shareStatus').textContent = 'No tract selected yet.';
      return;
    }
    await navigator.clipboard.writeText(geoid);
    document.getElementById('shareStatus').textContent = `Copied ${geoid}.`;
  });
  const searchInput = document.getElementById('searchInput');
  searchInput.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    runSearch();
  });
  searchInput.addEventListener('focus', () => setSearchStatus(''));
  document.querySelector('.search-shell i')?.addEventListener('click', runSearch);
  document.getElementById('toggleCoiOverlay')?.addEventListener('change', e => {
    state.showCoiOverlay = e.target.checked;
    syncOverlayControls();
    updateAll();
  });
  document.getElementById('toggleServices').addEventListener('change', e => {
    state.showServices = e.target.checked;
    updateAll();
  });
  document.getElementById('toggleSupervisorDistricts').addEventListener('change', e => {
    state.showSupervisorDistricts = e.target.checked;
    updateAll();
  });
}

async function loadCsv(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  const text = await res.text();
  const parsed = Papa.parse(text, { header: true, dynamicTyping: false, skipEmptyLines: true }).data;
  return coerceCsvRows(parsed);
}

async function loadJson(path) {
  const res = await fetch(path);
  if (!res.ok) return null;
  return res.json();
}

function initGeojsonProps() {
  if (!state.geojson?.features) return;
  state.geojson.features.forEach(f => {
    const p = f.properties || {};
    p.tract_geoid = normalizeGeoid(p.tract_geoid ?? p.GEOID ?? p.geoid ?? p.Tract ?? p.TRACT);
    f.properties = p;
  });
}

function applyInitialMapView() {
  if (state.hasInitialFit) return;
  if (!tractLayer) return;

  let fitted = false;

  if (state.selectedGeoid) {
    const feature = searchFeature(state.selectedGeoid);
    if (feature) {
      const bounds = L.geoJSON(feature).getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds.pad(0.8), {
          animate: false,
          paddingTopLeft: [390, 110],
          paddingBottomRight: [310, 70],
        });
        fitted = true;
      }
    }
  }

  if (!fitted) {
    const bounds = tractLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, {
  animate: false,
  paddingTopLeft: [400, 50],
  paddingBottomRight: [140, 30],
  maxZoom: 11,
});
      fitted = true;
    }
  }

  if (fitted) {
    state.hasInitialFit = true;

    requestAnimationFrame(() => {
      map.invalidateSize(false);
      requestAnimationFrame(() => {
        map.getContainer().style.opacity = '1';
      });
    });
  }
}

async function init() {
  buildLayerSelect();
  buildWeightSliders();
  bindControls();

  state.rawYoi = await loadCsv('./data/processed/yoi/yoi_components.csv');
  state.meta = await loadCsv('./data/processed/yoi/yoi_indicator_meta.csv').catch(() => []);
  state.geojson = await loadJson('./data/processed/boundaries/sd_tracts.geojson');
  state.routesGeojson = await loadJson('./data/processed/boundaries/transit_routes.geojson').catch(() => null);
  state.stopsGeojson = await loadJson('./data/processed/boundaries/transit_stops.geojson').catch(() => null);
  state.coiRows = await loadCsv('./data/processed/overlays/sd_coi_2023.csv').catch(() => []);
  state.coiMap = new Map(state.coiRows.map(r => [normalizeGeoid(r.tract_geoid), r]));
  state.servicesGeojson = await loadJson('./data/processed/overlays/service_locations.geojson').catch(() => null);
  state.supervisorDistrictsGeojson = await loadJson('./data/processed/overlays/supervisor_districts.geojson').catch(() => null);

  initGeojsonProps();
  updateTransitAvailabilityNote();

  const params = new URLSearchParams(window.location.search);
  const tract = normalizeGeoid(params.get('tract'));
  const layer = params.get('layer');
  if (tract) state.selectedGeoid = tract;
  if (layer && ['YOI (0–100)', ...DOMAINS.map(d => `${d} score`)].includes(layer)) {
    state.mapLayer = layer;
    document.getElementById('mapLayerSelect').value = layer;
  }

  updateAll();
if (state.selectedGeoid) setPanel('location');

requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    map.invalidateSize(false);
    applyInitialMapView();
  });
});
}

init().catch(err => {
  console.error(err);
  document.getElementById('locationDetails').innerHTML = `<div class="callout-note">Failed to load dashboard data: ${err.message}</div>`;
});
