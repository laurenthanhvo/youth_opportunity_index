from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import duckdb

from . import settings


SCORE_COLUMN_CANDIDATES = {
    "overall": ["yoi_custom_0_100", "yoi_0_100", "overall_yoi", "yoi_score"],
    "economic": ["economic_score"],
    "education": ["education_score"],
    "health": ["health_score"],
    "housing": ["housing_score"],
    "safety_environment": ["safety_env_score", "safety_environment_score"],
    "mobility_connectivity": [
        "mobility_connectivity_score",
        "mobility_score",
    ],
    "youth_supports": ["youth_supports_score"],
}

DOMAIN_ALIASES = {
    "overall": "overall",
    "yoi": "overall",
    "economic": "economic",
    "education": "education",
    "health": "health",
    "housing": "housing",
    "safety": "safety_environment",
    "environment": "safety_environment",
    "safety_environment": "safety_environment",
    "safety / environment": "safety_environment",
    "mobility": "mobility_connectivity",
    "connectivity": "mobility_connectivity",
    "mobility_connectivity": "mobility_connectivity",
    "mobility / connectivity": "mobility_connectivity",
    "youth supports": "youth_supports",
    "youth_supports": "youth_supports",
}

POPULATION_COLUMN_CANDIDATES = [
    "youth_pop_14_24",
    "total_population",
]

TABLE_SOURCE_LABELS = {
    "tracts": "YOI tract-level components dataset",
    "regions": "YOI county-region components dataset",
}


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def quote_path(path: Path) -> str:
    return str(path).replace("'", "''")


