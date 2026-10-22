# Gate historical data for locked QD V3

This tool downloads **real public-market candles** for the exact 20-symbol universe in
`docs/strategies/QD_Adaptive_Quant_Portfolio_20_Risk_Controlled_V3.py`, on Gate USDT
perpetual futures, for 15-minute and 1-hour timeframes.

## Safety and scope

- Data acquisition only. It does **not** import or execute the strategy.
- It does **not** simulate fills, calculate PnL, or send orders.
- Uses only Gate's public futures candlestick REST endpoint; no API key is required.
- It verifies the locked strategy's Git blob SHA-1 before collecting data. If the strategy
  changes, collection stops rather than silently testing a different version.
- Missing historical candles are not synthesized. Internal gaps, duplicate timestamps, invalid OHLCV, and missing leading/trailing bars are audited.
- The public contract metadata `create_time` is used as the earliest expected-history boundary (rounded up to a candle boundary); this avoids falsely treating pre-listing time as missing history.
- The manifest records expected vs observed bar counts, coverage ratio, leading/trailing missing bars, internal gap spans, and duplicate/invalid row counts. Any incomplete coverage makes the collection exit non-zero.
- Files are gzip-compressed CSVs plus a manifest with time coverage, bar counts, gap counts,
  and SHA-256 checksums.
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

- `<BASE>_USDT_15m.csv.gz` and `<BASE>_USDT_1h.csv.gz` per contract.
- `manifest.json` (schema version 2) records the requested range, source endpoint, locked strategy fingerprint,
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
