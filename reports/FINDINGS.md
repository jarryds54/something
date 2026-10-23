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

---

# Phase three — your own broker's data and your own costs

Second export, from the FundingPips terminal, same period and timeframe. This is
both a cost measurement and an independent check: the configuration was chosen on
TraderScale prices and is re-tested here on a different feed.

## Measured costs

| spread, $/oz | 10% | 25% | median | 75% | 90% | 99% | max |
|---|---|---|---|---|---|---|---|
| FundingPips | 0.10 | 0.12 | **0.15** | 0.18 | 0.28 | 0.59 | 5.33 |

Mean $0.18. Roughly flat through the day, widening to ~$0.26 at 22:00–23:00 UTC.
6.8% of bars exceed $0.30. Not better than TraderScale (median $0.13) — slightly
worse in the middle of the distribution.

Charging the spread recorded on each bar plus $7/lot commission ($0.07/oz), the
**actual cost paid averaged $0.24 per trade, a median 2.6% of risk**.

## Result with real costs (plus 10c of stop slippage)

| version | trades | win rate | mean R | total | max DD |
|---|---|---|---|---|---|
| your rules as described | 999 | 55.3% | +0.044R | +38R | — |
| **+ volatility filter** | **592** | **56.9%** | **+0.089R** | **+53R** | −11.5R |

Positive in train, validate and holdout for both versions. 12 of 18 months
profitable; the best month is 21% of the total, so it is not one lucky window.

## Stress tests (filtered version, full period)

| scenario | mean R | total |
|---|---|---|
| measured spreads, $7/lot | +0.097R | +58R |
| commission charged per side ($0.14/oz) | +0.084R | +50R |
| spreads × 1.5 | +0.082R | +49R |
| spreads × 2 and commission per side | +0.054R | +32R |
| 25c slippage on every stop | +0.077R | +46R |
| 50c slippage on every stop | +0.057R | +34R |
| $1.00 slippage on every stop | +0.017R | +10R |

The edge only disappears under conditions well outside anything normal.

## Conclusion

The strategy is **viable at your costs**, at roughly +0.09R per trade over about
35 trades a month. That is a grinding edge, not a large one: expect long flat
stretches, and six losing months in eighteen.

## What is still not modelled

- **Limit fills are assumed.** Every entry assumes an order filled exactly at the
  level. In fast moves that is optimistic.
- **Stops are assumed to fill at the stop**, adjusted only by the flat slippage above.
- One instrument, one 17-month period containing an exceptional gold move.
- The trend filter is `slope`, a mechanical proxy for a judgement you make by eye.
  It agrees with you often, not always.

---

# Phase four — exhaustive search for a better version

112 single variations plus 20 combinations, all judged on train and validate, with
the holdout opened only for the three finalists. Costs throughout: measured
FundingPips spread per bar, $7/lot commission, 10c slippage on every stop.

## First: where do these trades actually go?

Excursion analysis on 592 entries, measured over the following 24 hours in units of
initial risk, asking how often each target is reached **before** a 1R adverse move:

| target | reached first |
|---|---|
| 1.0R | 56.9% |
| 1.5R | 44.9% |
| 2.0R | 37.5% |
| 3.0R | 27.2% |
| 4.0R | 20.9% |

Gross expectancy implied: 1R → +0.14R, 1.5R → +0.12R, 2R → +0.13R, 3R → +0.09R.
The 56.9% at 1R matches the engine's win rate exactly, which is a useful check that
two independent calculations agree. **Your 1:1 target leaves money on the table.**

## What failed

| idea | result |
|---|---|
| **breakeven stop** at 0.3R / 0.5R / 0.75R / 1.0R, with and without offset | **every variant below baseline on validate**; the scratches cost more than the saved losses, exactly as the literature predicts |
| **time stops** at 12 / 24 / 48 / 96 bars | all below baseline; the longer the leash the better, so cutting trades early destroys value |
| **trailing from 0R, 0.5R or 1R** | negative on train; trailing too early strangles the winners |
| hour-of-day and session filters (phase two) | overfitted, reversed out of sample |
| **stacking every filter together** | 11 validation trades, −0.085R; over-filtering |
| removing the volatility filter | kills everything; it remains essential |

