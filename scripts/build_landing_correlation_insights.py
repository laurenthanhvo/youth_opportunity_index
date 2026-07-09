from pathlib import Path
import itertools
import json
import re

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
OUT = ROOT / "data" / "processed" / "landing" / "landing_correlation_insights.json"


DOMAIN_PATTERNS = {
    "Economic": ["economic"],
    "Education": ["education"],
    "Health": ["health"],
    "Housing": ["housing"],
    "Safety / Env": ["safety", "env", "environment"],
    "Mobility / Connectivity": ["mobility", "connectivity"],
    "Youth Supports": ["youth_support", "youthsupports", "support"],
}


def clean_name(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def pretty_label(col):
    text = str(col)
    text = re.sub(r"_?0_100$", "", text)
    text = re.sub(r"_?score$", "", text)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip().title()
    text = text.replace("Yoi", "YOI")
    text = text.replace("YOI Z", "Standardized YOI (z-score)")
    text = text.replace("Yoi Z", "Standardized YOI (z-score)")
    text = text.replace("Coi", "COI")
    text = text.replace("Acs", "ACS")
    text = text.replace("Pums", "PUMS")
    text = text.replace("Pct", "%")
    text = text.replace("Percent", "%")
    text = text.replace("14 24", "14–24")
    text = text.replace("16 19", "16–19")
    text = text.replace("18 24", "18–24")
    return text


def read_csv_sample(path, nrows=None):
    return pd.read_csv(path, nrows=nrows, low_memory=False)


def find_overall_col(df):
    exact = [
        "overall_yoi_0_100",
        "overall_yoi",
        "yoi_overall_0_100",
        "overall_score",
        "yoi_custom_0_100",
    ]

    normalized = {clean_name(c): c for c in df.columns}

    for name in exact:
        if clean_name(name) in normalized:
            return normalized[clean_name(name)]

    for c in df.columns:
        lc = str(c).lower()
        if "overall" in lc and ("yoi" in lc or "score" in lc or "0_100" in lc):
            return c

    return None


def find_domain_cols(df):
    cols = {}

    for label, tokens in DOMAIN_PATTERNS.items():
        best = None
        best_score = -1

        for c in df.columns:
            lc = str(c).lower()
            numeric = pd.to_numeric(df[c], errors="coerce")

            if numeric.notna().sum() < 25:
                continue

            token_match = any(token in lc for token in tokens)
            score_like = any(term in lc for term in ["0_100", "score", "index"])

            if not token_match or not score_like:
                continue

            score = 0
            score += 20 if "0_100" in lc else 0
            score += 10 if "score" in lc else 0
            score += 10 if lc.endswith("_0_100") else 0
            score += 5 if len(lc) < 40 else 0

            if score > best_score:
                best = c
                best_score = score

        if best:
            cols[label] = best

    return cols


def find_tract_source_file():
    candidates = []

    for path in sorted(PROCESSED_DIR.rglob("*.csv")):
        lowered = str(path).lower()

        if any(skip in lowered for skip in [
            "/landing/",
            "/validation/",
            "/workforce/",
            "/cde/",
            "countywide",
            "summary",
            "county_region",
            "supervisor",
            "city_council",
            "zip"
        ]):
            continue

        try:
            sample = read_csv_sample(path, nrows=100)
        except Exception:
            continue

        overall_col = find_overall_col(sample)

        if not overall_col:
            continue

        domain_cols = find_domain_cols(sample)

        if len(domain_cols) < 3:
            continue

        cols_lower = [str(c).lower() for c in sample.columns]
        has_tract_id = any("tract" in c or "geoid" in c for c in cols_lower)

        try:
            row_count = sum(1 for _ in open(path, "r", encoding="utf-8", errors="ignore")) - 1
        except Exception:
            row_count = len(sample)

        score = 0
        score += 100
        score += 80 if has_tract_id else 0
        score += 80 if 600 <= row_count <= 900 else 0
        score += 40 if "tract" in path.name.lower() else 0
        score += 30 if "component" in path.name.lower() else 0
        score += 30 if "yoi" in path.name.lower() else 0
        score += 10 * len(domain_cols)
        score += min(40, len(sample.columns))

        candidates.append({
            "score": score,
            "path": path,
            "rows": row_count,
            "overall_col": overall_col,
            "domain_cols": domain_cols,
        })

    if not candidates:
        print("\nCould not automatically find the tract-level YOI file.")
        print("Here are CSV files under data/processed that were checked:\n")
        for path in sorted(PROCESSED_DIR.rglob("*.csv")):
            print(" -", path.relative_to(ROOT))
        raise RuntimeError("No tract-level YOI CSV found.")

    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
    selected = candidates[0]

    print("Selected tract-level source:", selected["path"].relative_to(ROOT))
    print("Rows:", selected["rows"])
    print("Overall column:", selected["overall_col"])
    print("Domain columns:", selected["domain_cols"])

    return selected


def pearson(df, x_col, y_col):
    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")
    valid = x.notna() & y.notna()

    if valid.sum() < 25:
        return None, int(valid.sum())

    if x[valid].nunique() < 4 or y[valid].nunique() < 4:
        return None, int(valid.sum())

    r = x[valid].corr(y[valid])

    if pd.isna(r):
        return None, int(valid.sum())

    return float(r), int(valid.sum())


def corr_direction(r):
    if r is None:
        return "not enough data"
    if r >= 0.35:
        return "positive"
    if r <= -0.35:
        return "negative"
    return "weak"


def is_indicator_candidate(col, aggregate_cols):
    lc = str(col).lower()

    if col in aggregate_cols:
        return False

    blocked = [
        "geoid",
        "geometry",
        "objectid",
        "shape",
        "name",
        "rank",
        "percentile",
        "quintile",
        "decile",
        "district",
        "region",
        "zip",
        "tractce",
        "statefp",
        "countyfp",
    ]

    if any(token in lc for token in blocked):
        return False

    if any(token in lc for token in [
        "total_pop",
        "population_total",
        "youth_pop",
        "pop_14",
        "pop_16",
        "pop_18",
    ]):
        return False

    useful_terms = [
        "0_100",
        "score",
        "index",
        "rate",
        "pct",
        "percent",
        "share",
        "ratio",
        "poverty",
        "income",
        "unemploy",
        "employment",
        "graduat",
        "dropout",
        "school",
        "student",
        "college",
        "rent",
        "housing",
        "vehicle",
        "transit",
        "commute",
        "crime",
        "safety",
        "pollution",
        "asthma",
        "health",
        "insurance",
        "park",
        "service",
        "support",
        "broadband",
    ]

    return any(term in lc for term in useful_terms)


def find_name_col(df):
    for c in df.columns:
        lc = str(c).lower()
        if lc in ["name", "tract_name", "label"] or "name" in lc:
            return c
    return None


def find_geoid_col(df):
    for c in df.columns:
        lc = str(c).lower()
        if lc in ["geoid", "tract_geoid", "geoid20"] or "geoid" in lc:
            return c
    return None


def make_scatter(df, x_col, y_col, title, x_label, y_label, r):
    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")

    name_col = find_name_col(df)
    geoid_col = find_geoid_col(df)

    valid = x.notna() & y.notna()
    points = []

    for idx in df[valid].index:
        raw_name = df.loc[idx, name_col] if name_col else None
        raw_geoid = df.loc[idx, geoid_col] if geoid_col else None

        points.append({
            "x": round(float(x.loc[idx]), 3),
            "y": round(float(y.loc[idx]), 3),
            "name": str(raw_name or raw_geoid or f"Tract {idx}"),
        })

    return {
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "r": round(float(r), 3) if r is not None else None,
        "points": points,
    }


def main():
    selected = find_tract_source_file()
    source_file = selected["path"]
    overall_col = selected["overall_col"]

    df = read_csv_sample(source_file)
    domain_cols = find_domain_cols(df)

    aggregate_cols = {overall_col, *domain_cols.values()}

    domain_to_overall = []

    for domain, col in domain_cols.items():
        r, n = pearson(df, col, overall_col)

        if r is None:
            continue

        domain_to_overall.append({
            "domain": domain,
            "column": col,
            "r": round(r, 3),
            "n": n,
            "direction": corr_direction(r),
        })

    domain_to_overall.sort(key=lambda d: abs(d["r"]), reverse=True)

    domain_pairs = []

    for (d1, c1), (d2, c2) in itertools.combinations(domain_cols.items(), 2):
        r, n = pearson(df, c1, c2)

        if r is None:
            continue

        domain_pairs.append({
            "x_domain": d1,
            "y_domain": d2,
            "x_column": c1,
            "y_column": c2,
            "r": round(r, 3),
            "n": n,
            "direction": corr_direction(r),
        })

    domain_pairs.sort(key=lambda d: abs(d["r"]), reverse=True)

    indicator_corrs = []

    for col in df.columns:
        if not is_indicator_candidate(col, aggregate_cols):
            continue

        numeric = pd.to_numeric(df[col], errors="coerce")

        if numeric.notna().sum() < 25 or numeric.nunique(dropna=True) < 4:
            continue

        r, n = pearson(df, col, overall_col)

        if r is None:
            continue

        indicator_corrs.append({
            "indicator": pretty_label(col),
            "column": col,
            "r": round(r, 3),
            "n": n,
            "direction": corr_direction(r),
        })

    indicator_corrs.sort(key=lambda d: abs(d["r"]), reverse=True)

    top_positive = sorted(
        [d for d in indicator_corrs if d["r"] > 0],
        key=lambda d: d["r"],
        reverse=True
    )[:8]

    top_negative = sorted(
        [d for d in indicator_corrs if d["r"] < 0],
        key=lambda d: d["r"]
    )[:8]

    scatter_plots = []

    if domain_to_overall:
        top_domain = domain_to_overall[0]
        scatter_plots.append(make_scatter(
            df,
            top_domain["column"],
            overall_col,
            f"{top_domain['domain']} score vs overall YOI",
            f"{top_domain['domain']} score",
            "Overall YOI score",
            top_domain["r"],
        ))

    if indicator_corrs:
        top_indicator = indicator_corrs[0]
        scatter_plots.append(make_scatter(
            df,
            top_indicator["column"],
            overall_col,
            f"{top_indicator['indicator']} vs overall YOI",
            top_indicator["indicator"],
            "Overall YOI score",
            top_indicator["r"],
        ))

    takeaways = []

    if domain_to_overall:
        strongest_domain = domain_to_overall[0]
        takeaways.append(
            f"{strongest_domain['domain']} has the strongest domain-level relationship with overall YOI "
            f"(r={strongest_domain['r']})."
        )

    if domain_pairs:
        strongest_pair = domain_pairs[0]
        takeaways.append(
            f"{strongest_pair['x_domain']} and {strongest_pair['y_domain']} move together most strongly "
            f"among domain pairs (r={strongest_pair['r']})."
        )

    if indicator_corrs:
        strongest_indicator = indicator_corrs[0]
        takeaways.append(
            f"{strongest_indicator['indicator']} has the strongest indicator-level relationship with overall YOI "
            f"(r={strongest_indicator['r']})."
        )

    out = {
        "metadata": {
            "source_file": str(source_file.relative_to(ROOT)),
            "overall_column": overall_col,
            "tract_count": int(len(df)),
            "note": "Pearson correlations across tract-level rows. Correlation is descriptive and does not prove causation.",
        },
        "domain_to_overall": domain_to_overall,
        "domain_pair_correlations": domain_pairs,
        "top_positive_indicators": top_positive,
        "top_negative_indicators": top_negative,
        "scatter_plots": scatter_plots,
        "takeaways": takeaways,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))

    print("Saved:", OUT.relative_to(ROOT))
    print("Domain correlations:", len(domain_to_overall))
    print("Domain-pair correlations:", len(domain_pairs))
    print("Indicator correlations:", len(indicator_corrs))


if __name__ == "__main__":
    main()
