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

const EXCLUDED_TRACT_GEOIDS = new Set(['06073990100']);

// const BLUES = ['#eaf3fb', '#b6d3e9', '#6da3c9', '#275c81', '#0a2f4a'];
const BLUES = ['#B6442C', '#E59A22', '#EEC574', '#7CC6BB', '#2B989E', '#246E7E', '#27373D'];

const WARM_COLORS = ['#B6442C', '#E59A22', '#EEC574'];
const MID_COLORS = ['#EEC574', '#B5C6A8', '#7CC6BB'];
const COOL_COLORS = ['#7CC6BB', '#2B989E', '#246E7E', '#27373D'];

const state = {
  rawYoi: [],
  tractMap: new Map(),
  geojson: null,
  routesGeojson: null,
  stopsGeojson: null,
  zipGeojson: null,
  zipRows: [],
  zipMap: new Map(),
  supervisorDistrictsGeojson: null,
  supervisorDistrictRows: [],
  supervisorDistrictMap: new Map(),
  meta: [],
  selectedGeoid: null,
  activePanel: 'controls',
  mapLayer: 'YOI (0–100)',
  scoreMode: 'score',
  showDataFor: 'tracts',
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
  profileSort: 'desert',
};

let tractLayer = null;
let routesLayer = null;
let stopsLayer = null;
let legendControl = null;
let chartTooltip = null;
let popupRef = null;
let serviceLayer = null;

const ASSISTANT_API_URL = 'https://youth-opportunity-index.onrender.com/api/chat';

function clearTransientUi() {
  if (chartTooltip) chartTooltip.style('opacity', 0);

  if (popupRef) {
    popupRef.remove();
    popupRef = null;
  }
}

const map = L.map('map', { zoomControl: false, preferCanvas: true, attributionControl: true }).setView([32.87, -116.96], 10);

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

map.createPane('routes');
map.getPane('routes').style.zIndex = 640;

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


function normalizeZip(v) {
  if (v == null) return '';
  const digits = String(v).replace(/\D/g, '');
  if (!digits) return '';
  if (digits.length >= 5) return digits.slice(0, 5);
  return digits.padStart(5, '0');
}

function normalizeDistrict(v) {
  if (v == null) return '';
  const digits = String(v).replace(/\D/g, '');
  return digits || String(v).trim();
}

function effectiveShowCoiOverlay() {
  return state.showCoiOverlay && state.showDataFor === 'tracts';
}

function featureTractGeoid(feature) {
  const p = feature?.properties || {};
  return normalizeGeoid(p.tract_geoid ?? p.GEOID ?? p.geoid ?? p.Tract ?? p.TRACT ?? p.GEOIDFQ);
}

function featureZipCode(feature) {
  const p = feature?.properties || {};
  return normalizeZip(p.zip ?? p.ZIP ?? p.zip_code ?? p.ZIPCODE ?? p.ZCTA5CE20 ?? p.GEOID20 ?? p.geoid ?? p.GEOID);
}

function featureSupervisorDistrictKey(feature) {
  const p = feature?.properties || {};
  return normalizeDistrict(p.distno ?? p.DISTNO ?? p.district ?? p.District ?? p.DISTRICT ?? p.id ?? p.ID);
}

function currentFeatureKey(feature) {
  if (state.showDataFor === 'zips') return featureZipCode(feature);
  if (state.showDataFor === 'supervisor_districts') return featureSupervisorDistrictKey(feature);
  return featureTractGeoid(feature);
}

function currentFeatureLabel(key) {
  if (state.showDataFor === 'zips') return `ZIP code ${normalizeZip(key)}`;
  if (state.showDataFor === 'supervisor_districts') return `Supervisor District ${normalizeDistrict(key)}`;
  return tractLabelFromGeoid(key);
}

function currentDataMap() {
  if (state.showDataFor === 'zips') return state.zipMap;
  if (state.showDataFor === 'supervisor_districts') return state.supervisorDistrictMap;
  return state.tractMap;
}

function currentRows() {
  if (state.showDataFor === 'zips') return state.zipRows;
  if (state.showDataFor === 'supervisor_districts') return state.supervisorDistrictRows;
  return state.rawYoi;
}

function currentIdForRow(row) {
  if (!row) return '';
  if (state.showDataFor === 'zips') return normalizeZip(row.zip ?? row.ZIP ?? row.zcta ?? row.zip_code);
  if (state.showDataFor === 'supervisor_districts') return normalizeDistrict(row.distno ?? row.DISTNO ?? row.district ?? row.District ?? row.supervisor_district ?? row.id ?? row.ID);
  return normalizeGeoid(row.tract_geoid);
}

function currentFeatureCollection() {
  if (state.showDataFor === 'zips') return state.zipGeojson;
  if (state.showDataFor === 'supervisor_districts') return state.supervisorDistrictsGeojson;
  return state.geojson;
}

function currentAreaLabelPlural() {
  if (state.showDataFor === 'zips') return 'ZIP codes';
  if (state.showDataFor === 'supervisor_districts') return 'supervisor districts';
  return 'tracts';
}

function isFiniteNumber(v) {
  if (v === null || v === undefined) return false;
  if (typeof v === 'string' && v.trim() === '') return false;
  return Number.isFinite(Number(v));
}

