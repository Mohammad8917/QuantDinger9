"""Offline tests for the Gate V3 historical data acquisition tool."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

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
    assert audit["complete_source_coverage"] is True


def test_audit_accepts_verified_source_empty_buckets_without_claiming_contiguous_history() -> None:
    start = 1800000000
    rows = [
        {"timestamp": start, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0, "quote_volume": None},
        {"timestamp": start + 1800, "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 2.0, "quote_volume": None},
    ]
    audit = MODULE.audit_rows(
        rows, "15m", expected_start=start, expected_end=start + 2700,
        verified_source_empty_timestamps={start + 900, start + 2700},
    )
    assert audit["missing_expected_bars"] == 2
    assert audit["verified_source_empty_bars"] == 2
    assert audit["unresolved_missing_bars"] == 0
    assert audit["source_coverage_ratio"] == 1.0
    assert audit["complete_source_coverage"] is True
    assert audit["complete_contiguous_history"] is False


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


def test_aggregate_15m_omits_incomplete_5m_source_buckets() -> None:
    start = 1800000000
    rows = [
        {"timestamp": start, "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1.0, "quote_volume": None},
        {"timestamp": start + 300, "open": 101.0, "high": 104.0, "low": 100.0, "close": 103.0, "volume": 2.0, "quote_volume": None},
        {"timestamp": start + 600, "open": 103.0, "high": 105.0, "low": 102.0, "close": 104.0, "volume": 3.0, "quote_volume": None},
        {"timestamp": start + 900, "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0, "volume": 4.0, "quote_volume": None},
        {"timestamp": start + 1500, "open": 105.0, "high": 107.0, "low": 104.0, "close": 106.0, "volume": 5.0, "quote_volume": None},
    ]
    aggregated = MODULE.aggregate_5m_to_15m(rows)
    assert aggregated == [{
        "timestamp": start, "open": 100.0, "high": 105.0, "low": 99.0,
        "close": 104.0, "volume": 6.0, "quote_volume": None,
    }]

def test_aggregate_15m_rejects_duplicate_5m_timestamps() -> None:
    row = {"timestamp": 1800000000, "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1.0, "quote_volume": None}
    try:
        MODULE.aggregate_5m_to_15m([row, dict(row)])
    except MODULE.DataError as exc:
        assert "Duplicate 5m candle timestamp" in str(exc)
    else:
        raise AssertionError("Duplicate source candles must not be silently aggregated")

def test_aggregate_10s_to_15m_requires_complete_source_bucket() -> None:
    start = 1735689600
    rows = [
        {"timestamp": start + index * 10, "open": 100.0 + index,
         "high": 101.0 + index, "low": 99.0 + index,
         "close": 100.5 + index, "volume": 1.0, "quote_volume": None}
        for index in range(90)
    ]
    aggregated = MODULE.aggregate_10s_to_timeframe(rows, "15m")
    assert aggregated == [{
        "timestamp": start, "open": 100.0, "high": 190.0, "low": 99.0,
        "close": 189.5, "volume": 90.0, "quote_volume": None,
    }]
    assert MODULE.aggregate_10s_to_timeframe(rows[:-1], "15m") == []


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

def test_native_15m_archive_is_preferred_when_available() -> None:
    import gzip

    timestamp = 1800000000
    archive_bytes = gzip.compress(
        f"{timestamp},12.5,102,105,95,100\n".encode("utf-8")
    )

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
    rows, source = MODULE.fetch_15m_archive_candles(
        session, "BTC_USDT", timestamp, timestamp, sleep_seconds=0,
    )
    assert source == "Gate official native 15m candle archive"
    assert [row["timestamp"] for row in rows] == [timestamp]
    assert session.urls == [
        f"{MODULE.ARCHIVE_BASE_URL}/candlesticks_15m/202701/BTC_USDT-202701.csv.gz"
    ]


def test_native_15m_archive_404_falls_back_to_complete_real_5m_group() -> None:
    import gzip

    timestamp = 1800000000
    five_minute_rows = "".join(
        f"{timestamp + index * 300},{index + 1},{101 + index},{102 + index},"
        f"{99 + index},{100 + index}\n"
        for index in range(3)
    )
    archive_bytes = gzip.compress(five_minute_rows.encode("utf-8"))

    class FakeResponse:
        def __init__(self, status_code: int, content: bytes = b"") -> None:
            self.status_code = status_code
            self.content = content
            self.text = "not found" if status_code == 404 else ""

    class FakeSession:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            self.urls.append(url)
            if "candlesticks_15m" in url:
                return FakeResponse(404)
            return FakeResponse(200, archive_bytes)

    session = FakeSession()
    rows, source = MODULE.fetch_15m_archive_candles(
        session, "BTC_USDT", timestamp, timestamp, sleep_seconds=0,
    )
    assert source == "Gate 5m archive aggregated from observed real candles"
    assert rows == [{
        "timestamp": timestamp, "open": 100.0, "high": 104.0, "low": 99.0,
        "close": 103.0, "volume": 6.0, "quote_volume": None,
    }]
    assert len(session.urls) == 2
    assert "candlesticks_15m" in session.urls[0]
    assert "candlesticks_5m" in session.urls[1]


def test_aggregate_1m_to_15m_omits_incomplete_source_buckets() -> None:
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
    assert MODULE.aggregate_1m_to_timeframe(rows, "15m") == []
    complete_rows = [
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
    ]
    assert MODULE.aggregate_1m_to_timeframe(complete_rows, "15m") == [{
        "timestamp": start, "open": 100.0, "high": 115.0, "low": 99.0,
        "close": 114.5, "volume": 15.0, "quote_volume": None,
    }]



def test_aggregate_1m_to_1h_omits_incomplete_source_buckets() -> None:
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
    assert MODULE.aggregate_1m_to_timeframe(rows, "1h") == []
    complete_rows = [
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
    ]
    assert MODULE.aggregate_1m_to_timeframe(complete_rows, "1h") == [{
        "timestamp": start, "open": 100.0, "high": 160.0, "low": 99.0,
        "close": 159.5, "volume": 60.0, "quote_volume": None,
    }]



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


def test_current_month_archive_404_rest_fallback_stays_inside_recent_window(monkeypatch: Any) -> None:
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
    monkeypatch.setattr(MODULE.time, "time", lambda: now_ts)
    month_start = int(datetime.fromtimestamp(now_ts, timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).timestamp())
    expected_rest_start = MODULE.recent_rest_window_start(60, now_ts=now_ts)
    last_closed = MODULE.last_closed_candle_start(now_ts, 60, now_ts=now_ts)
    candle = {
        "t": last_closed, "o": "100", "h": "105", "l": "95",
        "c": "102", "v": 12.5,
    }
    session = FakeSession(candle)
    rows = MODULE.fetch_archive_candles(
        session, "BTC_USDT", "1m", month_start, last_closed, sleep_seconds=0,
    )
    assert rows == [{
        "timestamp": last_closed, "open": 100.0, "high": 105.0,
        "low": 95.0, "close": 102.0, "volume": 12.5, "quote_volume": None,
    }]
    assert session.calls[0][0].startswith(MODULE.ARCHIVE_BASE_URL)
    rest_calls = [call for call in session.calls if call[0] == "https://api.gateio.ws/api/v4/futures/usdt/candlesticks"]
    assert rest_calls
    assert rest_calls[0][1] == {
        "contract": "BTC_USDT", "interval": "1m",
        "from": expected_rest_start, "to": min(last_closed, expected_rest_start + 899 * 60),
    }
    assert all(
        (int(params["to"]) - int(params["from"])) // 60 + 1 <= 900
        for _, params in rest_calls if params is not None
    )
    assert all(int(params["from"]) >= expected_rest_start for _, params in rest_calls if params is not None)


def test_missing_native_rest_repair_skips_gaps_outside_recent_window() -> None:
    start = 1735689600

    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get(self, url: str, **kwargs: object) -> object:
            self.calls.append(kwargs)
            raise AssertionError("Historical gaps outside Gate's recent window must not call REST")

    session = FakeSession()
    rows = MODULE.fetch_missing_native_rest_candles(
        session, "BTC_USDT", "15m", [start],
        sleep_seconds=0, now_ts=start + 20000 * 900,
    )
    assert rows == []
    assert session.calls == []


def test_audit_reports_exact_unresolved_timestamps() -> None:
    start = 1800000000
    rows = [
        {"timestamp": start, "open": 100.0, "high": 101.0, "low": 99.0,
         "close": 100.5, "volume": 1.0, "quote_volume": None},
    ]
    audit = MODULE.audit_rows(
        rows, "15m", expected_start=start, expected_end=start + 1800,
    )
    assert audit["unresolved_missing_timestamps"] == [start + 900, start + 1800]
    assert audit["unresolved_missing_bars"] == 2


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

def test_parse_futures_trade_row_preserves_signed_size() -> None:
    row = MODULE.parse_futures_trade_row(["1800000000.125", "42", "101.5", "-3"])
    assert row == (1800000000.125, 42, 101.5, -3.0)


def test_trade_aggregation_uses_real_trade_order_and_absolute_contract_volume() -> None:
    start = 1800000000
    trades = [
        (start + 700.0, 3, 102.0, -2.0),
        (start + 100.0, 1, 100.0, 3.0),
        (start + 500.0, 2, 105.0, -4.0),
        (start + 901.0, 4, 110.0, 1.0),
    ]
    candles = MODULE.aggregate_futures_trades_to_15m(trades)
    assert candles == [
        {
            "timestamp": start, "open": 100.0, "high": 105.0, "low": 100.0,
            "close": 102.0, "volume": 9.0, "quote_volume": None,
        },
        {
            "timestamp": start + 900, "open": 110.0, "high": 110.0, "low": 110.0,
            "close": 110.0, "volume": 1.0, "quote_volume": None,
        },
    ]


def test_trade_reconstruction_requires_minimum_overlap_and_exact_ohlcv() -> None:
    start = 1800000000
    trades = [
        (start + index * 900 + 1.0, index, 100.0 + index, 2.0)
        for index in range(MODULE.MIN_TRADE_VALIDATION_OVERLAP)
    ]
    reconstructed = MODULE.aggregate_futures_trades_to_15m(trades)
    official = [dict(row) for row in reconstructed]
    validation = MODULE.validate_trade_reconstruction(reconstructed, official)
    assert validation["valid"] is True
    assert validation["overlap_bars"] == MODULE.MIN_TRADE_VALIDATION_OVERLAP
    assert validation["reason"] == "OHLCV matches"

    insufficient = MODULE.validate_trade_reconstruction(reconstructed[:3], official[:3])
    assert insufficient["valid"] is False
    assert insufficient["overlap_bars"] == 3
    assert "insufficient overlap" in insufficient["reason"]


def test_trade_reconstruction_rejects_missing_official_positive_volume_candle() -> None:
    start = 1800000000
    trades = [
        (start + index * 900 + 1.0, index, 100.0 + index, 2.0)
        for index in range(MODULE.MIN_TRADE_VALIDATION_OVERLAP)
    ]
    reconstructed = MODULE.aggregate_futures_trades_to_15m(trades)
    official = [dict(row) for row in reconstructed]
    official.append({
        "timestamp": start + MODULE.MIN_TRADE_VALIDATION_OVERLAP * 900,
        "open": 250.0, "high": 251.0, "low": 249.0, "close": 250.5,
        "volume": 5.0, "quote_volume": None,
    })

    validation = MODULE.validate_trade_reconstruction(reconstructed, official)

    assert validation["overlap_bars"] == MODULE.MIN_TRADE_VALIDATION_OVERLAP
    assert validation["valid"] is False
    assert validation["reason"] == "OHLCV mismatch"
    assert any("missing_trade_candle" in item["fields"] for item in validation["mismatches"])


def test_trade_reconstruction_allows_official_zero_volume_candle_without_trade() -> None:
    start = 1800000000
    trades = [
        (start + index * 900 + 1.0, index, 100.0 + index, 2.0)
        for index in range(MODULE.MIN_TRADE_VALIDATION_OVERLAP)
    ]
    reconstructed = MODULE.aggregate_futures_trades_to_15m(trades)
    official = [dict(row) for row in reconstructed]
    official.append({
        "timestamp": start + MODULE.MIN_TRADE_VALIDATION_OVERLAP * 900,
        "open": 199.0, "high": 199.0, "low": 199.0, "close": 199.0,
        "volume": 0.0, "quote_volume": None,
    })

    validation = MODULE.validate_trade_reconstruction(reconstructed, official)

    assert validation["overlap_bars"] == MODULE.MIN_TRADE_VALIDATION_OVERLAP
    assert validation["valid"] is True
    assert validation["reason"] == "OHLCV matches"


def test_trade_reconstruction_rejects_any_ohlcv_mismatch() -> None:
    start = 1800000000
    trades = [
        (start + index * 900 + 1.0, index, 100.0 + index, 2.0)
        for index in range(MODULE.MIN_TRADE_VALIDATION_OVERLAP)
    ]
    reconstructed = MODULE.aggregate_futures_trades_to_15m(trades)
    official = [dict(row) for row in reconstructed]
    official[10]["volume"] = float(official[10]["volume"]) + 1.0
    validation = MODULE.validate_trade_reconstruction(reconstructed, official)
    assert validation["valid"] is False
    assert validation["reason"] == "OHLCV mismatch"
    assert validation["mismatches"]


def test_monthly_trade_archive_rejects_duplicate_deal_ids() -> None:
    import gzip

    content = gzip.compress(
        (
            "1735689600.1,42,100.0,1\n"
            "1735689600.2,42,100.5,-1\n"
        ).encode("utf-8")
    )

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self) -> None:
            self.content = content

    class FakeSession:
        def get(self, url: str, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    try:
        MODULE.fetch_monthly_futures_trades(FakeSession(), "BTC_USDT", "202501")
    except MODULE.DataError as exc:
        assert "duplicate dealid 42" in str(exc)
    else:
        raise AssertionError("Duplicate trade IDs must reject the archive")


def test_monthly_trade_archive_rejects_rows_outside_requested_month() -> None:
    import gzip

    # 2024-12-31 23:59:59 UTC is outside the requested 2025-01 archive.
    content = gzip.compress(
        "1735689599,43,100.0,1\n".encode("utf-8")
    )

    payload = content
    class FakeResponse:
        status_code = 200
        content = payload
        text = ""

    class FakeSession:
        def get(self, url: str, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    try:
        MODULE.fetch_monthly_futures_trades(FakeSession(), "BTC_USDT", "202501")
    except MODULE.DataError as exc:
        assert "falls outside requested month 202501" in str(exc)
    else:
        raise AssertionError("Out-of-month trades must reject the archive")


def test_monthly_trade_archive_404_is_unavailable_not_zero_trade() -> None:
    class FakeResponse:
        status_code = 404
        text = "not found"

    class FakeSession:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            self.urls.append(url)
            return FakeResponse()

    session = FakeSession()
    assert MODULE.fetch_monthly_futures_trades(
        session, "BTC_USDT", "202501",
    ) is None
    assert session.urls == [
        f"{MODULE.ARCHIVE_BASE_URL}/trades/202501/BTC_USDT-202501.csv.gz"
    ]

