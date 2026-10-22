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


def test_aggregate_15m_uses_observed_real_5m_bars_without_filling_gaps() -> None:
    start = 1800000000
    rows = [
        {"timestamp": start, "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1.0, "quote_volume": None},
        {"timestamp": start + 300, "open": 101.0, "high": 104.0, "low": 100.0, "close": 103.0, "volume": 2.0, "quote_volume": None},
        {"timestamp": start + 600, "open": 103.0, "high": 105.0, "low": 102.0, "close": 104.0, "volume": 3.0, "quote_volume": None},
        {"timestamp": start + 900, "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0, "volume": 4.0, "quote_volume": None},
        {"timestamp": start + 1500, "open": 105.0, "high": 107.0, "low": 104.0, "close": 106.0, "volume": 5.0, "quote_volume": None},
    ]
    aggregated = MODULE.aggregate_5m_to_15m(rows)
    assert len(aggregated) == 2
    assert aggregated[0] == {
        "timestamp": start, "open": 100.0, "high": 105.0, "low": 99.0,
        "close": 104.0, "volume": 6.0, "quote_volume": None,
    }
    assert aggregated[1] == {
        "timestamp": start + 900, "open": 104.0, "high": 107.0, "low": 103.0,
        "close": 106.0, "volume": 9.0, "quote_volume": None,
    }

def test_aggregate_15m_rejects_duplicate_5m_timestamps() -> None:
    row = {"timestamp": 1800000000, "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1.0, "quote_volume": None}
    try:
        MODULE.aggregate_5m_to_15m([row, dict(row)])
    except MODULE.DataError as exc:
        assert "Duplicate 5m candle timestamp" in str(exc)
    else:
        raise AssertionError("Duplicate source candles must not be silently aggregated")

def test_aggregate_10s_to_15m_uses_observed_official_candles_without_synthesis() -> None:
    start = 1735689600
    rows = [
        {"timestamp": start, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 0.0, "quote_volume": None},
        {"timestamp": start + 10, "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 2.0, "quote_volume": None},
        {"timestamp": start + 20, "open": 101.5, "high": 103.0, "low": 101.0, "close": 102.5, "volume": 3.0, "quote_volume": None},
    ]
    aggregated = MODULE.aggregate_10s_to_timeframe(rows, "15m")
    assert aggregated == [{
        "timestamp": start, "open": 100.0, "high": 103.0, "low": 99.0,
        "close": 102.5, "volume": 5.0, "quote_volume": None,
    }]


def test_archive_fetch_supports_official_10s_files() -> None:
    import gzip

    timestamp = 1735689600
    archive_bytes = gzip.compress(
        f"{timestamp},0,100,101,99,100\n".encode("utf-8")
    )

    class FakeResponse:
        status_code = 200
        content = archive_bytes
        text = ""

        def raise_for_status(self) -> None:
            return None

    class FakeSession:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            self.urls.append(url)
            return FakeResponse()

    session = FakeSession()
    rows = MODULE.fetch_archive_candles(
        session, "BTC_USDT", "10s", timestamp, timestamp, sleep_seconds=0,
    )
    assert rows[0]["timestamp"] == timestamp
    assert rows[0]["volume"] == 0.0
    assert session.urls == [
        f"{MODULE.ARCHIVE_BASE_URL}/candlesticks_10s/202501/BTC_USDT-202501.csv.gz"
    ]


def test_aggregate_1m_to_15m_uses_observed_real_minutes_without_filling_gaps() -> None:
    start = 1800000000
    rows = [
        {
            "timestamp": start + index * 60,
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.5 + index,
            "volume": 1.0,
            "quote_volume": None,
        }
        for index in range(15)
        if index != 7
    ]
    aggregated = MODULE.aggregate_1m_to_timeframe(rows, "15m")
    assert len(aggregated) == 1
    assert aggregated[0]["timestamp"] == start
    assert aggregated[0]["open"] == 100.0
    assert aggregated[0]["high"] == 115.0
    assert aggregated[0]["low"] == 99.0
    assert aggregated[0]["close"] == 114.5
    assert aggregated[0]["volume"] == 14.0



def test_aggregate_1m_to_1h_uses_observed_real_minutes_without_filling_gaps() -> None:
    start = 1800000000
    rows = [
        {
            "timestamp": start + index * 60,
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.5 + index,
            "volume": 1.0,
            "quote_volume": None,
        }
        for index in range(60)
        if index != 30
    ]
    aggregated = MODULE.aggregate_1m_to_timeframe(rows, "1h")
    assert len(aggregated) == 1
    assert aggregated[0]["timestamp"] == start
    assert aggregated[0]["volume"] == 59.0
    assert aggregated[0]["high"] == 160.0
    assert aggregated[0]["low"] == 99.0
    assert aggregated[0]["close"] == 159.5



def test_missing_expected_timestamps_are_reported_not_filled() -> None:
    start = 1800000000
    rows = [
        {"timestamp": start, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0, "quote_volume": None},
        {"timestamp": start + 1800, "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1.0, "quote_volume": None},
    ]
    assert MODULE.missing_expected_timestamps(rows, "15m", start, start + 1800) == [start + 900]


def test_archive_month_iteration_spans_year_boundary() -> None:
    start = MODULE.utc_timestamp("2024-12-31")
    end = MODULE.utc_timestamp("2025-02-01")
    assert [d.strftime("%Y%m") for d in MODULE._month_starts(start, end)] == ["202412", "202501", "202502"]


def test_recent_rest_window_is_aligned_and_at_most_10000_points() -> None:
    now_ts = 1800000000
    for interval in (900, 3600):
        start = MODULE.recent_rest_window_start(interval, now_ts=now_ts)
        last_closed = MODULE.last_closed_candle_start(now_ts, interval, now_ts=now_ts)
        assert start % interval == 0
        assert (last_closed - start) // interval + 1 <= 10000


def test_parse_public_rest_candle_keeps_quote_volume_unknown() -> None:
    row = MODULE._parse_rest_row({
        "t": 1800000000, "o": "100", "h": "105", "l": "95",
        "c": "102", "v": 12.5,
    })
    assert row == {
        "timestamp": 1800000000, "open": 100.0, "high": 105.0,
        "low": 95.0, "close": 102.0, "volume": 12.5, "quote_volume": None,
    }
    assert MODULE._validate_row(row, 300) is None


def test_public_rest_fetch_supports_native_15m_candles() -> None:
    timestamp = 1800000000

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return [{
                "t": timestamp, "o": "100", "h": "105", "l": "95",
                "c": "102", "v": 12.5,
            }]

    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            assert url == "https://api.gateio.ws/api/v4/futures/usdt/candlesticks"
            params = kwargs.get("params")
            assert isinstance(params, dict)
            self.calls.append(params)
            return FakeResponse()

    session = FakeSession()
    rows = MODULE.fetch_recent_rest_candles(
        session, "BTC_USDT", "15m", timestamp, timestamp, sleep_seconds=0,
    )
    assert rows == [{
        "timestamp": timestamp, "open": 100.0, "high": 105.0,
        "low": 95.0, "close": 102.0, "volume": 12.5, "quote_volume": None,
    }]
    assert session.calls == [{
        "contract": "BTC_USDT", "interval": "15m",
        "from": timestamp, "to": timestamp,
    }]


def test_public_rest_pagination_stays_within_900_candles() -> None:
    start = 1800000000
    end = start + 900 * 900

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return []

    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            params = kwargs.get("params")
            assert isinstance(params, dict)
            self.calls.append(params)
            return FakeResponse()

    session = FakeSession()
    MODULE.fetch_recent_rest_candles(
        session, "BTC_USDT", "15m", start, end, sleep_seconds=0,
    )
    assert len(session.calls) == 2
    assert session.calls[0]["from"] == start
    assert session.calls[0]["to"] == start + 899 * 900
    assert session.calls[1]["from"] == start + 900 * 900
    assert session.calls[1]["to"] == end
    assert all(
        (int(call["to"]) - int(call["from"])) // 900 + 1 <= 900
        for call in session.calls
    )
    assert all("limit" not in call for call in session.calls)


def test_missing_native_rest_repair_accepts_only_requested_gap_opens() -> None:
    start = 1735689600

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return [
                {"t": start, "o": "100", "h": "102", "l": "99", "c": "101", "v": 1},
                {"t": start + 900, "o": "101", "h": "103", "l": "100", "c": "102", "v": 2},
                {"t": start + 1800, "o": "102", "h": "104", "l": "101", "c": "103", "v": 3},
            ]

    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            assert url == "https://api.gateio.ws/api/v4/futures/usdt/candlesticks"
            params = kwargs.get("params")
            assert isinstance(params, dict)
            self.calls.append(params)
            return FakeResponse()

    session = FakeSession()
    rows = MODULE.fetch_missing_native_rest_candles(
        session, "BTC_USDT", "15m", [start, start + 1800],
        sleep_seconds=0, now_ts=start + 3600,
    )
    assert [row["timestamp"] for row in rows] == [start, start + 1800]
    assert all(row["quote_volume"] is None for row in rows)
    assert session.calls == [{
        "contract": "BTC_USDT", "interval": "15m",
        "from": start, "to": start + 1800,
    }]


def test_archive_fetch_supports_1m_files_for_gap_repair() -> None:
    import gzip

    timestamp = 1735689600
    archive_bytes = gzip.compress(b"1735689600,12.5,102,105,95,100\n")

    class FakeResponse:
        status_code = 200
        content = archive_bytes
        text = ""

    class FakeSession:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            self.urls.append(url)
            return FakeResponse()

    session = FakeSession()
    rows = MODULE.fetch_archive_candles(
        session, "BTC_USDT", "1m", timestamp, timestamp, sleep_seconds=0,
    )
    assert rows == [{
        "timestamp": timestamp, "volume": 12.5, "close": 102.0,
        "high": 105.0, "low": 95.0, "open": 100.0, "quote_volume": None,
    }]
    assert MODULE._validate_row(rows[0], 60) is None
    assert session.urls == [
        f"{MODULE.ARCHIVE_BASE_URL}/candlesticks_1m/202501/BTC_USDT-202501.csv.gz"
    ]


def test_current_month_archive_404_uses_public_rest_fallback() -> None:
    from datetime import datetime, timezone

    class FakeResponse:
        def __init__(self, status_code: int, payload: object = None, text: str = "") -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = text
            self.content = b""

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise MODULE.requests.HTTPError(f"HTTP {self.status_code}")

        def json(self) -> object:
            return self._payload

    class FakeSession:
        def __init__(self, candle: dict[str, object]) -> None:
            self.candle = candle
            self.calls: list[tuple[str, dict[str, object] | None]] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            params = kwargs.get("params")
            self.calls.append((url, params if isinstance(params, dict) else None))
            if url.startswith(MODULE.ARCHIVE_BASE_URL):
                return FakeResponse(404, text="not published yet")
            return FakeResponse(200, payload=[self.candle])

    now_ts = int(MODULE.time.time())
    month_start = int(datetime.fromtimestamp(now_ts, timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).timestamp())
    last_closed = MODULE.last_closed_candle_start(now_ts, 3600, now_ts=now_ts)
    candle = {
        "t": last_closed, "o": "100", "h": "105", "l": "95",
        "c": "102", "v": 12.5,
    }
    session = FakeSession(candle)
    rows = MODULE.fetch_archive_candles(
        session, "BTC_USDT", "1h", month_start, last_closed, sleep_seconds=0,
    )
    assert rows == [{
        "timestamp": last_closed, "open": 100.0, "high": 105.0,
        "low": 95.0, "close": 102.0, "volume": 12.5, "quote_volume": None,
    }]
    assert len(session.calls) == 2
    assert session.calls[0][0].startswith(MODULE.ARCHIVE_BASE_URL)
    assert session.calls[1][0] == "https://api.gateio.ws/api/v4/futures/usdt/candlesticks"



def test_missing_native_rest_repair_skips_timestamps_outside_recent_window() -> None:
    start = 1735689600

    class FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, **kwargs: object) -> object:
            self.calls += 1
            raise AssertionError("Old historical gaps must never be sent to recent REST")

    session = FakeSession()
    rows = MODULE.fetch_missing_native_rest_candles(
        session, "BTC_USDT", "15m", [start],
        sleep_seconds=0, now_ts=start + 20000 * 900,
    )
    assert rows == []
    assert session.calls == 0


def test_trade_archive_reconstructs_only_buckets_with_real_trades(capsys: object) -> None:
    import gzip

    start = 1735689600
    payload = (
        f"{start + 2}.1,10,100,2\n"
        f"{start + 100}.2,11,101,-3\n"
        f"{start + 200}.3,12,98,1\n"
        f"{start + 901}.1,13,200,5\n"
    ).encode("utf-8")
    archive_bytes = gzip.compress(payload)

    class FakeResponse:
        status_code = 200
        text = ""
        content = archive_bytes
        raw = None

        def close(self) -> None:
            return None

    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            self.calls.append((url, kwargs))
            return FakeResponse()

    session = FakeSession()
    rows = MODULE.fetch_missing_trade_archive_candles(
        session, "BTC_USDT", "15m", [start, start + 1800], sleep_seconds=0,
    )
    assert rows == [{
        "timestamp": start,
        "open": 100.0,
        "high": 101.0,
        "low": 98.0,
        "close": 98.0,
        "volume": 6.0,
        "quote_volume": None,
    }]
    assert len(session.calls) == 1
    assert session.calls[0][0] == (
        f"{MODULE.ARCHIVE_BASE_URL}/trades/202501/BTC_USDT-202501.csv.gz"
    )
    assert session.calls[0][1]["stream"] is True
    output = capsys.readouterr().out
    assert "rows_scanned=4" in output
    assert "matched_trade_rows=3" in output
    assert "wanted_buckets=2" in output
    assert "recovered_buckets=1" in output
    assert f"trade_timestamp_min={start + 2.1}" in output
    assert f"trade_timestamp_max={start + 901.1}" in output


def test_public_rest_http_400_is_not_retried_and_body_is_reported() -> None:
    import pytest

    class FakeResponse:
        status_code = 400
        text = '{"label":"INVALID_PARAM_VALUE","message":"bad time range"}'

        def raise_for_status(self) -> None:
            raise MODULE.requests.HTTPError("400 Client Error")

        def json(self) -> object:
            raise AssertionError("An HTTP error must fail before JSON parsing")

    class FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            self.calls += 1
            return FakeResponse()

    session = FakeSession()
    with pytest.raises(MODULE.DataError, match="bad time range"):
        MODULE.fetch_recent_rest_candles(
            session, "BTC_USDT", "15m", 1800000000, 1800000000,
            sleep_seconds=0,
        )
    assert session.calls == 1