function coerceCsvRows(rows) {
  return rows.map(row => {
    const out = {};
    Object.entries(row).forEach(([k, v]) => {
      if (k === 'tract_geoid') out[k] = normalizeGeoid(v);
      else if (k.toLowerCase() === 'zip' || k.toLowerCase() === 'zip_code' || k.toLowerCase() === 'zcta') out[k] = normalizeZip(v);
      else if (['distno','district','supervisor_district','id'].includes(k.toLowerCase())) out[k] = normalizeDistrict(v);
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
  const mid = min + (max - min) * 0.5;

  return [
    min + (mid - min) * (1 / 3),
    min + (mid - min) * (2 / 3),
    mid,
    mid + (max - mid) * (1 / 4),
    mid + (max - mid) * (2 / 4),
    mid + (max - mid) * (3 / 4),
  ];
}

function currentBins() {
  return levelBins();
}

function currentLegendLabels() {
  if (state.scoreMode === 'score') {
    return ['0', '20', '40', '60', '80', '100'];
  }
  return ['Very Low', 'Low', 'Low-Mid', 'Moderate', 'Mid-High', 'High', 'Very High'];
}

function valueToCategory(v) {
  if (!isFiniteNumber(v)) return 'N/A';
  const bins = levelBins();
  const labels = currentLegendLabels();

  for (let i = 0; i < bins.length; i++) {
    if (v < bins[i]) return labels[i];
  }

  return labels[labels.length - 1];
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

function searchModeMeta() {
  if (state.showDataFor === 'zips') {
    return {
      placeholder: 'Search ZIP code',
      helper: 'Start typing a ZIP code to see matching options.',
      emptyZoomMessage: 'Zoomed to selected ZIP code.',
      notFound: 'No matching ZIP code found.'
    };
  }

  if (state.showDataFor === 'supervisor_districts') {
    return {
      placeholder: 'Search supervisor district',
      helper: 'Start typing a district number to see matching options.',
      emptyZoomMessage: 'Zoomed to selected supervisor district.',
      notFound: 'No matching supervisor district found.'
    };
  }

  return {
    placeholder: 'Search census tract',
    helper: 'Start typing a tract number or GEOID to see matching options.',
    emptyZoomMessage: 'Zoomed to selected tract.',
    notFound: 'No matching census tract found. Try a tract number like 20.00 or an 11-digit GEOID.'
  };
}

function searchTokensForFeature(key, label) {
  if (state.showDataFor === 'zips') {
    const zip = normalizeZip(key);
    return {
      text: [label, zip, label.replace(/^ZIP code\s+/i, '')].filter(Boolean),
      digits: [zip]
    };
  }

  if (state.showDataFor === 'supervisor_districts') {
    const district = normalizeDistrict(key);
    return {
      text: [label, district, label.replace(/^Supervisor District\s+/i, '')].filter(Boolean),
      digits: [district]
    };
  }

  const geoid = normalizeGeoid(key);
  const tractSuffix = tractSuffixFromGeoid(geoid);
  const tractDisplay = tractLabelFromGeoid(geoid).replace(/^Census tract\s+/i, '');

  return {
    text: [label, geoid, tractDisplay, tractSuffix].filter(Boolean),
    digits: [geoid, tractSuffix]
  };
}

function currentSearchCandidates() {
  const features = currentFeatureCollection()?.features || [];

  return features
    .map(feature => {
      const key = currentFeatureKey(feature);
      if (!key) return null;

      const label = currentFeatureLabel(key);
      const tokens = searchTokensForFeature(key, label);

      return {
        feature,
        key,
        label,
        text: tokens.text,
        digits: tokens.digits
      };
    })
    .filter(Boolean);
}

function matchPriority(candidate, query) {
  const lowered = String(query || '').trim().toLowerCase();
  const digits = String(query || '').replace(/\D/g, '');

  if (!lowered && !digits) return 0;

  if (
    candidate.text.some(token => String(token).toLowerCase() === lowered) ||
    (digits && candidate.digits.some(token => token === digits))
  ) {
    return 0;
  }

  if (
    candidate.text.some(token => String(token).toLowerCase().startsWith(lowered)) ||
    (digits && candidate.digits.some(token => token.startsWith(digits)))
  ) {
    return 1;
  }

  if (
    candidate.text.some(token => String(token).toLowerCase().includes(lowered)) ||
    (digits && candidate.digits.some(token => token.includes(digits)))
  ) {
    return 2;
  }

  return Number.POSITIVE_INFINITY;
}

function searchCandidates(query = '') {
  const lowered = String(query || '').trim().toLowerCase();
  const digits = String(query || '').replace(/\D/g, '');

  return currentSearchCandidates()
    .filter(candidate => {
      if (!lowered && !digits) return true;

      return (
        candidate.text.some(token => String(token).toLowerCase().includes(lowered)) ||
        (digits && candidate.digits.some(token => token.includes(digits)))
      );
    })
    .sort((a, b) => {
      const scoreA = matchPriority(a, query);
      const scoreB = matchPriority(b, query);

      if (scoreA !== scoreB) return scoreA - scoreB;
      return a.label.localeCompare(b.label, undefined, { numeric: true });
    });
}

function searchFeature(query) {
  const trimmed = String(query || '').trim();
  if (!trimmed) return null;
  return searchCandidates(trimmed)[0] || null;
}

function updateSearchSuggestions(query = '') {
  const datalist = document.getElementById('searchSuggestions');
  if (!datalist) return;

  datalist.innerHTML = '';

  searchCandidates(query).slice(0, 25).forEach(candidate => {
    const option = document.createElement('option');
    option.value = candidate.label;
    option.label = candidate.key;
    datalist.appendChild(option);
  });
}

function updateSearchUi() {
  const input = document.getElementById('searchInput');
  const helper = document.getElementById('searchHelperText');
  const meta = searchModeMeta();

  if (input) {
    input.placeholder = meta.placeholder;
    updateSearchSuggestions(input.value);
  }

  if (helper) {
    helper.textContent = meta.helper;
  }
}

function setSearchStatus(message, isError = false) {
  const input = document.getElementById('searchInput');
  if (!input) return;
  input.setCustomValidity(isError ? message : '');
  input.title = message || '';
  if (isError && typeof input.reportValidity === 'function') input.reportValidity();
}

function setRailSearchOpen(isOpen) {
  const flyout = document.getElementById('railSearchFlyout');
  if (!flyout) return;

  flyout.classList.toggle('open', isOpen);

  if (isOpen) {
    requestAnimationFrame(() => {
      document.getElementById('searchInput')?.focus();
    });
  }
}

function runSearch() {
  const input = document.getElementById('searchInput');
  if (!input) return;

  const query = input.value;
  const meta = searchModeMeta();

  if (!String(query || '').trim()) {
    if (state.selectedGeoid) {
      const match = searchFeature(state.selectedGeoid);
      if (match) {
        map.fitBounds(L.geoJSON(match.feature).getBounds().pad(0.8));
        setSearchStatus(meta.emptyZoomMessage);
      }
    }
    return;
  }

  const match = searchFeature(query);
  if (!match) {
    setSearchStatus(meta.notFound, true);
    return;
  }

  const { feature, key, label } = match;

  state.selectedGeoid = key;
  updateAll(true);
  setPanel('location');
  map.fitBounds(L.geoJSON(feature).getBounds().pad(0.8));
  setSearchStatus(`Found ${label}.`);

  input.value = label;
  updateSearchSuggestions(label);

  const row = currentDataMap().get(key);
  if (popupRef) popupRef.remove();
  popupRef = L.popup({ closeButton: false, autoPan: false, offset: [0, -4] })
    .setLatLng(L.geoJSON(feature).getBounds().getCenter())
    .setContent(popupHtml(row, key))
    .openOn(map);
}

// function geoidFromSearchQuery(query) {
//   const raw = String(query || '').trim();
//   if (!raw) return '';

//   const digits = raw.replace(/\D/g, '');
//   if (!digits) return '';

//   if (digits.length >= 11) return normalizeGeoid(digits);

//   if (digits.length <= 6) return '';

//   // tract-only search like 20801 or 208.01 -> county tract GEOID suffix
//   const tractSuffix = digits.padStart(6, '0').slice(-6);
//   return `06073${tractSuffix}`;
// }

// function searchFeature(query) {
//   const geoFeatures = state.geojson?.features || [];
//   if (!geoFeatures.length) return null;

//   const normalized = geoidFromSearchQuery(query);
//   if (normalized) {
//     const exact = geoFeatures.find(f => normalizeGeoid(f.properties?.tract_geoid) === normalized);
//     if (exact) return exact;

//     const suffix = tractSuffixFromGeoid(normalized);
//     const suffixMatch = geoFeatures.find(f => tractSuffixFromGeoid(f.properties?.tract_geoid) === suffix);
//     if (suffixMatch) return suffixMatch;
//   }

//   const lowered = String(query || '').trim().toLowerCase();
//   if (!lowered) return null;

//   return geoFeatures.find(f => tractLabelFromGeoid(f.properties?.tract_geoid).toLowerCase().includes(lowered));
// }

// function setSearchStatus(message, isError = false) {
//   const input = document.getElementById('searchInput');
//   if (!input) return;
//   input.setCustomValidity(isError ? message : '');
//   input.title = message || '';
//   if (isError && typeof input.reportValidity === 'function') input.reportValidity();
// }

// function setRailSearchOpen(isOpen) {
//   const flyout = document.getElementById('railSearchFlyout');
//   if (!flyout) return;

//   flyout.classList.toggle('open', isOpen);

//   if (isOpen) {
//     requestAnimationFrame(() => {
//       document.getElementById('searchInput')?.focus();
//     });
//   }
// }

// function runSearch() {
//   const input = document.getElementById('searchInput');
//   if (!input) return;
//   const query = input.value;

//   if (!String(query || '').trim()) {
//     if (state.selectedGeoid) {
//       const feature = searchFeature(state.selectedGeoid);
//       if (feature) {
//         map.fitBounds(L.geoJSON(feature).getBounds().pad(0.8));
//         setSearchStatus('Zoomed to selected tract.');
//       }
//     }
//     return;
//   }

//   const feature = searchFeature(query);
//   if (!feature) {
//     setSearchStatus('No matching tract found. Try an 11-digit GEOID or tract number like 208.01.', true);
//     return;
//   }

//   const geoid = normalizeGeoid(feature.properties?.tract_geoid);
//   state.selectedGeoid = geoid;
//   updateAll(true);
//   setPanel('location');
//   map.fitBounds(L.geoJSON(feature).getBounds().pad(0.8));
//   setSearchStatus(`Found ${tractLabelFromGeoid(geoid)}.`);

//   const row = state.tractMap.get(geoid);
//   if (popupRef) popupRef.remove();
//   popupRef = L.popup({ closeButton: false, autoPan: false, offset: [0, -4] })
//     .setLatLng(L.geoJSON(feature).getBounds().getCenter())
//     .setContent(popupHtml(row, geoid))
//     .openOn(map);
// }

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

  const applyCustomScore = row => {
    let total = 0;
    let hasDomainScore = false;

    DOMAINS.forEach(d => {
      const score = +row[`${d}_score`];
      if (Number.isFinite(score)) {
        total += score * state.normalizedWeights[d];
        hasDomainScore = true;
      }
    });

    if (hasDomainScore) {
      row.yoi_custom_0_1 = total;
      row.yoi_custom_0_100 = total * 100;
    } else {
      if (isFiniteNumber(row.yoi_0_100)) row.yoi_custom_0_100 = +row.yoi_0_100;
      if (isFiniteNumber(row.yoi_raw_0_1)) row.yoi_custom_0_1 = +row.yoi_raw_0_1;
      else if (isFiniteNumber(row.yoi_custom_0_100)) row.yoi_custom_0_1 = +row.yoi_custom_0_100 / 100;
    }
  };

  state.rawYoi.forEach(applyCustomScore);
  state.zipRows.forEach(applyCustomScore);
  state.supervisorDistrictRows.forEach(applyCustomScore);

  state.tractMap = new Map(
    state.rawYoi.map(r => [normalizeGeoid(r.tract_geoid), r])
  );

  state.zipMap = new Map(
    state.zipRows.map(r => [normalizeZip(r.zip ?? r.ZIP ?? r.zcta ?? r.zip_code), r])
  );

  state.supervisorDistrictMap = new Map(
    state.supervisorDistrictRows.map(r => [
      normalizeDistrict(r.distno ?? r.DISTNO ?? r.district ?? r.District ?? r.supervisor_district ?? r.id ?? r.ID),
      r
    ])
  );
}

function percentileForRow(row) {
  const rows = currentRows();
  const ranked = [...rows].sort((a, b) => (+b.yoi_custom_0_100 || 0) - (+a.yoi_custom_0_100 || 0));
  const selectedId = currentIdForRow(row);
  const idx = ranked.findIndex(r => currentIdForRow(r) === selectedId);
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

function colorForValue(v) {
  if (!isFiniteNumber(v)) return '#eef2f7';

  if (state.scoreMode === 'score') {
    const [min, max] = metricDomain();
    const t = Math.max(0, Math.min(1, (v - min) / (max - min || 1)));

    if (t <= 0.45) {
      return d3.interpolateRgbBasis(WARM_COLORS)(t / 0.45);
    }

    if (t <= 0.55) {
      return d3.interpolateRgbBasis(MID_COLORS)((t - 0.45) / 0.10);
    }

    return d3.interpolateRgbBasis(COOL_COLORS)((t - 0.55) / 0.45);
  }

  const bins = levelBins();
  for (let i = 0; i < bins.length; i++) {
    if (v < bins[i]) return BLUES[i];
  }

  return BLUES[BLUES.length - 1];
}

function styleFeature(feature) {
  const featureKey = currentFeatureKey(feature);
  const row = currentDataMap().get(featureKey);
  const value = effectiveShowCoiOverlay() ? currentCoiValue(featureKey) : currentValue(row);
  const selectedKey = state.showDataFor === 'zips'
    ? normalizeZip(state.selectedGeoid)
    : state.showDataFor === 'supervisor_districts'
      ? normalizeDistrict(state.selectedGeoid)
      : normalizeGeoid(state.selectedGeoid);
  const isSelected = featureKey === selectedKey;

  const showFill =
    effectiveShowCoiOverlay() ||
    state.mapLayer !== 'YOI (0–100)' ||
    state.showDataFor !== 'tracts' ||
    state.showChoro;

  return {
    color: isSelected ? '#ffffff' : (state.showBounds ? 'rgba(27,51,75,0.34)' : 'transparent'),
    weight: isSelected ? 3.2 : (state.showBounds ? 0.6 : 0),
    fillColor: showFill ? colorForValue(value) : '#ffffff',
    fillOpacity: showFill ? 0.92 : 0.02,
  };
}

function popupHtml(row, geoid) {
  const value = effectiveShowCoiOverlay() ? currentCoiValue(geoid) : currentValue(row);
  const badge = effectiveShowCoiOverlay()
    ? (state.scoreMode === 'score' ? `${Math.round(value)}/100` : currentCoiCategory(geoid))
    : (state.scoreMode === 'score' ? scoreDisplayValue(value) : valueToCategory(value));
  return `
    <div class="popup-card">
      <div class="popup-title">${currentFeatureLabel(geoid)}</div>
      <div class="popup-subtitle">San Diego County, CA</div>
      <div class="popup-note">Click ${state.showDataFor === 'zips' ? 'ZIP code' : state.showDataFor === 'supervisor_districts' ? 'supervisor district' : 'census tract'} for details</div>
      <div class="popup-divider"></div>
      <div class="popup-row">
        <div>
          <div class="popup-label">${effectiveShowCoiOverlay() ? 'Child Opportunity Index' : (state.mapLayer === 'YOI (0–100)' ? 'Overall index' : activeLayerTitle())}</div>
          <div class="popup-context">${effectiveShowCoiOverlay() ? 'Compared to nation' : 'Compared to county'}</div>
        </div>
        <div class="popup-badge ${state.scoreMode === 'score' ? 'score-badge' : ''}">${badge}</div>
      </div>
      ${state.scoreMode === 'score' && isFiniteNumber(value) ? `<div class="popup-score-track"><div class="popup-score-fill" style="width:${state.mapLayer === 'YOI (0–100)' ? Math.max(0, Math.min(100, value)) : Math.max(0, Math.min(100, value * 100))}%"></div></div>` : ''}
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
  const titleEl = document.querySelector('.legend-title');
  const subtitleEl = document.getElementById('legendSubtitle');
  const scale = document.getElementById('legendScale');
  const labels = document.getElementById('legendLabels');

  titleEl.textContent = effectiveShowCoiOverlay()
  ? (state.scoreMode === 'score' ? 'Child Opportunity Scores' : 'Child Opportunity Levels')
  : (state.scoreMode === 'score' ? 'Youth Opportunity Scores' : 'Youth Opportunity Levels');

  const areaLabel = state.showDataFor === 'zips' ? 'ZIP Code' : state.showDataFor === 'supervisor_districts' ? 'Supervisor District' : 'Census Tract';
  subtitleEl.textContent = effectiveShowCoiOverlay()
    ? 'Child Opportunity Index by Census Tract, nationally normalized for 2023'
    : `${activeLayerTitle()} by ${areaLabel}, county-normalized for 2024`;

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
  const count = state.showDataFor === 'zips' ? state.zipRows.length : state.showDataFor === 'supervisor_districts' ? state.supervisorDistrictRows.length : state.rawYoi.length;
  const noun = state.showDataFor === 'zips' ? 'ZIP codes' : state.showDataFor === 'supervisor_districts' ? 'supervisor districts' : 'tracts';
  document.getElementById('mapStatusPill').textContent = `${count.toLocaleString()} ${noun} loaded`;
}

function renderMap() {
  const activeGeojson = currentFeatureCollection();
  if (!activeGeojson) return;

  if (tractLayer) tractLayer.remove();
  tractLayer = L.geoJSON(activeGeojson, {
    style: styleFeature,
    onEachFeature: (feature, layer) => {
      const featureKey = currentFeatureKey(feature);
      const row = currentDataMap().get(featureKey);
      const valueText = state.scoreMode === 'score' ? scoreDisplayValue(currentValue(row)) : valueToCategory(currentValue(row));

      if (state.showHover) {
        layer.bindTooltip(`<strong>${currentFeatureLabel(featureKey)}</strong><br>${activeLayerTitle()}: ${valueText}`, { sticky: false, opacity: 0.94 });
      }

      layer.on({
        mouseover: e => {
          const selectedKey = state.showDataFor === 'zips'
            ? normalizeZip(state.selectedGeoid)
            : state.showDataFor === 'supervisor_districts'
              ? normalizeDistrict(state.selectedGeoid)
              : normalizeGeoid(state.selectedGeoid);
          if (selectedKey !== featureKey) {
            e.target.setStyle({ color: '#ffffff', weight: 1.8 });
          }
        },
        mouseout: e => {
          tractLayer.resetStyle(e.target);
        },
                click: e => {
          state.selectedGeoid = featureKey;
          updateAll(true);

          if (state.showDataFor === 'tracts') {
            setPanel('location');
          }

          if (popupRef) popupRef.remove();
          popupRef = L.popup({ closeButton: false, autoPan: false, offset: [0, -4] })
            .setLatLng(e.latlng)
            .setContent(popupHtml(row, featureKey))
            .openOn(map);
        },
      });
    },
  }).addTo(map);

  if (routesLayer) routesLayer.remove();
routesLayer = null;

if (state.showRoutes && state.routesGeojson && featureCount(state.routesGeojson) > 0) {
  const routeOutlineLayer = L.geoJSON(state.routesGeojson, {
  style: () => ({
    color: 'rgba(255, 255, 255, 0.88)',
    weight: 5.4,
    opacity: 1,
    lineCap: 'round',
    lineJoin: 'round',
  }),
  interactive: false,
});

const routeCenterLayer = L.geoJSON(state.routesGeojson, {
  style: () => ({
    color: '#3B828D',
    weight: 2.8,
    opacity: 0.98,
    lineCap: 'round',
    lineJoin: 'round',
  }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {};
      const label =
        p.route_name ||
        p.route_short_name ||
        p.route_long_name ||
        p.route_id ||
        p.name ||
        'Transit route';

      if (state.showHover) {
        layer.bindTooltip(String(label), {
          sticky: true,
          opacity: 0.96,
        });
      }

      layer.on({
        mouseover: e => {
          e.target.setStyle({
            weight: 4.2,
            opacity: 1,
          });
        },
        mouseout: e => {
          routeCenterLayer.resetStyle(e.target);
        },
      });
    },
  });

  routesLayer = L.layerGroup([routeOutlineLayer, routeCenterLayer]).addTo(map);
}

  if (stopsLayer) stopsLayer.remove();
  stopsLayer = null;
  if (state.showStops && state.stopsGeojson && featureCount(state.stopsGeojson) > 0) {
    stopsLayer = L.geoJSON(state.stopsGeojson, {
      pointToLayer: (_, latlng) => L.circleMarker(latlng, {
  radius: 4,
  weight: 1.4,
  color: '#143a3d',
  fillColor: '#2B989E',
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
  color: '#0B151C',
  fillColor: '#D9A95D',
  fillOpacity: 0.94,
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

function scoreOutOf100(v) {
  if (!isFiniteNumber(v)) return 'N/A';
  return `${Math.round(+v * 100)}/100`;
}

function meanValue(values) {
  if (!values.length) return NaN;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

function medianValue(sortedValues) {
  if (!sortedValues.length) return NaN;
  const mid = Math.floor(sortedValues.length / 2);
  return sortedValues.length % 2
    ? sortedValues[mid]
    : (sortedValues[mid - 1] + sortedValues[mid]) / 2;
}

function domainDistributionStats(domainKey) {
  const values = currentRows()
    .map(r => +r[`${domainKey}_score`])
    .filter(v => Number.isFinite(v))
    .sort((a, b) => a - b);

  if (!values.length) {
    return { min: NaN, median: NaN, mean: NaN, max: NaN };
  }

  return {
    min: values[0],
    median: medianValue(values),
    mean: meanValue(values),
    max: values[values.length - 1],
  };
}

function quantileSorted(sortedValues, q) {
  if (!sortedValues.length) return NaN;
  const pos = (sortedValues.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  if (sortedValues[base + 1] !== undefined) {
    return sortedValues[base] + rest * (sortedValues[base + 1] - sortedValues[base]);
  }
  return sortedValues[base];
}

function ordinalSuffix(n) {
  if (!Number.isFinite(+n)) return 'N/A';
  const v = Math.round(+n);
  const mod10 = v % 10;
  const mod100 = v % 100;
  if (mod10 === 1 && mod100 !== 11) return `${v}st`;
  if (mod10 === 2 && mod100 !== 12) return `${v}nd`;
  if (mod10 === 3 && mod100 !== 13) return `${v}rd`;
  return `${v}th`;
}

function domainProfileStats(domainKey, selectedScore) {
  const values = currentRows()
    .map(r => +r[`${domainKey}_score`])
    .filter(v => Number.isFinite(v))
    .sort((a, b) => a - b);

  if (!values.length) {
    return {
      total: 0,
      rank: null,
      percentile: null,
      min: NaN,
      q1: NaN,
      median: NaN,
      mean: NaN,
      q3: NaN,
      max: NaN,
      signedGap: NaN,
      deficit: NaN,
    };
  }

  const total = values.length;
  const rank = values.filter(v => v > selectedScore).length + 1;
  const percentile = Math.round((values.filter(v => v <= selectedScore).length / total) * 100);
  const min = values[0];
  const q1 = quantileSorted(values, 0.25);
  const median = medianValue(values);
  const mean = meanValue(values);
  const q3 = quantileSorted(values, 0.75);
  const max = values[values.length - 1];
  const signedGap = selectedScore - median;
  const deficit = Math.max(0, median - selectedScore);

  return {
    total,
    rank,
    percentile,
    min,
    q1,
    median,
    mean,
    q3,
    max,
    signedGap,
    deficit,
  };
}

function profileBadgeForDomain(stats) {
  if (!Number.isFinite(stats.percentile)) {
    return { label: 'No data', tone: 'neutral' };
  }

  if (stats.percentile <= 20 || stats.deficit >= 0.18) {
    return { label: 'Primary driver', tone: 'driver' };
  }

  if (stats.percentile <= 40 || stats.deficit >= 0.08) {
    return { label: 'Secondary gap', tone: 'watch' };
  }

  if (stats.percentile >= 75) {
    return { label: 'Relative strength', tone: 'strength' };
  }

  return { label: 'Near county avg', tone: 'neutral' };
}

function buildProfileSummaryText(domainData) {
  const drivers = [...domainData]
    .sort((a, b) => b.deficit - a.deficit)
    .filter(d => d.deficit > 0.001)
    .slice(0, 3);

  const belowMedianCount = domainData.filter(d => d.signedGap < 0).length;
  const pattern =
    belowMedianCount >= 5
      ? 'broad desert pattern'
      : belowMedianCount >= 3
        ? 'mixed opportunity gaps'
        : belowMedianCount >= 1
          ? 'targeted domain gap'
          : 'relative county strength';

  if (!drivers.length) {
    return `This area shows ${pattern} and is at or above the county median across all domains.`;
  }

  return `This area shows a ${pattern}. The largest county-relative deficits are in ${drivers.map(d => d.label).join(', ')}.`;
}

function formatIndicatorDisplayName(name) {
  return String(name || '')
    .replace(/^norm_/, '')
    .replace(/_/g, ' ')
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase());
}

function buildDomainBreakdownMarkup(row, domainKey) {
  const boolFromMeta = value => String(value).toLowerCase() === 'true';

  const formatRawValue = value => {
    if (!isFiniteNumber(value)) return 'N/A';
    const n = +value;

    if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (Math.abs(n) >= 100) return n.toFixed(1).replace(/\.0$/, '');
    if (Math.abs(n) >= 10) return n.toFixed(1).replace(/\.0$/, '');
    if (Math.abs(n) >= 1) return n.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
    return n.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
  };

  const countyAverageForCol = col => {
    const rows = (state.rawYoi || [])
      .map(r => ({ value: +r[col], weight: +r.total_population }))
      .filter(d => Number.isFinite(d.value));

    if (!rows.length) return NaN;

    const weighted = rows.filter(d => Number.isFinite(d.weight) && d.weight > 0);
    const totalWeight = weighted.reduce((sum, d) => sum + d.weight, 0);

    if (weighted.length && totalWeight > 0) {
      return weighted.reduce((sum, d) => sum + d.value * d.weight, 0) / totalWeight;
    }

    return rows.reduce((sum, d) => sum + d.value, 0) / rows.length;
  };

  const metaRows = (state.meta || []).filter(m => m.domain === domainKey);
  const d = domainRows(row).find(x => x.key === domainKey);
  if (!d) return '';

  const stats = domainDistributionStats(d.key);
  const countyDomainMean = countyAverageForCol(`${d.key}_score`);

  const availableNormIndicators = metaRows.filter(m => isFiniteNumber(row[`norm_${m.indicator}`]));
  const divisor = availableNormIndicators.length || metaRows.length || 1;

  const hasIndicatorValues = metaRows.some(m =>
    Object.prototype.hasOwnProperty.call(row, m.indicator) ||
    Object.prototype.hasOwnProperty.call(row, `norm_${m.indicator}`)
  );

  const indicatorMarkup = hasIndicatorValues
    ? metaRows.map(m => {
        const rawCol = m.indicator;
        const normCol = `norm_${m.indicator}`;

        const selectedRaw = row[rawCol];
        const countyRaw = countyAverageForCol(rawCol);
        const selectedNorm = +row[normCol];
        const displayName = formatIndicatorDisplayName(m.indicator);

        const influenceOnDomain = isFiniteNumber(selectedNorm) ? selectedNorm / divisor : NaN;
        const influenceOnOverall = isFiniteNumber(influenceOnDomain)
          ? influenceOnDomain * (+state.normalizedWeights[d.key] || 0)
          : NaN;

        return `
          <div class="indicator-row">
            <div class="indicator-row-top">
              <div>
                <div class="indicator-name">${displayName}</div>
                <div class="indicator-direction">${boolFromMeta(m.higher_is_better) ? 'Higher is better' : 'Lower is better'}</div>
              </div>
              <div class="indicator-chip">${isFiniteNumber(selectedNorm) ? scoreOutOf100(selectedNorm) : 'N/A'}</div>
            </div>

            <div class="indicator-grid">
              <div class="indicator-stat">
                <span>Selected value</span>
                <strong>${formatRawValue(selectedRaw)}</strong>
              </div>

              <div class="indicator-stat">
                <span>County avg</span>
                <strong>${formatRawValue(countyRaw)}</strong>
              </div>

              <div class="indicator-stat">
                <span>Influence on domain</span>
                <strong>${isFiniteNumber(influenceOnDomain) ? influenceOnDomain.toFixed(3) : 'N/A'}</strong>
              </div>

              <div class="indicator-stat">
                <span>Influence on overall</span>
                <strong>${isFiniteNumber(influenceOnOverall) ? influenceOnOverall.toFixed(3) : 'N/A'}</strong>
              </div>
            </div>

            <div class="indicator-source-line">
              <span>Source</span>
              <strong>${m.source || 'N/A'}</strong>
            </div>

            <div class="indicator-note">${m.notes || 'No source note available.'}</div>
          </div>
        `;
      }).join('')
    : `
        <div class="callout-note">
          Indicator-level values are not in the current processed CSV for this geography yet.
        </div>
      `;

  return `
    <div class="profile-breakdown-shell">
      <div class="domain-overview-grid">
        <div class="domain-overview-stat">
          <span>Selected domain score</span>
          <strong>${scoreOutOf100(d.score)}</strong>
        </div>

        <div class="domain-overview-stat">
          <span>County avg</span>
          <strong>${scoreOutOf100(countyDomainMean)}</strong>
        </div>

        <div class="domain-overview-stat">
          <span>Gap vs median</span>
          <strong>${Number.isFinite(stats.median) ? `${d.score - stats.median >= 0 ? '+' : ''}${Math.round((d.score - stats.median) * 100)}` : 'N/A'}</strong>
        </div>

        <div class="domain-overview-stat">
          <span>Contribution to overall</span>
          <strong>${d.weighted.toFixed(3)}</strong>
        </div>
      </div>

      <div class="domain-overview-note">
        This domain score is the mean of the normalized indicators available for this domain.
        Its contribution to the overall YOI equals domain score × current domain weight.
      </div>

      <div class="indicator-breakdown-title">Indicators used in this domain</div>
      <div class="indicator-breakdown">
        ${indicatorMarkup}
      </div>
    </div>
  `;
}

function renderLocationDetails() {
  const el = document.getElementById('locationDetails');

  if (!state.selectedGeoid) {
    el.innerHTML = `<div class="helper-text">Select a ${state.showDataFor === 'zips' ? 'ZIP code' : state.showDataFor === 'supervisor_districts' ? 'supervisor district' : 'tract'} on the map to view detailed information here.</div>`;
    return;
  }

  const row = currentDataMap().get(
    state.showDataFor === 'zips'
      ? normalizeZip(state.selectedGeoid)
      : state.showDataFor === 'supervisor_districts'
        ? normalizeDistrict(state.selectedGeoid)
        : normalizeGeoid(state.selectedGeoid)
  );

  if (!row) {
    el.innerHTML = `<div class="helper-text">Selected ${state.showDataFor === 'zips' ? 'ZIP code' : state.showDataFor === 'supervisor_districts' ? 'supervisor district' : 'tract'} was not found in the processed CSV.</div>`;
    return;
  }

  const areaLabel = currentFeatureLabel(currentIdForRow(row));
  const popMissing = row.total_population == null;
  const pop = popMissing ? 'N/A' : Number(row.total_population).toLocaleString();
  const { rank, total, percentile } = percentileForRow(row);

  const domainData = domainRows(row).sort((a, b) => b.score - a.score);
  const best = domainData[0];
  const worst = domainData[domainData.length - 1];

  const boolFromMeta = value => String(value).toLowerCase() === 'true';

  const formatRawValue = value => {
    if (!isFiniteNumber(value)) return 'N/A';
    const n = +value;

    if (Math.abs(n) >= 1000) {
      return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    if (Math.abs(n) >= 100) {
      return n.toFixed(1).replace(/\.0$/, '');
    }
    if (Math.abs(n) >= 10) {
      return n.toFixed(1).replace(/\.0$/, '');
    }
    if (Math.abs(n) >= 1) {
      return n.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
    }
    return n.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
  };

  const countyAverageForCol = col => {
    const rows = (state.rawYoi || [])
      .map(r => ({ value: +r[col], weight: +r.total_population }))
      .filter(d => Number.isFinite(d.value));

    if (!rows.length) return NaN;

    const weighted = rows.filter(d => Number.isFinite(d.weight) && d.weight > 0);
    const totalWeight = weighted.reduce((sum, d) => sum + d.weight, 0);

    if (weighted.length && totalWeight > 0) {
      return weighted.reduce((sum, d) => sum + d.value * d.weight, 0) / totalWeight;
    }

    return rows.reduce((sum, d) => sum + d.value, 0) / rows.length;
  };

  const metaForDomain = domainKey => (state.meta || []).filter(m => m.domain === domainKey);

  const domainMarkup = domainData.map((d, idx) => {
    const stats = domainDistributionStats(d.key);
    const countyDomainMean = countyAverageForCol(`${d.key}_score`);
    const metaRows = metaForDomain(d.key);

    const availableNormIndicators = metaRows.filter(m => isFiniteNumber(row[`norm_${m.indicator}`]));
    const divisor = availableNormIndicators.length || metaRows.length || 1;

    const hasIndicatorValues = metaRows.some(m =>
      Object.prototype.hasOwnProperty.call(row, m.indicator) ||
      Object.prototype.hasOwnProperty.call(row, `norm_${m.indicator}`)
    );

    const indicatorMarkup = hasIndicatorValues
      ? metaRows.map(m => {
          const rawCol = m.indicator;
          const normCol = `norm_${m.indicator}`;

          const selectedRaw = row[rawCol];
          const countyRaw = countyAverageForCol(rawCol);
          const selectedNorm = +row[normCol];

          const influenceOnDomain = isFiniteNumber(selectedNorm) ? selectedNorm / divisor : NaN;
          const influenceOnOverall = isFiniteNumber(influenceOnDomain)
            ? influenceOnDomain * (+state.normalizedWeights[d.key] || 0)
            : NaN;

          return `
            <div class="indicator-row">
              <div class="indicator-row-top">
                <div>
                  <div class="indicator-name">${m.indicator}</div>
                  <div class="indicator-direction">${boolFromMeta(m.higher_is_better) ? 'Higher is better' : 'Lower is better'}</div>
                </div>
                <div class="indicator-chip">${isFiniteNumber(selectedNorm) ? scoreOutOf100(selectedNorm) : 'N/A'}</div>
              </div>

              <div class="indicator-grid">
                <div class="indicator-stat">
                  <span>Selected value</span>
                  <strong>${formatRawValue(selectedRaw)}</strong>
                </div>

                <div class="indicator-stat">
                  <span>County avg</span>
                  <strong>${formatRawValue(countyRaw)}</strong>
                </div>

                <div class="indicator-stat">
                  <span>Influence on domain</span>
                  <strong>${isFiniteNumber(influenceOnDomain) ? influenceOnDomain.toFixed(3) : 'N/A'}</strong>
                </div>

                <div class="indicator-stat">
                  <span>Influence on overall</span>
                  <strong>${isFiniteNumber(influenceOnOverall) ? influenceOnOverall.toFixed(3) : 'N/A'}</strong>
                </div>
              </div>

              <div class="indicator-source-line">
                <span>Source</span>
                <strong>${m.source || 'N/A'}</strong>
              </div>

              <div class="indicator-note">${m.notes || 'No source note available.'}</div>
            </div>
          `;
        }).join('')
      : `
          <div class="callout-note">
            Indicator-level values are not in the current processed CSV for this geography yet.
            Rebuild the processed YOI CSVs after updating the Python export scripts below.
          </div>
        `;

    return `
      <div class="domain-accordion ${idx === 0 ? 'open' : ''}">
        <button type="button" class="domain-accordion-btn" data-domain="${d.key}" aria-expanded="${idx === 0 ? 'true' : 'false'}">
          <div class="domain-accordion-main">
            <div class="domain-accordion-title-row">
              <div class="domain-accordion-title">${d.label}</div>
              <div class="domain-accordion-score">${scoreOutOf100(d.score)}</div>
            </div>
            <div class="domain-accordion-meta">
              County avg ${scoreOutOf100(countyDomainMean)} · Weight ${(d.weight * 100).toFixed(1)}% · Overall contribution ${d.weighted.toFixed(3)}
            </div>
          </div>

          <div class="domain-accordion-icon">
            <i class="bi bi-chevron-down"></i>
          </div>
        </button>

        <div class="domain-accordion-body">
          <div class="domain-overview-grid">
            <div class="domain-overview-stat">
              <span>Selected domain score</span>
              <strong>${scoreOutOf100(d.score)}</strong>
            </div>

            <div class="domain-overview-stat">
              <span>County avg</span>
              <strong>${scoreOutOf100(countyDomainMean)}</strong>
            </div>

            <div class="domain-overview-stat">
              <span>Gap vs median</span>
              <strong>${Number.isFinite(stats.median) ? `${d.score - stats.median >= 0 ? '+' : ''}${Math.round((d.score - stats.median) * 100)}` : 'N/A'}</strong>
            </div>

            <div class="domain-overview-stat">
              <span>Contribution to overall</span>
              <strong>${d.weighted.toFixed(3)}</strong>
            </div>
          </div>

          <div class="domain-overview-note">
            This domain score is the mean of the normalized indicators available for this domain.
            Its contribution to the overall YOI equals domain score × current domain weight.
          </div>

          <div class="indicator-breakdown-title">Indicators used in this domain</div>
          <div class="indicator-breakdown">
            ${indicatorMarkup}
          </div>
        </div>
      </div>
    `;
  }).join('');

  el.innerHTML = `
    <div class="location-panel-head">
      <div class="location-header">
        <div class="loc-tract">${areaLabel}</div>
        <div class="loc-sub">San Diego County, CA</div>
        ${popMissing ? '<div class="warning-badge">Population unavailable</div>' : ''}
      </div>

      <button type="button" class="location-jump-btn" data-jump-to-profile>
        <span>Domain Profile</span>
        <i class="bi bi-chevron-down"></i>
      </button>
    </div>

    <div class="loc-metric-grid">
      <div class="loc-metric">
        <div class="loc-metric-label">Overall YOI</div>
        <div class="loc-metric-value">${(+row.yoi_custom_0_100).toFixed(1)}</div>
      </div>

      <div class="loc-metric">
        <div class="loc-metric-label">Population</div>
        <div class="loc-metric-value">${pop}</div>
      </div>

      <div class="loc-metric">
        <div class="loc-metric-label">Rank</div>
        <div class="loc-metric-value">${Number.isFinite(rank) ? `${rank}/${total}` : 'N/A'}</div>
      </div>

      <div class="loc-metric">
        <div class="loc-metric-label">Percentile</div>
        <div class="loc-metric-value">${Number.isFinite(percentile) ? `${percentile}th` : 'N/A'}</div>
      </div>

      <div class="loc-metric">
        <div class="loc-metric-label">Best domain</div>
        <div class="loc-metric-value">${best.label}</div>
      </div>

      <div class="loc-metric">
        <div class="loc-metric-label">Lowest domain</div>
        <div class="loc-metric-value">${worst.label}</div>
      </div>
    </div>

    <div class="location-section" id="locationDomainProfileSection">
      <div class="location-section-head">
        <div>
          <div class="location-section-title">Domain Profile</div>
          <div class="location-section-subtitle">County-relative domain diagnostics for the selected area.</div>
        </div>
      </div>
      <div id="profileChart"></div>
    </div>

    
  `;

  el.querySelector('[data-jump-to-profile]')?.addEventListener('click', () => {
    el.querySelector('#locationDomainProfileSection')?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    });
  });

  el.querySelectorAll('.domain-accordion-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.domain-accordion');
      const isOpen = card.classList.contains('open');

      el.querySelectorAll('.domain-accordion').forEach(node => {
        node.classList.remove('open');
        node.querySelector('.domain-accordion-btn')?.setAttribute('aria-expanded', 'false');
      });

      if (!isOpen) {
        card.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
      }
    });
  });
}

function ensureChartTooltip() {
  if (!chartTooltip) chartTooltip = d3.select('body').append('div').attr('class', 'chart-tooltip');
}

function renderProfileChart() {
  const wrap = d3.select('#profileChart');
  wrap.selectAll('*').remove();

  const row = state.selectedGeoid
    ? currentDataMap().get(
        state.showDataFor === 'zips'
          ? normalizeZip(state.selectedGeoid)
          : state.showDataFor === 'supervisor_districts'
            ? normalizeDistrict(state.selectedGeoid)
            : normalizeGeoid(state.selectedGeoid)
      )
    : null;

  if (!row) {
    wrap
      .append('div')
      .attr('class', 'helper-text')
      .text(
        `Select a ${state.showDataFor === 'zips'
          ? 'ZIP code'
          : state.showDataFor === 'supervisor_districts'
            ? 'supervisor district'
            : 'tract'} on the map to view its domain scores.`
      );
    return;
  }

  ensureChartTooltip();

  // Sort by raw domain score, highest first, so the most important scores are easiest to scan
  const data = domainRows(row).sort((a, b) => b.score - a.score);

  const margin = { top: 10, right: 82, bottom: 30, left: 128 };
  const width = 300;
  const barH = 42;
  const height = margin.top + margin.bottom + data.length * barH;

  const svg = wrap
    .append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .style('width', '100%')
    .style('height', 'auto');

  // Use raw score for the bar scale so bars visually match the /100 labels
  const x = d3.scaleLinear()
    .domain([0, 1])
    .range([margin.left, width - margin.right]);

  const y = d3.scaleBand()
    .domain(data.map(d => d.label))
    .range([margin.top, height - margin.bottom])
    .padding(0.24);

  // Bottom axis in score units
  svg.append('g')
    .attr('transform', `translate(0,${height - margin.bottom})`)
    .call(
      d3.axisBottom(x)
        .tickValues([0, 0.25, 0.5, 0.75, 1])
        .tickFormat(d => `${Math.round(d * 100)}`)
    )
    .call(g => g.select('.domain').remove())
    .call(g => g.selectAll('text').attr('fill', '#64748b').style('font-size', '11px'))
    .call(g => g.selectAll('line').attr('stroke', 'rgba(148,163,184,0.35)'));

  // Left labels
  svg.append('g')
    .attr('transform', `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).tickSize(0))
    .call(g => g.select('.domain').remove())
    .call(g => g.selectAll('text').attr('class', 'bar-label'));

  // Background tracks
  svg.selectAll('.bar-track')
    .data(data, d => d.key)
    .join('rect')
    .attr('class', 'bar-track')
    .attr('x', x(0))
    .attr('y', d => y(d.label))
    .attr('height', y.bandwidth())
    .attr('width', x(1) - x(0))
    .attr('rx', 6)
    .attr('fill', '#e7eef5');

  // Filled score bars
  svg.selectAll('.bar')
    .data(data, d => d.key)
    .join('rect')
    .attr('class', 'bar')
    .attr('x', x(0))
    .attr('y', d => y(d.label))
    .attr('height', y.bandwidth())
    .attr('rx', 6)
    .attr('fill', '#5a8bb1')
    .attr('width', 0)
    .transition()
    .duration(350)
    .attr('width', d => x(d.score) - x(0));

  // Full-row hit area so clicking is easy
  svg.selectAll('.bar-hit')
    .data(data, d => d.key)
    .join('rect')
    .attr('class', 'bar-hit')
    .attr('x', x(0))
    .attr('y', d => y(d.label))
    .attr('height', y.bandwidth())
    .attr('width', x(1) - x(0))
    .attr('fill', 'transparent')
    .style('cursor', 'pointer')
    .on('mousemove', (event, d) => {
      chartTooltip
        .style('opacity', 1)
        .html(
          `<strong>${d.label}</strong>` +
          `<br>Domain score: ${Math.round(d.score * 100)}/100` +
          `<br>Current weight: ${(d.weight * 100).toFixed(1)}%` +
          `<br>Weighted contribution: ${d.weighted.toFixed(3)}`
        )
        .style('left', `${event.pageX + 12}px`)
        .style('top', `${event.pageY - 28}px`);
    })
    .on('mouseout', () => chartTooltip.style('opacity', 0))
    .on('click', (_, d) => {
      state.mapLayer = `${d.key} score`;
      document.getElementById('mapLayerSelect').value = state.mapLayer;
      updateAll();
    });

  // Main visible label: score out of 100
  svg.selectAll('.bar-value')
    .data(data, d => d.key)
    .join('text')
    .attr('class', 'bar-value')
    .attr('x', width - margin.right + 8)
    .attr('y', d => y(d.label) + y.bandwidth() / 2 - 2)
    .text(d => `${Math.round(d.score * 100)}/100`);

  // Small supporting text: contribution
  svg.selectAll('.bar-subvalue')
    .data(data, d => d.key)
    .join('text')
    .attr('class', 'bar-subvalue')
    .attr('x', width - margin.right + 8)
    .attr('y', d => y(d.label) + y.bandwidth() / 2 + 11)
    .text(d => `contrib. ${d.weighted.toFixed(3)}`);
}

function renderProfileChart() {
  const wrap = d3.select('#profileChart');
  wrap.selectAll('*').remove();

  const row = state.selectedGeoid
    ? currentDataMap().get(
        state.showDataFor === 'zips'
          ? normalizeZip(state.selectedGeoid)
          : state.showDataFor === 'supervisor_districts'
            ? normalizeDistrict(state.selectedGeoid)
            : normalizeGeoid(state.selectedGeoid)
      )
    : null;

  if (!row) {
    wrap
      .append('div')
      .attr('class', 'helper-text')
      .text(
        `Select a ${state.showDataFor === 'zips'
          ? 'ZIP code'
          : state.showDataFor === 'supervisor_districts'
            ? 'supervisor district'
            : 'tract'} on the map to view its domain diagnostics.`
      );
    return;
  }

  ensureChartTooltip();

  const areaId = currentIdForRow(row);
  const areaLabel = currentFeatureLabel(areaId);
  const overallYoi = Number.isFinite(+row.yoi_custom_0_100) ? +row.yoi_custom_0_100 : +row.yoi_0_100;
  const overallRank = percentileForRow(row);

  const diagnostics = domainRows(row).map(d => {
    const stats = domainProfileStats(d.key, d.score);
    const badge = profileBadgeForDomain(stats);
    return { ...d, ...stats, badge };
  });

  const belowMedianCount = diagnostics.filter(d => d.signedGap < 0).length;
  const primaryDriverCount = diagnostics.filter(d => d.badge.tone === 'driver').length;

  const patternLabel =
    primaryDriverCount >= 3 || belowMedianCount >= 5
      ? 'Broad desert'
      : belowMedianCount >= 3
        ? 'Mixed deficits'
        : belowMedianCount >= 1
          ? 'Targeted gap'
          : 'Relative strength';

  const sortMode = state.profileSort || 'desert';

  const sorted = [...diagnostics].sort(
    sortMode === 'strength'
      ? (a, b) => (b.score - a.score) || (a.rank - b.rank)
      : (a, b) => (b.deficit - a.deficit) || (a.percentile - b.percentile) || (b.score - a.score)
  );

  const narrative = buildProfileSummaryText(diagnostics);
  const byKey = new Map(diagnostics.map(d => [d.key, d]));

  wrap.html(`
    <div class="profile-summary-grid">
      <div class="profile-summary-card">
        <div class="profile-summary-label">Overall YOI</div>
        <div class="profile-summary-value">${Number.isFinite(overallYoi) ? `${Math.round(overallYoi)}/100` : 'N/A'}</div>
      </div>

      <div class="profile-summary-card">
        <div class="profile-summary-label">County percentile</div>
        <div class="profile-summary-value">
          ${overallRank.percentile != null ? ordinalSuffix(overallRank.percentile) : 'N/A'}
        </div>
      </div>

      <div class="profile-summary-card">
        <div class="profile-summary-label">Domains below median</div>
        <div class="profile-summary-value">${belowMedianCount}/${diagnostics.length}</div>
      </div>

      <div class="profile-summary-card">
        <div class="profile-summary-label">Pattern</div>
        <div class="profile-summary-value profile-summary-value-sm">${patternLabel}</div>
      </div>
    </div>

    <div class="profile-narrative">
      <div class="profile-narrative-title">${areaLabel}</div>
      <div class="profile-narrative-text">${narrative}</div>
    </div>

    <div class="profile-toolbar">
      <div class="profile-toolbar-label">Sort domains by</div>
      <div class="profile-sort-group">
        <button class="profile-sort-btn ${sortMode === 'desert' ? 'active' : ''}" data-sort="desert">
          Desert drivers
        </button>
        <button class="profile-sort-btn ${sortMode === 'strength' ? 'active' : ''}" data-sort="strength">
          Strongest domains
        </button>
      </div>
    </div>

    <div class="profile-domain-list">
      ${sorted.map(d => `
        <div class="profile-domain-card" data-domain="${d.key}">
          <div class="profile-card-top">
            <div>
              <div class="profile-domain-title">${d.label}</div>
              <div class="profile-domain-meta">${scoreOutOf100(d.score)} · ${ordinalSuffix(d.percentile)} percentile</div>
            </div>
            <div class="profile-driver-badge ${d.badge.tone}">${d.badge.label}</div>
          </div>

          <div class="profile-domain-track">
            <div class="profile-domain-iqr" style="left:${d.q1 * 100}%; width:${Math.max(0, (d.q3 - d.q1) * 100)}%;"></div>
            <div class="profile-domain-fill" style="width:${Math.max(0, Math.min(100, d.score * 100))}%"></div>
            <div class="profile-domain-marker median" style="left:${d.median * 100}%"></div>
            <div class="profile-domain-marker mean" style="left:${d.mean * 100}%"></div>
          </div>

          <div class="profile-track-legend">
            <span><i class="swatch selected"></i>Selected</span>
            <span><i class="swatch median"></i>Median</span>
            <span><i class="swatch mean"></i>Mean</span>
            <span><i class="swatch iqr"></i>IQR</span>
          </div>

          <div class="profile-domain-stats">
            <div class="profile-domain-stat">
              <span>Rank</span>
              <strong>${d.rank}/${d.total}</strong>
            </div>

            <div class="profile-domain-stat">
              <span>Gap vs median</span>
              <strong>${Number.isFinite(d.signedGap) ? `${d.signedGap >= 0 ? '+' : ''}${Math.round(d.signedGap * 100)}` : 'N/A'}</strong>
            </div>

            <div class="profile-domain-stat">
              <span>Mean</span>
              <strong>${scoreOutOf100(d.mean)}</strong>
            </div>

            <div class="profile-domain-stat">
              <span>Min–max</span>
              <strong>${scoreOutOf100(d.min)}–${scoreOutOf100(d.max)}</strong>
            </div>
          </div>
        </div>
      `).join('')}
    </div>

    <div class="helper-text mt-3">
      Click a domain card to recolor the map. Hover a card to inspect percentile, rank, county statistics, and desert-driver context.
    </div>
  `);

  wrap.selectAll('.profile-sort-btn')
    .on('click', function () {
      state.profileSort = this.dataset.sort;
      renderProfileChart();
    });

    wrap.selectAll('.profile-domain-card')
    .on('click', function (event) {
      if (event.target.closest('.profile-domain-toggle')) return;

      const key = this.dataset.domain;
      state.mapLayer = `${key} score`;
      document.getElementById('mapLayerSelect').value = state.mapLayer;
      updateAll();
    })
    .on('mousemove', function (event) {
      if (event.target.closest('.profile-domain-toggle')) return;

      const d = byKey.get(this.dataset.domain);
      if (!d) return;

      chartTooltip
        .style('opacity', 1)
        .html(
          `<strong>${d.label}</strong>` +
          `<br>Domain score: ${scoreOutOf100(d.score)}` +
          `<br>County percentile: ${ordinalSuffix(d.percentile)}` +
          `<br>Rank: ${d.rank}/${d.total}` +
          `<br>Median: ${scoreOutOf100(d.median)} | Mean: ${scoreOutOf100(d.mean)}` +
          `<br>Gap vs median: ${d.signedGap >= 0 ? '+' : ''}${Math.round(d.signedGap * 100)}` +
          `<br>Weighted contribution: ${d.weighted.toFixed(3)}`
        )
        .style('left', `${event.pageX + 12}px`)
        .style('top', `${event.pageY - 28}px`);
    })
    .on('mouseout', () => chartTooltip.style('opacity', 0));

  wrap.selectAll('.profile-domain-card').each(function () {
    const card = this;
    const key = card.dataset.domain;
    const d = byKey.get(key);
    if (!d) return;

    const top = card.querySelector('.profile-card-top');
    const legend = card.querySelector('.profile-track-legend');
    if (!top || !legend) return;

    if (!top.querySelector('.profile-domain-toggle')) {
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'profile-domain-toggle';
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('title', 'Show domain score breakdown');
      toggle.innerHTML = '<i class="bi bi-chevron-down"></i>';
      top.appendChild(toggle);
    }

    if (!card.querySelector('.profile-domain-expand')) {
      const expand = document.createElement('div');
      expand.className = 'profile-domain-expand';
      legend.insertAdjacentElement('afterend', expand);
    }

    const toggle = top.querySelector('.profile-domain-toggle');
    const expand = card.querySelector('.profile-domain-expand');

    toggle.onclick = event => {
      event.preventDefault();
      event.stopPropagation();

      const isOpen = card.classList.contains('breakdown-open');

      wrap.selectAll('.profile-domain-card').each(function () {
        this.classList.remove('breakdown-open');
        const btn = this.querySelector('.profile-domain-toggle');
        const body = this.querySelector('.profile-domain-expand');
        if (btn) btn.setAttribute('aria-expanded', 'false');
        if (body) body.innerHTML = '';
      });

      if (!isOpen) {
        card.classList.add('breakdown-open');
        toggle.setAttribute('aria-expanded', 'true');
        expand.innerHTML = buildDomainBreakdownMarkup(row, key);
      }
    };
  });
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

function syncDrawerToolPositions() {
  const drawerPanel = document.getElementById('drawerPanel');
  const toolStack = document.querySelector('.drawer-tool-stack');
  const searchFlyout = document.querySelector('.drawer-search-flyout');

  if (!drawerPanel || !toolStack) return;

  const rect = drawerPanel.getBoundingClientRect();
  const gap = 14;
  const margin = 16;

  const stackWidth = toolStack.offsetWidth || 42;
  const stackHeight = toolStack.offsetHeight || 150;

  let left = rect.right + gap;
  let top = rect.top + 890;

  left = Math.min(left, window.innerWidth - stackWidth - margin);
  top = Math.min(top, window.innerHeight - stackHeight - margin);
  left = Math.max(margin, left);
  top = Math.max(margin, top);

  toolStack.style.left = `${Math.round(left)}px`;
  toolStack.style.top = `${Math.round(top)}px`;
  toolStack.classList.add('ready');

  if (searchFlyout) {
    const flyoutWidth = searchFlyout.offsetWidth || 320;

    let flyoutLeft = left + stackWidth + 10;
    let flyoutTop = top + 44;

    flyoutLeft = Math.min(flyoutLeft, window.innerWidth - flyoutWidth - margin);
    flyoutLeft = Math.max(margin, flyoutLeft);
    flyoutTop = Math.max(margin, flyoutTop);

    searchFlyout.style.left = `${Math.round(flyoutLeft)}px`;
    searchFlyout.style.top = `${Math.round(flyoutTop)}px`;
  }
}

// function syncDrawerToolPositions() {
//   const drawerPanel = document.getElementById('drawerPanel');
//   const toolStack = document.querySelector('.drawer-tool-stack');
//   const searchFlyout = document.querySelector('.drawer-search-flyout');

//   if (!drawerPanel || !toolStack) return;

//   const rect = drawerPanel.getBoundingClientRect();

//   toolStack.style.left = `${Math.round(rect.right + 14)}px`;
//   toolStack.style.top = `${Math.round(rect.top + 12)}px`;

//   if (searchFlyout) {
//     searchFlyout.style.left = `${Math.round(rect.right + 64)}px`;
//     searchFlyout.style.top = `${Math.round(rect.top + 48)}px`;
//   }
// }

function setPanel(panelName) {
  clearTransientUi();

  state.activePanel = panelName;
  document.querySelectorAll('.rail-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.panel === panelName));
  document.querySelectorAll('.panel-view').forEach(view => view.classList.toggle('active', view.id === `panel-${panelName}`));

  const titleMap = {
    controls: ['Data Controls', 'Adjust the map and comparison view.'],
    overlays: ['Overlays', 'Turn map layers on and off.'],
    profile: ['Domain Profile', 'Domain scores for the selected area, shown out of 100.'],
    location: ['Location Details', 'Inspect the selected area in detail.'],
    faqs: ['Frequently asked questions', 'Helpful context for interpreting the dashboard.'],
    share: ['Share', 'Copy the current state of the explorer.'],
    assistant: ['Assistant', 'Ask questions to navigate and understand the data.'],
  };

  document.getElementById('drawerTitle').textContent = titleMap[panelName][0];
  document.getElementById('drawerSubtitle').textContent = titleMap[panelName][1];

    const drawerPanel = document.getElementById('drawerPanel');
  drawerPanel.classList.toggle('panel-popout', panelName === 'profile' || panelName === 'location');
  drawerPanel.classList.remove('collapsed');

  document.body.classList.toggle('location-panel-open', panelName === 'location');

  syncDrawerToolPositions();
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
  renderPanelContent();
  if (reRenderMap) renderMap();
  updateLegendCard();
}

function buildLayerSelect() {
  const select = document.getElementById('mapLayerSelect');
  select.innerHTML = ['YOI (0–100)', ...DOMAINS.map(d => `${d} score`)].map(v => `<option value="${v}">${v === 'YOI (0–100)' ? 'Overall Youth Opportunity' : DOMAIN_LABELS[v.replace(/ score$/, '')] + ' Domain'}</option>`).join('');
  select.value = state.mapLayer;
    select.addEventListener('change', e => {
    state.mapLayer = e.target.value;
    clearTransientUi();
    updateAll();
  });
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

function syncGeographyControls() {
  document.querySelectorAll('[data-show-data-for]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.showDataFor === state.showDataFor);
  });

  updateSearchUi();
  syncPrimaryViewToggles();
}

function openSiteMenu() {
  const drawer = document.getElementById('siteMenuDrawer');
  const backdrop = document.getElementById('menuBackdrop');

  if (!drawer || !backdrop) return;

  drawer.classList.add('open');
  drawer.setAttribute('aria-hidden', 'false');
  backdrop.classList.add('open');
}

function closeSiteMenu() {
  const drawer = document.getElementById('siteMenuDrawer');
  const backdrop = document.getElementById('menuBackdrop');

  if (!drawer || !backdrop) return;

  drawer.classList.remove('open');
  drawer.setAttribute('aria-hidden', 'true');
  backdrop.classList.remove('open');
}

function toggleDrawerPanel(panelName = 'controls') {
  const drawerPanel = document.getElementById('drawerPanel');
  if (!drawerPanel) return;

  const isCollapsed = drawerPanel.classList.contains('collapsed');
  const isSamePanel = state.activePanel === panelName;

  // if the same panel is already open, close it
  if (!isCollapsed && isSamePanel) {
    drawerPanel.classList.add('collapsed');

    document.querySelectorAll('.rail-btn').forEach(btn => {
      btn.classList.remove('active');
    });

    document.body.classList.remove('location-panel-open');
    requestAnimationFrame(syncDrawerToolPositions);
    return;
  }

  // otherwise open that panel normally
  setPanel(panelName);
}

function bindControls() {
  document.getElementById('toggleChoro')?.addEventListener('change', e => {
  if (e.target.checked) {
    setPrimaryView('yoi');
  } else {
    syncPrimaryViewToggles();
  }
});

document.getElementById('toggleCoiOverlay')?.addEventListener('change', e => {
  if (e.target.checked) {
    setPrimaryView('coi');
  } else {
    setPrimaryView('yoi');
  }
});

document.getElementById('toggleSupervisorDistricts')?.addEventListener('change', e => {
  if (e.target.checked) {
    setPrimaryView('supervisor');
  } else {
    setPrimaryView('yoi');
  }
});
  document.getElementById('toggleBounds').addEventListener('change', e => { state.showBounds = e.target.checked; updateAll(); });
  document.getElementById('toggleRoutes').addEventListener('change', e => { state.showRoutes = e.target.checked; updateAll(); });
  document.getElementById('toggleStops').addEventListener('change', e => { state.showStops = e.target.checked; updateAll(); });
  document.getElementById('hoverToggle').addEventListener('change', e => { state.showHover = e.target.checked; updateAll(); });
    document.querySelectorAll('#scoreModeGroup .seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#scoreModeGroup .seg-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.scoreMode = btn.dataset.mode;
      clearTransientUi();
      updateAll();
    });
  });
    document.querySelectorAll('[data-show-data-for]').forEach(btn => {
  btn.addEventListener('click', () => {
    const mode = btn.dataset.showDataFor;

    if (mode === 'zips' && (!state.zipGeojson || state.zipRows.length === 0)) {
      console.warn('ZIP code mode requires ./data/processed/boundaries/sd_zip_codes.geojson and ./data/processed/yoi/yoi_zip_components.csv');
      return;
    }

    if (mode === 'supervisor_districts') {
      setPrimaryView('supervisor');
      return;
    }

    if (mode === 'tracts') {
      setPrimaryView('yoi');
      return;
    }

    if (mode === 'zips') {
      state.showDataFor = 'zips';
      state.showChoro = false;
      state.showCoiOverlay = false;
      state.selectedGeoid = null;
      clearTransientUi();
      syncGeographyControls();
      updateAll();
    }
  });
});


  document.querySelectorAll('.rail-btn').forEach(btn => {
  btn.addEventListener('click', () => toggleDrawerPanel(btn.dataset.panel));
});
document.querySelector('.legend-icon')?.addEventListener('click', () => {
  toggleDrawerPanel('controls');
});
document.getElementById('closeDrawerBtn').addEventListener('click', () => {
  document.getElementById('drawerPanel').classList.add('collapsed');

  document.querySelectorAll('.rail-btn').forEach(btn => {
    btn.classList.remove('active');
  });

  document.body.classList.remove('location-panel-open');
  requestAnimationFrame(syncDrawerToolPositions);
});
// document.getElementById('railMenuBtn')?.addEventListener('click', () => {
//   const drawer = document.getElementById('siteMenuDrawer');
//   if (drawer?.classList.contains('open')) closeSiteMenu();
//   else openSiteMenu();
// });

// document.getElementById('railSearchBtn')?.addEventListener('click', () => {
//   const flyout = document.getElementById('railSearchFlyout');
//   setRailSearchOpen(!flyout?.classList.contains('open'));
// });

// document.getElementById('closeRailSearchBtn')?.addEventListener('click', () => {
//   setRailSearchOpen(false);
// });

// document.getElementById('railZoomInBtn')?.addEventListener('click', () => {
//   map.zoomIn();
// });

// document.getElementById('railZoomOutBtn')?.addEventListener('click', () => {
//   map.zoomOut();
// });

document.getElementById('railHomeBtn')?.addEventListener('click', () => {
  goToHomeView();
});

document.getElementById('railZoomInBtn')?.addEventListener('click', () => {
  map.zoomIn();
});

document.getElementById('railZoomOutBtn')?.addEventListener('click', () => {
  map.zoomOut();
});

document.getElementById('closeSiteMenuBtn')?.addEventListener('click', closeSiteMenu);
document.getElementById('menuBackdrop')?.addEventListener('click', closeSiteMenu);

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeSiteMenu();
    setRailSearchOpen(false);
  }
});

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

