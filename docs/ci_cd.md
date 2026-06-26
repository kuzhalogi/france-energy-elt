# CI/CD

What runs automatically, when, and why. The tool is GitHub Actions; the workflow
is `.github/workflows/ci.yml`.

## What runs

On every pull request (and push to `main`), two jobs run:

- **python-tests**:  runs `pytest` against the cleaning logic. No database needed,
  so it's fast.
- **dbt-build**:  spins up a throwaway Postgres, loads small sample files, and runs
  the full dbt build with all tests.

If either job fails, the pull request shows a red check and you know before
merging.

## Why sample data, not real data

The dbt job does **not** use the real dataset (the daily table alone is ~2.8M rows,
and pulling it would depend on the API being up). Instead it loads five tiny
fixture files committed in `ci/seeds/` one per source, a handful of rows each.
That keeps CI fast and self-contained, while still exercising the whole chain:
load → staging → intermediate → marts → tests.

## The dbt-build job, step by step

1. Start a Postgres service container (throwaway, lives only for the run).
2. Install dependencies from `requirements.txt`.
3. `python scripts/load.py` loads the `ci/seeds/` fixtures into the `raw` schema.
   (It points at the fixtures via the `PROCESSED_DATA_DIR=ci/seeds` environment
   variable.)
4. `dbt deps` installs dbt packages (dbt_utils).
5. `dbt build` builds every model and runs every test.

The dbt steps run inside `energy_analytics/` (where the dbt project lives), and
the Postgres connection details are passed as environment variables in the
workflow.

## What gets tested

The `dbt build` runs the same tests defined in the model YAML:

- `not_null` on keys, `accepted_values` on consumption status.
- `relationships`  every fact row links to a real region and date.
- `unique_combination_of_columns` exactly one row per grain (date + region, or
  year + region).

Plus the pytest suite, which checks the Python cleaning logic (status filter,
type casting, null handling, negative-reading drop, validators).

## A note on the CI password

The workflow sets a Postgres password in plain text. That's fine here because it's
a throwaway database that only exists for the length of the run it's not a real
secret. Real credentials (for an actual warehouse) belong in GitHub repository
secrets and are referenced as `${{ secrets.NAME }}`, never written in the file.

## CD not built yet

There's no deploy step yet. With everything running locally on Postgres, there's
nothing to deploy to. CD lands in the planned GCP phase, where a push to `main`
would build the models against the real cloud warehouse and/or trigger the
orchestrator. At that point the CD scope also needs revisiting, since the daily
data is now ingested incrementally rather than downloaded by hand.
