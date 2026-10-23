# Wickless-candle retest on XAUUSD 5m — findings

Data: 100,000 five-minute bars, 27 May 2025 to 23 October 2026 (MetaTrader export,
broker clock +3h, converted to UTC). 656,254 simulated trades across 300 configurations.

## Verdict

The pattern has a **real but small edge before costs**, and **realistic costs consume
most of it**. Break-even sits at a round-trip cost of about **$0.33 per ounce**.

| round trip | mean per trade | total over 17 months |
|---|---|---|
| $0.00 | +0.080R | +98R |
| $0.15 | +0.043R | +53R |
| $0.30 | +0.007R | +8R |
| $0.50 | −0.043R | −52R |

## Why the edge is credible

- **Out of sample it held.** Configuration chosen on the first 60% of the data; on the
  untouched last 40% it returned +0.096R gross (54.7% win) against +0.070R in sample.
- **Positive in six of seven quarters**, the exception being a 104-trade stub quarter.
- **Symmetric** between longs (53.6%) and shorts (54.3%), so it is not an artefact of
  gold's bull run.
- **Robust across settings.** Of the 40 configurations using an exactly wickless candle
  with swing-pivot stops, 40 were positive gross, median +0.054R. Not one lucky cell.
- Gross win rate 53.9% over 1,236 trades, outside the 47.2–52.8% band a coin flip
  would produce.

## Why it does not survive costs

Average stop is about $10, so $0.30 of spread is ~3% of risk per trade, against a raw
edge of ~8%. Cost eats roughly three quarters of it. Stop size is therefore decisive:

| stop rule | avg stop | cost as % of risk | net at $0.30 |
|---|---|---|---|
| ATR 1.5× | $6.60 | 4.5% | −0.040R |
| swing pivot | $9.72 | 3.1% | +0.007R |
| 50-bar low/high | $23.60 | 1.3% | +0.026R |

## The single most important rule

Wick tolerance dominates every other parameter.

| "no wick" means | gross median | configs positive | net median at $0.30 |
|---|---|---|---|
| exactly zero | +0.022R | 74% | −0.043R |
| within $0.05 | −0.016R | 38% | −0.065R |
| within $0.20 | −0.014R | 38% | −0.075R |

Loosening the definition roughly quadruples trade count and destroys the edge. A
backtest that encoded any tolerance here would correctly report "no edge" while the
strict rule still had one — the likely source of the earlier disagreement.

## Ideas tested and rejected

Recorded because discarding them honestly is what keeps the rest trustworthy.

- **Requiring a slower retest** (subgroups suggested 3+ bars won far more often): failed.
  Worse at every cost level and out of sample. The subgroup pattern was noise.
- **Larger targets.** 3:1 survived out of sample (+0.031R) but no better than the
  original 1:1 (+0.031R), at a 28% win rate. No reason to change.
- **100-bar stops.** Cost share falls to 1.1% but the edge falls faster; net negative.

## What would make it tradeable

1. **Cost below ~$0.25 round trip.** This is the main lever. At $0.15 it returns
   +0.043R per trade, which over 1,227 trades is +53R.
2. **Wider structural stops**, which shrink cost as a share of risk.
3. **Position size**, since nothing here beats about +0.04R per trade; it is a
   grinding edge, not a large one.

## Caveats

- Costs are modelled as a flat round trip; real slippage worsens in fast markets,
  which is exactly when these levels get hit.
- The data is one broker's feed over one 17-month period dominated by a violent gold
  rally and reversal.
- Entry assumes a limit order filling at the level. Fills on a touch are not guaranteed.
- 300 configurations were examined. The out-of-sample and cross-configuration checks
  are what guard against that, but they do not eliminate it.

---

# Phase two — searching for a better configuration

Method: the data was split into train (May 2025–Feb 2026), validate (Feb–Jun 2026)
and holdout (Jun–Oct 2026). Ideas were generated on train, confirmed on validate,
and the holdout was spent exactly once on the final configuration.

## Ideas tested

| idea | train | validate | verdict |
|---|---|---|---|
| best 12 hours of the day, chosen on train | +0.076R | −0.030R | **overfit** |
| US session only (12–20 UTC) | +0.030R | −0.074R | **fails** |
| London session only (7–15 UTC) | −0.066R | +0.119R | **inconsistent** |
| above-median volatility | +0.044R | +0.058R | **survives** |
| below-median volatility | −0.092R | +0.010R | fails |
| signal body ≥ 0.5 ATR | +0.007R | +0.094R | weak on train |
| signal body ≥ 1.0 ATR | −0.052R | +0.124R | inconsistent |
| 50-bar wide stop | −0.009R | +0.090R | inconsistent |
| overlapping positions allowed | −0.017R | +0.024R | no change |
| trend lookback 20 | −0.057R | +0.026R | worse |
| wait up to 10 candles | −0.017R | +0.007R | no better than 7 |

The hour-of-day result is the clearest warning: each hour held only 20–40 trades, so
picking the good ones fitted noise almost perfectly and then reversed out of sample.

## What survived

**Trade only when volatility is above its recent median** (ATR percentile rank against
the trailing 2,000 bars). It works across a plateau of thresholds (0.3–0.5) rather than
one lucky value, and the reason is mechanical: in quiet markets the stop is small, so a
fixed spread is a larger share of risk, and there is less room to reach a 1:1 target
before noise intervenes.

## Final configuration

    trend=slope, trend_len=10, wick_tol=0.0, wait_bars=7,
    stop_mode=pivot, buffer_atr=0.0, atr_pct_min=0.4, rr=1.0

| period | trades | win rate | mean R @ $0.25 |
|---|---|---|---|
| train | 379 | 54.9% | +0.042R |
| validate | 139 | 56.1% | +0.085R |
| **holdout (spent once)** | **191** | **57.6%** | **+0.108R** |

Your unfiltered rules on the same holdout: 324 trades, 56.5%, +0.075R. The filter
improved the per-trade result in all three periods, by 0.03–0.06R, while roughly
halving the number of trades. Over the full 17 months at $0.25 the filtered version
returns +49R against +23R unfiltered.

## Honest caveats

- The three periods are not independent samples of one stable process. The later
  periods were better for *every* variant, so part of the improvement across splits is
  regime, not skill. The filter's advantage *within* each period is the real evidence.
- About twenty ideas were tested. The holdout protects the final number, but the
  search itself still inflates expectations.
- Everything still depends on cost. At $0.35 the filtered edge is +0.089R on holdout;
  the exact figure for FundingPips is unmeasured.

## Next step that would matter most

Export the same 5-minute history from the **FundingPips** terminal. Its spread column
records the real spread on every bar, which would replace the flat cost assumption
with the actual cost at the moment of each trade, including the wide ones around news.
