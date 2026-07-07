# Workforce Report Validation Draft

## Countywide context benchmarks

- CDE adjusted cohort graduation rate: **84.6%**
- CDE four-year cohort dropout rate: **7.9%**
- CDE homeless students: **23,641**
- CDE homeless student rate: **4.7%**
- CDE English learner students: **74,812**
- ACS PUMS youth unemployment rate, ages 16–19: **18.8%**
- ACS PUMS labor force participation rate, ages 16–19: **33.0%**

## County-region YOI pattern

- The lowest overall YOI region is **North County** with an overall score of **44.3/100**.
- The highest overall YOI region is **Metro San Diego** with an overall score of **51.7/100**.
- The lowest economic-domain region is **South San Diego** with an economic score of **38.0/100**.
- The lowest youth-supports region is **North County** with a youth-supports score of **28.2/100**.

## Clean county-region table

county_region,overall_yoi_0_100,overall_rank_low_to_high,economic_0_100,economic_rank_low_to_high,education_0_100,health_0_100,housing_0_100,safety_env_0_100,mobility_connectivity_0_100,youth_supports_0_100,lowest_domain,lowest_domain_score,strongest_domain,strongest_domain_score,youth_population_basis
North County,44.3,1,46.3,3,42.4,41.6,44.2,53.3,53.9,28.2,Youth Supports,28.2,Mobility / Connectivity,53.9,132527
East San Diego,44.6,2,44.3,2,44.9,34.0,49.9,53.4,45.0,40.3,Health,34.0,Safety / Env,53.4,73290
South San Diego,45.7,3,38.0,1,51.1,38.6,47.4,47.8,41.9,55.3,Economic,38.0,Youth Supports,55.3,90127
Metro San Diego,51.7,4,46.7,4,58.9,48.4,41.9,47.5,55.3,63.3,Housing,41.9,Youth Supports,63.3,181273


## Validation interpretation

The dashboard should be validated directionally against the Workforce report rather than treated as an exact replication. The Workforce report combines countywide CDE indicators, ACS/PUMS labor-force indicators, and regional findings, while the dashboard computes normalized YOI scores across tracts, ZIP codes, districts, and county regions.

The strongest validation use is therefore regional pattern alignment: whether the dashboard identifies similar areas of labor-market, education, service-access, and youth-support concern as the Workforce report. Countywide indicators such as graduation rate, dropout rate, homelessness, English learners, and PUMS youth unemployment should be used as context benchmarks, not as selected-tract values.

## Important limitation

The dashboard's region-level YOI scores are useful for comparing opportunity patterns, but the Workforce report metrics do not all share the same geography. CDE indicators are school/county based, PUMS unemployment is PUMA/county based, and ACS youth-population estimates are tract based. For this reason, the validation supports directional consistency, not exact one-to-one numeric agreement.