## What worked

- **A wider target.** Everything from 1.25R to 2.5R beat 1:1 on both splits.
- **Trailing late.** 2× ATR starting at 2–3R is a genuine plateau: train +0.095 to
  +0.111R and validate +0.266 to +0.382R across the whole neighbourhood.
- Partials help slightly; imbalance and 15m-structure filters look strong but cut the
  sample to 31–50 validation trades, too thin to rely on.

## The three finalists, holdout included

| | trades | win rate | mean R | total | max DD | return/DD | worst losing run | longest flat |
|---|---|---|---|---|---|---|---|---|
| **A. your rules, 1:1** | 592 | 56.9% | +0.089R | +53R | −11.5R | **4.59** | 6 | 84 days |
| **B. target 2.5R** | 509 | 35.8% | +0.148R | +75R | −23.2R | 3.24 | 12 | 118 days |
| **C. trail 2×ATR from 2.5R** | 507 | 33.3% | +0.184R | **+93R** | −22.5R | 4.13 | 12 | 102 days |

Holdout alone: A +0.121R, B +0.157R, C +0.153R. All three positive.

**B is dominated** — it earns less than C for slightly more drawdown. The real choice
is A against C.

## The trade-off, stated plainly

C earns 76% more per month (5.5R vs 3.1R) for roughly double the drawdown, a win rate
of one in three, losing runs up to twelve trades, and three-month flat stretches.
A is calmer, wins more often than it loses, and has the better return-to-drawdown
ratio, which is what a prop-firm drawdown limit actually tests.

**For a funded-account evaluation, A's profile is the safer instrument. For long-run
capital growth with the drawdown tolerance to sit through it, C earns more.**

## Caveats that now matter more

- The holdout has been opened twice, which degrades it as evidence.
- Roughly 130 variations were tested. Some of the gap between A and C is search.
- C's 33% win rate changes what trading it feels like: a 12-trade losing run is normal,
  not a malfunction, and most people abandon a system there.

---

# Phase five — will it pass a funded evaluation?

Expectancy is not what an evaluation tests. It tests whether the equity path touches
a limit before it reaches the target, which depends on risk per trade and on the
order the losses happen to arrive in. So the answer is a probability.

Method: block bootstrap (blocks of 20 trades, so losing streaks survive the
resampling), 1,500 simulated evaluations per cell, $100k nominal, fixed-fractional
risk. Intraday equity is modelled, not just closed trades: one position at a time
with a hard stop means floating loss never exceeds 1R, so the worst point of any day
is the running total minus one risk unit. The daily limit resets at midnight platform
time (UTC+3), not UTC.

Rules used: 6% + 6% targets, static drawdown from the starting balance. Their own
site is unreachable from this container and third-party sources conflict on the
limits, so both plausible sets are shown.

## Probability of passing both phases

**Tight limits (3% daily, 6% max)**

| variant | 0.25% | 0.50% | 0.75% | 1.00% |
|---|---|---|---|---|
| **A. your 1:1** | 63.5% | **80.7%** | 38.0% | 17.0% |
| B. 2.5R target | 76.3% | 54.4% | 33.0% | 18.1% |
| C. trail from 2.5R | 76.7% | 51.3% | 34.6% | 17.4% |

**Loose limits (5% daily, 10% max)**

| variant | 0.25% | 0.50% | 0.75% | 1.00% |
|---|---|---|---|---|
| **A. your 1:1** | 63.7% | **91.8%** | 87.9% | 61.1% |
| B. 2.5R target | 82.7% | 81.1% | 65.9% | 54.6% |
| C. trail from 2.5R | 87.1% | 77.3% | 62.5% | 50.1% |

(At 0.25% risk the lower pass rates are not failures — most of those runs simply had
not reached the target within 17 months of trades.)

## This reverses the phase-four recommendation

