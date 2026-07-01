# YOI / Workforce Report Validation Summary

## Report benchmarks used

This validation uses the Workforce report's exact region-level benchmark values from:

- Figure 10, page 15: youth demographic snapshot and education/employment outcomes.
- Figure 2, page 6: youth population characteristics across the four regions.
- Figure 22, page 27: number of sites offering education, employment, and wraparound services by region.
- Figure 7, page 13: limitations, which state that findings should be interpreted directionally rather than exactly.

## Report pattern to validate

From Figure 10, the largest youth population is in **Metro San Diego** (180,692 youth ages 14-24). The highest youth unemployment rate is in **South San Diego** (31.0%), while the highest dropout rate is in **East San Diego** (11.6%). The lowest unemployment rate is in **North County** (9.0%).

From Figure 2, the largest not-in-school youth count is in **Metro San Diego** (52,661); the largest refugee youth count is in **East San Diego** (2,527); and the largest youth homelessness count is in **Metro San Diego** (2,352).

From Figure 22, Metro San Diego has the highest service-site counts in all three broad domains: education-related services, employment-related services, and wraparound services. South San Diego and East San Diego have substantially smaller service footprints.

## Validation outputs

- Direct metric validation status counts: missing_dashboard_column: 68, review: 4
- Service validation status counts: review: 12
- Domain trend validation status counts: direction_match: 6

## Files generated

- `data/processed/validation/workforce_report_metric_level_validation.csv`
- `data/processed/validation/workforce_report_service_validation.csv`
- `data/processed/validation/workforce_report_domain_trend_tests.csv`
- `data/processed/validation/workforce_report_region_rank_summary.csv`
- `data/processed/validation/service_category_audit.csv`

## Interpretation guidance

Treat exact numeric differences as a debugging signal, not automatically as an error. The report itself notes limitations from age-range differences, proxy indicators, geographic boundary mismatches, coverage/reporting gaps, timing alignment, and service-data reliability. A strong validation result is therefore: (1) the same four-region geography, (2) the same high/low regional pattern, and (3) reasonable numeric closeness where the dashboard uses the same metric definition and data vintage.
