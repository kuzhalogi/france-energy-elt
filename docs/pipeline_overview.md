# Pipeline Overview

How data moves from the ODRE API to the final modeled tables, stage by stage.
Read `data_catalog.md` and `data_model_design.md` first.

## The flow

```
ODRE API
    │   scripts/extract.py incremental daily, full refresh for the rest
    ▼
data/raw/*.csv            raw downloads, original column names
    │   scripts/preprocess.py rename, type, filter, validate
    ▼
processed/*.csv           clean files, English column names
    │   scripts/load.py COPY into Postgres
    ▼
Postgres: raw schema      landed as text, no logic (bronze)
    │   dbt: staging → intermediate → marts
    ▼
Postgres: marts schema    star schema, ready to query (gold)
```

It's a batch pipeline you run by hand, in that order. There's no scheduler or
dashboard yet (see "Not built yet" at the end).

## Stage 1: Extract

`scripts/extract.py` pulls each dataset from the ODRE OpenDataSoft API into
`data/raw/`. Two patterns:

- **Daily consumption** (~2.8M rows) is fetched **incrementally** it reads the
  newest date already in the file and asks the API only for newer rows.
- The **four smaller datasets** are re-downloaded in full each run.

## Stage 2: Preprocess and validate

`scripts/preprocess.py` reads each raw file and produces a clean one in
`processed/`. Per file it: selects the columns it needs, renames them to English
snake_case, casts types, and applies the dataset's cleaning rules (status filter
on consumption, structural-zero fill on nuclear, etc.).

Before writing, it runs **validators** row-count ranges, value ranges, allowed
region codes, no-nulls on keys. If any check fails it raises and stops, so bad
data never reaches the database. This is the first quality gate.

## Stage 3: Load

`scripts/load.py` loads the clean CSVs into the Postgres `raw` schema, every
column as text, using COPY. This is the bronze layer: data landed exactly as it
came out of preprocessing, no transformation. The connection comes from
environment variables (`PGHOST`, `PGUSER`, etc.).

## Stage 4: Transform (dbt)

The dbt project lives in `energy_analytics/` and turns the raw tables into the
star schema, in three layers (each its own Postgres schema):

- **staging**: one `stg_` model per source. Casts the text columns to real types.
  Materialized as views.
- **intermediate**: `int_consumption_daily` rolls the half-hourly consumption up
  to daily energy (MWh) plus peak/average/min load.
- **marts**: `dim_region`, `dim_date`, `fact_consumption_daily`,
  `fact_weather_daily`, `fact_production_annual`. Materialized as tables.

Schema routing is handled by a small macro (`generate_schema_name.sql`) so models
land in clean `staging` / `intermediate` / `marts` schemas instead of Postgres's
default prefixed names.

## Testing

Checks run at every stage so problems surface early:

- **Preprocess validators**: stop bad data before load.
- **pytest** (`tests/test_preprocess.py`): tests the cleaning logic on tiny
  sample data.
- **dbt tests**: after the models build: not-null and accepted-values on staging,
  and on the marts: foreign-key integrity (every fact row points to a real region
  and date) plus one-row-per-grain uniqueness.

## How to run it

```bash
pip install -r requirements.txt

python scripts/extract.py        # pull from the API
python scripts/preprocess.py     # clean + validate
python scripts/load.py           # load into Postgres raw

cd energy_analytics
export DBT_PROFILES_DIR=.
dbt deps
dbt build                        # build models + run tests
```

## Folder structure

```
scripts/            extract.py, preprocess.py, load.py
tests/              pytest tests for the cleaning logic
energy_analytics/   the dbt project
  models/staging/        stg_*
  models/intermediate/   int_consumption_daily
  models/marts/          dim_*, fact_*
  macros/                generate_schema_name.sql
  profiles.yml           Postgres connection (uses env vars)
ci/seeds/           small sample files for CI
data/raw/           raw downloads (not committed)
processed/          cleaned files (not committed)
docs/               these documents
.github/            CI workflow
```

## Environment variables

Kept in a `.env` file (not committed):

```
PGHOST=localhost
PGPORT=5432
PGUSER=energy_user
PGPASSWORD=yourpassword
PGDATABASE=energy
```

## Not built yet

- **Orchestration**: the stages are run manually; a scheduler (Airflow) to chain
  and schedule them is the next step.
- **A serving/dashboard layer**: the marts are query-ready but nothing is plugged
  in on top.
- **Cloud**: everything runs locally on Postgres. A GCP/BigQuery version is the
  planned follow-up.
