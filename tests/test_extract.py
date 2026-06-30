"""
Unit tests for scripts/extract.py
Tests the backfill chunking *logic* — pure function, no network, no files.
Safe for CI on every pull request.
Run:
    pytest tests/ -v
"""
import sys
from pathlib import Path
from datetime import date

# Make scripts/ importable without installing the package (matches test_preprocess.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract import _daterange_chunks   # noqa: E402  (import after sys.path insert)


def test_chunks_cover_full_range_without_gaps_or_overlap():
    """Slices must tile (since, until] contiguously: each hi == next lo."""
    chunks = list(_daterange_chunks("2013-01-01", "2016-01-01", 366))
    assert chunks[0][0] == "2013-01-01"
    assert chunks[-1][1] == "2016-01-01"
    for (_, hi), (lo_next, _) in zip(chunks, chunks[1:]):
        assert hi == lo_next


def test_no_chunk_exceeds_step_days():
    """Every slice spans at most step_days."""
    step = 366
    for lo, hi in _daterange_chunks("2013-01-01", "2026-06-29", step):
        assert (date.fromisoformat(hi) - date.fromisoformat(lo)).days <= step


def test_single_short_gap_yields_one_chunk():
    """A gap smaller than step_days produces exactly one slice."""
    chunks = list(_daterange_chunks("2026-06-01", "2026-06-20", 366))
    assert chunks == [("2026-06-01", "2026-06-20")]


def test_empty_when_since_equals_until():
    """No range to cover → no slices."""
    assert list(_daterange_chunks("2026-06-29", "2026-06-29", 366)) == []