"""
preprocess.py
-------------
Cleans raw CSV files from data/raw/ and writes processed outputs to data/processed/.

Architecture (so CI can test the logic without the real data):

    transform_<dataset>(df)  -> df     pure, no I/O          <- unit-tested in CI
    validate_<dataset>(df)   -> None   raises on violation   <- unit-tested in CI
    process_<dataset>()      -> None   read -> transform -> validate -> save

The full run reads multi-million-row files and is meant for local dev or the
Airflow task. CI never runs `main()`; it imports the transform/validate
functions and exercises them on tiny fixtures (see tests/test_preprocess.py).

Run the full pipeline:
    python scripts/preprocess.py                  # all datasets
    python scripts/preprocess.py --dataset temperature
    python scripts/preprocess.py --no-validate    # skip the quality gate (debug only)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable

import pandas as pd
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

RAW_DIR = Path(os.getenv("RAW_DATA_DIR", "data/raw"))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

# ─────────────────────────────────────────────
# Reference data (from data_catalog.md)
# ─────────────────────────────────────────────

# 13 metropolitan regions. Corsica (94) is ABSENT from the RTE daily dataset
# but present in every other source — documented inconsistency.
DAILY_REGION_CODES = {11, 24, 27, 28, 32, 44, 52, 53, 75, 76, 84, 93}
ALL_REGION_CODES = DAILY_REGION_CODES | {94}

VALID_STATUSES = {"Définitif", "Consolidé"}

# Per-file separators. data.gouv.fr / ODRE files vary; override here if a file
# fails to parse instead of guessing globally.
SEPARATORS = {
    "econsumption-daily-regionale.csv": ";",
    "econsumption-annual-regionale.csv": ";",
    "temperature-quotidienne-regionale.csv": ";",
    "prod-region-annuelle-filiere.csv": ";",
    "prod-region-annuelle-enr.csv": ";",
}


class ValidationError(Exception):
    """Raised when a cleaned dataset violates its data contract."""


# ─────────────────────────────────────────────
# Generic helpers
# ─────────────────────────────────────────────

def read_raw(filename: str) -> pd.DataFrame:
    path = RAW_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Raw file not found: {path.resolve()}")
    sep = SEPARATORS.get(filename, ";")
    df = pd.read_csv(path, sep=sep, low_memory=False)
    logger.info(f"Read {filename}: {df.shape[0]:,} rows × {df.shape[1]} cols (sep={sep!r})")
    return df


def save(df: pd.DataFrame, filename: str) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / filename
    df.to_csv(path, index=False)
    logger.success(f"Saved → {path} ({len(df):,} rows)")


def _run_checks(name: str, checks: list[tuple[str, bool]]) -> None:
    """Evaluate (label, passed) checks; raise ValidationError listing all failures."""
    failures = [label for label, passed in checks if not passed]
    if failures:
        bullets = "\n  - ".join(failures)
        raise ValidationError(f"[{name}] {len(failures)} check(s) failed:\n  - {bullets}")
    logger.success(f"[{name}] all {len(checks)} checks passed")


def _expect_columns(df: pd.DataFrame, cols: list[str]) -> tuple[str, bool]:
    missing = [c for c in cols if c not in df.columns]
    return (f"missing columns: {missing}", not missing)


def _expect_no_nulls(df: pd.DataFrame, cols: list[str]) -> tuple[str, bool]:
    if any(c not in df.columns for c in cols):
        return ("null-check skipped (columns missing)", False)
    bad = {c: int(df[c].isnull().sum()) for c in cols if df[c].isnull().any()}
    return (f"nulls in key columns: {bad}", not bad)


def _expect_subset(df: pd.DataFrame, col: str, allowed: set) -> tuple[str, bool]:
    if col not in df.columns:
        return (f"subset-check skipped ({col} missing)", False)
    extra = set(df[col].dropna().unique()) - allowed
    return (f"{col} has unexpected values: {sorted(extra)}", not extra)


def _expect_between(df: pd.DataFrame, col: str, lo: float, hi: float) -> tuple[str, bool]:
    if col not in df.columns:
        return (f"range-check skipped ({col} missing)", False)
    s = df[col].dropna()
    ok = bool(((s >= lo) & (s <= hi)).all())
    return (f"{col} outside [{lo}, {hi}] (min={s.min()}, max={s.max()})", ok)


def _expect_rowcount(df: pd.DataFrame, lo: int, hi: int) -> tuple[str, bool]:
    return (f"row count {len(df):,} outside [{lo:,}, {hi:,}]", lo <= len(df) <= hi)


# ─────────────────────────────────────────────
# Dataset 1: RTE Daily Electricity Consumption
# ─────────────────────────────────────────────

RENAME_CONSUMPTION_DAILY = {
    "date_heure": "datetime",
    "date": "date",
    "heure": "hour",
    "code_insee_region": "region_code",
    "region": "region",
    "consommation_brute_electricite_rte": "consumption_mw",
    "statut_rte": "status",
    "consommation_brute_totale": "consumption_total_mw",
}


def transform_consumption_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["flag_ignore"] == "non"]  # drop ODRE-flagged anomalies (negatives etc.)
    df = df[list(RENAME_CONSUMPTION_DAILY)].copy()
    df = df[df["statut_rte"].isin(VALID_STATUSES)]
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.rename(columns=RENAME_CONSUMPTION_DAILY)
    df["region_code"] = pd.to_numeric(df["region_code"], errors="coerce").astype("Int64")
    df = df[df["consumption_mw"] >= 0]  # drop impossible negative readings (source glitches)
    return df.reset_index(drop=True)


def validate_consumption_daily(df: pd.DataFrame) -> None:
    _run_checks("consumption_daily", [
        _expect_columns(df, ["date", "region_code", "consumption_mw", "status"]),
        _expect_no_nulls(df, ["date", "region_code", "consumption_mw"]),
        _expect_subset(df, "status", VALID_STATUSES),
        _expect_subset(df, "region_code", DAILY_REGION_CODES),
        _expect_between(df, "consumption_mw", 0, 50_000),
        _expect_rowcount(df, 2_500_000, 2_900_000),
    ])


def process_consumption_daily() -> None:
    df = transform_consumption_daily(read_raw("econsumption-daily-regionale.csv"))
    validate_consumption_daily(df)
    save(df, "consumption_daily.csv")


# ─────────────────────────────────────────────
# Dataset 2: RTE Annual Consumption
# ─────────────────────────────────────────────

RENAME_CONSUMPTION_ANNUAL = {
    "annee": "year",
    "code_insee_region": "region_code",
    "region": "region",
    "consommation_brute_electricite_rte": "consumption_gwh",
}


def transform_consumption_annual(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=RENAME_CONSUMPTION_ANNUAL)
    df = df[[c for c in RENAME_CONSUMPTION_ANNUAL.values() if c in df.columns]]
    df["year"] = df["year"].astype(int)
    df["region_code"] = pd.to_numeric(df["region_code"], errors="coerce").astype("Int64")
    return df.reset_index(drop=True)


def validate_consumption_annual(df: pd.DataFrame) -> None:
    _run_checks("consumption_annual", [
        _expect_columns(df, ["year", "region_code"]),
        _expect_no_nulls(df, ["year", "region_code"]),
        _expect_between(df, "year", 2013, 2025),
        _expect_subset(df, "region_code", ALL_REGION_CODES),
        _expect_rowcount(df, 150, 200),
    ])


def process_consumption_annual() -> None:
    df = transform_consumption_annual(read_raw("econsumption-annual-regionale.csv"))
    validate_consumption_annual(df)
    save(df, "consumption_annual.csv")


# ─────────────────────────────────────────────
# Dataset 3: Météo-France Regional Daily Temperature
# ─────────────────────────────────────────────

RENAME_TEMPERATURE = {
    "date": "date",
    "code_insee_region": "region_code",
    "region": "region",
    "tmin": "t_min_c",
    "tmax": "t_max_c",
    "tmoy": "t_mean_c",
}


def transform_temperature(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=RENAME_TEMPERATURE)
    df = df[[c for c in RENAME_TEMPERATURE.values() if c in df.columns]]
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["region_code"] = pd.to_numeric(df["region_code"], errors="coerce").astype("Int64")
    return df.reset_index(drop=True)


def validate_temperature(df: pd.DataFrame) -> None:
    _run_checks("temperature", [
        _expect_columns(df, ["date", "region_code", "t_min_c", "t_max_c", "t_mean_c"]),
        _expect_no_nulls(df, ["date", "region_code", "t_min_c", "t_max_c", "t_mean_c"]),
        _expect_between(df, "t_min_c", -25, 35),
        _expect_between(df, "t_max_c", -10, 50),
        _expect_between(df, "t_mean_c", -20, 45),
        _expect_subset(df, "region_code", ALL_REGION_CODES),
        _expect_rowcount(df, 45_000, 52_000),
    ])


def process_temperature() -> None:
    df = transform_temperature(read_raw("temperature-quotidienne-regionale.csv"))
    validate_temperature(df)
    save(df, "temperature.csv")


# ─────────────────────────────────────────────
# Dataset 4: Annual Production by Filière
# ─────────────────────────────────────────────

RENAME_PRODUCTION_FILIERE = {
    "annee": "year",
    "code_insee_region": "region_code",
    "region": "region",
    "production_nucleaire": "nuclear_gwh",
    "production_thermique": "thermal_gwh",
    "production_hydraulique": "hydro_gwh",
    "production_eolienne": "wind_gwh",
    "production_solaire": "solar_gwh",
    "production_bioenergies": "bioenergy_gwh",
}

# Regions with no nuclear plants report null, not zero — a structural null.
PRODUCTION_FILL_ZERO = ["nuclear_gwh", "thermal_gwh", "hydro_gwh",
                        "wind_gwh", "solar_gwh", "bioenergy_gwh"]


def transform_production_filiere(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=RENAME_PRODUCTION_FILIERE)
    df = df[[c for c in RENAME_PRODUCTION_FILIERE.values() if c in df.columns]]
    df["year"] = df["year"].astype(int)
    df["region_code"] = pd.to_numeric(df["region_code"], errors="coerce").astype("Int64")
    for col in PRODUCTION_FILL_ZERO:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    return df.reset_index(drop=True)


def validate_production_filiere(df: pd.DataFrame) -> None:
    _run_checks("production_filiere", [
        _expect_columns(df, ["year", "region_code", "nuclear_gwh", "solar_gwh"]),
        _expect_no_nulls(df, ["year", "region_code"] + PRODUCTION_FILL_ZERO),
        _expect_between(df, "year", 2008, 2025),
        _expect_between(df, "nuclear_gwh", 0, 150_000),
        _expect_between(df, "solar_gwh", 0, 15_000),
        _expect_subset(df, "region_code", ALL_REGION_CODES),
        _expect_rowcount(df, 220, 250),
    ])


def process_production_filiere() -> None:
    df = transform_production_filiere(read_raw("prod-region-annuelle-filiere.csv"))
    validate_production_filiere(df)
    save(df, "production_filiere.csv")


# ─────────────────────────────────────────────
# Dataset 5: Annual Renewable Production (ENR)
# ─────────────────────────────────────────────

RENAME_PRODUCTION_ENR = {
    "annee": "year",
    "nom_insee_region": "region",
    "code_insee_region": "region_code",
    "production_hydraulique_renouvelable": "hydro_renewable_gwh",
    "production_bioenergies_renouvelable": "bioenergy_renewable_gwh",
    "production_eolienne_renouvelable": "wind_renewable_gwh",
    "production_solaire_renouvelable": "solar_renewable_gwh",
    "production_electrique_renouvelable": "electricity_renewable_gwh",
    "production_gaz_renouvelable": "gas_renewable_gwh",
    "production_totale_renouvelable": "total_renewable_gwh",
}


def transform_production_enr(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=RENAME_PRODUCTION_ENR)
    df = df[[c for c in RENAME_PRODUCTION_ENR.values() if c in df.columns]]
    df["year"] = df["year"].astype(int)
    df["region_code"] = pd.to_numeric(df["region_code"], errors="coerce").astype("Int64")
    return df.reset_index(drop=True)


def validate_production_enr(df: pd.DataFrame) -> None:
    _run_checks("production_enr", [
        _expect_columns(df, ["year", "region_code", "total_renewable_gwh"]),
        _expect_no_nulls(df, ["year", "region_code", "total_renewable_gwh"]),
        _expect_between(df, "year", 2008, 2025),
        _expect_between(df, "total_renewable_gwh", 0, 50_000),
        _expect_subset(df, "region_code", ALL_REGION_CODES),
        _expect_rowcount(df, 220, 250),
    ])


def process_production_enr() -> None:
    df = transform_production_enr(read_raw("prod-region-annuelle-enr.csv"))
    validate_production_enr(df)
    save(df, "production_enr.csv")


# ─────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────

PROCESSORS: dict[str, Callable[[], None]] = {
    "consumption_daily": process_consumption_daily,
    "consumption_annual": process_consumption_annual,
    "temperature": process_temperature,
    "production_filiere": process_production_filiere,
    "production_enr": process_production_enr,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess France energy raw CSVs.")
    parser.add_argument("--dataset", choices=list(PROCESSORS), default=None,
                        help="Process a single dataset (default: all).")
    parser.add_argument("--no-validate", action="store_true",
                        help="Skip the validation gate (debugging only).")
    args = parser.parse_args()

    logger.info("=== Starting preprocessing ===")
    logger.info(f"Raw dir:       {RAW_DIR.resolve()}")
    logger.info(f"Processed dir: {PROCESSED_DIR.resolve()}")

    targets = [args.dataset] if args.dataset else list(PROCESSORS)
    failed: list[str] = []

    for name in targets:
        try:
            logger.info(f"--- {name} ---")
            PROCESSORS[name]()
        except (FileNotFoundError, ValidationError) as exc:
            logger.error(f"{name} failed: {exc}")
            failed.append(name)
        except Exception as exc:  # noqa: BLE001 — surface anything unexpected
            logger.exception(f"{name} crashed: {exc}")
            failed.append(name)

    if failed:
        logger.error(f"=== FAILED: {failed} ===")
        return 1

    logger.success("=== Preprocessing complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())