class YOIDatabase:
    """Read-only DuckDB access to approved YOI CSV files."""

    def __init__(self) -> None:
        self.connection = duckdb.connect(database=":memory:")
        self.available_tables: set[str] = set()

        self._register_csv("tracts", settings.TRACT_YOI_CSV)
        self._register_csv("regions", settings.REGION_YOI_CSV)

    def _register_csv(self, table_name: str, path: Path) -> None:
        if not path.exists():
            return

        sql = (
            f"CREATE VIEW {quote_identifier(table_name)} AS "
            f"SELECT * FROM read_csv_auto('{quote_path(path)}', "
            "header=true, sample_size=-1)"
        )
        self.connection.execute(sql)
        self.available_tables.add(table_name)

    def columns(self, table_name: str) -> list[str]:
        self._require_table(table_name)
        rows = self.connection.execute(
            f"PRAGMA table_info({quote_identifier(table_name)})"
        ).fetchall()
        return [row[1] for row in rows]

    def _require_table(self, table_name: str) -> None:
        if table_name not in self.available_tables:
            raise FileNotFoundError(
                f"YOI table '{table_name}' is unavailable. "
                "Check the CSV paths in .env."
            )

    def first_existing_column(
        self,
        table_name: str,
        candidates: list[str],
    ) -> str | None:
        available = set(self.columns(table_name))
        return next((col for col in candidates if col in available), None)

    def resolve_domain_column(
        self,
        table_name: str,
        domain: str,
    ) -> tuple[str, str]:
        normalized = DOMAIN_ALIASES.get(domain.strip().lower())
        if not normalized:
            raise ValueError(
                "Unsupported domain. Use overall, economic, education, "
                "health, housing, safety/environment, "
                "mobility/connectivity, or youth supports."
            )

        column = self.first_existing_column(
            table_name,
            SCORE_COLUMN_CANDIDATES[normalized],
        )
        if not column:
            raise ValueError(
                f"No score column was found for domain '{domain}' "
                f"in the {table_name} data."
            )

        return normalized, column

    def find_geography(
        self,
        geography: str,
    ) -> dict[str, Any]:
        query = geography.strip()
        if not query:
            raise ValueError("Geography cannot be empty.")

        searches = [
            (
                "regions",
                [
                    "county_region",
                    "county_region_id",
                    "region",
                    "region_id",
                ],
                "county region",
            ),
            (
                "tracts",
                [
                    "tract_geoid",
                    "geoid",
                    "GEOID",
                    "tract",
                ],
                "census tract",
            ),
        ]

        for table_name, candidates, geography_type in searches:
            if table_name not in self.available_tables:
                continue

            available = set(self.columns(table_name))
            search_columns = [
                column for column in candidates if column in available
            ]

            for column in search_columns:
                identifier = quote_identifier(column)

                if table_name == "tracts":
                    sql = (
                        f"SELECT * FROM {quote_identifier(table_name)} "
                        f"WHERE TRY_CAST({identifier} AS BIGINT) "
                        "= TRY_CAST(? AS BIGINT) LIMIT 1"
                    )
                else:
                    sql = (
                        f"SELECT * FROM {quote_identifier(table_name)} "
                        f"WHERE lower(trim(CAST({identifier} AS VARCHAR))) "
                        "= lower(trim(?)) LIMIT 1"
                    )

                cursor = self.connection.execute(sql, [query])
                row = cursor.fetchone()
                if row is not None:
                    columns = [item[0] for item in cursor.description]
                    return {
                        "table": table_name,
                        "geography_type": geography_type,
                        "matched_column": column,
                        "record": dict(zip(columns, row)),
                    }

        raise LookupError(
            f"No exact match was found for '{geography}'. "
            "The starter currently supports county-region names/IDs "
            "and census-tract GEOIDs."
        )

    def geography_summary(
        self,
        geography: str,
    ) -> dict[str, Any]:
        match = self.find_geography(geography)
        record = match["record"]
        table_name = match["table"]

        score_columns: dict[str, str] = {}
        for domain, candidates in SCORE_COLUMN_CANDIDATES.items():
            column = self.first_existing_column(table_name, candidates)
            if column:
                score_columns[domain] = column

        population_column = self.first_existing_column(
            table_name,
            POPULATION_COLUMN_CANDIDATES,
        )

        scores = {
            domain: _score_to_100(record.get(column), column)
            for domain, column in score_columns.items()
        }

        identity_columns = [
            "tract_geoid",
            "county_region",
            "county_region_id",
            "puma_codes",
            "tract_count",
        ]
        identity = {
            column: (
                _normalize_tract_geoid(record.get(column))
                if column == "tract_geoid"
                else record.get(column)
            )
            for column in identity_columns
            if column in record
        }

        youth_population = (
            _round_population(record.get(population_column))
            if population_column
            else None
        )

        if table_name == "regions":
            geography_note = (
                "Regional scores aggregate multiple census tracts. "
                "County-region assignments use the project's "
                "tract-to-PUMA regional crosswalk."
            )
            caveats = [
                "Regional averages can hide variation among census tracts.",
                "Survey-based estimates carry uncertainty.",
            ]
        else:
            geography_note = (
                "Census tracts are statistical areas and may not match "
                "community-recognized neighborhood boundaries."
            )
            caveats = [
                "Survey-based estimates carry uncertainty.",
                "Census-tract boundaries may not match neighborhoods.",
            ]

        return {
            "requested_geography": geography,
            "geography_type": match["geography_type"],
            "identity": identity,
            "youth_population": youth_population,
            "population_is_estimate": youth_population is not None,
            "population_source_column": population_column,
            "scores_0_to_100": scores,
            "score_scale": "0 to 100",
            "source_label": TABLE_SOURCE_LABELS[table_name],
            "geography_note": geography_note,
            "recommended_caveats": caveats,
        }

    def lowest_areas(
        self,
        domain: str,
        limit: int,
        county_region: str | None = None,
    ) -> dict[str, Any]:
        self._require_table("tracts")

        safe_limit = max(1, min(int(limit), 25))
        normalized_domain, score_column = self.resolve_domain_column(
            "tracts",
            domain,
        )

        geoid_column = self.first_existing_column(
            "tracts",
            ["tract_geoid", "geoid", "GEOID", "tract"],
        )
        if not geoid_column:
            raise ValueError("No tract identifier column was found.")

        select_columns = [
            f"{quote_identifier(geoid_column)} AS geography",
            f"{quote_identifier(score_column)} AS score",
        ]

        region_column = self.first_existing_column(
            "tracts",
            ["county_region", "region"],
        )
        if region_column:
            select_columns.append(
                f"{quote_identifier(region_column)} AS county_region"
            )

        population_column = self.first_existing_column(
            "tracts",
            POPULATION_COLUMN_CANDIDATES,
        )
        if population_column:
            select_columns.append(
                f"{quote_identifier(population_column)} AS youth_population"
            )

        where_parts = [
            f"{quote_identifier(score_column)} IS NOT NULL"
        ]
        parameters: list[Any] = []

        if county_region:
            if not region_column:
                raise ValueError(
                    "The tract data do not contain a county-region column."
                )
            where_parts.append(
                f"lower(trim(CAST({quote_identifier(region_column)} "
                "AS VARCHAR))) = lower(trim(?))"
            )
            parameters.append(county_region)

        parameters.append(safe_limit)

        sql = (
            "SELECT "
            + ", ".join(select_columns)
            + f" FROM {quote_identifier('tracts')} "
            + " WHERE "
            + " AND ".join(where_parts)
            + f" ORDER BY {quote_identifier(score_column)} ASC "
            + " LIMIT ?"
        )

        cursor = self.connection.execute(sql, parameters)
        columns_out = [item[0] for item in cursor.description]
        rows = []

        for row in cursor.fetchall():
            output_row: dict[str, Any] = {}

            for key, value in zip(columns_out, row):
                if key == "geography":
                    output_row[key] = _normalize_tract_geoid(value)
                elif key == "score":
                    output_row[key] = _score_to_100(
                        value,
                        score_column,
                    )
                elif key == "youth_population":
                    output_row[key] = _round_population(value)
                else:
                    output_row[key] = _to_number(value)

            rows.append(output_row)

        return {
            "domain": normalized_domain,
            "score_column": score_column,
            "score_scale": "0 to 100",
            "county_region_filter": county_region,
            "areas": rows,
            "source_label": TABLE_SOURCE_LABELS["tracts"],
            "geography_note": (
                "Census tracts are statistical areas and may not match "
                "community-recognized neighborhood boundaries."
            ),
            "recommended_caveats": [
                "Survey-based estimates carry uncertainty.",
                "Census-tract boundaries may not match neighborhoods.",
            ],
        }


def _normalize_tract_geoid(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]

    digits = re.sub(r"\D", "", text)
    return digits.zfill(11) if digits else text


def _score_to_100(
    value: Any,
    source_column: str,
) -> Any:
    number = _to_number(value)
    if not isinstance(number, (int, float)):
        return number

    if "0_100" not in source_column and 0 <= number <= 1:
        number *= 100

    return round(number, 1)


def _round_population(value: Any) -> Any:
    number = _to_number(value)
    if isinstance(number, (int, float)):
        return round(number)
    return number


def _to_number(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value

    try:
        number = float(value)
    except (TypeError, ValueError):
        return value

    return int(number) if number.is_integer() else round(number, 4)