searchInput?.addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  e.preventDefault();
  runSearch();
});

searchInput?.addEventListener('focus', () => {
  setSearchStatus('');
  updateSearchSuggestions(searchInput.value);
});

searchInput?.addEventListener('input', () => {
  setSearchStatus('');
  updateSearchSuggestions(searchInput.value);
});

document.getElementById('searchBtn')?.addEventListener('click', runSearch);
//   document.getElementById('toggleCoiOverlay')?.addEventListener('change', e => {
//     state.showCoiOverlay = e.target.checked;
//     clearTransientUi();
//     updateAll();
// });

document.getElementById('toggleServices').addEventListener('change', e => {
  state.showServices = e.target.checked;
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
  if (state.geojson?.features) {
    state.geojson.features.forEach(f => {
      const p = f.properties || {};
      p.tract_geoid = normalizeGeoid(p.tract_geoid ?? p.GEOID ?? p.geoid ?? p.Tract ?? p.TRACT);
      f.properties = p;
    });
  }

  if (state.zipGeojson?.features) {
    state.zipGeojson.features.forEach(f => {
      const p = f.properties || {};
      p.zip = normalizeZip(p.zip ?? p.ZIP ?? p.zip_code ?? p.ZIPCODE ?? p.ZCTA5CE20 ?? p.GEOID20 ?? p.geoid ?? p.GEOID);
      f.properties = p;
    });
  }

  if (state.supervisorDistrictsGeojson?.features) {
    state.supervisorDistrictsGeojson.features.forEach(f => {
      const p = f.properties || {};
      p.distno = normalizeDistrict(p.distno ?? p.DISTNO ?? p.district ?? p.District ?? p.DISTRICT ?? p.id ?? p.ID);
      f.properties = p;
    });
  }
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
      paddingTopLeft: [400, 110],
      paddingBottomRight: [140, 40],
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

function goToHomeView() {
  const bounds = tractLayer?.getBounds?.();

  if (bounds && bounds.isValid()) {
    map.fitBounds(bounds, {
      animate: true,
      paddingTopLeft: [400, 110],
      paddingBottomRight: [140, 40],
      maxZoom: 11,
    });
    return;
  }

  map.setView([32.87, -116.96], 10, { animate: true });
}

function filterExcludedTracts() {
  state.rawYoi = (state.rawYoi || []).filter(
    row => !EXCLUDED_TRACT_GEOIDS.has(normalizeGeoid(row.tract_geoid))
  );

  if (state.geojson?.features) {
    state.geojson.features = state.geojson.features.filter(feature => {
      const geoid = normalizeGeoid(
        feature.properties?.tract_geoid ??
        feature.properties?.GEOID ??
        feature.properties?.geoid ??
        feature.properties?.Tract ??
        feature.properties?.TRACT
      );
      return !EXCLUDED_TRACT_GEOIDS.has(geoid);
    });
  }

  if (EXCLUDED_TRACT_GEOIDS.has(normalizeGeoid(state.selectedGeoid))) {
    state.selectedGeoid = null;
  }
}

function syncPrimaryViewToggles() {
  const yoiToggle = document.getElementById('toggleChoro');
  const coiToggle = document.getElementById('toggleCoiOverlay');
  const supervisorToggle = document.getElementById('toggleSupervisorDistricts');

  if (yoiToggle) yoiToggle.checked = state.showDataFor === 'tracts' && state.showChoro && !state.showCoiOverlay;
  if (coiToggle) coiToggle.checked = state.showDataFor === 'tracts' && state.showCoiOverlay;
  if (supervisorToggle) supervisorToggle.checked = state.showDataFor === 'supervisor_districts';
}

function setPrimaryView(view) {
  if (view === 'supervisor') {
    if (!state.supervisorDistrictsGeojson || state.supervisorDistrictRows.length === 0) {
      console.warn('Supervisor district mode requires ./data/processed/overlays/supervisor_districts.geojson and ./data/processed/yoi/yoi_supervisor_district_components.csv');
      return;
    }
    state.showDataFor = 'supervisor_districts';
    state.showChoro = false;
    state.showCoiOverlay = false;
  } else if (view === 'coi') {
    state.showDataFor = 'tracts';
    state.showChoro = false;
    state.showCoiOverlay = true;
  } else {
    state.showDataFor = 'tracts';
    state.showChoro = true;
    state.showCoiOverlay = false;
  }

  state.selectedGeoid = null;
  clearTransientUi();
  syncGeographyControls();
  syncPrimaryViewToggles();
  updateAll();
}

function buildAssistantContext() {
  const selectedRow = state.selectedGeoid
    ? currentDataMap().get(
        state.showDataFor === 'zips'
          ? normalizeZip(state.selectedGeoid)
          : state.showDataFor === 'supervisor_districts'
            ? normalizeDistrict(state.selectedGeoid)
            : normalizeGeoid(state.selectedGeoid)
      )
    : null;

  // 1. Calculate dynamic service counts for the map markers
  let totalServices = 0;
  let serviceCountsByType = {};

  if (state.servicesGeojson && state.servicesGeojson.features) {
    const features = state.servicesGeojson.features;
    totalServices = features.length;
    features.forEach(f => {
      const type = (f.properties && f.properties.type) ? f.properties.type : 'Unknown';
      serviceCountsByType[type] = (serviceCountsByType[type] || 0) + 1;
    });
  }

  return {
    selectedGeoid: state.selectedGeoid,
    selectedLabel: state.selectedGeoid ? currentFeatureLabel(state.selectedGeoid) : null,
    mapLayer: state.mapLayer,
    showDataFor: state.showDataFor,
    showChoro: state.showChoro,
    showCoiOverlay: state.showCoiOverlay,
    showBounds: state.showBounds,
    showRoutes: state.showRoutes,
    showStops: state.showStops,
    showServices: state.showServices,
    availablePanels: ['controls', 'overlays', 'location', 'assistant', 'faqs', 'share'],
    availablePrimaryViews: ['yoi', 'coi', 'supervisor'],
    selectedRow: selectedRow
      ? {
          yoi_custom_0_100: selectedRow.yoi_custom_0_100 ?? null,
          total_population: selectedRow.total_population ?? null
        }
      : null,
    
    // 2. Feed the marker counts to the AI!
    mapDataStats: {
      totalServiceLocations: totalServices,
      servicesBreakdownByType: serviceCountsByType
    }
  };
}

function appendAssistantMessage(text, role = 'bot') {
  const wrap = document.getElementById('assistantMessages');
  if (!wrap) return;

  const div = document.createElement('div');
  div.className = `assistant-msg assistant-msg-${role}`;
  div.textContent = text;
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}

function setAssistantBusy(isBusy) {
  const input = document.getElementById('assistantInput');
  const btn = document.getElementById('assistantSendBtn');
  if (input) input.disabled = isBusy;
  if (btn) btn.disabled = isBusy;
}

function executeAssistantAction(action) {
  if (!action || !action.type) return;

  if (action.type === 'set_panel' && action.panel) {
    setPanel(action.panel);
    return;
  }

  if (action.type === 'set_primary_view' && action.view) {
    setPrimaryView(action.view);
    return;
  }

  if (action.type === 'toggle_overlay' && action.overlay) {
    const enabled = !!action.enabled;

    if (action.overlay === 'bounds') state.showBounds = enabled;
    if (action.overlay === 'routes') state.showRoutes = enabled;
    if (action.overlay === 'stops') state.showStops = enabled;
    if (action.overlay === 'services') state.showServices = enabled;

    const boundsToggle = document.getElementById('toggleBounds');
    const routesToggle = document.getElementById('toggleRoutes');
    const stopsToggle = document.getElementById('toggleStops');
    const servicesToggle = document.getElementById('toggleServices');

    if (boundsToggle && action.overlay === 'bounds') boundsToggle.checked = enabled;
    if (routesToggle && action.overlay === 'routes') routesToggle.checked = enabled;
    if (stopsToggle && action.overlay === 'stops') stopsToggle.checked = enabled;
    if (servicesToggle && action.overlay === 'services') servicesToggle.checked = enabled;

    updateAll();
  }
}

async function sendAssistantMessage(prefilledText = null) {
  const input = document.getElementById('assistantInput');
  if (!input) return;

  const message = (prefilledText ?? input.value).trim();
  if (!message) return;

  appendAssistantMessage(message, 'user');
  input.value = '';
  setAssistantBusy(true);

  try {
    const res = await fetch(ASSISTANT_API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        context: buildAssistantContext(),
      }),
    });

    if (!res.ok) {
      throw new Error(`Assistant request failed: ${res.status}`);
    }

    const data = await res.json();
    appendAssistantMessage(data.reply || 'Sorry, I could not answer that.', 'bot');

    if (data.action) {
      executeAssistantAction(data.action);
    }
  } catch (err) {
    console.error(err);
    appendAssistantMessage('Sorry — the assistant backend is not reachable right now.', 'bot');
  } finally {
    setAssistantBusy(false);
  }
}

