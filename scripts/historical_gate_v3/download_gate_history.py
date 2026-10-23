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


def fetch_missing_5m_archive_candles(
    session: requests.Session,
    contract: str,
    timeframe: str,
    missing_timestamps: list[int],
    *,
    sleep_seconds: float = 0.05,
) -> list[dict[str, float | int | None]]:
    """Recover 15m gaps only from three contiguous observed official Gate 5m candles."""
    if timeframe != "15m":
        return []
    if not missing_timestamps:
        return []

    missing_by_month: dict[str, list[int]] = {}
    for timestamp in sorted(set(missing_timestamps)):
        month = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y%m")
        missing_by_month.setdefault(month, []).append(timestamp)

    recovered: list[dict[str, float | int | None]] = []
    current_month = datetime.now(timezone.utc).strftime("%Y%m")
    for month, month_timestamps in sorted(missing_by_month.items()):
        if month == current_month:
            continue
        wanted = set(month_timestamps)
        try:
            source_rows = fetch_archive_candles(
                session, contract, "5m", month_timestamps[0],
                month_timestamps[-1] + 600, sleep_seconds=sleep_seconds,
            )
            candidates = aggregate_5m_to_15m(source_rows)
            accepted = [
                row for row in candidates
                if int(row["timestamp"]) in wanted
            ]
        except Exception as repair_error:
            print(
                f"[5m-repair-warning] {contract} {timeframe} {month}: "
                f"5m archive recovery unavailable: {repair_error}",
                flush=True,
            )
            continue
        recovered.extend(accepted)
        print(
            f"[5m-repair] {contract} {timeframe} {month}: "
            f"{len(accepted)}/{len(wanted)} missing bars recovered "
            "from complete observed official 5m candle sets",
            flush=True,
        )
    return sorted(recovered, key=lambda row: int(row["timestamp"]))


def fetch_missing_5m_rest_candles(
    session: requests.Session,
    contract: str,
    timeframe: str,
    missing_timestamps: list[int],
    *,
    sleep_seconds: float = 0.05,
    now_ts: int | None = None,
) -> list[dict[str, float | int | None]]:
    """Recover recent 15m gaps from three observed official 5m REST candles."""
    if timeframe != "15m" or not missing_timestamps:
        return []

    effective_now = int(time.time()) if now_ts is None else now_ts
    source_interval = 300
    recent_first = recent_rest_window_start(source_interval, now_ts=effective_now)
    recent_last = last_closed_candle_start(
        effective_now, source_interval, now_ts=effective_now,
    )
    eligible = sorted({
        timestamp for timestamp in missing_timestamps
        if timestamp % 900 == 0
        and recent_first <= timestamp
        and timestamp + 600 <= recent_last
    })
    skipped = len(set(missing_timestamps)) - len(eligible)
    if skipped:
        print(
            f"[5m-rest-repair-skip] {contract} {timeframe}: skipped {skipped} "
            "timestamps outside the complete recent 5m REST window",
            flush=True,
        )
    if not eligible:
        return []

    recovered: list[dict[str, float | int | None]] = []
    by_month: dict[str, list[int]] = {}
    for timestamp in eligible:
        month = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y%m")
        by_month.setdefault(month, []).append(timestamp)

    for month, month_timestamps in sorted(by_month.items()):
        wanted = set(month_timestamps)
        try:
            source_rows = fetch_recent_rest_candles(
                session, contract, "5m", month_timestamps[0],
                month_timestamps[-1] + 600,
                sleep_seconds=sleep_seconds,
            )
            for source_row in source_rows:
                invalid_reason = _validate_row(source_row, source_interval)
                if invalid_reason:
                    raise DataError(
                        f"Invalid official 5m REST candle at "
                        f"{source_row.get('timestamp')}: {invalid_reason}"
                    )
            candidates = aggregate_5m_to_15m(source_rows)
            accepted = [
                row for row in candidates
                if int(row["timestamp"]) in wanted
            ]
        except Exception as repair_error:
            print(
                f"[5m-rest-repair-warning] {contract} {timeframe} {month}: "
                f"official 5m REST recovery unavailable: {repair_error}",
                flush=True,
            )
            continue
        recovered.extend(accepted)
        print(
            f"[5m-rest-repair] {contract} {timeframe} {month}: "
            f"{len(accepted)}/{len(wanted)} missing bars recovered "
            "from complete observed official 5m REST groups",
            flush=True,
        )
    return sorted(recovered, key=lambda row: int(row["timestamp"]))


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
    """Recover missing closed candles only inside Gate's actual recent REST window.

    Gate's futures candlesticks endpoint rejects timestamps older than its latest
    10,000-point window, even when from/to are supplied. Historical gaps outside
    that window must remain unresolved unless a reliable archive source reconstructs
    them; do not repeatedly issue known-invalid calls.
    """
    if not missing_timestamps:
        return []
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported native REST repair timeframe: {timeframe}")

    interval = TIMEFRAMES[timeframe]
    effective_now = int(time.time()) if now_ts is None else now_ts
    last_closed = last_closed_candle_start(effective_now, interval, now_ts=effective_now)
    rest_window_start = recent_rest_window_start(interval, now_ts=effective_now)
    eligible_timestamps = sorted({
        timestamp for timestamp in missing_timestamps
        if timestamp % interval == 0
        and rest_window_start <= timestamp <= last_closed
    })
    skipped_count = len(set(missing_timestamps)) - len(eligible_timestamps)
    if skipped_count:
        print(
            f"[rest-repair-skip] {contract} {timeframe}: skipped {skipped_count} "
            f"timestamps outside Gate's recent 10,000-point REST window or not closed "
            f"(window_start={rest_window_start}, latest_closed={last_closed})",
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
                "from official historical/native REST candles",
                flush=True,
            )
        except Exception as repair_error:
            print(
                f"[rest-repair-warning] {contract} {timeframe} {month}: "
                f"native REST repair unavailable: {repair_error}",
                flush=True,
            )
    return sorted(recovered, key=lambda row: int(row["timestamp"]))


