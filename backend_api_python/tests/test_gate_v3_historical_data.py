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
        "volume": 12.0,\n        "quote_volume": 12000.0,
    }
    # 1800000000 is divisible by 900 and 3600.
    assert MODULE._validate_row(valid, 900) is None
    assert MODULE._validate_row({**valid, "high": 90.0}, 900) == "invalid_high"
    assert MODULE._validate_row({**valid, "close": 0.0}, 900) == "non_positive_price"
    assert MODULE._validate_row({**valid, "volume": -1.0, "quote_volume": 12000.0}, 900) == "negative_volume"


def test_gap_audit_does_not_fill_missing_candles() -> None:
    rows = [
        {"timestamp": 1800000000, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1.0},
        {"timestamp": 1800001800, "open": 102.0, "high": 106.0, "low": 99.0, "close": 104.0, "volume": 2.0},
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
        {"timestamp": start + 900, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1.0},
        {"timestamp": start + 1800, "open": 102.0, "high": 106.0, "low": 99.0, "close": 104.0, "volume": 2.0},
    ]
    audit = MODULE.audit_rows(rows, "15m", expected_start=start, expected_end=start + 2700)
    assert audit["expected_bars"] == 4
    assert audit["observed_expected_bars"] == 2
    assert audit["missing_expected_bars"] == 2
    assert audit["leading_missing_bars"] == 1
    assert audit["trailing_missing_bars"] == 1
    assert audit["coverage_ratio"] == 0.5
    assert audit["complete_contiguous_history"] is False


def test_fetch_candles_preserves_duplicate_timestamps(monkeypatch) -> None:
    start = 1800000000
    end = start + 1800
    monkeypatch.setattr(MODULE, "time", type("FakeTime", (), {"time": staticmethod(lambda: end), "sleep": staticmethod(lambda _: None)})())
    item = {"t": start, "o": "100", "h": "105", "l": "95", "c": "102", "v": "1", "sum": "1000"}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return [dict(item), dict(item)]

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    rows = MODULE.fetch_candles(FakeSession(), "BTC_USDT", "15m", start, end, sleep_seconds=0)
    assert len(rows) == 2
    assert rows[0]["timestamp"] == rows[1]["timestamp"] == start


def test_audit_detects_duplicate_timestamps_before_deduplication() -> None:
    row = {"timestamp": 1800000000, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1.0}
    audit = MODULE.audit_rows([row, dict(row)], "15m", expected_start=1800000000, expected_end=1800000000)
    assert audit["bars"] == 2
    assert audit["unique_timestamps"] == 1
    assert audit["invalid_rows"]["duplicate_timestamp"] == 1
    assert audit["complete_contiguous_history"] is False


def test_audit_marks_exact_expected_coverage_complete() -> None:
    start = 1800000000
    rows = [
        {"timestamp": start, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1.0},
        {"timestamp": start + 900, "open": 102.0, "high": 106.0, "low": 99.0, "close": 104.0, "volume": 2.0},
    ]
    audit = MODULE.audit_rows(rows, "15m", expected_start=start, expected_end=start + 900)
    assert audit["missing_expected_bars"] == 0
    assert audit["gap_count"] == 0
    assert audit["complete_contiguous_history"] is True


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
        "volume": 12.0,\n        "quote_volume": 12000.0,
    }
    assert MODULE._validate_row({**valid, "close": float("nan")}, 900) == "non_finite_value"
    assert MODULE._validate_row({**valid, "volume": float("inf")}, 900) == "non_finite_value"