function bindAssistantUi() {
  const input = document.getElementById('assistantInput');
  const sendBtn = document.getElementById('assistantSendBtn');

  if (!input || !sendBtn || input.dataset.bound === 'true') return;

  input.dataset.bound = 'true';

  sendBtn.addEventListener('click', () => sendAssistantMessage());

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      sendAssistantMessage();
    }
  });

  document.querySelectorAll('[data-assistant-prompt]').forEach(btn => {
    btn.addEventListener('click', () => {
      sendAssistantMessage(btn.dataset.assistantPrompt || '');
    });
  });
}

async function init() {
  buildLayerSelect();
  buildWeightSliders();
  bindControls();
  bindAssistantUi();
  syncGeographyControls();

  state.rawYoi = await loadCsv('./data/processed/yoi/yoi_components.csv');
  state.zipRows = await loadCsv('./data/processed/yoi/yoi_zip_components.csv').catch(() => []);
  state.supervisorDistrictRows = await loadCsv('./data/processed/yoi/yoi_supervisor_district_components.csv').catch(() => []);
  state.meta = await loadCsv('./data/processed/yoi/yoi_indicator_meta.csv').catch(() => []);
  state.geojson = await loadJson('./data/processed/boundaries/sd_tracts.geojson');
  state.zipGeojson = await loadJson('./data/processed/boundaries/sd_zip_codes.geojson').catch(() => null);
  state.routesGeojson = await loadJson('./data/processed/boundaries/transit_routes.geojson').catch(() => null);
  state.stopsGeojson = await loadJson('./data/processed/boundaries/transit_stops.geojson').catch(() => null);
  state.coiRows = await loadCsv('./data/processed/overlays/sd_coi_2023.csv').catch(() => []);
  state.coiMap = new Map(state.coiRows.map(r => [normalizeGeoid(r.tract_geoid), r]));
  state.servicesGeojson = await loadJson('./data/processed/overlays/service_locations.geojson').catch(() => null);
  state.supervisorDistrictsGeojson = await loadJson('./data/processed/overlays/supervisor_districts.geojson').catch(() => null);

  initGeojsonProps();
  filterExcludedTracts();
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
    syncDrawerToolPositions();
  });
});
}

init().catch(err => {
  console.error(err);
  document.getElementById('locationDetails').innerHTML = `<div class="callout-note">Failed to load dashboard data: ${err.message}</div>`;
});

window.addEventListener('resize', syncDrawerToolPositions);