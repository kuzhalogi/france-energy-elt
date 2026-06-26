# France Energy ELT

A data pipeline that pulls French regional energy data, cleans it, loads it into
Postgres, and models it with dbt into tables that are easy to query and analyze.

The data comes from ODRE (Open Data Réseaux Énergies), France's open energy data
portal. It covers electricity consumption (half-hourly and annual, by region),
daily temperature by region, and yearly electricity production broken down by
source (nuclear, wind, solar, and so on). The earliest data goes back to 2013.

## How it works

The pipeline runs in four steps. Data moves left to right and gets a little
cleaner at each stage.

**1. Extract** `scripts/extract.py`
Pulls the data from the ODRE API and saves raw CSVs into `data/raw/`. The big
daily consumption dataset (around 2.8 million rows) is fetched incrementally  
only the days we don't already have   while the smaller yearly datasets are just
re-downloaded each time.

**2. Preprocess** `scripts/preprocess.py`
Reads the raw CSVs, renames the columns to plain English, fixes the types,
filters out unvalidated and bad rows, and writes clean CSVs to `processed/`.
Before saving, it runs checks (row counts, value ranges, region codes, missing
values). If something looks wrong, it stops with an error instead of passing bad
data along. Clean files land in `processed/`.

**3. Load** `scripts/load.py`
Loads the clean CSVs into Postgres, into a schema called `raw`, with every column
stored as text. This is the landing zone   data goes in exactly as it came out of
preprocessing, no logic applied. It uses Postgres COPY so even the big table loads
in a few seconds.

**4. Transform**   dbt, in `energy_analytics/`
This is where the raw tables become useful. The models are organized in three
layers, each its own schema in Postgres:

- `staging`   one model per source, casting the text columns to real types
  (dates, numbers). One-to-one with the raw tables.
- `intermediate`   rolls the half-hourly consumption up into daily totals
  (energy in MWh, plus peak and average load).
- `marts`   the final tables, shaped as a star schema: two shared dimensions
  (`dim_region`, `dim_date`) and three fact tables for consumption, weather, and
  production. These are what you'd point a dashboard or analysis at.

## Testing

Checks happen at every step, so problems get caught early instead of showing up
as wrong numbers later:

- The preprocess checks stop bad data before it ever reaches the database.
- `pytest` (in `tests/`) tests the cleaning logic on small sample data.
- dbt tests run after the models build   checking for missing values, valid
  region codes, that every fact row links to a real region and date, and that
  there's exactly one row per region per day (or per year).

## Running it

You'll need Postgres running and a few environment variables set (host, port,
user, password, database). Put them in a `.env` file:

```
PGHOST=localhost
PGPORT=5432
PGUSER=energy_user
PGPASSWORD=yourpassword
PGDATABASE=energy
```

Then install the dependencies and run the steps in order:

```bash
pip install -r requirements.txt

python scripts/extract.py        # pull from the API
python scripts/preprocess.py     # clean + validate
python scripts/load.py           # load into Postgres raw schema

cd energy_analytics
export DBT_PROFILES_DIR=.
dbt deps                         # install dbt packages
dbt build                        # build all models + run tests
```

After that, the modeled tables live in the `marts` schema, ready to query.

## Continuous integration

There's a GitHub Actions workflow in `.github/` that runs on every pull request.
It runs the Python tests, then spins up a throwaway Postgres, loads small sample
files from `ci/seeds/`, and runs the full dbt build. It uses the sample data
instead of the real millions of rows, so it's fast and doesn't depend on the API
being up. If a change breaks something, the PR shows a red check.

## Project layout

```
scripts/          extract, preprocess, load
tests/            python tests for the cleaning logic
energy_analytics/ the dbt project (staging, intermediate, marts)
ci/seeds/         small sample files used by CI
data/raw/         raw downloads (not committed)
processed/        cleaned files (not committed)
docs/             notes on the data and design
.github/          CI workflow
```

## What's not here yet

It runs as a batch pipeline you kick off by hand. There's no scheduler wiring the
steps together automatically yet adding something like Airflow to run it on a
schedule is the natural next step.