MIN_TRADE_VALIDATION_OVERLAP = 100


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

    month_start_dt = datetime.strptime(month, "%Y%m").replace(tzinfo=timezone.utc)
    next_month_dt = (month_start_dt.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_start_ts = month_start_dt.timestamp()
    next_month_ts = next_month_dt.timestamp()
    trades: list[tuple[float, int, float, float]] = []
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(response.content), mode="rb") as zipped:
            text_stream = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            for line_number, values in enumerate(csv.reader(text_stream), start=1):
                if not values:
                    continue
                try:
                    trade = parse_futures_trade_row(values)
                    if not month_start_ts <= trade[0] < next_month_ts:
                        raise DataError(
                            f"trade timestamp {trade[0]} falls outside requested month {month}"
                        )
                    trades.append(trade)
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


TRADE_OUTLIER_LOOKBACK = 5
TRADE_OUTLIER_MAX_DEVIATION = 0.05


def filter_futures_trade_outliers(
    trades: list[tuple[float, int, float, float]],
    *,
    lookback: int = TRADE_OUTLIER_LOOKBACK,
    max_deviation: float = TRADE_OUTLIER_MAX_DEVIATION,
) -> tuple[list[tuple[float, int, float, float]], list[tuple[float, int, float, float]]]:
    """Filter prices >5% from the mean of the preceding five raw trade prices.

    Every raw price enters the rolling history, including rejected candidates, so
    the baseline can adapt to a genuine price-regime change. This is a heuristic:
    it cannot identify liquidation/internal trades, and it may reject legitimate
    fast-market trades. Callers must still validate the reconstructed candles.
    """
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    if not math.isfinite(max_deviation) or not 0 < max_deviation < 1:
        raise ValueError("max_deviation must be finite and between 0 and 1")

    ordered = sorted(trades, key=lambda item: (item[0], item[1]))
    history: list[float] = []
    accepted: list[tuple[float, int, float, float]] = []
    rejected: list[tuple[float, int, float, float]] = []
    for trade in ordered:
        timestamp, _deal_id, price, size = trade
        if not all(math.isfinite(value) for value in (timestamp, price, size)):
            raise DataError("Non-finite trade cannot be filtered")
        if timestamp < 0 or price <= 0 or size == 0:
            raise DataError("Invalid trade cannot be filtered")
        if len(history) >= lookback:
            mean_price = sum(history[-lookback:]) / lookback
            if abs(price - mean_price) / mean_price > max_deviation:
                rejected.append(trade)
            else:
                accepted.append(trade)
        else:
            accepted.append(trade)
        history.append(price)
    return accepted, rejected


def aggregate_futures_trades_to_15m(
    trades: list[tuple[float, int, float, float]],
    *,
    apply_outlier_filter: bool = True,
) -> list[dict[str, float | int | None]]:
    """Build 15m OHLCV from observed trades; filter price outliers before aggregation."""
    if apply_outlier_filter:
        trades, _rejected = filter_futures_trade_outliers(trades)
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


