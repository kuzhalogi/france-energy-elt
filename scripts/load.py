"""
load.py
-------
Loads the cleaned processed/*.csv files into the Postgres
`raw` schema (bronze layer) as TEXT tables, using COPY for speed.

Bronze principle: land the data as-is, no typing or logic. The dbt `staging`
layer (silver) casts these TEXT columns to real types; `marts` (gold) builds
the star schema. Keeping raw untyped gives staging a clear, testable job.

Connection comes from environment variables (.env):
    PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD

Run:
    python scripts/load.py                  # load all
    python scripts/load.py --table temperature
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

PROCESSED_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
RAW_SCHEMA = "raw"

# raw table name -> processed filename
TABLES = {
    "consumption_daily": "consumption_daily.csv",
    "consumption_annual": "consumption_annual.csv",
    "temperature": "temperature.csv",
    "production_filiere": "production_filiere.csv",
    "production_enr": "production_enr.csv",
}


def connect():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "energy"),
        user=os.getenv("PGUSER", "energy_user"),
        password=os.getenv("PGPASSWORD", "passwordenergy"),
    )


def read_header(path: Path) -> list[str]:
    with path.open(newline="") as f:
        return next(csv.reader(f))


def create_table(cur, table: str, columns: list[str]) -> None:
    cols_ddl = ",\n  ".join(f'"{c}" TEXT' for c in columns)
    # Create only if absent — never drop, so dbt's dependent views stay valid.
    cur.execute(
        f'CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}."{table}" (\n  {cols_ddl}\n);'
    )
    # Empty it for a clean full-refresh without dropping the table object.
    cur.execute(f'TRUNCATE TABLE {RAW_SCHEMA}."{table}";')


def copy_csv(cur, table: str, path: Path) -> None:
    sql = f'COPY {RAW_SCHEMA}."{table}" FROM STDIN WITH (FORMAT csv, HEADER true)'
    with path.open() as f:
        cur.copy_expert(sql, f)


def load_table(cur, table: str, filename: str) -> None:
    path = PROCESSED_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Processed file not found: {path.resolve()}")
    columns = read_header(path)
    create_table(cur, table, columns)
    copy_csv(cur, table, path)
    cur.execute(f'SELECT count(*) FROM {RAW_SCHEMA}."{table}";')
    n = cur.fetchone()[0]
    logger.success(f"Loaded raw.{table}: {n:,} rows ({len(columns)} cols)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load processed CSVs into Postgres raw schema.")
    parser.add_argument("--table", choices=list(TABLES), default=None)
    args = parser.parse_args()

    targets = {args.table: TABLES[args.table]} if args.table else TABLES

    conn = connect()
    conn.autocommit = False
    failed: list[str] = []
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA};")
            for table, filename in targets.items():
                try:
                    load_table(cur, table, filename)
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    logger.error(f"{table} failed: {exc}")
                    failed.append(table)
    finally:
        conn.close()

    if failed:
        logger.error(f"=== FAILED: {failed} ===")
        return 1
    logger.success("=== Load complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())