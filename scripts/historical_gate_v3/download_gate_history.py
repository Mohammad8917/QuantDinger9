#!/usr/bin/env python3
"""Download real Gate.io USDT-perpetual OHLCV for the locked QD V3 universe.

This is a DATA ACQUISITION tool only. It does not execute a strategy, simulate
fills, or submit orders. It uses Gate's public historical archive and public contract metadata; no API key is required.
Large data files are written outside the Git checkout by default.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ARCHIVE_BASE_URL = "https://download.gatedata.org/futures_usdt"
ARCHIVE_FIRST_MONTH = "202301"
CONTRACT_API_URL = "https://api.gateio.ws/api/v4/futures/usdt/contracts"
STRATEGY_PATH = "docs/strategies/QD_Adaptive_Quant_Portfolio_20_Risk_Controlled_V3.py"
LOCKED_STRATEGY_BLOB_SHA = "3cd1fbbcf3e57ad5031791b944ce764aad6151b1"
SYMBOLS = (
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "LINK", "POL",
    "ATOM", "NEAR", "APT", "ARB", "OP", "LTC", "BCH", "DOGE", "UNI", "ETC",
)
TIMEFRAMES = {"15m": 900, "1h": 3600}
FIELDS = ("timestamp", "open", "high", "low", "close", "volume", "quote_volume")
USER_AGENT = "QuantDinger9-V3-HistoricalData/1.0 (public-market-data-only)"


class DataError(RuntimeError):
    """Raised when the exchange returns unusable or inconsistent data."""


def utc_timestamp(value: str) -> int:
    """Parse YYYY-MM-DD or ISO-8601 and return an epoch timestamp in UTC."""
    raw = value.strip()
    if len(raw) == 10:
        parsed = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError(f"Timestamp must include a timezone: {value}")
        parsed = parsed.astimezone(timezone.utc)
    return int(parsed.timestamp())


def utc_end_timestamp(value: str) -> int:
    """Parse an inclusive UTC end date; date-only values include that whole day."""
    raw = value.strip()
    timestamp = utc_timestamp(raw)
    return timestamp + 24 * 60 * 60 if len(raw) == 10 else timestamp


def default_output_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache")
    return root / "QuantDinger9" / "historical" / "gate_v3"


def _blob_sha(content: bytes) -> str:
    return hashlib.sha1(f"blob {len(content)}\0".encode("ascii") + content).hexdigest()


def verify_locked_strategy(repo_root: Path) -> None:
    path = repo_root / STRATEGY_PATH
    if not path.is_file():
        raise DataError(f"Locked strategy file not found: {path}")
    actual = _blob_sha(path.read_bytes())
    if actual != LOCKED_STRATEGY_BLOB_SHA:
        raise DataError(
            "Refusing to collect data: locked V3 strategy fingerprint mismatch "
            f"(expected {LOCKED_STRATEGY_BLOB_SHA}, got {actual})."
        )


def _parse_archive_row(values: list[str]) -> dict[str, float | int | None] | None:
    """Parse Gate official monthly archive row: timestamp,size,close,high,low,open."""
    if len(values) != 6:
        return None
    try:
        timestamp_value = float(values[0])
        if not math.isfinite(timestamp_value) or not timestamp_value.is_integer():
            return None
        return {
            "timestamp": int(timestamp_value),
            "volume": float(values[1]),
            "close": float(values[2]),
            "high": float(values[3]),
            "low": float(values[4]),
            "open": float(values[5]),
            "quote_volume": None,
        }
    except (TypeError, ValueError, OverflowError):
        return None


def _validate_row(row: dict[str, float | int | None], interval: int) -> str | None:
    ts = int(row["timestamp"])
    o, h, low, close, volume = (
        float(row["open"]), float(row["high"]), float(row["low"]),
        float(row["close"]), float(row["volume"]),
    )
    quote_raw = row.get("quote_volume")
    quote_volume = None if quote_raw is None else float(quote_raw)
    values = (o, h, low, close, volume) + (() if quote_volume is None else (quote_volume,))
    if ts % interval:
        return "timestamp_not_aligned"
    if not all(math.isfinite(value) for value in values):
        return "non_finite_value"
    if min(o, h, low, close) <= 0:
        return "non_positive_price"
    if h < max(o, low, close):
        return "invalid_high"
    if low > min(o, h, close):
        return "invalid_low"
    if volume < 0:
        return "negative_volume"
    if quote_volume is not None and quote_volume < 0:
        return "negative_quote_volume"
    return None


def fetch_contract_create_time(
    session: requests.Session, contract: str, *, timeout_seconds: float = 20.0
) -> int:
    """Read public contract creation time to qualify historical coverage."""
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = session.get(
                f"{CONTRACT_API_URL}/{contract}", timeout=timeout_seconds,
                headers={"User-Agent": USER_AGENT},
            )
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt == 4:
                    response.raise_for_status()
                time.sleep(min(2 ** attempt, 12))
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise DataError(f"Unexpected Gate contract metadata for {contract}: expected object")
            created = int(float(payload["create_time"]))
            if created <= 0:
                raise DataError(f"Invalid Gate contract create_time for {contract}")
            return created
        except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError) as exc:
            last_error = exc
            if attempt == 4:
                break
            time.sleep(min(2 ** attempt, 12))
    raise DataError(f"Could not verify Gate contract creation time for {contract}: {last_error}")


def ceil_to_interval(timestamp: int, interval: int) -> int:
    """Return the first candle boundary at or after timestamp."""
    return ((timestamp + interval - 1) // interval) * interval


def last_closed_candle_start(end_ts: int, interval: int, now_ts: int | None = None) -> int:
    """Return latest candle open timestamp whose full interval has closed."""
    effective_end = min(end_ts, int(time.time()) if now_ts is None else now_ts)
    return (effective_end // interval) * interval - interval


def _month_starts(start_ts: int, end_ts: int) -> list[datetime]:
    """Return UTC first-of-month values spanning the inclusive timestamp range."""
    current = datetime.fromtimestamp(start_ts, timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = datetime.fromtimestamp(end_ts, timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    months: list[datetime] = []
    while current <= end:
        months.append(current)
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def _parse_rest_row(item: Any) -> dict[str, float | int | None] | None:
    """Parse one public Gate futures REST candle without inventing quote turnover."""
    if not isinstance(item, dict):
        return None
    try:
        timestamp_value = float(item["t"])
        if not math.isfinite(timestamp_value) or not timestamp_value.is_integer():
            return None
        return {
            "timestamp": int(timestamp_value),
            "open": float(item["o"]),
            "high": float(item["h"]),
            "low": float(item["l"]),
            "close": float(item["c"]),
            "volume": float(item["v"]),
            "quote_volume": None,
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def recent_rest_window_start(interval_seconds: int, *, now_ts: int | None = None) -> int:
    """Earliest aligned candle open within Gate's recent 10,000-point REST window."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    effective_now = int(time.time()) if now_ts is None else now_ts
    return ceil_to_interval(effective_now - interval_seconds * 9999, interval_seconds)


