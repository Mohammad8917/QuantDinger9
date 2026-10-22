#!/usr/bin/env python3
"""Download real Gate.io USDT-perpetual OHLCV for the locked QD V3 universe.

This is a DATA ACQUISITION tool only. It does not execute a strategy, simulate
fills, or submit orders. It never uses private exchange endpoints or API keys.
Large data files are written outside the Git checkout by default.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

API_URL = "https://api.gateio.ws/api/v4/futures/usdt/candlesticks"
STRATEGY_PATH = "docs/strategies/QD_Adaptive_Quant_Portfolio_20_Risk_Controlled_V3.py"
LOCKED_STRATEGY_BLOB_SHA = "3cd1fbbcf3e57ad5031791b944ce764aad6151b1"
SYMBOLS = (
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "LINK", "POL",
    "ATOM", "NEAR", "APT", "ARB", "OP", "LTC", "BCH", "DOGE", "UNI", "ETC",
)
TIMEFRAMES = {"15m": 900, "1h": 3600}
FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
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


def _parse_row(item: Any) -> dict[str, float | int] | None:
    if not isinstance(item, dict):
        return None
    try:
        row: dict[str, float | int] = {
            "timestamp": int(item["t"]),
            "open": float(item["o"]),
            "high": float(item["h"]),
            "low": float(item["l"]),
            "close": float(item["c"]),
            "volume": float(item["v"]),
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return row


def _validate_row(row: dict[str, float | int], interval: int) -> str | None:
    ts = int(row["timestamp"])
    o, h, low, close, volume = (
        float(row["open"]), float(row["high"]), float(row["low"]),
        float(row["close"]), float(row["volume"]),
    )
    if ts % interval:
        return "timestamp_not_aligned"
    if not all(math.isfinite(value) for value in (o, h, low, close, volume)):
        return "non_finite_value"
    if min(o, h, low, close) <= 0:
        return "non_positive_price"
    if h < max(o, low, close):
        return "invalid_high"
    if low > min(o, h, close):
        return "invalid_low"
    if volume < 0:
        return "negative_volume"
    return None


def fetch_candles(
    session: requests.Session,
    contract: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
    *,
    sleep_seconds: float = 0.12,
    timeout_seconds: float = 20.0,
) -> list[dict[str, float | int]]:
    """Fetch candles in bounded, non-overlapping time windows; never synthesize gaps."""
    interval = TIMEFRAMES[timeframe]
    now_ts = int(time.time())
    effective_end = min(end_ts, now_ts)
    # Only keep fully closed candles. A bar's close time is timestamp + interval.
    last_closed_start = (effective_end // interval) * interval - interval
    if last_closed_start < start_ts:
        raise DataError(f"No fully closed candles available for {contract} {timeframe}")

    cursor = (start_ts // interval) * interval
    result: dict[int, dict[str, float | int]] = {}
    consecutive_empty = 0
    while cursor <= last_closed_start:
        window_end = min(cursor + interval * 999, last_closed_start)
        # Gate's API accepts either a limit-only query or a from/to range;
        # follow the repository's existing native client and omit limit for ranges.
        params = {
            "contract": contract,
            "interval": timeframe,
            "from": cursor,
            "to": window_end,
        }
        response = None
        for attempt in range(5):
            try:
                response = session.get(
                    API_URL,
                    params=params,
                    timeout=timeout_seconds,
                    headers={"User-Agent": USER_AGENT},
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt == 4:
                        response.raise_for_status()
                    time.sleep(min(2 ** attempt, 12))
                    continue
                response.raise_for_status()
                payload = response.json()
                break
            except (requests.RequestException, ValueError) as exc:
                if attempt == 4:
                    raise DataError(
                        f"Gate request failed for {contract} {timeframe} at {cursor}: {exc}"
                    ) from exc
                time.sleep(min(2 ** attempt, 12))
        if not isinstance(payload, list):
            raise DataError(f"Unexpected Gate response for {contract} {timeframe}: expected list")

        parsed = [_parse_row(item) for item in payload]
        valid_in_window = 0
        for row in parsed:
            if row is None:
                continue
            ts = int(row["timestamp"])
            if max(cursor, start_ts) <= ts <= window_end and ts % interval == 0:
                result[ts] = row
                valid_in_window += 1
        if valid_in_window == 0:
            consecutive_empty += 1
        else:
            consecutive_empty = 0
        # Advance to the next candle boundary. Adding one second would drift
        # subsequent windows off the timeframe grid and weaken range filtering.
        cursor = window_end + interval
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        if consecutive_empty >= 3:
            # Keep checking later windows, but don't let a broken API loop indefinitely.
            consecutive_empty = 0
    rows = [result[key] for key in sorted(result)]
    if not rows:
        raise DataError(f"Gate returned no valid candles for {contract} {timeframe}")
    return rows


def audit_rows(rows: list[dict[str, float | int]], timeframe: str) -> dict[str, Any]:
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
    gaps = sum(1 for a, b in zip(ordered, ordered[1:]) if b - a > interval)
    return {
        "bars": len(rows),
        "first_timestamp": ordered[0] if ordered else None,
        "last_timestamp": ordered[-1] if ordered else None,
        "invalid_rows": invalid,
        "gap_count": gaps,
        "complete_contiguous_history": gaps == 0 and not invalid,
    }


def write_gzip_csv(path: Path, rows: list[dict[str, float | int]]) -> str:
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
        "schema_version": 1,
        "data_source": "Gate.io public USDT perpetual futures REST API",
        "endpoint": API_URL,
        "strategy_path": STRATEGY_PATH,
        "locked_strategy_git_blob_sha1": LOCKED_STRATEGY_BLOB_SHA,
        "start_timestamp_requested": start_ts,
        "end_timestamp_requested": end_ts,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "order_execution": "NOT_PERFORMED_DATA_DOWNLOAD_ONLY",
        "symbols": {},
    }
    failures: list[str] = []
    for base in SYMBOLS:
        contract = f"{base}_USDT"
        manifest["symbols"][contract] = {}
        for timeframe in TIMEFRAMES:
            print(f"[download] {contract} {timeframe}", flush=True)
            try:
                rows = fetch_candles(session, contract, timeframe, start_ts, end_ts)
                audit = audit_rows(rows, timeframe)
                if audit["invalid_rows"]:
                    raise DataError(f"Invalid candle rows: {audit['invalid_rows']}")
                filename = f"{contract}_{timeframe}.csv.gz"
                sha256 = write_gzip_csv(output_dir / filename, rows)
                manifest["symbols"][contract][timeframe] = {
                    **audit,
                    "file": filename,
                    "sha256": sha256,
                    "interval_seconds": TIMEFRAMES[timeframe],
                }
                print(
                    f"[ok] {contract} {timeframe}: {audit['bars']} bars; "
                    f"{audit['gap_count']} gaps; sha256={sha256}",
                    flush=True,
                )
            except Exception as exc:
                failures.append(f"{contract} {timeframe}: {exc}")
                manifest["symbols"][contract][timeframe] = {"error": str(exc)}
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
    parser.add_argument("--output", type=Path, default=default_output_dir(),
                        help="Output directory (default is outside the Git checkout)")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="QuantDinger9 repository root; used only to verify the locked strategy")
    args = parser.parse_args(argv)
    end_ts = utc_timestamp(args.end) if args.end else int(time.time())
    start_ts = utc_timestamp(args.start) if args.start else end_ts - 2 * 365 * 24 * 60 * 60
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
