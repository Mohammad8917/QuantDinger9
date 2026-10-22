"""Offline tests for the Gate V3 historical data acquisition tool."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "historical_gate_v3" / "download_gate_history.py"
SPEC = importlib.util.spec_from_file_location("download_gate_history", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_exact_twenty_contract_universe() -> None:
    assert len(MODULE.SYMBOLS) == 20
    assert len(set(MODULE.SYMBOLS)) == 20
    assert MODULE.TIMEFRAMES == {"15m": 900, "1h": 3600}


def test_utc_date_parsing() -> None:
    assert MODULE.utc_timestamp("2026-10-22") == 1792627200
    assert MODULE.utc_timestamp("2026-10-22T00:00:00Z") == 1792627200


def test_date_only_end_includes_full_utc_day() -> None:
    assert MODULE.utc_end_timestamp("2026-10-22") == MODULE.utc_timestamp("2026-10-23")
    assert MODULE.utc_end_timestamp("2026-10-22T12:00:00Z") == MODULE.utc_timestamp("2026-10-22T12:00:00Z")


def test_candle_row_validation() -> None:
    valid = {
        "timestamp": 1800000000,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 12.0,
        "quote_volume": 12000.0,
    }
    # 1800000000 is divisible by 900 and 3600.
    assert MODULE._validate_row(valid, 900) is None
    assert MODULE._validate_row({**valid, "high": 90.0}, 900) == "invalid_high"
    assert MODULE._validate_row({**valid, "close": 0.0}, 900) == "non_positive_price"
    assert MODULE._validate_row({**valid, "volume": -1.0, "quote_volume": 12000.0}, 900) == "negative_volume"


def test_gap_audit_does_not_fill_missing_candles() -> None:
    rows = [
        {"timestamp": 1800000000, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1.0, "quote_volume": 1000.0},
        {"timestamp": 1800001800, "open": 102.0, "high": 106.0, "low": 99.0, "close": 104.0, "volume": 2.0, "quote_volume": 1000.0},
    ]
    audit = MODULE.audit_rows(rows, "15m")
    assert audit["bars"] == 2
    assert audit["gap_count"] == 1
    assert audit["complete_contiguous_history"] is False
    assert len(rows) == 2


def test_coverage_bounds_are_candle_aligned() -> None:
    assert MODULE.ceil_to_interval(1800000001, 900) == 1800000900
    assert MODULE.ceil_to_interval(1800000000, 900) == 1800000000
    assert MODULE.last_closed_candle_start(1800003600, 900, now_ts=1800003600) == 1800002700


def test_audit_detects_missing_range_edges() -> None:
    start = 1800000000
    rows = [
        {"timestamp": start + 900, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1.0, "quote_volume": 1000.0},
        {"timestamp": start + 1800, "open": 102.0, "high": 106.0, "low": 99.0, "close": 104.0, "volume": 2.0, "quote_volume": 1000.0},
    ]
    audit = MODULE.audit_rows(rows, "15m", expected_start=start, expected_end=start + 2700)
    assert audit["expected_bars"] == 4
    assert audit["observed_expected_bars"] == 2
    assert audit["missing_expected_bars"] == 2
    assert audit["leading_missing_bars"] == 1
    assert audit["trailing_missing_bars"] == 1
    assert audit["coverage_ratio"] == 0.5
    assert audit["complete_contiguous_history"] is False


def test_audit_detects_duplicate_timestamps_before_deduplication() -> None:
    row = {"timestamp": 1800000000, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1.0, "quote_volume": 1000.0}
    audit = MODULE.audit_rows([row, dict(row)], "15m", expected_start=1800000000, expected_end=1800000000)
    assert audit["bars"] == 2
    assert audit["unique_timestamps"] == 1
    assert audit["invalid_rows"]["duplicate_timestamp"] == 1
    assert audit["complete_contiguous_history"] is False


def test_audit_marks_exact_expected_coverage_complete() -> None:
    start = 1800000000
    rows = [
        {"timestamp": start, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1.0, "quote_volume": 1000.0},
        {"timestamp": start + 900, "open": 102.0, "high": 106.0, "low": 99.0, "close": 104.0, "volume": 2.0, "quote_volume": 1000.0},
    ]
    audit = MODULE.audit_rows(rows, "15m", expected_start=start, expected_end=start + 900)
    assert audit["missing_expected_bars"] == 0
    assert audit["gap_count"] == 0
    assert audit["complete_contiguous_history"] is True


def test_audit_rejects_rows_outside_expected_coverage() -> None:
    start = 1800000000
    rows = [
        {"timestamp": start - 900, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1.0, "quote_volume": 1000.0},
        {"timestamp": start, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1.0, "quote_volume": 1000.0},
        {"timestamp": start + 900, "open": 102.0, "high": 106.0, "low": 99.0, "close": 104.0, "volume": 2.0, "quote_volume": 1000.0},
        {"timestamp": start + 1800, "open": 104.0, "high": 107.0, "low": 101.0, "close": 105.0, "volume": 2.0, "quote_volume": 1000.0},
    ]
    audit = MODULE.audit_rows(rows, "15m", expected_start=start, expected_end=start + 900)
    assert audit["out_of_range_timestamps"] == 2
    assert audit["observed_expected_bars"] == 2
    assert audit["complete_contiguous_history"] is False


def test_locked_strategy_fingerprint_is_checked(tmp_path: Path) -> None:
    # An empty checkout must fail closed instead of downloading under an unknown strategy.
    try:
        MODULE.verify_locked_strategy(tmp_path)
    except MODULE.DataError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("Missing strategy file should have stopped data collection")


def test_candle_row_rejects_non_finite_values() -> None:
    valid = {
        "timestamp": 1800000000,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 12.0,
        "quote_volume": 12000.0,
    }
    assert MODULE._validate_row({**valid, "close": float("nan")}, 900) == "non_finite_value"
    assert MODULE._validate_row({**valid, "volume": float("inf")}, 900) == "non_finite_value"
    assert MODULE._validate_row({**valid, "quote_volume": float("inf")}, 900) == "non_finite_value"
    assert MODULE._validate_row({**valid, "quote_volume": -1.0}, 900) == "negative_quote_volume"

def test_parse_gate_archive_row_preserves_real_ohlcv_and_missing_quote_volume() -> None:
    row = MODULE._parse_archive_row(["1800000000", "12.5", "102", "105", "95", "100"])
    assert row == {
        "timestamp": 1800000000,
        "volume": 12.5,
        "close": 102.0,
        "high": 105.0,
        "low": 95.0,
        "open": 100.0,
        "quote_volume": None,
    }
    assert MODULE._validate_row(row, 300) is None


def test_aggregate_15m_requires_three_contiguous_real_5m_bars() -> None:
    rows = [
        {"timestamp": 1800000000, "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1.0, "quote_volume": None},
        {"timestamp": 1800000300, "open": 101.0, "high": 104.0, "low": 100.0, "close": 103.0, "volume": 2.0, "quote_volume": None},
        {"timestamp": 1800000600, "open": 103.0, "high": 105.0, "low": 102.0, "close": 104.0, "volume": 3.0, "quote_volume": None},
        {"timestamp": 1800000900, "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0, "volume": 4.0, "quote_volume": None},
        {"timestamp": 1800001500, "open": 105.0, "high": 107.0, "low": 104.0, "close": 106.0, "volume": 5.0, "quote_volume": None},
    ]
    aggregated = MODULE.aggregate_5m_to_15m(rows)
    assert len(aggregated) == 1
    assert aggregated[0] == {
        "timestamp": 1800000000,
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 6.0,
        "quote_volume": None,
    }


def test_archive_month_iteration_spans_year_boundary() -> None:
    start = MODULE.utc_timestamp("2024-12-31")
    end = MODULE.utc_timestamp("2025-02-01")
    assert [d.strftime("%Y%m") for d in MODULE._month_starts(start, end)] == ["202412", "202501", "202502"]

