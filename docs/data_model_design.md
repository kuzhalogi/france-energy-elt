# Data Model Design

Describes the warehouse tables dbt builds: what each one holds, how they connect,
and the conventions used. The warehouse is Postgres; all of this is built and
maintained by dbt.

## The shape

It's a star schema: two shared dimensions and three fact tables, all in the
`marts` schema. The dimensions are "conformed" every fact joins to the same
`dim_region` and (for daily facts) `dim_date`.

```
        dim_date                         dim_region
       (date PK)                       (region_code PK)
           |                                  |
           +------ fact_consumption_daily ----+
           +------ fact_weather_daily --------+
                                              |
                   fact_production_annual ----+
                   (joins region; year is its own time key)
```

Facts hold the measures (consumption, temperature, production). Dimensions hold
the descriptive attributes (region name, calendar fields). They join on
`region_code` and `date`.

## dim_region

One row per INSEE region. Built by unioning the region code/name from all five
staging models, so it carries all 13 regions even though daily consumption only
covers 12.

| Column          | Type | Notes                   |
| --------------- | ---- | ----------------------- |
| `region_code` | int  | INSEE code, primary key |
| `region_name` | text | Official region name    |

## dim_date

One row per calendar day, 2013-01-01 → 2026-12-31 (~5,113 rows). Generated in dbt
with a native Postgres `generate_series` spine no source file, no extra package.

| Column           | Type    | Notes                         |
| ---------------- | ------- | ----------------------------- |
| `date`         | date    | primary key                   |
| `date_key`     | int     | YYYYMMDD form (e.g. 20200131) |
| `year`         | int     |                               |
| `quarter`      | int     | 1–4                          |
| `month`        | int     | 1–12                         |
| `day_of_month` | int     |                               |
| `day_of_week`  | int     | 1 = Monday … 7 = Sunday      |
| `day_name`     | text    | e.g. Monday                   |
| `month_name`   | text    | e.g. January                  |
| `is_weekend`   | boolean | true for Sat/Sun              |

## fact_consumption_daily

Daily electricity consumption per region, rolled up from the half-hourly source.
Grain: one row per region per day (~57k rows: 12 regions × ~4,800 days).

| Column              | Type    | Notes                                    |
| ------------------- | ------- | ---------------------------------------- |
| `date`            | date    | join to dim_date                         |
| `region_code`     | int     | join to dim_region                       |
| `consumption_mwh` | numeric | daily energy: sum(half-hourly MW) × 0.5 |
| `avg_load_mw`     | numeric | average load across the day              |
| `peak_load_mw`    | numeric | highest half-hourly reading              |
| `min_load_mw`     | numeric | lowest half-hourly reading               |
| `n_intervals`     | int     | half-hourly rows aggregated (~48)        |

The MWh conversion: each half-hour at P MW carries P × 0.5 MWh of energy, so daily
energy is `sum(consumption_mw) × 0.5`.

## fact_weather_daily

Daily temperature per region. Same grain as consumption (date × region), so the
two join directly for "consumption vs temperature" analysis.

| Column          | Type    | Notes              |
| --------------- | ------- | ------------------ |
| `date`        | date    | join to dim_date   |
| `region_code` | int     | join to dim_region |
| `t_min_c`     | numeric | daily min °C      |
| `t_max_c`     | numeric | daily max °C      |
| `t_mean_c`    | numeric | daily mean °C     |

Covers 2016 onward, so joins to 2013–2015 consumption return null temperature.

## fact_production_annual

Annual production by source per region. Grain: one row per region per year (~234
rows, 2008–2025). Joins `dim_region` on `region_code`; `year` is its own time key
(annual grain, so it doesn't use the daily `dim_date`).

| Column                   | Type    | Notes                            |
| ------------------------ | ------- | -------------------------------- |
| `year`                 | int     |                                  |
| `region_code`          | int     | join to dim_region               |
| `nuclear_gwh`          | numeric | nulls filled with 0 (structural) |
| `thermal_gwh`          | numeric |                                  |
| `hydro_gwh`            | numeric |                                  |
| `wind_gwh`             | numeric |                                  |
| `solar_gwh`            | numeric |                                  |
| `bioenergy_gwh`        | numeric |                                  |
| `total_production_gwh` | numeric | sum of the six source columns    |

Built from the filière file only. The ENR renewable file is cleaned and staged
(`stg_production_enr`) but not yet merged here adding a renewable-share metric
is a planned extension.

## How the joins work

```sql
select ...
from marts.fact_consumption_daily fc
left join marts.dim_date   dd on fc.date        = dd.date
left join marts.dim_region dr on fc.region_code = dr.region_code
left join marts.fact_weather_daily fw
       on fc.date = fw.date and fc.region_code = fw.region_code
```

All left joins   fact rows with no matching dimension row (2013–2015 weather, or
Corsica) are kept with nulls rather than dropped.

## Naming conventions

- Tables: `fact_*` and `dim_*`, snake_case.
- Columns: snake_case, with units as suffixes (`_mw`, `_mwh`, `_gwh`, `_c`).
- Booleans prefixed `is_`.
- Source column names are never carried through everything is renamed by
  preprocessing.

## The dbt layers

- `staging` (views)   one model per source, casts the raw text columns to real
  types. 1:1 with the raw tables.
- `intermediate` (views)   `int_consumption_daily` aggregates half-hourly to daily.
- `marts` (tables)   the dimensions and facts above.

No surrogate keys or load timestamps facts use their natural composite keys
(`date`/`year` + `region_code`), and uniqueness on that grain is enforced by a dbt
test.

## Known limitations

- Corsica has no daily consumption rows (missing at source).
- 2013–2015 consumption has no temperature (weather starts 2016).
- Production is annual against a daily consumption fact one production row covers
  the whole year for a region.
- Renewable (ENR) detail isn't in a mart yet.
- Population / per-capita metrics are out of scope.
