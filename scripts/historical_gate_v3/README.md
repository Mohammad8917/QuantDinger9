# Gate historical data for locked QD V3

This tool downloads **real public-market candles** for the exact 20-symbol universe in
`docs/strategies/QD_Adaptive_Quant_Portfolio_20_Risk_Controlled_V3.py`, on Gate USDT
perpetual futures, for 15-minute and 1-hour timeframes.

## Safety and scope

- Data acquisition only. It does **not** import or execute the strategy.
- It does **not** simulate fills, calculate PnL, or send orders.
- Uses Gate's official monthly 10s/1m/5m/1h candle and futures-trade archives for older history, plus public futures candlestick REST only inside its recent 10,000-point window; no API key is required.
- Gate's REST API enforces a recent-history boundary (the endpoint returns `Candlestick too long ago. Maximum 10000 points recently are allowed` for older candles) and a per-query point limit. Requests use `from` and `to` only, with at most 900 points per page, and are sent only inside that recent window. Older gaps must be recovered from official monthly archives, including real futures trades; invalid old REST requests are not used as a repair mechanism.
- Historical 15m candles are aggregated from observed real 5m archive candles. Older 1h candles come from the 1h archive. Missing buckets are first repaired from observed real 1m candles, then official 10s candle archives, then actual futures trades in Gate monthly trade archives; recent gaps may use REST only inside its allowed window. Empty intervals are not synthesized. The recent 15m/1h tails come directly from REST; the downloader never retries a multi-year range against REST.
- Gap repair first uses observed 1m OHLCV. Historical gaps not recovered from 1m candles are reconstructed from actual rows in Gate's monthly futures `trades` archive (timestamp, deal ID, price, signed size); open/close follow chronological trade order and volume sums absolute contract sizes. A bucket with no actual trades remains missing. The recent REST endpoint is used only within its documented/observed recent-history boundary. No interpolation or fabricated empty candles are permitted; remaining gaps fail the final audit.
- It verifies the locked strategy's Git blob SHA-1 before collecting data. If the strategy
  changes, collection stops rather than silently testing a different version.
- Missing historical candles are not synthesized. Internal gaps, duplicate timestamps, invalid OHLCV, and missing leading/trailing bars are audited.
- The public contract metadata `create_time` is used as the earliest expected-history boundary (rounded up to a candle boundary); this avoids falsely treating pre-listing time as missing history.
- The manifest records raw expected/observed counts, unresolved gaps, and separate source-coverage and contiguous-history flags. A missing bucket is resolved only when reconstructed from observed real source data. A successfully parsed trade archive with no row inside a bucket is not enough to prove that no trades occurred, because archive completeness is not independently verified here. Such gaps remain unresolved and collection exits non-zero; no candles are synthesized. `complete_contiguous_history` and `backtest_ready` remain false when any expected candle is absent.
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

- `<BASE>_USDT_15m.csv.gz` (observed 5m archive aggregation plus native recent REST tail, with missing buckets recovered from observed 1m/10s archives or actual futures trades) and `<BASE>_USDT_1h.csv.gz` (older 1h archive plus native recent REST tail, with missing buckets recovered from observed 1m/10s archives or actual futures trades) per contract. The `quote_volume` column is blank because the public sources do not provide it and the downloader keeps the schema consistent.
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
