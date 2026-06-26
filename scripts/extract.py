"""
extract.py
----------
The "E" in ELT. Pulls raw data from the ODRE OpenDataSoft Explore v2 API and
lands raw CSVs into data/raw/. Downstream (preprocess -> dbt) is unchanged.

Two patterns:
  - full-refresh : refetch the whole dataset every run (small annual/temp sets)
  - incremental  : fetch only rows newer than what we already have (daily, 2.78M)

Run:
    python scripts/extract.py                    # all datasets
    python scripts/extract.py --dataset temperature
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

RAW_DIR = Path(os.getenv("RAW_DATA_DIR", "data/raw"))
BASE = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets"

# Backfill bounds for the daily set when no file exists yet.
DAILY_START = "2013-01-01"

# ─────────────────────────────────────────────
# Dataset registry
#   id          : ODRE dataset identifier (the slug in the dataset URL)
#   out         : filename written into data/raw/
#   mode        : "full" | "incremental"
#   api_date    : technical field id used in the ODSQL where-clause (incremental)
#   raw_date    : column header in the saved CSV used to read the last date
#
# All five ids are confirmed ODRE slugs.
# ─────────────────────────────────────────────
DATASETS = {
    "consumption_daily": {
        "id": "consommation-quotidienne-brute-regionale",
        "out": "econsumption-daily-regionale.csv",
        "mode": "incremental",
        "api_date": "date",
        "raw_date": "date",
    },
    "consumption_annual": {
        "id": "consommation-annuelle-brute-regionale",
        "out": "econsumption-annual-regionale.csv",
        "mode": "full",
    },
    "temperature": {
        "id": "temperature-quotidienne-regionale",
        "out": "temperature-quotidienne-regionale.csv",
        "mode": "full",
    },
    "production_filiere": {
        "id": "prod-region-annuelle-filiere",
        "out": "prod-region-annuelle-filiere.csv",
        "mode": "full",
    },
    "production_enr": {
        "id": "prod-region-annuelle-enr",
        "out": "prod-region-annuelle-enr.csv",
        "mode": "full",
    },
}


# ─────────────────────────────────────────────
# Pure helpers (testable, no network)
# ─────────────────────────────────────────────

def build_where(api_date: str, since: str) -> str:
    """ODSQL filter: rows strictly newer than `since` (YYYY-MM-DD)."""
    return f"{api_date} > date'{since}'"


def last_loaded_date(path: Path, raw_date_col: str) -> str | None:
    """Max date in an existing raw CSV, or None if the file is absent."""
    if not path.exists():
        return None
    s = pd.read_csv(path, sep=";", usecols=[raw_date_col])[raw_date_col]
    return str(pd.to_datetime(s, errors="coerce").max().date())


# ─────────────────────────────────────────────
# Network
# ─────────────────────────────────────────────

def export_csv(dataset_id: str, where: str | None = None) -> pd.DataFrame:
    """Pull a dataset (or a filtered slice) via the bulk export endpoint."""
    url = f"{BASE}/{dataset_id}/exports/csv"
    params = {"delimiter": ";"}
    if where:
        params["where"] = where
    logger.info(f"GET {dataset_id} export" + (f" where {where}" if where else ""))
    r = requests.get(url, params=params, timeout=300)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text), sep=";", low_memory=False)


# ─────────────────────────────────────────────
# Extract modes
# ─────────────────────────────────────────────

def extract_full(cfg: dict) -> None:
    df = export_csv(cfg["id"])
    out = RAW_DIR / cfg["out"]
    df.to_csv(out, sep=";", index=False)
    logger.success(f"Full refresh → {out} ({len(df):,} rows)")


def extract_incremental(cfg: dict) -> None:
    out = RAW_DIR / cfg["out"]
    since = last_loaded_date(out, cfg["raw_date"]) or DAILY_START
    new = export_csv(cfg["id"], where=build_where(cfg["api_date"], since))

    if new.empty:
        logger.info(f"No new rows since {since} → {cfg['out']} unchanged")
        return

    if out.exists():
        old = pd.read_csv(out, sep=";", low_memory=False)
        if set(old.columns) != set(new.columns):
            raise ValueError(
                f"Schema mismatch in {cfg['out']}: existing columns differ from the "
                f"API export. Delete the file and re-run for a clean backfill."
            )
        combined = pd.concat([old, new], ignore_index=True).drop_duplicates()
    else:
        combined = new

    combined.to_csv(out, sep=";", index=False)
    logger.success(f"Incremental → {out} (+{len(new):,} new, {len(combined):,} total)")


# ─────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────

def run(name: str) -> None:
    cfg = DATASETS[name]
    logger.info(f"--- {name} ({cfg['mode']}) ---")
    if cfg["mode"] == "incremental":
        extract_incremental(cfg)
    else:
        extract_full(cfg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract raw data from the ODRE API.")
    parser.add_argument("--dataset", choices=list(DATASETS), default=None)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    targets = [args.dataset] if args.dataset else list(DATASETS)
    failed: list[str] = []

    for name in targets:
        try:
            run(name)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"{name} failed: {exc}")
            failed.append(name)

    if failed:
        logger.error(f"=== FAILED: {failed} ===")
        return 1
    logger.success("=== Extract complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())