def classify_trade_reconstruction_buckets(
    wanted_timestamps: set[int],
    reconstructed_candles: list[dict[str, float | int | None]],
    raw_trades: list[tuple[float, int, float, float]],
) -> tuple[set[int], set[int]]:
    """Classify missing buckets without treating filtered raw trades as zero-trade proof.

    Returns (verified_zero_trade_timestamps, raw_trade_but_unreconstructed_timestamps).
    A bucket is verified empty only when no raw archive trade and no reconstructed
    candle exists for it. Raw trades filtered out by the outlier heuristic are evidence
    that the bucket is not empty; it must remain unresolved unless another source repairs it.
    """
    reconstructed_timestamps = {int(row["timestamp"]) for row in reconstructed_candles}
    raw_trade_timestamps = {
        math.floor(trade[0] / 900) * 900 for trade in raw_trades
    }
    verified_empty = wanted_timestamps - reconstructed_timestamps - raw_trade_timestamps
    raw_but_unreconstructed = (
        wanted_timestamps & raw_trade_timestamps
    ) - reconstructed_timestamps
    return verified_empty, raw_but_unreconstructed


def build_trade_validation_windows(
    wanted_timestamps: set[int],
    month_start: int,
    next_month: int,
    *,
    window_seconds: int = 6 * 60 * 60,
    stride_seconds: int = 60 * 60,
) -> dict[int, set[int]]:
    """Map wanted 15m buckets to overlapping, fully in-month UTC validation windows.

    Windows remain six hours and retain the existing 18-of-24 official-candle
    overlap requirement. Hourly staggering avoids making repair eligibility depend
    solely on one fixed six-hour partition boundary.
    """
    if month_start < 0 or next_month <= month_start:
        raise ValueError("month bounds must be non-negative and increasing")
    if window_seconds <= 0 or stride_seconds <= 0 or window_seconds % stride_seconds:
        raise ValueError("window_seconds must be positive and divisible by stride_seconds")

    windows: dict[int, set[int]] = {}
    for timestamp in sorted(wanted_timestamps):
        if not month_start <= timestamp < next_month:
            raise ValueError("wanted timestamp must fall inside the requested month")
        latest_start = (timestamp // stride_seconds) * stride_seconds
        earliest_start = latest_start - window_seconds + stride_seconds
        for window_start in range(earliest_start, latest_start + 1, stride_seconds):
            if window_start < month_start or window_start + window_seconds > next_month:
                continue
            if window_start <= timestamp < window_start + window_seconds:
                windows.setdefault(window_start, set()).add(timestamp)
    return windows


def summarize_trade_bucket(
    trades: list[tuple[float, int, float, float]],
    bucket_timestamp: int,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """Return bounded raw-row diagnostics for one 15m bucket; never alter source trades."""
    bucket_trades = [
        trade for trade in trades
        if math.floor(trade[0] / 900) * 900 == bucket_timestamp
    ]
    if not bucket_trades:
        return {"timestamp": bucket_timestamp, "trade_count": 0, "rows": []}
    ordered = sorted(bucket_trades, key=lambda item: (item[0], item[1]))
    by_price = sorted(ordered, key=lambda item: (item[2], item[0], item[1]))
    selected: dict[tuple[float, int, float, float], None] = {}
    for trade in (ordered[:limit] + ordered[-limit:] + by_price[:limit] + by_price[-limit:]):
        selected[trade] = None
    return {
        "timestamp": bucket_timestamp,
        "trade_count": len(ordered),
        "min_price": min(item[2] for item in ordered),
        "max_price": max(item[2] for item in ordered),
        "total_absolute_size": sum(abs(item[3]) for item in ordered),
        "rows": [
            {"timestamp": item[0], "dealid": item[1], "price": item[2], "signed_size": item[3]}
            for item in sorted(selected, key=lambda item: (item[0], item[1]))
        ],
    }


def validate_trade_reconstruction(
    reconstructed: list[dict[str, float | int | None]],
    official_rows: list[dict[str, float | int | None]],
    *,
    minimum_overlap: int = MIN_TRADE_VALIDATION_OVERLAP,
    open_close_tolerance: float = 0.0001,
    high_low_tolerance: float = 0.005,
) -> dict[str, Any]:
    """Validate trade-derived candles against official candles with explicit price tolerances.

    Open/close must be within 0.01%; high/low may differ by at most 0.5%.
    Volume is assessed separately because signed trade-size aggregation can differ
    from the exchange candle volume convention. Tolerated differences do not prove
    a liquidation/internal-trade cause; that remains a hypothesis unless independently
    confirmed by source metadata.
    """
    if not (math.isfinite(open_close_tolerance) and 0 <= open_close_tolerance < 1):
        raise ValueError("open_close_tolerance must be finite and in [0, 1)")
    if not (math.isfinite(high_low_tolerance) and 0 <= high_low_tolerance < 1):
        raise ValueError("high_low_tolerance must be finite and in [0, 1)")

    official_by_ts: dict[int, dict[str, float | int | None]] = {}
    duplicate_official_timestamps = 0
    for row in official_rows:
        timestamp = int(row["timestamp"])
        if timestamp in official_by_ts:
            duplicate_official_timestamps += 1
        official_by_ts[timestamp] = row
    if duplicate_official_timestamps:
        return {
            "valid": False, "overlap_bars": 0, "exact_match_bars": 0,
            "exact_match_ratio": 0.0, "mismatch_bars": 0,
            "price_mismatch_bars": 0, "price_tolerated_mismatch_bars": 0,
            "price_valid_bars": 0, "missing_official_positive_volume_bars": 0,
            "reason": f"duplicate official timestamps: {duplicate_official_timestamps}",
            "mismatches": [],
        }

    reconstructed_by_ts: dict[int, dict[str, float | int | None]] = {}
    for row in reconstructed:
        timestamp = int(row["timestamp"])
        if timestamp in reconstructed_by_ts:
            return {
                "valid": False, "overlap_bars": 0, "exact_match_bars": 0,
                "exact_match_ratio": 0.0, "mismatch_bars": 0,
                "price_mismatch_bars": 0, "price_tolerated_mismatch_bars": 0,
                "price_valid_bars": 0, "missing_official_positive_volume_bars": 0,
                "reason": f"duplicate reconstructed timestamps: {timestamp}",
                "mismatches": [],
            }
        reconstructed_by_ts[timestamp] = row

    mismatches: list[dict[str, Any]] = []
    out_of_tolerance_examples: list[dict[str, Any]] = []
    overlap = exact_matches = mismatch_bars = 0
    price_mismatch_bars = price_tolerated_mismatch_bars = price_valid_bars = 0
    missing_official_positive_volume = 0
    volume_only_mismatch_bars = 0
    price_fields = ("open", "high", "low", "close")
    fields = (*price_fields, "volume")
    for candidate in reconstructed:
        timestamp = int(candidate["timestamp"])
        official = official_by_ts.get(timestamp)
        if official is None:
            continue
        overlap += 1
        different: dict[str, Any] = {}
        out_of_tolerance: dict[str, Any] = {}
        price_different = False
        for field in fields:
            left, right = float(candidate[field]), float(official[field])
            if not math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-6):
                different[field] = {"trades": left, "official": right}
                if field in price_fields:
                    price_different = True
                    tolerance = (
                        open_close_tolerance if field in ("open", "close")
                        else high_low_tolerance
                    )
                    relative_difference = abs(left - right) / max(abs(right), 1e-12)
                    if relative_difference > tolerance:
                        out_of_tolerance[field] = {
                            "trades": left,
                            "official": right,
                            "relative_difference": relative_difference,
                            "allowed_relative_difference": tolerance,
                        }
        if different:
            mismatch_bars += 1
            if "volume" in different and not price_different:
                volume_only_mismatch_bars += 1
            if price_different and out_of_tolerance:
                price_mismatch_bars += 1
            elif price_different:
                price_tolerated_mismatch_bars += 1
            mismatch_detail = {
                "timestamp": timestamp,
                "fields": different,
                "price_fields_outside_tolerance": out_of_tolerance,
                "interpretation": (
                    "Possible source/trade-set difference (including internal or liquidation trades); "
                    "cause is not confirmed by this comparison alone."
                    if price_different and not out_of_tolerance else None
                ),
            }
            if out_of_tolerance and len(out_of_tolerance_examples) < 10:
                out_of_tolerance_examples.append(mismatch_detail)
            if len(mismatches) < 5:
                mismatches.append(mismatch_detail)
        else:
            exact_matches += 1
        if not out_of_tolerance:
            price_valid_bars += 1

    # Never accept a trade archive that omits an observed official positive-volume candle.
    for timestamp, official in official_by_ts.items():
        if timestamp in reconstructed_by_ts or float(official["volume"]) <= 0:
            continue
        missing_official_positive_volume += 1
        if len(mismatches) < 5:
            mismatches.append({
                "timestamp": timestamp,
                "fields": {
                    "missing_trade_candle": {
                        "official_volume": float(official["volume"])
                    }
                },
            })

    exact_match_ratio = exact_matches / overlap if overlap else 0.0
    price_match_ratio = price_valid_bars / overlap if overlap else 0.0
    if overlap < minimum_overlap:
        reason = f"insufficient overlap (need {minimum_overlap})"
    elif price_valid_bars < minimum_overlap:
        reason = (
            f"insufficient candles within OHLC tolerances "
            f"({price_valid_bars}; need {minimum_overlap})"
        )
    elif price_mismatch_bars:
        reason = (
            f"{price_mismatch_bars} OHLC price mismatch bars exceed tolerance "
            f"(open/close <= {open_close_tolerance:.2%}; high/low <= {high_low_tolerance:.2%})"
        )
    elif missing_official_positive_volume:
        reason = (
            f"trade archive omits {missing_official_positive_volume} official "
            "positive-volume candles"
        )
    else:
        reason = (
            f"OHLC prices within tolerance across {overlap} overlapping bars; "
            f"{price_tolerated_mismatch_bars} bars have tolerated price differences; "
            f"{exact_matches} exact OHLCV matches. Possible internal/liquidation-trade "
            "differences are not independently confirmed; volume discrepancies are reported separately."
        )

    valid = (
        overlap >= minimum_overlap
        and price_valid_bars >= minimum_overlap
        and price_mismatch_bars == 0
        and missing_official_positive_volume == 0
    )
    return {
        "valid": valid,
        "overlap_bars": overlap,
        "exact_match_bars": exact_matches,
        "exact_match_ratio": exact_match_ratio,
        "price_match_ratio": price_match_ratio,
        "price_valid_bars": price_valid_bars,
        "mismatch_bars": mismatch_bars,
        "price_mismatch_bars": price_mismatch_bars,
        "price_tolerated_mismatch_bars": price_tolerated_mismatch_bars,
        "volume_only_mismatch_bars": volume_only_mismatch_bars,
        "missing_official_positive_volume_bars": missing_official_positive_volume,
        "open_close_tolerance": open_close_tolerance,
        "high_low_tolerance": high_low_tolerance,
        "liquidation_cause_confirmed": False,
        "reason": reason,
        "mismatches": mismatches,
        "out_of_tolerance_examples": out_of_tolerance_examples,
    }


def summarize_missing_timestamps(
    timestamps: list[int], interval: int,
) -> dict[str, dict[str, Any]]:
    """Group unresolved candle opens by UTC month and exact contiguous ranges."""
    if interval <= 0:
        raise ValueError("interval must be positive")
    by_month: dict[str, list[int]] = {}
    for timestamp in sorted(set(timestamps)):
        month = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")
        by_month.setdefault(month, []).append(timestamp)

    summary: dict[str, dict[str, Any]] = {}
    for month, month_timestamps in sorted(by_month.items()):
        ranges: list[dict[str, Any]] = []
        for timestamp in month_timestamps:
            if not ranges or timestamp != ranges[-1]["end_timestamp"] + interval:
                ranges.append({
                    "start_timestamp": timestamp,
                    "end_timestamp": timestamp,
                    "start_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                    "end_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                    "bars": 1,
                })
            else:
                current = ranges[-1]
                current["end_timestamp"] = timestamp
                current["end_utc"] = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
                current["bars"] += 1
        summary[month] = {"missing_bars": len(month_timestamps), "ranges": ranges}
    return summary


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
        "unresolved_missing_by_month": summarize_missing_timestamps(unresolved_timestamps, interval),
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
        "recent_rest_policy": "Public REST historical from/to queries are paged at no more than 900 points per request; recent REST is also used for the current archive tail. Historical gaps are retried through the official REST endpoint before remaining unresolved.",
        "coverage_policy": "Expected range begins at max(requested start, public contract create_time), rounded up to a candle boundary; only fully closed candles are expected. Missing 15m buckets may be reconstructed from official monthly futures trades only within UTC six-hour windows that have at least 18 of 24 expected 15m candles overlapping (75%), all overlapping OHLC prices within tolerance (open/close relative difference <= 0.01%; high/low <= 0.5%), and no official positive-volume candle absent from the trade-derived candles. Volume differences are measured and reported separately; a liquidation/internal-trade cause is not assumed without independent evidence. A successfully downloaded and validated trade archive may certify a missing bucket as zero-trade, but no candle is synthesized for it. Other unresolved gaps remain failures.",
        "endpoint": "Gate official monthly futures candle/trade archives plus the public futures candlestick REST endpoint with historical from/to paging",
        "strategy_path": STRATEGY_PATH,
        "locked_strategy_git_blob_sha1": LOCKED_STRATEGY_BLOB_SHA,
        "start_timestamp_requested": start_ts,
        "end_timestamp_requested": end_ts,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "order_execution": "NOT_PERFORMED_DATA_DOWNLOAD_ONLY",
        "quote_volume_available": False,
        "quote_volume_policy": "Gate historical candle archives provide contract-size volume but not quote-currency turnover; quote_volume is blank, never estimated.",
        "fifteen_minute_policy": "Historical 15m candles prefer the native official archive and otherwise aggregate complete sets of observed real 5m archive candles. Remaining 15m gaps may use official monthly futures trades only within UTC six-hour windows with at least 18 of 24 expected 15m candles overlapping (75%) and all overlapping OHLC prices within tolerance (open/close <= 0.01%; high/low <= 0.5%), no overlapping OHLC price exceeds its tolerance, and no official positive-volume candle is absent from the trade-derived candles. Volume differences are reported separately and do not alone invalidate price validation; liquidation/internal-trade explanations remain unconfirmed unless independently evidenced. Buckets with no trades remain absent; a validated complete monthly trades archive can certify such buckets as zero-trade intervals. No synthetic candles are created.",
        "gap_repair_policy": "Repair missing candle opens only from observed official sources: complete 5m archive groups, complete recent 5m REST groups inside the latest 10,000-point source window, complete 1m/10s archive groups, and official native REST candles. For unresolved 15m gaps, monthly futures trades are accepted only with within UTC six-hour windows with at least 18 of 24 expected 15m candles overlapping (75%) and all overlapping OHLC prices within the stated tolerances (open/close <= 0.01%; high/low <= 0.5%), no out-of-tolerance OHLC prices in the validation overlap, and zero missing official positive-volume candles. Gate trade size is signed by direction, so reconstructed total volume sums absolute sizes. Volume discrepancies are reported separately. Unavailable, malformed, incomplete, price-mismatched, or truncated sources do not repair gaps; unverified gaps fail closed.",
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
                verified_trade_empty_timestamps: set[int] = set()
                trade_archive_audit: dict[str, dict[str, Any]] = {}
                already_observed = {
                    int(row["timestamp"]) for row in rows + repaired_rows
                }
                remaining_missing = [
                    timestamp for timestamp in missing_before_repair
                    if timestamp not in already_observed
                    and timestamp not in verified_trade_empty_timestamps
                ]
                if timeframe == "15m" and remaining_missing:
                    missing_trade_months: dict[str, list[int]] = {}
                    for timestamp in remaining_missing:
                        month = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y%m")
                        missing_trade_months.setdefault(month, []).append(timestamp)
                    current_month = datetime.now(timezone.utc).strftime("%Y%m")
                    for month, missing_in_month in sorted(missing_trade_months.items()):
                        if month == current_month:
                            trade_archive_audit[month] = {
                                "status": "skipped_current_month_not_finalized",
                                "requested_missing_bars": len(missing_in_month),
                            }
                            print(
                                f"[trade-repair-skip] {contract} {month}: current month is not finalized; "
                                "monthly trades cannot prove complete coverage",
                                flush=True,
                            )
                            continue
                        try:
                            monthly_trades = fetch_monthly_futures_trades(session, contract, month)
                            if monthly_trades is None:
                                trade_archive_audit[month] = {
                                    "status": "unavailable_http_404",
                                    "requested_missing_bars": len(missing_in_month),
                                }
                                print(
                                    f"[trade-repair-skip] {contract} {month}: official trade archive unavailable (HTTP 404)",
                                    flush=True,
                                )
                                continue
                            filtered_trades, rejected_trades = filter_futures_trade_outliers(monthly_trades)
                            trade_archive_audit[month] = {
                                "status": "available",
                                "requested_missing_bars": len(missing_in_month),
                                "raw_trade_rows": len(monthly_trades),
                                "outlier_rejected_rows": len(rejected_trades),
                            }
                            if rejected_trades:
                                print(
                                    f"[trade-outlier-filter] {contract} {month}: "
                                    f"rejected={len(rejected_trades)}/{len(monthly_trades)} "
                                    f"threshold={TRADE_OUTLIER_MAX_DEVIATION:.2%} "
                                    f"lookback={TRADE_OUTLIER_LOOKBACK}",
                                    flush=True,
                                )
                            trade_candles = aggregate_futures_trades_to_15m(
                                filtered_trades, apply_outlier_filter=False,
                            )
                            trade_archive_audit[month]["trade_derived_candles"] = len(trade_candles)
                            month_start = int(datetime.strptime(month, "%Y%m").replace(tzinfo=timezone.utc).timestamp())
                            next_month_dt = (datetime.fromtimestamp(month_start, timezone.utc).replace(day=28) + timedelta(days=4)).replace(day=1)
                            next_month = int(next_month_dt.timestamp())
                            month_official_rows = [
                                row for row in rows
                                if month_start <= int(row["timestamp"]) < next_month
                            ]
                            # Validate in UTC-day partitions rather than rejecting an entire
                            # month because of one inconsistent candle. Only days with enough
                            # overlap and fully passing OHLC validation can repair gaps; a bad
                            # day remains unresolved and is eligible for other official sources.
                            wanted = set(missing_in_month)
                            # Validate in UTC six-hour windows instead of whole days.
                            # Each window expects 24 15m candles; require at least 18
                            # observed overlaps (75%) and reject only the failing window.
                            # This keeps the evidence threshold proportional while preventing
                            # one bad interval or sparse part of a day from discarding valid
                            # reconstructions from the other UTC windows.
                            validation_window_seconds = 6 * 60 * 60
                            minimum_window_overlap = 18
                            window_stride_seconds = 60 * 60
                            wanted_by_window = build_trade_validation_windows(
                                wanted, month_start, next_month,
                                window_seconds=validation_window_seconds,
                                stride_seconds=window_stride_seconds,
                            )
                            official_by_hour: dict[int, list[dict[str, float | int | None]]] = {}
                            trades_by_hour: dict[int, list[dict[str, float | int | None]]] = {}
                            for row in month_official_rows:
                                ts = int(row["timestamp"])
                                hour_start = (ts // 3600) * 3600
                                official_by_hour.setdefault(hour_start, []).append(row)
                            for row in trade_candles:
                                ts = int(row["timestamp"])
                                hour_start = (ts // 3600) * 3600
                                trades_by_hour.setdefault(hour_start, []).append(row)

                            accepted_trade_candles: dict[int, dict[str, float | int | None]] = {}
                            verified_empty_timestamps: set[int] = set()
                            raw_unreconstructed_timestamps: set[int] = set()
                            valid_windows = 0
                            rejected_windows = 0
                            for window_key, window_wanted in sorted(wanted_by_window.items()):
                                window_official = [
                                    row
                                    for hour_start in range(
                                        window_key, window_key + validation_window_seconds, 3600,
                                    )
                                    for row in official_by_hour.get(hour_start, [])
                                ]
                                window_trades = [
                                    row
                                    for hour_start in range(
                                        window_key, window_key + validation_window_seconds, 3600,
                                    )
                                    for row in trades_by_hour.get(hour_start, [])
                                ]
                                validation = validate_trade_reconstruction(
                                    window_trades,
                                    window_official,
                                    minimum_overlap=minimum_window_overlap,
                                )
                                window_label = datetime.fromtimestamp(
                                    window_key, timezone.utc
                                ).strftime("%Y-%m-%dT%H:00Z")
                                if not validation["valid"]:
                                    rejected_windows += 1
                                    print(
                                        f"[trade-repair-reject] {contract} {month} window={window_label}: "
                                        f"overlap={validation['overlap_bars']} reason={validation['reason']} "
                                        f"out_of_tolerance={validation.get('out_of_tolerance_examples', [])} "
                                        f"details={validation['mismatches']}",
                                        flush=True,
                                    )
                                    if contract == "ETC_USDT" and month == "202510":
                                        for example in validation.get("out_of_tolerance_examples", []):
                                            bucket_timestamp = int(example["timestamp"])
                                            print(
                                                f"[trade-raw-diagnostic] {contract} {month}: "
                                                f"{json.dumps(summarize_trade_bucket(monthly_trades, bucket_timestamp), sort_keys=True)}",
                                                flush=True,
                                            )
                                    continue

                                valid_windows += 1
                                for row in window_trades:
                                    timestamp = int(row["timestamp"])
                                    if timestamp in window_wanted:
                                        accepted_trade_candles.setdefault(timestamp, row)
                                verified_empty, raw_unreconstructed = classify_trade_reconstruction_buckets(
                                    window_wanted, window_trades, monthly_trades,
                                )
                                verified_trade_empty_timestamps.update(verified_empty)
                                verified_empty_timestamps.update(verified_empty)
                                raw_unreconstructed_timestamps.update(raw_unreconstructed)

                            repaired_rows.extend(
                                accepted_trade_candles[timestamp]
                                for timestamp in sorted(accepted_trade_candles)
                            )
                            accepted_total = len(accepted_trade_candles)
                            verified_empty_total = len(verified_empty_timestamps)
                            raw_unreconstructed_total = len(raw_unreconstructed_timestamps)
                            trade_archive_audit[month].update({
                                "valid_windows": valid_windows,
                                "rejected_windows": rejected_windows,
                                "reconstructed_bars": accepted_total,
                                "verified_zero_trade_bars": verified_empty_total,
                                "raw_trade_but_unreconstructed_bars": raw_unreconstructed_total,
                            })
                            if accepted_total or verified_empty_total:
                                print(
                                    f"[trade-repair-partial-ok] {contract} {month}: "
                                    f"reconstructed={accepted_total}/{len(wanted)} missing candles; "
                                    f"verified_zero_trade={verified_empty_total}; "
                                    f"valid_windows={valid_windows}; rejected_windows={rejected_windows}",
                                    flush=True,
                                )
                                source_parts.append(
                                    "Gate official monthly futures trades (UTC six-hour OHLCV-overlap validated)"
                                )
                            else:
                                print(
                                    f"[trade-repair-reject] {contract} {month}: no window passed validation "
                                    f"(valid_windows={valid_windows}, rejected_windows={rejected_windows})",
                                    flush=True,
                                )
                        except Exception as trade_error:
                            trade_archive_audit.setdefault(month, {
                                "requested_missing_bars": len(missing_in_month),
                            }).update({
                                "status": "error",
                                "error": str(trade_error),
                            })
                            print(
                                f"[trade-repair-warning] {contract} {month}: "
                                f"monthly trades recovery unavailable: {trade_error}",
                                flush=True,
                            )


                # Continue only with gaps not reconstructed or verified empty by the trade archive.
                already_observed = {
                    int(row["timestamp"]) for row in rows + repaired_rows
                }
                remaining_missing = [
                    timestamp for timestamp in missing_before_repair
                    if timestamp not in already_observed
                    and timestamp not in verified_trade_empty_timestamps
                ]
                trade_repaired_count = len(repaired_rows)
                # A rejected/incomplete trade archive must not block another official source.
                # Rebuild a 15m bar only when all three real 5m candles are present.
                five_minute_rows = fetch_missing_5m_archive_candles(
                    session, contract, timeframe, remaining_missing,
                )
                if five_minute_rows:
                    repaired_rows.extend(five_minute_rows)
                    source_parts.append("Gate official 5m archive recovery (complete three-candle groups)")

                already_observed = {
                    int(row["timestamp"]) for row in rows + repaired_rows
                }
                remaining_missing = [
                    timestamp for timestamp in missing_before_repair
                    if timestamp not in already_observed
                    and timestamp not in verified_trade_empty_timestamps
                ]

                five_minute_rest_rows = fetch_missing_5m_rest_candles(
                    session, contract, timeframe, remaining_missing,
                )
                if five_minute_rest_rows:
                    repaired_rows.extend(five_minute_rest_rows)
                    source_parts.append(
                        "Gate official recent 5m REST recovery (complete three-candle groups)"
                    )

                already_observed = {
                    int(row["timestamp"]) for row in rows + repaired_rows
                }
                remaining_missing = [
                    timestamp for timestamp in missing_before_repair
                    if timestamp not in already_observed
                    and timestamp not in verified_trade_empty_timestamps
                ]

                missing_by_month: dict[str, list[int]] = {}
                for timestamp in remaining_missing:
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

                archive_repaired_count = len(repaired_rows) - trade_repaired_count
                already_observed = {
                    int(row["timestamp"]) for row in rows + repaired_rows
                }
                remaining_missing = [
                    timestamp for timestamp in missing_before_repair
                    if timestamp not in already_observed
                    and timestamp not in verified_trade_empty_timestamps
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
                    and timestamp not in verified_trade_empty_timestamps
                ]
                if remaining_missing:
                    native_rest_rows = fetch_missing_native_rest_candles(
                        session, contract, timeframe, remaining_missing,
                        now_ts=repair_now,
                    )
                    if native_rest_rows:
                        repaired_rows.extend(native_rest_rows)
                        source_parts.append("Gate native public REST recovery for recent missing intervals")

                already_observed = {
                    int(row["timestamp"]) for row in rows + repaired_rows
                }
                remaining_missing = [
                    timestamp for timestamp in missing_before_repair
                    if timestamp not in already_observed
                    and timestamp not in verified_trade_empty_timestamps
                ]

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
                    **({"trade_archive_audit": trade_archive_audit} if timeframe == "15m" else {}),
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