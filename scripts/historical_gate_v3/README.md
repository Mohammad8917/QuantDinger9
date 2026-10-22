# Gate historical data for locked QD V3

This tool downloads **real public-market candles** for the exact 20-symbol universe in
`docs/strategies/QD_Adaptive_Quant_Portfolio_20_Risk_Controlled_V3.py`, on Gate USDT
perpetual futures, for 15-minute and 1-hour timeframes.

## Safety and scope

- Data acquisition only. It does **not** import or execute the strategy.
- It does **not** simulate fills, calculate PnL, or send orders.
- Uses Gate's official monthly futures candle archives for older history, preferring the native 15m archive when available and otherwise aggregating only complete observed 5m groups; 1m/10s archives are used for gap recovery. Public futures candlestick REST is used for the recent tail and unresolved historical gaps, in bounded pages of at most 900 candles; no API key is required.
- Gate's REST API enforces a recent-history boundary (the endpoint returns `Candlestick too long ago. Maximum 10000 points recently are allowed` for older candles) and a per-query point limit. Requests use `from` and `to` only, with at most 900 points per page, and are sent only inside that recent window. Older gaps are repaired only from official monthly candle archives; invalid old REST requests are not used as a repair mechanism.
- Historical 15m candles use Gate's native official 15m monthly archive when that archive is available. If the native 15m archive returns HTTP 404, the downloader falls back to observed real 5m archive candles only when all three expected 5m rows are present. Missing buckets are repaired from observed real 1m candles only when every expected minute is present, then official 10s candle archives only when every expected 10s row is present; recent gaps may use REST only inside its allowed window. Partial lower-timeframe groups are skipped rather than promoted to full target candles, and empty intervals are not synthesized. The recent 15m/1h tails come directly from REST; the downloader never retries a multi-year range against REST.
- Gap repair uses complete observed 1m or 10s candle sets and bounded recent REST only. Trade archives are intentionally not converted into candles because their documented schema does not expose the `is_internal` flag used to exclude internal trades from K-lines. No interpolation or fabricated empty candles are permitted; remaining gaps fail the final audit.
- It verifies the locked strategy's Git blob SHA-1 before collecting data. If the strategy
  changes, collection stops rather than silently testing a different version.
- Missing historical candles are not synthesized. Internal gaps, duplicate timestamps, invalid OHLCV, and missing leading/trailing bars are audited.
- The public contract metadata `create_time` is used as the earliest expected-history boundary (rounded up to a candle boundary); this avoids falsely treating pre-listing time as missing history.
- The manifest records raw expected/observed counts, unresolved gaps, and separate source-coverage and contiguous-history flags. Partial lower-timeframe candle groups do not prove full target OHLCV and are skipped; such gaps remain unresolved and collection exits non-zero. No candles are synthesized. `complete_contiguous_history` and `backtest_ready` remain false when any expected candle is absent.
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

- `<BASE>_USDT_15m.csv.gz` (native official 15m archive when available, otherwise complete observed 5m archive aggregation, plus native recent REST tail; missing buckets are recovered from complete 1m/10s candle sets or verified native public REST candles) and `<BASE>_USDT_1h.csv.gz` (older 1h archive plus native recent REST tail, with missing buckets recovered only from complete 1m/10s candle sets) per contract. The `quote_volume` column is blank because the public sources do not provide it and the downloader keeps the schema consistent.
- `manifest.json` (schema version 4) records the requested range, source endpoint, locked strategy fingerprint,
  actual and expected first/last candle, expected/observed bar counts, coverage ratio, missing leading/trailing/internal bars, duplicate/invalid row counts, and file SHA-256.

A non-zero exit code means source coverage remains unresolved or data validation failed. Inspect the manifest's `failures` and per-market entries. `source_coverage_complete` means every expected timestamp has a real observed or reconstructed candle; unverified absences remain unresolved and make the run fail. `complete_contiguous_history` is stricter, and `backtest_ready` remains false if any expected candle is absent.

## Important limitation: this is not the backtest

The locked V3 file uses the QuantDinger host runtime contract (`initialize`, `handle_data`,
`get_history`, `get_position`, `order_target_percent`, order status/reconciliation and
portfolio state). The repository's generic Strategy API V2 backtest path is not automatically
proof that this host-specific strategy executes correctly. A faithful historical backtest still
needs a compatible runner that replays these exact real candles chronologically and replaces
all order calls with simulated fills, with fees/slippage and risk checks. Until that runner is
verified, no trade count, PnL, win rate, or drawdown should be reported as a test result.
