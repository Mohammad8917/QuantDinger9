# Gate historical data for locked QD V3

This tool downloads **real public-market candles** for the exact 20-symbol universe in
`docs/strategies/QD_Adaptive_Quant_Portfolio_20_Risk_Controlled_V3.py`, on Gate USDT
perpetual futures, for 15-minute and 1-hour timeframes.

## Safety and scope

- Data acquisition only. It does **not** import or execute the strategy.
- It does **not** simulate fills, calculate PnL, or send orders.
- Uses Gate's official monthly historical archives for older candles and the public futures candlestick REST endpoint only for the recent tail; no API key is required.
- Gate's public REST endpoint rejects older historical ranges outside its recent 10,000-point window. The downloader uses monthly archives for older history and native REST candles only inside that recent window, fetching at most 900 points per request to stay below the observed request limit.
- Older 15m candles are aggregated from observed real 5m archive candles, including partial groups when the archive omits no-trade 5m intervals. Older 1h candles come from the 1h archive. If a 15m or 1h candle is missing, the downloader tries to recover that exact bucket from observed real 1m archive candles. The recent 15m/1h tails come directly from REST. The downloader never retries a multi-year range against REST.
- Gap repair uses actual 1m OHLCV only; it does not interpolate prices or manufacture empty candles. A bucket with observed 1m candles is aggregated from those real rows; a bucket with no observed 1m candles remains missing. The final audit reports any remaining gaps and the run fails closed when coverage is incomplete.
- It verifies the locked strategy's Git blob SHA-1 before collecting data. If the strategy
  changes, collection stops rather than silently testing a different version.
- Missing historical candles are not synthesized. Internal gaps, duplicate timestamps, invalid OHLCV, and missing leading/trailing bars are audited.
- The public contract metadata `create_time` is used as the earliest expected-history boundary (rounded up to a candle boundary); this avoids falsely treating pre-listing time as missing history.
- The manifest records expected vs observed bar counts, coverage ratio, leading/trailing missing bars, internal gap spans, and duplicate/invalid row counts. No-trade intervals are never filled with fabricated candles; any expected interval that remains absent after 1m-source recovery makes the collection exit non-zero.
- Files are gzip-compressed CSVs plus a manifest with time coverage, bar counts, gap counts,
  and SHA-256 checksums.
- `volume` preserves Gate contract-size volume from the selected source: archive `size` or public REST `v`. Neither source used here provides quote-currency turnover, so `quote_volume` is blank and explicitly marked unavailable. The downloader never estimates it or presents it as exact.
- Output defaults outside the checkout: Windows `%LOCALAPPDATA%\QuantDinger9\historical\gate_v3`
  or `~/.cache/QuantDinger9/historical/gate_v3` on Unix-like systems. Large datasets are
  not committed to Git.

## Run on Windows / Python 3.13

From the repository root, with the project's Python environment activated and `requests`
installed:

```powershell
py -3.13 scripts/historical_gate_v3/download_gate_history.py
```

By default, the date range ends at the current UTC time and begins two 365-day years earlier.
Only fully closed candles are kept. Date-only `--start` values mean midnight UTC at the start of
that date; date-only `--end` values include the full named UTC date.

Optional explicit dates:

```powershell
py -3.13 scripts/historical_gate_v3/download_gate_history.py --start 2024-10-22 --end 2026-10-22
```

Choose an output directory:

```powershell
py -3.13 scripts/historical_gate_v3/download_gate_history.py --output "D:\QuantDingerData\gate_v3"
```

## Output

- `<BASE>_USDT_15m.csv.gz` (observed 5m archive aggregation plus native recent REST tail, with missing buckets recovered only from observed 1m candles) and `<BASE>_USDT_1h.csv.gz` (older 1h archive plus native recent REST tail, with the same 1m-source recovery) per contract. The `quote_volume` column is blank because the public sources do not provide it and the downloader keeps the schema consistent.
- `manifest.json` (schema version 3) records the requested range, source endpoint, locked strategy fingerprint,
  actual and expected first/last candle, expected/observed bar counts, coverage ratio, missing leading/trailing/internal bars, duplicate/invalid row counts, and file SHA-256.

A non-zero exit code means collection was incomplete or data validation failed. Inspect the
manifest's `failures` and per-market entries; do not treat a partial dataset as complete.

## Important limitation: this is not the backtest

The locked V3 file uses the QuantDinger host runtime contract (`initialize`, `handle_data`,
`get_history`, `get_position`, `order_target_percent`, order status/reconciliation and
portfolio state). The repository's generic Strategy API V2 backtest path is not automatically
proof that this host-specific strategy executes correctly. A faithful historical backtest still
needs a compatible runner that replays these exact real candles chronologically and replaces
all order calls with simulated fills, with fees/slippage and risk checks. Until that runner is
verified, no trade count, PnL, win rate, or drawdown should be reported as a test result.
