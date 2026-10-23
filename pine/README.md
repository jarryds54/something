# TradingView version

`wickless_retest.pine` is a Pine v6 strategy mirroring `src/engine.py`. Defaults are
the configuration recommended for a FundingPips 2-Step Pro evaluation: the 1:1 target,
the volatility filter, 0.5% risk and a −2R daily stop.

## Using it

1. TradingView → Pine Editor → paste the file → **Add to chart**.
2. Set the chart to **XAUUSD, 5 minutes**. The rules are timeframe-specific; on any
   other timeframe the numbers mean nothing.
3. Open **Strategy Tester** for the trade list, and the settings gear to change inputs.
4. `Broker hours ahead of UTC` must match your platform (FundingPips is UTC+3). It
   decides when the daily stop resets.

Triangles mark wickless candles, horizontal lines show each level for as long as it
stays live, and the background turns red on days where the −2R stop has halted trading.

## Where it will differ from the Python backtest

Expect similar but not identical results. The differences are known and none of them
indicate a bug:

- **Spread.** TradingView charges the commission set in the script ($7/lot, as
  `cash_per_contract`) but models no spread at all. The Python results charge your
  real recorded spread per bar, averaging $0.24 a trade. **TradingView will therefore
  look better than the truth by roughly 0.02–0.03R per trade.**
- **Data.** TradingView's XAUUSD feed is a different provider from your FundingPips
  export, so individual candles — and therefore which candles are exactly wickless —
  will not match perfectly. Since wick tolerance is the single most important
  parameter, expect a different trade count.
- **Ambiguous bars.** When one candle contains both the stop and the target, the
  Python engine always books the loss. TradingView resolves it by its own assumption.
  On a paid plan, enable **Bar Magnifier** in the strategy properties to reduce this.
- **Volatility percentile.** `ta.percentrank` and the pandas rolling rank treat the
  current bar slightly differently, so the filter will disagree at the margin.
- **Position sizing.** Quantity is rounded down to whole ounces.

## Reading the comparison

If TradingView shows a materially *worse* result than the Python backtest, that is
worth investigating, because the spread difference should push it the other way. If it
shows a modestly better one, that is expected.

The point of this script is not to re-run the backtest. It is to let you watch the
entries appear on a chart and confirm they are the trades you would actually have
taken — which is the one thing the Python engine cannot tell you.
