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
    """Fetch any supported Gate REST time range in pages of at most 900 candles."""
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
            except requests.HTTPError as exc:
                # HTTP 4xx parameter/range errors are deterministic; do not retry them.
                status = response.status_code if response is not None else None
                body = str(getattr(response, "text", "") or "").strip()[:500]
                if status not in (429, 500, 502, 503, 504):
                    detail = body or str(exc)
                    raise DataError(
                        f"Gate REST HTTP {status} for {contract} {timeframe} "
                        f"{cursor}..{page_end}: {detail}"
                    ) from exc
                if attempt == 4:
                    raise DataError(
                        f"Gate REST request failed for {contract} {timeframe} "
                        f"{cursor}..{page_end}: HTTP {status}: {body or exc}"
                    ) from exc
                time.sleep(min(2 ** attempt, 12))
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
    interval_seconds = {"10s": 10, "1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(timeframe)
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
                    # Monthly archives are not published until the month closes.
                    # REST fallback is allowed only for intervals supported by the
                    # public endpoint and only inside its latest 10,000-point window.
                    if timeframe not in {"1m", "5m", "1h"}:
                        response = None
                        break
                    month_start_ts = int(month_dt.timestamp())
                    now_ts = int(time.time())
                    fallback_start = max(
                        start_ts,
                        month_start_ts,
                        recent_rest_window_start(interval_seconds, now_ts=now_ts),
                    )
                    fallback_end = min(
                        end_ts,
                        last_closed_candle_start(now_ts, interval_seconds, now_ts=now_ts),
                    )
                    if fallback_start > fallback_end:
                        response = None
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
            # Current-month fallback was either completed above or is unsupported.
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
    """Aggregate only 15m buckets with all three observed real 5m candles."""
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
        # Without independent proof that a missing sub-interval had no trades,
        # partial groups cannot establish complete target OHLCV. Leave them absent.
        if timestamps != list(range(bucket, bucket + 900, 300)):
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


def fetch_15m_archive_candles(
    session: requests.Session,
    contract: str,
    start_ts: int,
    end_ts: int,
    *,
    sleep_seconds: float = 0.05,
) -> tuple[list[dict[str, float | int | None]], str]:
    """Prefer Gate's native 15m archive; fall back to complete real 5m groups only if unavailable."""
    try:
        native_rows = fetch_archive_candles(
            session, contract, "15m", start_ts, end_ts,
            sleep_seconds=sleep_seconds,
        )
    except DataError as exc:
        # A missing native archive is an availability limitation, not permission
        # to invent candles. Other errors (bad gzip, malformed rows, HTTP 5xx)
        # must remain visible instead of being silently hidden by fallback.
        if "Gate archive HTTP 404" not in str(exc):
            raise
        native_rows = []
        print(
            f"[15m-archive-fallback] {contract}: native 15m archive unavailable; "
            "using complete observed 5m archive groups",
            flush=True,
        )

    if native_rows:
        return native_rows, "Gate official native 15m candle archive"

    source_rows = fetch_archive_candles(
        session, contract, "5m", start_ts, end_ts + 600,
        sleep_seconds=sleep_seconds,
    )
    aggregated_rows = aggregate_5m_to_15m(source_rows)
    return aggregated_rows, "Gate 5m archive aggregated from observed real candles"


def aggregate_1m_to_timeframe(
    rows: list[dict[str, float | int | None]], timeframe: str,
) -> list[dict[str, float | int | None]]:
    """Aggregate only target buckets with complete observed 1m source coverage."""
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
        # A partial minute set cannot prove full target OHLCV. Do not assume
        # missing minutes were zero-trade intervals; keep this target bucket absent.
        if timestamps != list(range(bucket, bucket + interval, 60)):
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


def aggregate_10s_to_timeframe(
    rows: list[dict[str, float | int | None]], timeframe: str,
) -> list[dict[str, float | int | None]]:
    """Aggregate only target buckets with complete observed official 10s coverage."""
    interval = TIMEFRAMES.get(timeframe)
    if interval not in (900, 3600):
        raise ValueError(f"Unsupported 10s aggregation target: {timeframe}")
    groups: dict[int, list[dict[str, float | int | None]]] = {}
    for row in rows:
        timestamp = int(row["timestamp"])
        if timestamp % 10:
            raise DataError(f"Cannot aggregate unaligned 10s candle timestamp: {timestamp}")
        bucket = (timestamp // interval) * interval
        groups.setdefault(bucket, []).append(row)

    aggregated: list[dict[str, float | int | None]] = []
    for bucket, group in sorted(groups.items()):
        group.sort(key=lambda row: int(row["timestamp"]))
        timestamps = [int(row["timestamp"]) for row in group]
        if len(set(timestamps)) != len(timestamps):
            raise DataError(f"Duplicate 10s candle timestamp in {timeframe} bucket {bucket}")
        # Never promote a partial 10s window to a full 15m/1h candle.
        if timestamps != list(range(bucket, bucket + interval, 10)):
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


def fetch_missing_10s_archive_candles(
    session: requests.Session,
    contract: str,
    timeframe: str,
    missing_timestamps: list[int],
    *,
    sleep_seconds: float = 0.05,
) -> list[dict[str, float | int | None]]:
    """Recover historical gaps from Gate's official 10s candle archive, without synthesis."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported 10s archive repair timeframe: {timeframe}")
    if not missing_timestamps:
        return []

    interval = TIMEFRAMES[timeframe]
    missing_by_month: dict[str, list[int]] = {}
    for timestamp in sorted(set(missing_timestamps)):
        month = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y%m")
        missing_by_month.setdefault(month, []).append(timestamp)
    recovered: list[dict[str, float | int | None]] = []
    current_month = datetime.now(timezone.utc).strftime("%Y%m")
    for month, month_timestamps in sorted(missing_by_month.items()):
        # Gate does not publish a complete 10s archive for the still-open month,
        # and its public REST candlestick endpoint has no 10s interval.
        if month == current_month:
            continue
        wanted = set(month_timestamps)
        repair_start = month_timestamps[0]
        repair_end = month_timestamps[-1] + interval - 10
        try:
            source_rows = fetch_archive_candles(
                session, contract, "10s", repair_start, repair_end,
                sleep_seconds=sleep_seconds,
            )
            candidates = aggregate_10s_to_timeframe(source_rows, timeframe)
            accepted = [row for row in candidates if int(row["timestamp"]) in wanted]
        except Exception as repair_error:
            print(
                f"[10s-repair-warning] {contract} {timeframe} {month}: "
                f"10s archive recovery unavailable: {repair_error}",
                flush=True,
            )
            continue
        recovered.extend(accepted)
        print(
            f"[10s-repair] {contract} {timeframe} {month}: "
            f"{len(accepted)}/{len(wanted)} missing bars recovered "
            "from observed official 10s candles",
            flush=True,
        )
    return sorted(recovered, key=lambda row: int(row["timestamp"]))


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


def fetch_missing_native_rest_candles(
    session: requests.Session,
    contract: str,
    timeframe: str,
    missing_timestamps: list[int],
    *,
    sleep_seconds: float = 0.05,
    now_ts: int | None = None,
) -> list[dict[str, float | int | None]]:
    """Recover missing candle opens from public REST, including historical gaps outside the recent tail."""
    if not missing_timestamps:
        return []
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported native REST repair timeframe: {timeframe}")

    interval = TIMEFRAMES[timeframe]
    effective_now = int(time.time()) if now_ts is None else now_ts
    last_closed = last_closed_candle_start(effective_now, interval, now_ts=effective_now)
    eligible_timestamps = sorted({
        timestamp for timestamp in missing_timestamps
        if timestamp <= last_closed and timestamp % interval == 0
    })
    skipped_count = len(set(missing_timestamps)) - len(eligible_timestamps)
    if skipped_count:
        print(
            f"[rest-repair-skip] {contract} {timeframe}: skipped {skipped_count} "
            f"timestamps that are not aligned closed candles (latest closed={last_closed})",
            flush=True,
        )
    if not eligible_timestamps:
        return []

    missing_by_month: dict[str, list[int]] = {}
    for timestamp in eligible_timestamps:
        month = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y%m")
        missing_by_month.setdefault(month, []).append(timestamp)

    recovered: list[dict[str, float | int | None]] = []
    for month, month_timestamps in sorted(missing_by_month.items()):
        wanted = set(month_timestamps)
        try:
            candidates = fetch_recent_rest_candles(
                session, contract, timeframe, month_timestamps[0], month_timestamps[-1],
                sleep_seconds=sleep_seconds,
            )
            accepted = [
                row for row in candidates if int(row["timestamp"]) in wanted
            ]
            recovered.extend(accepted)
            print(
                f"[rest-repair] {contract} {timeframe} {month}: "
                f"{len(accepted)}/{len(wanted)} missing bars recovered "
                "from native public REST candles",
                flush=True,
            )
        except Exception as repair_error:
            # REST is an additional real source, not a reason to hide unresolved gaps.
            print(
                f"[rest-repair-warning] {contract} {timeframe} {month}: "
                f"native REST repair unavailable: {repair_error}",
                flush=True,
            )
    return recovered



MIN_TRADE_VALIDATION_OVERLAP = 20


def parse_futures_trade_row(values: list[str]) -> tuple[float, int, float, float]:
    """Parse Gate futures trades CSV: timestamp, dealid, price, signed size."""
    if len(values) != 4:
        raise DataError(f"Malformed Gate futures trade row: expected 4 fields, got {len(values)}")
    try:
        timestamp, deal_id, price, size = float(values[0]), int(values[1]), float(values[2]), float(values[3])
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataError(f"Malformed Gate futures trade row: {values!r}") from exc
    if not all(math.isfinite(value) for value in (timestamp, price, size)):
        raise DataError(f"Non-finite value in Gate futures trade row: {values!r}")
    if timestamp < 0 or price <= 0 or size == 0:
        raise DataError(f"Out-of-range value in Gate futures trade row: {values!r}")
    return timestamp, deal_id, price, size


def fetch_monthly_futures_trades(
    session: requests.Session,
    contract: str,
    month: str,
    *,
    timeout_seconds: float = 90.0,
) -> list[tuple[float, int, float, float]] | None:
    """Fetch one official Gate futures monthly trade archive; None means archive unavailable."""
    if len(month) != 6 or not month.isdigit():
        raise ValueError(f"Invalid UTC month: {month!r}")
    url = f"{ARCHIVE_BASE_URL}/trades/{month}/{contract}-{month}.csv.gz"
    response = None
    for attempt in range(5):
        try:
            response = session.get(
                url, timeout=timeout_seconds, headers={"User-Agent": USER_AGENT}
            )
            if response.status_code == 404:
                return None
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt == 4:
                    raise DataError(
                        f"Gate trade archive HTTP {response.status_code} for {contract} {month}"
                    )
                time.sleep(min(2 ** attempt, 12))
                continue
            if response.status_code >= 400:
                body = str(getattr(response, "text", "") or "")[:500]
                raise DataError(
                    f"Gate trade archive HTTP {response.status_code} for {contract} {month}: "
                    f"{body or '<empty>'}"
                )
            break
        except requests.RequestException as exc:
            if attempt == 4:
                raise DataError(
                    f"Gate trade archive request failed for {contract} {month}: {exc}"
                ) from exc
            time.sleep(min(2 ** attempt, 12))
    if response is None or response.status_code != 200:
        raise DataError(f"Gate trade archive returned no usable response for {contract} {month}")

    trades: list[tuple[float, int, float, float]] = []
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(response.content), mode="rb") as zipped:
            text_stream = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            for line_number, values in enumerate(csv.reader(text_stream), start=1):
                if not values:
                    continue
                try:
                    trades.append(parse_futures_trade_row(values))
                except DataError as exc:
                    raise DataError(
                        f"Invalid Gate futures trade row {line_number} for {contract} {month}: {exc}"
                    ) from exc
    except (OSError, EOFError, gzip.BadGzipFile, UnicodeError, csv.Error) as exc:
        raise DataError(
            f"Could not decode Gate futures trades archive for {contract} {month}: {exc}"
        ) from exc
    trades.sort(key=lambda item: (item[0], item[1]))
    return trades


def aggregate_futures_trades_to_15m(
    trades: list[tuple[float, int, float, float]],
) -> list[dict[str, float | int | None]]:
    """Build 15m OHLCV from observed trades only; signed contract size becomes absolute volume."""
    groups: dict[int, list[tuple[float, int, float, float]]] = {}
    for trade in trades:
        timestamp, _deal_id, price, size = trade
        if not all(math.isfinite(value) for value in (timestamp, price, size)):
            raise DataError("Non-finite trade cannot be aggregated")
        if timestamp < 0 or price <= 0 or size == 0:
            raise DataError("Invalid trade cannot be aggregated")
        bucket = math.floor(timestamp / 900) * 900
        groups.setdefault(bucket, []).append(trade)

    candles: list[dict[str, float | int | None]] = []
    for bucket, group in sorted(groups.items()):
        group.sort(key=lambda item: (item[0], item[1]))
        prices = [item[2] for item in group]
        candles.append({
            "timestamp": bucket,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            # Gate's trade size is signed (long/short); volume is traded size, not net direction.
            "volume": sum(abs(item[3]) for item in group),
            "quote_volume": None,
        })
    return candles


def validate_trade_reconstruction(
    reconstructed: list[dict[str, float | int | None]],
    official_rows: list[dict[str, float | int | None]],
    *,
    minimum_overlap: int = MIN_TRADE_VALIDATION_OVERLAP,
) -> dict[str, Any]:
    """Require adequate overlap and matching OHLCV before accepting a month's trade reconstruction."""
    official_by_ts: dict[int, dict[str, float | int | None]] = {}
    duplicate_official_timestamps = 0
    for row in official_rows:
        timestamp = int(row["timestamp"])
        if timestamp in official_by_ts:
            duplicate_official_timestamps += 1
        official_by_ts[timestamp] = row
    if duplicate_official_timestamps:
        return {
            "valid": False, "overlap_bars": 0,
            "reason": f"duplicate official timestamps: {duplicate_official_timestamps}",
            "mismatches": [],
        }

    mismatches: list[dict[str, Any]] = []
    overlap = 0
    fields = ("open", "high", "low", "close", "volume")
    for candidate in reconstructed:
        timestamp = int(candidate["timestamp"])
        official = official_by_ts.get(timestamp)
        if official is None:
            continue
        overlap += 1
        different = {}
        for field in fields:
            left, right = float(candidate[field]), float(official[field])
            if not math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-6):
                different[field] = {"trades": left, "official": right}
        if different and len(mismatches) < 5:
            mismatches.append({"timestamp": timestamp, "fields": different})

    if overlap < minimum_overlap:
        return {
            "valid": False, "overlap_bars": overlap,
            "reason": f"insufficient overlap (need {minimum_overlap})",
            "mismatches": mismatches,
        }
    return {
        "valid": not mismatches, "overlap_bars": overlap,
        "reason": "OHLCV matches" if not mismatches else "OHLCV mismatch",
        "mismatches": mismatches,
    }


def audit_rows(
    rows: list[dict[str, float | int | None]], timeframe: str, *,
    expected_start: int | None = None, expected_end: int | None = None,
    verified_source_empty_timestamps: set[int] | None = None,
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
    verified_source_empty_set = verified_source_empty_timestamps or set()
    if has_range:
        expected_bars = ((expected_end - expected_start) // interval) + 1
        in_range = [ts for ts in ordered if expected_start <= ts <= expected_end]
        leading_missing = max(0, (in_range[0] - expected_start) // interval) if in_range else expected_bars
        trailing_missing = max(0, (expected_end - in_range[-1]) // interval) if in_range else expected_bars
        observed_expected = len(in_range)
        missing_timestamps = [
            timestamp for timestamp in range(expected_start, expected_end + 1, interval)
            if timestamp not in seen
        ]
        verified_empty = sorted(
            timestamp for timestamp in missing_timestamps
            if timestamp in verified_source_empty_set
        )
        unresolved_timestamps = [
            timestamp for timestamp in missing_timestamps
            if timestamp not in verified_source_empty_set
        ]
        missing_expected = len(missing_timestamps)
        unresolved_missing = len(unresolved_timestamps)
        coverage_ratio = observed_expected / expected_bars
        source_coverage_ratio = (observed_expected + len(verified_empty)) / expected_bars
        effective_expected_bars = expected_bars - len(verified_empty)
        effective_coverage_ratio = (
            observed_expected / effective_expected_bars if effective_expected_bars else None
        )
        unresolved_gap_count = 0
        previous_unresolved: int | None = None
        for timestamp in unresolved_timestamps:
            if previous_unresolved is None or timestamp - previous_unresolved > interval:
                unresolved_gap_count += 1
            previous_unresolved = timestamp
    else:
        expected_bars = leading_missing = trailing_missing = observed_expected = missing_expected = 0
        unresolved_missing = unresolved_gap_count = effective_expected_bars = 0
        verified_empty = []
        unresolved_timestamps = []
        coverage_ratio = source_coverage_ratio = effective_coverage_ratio = None

    out_of_range_timestamps = (
        sum(1 for ts in ordered if not expected_start <= ts <= expected_end)
        if has_range else 0
    )
    complete = bool(
        has_range and expected_bars > 0 and observed_expected == expected_bars
        and out_of_range_timestamps == 0
        and gap_count == 0 and not invalid and leading_missing == 0 and trailing_missing == 0
    )
    source_coverage_complete = bool(
        has_range and expected_bars > 0 and unresolved_missing == 0
        and out_of_range_timestamps == 0 and not invalid
    )
    return {
        "bars": len(rows), "unique_timestamps": len(ordered),
        "first_timestamp": ordered[0] if ordered else None,
        "last_timestamp": ordered[-1] if ordered else None,
        "expected_first_timestamp": expected_start if has_range else None,
        "expected_last_timestamp": expected_end if has_range else None,
        "expected_bars": expected_bars, "observed_expected_bars": observed_expected,
        "missing_expected_bars": missing_expected,
        "verified_source_empty_bars": len(verified_empty),
        "verified_source_empty_timestamps": verified_empty,
        "unresolved_missing_timestamps": unresolved_timestamps,
        "unresolved_missing_bars": unresolved_missing,
        "effective_expected_bars": effective_expected_bars,
        "coverage_ratio": coverage_ratio,
        "source_coverage_ratio": source_coverage_ratio,
        "effective_coverage_ratio": effective_coverage_ratio,
        "unresolved_gap_count": unresolved_gap_count,
        "leading_missing_bars": leading_missing,
        "trailing_missing_bars": trailing_missing,
        "out_of_range_timestamps": out_of_range_timestamps,
        "invalid_rows": invalid, "gap_count": gap_count,
        "internal_missing_bars": internal_missing_bars,
        "complete_contiguous_history": complete,
        "complete_source_coverage": source_coverage_complete,
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
        "schema_version": 4,
        "data_source": "Gate official monthly futures candle and trade archives, plus public REST candles only inside the recent 10,000-point window and public contracts metadata",
        "archive_first_documented_month": ARCHIVE_FIRST_MONTH,
        "archive_intervals_downloaded": ["15m", "10s", "1m", "5m", "1h", "trades (only months with unresolved 15m gaps)"],
        "recent_rest_policy": "The recent tail uses public REST; unresolved historical gaps are also checked against public REST using from/to ranges, pages of at most 900 points, and only closed aligned candles.",
        "coverage_policy": "Expected range begins at max(requested start, public contract create_time), rounded up to a candle boundary; only fully closed candles are expected. Missing 15m buckets may be reconstructed from official monthly futures trades only after at least 20 overlapping OHLCV bars match the official candle source. A successfully downloaded and validated trade archive may certify a missing bucket as zero-trade, but no candle is synthesized for it. Other unresolved gaps remain failures.",
        "endpoint": "Gate official monthly archives plus https://api.gateio.ws/api/v4/futures/usdt/candlesticks for recent candles and historical gap recovery",
        "strategy_path": STRATEGY_PATH,
        "locked_strategy_git_blob_sha1": LOCKED_STRATEGY_BLOB_SHA,
        "start_timestamp_requested": start_ts,
        "end_timestamp_requested": end_ts,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "order_execution": "NOT_PERFORMED_DATA_DOWNLOAD_ONLY",
        "quote_volume_available": False,
        "quote_volume_policy": "Gate historical candle archives provide contract-size volume but not quote-currency turnover; quote_volume is blank, never estimated.",
        "fifteen_minute_policy": "Historical 15m candles prefer the native official archive and otherwise aggregate complete sets of observed real 5m archive candles. Remaining 15m gaps may use official monthly futures trades only after at least 20 overlapping OHLCV bars match the official candle source. Buckets with no trades remain absent; a validated complete monthly trades archive can certify such buckets as zero-trade intervals. No synthetic candles are created.",
        "gap_repair_policy": "Repair missing candle opens from complete observed real 1m/10s candle archives and recent native public REST. For unresolved 15m gaps, download only the affected official monthly futures trade archives, aggregate trades by UTC 900-second bucket, validate OHLCV against at least 20 overlapping official candles, and accept only months that match. Gate trade size is signed by direction, so reconstructed total volume sums absolute sizes. Unavailable or mismatching archives do not repair gaps; unverified gaps fail closed.",
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
                        archive_rows, archive_source_label = fetch_15m_archive_candles(
                            session, contract, requested_first, archive_last,
                        )
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
                            "from complete observed 1m candle sets",
                            flush=True,
                        )
                    except Exception as repair_error:
                        print(
                            f"[repair-warning] {contract} {timeframe} {month}: "
                            f"1m archive repair unavailable: {repair_error}",
                            flush=True,
                        )

                archive_repaired_count = len(repaired_rows)
                already_observed = {
                    int(row["timestamp"]) for row in rows + repaired_rows
                }
                remaining_missing = [
                    timestamp for timestamp in missing_before_repair
                    if timestamp not in already_observed
                ]
                repair_now = int(time.time())
                rest_start = recent_rest_window_start(interval, now_ts=repair_now)
                rest_end = last_closed_candle_start(repair_now, interval, now_ts=repair_now)
                historical_missing = [
                    timestamp for timestamp in remaining_missing
                    if not rest_start <= timestamp <= rest_end
                ]
                if historical_missing:
                    ten_second_rows = fetch_missing_10s_archive_candles(
                        session, contract, timeframe, historical_missing,
                    )
                    if ten_second_rows:
                        repaired_rows.extend(ten_second_rows)
                        source_parts.append("Gate official 10s candle archive recovery")

                already_observed = {
                    int(row["timestamp"]) for row in rows + repaired_rows
                }
                remaining_missing = [
                    timestamp for timestamp in missing_before_repair
                    if timestamp not in already_observed
                ]
                if remaining_missing:
                    native_rest_rows = fetch_missing_native_rest_candles(
                        session, contract, timeframe, remaining_missing,
                        now_ts=repair_now,
                    )
                    if native_rest_rows:
                        repaired_rows.extend(native_rest_rows)
                        source_parts.append("Gate native public REST recovery for recent missing intervals")

                # Recompute after all earlier repair sources so trades never duplicate
                # a timestamp already recovered from 1m/10s/REST data.
                already_observed = {
                    int(row["timestamp"]) for row in rows + repaired_rows
                }
                remaining_missing = [
                    timestamp for timestamp in missing_before_repair
                    if timestamp not in already_observed
                ]
                verified_trade_empty_timestamps: set[int] = set()
                if timeframe == "15m" and remaining_missing:
                    missing_trade_months: dict[str, list[int]] = {}
                    for timestamp in remaining_missing:
                        month = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y%m")
                        missing_trade_months.setdefault(month, []).append(timestamp)
                    for month, missing_in_month in sorted(missing_trade_months.items()):
                        try:
                            monthly_trades = fetch_monthly_futures_trades(session, contract, month)
                            if monthly_trades is None:
                                print(
                                    f"[trade-repair-skip] {contract} {month}: official trade archive unavailable (HTTP 404)",
                                    flush=True,
                                )
                                continue
                            trade_candles = aggregate_futures_trades_to_15m(monthly_trades)
                            month_start = int(datetime.strptime(month, "%Y%m").replace(tzinfo=timezone.utc).timestamp())
                            next_month_dt = (datetime.fromtimestamp(month_start, timezone.utc).replace(day=28) + timedelta(days=4)).replace(day=1)
                            next_month = int(next_month_dt.timestamp())
                            month_official_rows = [
                                row for row in rows
                                if month_start <= int(row["timestamp"]) < next_month
                            ]
                            validation = validate_trade_reconstruction(trade_candles, month_official_rows)
                            if not validation["valid"]:
                                print(
                                    f"[trade-repair-reject] {contract} {month}: "
                                    f"overlap={validation['overlap_bars']} reason={validation['reason']} "
                                    f"details={validation['mismatches']}",
                                    flush=True,
                                )
                                continue
                            wanted = set(missing_in_month)
                            trade_timestamps = {int(row["timestamp"]) for row in trade_candles}
                            accepted = [
                                row for row in trade_candles
                                if int(row["timestamp"]) in wanted
                            ]
                            repaired_rows.extend(accepted)
                            verified_empty = wanted - trade_timestamps
                            verified_trade_empty_timestamps.update(verified_empty)
                            print(
                                f"[trade-repair-ok] {contract} {month}: "
                                f"{len(accepted)}/{len(wanted)} missing candles reconstructed; "
                                f"{len(verified_empty)} verified zero-trade buckets; "
                                f"validated_overlap={validation['overlap_bars']}",
                                flush=True,
                            )
                            source_parts.append(
                                "Gate official monthly futures trades (15m OHLCV overlap-validated)"
                            )
                        except Exception as trade_error:
                            print(
                                f"[trade-repair-warning] {contract} {month}: "
                                f"monthly trades recovery unavailable: {trade_error}",
                                flush=True,
                            )

                if repaired_rows:
                    rows = sorted(rows + repaired_rows, key=lambda row: int(row["timestamp"]))
                    if archive_repaired_count:
                        source_parts.append(
                            "Gate 1m archive recovery for complete source buckets"
                        )
                source_label = " + ".join(source_parts) or "no source rows"
                audit = audit_rows(
                    rows, timeframe, expected_start=requested_first, expected_end=requested_last,
                    verified_source_empty_timestamps=verified_trade_empty_timestamps,
                )
                if audit["invalid_rows"]:
                    raise DataError(f"Invalid candle rows: {audit['invalid_rows']}")
                if not audit["complete_source_coverage"]:
                    failures.append(
                        f"{contract} {timeframe}: unresolved source coverage "
                        f"({audit['unresolved_missing_bars']} unverified expected bars; "
                        f"{audit['unresolved_gap_count']} unresolved gap spans; "
                        f"timestamps={audit['unresolved_missing_timestamps']})"
                    )
                filename = f"{contract}_{timeframe}.csv.gz"
                sha256 = write_gzip_csv(output_dir / filename, rows)
                manifest["symbols"][contract][timeframe] = {
                    **audit, "file": filename, "sha256": sha256, "interval_seconds": interval,
                    "contract_create_time": create_time, "quote_volume_available": False,
                    "volume_source": "Gate contract-size volume (archive size / public REST v)",
                    "source": source_label,
                    "coverage_status": (
                        "complete_contiguous"
                        if audit["complete_contiguous_history"]
                        else "complete_source_coverage"
                        if audit["complete_source_coverage"]
                        else "partial_unverified_gaps"
                    ),
                }
                print(
                    f"[ok] {contract} {timeframe}: {audit['bars']} bars; "
                    f"expected={audit['expected_bars']}; missing={audit['missing_expected_bars']}; "
                    f"source_empty={audit['verified_source_empty_bars']}; "
                    f"unresolved={audit['unresolved_missing_bars']}; "
                    f"contiguous={audit['complete_contiguous_history']}; sha256={sha256}", flush=True,
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
    series_entries = [
        series for symbol_data in manifest["symbols"].values()
        for key, series in symbol_data.items()
        if key in TIMEFRAMES and isinstance(series, dict) and "expected_bars" in series
        and series.get("expected_bars", 0) > 0
    ]
    manifest["failures"] = failures
    manifest["source_coverage_complete"] = not failures
    manifest["complete_contiguous_history"] = bool(series_entries) and all(
        series.get("complete_contiguous_history") is True for series in series_entries
    )
    manifest["backtest_ready"] = manifest["complete_contiguous_history"] and not failures
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