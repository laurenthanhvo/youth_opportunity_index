from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import duckdb
import pandas as pd

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

REGION_BY_PUMA = {
    "7308": "Metro San Diego",
    "7310": "Metro San Diego",
    "7311": "Metro San Diego",
    "7312": "Metro San Diego",
    "7315": "Metro San Diego",
    "7316": "Metro San Diego",
    "7317": "Metro San Diego",
    "7327": "Metro San Diego",

    "7301": "North County",
    "7306": "North County",
    "7323": "North County",
    "7324": "North County",
    "7325": "North County",
    "7326": "North County",

    "7322": "South San Diego",
    "7328": "South San Diego",
    "7329": "South San Diego",
    "7330": "South San Diego",

    "7302": "East San Diego",
    "7307": "East San Diego",
    "7313": "East San Diego",
    "7314": "East San Diego",
}

REGION_ID_BY_NAME = {
    "Metro San Diego": "metro_san_diego",
    "North County": "north_county",
    "South San Diego": "south_san_diego",
    "East San Diego": "east_san_diego",
}


REGION_ALIASES = {
    "metro": "Metro San Diego",
    "metro san diego": "Metro San Diego",
    "san diego metro": "Metro San Diego",

    "north": "North County",
    "north county": "North County",

    "south": "South San Diego",
    "south county": "South San Diego",
    "south san diego": "South San Diego",

    "east": "East San Diego",
    "east county": "East San Diego",
    "east san diego": "East San Diego",
}


