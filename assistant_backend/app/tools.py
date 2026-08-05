from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
import re

import pandas as pd
from bs4 import BeautifulSoup

from . import settings
from .db import YOIDatabase


SOURCE_LABELS = {
    "tracts": "YOI tract-level components dataset",
    "regions": "YOI county-region components dataset",
    "indicator_metadata": "YOI indicator metadata",
    "methodology": "YOI methodology",
    "map": "YOI interactive map",
}

SEARCH_STOPWORDS = {
    "and",
    "does",
    "from",
    "how",
    "indicator",
    "mean",
    "means",
    "source",
    "the",
    "what",
    "where",
    "with",
    "yoi",
}


@lru_cache(maxsize=1)
def get_database() -> YOIDatabase:
    return YOIDatabase()


def _normalize_search_text(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[^a-z0-9]+", " ", str(value).lower()),
    ).strip()


def _query_terms(value: str) -> list[str]:
    return [
        term
        for term in _normalize_search_text(value).split()
        if len(term) >= 3 and term not in SEARCH_STOPWORDS
    ]


def get_geography_summary(geography: str) -> dict[str, Any]:
    """Get approved YOI scores and youth population for a region or tract."""
    return get_database().geography_summary(geography)


def compare_geographies(
    geography_a: str,
    geography_b: str,
) -> dict[str, Any]:
    """Compare approved YOI scores for two county regions or tracts."""
    database = get_database()
    first = database.geography_summary(geography_a)
    second = database.geography_summary(geography_b)

    first_scores = first.get("scores_0_to_100", {})
    second_scores = second.get("scores_0_to_100", {})

    shared_domains = sorted(
        set(first_scores).intersection(second_scores)
    )
    differences = {}

    for domain in shared_domains:
        first_value = first_scores.get(domain)
        second_value = second_scores.get(domain)

        if isinstance(first_value, (int, float)) and isinstance(
            second_value,
            (int, float),
        ):
            differences[domain] = round(first_value - second_value, 1)

    first_source = first.get("source_label")
    second_source = second.get("source_label")
    source_label = (
        first_source
        if first_source == second_source
        else "YOI approved geography datasets"
    )

    return {
        "geography_a": first,
        "geography_b": second,
        "score_difference_a_minus_b": differences,
        "score_scale": "0 to 100",
        "source_label": source_label,
        "geography_note": (
            "Regional scores aggregate multiple census tracts. "
            "County-region assignments use the project's tract-to-PUMA "
            "regional crosswalk."
        ),
        "recommended_caveats": [
            "Regional averages can hide variation among census tracts.",
            "Survey-based estimates carry uncertainty.",
        ],
    }


def find_low_opportunity_areas(
    domain: str = "overall",
    limit: int = 5,
    county_region: str | None = None,
) -> dict[str, Any]:
    """Find the lowest-scoring tracts using an approved domain column."""
    return get_database().lowest_areas(
        domain=domain,
        limit=limit,
        county_region=county_region,
    )


def get_indicator_definition(indicator: str) -> dict[str, Any]:
    """Look up an indicator definition, source, year, domain, and notes."""
    path = settings.INDICATOR_META_CSV
    if not path.exists():
        return {
            "error": "Indicator metadata is unavailable.",
            "source_label": SOURCE_LABELS["indicator_metadata"],
        }

    dataframe = pd.read_csv(path)
    terms = _query_terms(indicator)
    if not terms:
        return {
            "error": "Indicator cannot be empty.",
            "source_label": SOURCE_LABELS["indicator_metadata"],
        }

    searchable_columns = [
        column
        for column in dataframe.columns
        if any(
            key in column.lower()
            for key in [
                "indicator",
                "name",
                "label",
                "description",
                "definition",
                "code",
                "source",
                "domain",
            ]
        )
    ]

    if not searchable_columns:
        searchable_columns = list(dataframe.columns)

    normalized_rows = (
        dataframe[searchable_columns]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .map(_normalize_search_text)
    )

    # Prefer rows containing every meaningful query term. If that returns
    # nothing, fall back to rows containing any term so wording variations
    # such as "uninsured-rate" versus "uninsured rate" still work.
    all_terms_mask = normalized_rows.map(
        lambda text: all(term in text for term in terms)
    )
    matches = dataframe.loc[all_terms_mask]

    if matches.empty:
        any_term_mask = normalized_rows.map(
            lambda text: any(term in text for term in terms)
        )
        matches = dataframe.loc[any_term_mask]

    matches = matches.head(5)
    if matches.empty:
        return {
            "indicator": indicator,
            "matches": [],
            "message": "No indicator metadata match was found.",
            "source_label": SOURCE_LABELS["indicator_metadata"],
        }

    return {
        "indicator": indicator,
        "matches": matches.where(matches.notna(), None).to_dict(
            orient="records"
        ),
        "source_label": SOURCE_LABELS["indicator_metadata"],
    }