def fetch_recent_rest_candles(
    session: requests.Session,
    contract: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
    *,
    sleep_seconds: float = 0.05,
    timeout_seconds: float = 30.0,
) -> list[dict[str, float | int | None]]:
    """Fetch a bounded recent range from Gate REST in sub-2000-candle pages."""
    interval_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(timeframe)
    if interval_seconds is None:
        raise ValueError(f"Unsupported Gate REST timeframe: {timeframe}")
    if end_ts < start_ts:
        raise DataError(f"Invalid REST range for {contract} {timeframe}")
    url = "https://api.gateio.ws/api/v4/futures/usdt/candlesticks"
    rows: list[dict[str, float | int | None]] = []
    cursor = start_ts
    while cursor <= end_ts:
        page_end = min(end_ts, cursor + interval_seconds * 899)
        response = None
        for attempt in range(5):
            try:
                response = session.get(
                    url,
                    params={
                        "contract": contract,
                        "interval": timeframe,
                        "from": cursor,
                        "to": page_end,
                    },
                    timeout=timeout_seconds,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt == 4:
                        response.raise_for_status()
                    time.sleep(min(2 ** attempt, 12))
                    continue
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                if attempt == 4:
                    raise DataError(
                        f"Gate REST request failed for {contract} {timeframe} "
                        f"{cursor}..{page_end}: {exc}"
                    ) from exc
                time.sleep(min(2 ** attempt, 12))
        if response is None:
            raise DataError(f"Gate REST returned no response for {contract} {timeframe}")
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise DataError(
                f"Invalid Gate REST JSON for {contract} {timeframe}: {exc}"
            ) from exc
        if not isinstance(payload, list):
            raise DataError(f"Unexpected Gate REST response for {contract} {timeframe}: expected list")
        for item in payload:
            row = _parse_rest_row(item)
            if row is None:
                raise DataError(f"Malformed Gate REST candle for {contract} {timeframe}: {item!r}")
            timestamp = int(row["timestamp"])
            if timestamp % interval_seconds:
                raise DataError(
                    f"Unaligned Gate REST candle for {contract} {timeframe}: {timestamp}"
                )
            if cursor <= timestamp <= page_end and start_ts <= timestamp <= end_ts:
                rows.append(row)
        cursor = page_end + interval_seconds
        if sleep_seconds > 0 and cursor <= end_ts:
            time.sleep(sleep_seconds)
    # Preserve duplicate rows so the downstream audit can detect them; never silently repair source data.
    rows.sort(key=lambda row: int(row["timestamp"]))
    return rows


def fetch_archive_candles(
    session: requests.Session,
    contract: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
    *,
    sleep_seconds: float = 0.05,
    timeout_seconds: float = 30.0,
) -> list[dict[str, float | int | None]]:
    """Download and parse Gate's official monthly futures candle archive files."""
    interval_seconds = {"1m": 60, "5m": 300, "1h": 3600}.get(timeframe)
    if interval_seconds is None:
        raise ValueError(f"Unsupported Gate archive timeframe: {timeframe}")
    if end_ts < start_ts:
        raise DataError(f"Invalid archive range for {contract} {timeframe}")
    first_month = datetime.fromtimestamp(start_ts, timezone.utc).strftime("%Y%m")
    if first_month < ARCHIVE_FIRST_MONTH:
        raise DataError(
            f"Gate's documented public candle archive begins at {ARCHIVE_FIRST_MONTH}; "
            f"requested first month is {first_month}"
        )

    rows: list[dict[str, float | int | None]] = []
    for month_dt in _month_starts(start_ts, end_ts):
        month = month_dt.strftime("%Y%m")
        url = f"{ARCHIVE_BASE_URL}/candlesticks_{timeframe}/{month}/{contract}-{month}.csv.gz"
        response = None
        for attempt in range(5):
            try:
                response = session.get(
                    url, timeout=timeout_seconds, headers={"User-Agent": USER_AGENT}
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt == 4:
                        body = str(getattr(response, "text", ""))[:500]
                        raise DataError(
                            f"Gate archive HTTP {response.status_code} for {contract} "
                            f"{timeframe} {month}: {body or '<empty>'}"
                        )
                    time.sleep(min(2 ** attempt, 12))
                    continue
                if response.status_code == 404 and month == datetime.now(timezone.utc).strftime("%Y%m"):
                    # Gate publishes monthly archive files after the month closes. For the
                    # still-open current month only, use the public REST endpoint in bounded
                    # pages; historical months must exist in the archive or fail closed.
                    month_start_ts = int(month_dt.timestamp())
                    fallback_start = max(start_ts, month_start_ts)
                    now_ts = int(time.time())
                    fallback_end = min(
                        end_ts,
                        last_closed_candle_start(now_ts, interval_seconds, now_ts=now_ts),
                    )
                    if fallback_start > fallback_end:
                        break
                    recent_rows = fetch_recent_rest_candles(
                        session, contract, timeframe, fallback_start, fallback_end,
                        sleep_seconds=sleep_seconds, timeout_seconds=timeout_seconds,
                    )
                    rows.extend(recent_rows)
                    response = None
                    break
                if response.status_code >= 400:
                    body = str(getattr(response, "text", ""))[:500]
                    raise DataError(
                        f"Gate archive HTTP {response.status_code} for {contract} "
                        f"{timeframe} {month}: {body or '<empty>'}"
                    )
                break
            except requests.RequestException as exc:
                if attempt == 4:
                    raise DataError(
                        f"Gate archive request failed for {contract} {timeframe} {month}: {exc}"
                    ) from exc
                time.sleep(min(2 ** attempt, 12))
        if response is None:
            # Current-month REST fallback already appended the requested recent rows.
            continue
        if response.status_code >= 400:
            raise DataError(f"Gate archive request failed for {contract} {timeframe} {month}")
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(response.content), mode="rb") as zipped:
                text_stream = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
                reader = csv.reader(text_stream)
                for line_number, values in enumerate(reader, start=1):
                    if not values:
                        continue
                    row = _parse_archive_row(values)
                    if row is None:
                        raise DataError(
                            f"Malformed Gate archive row {line_number} for "
                            f"{contract} {timeframe} {month}: expected six numeric fields"
                        )
                    timestamp = int(row["timestamp"])
                    if timestamp % interval_seconds:
                        raise DataError(
                            f"Unaligned timestamp in Gate archive for {contract} "
                            f"{timeframe} {month}: {timestamp}"
                        )
                    if start_ts <= timestamp <= end_ts:
                        rows.append(row)
        except (OSError, EOFError, gzip.BadGzipFile, UnicodeError, csv.Error) as exc:
            raise DataError(
                f"Could not decode Gate archive for {contract} {timeframe} {month}: {exc}"
            ) from exc
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    rows.sort(key=lambda row: int(row["timestamp"]))
    if not rows:
        raise DataError(
            f"Gate archive returned no candles for {contract} {timeframe} "
            f"in {start_ts}..{end_ts}"
        )
    return rows


def aggregate_5m_to_15m(
    rows: list[dict[str, float | int | None]],
) -> list[dict[str, float | int | None]]:
    """Aggregate observed real 5m candles into 15m buckets without filling empty intervals."""
    groups: dict[int, list[dict[str, float | int | None]]] = {}
    for row in rows:
        timestamp = int(row["timestamp"])
        if timestamp % 300:
            raise DataError(f"Cannot aggregate unaligned 5m candle timestamp: {timestamp}")
        bucket = (timestamp // 900) * 900
        groups.setdefault(bucket, []).append(row)

    aggregated: list[dict[str, float | int | None]] = []
    for bucket, group in sorted(groups.items()):
        group.sort(key=lambda row: int(row["timestamp"]))
        timestamps = [int(row["timestamp"]) for row in group]
        if len(set(timestamps)) != len(timestamps):
            raise DataError(f"Duplicate 5m candle timestamp in 15m bucket {bucket}")
        # Official Gate archives omit some no-trade sub-intervals. Aggregate
        # only observed real source candles; an entirely empty bucket stays missing.
        if not group:
            continue
        aggregated.append({
            "timestamp": bucket,
            "open": float(group[0]["open"]),
            "high": max(float(row["high"]) for row in group),
            "low": min(float(row["low"]) for row in group),
            "close": float(group[-1]["close"]),
            "volume": sum(float(row["volume"]) for row in group),
            "quote_volume": None,
        })
    if not aggregated:
        raise DataError("No complete groups of three contiguous 5m candles were available for 15m aggregation")
    return aggregated


def aggregate_1m_to_timeframe(
    rows: list[dict[str, float | int | None]], timeframe: str,
) -> list[dict[str, float | int | None]]:
    """Aggregate observed real 1m candles into 15m/1h buckets without filling empty intervals."""
    interval = TIMEFRAMES.get(timeframe)
    if interval not in (900, 3600):
        raise ValueError(f"Unsupported 1m aggregation target: {timeframe}")
    groups: dict[int, list[dict[str, float | int | None]]] = {}
    for row in rows:
        timestamp = int(row["timestamp"])
        if timestamp % 60:
            raise DataError(f"Cannot aggregate unaligned 1m candle timestamp: {timestamp}")
        bucket = (timestamp // interval) * interval
        groups.setdefault(bucket, []).append(row)

    aggregated: list[dict[str, float | int | None]] = []
    for bucket, group in sorted(groups.items()):
        group.sort(key=lambda row: int(row["timestamp"]))
        timestamps = [int(row["timestamp"]) for row in group]
        if len(set(timestamps)) != len(timestamps):
            raise DataError(f"Duplicate 1m candle timestamp in {timeframe} bucket {bucket}")
        # Missing minutes are not filled. Real minute candles that do exist
        # determine target OHLCV; a bucket with no rows stays missing.
        if not group:
            continue
        aggregated.append({
            "timestamp": bucket,
            "open": float(group[0]["open"]),
            "high": max(float(row["high"]) for row in group),
            "low": min(float(row["low"]) for row in group),
            "close": float(group[-1]["close"]),
            "volume": sum(float(row["volume"]) for row in group),
            "quote_volume": None,
        })
    return aggregated


def missing_expected_timestamps(
    rows: list[dict[str, float | int | None]],
    timeframe: str,
    expected_start: int,
    expected_end: int,
) -> list[int]:
    """Return expected candle opens absent from real rows without filling them."""
    interval = TIMEFRAMES[timeframe]
    observed = {
        int(row["timestamp"])
        for row in rows
        if expected_start <= int(row["timestamp"]) <= expected_end
    }
    return [
        timestamp
        for timestamp in range(expected_start, expected_end + 1, interval)
        if timestamp not in observed
    ]


def audit_rows(
    rows: list[dict[str, float | int | None]], timeframe: str, *,
    expected_start: int | None = None, expected_end: int | None = None,
) -> dict[str, Any]:
    """Audit OHLCV validity, duplicate timestamps, internal gaps, and range-edge coverage."""
    interval = TIMEFRAMES[timeframe]
    invalid: dict[str, int] = {}
    seen: set[int] = set()
    for row in rows:
        reason = _validate_row(row, interval)
        if reason:
            invalid[reason] = invalid.get(reason, 0) + 1
        ts = int(row["timestamp"])
        if ts in seen:
            invalid["duplicate_timestamp"] = invalid.get("duplicate_timestamp", 0) + 1
        seen.add(ts)

    ordered = sorted(seen)
    gap_count = sum(1 for a, b in zip(ordered, ordered[1:]) if b - a > interval)
    internal_missing_bars = sum(
        max(0, (b - a) // interval - 1) for a, b in zip(ordered, ordered[1:])
    )
    has_range = expected_start is not None and expected_end is not None and expected_start <= expected_end
    if has_range:
        expected_bars = ((expected_end - expected_start) // interval) + 1
        in_range = [ts for ts in ordered if expected_start <= ts <= expected_end]
        leading_missing = max(0, (in_range[0] - expected_start) // interval) if in_range else expected_bars
        trailing_missing = max(0, (expected_end - in_range[-1]) // interval) if in_range else expected_bars
        observed_expected = len(in_range)
        missing_expected = max(0, expected_bars - observed_expected)
        coverage_ratio = observed_expected / expected_bars
    else:
        expected_bars = leading_missing = trailing_missing = observed_expected = missing_expected = 0
        coverage_ratio = None

    out_of_range_timestamps = (
        sum(1 for ts in ordered if not expected_start <= ts <= expected_end)
        if has_range else 0
    )
    complete = bool(
        has_range and expected_bars > 0 and observed_expected == expected_bars
        and out_of_range_timestamps == 0
        and gap_count == 0 and not invalid and leading_missing == 0 and trailing_missing == 0
    )
    return {
        "bars": len(rows), "unique_timestamps": len(ordered),
        "first_timestamp": ordered[0] if ordered else None,
        "last_timestamp": ordered[-1] if ordered else None,
        "expected_first_timestamp": expected_start if has_range else None,
        "expected_last_timestamp": expected_end if has_range else None,
        "expected_bars": expected_bars, "observed_expected_bars": observed_expected,
        "missing_expected_bars": missing_expected, "leading_missing_bars": leading_missing,
        "trailing_missing_bars": trailing_missing, "coverage_ratio": coverage_ratio,
        "out_of_range_timestamps": out_of_range_timestamps,
        "invalid_rows": invalid, "gap_count": gap_count,
        "internal_missing_bars": internal_missing_bars,
        "complete_contiguous_history": complete,
    }


def write_gzip_csv(path: Path, rows: list[dict[str, float | int | None]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=6) as zipped:
            # Text wrapper avoids platform-dependent newlines; UTF-8 CSV is deterministic.
            import io
            text_stream = io.TextIOWrapper(zipped, encoding="utf-8", newline="", write_through=True)
            writer = csv.DictWriter(text_stream, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            text_stream.flush()
            text_stream.detach()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def run_download(repo_root: Path, output_dir: Path, start_ts: int, end_ts: int) -> dict[str, Any]:
    if end_ts <= start_ts:
        raise ValueError("end date must be later than start date")
    verify_locked_strategy(repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    manifest: dict[str, Any] = {
        "schema_version": 3,
        "data_source": "Gate official monthly futures candle archives plus public REST for the recent 10,000-point tail; public contracts REST API for create_time",
        "archive_first_documented_month": ARCHIVE_FIRST_MONTH,
        "archive_intervals_downloaded": ["1m", "5m", "1h"],
        "recent_rest_policy": "Public REST is used only for the latest aligned window of at most 10,000 points per timeframe; older history comes from official monthly archives.",
        "coverage_policy": "Expected range begins at max(requested start, public contract create_time), rounded up to a candle boundary; only fully closed candles are expected.",
        "endpoint": "Gate official monthly archives plus https://api.gateio.ws/api/v4/futures/usdt/candlesticks for the bounded recent tail",
        "strategy_path": STRATEGY_PATH,
        "locked_strategy_git_blob_sha1": LOCKED_STRATEGY_BLOB_SHA,
        "start_timestamp_requested": start_ts,
        "end_timestamp_requested": end_ts,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "order_execution": "NOT_PERFORMED_DATA_DOWNLOAD_ONLY",
        "quote_volume_available": False,
        "quote_volume_policy": "Gate historical candle archives provide contract-size volume but not quote-currency turnover; quote_volume is blank, never estimated.",
        "fifteen_minute_policy": "Historical 15m candles are aggregated from observed real 5m archive candles; missing 15m/1h intervals are recovered from observed real 1m candles within that interval. Empty intervals remain missing, no synthetic candles are created, and unresolved gaps fail closed.",
        "gap_repair_policy": "Repair missing 15m/1h opens from observed real 1m candles within the interval. Empty intervals are not synthesized; any remaining expected gaps make the collection fail.",
        "symbols": {},
    }
    failures: list[str] = []
    for base in SYMBOLS:
        contract = f"{base}_USDT"
        manifest["symbols"][contract] = {}
        try:
            create_time = fetch_contract_create_time(session, contract)
            manifest["symbols"][contract]["contract_metadata"] = {
                "create_time": create_time, "source": f"{CONTRACT_API_URL}/{contract}",
            }
        except Exception as exc:
            failures.append(f"{contract} contract metadata: {exc}")
            manifest["symbols"][contract]["contract_metadata"] = {"error": str(exc)}
            for timeframe in TIMEFRAMES:
                manifest["symbols"][contract][timeframe] = {
                    "error": "Skipped because contract history start could not be verified"
                }
                failures.append(f"{contract} {timeframe}: skipped; contract metadata unavailable")
            continue

        for timeframe, interval in TIMEFRAMES.items():
            print(f"[download] {contract} {timeframe}", flush=True)
            requested_first = ceil_to_interval(max(start_ts, create_time), interval)
            requested_last = last_closed_candle_start(end_ts, interval)
            if requested_first > requested_last:
                manifest["symbols"][contract][timeframe] = {
                    "interval_seconds": interval, "contract_create_time": create_time,
                    "expected_bars": 0, "coverage_status": "no_expected_bars_in_requested_range",
                    "complete_contiguous_history": None,
                }
                continue
            try:
                recent_first = max(
                    requested_first, recent_rest_window_start(interval, now_ts=int(time.time()))
                )
                archive_last = min(requested_last, recent_first - interval)
                archive_rows: list[dict[str, float | int | None]] = []
                recent_rows: list[dict[str, float | int | None]] = []
                archive_source_label = ""
                if requested_first <= archive_last:
                    if timeframe == "15m":
                        source_rows = fetch_archive_candles(
                            session, contract, "5m", requested_first, archive_last + 600,
                        )
                        archive_rows = aggregate_5m_to_15m(source_rows)
                        archive_source_label = "Gate 5m archive aggregated from observed real candles"
                    else:
                        archive_rows = fetch_archive_candles(
                            session, contract, "1h", requested_first, archive_last,
                        )
                        archive_source_label = "Gate official monthly 1h archive"
                if recent_first <= requested_last:
                    recent_rows = fetch_recent_rest_candles(
                        session, contract, timeframe, recent_first, requested_last,
                    )
                rows = sorted(
                    archive_rows + recent_rows,
                    key=lambda row: int(row["timestamp"]),
                )
                source_parts: list[str] = []
                if archive_rows:
                    source_parts.append(archive_source_label)
                if recent_rows:
                    source_parts.append("Gate public futures REST recent tail")

                missing_before_repair = missing_expected_timestamps(
                    rows, timeframe, requested_first, requested_last,
                )
                repaired_rows: list[dict[str, float | int | None]] = []
                missing_by_month: dict[str, list[int]] = {}
                for timestamp in missing_before_repair:
                    month = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y%m")
                    missing_by_month.setdefault(month, []).append(timestamp)
                for month, missing_in_month in sorted(missing_by_month.items()):
                    repair_start = missing_in_month[0]
                    repair_end = missing_in_month[-1] + interval - 60
                    try:
                        minute_rows = fetch_archive_candles(
                            session, contract, "1m", repair_start, repair_end,
                        )
                        candidates = aggregate_1m_to_timeframe(minute_rows, timeframe)
                        wanted = set(missing_in_month)
                        accepted = [
                            row for row in candidates if int(row["timestamp"]) in wanted
                        ]
                        repaired_rows.extend(accepted)
                        print(
                            f"[repair] {contract} {timeframe} {month}: "
                            f"{len(accepted)}/{len(missing_in_month)} missing bars recovered "
                            "from observed real 1m candles",
                            flush=True,
                        )
                    except Exception as repair_error:
                        # Preserve original rows and let the final strict audit report
                        # every gap that the independent 1m source could not repair.
                        print(
                            f"[repair-warning] {contract} {timeframe} {month}: "
                            f"1m archive repair unavailable: {repair_error}",
                            flush=True,
                        )
                if repaired_rows:
                    rows = sorted(rows + repaired_rows, key=lambda row: int(row["timestamp"]))
                    source_parts.append("Gate 1m archive recovery for missing intervals with observed trades")
                source_label = " + ".join(source_parts) or "no source rows"
                audit = audit_rows(
                    rows, timeframe, expected_start=requested_first, expected_end=requested_last,
                )
                if audit["invalid_rows"]:
                    raise DataError(f"Invalid candle rows: {audit['invalid_rows']}")
                if not audit["complete_contiguous_history"]:
                    failures.append(
                        f"{contract} {timeframe}: incomplete coverage "
                        f"({audit['missing_expected_bars']} expected bars missing; "
                        f"{audit['gap_count']} internal gap spans)"
                    )
                filename = f"{contract}_{timeframe}.csv.gz"
                sha256 = write_gzip_csv(output_dir / filename, rows)
                manifest["symbols"][contract][timeframe] = {
                    **audit, "file": filename, "sha256": sha256, "interval_seconds": interval,
                    "contract_create_time": create_time, "quote_volume_available": False,
                    "volume_source": "Gate contract-size volume (archive size / REST v)",
                    "source": source_label,
                    "coverage_status": "complete" if audit["complete_contiguous_history"] else "partial",
                }
                print(
                    f"[ok] {contract} {timeframe}: {audit['bars']} bars; "
                    f"expected={audit['expected_bars']}; missing={audit['missing_expected_bars']}; "
                    f"gap_spans={audit['gap_count']}; sha256={sha256}", flush=True,
                )
            except Exception as exc:
                failures.append(f"{contract} {timeframe}: {exc}")
                manifest["symbols"][contract][timeframe] = {
                    "error": str(exc), "expected_first_timestamp": requested_first,
                    "expected_last_timestamp": requested_last,
                    "expected_bars": ((requested_last - requested_first) // interval) + 1,
                    "contract_create_time": create_time, "coverage_status": "failed",
                    "complete_contiguous_history": False,
                }
                print(f"[error] {contract} {timeframe}: {exc}", file=sys.stderr, flush=True)
    manifest["failures"] = failures
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if failures:
        raise DataError(
            f"Historical collection incomplete: {len(failures)} symbol/timeframe jobs failed. "
            f"Details are recorded in {manifest_path}"
        )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="UTC date/time; default: two years before --end (YYYY-MM-DD)")
    parser.add_argument("--end", help="UTC date/time; default: current UTC time")
    parser.add_argument(
        "--probe-only", action="store_true",
        help="Probe Gate official monthly 5m and 1h archive files for BTC_USDT; do not save a dataset",
    )
    parser.add_argument("--output", type=Path, default=default_output_dir(),
                        help="Output directory (default is outside the Git checkout)")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="QuantDinger9 repository root; used only to verify the locked strategy")
    args = parser.parse_args(argv)
    end_ts = utc_end_timestamp(args.end) if args.end else int(time.time())
    start_ts = utc_timestamp(args.start) if args.start else end_ts - 2 * 365 * 24 * 60 * 60
    if args.probe_only:
        try:
            verify_locked_strategy(args.repo_root.resolve())
            import io

            session = requests.Session()
            month = datetime.fromtimestamp(start_ts, timezone.utc).strftime("%Y%m")
            for timeframe in ("5m", "1h"):
                url = (
                    "https://download.gatedata.org/futures_usdt/"
                    f"candlesticks_{timeframe}/{month}/BTC_USDT-{month}.csv.gz"
                )
                response = session.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
                if response.status_code != 200:
                    body = str(getattr(response, "text", ""))[:1000]
                    raise DataError(
                        f"Gate historical archive probe failed for {timeframe}: "
                        f"HTTP {response.status_code}; response body: {body or '<empty>'}"
                    )
                with gzip.GzipFile(fileobj=io.BytesIO(response.content), mode="rb") as zipped:
                    sample = zipped.readline().decode("utf-8", errors="replace").strip()
                print(
                    f"ARCHIVE_PROBE_OK: {timeframe} month={month} "
                    f"compressed_bytes={len(response.content)} first_row={sample}",
                    flush=True,
                )
            print("ARCHIVE_PROBE_COMPLETE: only two public archive samples were checked; no dataset or orders were created.")
            return 0
        except (DataError, ValueError, OSError, requests.RequestException) as exc:
            print(f"PROBE_FAILED: {exc}", file=sys.stderr)
            return 1
    try:
        manifest = run_download(args.repo_root.resolve(), args.output.expanduser().resolve(), start_ts, end_ts)
    except (DataError, ValueError, OSError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    total_bars = sum(
        int(info.get("bars", 0))
        for symbol in manifest["symbols"].values()
        for info in symbol.values()
        if isinstance(info, dict)
    )
    print(f"COMPLETE: {total_bars} real candles saved under {args.output.resolve()}")
    print("This program downloaded and audited data only; no backtest or orders were run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