def normalize_county_region(value: str) -> str:
    text = str(value or "").strip()
    return REGION_ALIASES.get(text.lower(), text)

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

        self._register_tract_region_crosswalk(
            settings.TRACT_PUMA_CROSSWALK
        )

        self._create_enriched_tracts_view()

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

    def _register_tract_region_crosswalk(
        self,
        path: Path,
    ) -> None:
        if not path.exists():
            return

        dataframe = pd.read_csv(
            path,
            dtype=str,
        )

        required = {
            "STATEFP",
            "COUNTYFP",
            "TRACTCE",
            "PUMA5CE",
        }

        if not required.issubset(dataframe.columns):
            return

        dataframe["STATEFP"] = (
            dataframe["STATEFP"]
            .astype(str)
            .str.zfill(2)
        )

        dataframe["COUNTYFP"] = (
            dataframe["COUNTYFP"]
            .astype(str)
            .str.zfill(3)
        )

        dataframe["TRACTCE"] = (
            dataframe["TRACTCE"]
            .astype(str)
            .str.zfill(6)
        )

        dataframe = dataframe[
            (dataframe["STATEFP"] == "06")
            & (dataframe["COUNTYFP"] == "073")
        ].copy()

        dataframe["tract_geoid"] = (
            dataframe["STATEFP"]
            + dataframe["COUNTYFP"]
            + dataframe["TRACTCE"]
        )

        dataframe["puma_code"] = (
            dataframe["PUMA5CE"]
            .astype(str)
            .str.replace(
                r"\D",
                "",
                regex=True,
            )
            .str.zfill(5)
            .str[-4:]
        )

        dataframe["county_region"] = (
            dataframe["puma_code"]
            .map(REGION_BY_PUMA)
        )

        dataframe["county_region_id"] = (
            dataframe["county_region"]
            .map(REGION_ID_BY_NAME)
        )

        dataframe = dataframe.dropna(
            subset=["county_region"]
        )

        dataframe = dataframe[
            [
                "tract_geoid",
                "county_region",
                "county_region_id",
            ]
        ].drop_duplicates(
            subset=["tract_geoid"]
        )

        self.connection.register(
            "_tract_region_dataframe",
            dataframe,
        )

        self.connection.execute(
            """
            CREATE TABLE tract_region_crosswalk AS
            SELECT * FROM _tract_region_dataframe
            """
        )

        self.connection.unregister(
            "_tract_region_dataframe"
        )

        self.available_tables.add(
            "tract_region_crosswalk"
        )

    def _create_enriched_tracts_view(self) -> None:
        if (
            "tracts" not in self.available_tables
            or "tract_region_crosswalk" not in self.available_tables
        ):
            return

        geoid_column = self.first_existing_column(
            "tracts",
            ["tract_geoid", "geoid", "GEOID", "tract"],
        )

        if not geoid_column:
            return

        self.connection.execute(
            f"""
            CREATE VIEW tracts_enriched AS
            SELECT
                t.*,
                x.county_region,
                x.county_region_id
            FROM tracts AS t
            LEFT JOIN tract_region_crosswalk AS x
                ON TRY_CAST(
                    t.{quote_identifier(geoid_column)} AS BIGINT
                )
                =
                TRY_CAST(
                    x.tract_geoid AS BIGINT
                )
            """
        )

        self.available_tables.add(
            "tracts_enriched"
        )

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

        region_query = normalize_county_region(query)

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

                search_value = (
                    query
                    if table_name == "tracts"
                    else region_query
                )

                cursor = self.connection.execute(
                    sql,
                    [search_value],
                )
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

    def analyze_regions(
        self,
        domains: list[str] | None = None,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        self._require_table("regions")

        score_columns: dict[str, str] = {}

        for domain_name, candidates in SCORE_COLUMN_CANDIDATES.items():
            if domain_name == "overall":
                continue

            column = self.first_existing_column(
                "regions",
                candidates,
            )

            if column:
                score_columns[domain_name] = column

        if domains:
            requested_domains = []

            for domain in domains:
                normalized = DOMAIN_ALIASES.get(
                    domain.strip().lower()
                )

                if (
                    normalized
                    and normalized != "overall"
                    and normalized in score_columns
                ):
                    requested_domains.append(normalized)

            requested_domains = list(dict.fromkeys(requested_domains))

            if not requested_domains:
                raise ValueError(
                    "None of the requested domains were recognized."
                )
        else:
            requested_domains = list(score_columns.keys())

        region_column = self.first_existing_column(
            "regions",
            ["county_region", "region"],
        )

        if not region_column:
            raise ValueError(
                "No county-region column was found."
            )

        select_columns = [
            quote_identifier(region_column)
        ]

        for domain in requested_domains:
            select_columns.append(
                quote_identifier(score_columns[domain])
            )

        cursor = self.connection.execute(
            "SELECT "
            + ", ".join(select_columns)
            + f" FROM {quote_identifier('regions')}"
        )

        regions = []

        normalized_weights: dict[str, float] = {}

        for key, value in (weights or {}).items():
            normalized = DOMAIN_ALIASES.get(
                str(key).strip().lower()
            )

            if normalized in requested_domains:
                normalized_weights[normalized] = float(value)

        for row in cursor.fetchall():
            region_name = row[0]

            scores: dict[str, Any] = {}

            for index, domain in enumerate(
                requested_domains,
                start=1,
            ):
                scores[domain] = _score_to_100(
                    row[index],
                    score_columns[domain],
                )

            numeric_scores = {
                domain: value
                for domain, value in scores.items()
                if isinstance(value, (int, float))
            }

            sorted_scores = sorted(
                numeric_scores.items(),
                key=lambda item: item[1],
            )

            weakest_domains = [
                {
                    "domain": domain,
                    "score": score,
                }
                for domain, score in sorted_scores[:2]
            ]

            strongest_domains = [
                {
                    "domain": domain,
                    "score": score,
                }
                for domain, score in reversed(sorted_scores[-2:])
            ]

            if numeric_scores:
                lowest_domain, lowest_score = min(
                    numeric_scores.items(),
                    key=lambda item: item[1],
                )

                highest_domain, highest_score = max(
                    numeric_scores.items(),
                    key=lambda item: item[1],
                )

                domain_gap = round(
                    highest_score - lowest_score,
                    1,
                )
            else:
                lowest_domain = None
                lowest_score = None
                highest_domain = None
                highest_score = None
                domain_gap = None

            if numeric_scores:
                weighted_total = 0.0
                total_weight = 0.0

                for domain, score in numeric_scores.items():
                    weight = normalized_weights.get(
                        domain,
                        1.0,
                    )

                    weighted_total += score * weight
                    total_weight += weight

                combined_score = (
                    round(weighted_total / total_weight, 1)
                    if total_weight > 0
                    else None
                )
            else:
                combined_score = None

            regions.append(
                {
                    "region": region_name,
                    "scores_0_to_100": scores,
                    "weakest_domains": weakest_domains,
                    "strongest_domains": strongest_domains,
                    "lowest_domain": lowest_domain,
                    "lowest_domain_score": lowest_score,
                    "highest_domain": highest_domain,
                    "highest_domain_score": highest_score,
                    "domain_gap": domain_gap,
                    "combined_requested_domain_score": combined_score,
                }
            )

        regions_ranked = sorted(
            regions,
            key=lambda item: (
                item["combined_requested_domain_score"]
                if item["combined_requested_domain_score"] is not None
                else float("inf")
            ),
        )

        largest_internal_gap = max(
            regions,
            key=lambda item: (
                item["domain_gap"]
                if item["domain_gap"] is not None
                else -1
            ),
        )

        domain_ranges = []

        for domain in requested_domains:
            values = [
                (
                    region["region"],
                    region["scores_0_to_100"].get(domain),
                )
                for region in regions
            ]

            values = [
                value
                for value in values
                if isinstance(value[1], (int, float))
            ]

            if not values:
                continue

            min_region, min_score = min(
                values,
                key=lambda item: item[1],
            )

            max_region, max_score = max(
                values,
                key=lambda item: item[1],
            )

            domain_ranges.append(
                {
                    "domain": domain,
                    "minimum_region": min_region,
                    "minimum_score": min_score,
                    "maximum_region": max_region,
                    "maximum_score": max_score,
                    "range": round(
                        max_score - min_score,
                        1,
                    ),
                }
            )

        domain_ranges.sort(
            key=lambda item: item["range"],
            reverse=True,
        )

        return {
            "domains_analyzed": requested_domains,
            "weights": normalized_weights or None,
            "regions": regions,
            "regions_ranked_by_combined_score": regions_ranked,
            "largest_internal_domain_gap": largest_internal_gap,
            "domain_ranges_across_regions": domain_ranges,
            "source_label": TABLE_SOURCE_LABELS["regions"],
            "geography_note": (
                "Regional scores aggregate multiple census tracts. "
                "County-region assignments use the project's "
                "tract-to-PUMA regional crosswalk."
            ),
            "recommended_caveats": [
                "Regional averages can hide variation among census tracts.",
                "Survey-based estimates carry uncertainty.",
            ],
        }

    def lowest_areas(
        self,
        domain: str,
        limit: int,
        county_region: str | None = None,
    ) -> dict[str, Any]:
        tract_table = (
            "tracts_enriched"
            if "tracts_enriched" in self.available_tables
            else "tracts"
        )

        self._require_table(tract_table)

        safe_limit = max(1, min(int(limit), 25))

        normalized_domain, score_column = self.resolve_domain_column(
            tract_table,
            domain,
        )

        geoid_column = self.first_existing_column(
            tract_table,
            ["tract_geoid", "geoid", "GEOID", "tract"],
        )

        if not geoid_column:
            raise ValueError("No tract identifier column was found.")

        # Find every available YOI score column.
        score_columns: dict[str, str] = {}

        for domain_name, candidates in SCORE_COLUMN_CANDIDATES.items():
            column = self.first_existing_column(
                tract_table,
                candidates,
            )

            if column:
                score_columns[domain_name] = column

        select_columns = [
            f"{quote_identifier(geoid_column)} AS geography",
            f"{quote_identifier(score_column)} AS score",
        ]

        # Return all domain scores for every ranked tract.
        for domain_name, column in score_columns.items():
            select_columns.append(
                f"{quote_identifier(column)} AS score__{domain_name}"
            )

        region_column = self.first_existing_column(
            tract_table,
            ["county_region", "region"],
        )

        if region_column:
            select_columns.append(
                f"{quote_identifier(region_column)} AS county_region"
            )

        population_column = self.first_existing_column(
            tract_table,
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
            county_region = normalize_county_region(county_region)

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
            + f" FROM {quote_identifier(tract_table)} "
            + " WHERE "
            + " AND ".join(where_parts)
            + f" ORDER BY {quote_identifier(score_column)} ASC "
            + " LIMIT ?"
        )

        cursor = self.connection.execute(
            sql,
            parameters,
        )

        columns_out = [
            item[0]
            for item in cursor.description
        ]

        rows = []

        for row in cursor.fetchall():
            output_row: dict[str, Any] = {}
            scores: dict[str, Any] = {}

            for key, value in zip(columns_out, row):

                if key == "geography":
                    output_row[key] = _normalize_tract_geoid(value)

                elif key == "score":
                    output_row[key] = _score_to_100(
                        value,
                        score_column,
                    )

                elif key.startswith("score__"):
                    domain_name = key.replace(
                        "score__",
                        "",
                        1,
                    )

                    source_column = score_columns[domain_name]

                    scores[domain_name] = _score_to_100(
                        value,
                        source_column,
                    )

                elif key == "youth_population":
                    output_row[key] = _round_population(value)

                else:
                    output_row[key] = _to_number(value)

            output_row["scores_0_to_100"] = scores

            # Identify the weakest actual domain, excluding overall YOI.
            domain_scores = {
                name: value
                for name, value in scores.items()
                if (
                    name != "overall"
                    and isinstance(value, (int, float))
                )
            }

            if domain_scores:
                weakest_domain = min(
                    domain_scores,
                    key=domain_scores.get,
                )

                output_row["weakest_domain"] = weakest_domain
                output_row["weakest_domain_score"] = domain_scores[
                    weakest_domain
                ]

            rows.append(output_row)

        # Calculate averages for the selected ranked group.
        group_averages: dict[str, float] = {}

        for domain_name in score_columns:
            values = [
                row["scores_0_to_100"].get(domain_name)
                for row in rows
            ]

            values = [
                value
                for value in values
                if isinstance(value, (int, float))
            ]

            if values:
                group_averages[domain_name] = round(
                    sum(values) / len(values),
                    1,
                )

        # Calculate countywide averages using DuckDB.
        average_select = [
            (
                f"AVG({quote_identifier(column)}) "
                f"AS avg__{domain_name}"
            )
            for domain_name, column in score_columns.items()
        ]

        countywide_averages: dict[str, Any] = {}

        if average_select:
            avg_cursor = self.connection.execute(
                "SELECT "
                + ", ".join(average_select)
                + f" FROM {quote_identifier(tract_table)}"
            )

            avg_row = avg_cursor.fetchone()

            if avg_row is not None:
                avg_columns = [
                    item[0]
                    for item in avg_cursor.description
                ]

                for key, value in zip(avg_columns, avg_row):
                    domain_name = key.replace(
                        "avg__",
                        "",
                        1,
                    )

                    source_column = score_columns[domain_name]

                    countywide_averages[domain_name] = (
                        _score_to_100(
                            value,
                            source_column,
                        )
                    )

        return {
            "domain": normalized_domain,
            "score_column": score_column,
            "score_scale": "0 to 100",
            "county_region_filter": county_region,
            "areas": rows,
            "selected_group_domain_averages": group_averages,
            "countywide_domain_averages": countywide_averages,
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

    def lowest_domain_overlap(
        self,
        domain_a: str,
        domain_b: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        self._require_table("tracts")

        safe_limit = max(
            1,
            min(int(limit), 100),
        )

        normalized_a, column_a = self.resolve_domain_column(
            "tracts",
            domain_a,
        )

        normalized_b, column_b = self.resolve_domain_column(
            "tracts",
            domain_b,
        )

        geoid_column = self.first_existing_column(
            "tracts",
            ["tract_geoid", "geoid", "GEOID", "tract"],
        )

        if not geoid_column:
            raise ValueError(
                "No tract identifier column was found."
            )

        def get_bottom_geoids(
            score_column: str,
        ) -> list[str]:
            cursor = self.connection.execute(
                (
                    "SELECT "
                    f"{quote_identifier(geoid_column)} "
                    f"FROM {quote_identifier('tracts')} "
                    f"WHERE {quote_identifier(score_column)} IS NOT NULL "
                    f"ORDER BY {quote_identifier(score_column)} ASC "
                    "LIMIT ?"
                ),
                [safe_limit],
            )

            return [
                _normalize_tract_geoid(row[0])
                for row in cursor.fetchall()
            ]

        bottom_a = get_bottom_geoids(column_a)
        bottom_b = get_bottom_geoids(column_b)

        set_a = set(bottom_a)
        set_b = set(bottom_b)

        overlap = sorted(
            set_a.intersection(set_b)
        )

        overlap_count = len(overlap)

        percentage_of_a = (
            round(
                overlap_count / len(bottom_a) * 100,
                1,
            )
            if bottom_a
            else 0.0
        )

        return {
            "domain_a": normalized_a,
            "domain_b": normalized_b,
            "limit": safe_limit,
            "bottom_domain_a_tracts": bottom_a,
            "bottom_domain_b_tracts": bottom_b,
            "overlap_tracts": overlap,
            "overlap_count": overlap_count,
            "percentage_of_domain_a_bottom_group": percentage_of_a,
            "source_label": TABLE_SOURCE_LABELS["tracts"],
            "recommended_caveats": [
                "Survey-based estimates carry uncertainty.",
                "Census-tract boundaries may not match neighborhoods.",
            ],
        }

    def areas_with_reference_filter(
        self,
        rank_domain: str,
        filter_domain: str,
        reference_statistic: str = "median",
        operator: str = "above",
        limit: int = 5,
    ) -> dict[str, Any]:
        self._require_table("tracts")

        safe_limit = max(
            1,
            min(int(limit), 25),
        )

        normalized_rank, rank_column = self.resolve_domain_column(
            "tracts",
            rank_domain,
        )

        normalized_filter, filter_column = self.resolve_domain_column(
            "tracts",
            filter_domain,
        )

        statistic = reference_statistic.strip().lower()

        statistic_sql = {
            "median": "MEDIAN",
            "average": "AVG",
            "mean": "AVG",
        }.get(statistic)

        if not statistic_sql:
            raise ValueError(
                "Unsupported reference statistic. Use median or average."
            )

        normalized_statistic = (
            "average"
            if statistic in {"average", "mean"}
            else "median"
        )

        operator_key = operator.strip().lower()

        operator_sql = {
            "above": ">",
            "below": "<",
            "at_or_above": ">=",
            "at_or_below": "<=",
        }.get(operator_key)

        if not operator_sql:
            raise ValueError(
                "Unsupported operator. Use above, below, "
                "at_or_above, or at_or_below."
            )

        reference_cursor = self.connection.execute(
            (
                f"SELECT {statistic_sql}("
                f"{quote_identifier(filter_column)}) "
                f"FROM {quote_identifier('tracts')} "
                f"WHERE {quote_identifier(filter_column)} IS NOT NULL"
            )
        )

        reference_value_raw = reference_cursor.fetchone()[0]

        geoid_column = self.first_existing_column(
            "tracts",
            ["tract_geoid", "geoid", "GEOID", "tract"],
        )

        if not geoid_column:
            raise ValueError(
                "No tract identifier column was found."
            )

        population_column = self.first_existing_column(
            "tracts",
            POPULATION_COLUMN_CANDIDATES,
        )

        select_columns = [
            f"{quote_identifier(geoid_column)} AS geography",
            f"{quote_identifier(rank_column)} AS rank_score",
            f"{quote_identifier(filter_column)} AS filter_score",
        ]

        if population_column:
            select_columns.append(
                f"{quote_identifier(population_column)} "
                "AS youth_population"
            )

        sql = (
            "SELECT "
            + ", ".join(select_columns)
            + f" FROM {quote_identifier('tracts')} "
            + f"WHERE {quote_identifier(filter_column)} "
            + f"{operator_sql} ? "
            + f"AND {quote_identifier(rank_column)} IS NOT NULL "
            + f"ORDER BY {quote_identifier(rank_column)} ASC "
            + "LIMIT ?"
        )

        cursor = self.connection.execute(
            sql,
            [
                reference_value_raw,
                safe_limit,
            ],
        )

        columns_out = [
            item[0]
            for item in cursor.description
        ]

        areas = []

        for row in cursor.fetchall():
            output: dict[str, Any] = {}

            for key, value in zip(columns_out, row):
                if key == "geography":
                    output[key] = _normalize_tract_geoid(value)

                elif key == "rank_score":
                    output[key] = _score_to_100(
                        value,
                        rank_column,
                    )

                elif key == "filter_score":
                    output[key] = _score_to_100(
                        value,
                        filter_column,
                    )

                elif key == "youth_population":
                    output[key] = _round_population(value)

                else:
                    output[key] = _to_number(value)

            areas.append(output)

        return {
            "rank_domain": normalized_rank,
            "filter_domain": normalized_filter,
            "reference_statistic": normalized_statistic,
            "reference_value": _score_to_100(
                reference_value_raw,
                filter_column,
            ),
            "operator": operator_key,
            "areas": areas,
            "score_scale": "0 to 100",
            "source_label": TABLE_SOURCE_LABELS["tracts"],
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