def get_methodology(topic: str) -> dict[str, Any]:
    """Retrieve approved methodology text for a requested topic.

    The methodology page stores many definitions as a `.column-name`
    followed by a `.column-desc`. Pairing those elements prevents the tool
    from returning only a heading such as "Normalization" without its
    explanation.
    """
    path = settings.METHODOLOGY_FILE
    if not path.exists():
        return {
            "error": "Methodology content is unavailable.",
            "source_label": SOURCE_LABELS["methodology"],
        }

    raw_text = path.read_text(encoding="utf-8", errors="replace")
    sections: list[str] = []

    if path.suffix.lower() in {".html", ".htm"}:
        soup = BeautifulSoup(raw_text, "html.parser")

        # First capture the page's structured definition rows as complete
        # title-and-description sections.
        used_nodes: set[int] = set()
        for row in soup.select(".column-row"):
            title_node = row.select_one(".column-name")
            description_node = row.select_one(".column-desc")
            title = (
                title_node.get_text(" ", strip=True)
                if title_node
                else ""
            )
            description = (
                description_node.get_text(" ", strip=True)
                if description_node
                else ""
            )
            combined = ": ".join(
                part for part in [title, description] if part
            )
            if combined:
                sections.append(combined)
            used_nodes.add(id(row))

        # Also capture ordinary headings together with following paragraphs
        # and list items until the next heading. This covers narrative parts
        # of the methodology page outside `.column-row` blocks.
        for heading in soup.select("h1, h2, h3"):
            title = heading.get_text(" ", strip=True)
            body_parts: list[str] = []
            sibling = heading.find_next_sibling()
            while sibling is not None:
                if getattr(sibling, "name", None) in {"h1", "h2", "h3"}:
                    break
                if "column-row" in (sibling.get("class") or []):
                    sibling = sibling.find_next_sibling()
                    continue
                text = sibling.get_text(" ", strip=True)
                if text:
                    body_parts.append(text)
                if len(" ".join(body_parts)) >= 1200:
                    break
                sibling = sibling.find_next_sibling()

            combined = ": ".join(
                part for part in [title, " ".join(body_parts)] if part
            )
            if combined:
                sections.append(combined)
    else:
        sections = [
            line.strip()
            for line in raw_text.splitlines()
            if line.strip()
        ]

    terms = _query_terms(topic)
    if not terms:
        return {
            "topic": topic,
            "excerpts": [],
            "source_label": SOURCE_LABELS["methodology"],
            "message": "No methodology topic was supplied.",
        }

    ranked: list[tuple[int, int, str]] = []
    for section in sections:
        normalized_section = _normalize_search_text(section)
        matched_terms = sum(term in normalized_section for term in terms)
        if not matched_terms:
            continue

        # Prefer sections matching more query terms, then shorter focused
        # passages over large unrelated page sections.
        ranked.append(
            (
                matched_terms,
                -len(section),
                section,
            )
        )

    ranked.sort(reverse=True)
    excerpts: list[str] = []
    seen: set[str] = set()

    for _, _, section in ranked:
        if section not in seen:
            excerpts.append(section)
            seen.add(section)
        if len(excerpts) >= 4:
            break

    return {
        "topic": topic,
        "excerpts": excerpts,
        "source_label": SOURCE_LABELS["methodology"],
        "message": (
            None
            if excerpts
            else "No directly matching methodology passage was found."
        ),
    }

def generate_map_url(
    geography: str,
    domain: str = "overall",
) -> dict[str, str]:
    """Create a dashboard map URL for a geography and domain."""
    query = urlencode(
        {
            "geography": geography,
            "domain": domain,
        }
    )
    return {
        "url": f"./map.html?{query}",
        "source_label": SOURCE_LABELS["map"],
    }


APPROVED_TOOLS = {
    "get_geography_summary": get_geography_summary,
    "compare_geographies": compare_geographies,
    "find_low_opportunity_areas": find_low_opportunity_areas,
    "get_indicator_definition": get_indicator_definition,
    "get_methodology": get_methodology,
    "generate_map_url": generate_map_url,
}


TOOL_DECLARATIONS = [
    {
        "type": "function",
        "name": "get_geography_summary",
        "description": (
            "Retrieve approved YOI scores and youth population for an "
            "exact county-region name/ID or census-tract GEOID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "geography": {
                    "type": "string",
                    "description": (
                        "Exact county-region name/ID or census-tract GEOID."
                    ),
                }
            },
            "required": ["geography"],
        },
    },
    {
        "type": "function",
        "name": "compare_geographies",
        "description": (
            "Compare approved YOI scores for two county regions or "
            "census tracts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "geography_a": {"type": "string"},
                "geography_b": {"type": "string"},
            },
            "required": ["geography_a", "geography_b"],
        },
    },
    {
        "type": "function",
        "name": "find_low_opportunity_areas",
        "description": (
            "Rank the lowest-scoring census tracts for an approved YOI "
            "domain, optionally within a county region."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": (
                        "overall, economic, education, health, housing, "
                        "safety/environment, mobility/connectivity, "
                        "or youth supports"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 25,
                },
                "county_region": {
                    "type": ["string", "null"],
                    "description": "Optional exact county-region name.",
                },
            },
            "required": ["domain", "limit"],
        },
    },
    {
        "type": "function",
        "name": "get_indicator_definition",
        "description": (
            "Retrieve an approved indicator definition, source, year, "
            "domain, and notes from indicator metadata."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
            },
            "required": ["indicator"],
        },
    },
    {
        "type": "function",
        "name": "get_methodology",
        "description": (
            "Retrieve approved methodology, definitions, and limitations "
            "for a requested YOI topic."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
            },
            "required": ["topic"],
        },
    },
    {
        "type": "function",
        "name": "generate_map_url",
        "description": (
            "Generate a relative dashboard map link for a geography "
            "and domain."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "geography": {"type": "string"},
                "domain": {"type": "string"},
            },
            "required": ["geography"],
        },
    },
]
