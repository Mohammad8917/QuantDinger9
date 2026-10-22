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


def test_candle_row_validation() -> None:
    valid = {
        "timestamp": 1800000000,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 12.0,
    }
    # 1800000000 is divisible by 900 and 3600.
    assert MODULE._validate_row(valid, 900) is None
    assert MODULE._validate_row({**valid, "high": 90.0}, 900) == "invalid_high"
    assert MODULE._validate_row({**valid, "close": 0.0}, 900) == "non_positive_price"
    assert MODULE._validate_row({**valid, "volume": -1.0}, 900) == "negative_volume"


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
    }
    assert MODULE._validate_row({**valid, "close": float("nan")}, 900) == "non_finite_value"
    assert MODULE._validate_row({**valid, "volume": float("inf")}, 900) == "non_finite_value"
