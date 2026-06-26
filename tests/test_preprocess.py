"""
Unit tests for scripts/preprocess.py

These test the *logic* (transforms + validators) on tiny in-memory fixtures.
They do NOT touch real data files, so they run in milliseconds and are safe
for CI on every pull request.

Run:
    pytest tests/ -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

# Make scripts/ importable without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import preprocess as pp  # noqa: E402


# ─────────────────────────────────────────────
# consumption_daily
# ─────────────────────────────────────────────

def _raw_daily():
    return pd.DataFrame({
        "date_heure": ["2020-01-01T00:00:00", "2020-01-01T00:30:00", "2020-01-01T01:00:00"],
        "date": ["2020-01-01", "2020-01-01", "2020-01-01"],
        "heure": ["00:00", "00:30", "01:00"],
        "code_insee_region": ["11", "11", "11"],
        "region": ["Île-de-France"] * 3,
        "consommation_brute_electricite_rte": [8000, 7900, None],
        "statut_rte": ["Définitif", "Consolidé", "Provisoire"],  # last row should drop
        "consommation_brute_totale": [8100, 8000, 7800],
        "flag_ignore": ["non", "non", "non"],
    })


def test_daily_status_filter_drops_provisoire():
    out = pp.transform_consumption_daily(_raw_daily())
    assert len(out) == 2
    assert set(out["status"]) <= pp.VALID_STATUSES


def test_daily_renames_and_types():
    out = pp.transform_consumption_daily(_raw_daily())
    assert {"date", "region_code", "consumption_mw", "status"} <= set(out.columns)
    assert str(out["region_code"].dtype) == "Int64"


def test_daily_validate_passes_on_clean_data():
    out = pp.transform_consumption_daily(_raw_daily())
    # Row count gate expects millions; patch a small frame to a passing range
    # by checking the other contracts directly instead.
    pp._run_checks("daily_subset", [
        pp._expect_subset(out, "region_code", pp.DAILY_REGION_CODES),
        pp._expect_subset(out, "status", pp.VALID_STATUSES),
        pp._expect_between(out, "consumption_mw", 0, 50_000),
    ])


def test_daily_validate_rejects_unknown_region():
    out = pp.transform_consumption_daily(_raw_daily())
    out.loc[0, "region_code"] = 99  # not a real region
    with pytest.raises(pp.ValidationError):
        pp._run_checks("bad_region",
                       [pp._expect_subset(out, "region_code", pp.DAILY_REGION_CODES)])


def test_daily_drops_negative_consumption():
    raw = _raw_daily()
    raw.loc[0, "consommation_brute_electricite_rte"] = -3239  # impossible reading
    out = pp.transform_consumption_daily(raw)
    assert (out["consumption_mw"] >= 0).all()


def test_daily_corsica_excluded_from_daily_set():
    assert 94 not in pp.DAILY_REGION_CODES
    assert 94 in pp.ALL_REGION_CODES


# ─────────────────────────────────────────────
# production_filiere — structural null fill
# ─────────────────────────────────────────────

def test_filiere_nuclear_null_filled_with_zero():
    raw = pd.DataFrame({
        "annee": [2020, 2020],
        "code_insee_region": ["11", "53"],
        "region": ["Île-de-France", "Bretagne"],
        "production_nucleaire": [5000, None],   # Bretagne has no nuclear
        "production_thermique": [100, 200],
        "production_hydraulique": [0, 50],
        "production_eolienne": [10, 800],
        "production_solaire": [20, 60],
        "production_bioenergies": [5, 30],
    })
    out = pp.transform_production_filiere(raw)
    assert out.loc[out["region_code"] == 53, "nuclear_gwh"].iloc[0] == 0
    assert out["nuclear_gwh"].isnull().sum() == 0
    assert out["year"].dtype == int


# ─────────────────────────────────────────────
# Generic validator behaviour
# ─────────────────────────────────────────────

def test_expect_between_catches_out_of_range():
    df = pd.DataFrame({"x": [1, 2, 999]})
    label, ok = pp._expect_between(df, "x", 0, 10)
    assert ok is False


def test_expect_no_nulls_catches_nulls_in_keys():
    df = pd.DataFrame({"k": [1, None, 3]})
    label, ok = pp._expect_no_nulls(df, ["k"])
    assert ok is False


def test_run_checks_raises_with_all_failures_listed():
    with pytest.raises(pp.ValidationError) as exc:
        pp._run_checks("demo", [("check A", False), ("check B", True), ("check C", False)])
    msg = str(exc.value)
    assert "check A" in msg and "check C" in msg and "check B" not in msg


def test_run_checks_passes_when_all_true():
    pp._run_checks("demo", [("a", True), ("b", True)])  # should not raise