The trailing version earns 76% more per month, yet **passes less often**, because an
evaluation does not reward expectancy, it punishes drawdown. A 33% win rate with
twelve-trade losing runs is exactly the shape of equity curve these rules are
designed to eliminate.

## Once funded: reaching a 5% payout before breaching

| | 0.25% risk | 0.50% | 0.75% |
|---|---|---|---|
| A, tight limits | 95.9% | 91.1% | 67.3% |
| C, tight limits | 87.8% | 70.5% | 59.4% |
| A, loose limits | — | 97.8% | 93.9% |
| C, loose limits | — | 86.9% | 77.7% |

## Recommendation

**Trade your original 1:1 rules with the volatility filter, at 0.5% risk per trade.**

- Tight limits: 80.7% pass, about 6 months.
- Loose limits: 91.8% pass, about 6 months; 0.75% risk gives 87.9% in 3.7 months.
- Funded: 91–98% chance of a payout before a breach.

Doubling risk to 1% roughly halves the pass rate while only halving the time. It is
a bad trade. The impatience that makes 1% attractive is the single largest threat to
the account.

Keep the wider-target versions for a personal account where no external drawdown
limit exists.

---

# Phase six — the actual rules, and the daily stop

Confirmed from the account dashboard: **FundingPips 2-Step Pro — 6% and 6% targets,
3% daily loss, 6% static maximum loss, no minimum days.**

## A methodology fix that changed the answer

Resampling individual trades spreads them evenly across the calendar and hides the
daily limit, which only bites when several losses land on the same day. The real
distribution is uneven: 1 to 9 trades a day, and **the worst day in the sample lost
5.26R**. The simulation now resamples whole trading days in blocks.

That produces a cliff. At 0.5% risk the worst day costs 2.6% — inside the limit. At
0.6% it costs 3.16% — a breach.

| risk | pass | daily breach | max breach | months |
|---|---|---|---|---|
| 0.30% | 97.7% | 0.0% | 2.3% | 11.7 |
| 0.40% | 91.6% | 0.0% | 8.3% | 8.2 |
| **0.50%** | **83.5%** | 0.0% | 16.5% | 5.9 |
| 0.60% | 50.0% | **35.4%** | 14.6% | 3.9 |
| 1.00% | 16.2% | 80.2% | 3.7% | 1.1 |

## Stopping for the day after −2R

Removing the cliff by construction: stop trading for the day once down 2R.

| risk | no daily stop | with −2R daily stop | months |
|---|---|---|---|
| 0.50% | 83.5% | **94.3%** | 5.6 |
| 0.60% | 50.0% | **89.7%** | 4.5 |
| 0.75% | 37.0% | 80.2% | 3.2 |
| 0.90% | 31.3% | 71.3% | 2.4 |
| 1.00% | 16.2% | 64.7% | 2.1 |

It eliminates daily breaches entirely up to 0.9% risk, and lets you carry more size
for the same safety — which is where the time saving comes from.

**Does it make more money? No.** Over the full period it looks like it (+65R vs +53R)
but that is almost entirely the training period: validate barely moved and holdout was
slightly worse. The 29 skipped trades averaged −0.43R, which is a small and
unreliable sample. Use the daily stop because it makes a daily breach arithmetically
impossible, not because it adds expectancy.

## Once funded (payout at 5%, same limits)

| risk | no daily stop | with −2R stop |
|---|---|---|
| 0.50% | 91.6% | **97.0%** |
| 0.60% | 73.8% | 94.9% |
| 0.75% | 64.5% | 90.4% |

## Final recommendation for this account

**Your original 1:1 rules, with the volatility filter, at 0.5–0.6% risk per trade,
stopping for the day after −2R.**

- 0.5% risk: 94.3% pass, about 5.6 months, 97.0% payout rate once funded.
- 0.6% risk: 89.7% pass, about 4.5 months, 94.9% payout rate once funded.

Do not use the wider-target or trailing versions here. They earn more per trade and
pass far less often (52% at 0.5% risk), because this account tests drawdown, not
expectancy. Keep those for a personal account with no external limits.
