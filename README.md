# Wickless-candle retest backtest (XAUUSD, 5-minute)

Tests a discretionary gold strategy mechanically, and measures how much of its
result depends on the parts of the rules that were never precisely defined.

## The strategy

1. In a trend, find a candle with no wick on the trend side
   (uptrend: a bullish candle whose low equals its open; downtrend: a bearish
   candle whose high equals its open).
2. Mark that open as a level.
3. If price returns to the level within the next few candles, enter with the trend.
4. Stop beyond the most recent swing against the position, target at 1:1.

## Why it is parameterised

Three parts of the description were judgement calls rather than rules, so each is a
parameter and the sweep reports results across all of them:

- **what counts as a trend** — `none`, `ema`, `slope`, `structure`
- **which swing the stop references, and how much room it gets** —
  `pivot` / `bars` / `atr`, with `pivot_k`, `stop_lookback`, `buffer_atr`
- **how exactly "no wick" is meant** — `wick_tol`, in dollars

A result that only appears at one setting is noise. A result that survives most
reasonable settings is worth taking seriously.

## Modelling choices (deliberately pessimistic)

- A bar that spans both stop and target counts as a **loss**: intrabar order is unknowable.
- Exits are checked on the entry bar itself, so a touch that runs straight to the stop counts.
- Stops are derived only from bars **strictly before** entry, never the entry bar's own range.
- Costs are charged once per round trip (`--cost`, in dollars per ounce).
- Malformed bars (low above high, and so on) raise rather than silently trade.

`tests/test_engine.py::test_no_lookahead` enforces the central guarantee: truncating
history immediately after a trade closes must not change that trade.

## Layout

    src/engine.py              rules and trade simulation
    src/engine_fast.py         vectorised trend / signal / pivot precomputation
    src/metrics.py             performance stats, bootstrap confidence intervals
    src/run_backtest.py        single run or full parameter sweep
    src/load_tool_result.py    broker price payloads -> tidy CSV
    tests/                     correctness and no-lookahead tests

## Running

    python3 -m pytest tests -q
    python3 src/run_backtest.py --data data/xauusd_5m_spot.csv --sweep

## Data

The broker feed available to this project caps every request at 3,500 bars ending at
the present moment, which is about twelve days of five-minute history, and expired
futures contracts return nothing. A one- to two-year test therefore needs an export
from a charting platform (MetaTrader or TradingView) with columns
`time, open, high, low, close`.
