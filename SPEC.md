# Wickless-Candle Retest — complete build specification

Hand this to an engineer or a model and they should be able to rebuild the backtest
and reproduce the reference numbers in section 12 exactly. It is written to be
self-contained: every rule, every parameter, every tie-break, and every trap already
discovered.

---

## 1. What the strategy is

Instrument: **XAUUSD (spot gold)**. Timeframe: **5-minute candles**, 24h, Sunday
evening to Friday evening.

In plain terms:

1. While price is trending, look for a candle with **no wick on the trend side** —
   in an uptrend a bullish candle whose **low equals its open**; in a downtrend a
   bearish candle whose **high equals its open**.
2. The open of that candle becomes a **level**.
3. If price **returns to that level within the next 7 candles**, enter in the
   direction of the trend with a limit order at the level.
4. The **stop** goes just beyond the most recent swing against the position.
5. The **target** sits at **1:1** — the same distance from entry as the stop.
6. Only trade when **volatility is above its recent median**.
7. **Stop trading for the day** once down 2R.

One position at a time. No pyramiding, no averaging, no hedging.

---

## 2. Data contract

Input is a CSV of 5-minute bars, ascending by time, columns:

    time, open, high, low, close, [tickvol], [spread]

- `time` — UTC, ISO 8601, timezone-aware.
- `spread` — optional, in MetaTrader **points**. For a 2-decimal gold feed,
  1 point = $0.01, so `spread = 15` means $0.15.
- The reference dataset was exported from MetaTrader 5 (FundingPips server,
  **UTC+3**, converted to UTC on load) and covers **2025-05-27 to 2026-10-23**,
  **100,000 bars**.

**Validation before anything else.** Reject the dataset if any bar has
`high < max(open, close)`, `low > min(open, close)`, `high < low`, any NaN in OHLC,
or if `time` is not strictly increasing. Malformed bars invent signals: an early
version of this work silently traded a candle whose low sat above its high.

**Price granularity matters.** "No wick" is a property of the quote precision, not
of price. On a 2-decimal feed it means "the wick is smaller than $0.01". On a feed
quoting 3 decimals, a tolerance of exactly 0 is a *stricter* rule than the one
tested, and will find a fraction of the setups. Set the wick tolerance to one tick
of whatever feed is used.

---

## 3. Parameters (the exact configuration that produced section 12)

| Parameter | Value | Meaning |
|---|---|---|
| `trend` | `"structure"` | trend definition, see 4.3 |
| `trend_len` | `20` | lookback for the trend test, in bars |
| `wick_tol` | `0.0` | dollars of wick still counted as "wickless" |
| `wait_bars` | `7` | level expires if untouched after this many bars |
| `min_wait_bars` | `1` | earliest bar after the signal an entry may happen |
| `stop_mode` | `"pivot"` | stop references a swing pivot |
| `pivot_k` | `2` | bars either side that define a pivot |
| `stop_lookback` | `20` | how far back a usable pivot may be |
| `buffer_atr` | `0.0` | extra room beyond the pivot, in ATR |
| `min_stop` | `5.0` | skip the setup if risk is below this, in dollars |
| `max_stop_atr` | `10.0` | skip the setup if risk exceeds this many ATR |
| `rr` | `1.0` | target distance as a multiple of risk |
| `atr_len` | `14` | ATR period (Wilder) |
| `atr_pct_min` | `0.40` | minimum volatility percentile to enter |
| `atr_pct_max` | `1.0` | maximum volatility percentile |
| `atr_rank_window` | `2000` | window for the volatility percentile |
| `tie_break` | `"stop"` | a bar hitting both stop and target counts as a loss |
| `max_hold` | `288` | abandon after this many bars (one day) |
| `allow_concurrent` | `false` | one position at a time |
| `use_bar_spread` | `true` | charge the spread recorded on the bar |
| `commission` | `0.07` | dollars per ounce, on top of the spread |
| `stop_slip` | `0.10` | dollars of adverse fill when a stop is hit |
| `point_size` | `0.01` | price move represented by one MT5 point |
| `daily_stop_r` | `2.0` | stop trading for the day after losing this much |
| `risk_pct` | `0.0075` | fraction of equity risked per trade (live layer) |

---

## 4. Indicators — exact definitions

All are computed over the whole series first; none may use information from a bar
later than the one being evaluated.

### 4.1 ATR (Wilder)

    prev_close = close.shift(1)
    tr  = max(high - low, |high - prev_close|, |low - prev_close|)
    atr = tr.ewm(alpha = 1/14, adjust = False).mean()

This is Wilder's smoothing (equivalently `ta.atr(14)` in Pine, or RMA). A simple
moving average of TR will give different numbers.

### 4.2 Volatility percentile — strictly backward-looking

    atr_pct = atr.rolling(2000, min_periods=200).rank(pct=True).shift(1)

The rank of the current ATR among the previous 2,000 bars, expressed 0–1, then
**shifted one bar** so the value used on bar *i* was knowable at the close of
bar *i−1*. Until 200 bars exist it is undefined and no entry may be taken.

A 500-bar window produces materially the same results and costs less warm-up; 2000
is what the reference numbers used.

### 4.3 Trend — "structure" mode

With `trend_len = 20`, let `half = max(2, trend_len // 2) = 10`:

    recent_high = highest high over the last 10 bars (inclusive of bar i)
    recent_low  = lowest  low  over the last 10 bars
    prior_high  = highest high over the 10 bars before those
    prior_low   = lowest  low  over the 10 bars before those

    uptrend   if recent_high > prior_high AND recent_low > prior_low
    downtrend if recent_high < prior_high AND recent_low < prior_low
    otherwise no trend

The first `trend_len + 1` bars have no trend by definition.

*(An alternative "displacement" mode — `close − close[trend_len]` exceeding
`trend_thresh × atr` — was also tested and performs slightly worse. See section 15.)*

### 4.4 Swing pivots

A **pivot low** at index *i* is a bar whose low equals the minimum low of the
window `[i − 2, i + 2]` (ties count). A **pivot high** is the mirror image.

A pivot at index *i* is **confirmed** only at bar `i + 2`, because the two bars to
its right must exist. Maintain, for each bar *j*, the index and price of the most
recent pivot low and pivot high confirmed by *j*:

    confirmed_pivot_index[j] = latest i such that i + 2 <= j and i is a pivot

---

## 5. Signal detection

On every bar *i*, with `wick_tol = 0`:

    bullish_wickless = close[i] > open[i] AND (open[i] - low[i])  <= wick_tol
    bearish_wickless = close[i] < open[i] AND (high[i] - open[i]) <= wick_tol

A **level** is created when the candle is wickless **on the trend side**:

- uptrend and `bullish_wickless` → level at `open[i]`, direction `+1`
- downtrend and `bearish_wickless` → level at `open[i]`, direction `−1`

No other combination creates a level. A single bar can create at most one level.

Roughly **5.8% of all bars** are exactly wickless in the reference data; after the
trend filter about **2,100 of 100,000 bars** produce a level.

---

## 6. Level lifecycle

Levels live in a queue in creation order. Each holds `(signal_index, price, direction)`.

- **Created** at the close of the signal bar. It cannot be entered on its own bar.
- **Eligible** from `signal_index + min_wait_bars` (so the next bar) through
  `signal_index + wait_bars` inclusive.
- **Expires** once `current_index − signal_index > wait_bars`, untouched.
- **Consumed** the moment it produces a filled trade. It must never fire twice.

> **Trap.** A trade that opens and closes inside the same candle must still consume
> its level. A platform implementation that only consumed levels while a position
> was *observed open* re-fired the same level six times in ten minutes.

---

## 7. Entry

On bar *i*, for each eligible level in creation order:

1. **Touch test** — long: `low[i] <= level`; short: `high[i] >= level`.
2. If not touched, the level survives to the next bar.
3. If touched but a position is already open (and `allow_concurrent` is false), the
   level survives — it is not consumed and may trigger later.
4. **Volatility gate** — if `atr_pct[i]` is undefined or outside
   `[atr_pct_min, atr_pct_max]`, skip; the level survives.
5. **Fill price** — a limit order fills at the level, or better if the bar opened
   beyond it:

       long:  fill = min(level, open[i])
       short: fill = max(level, open[i])

6. Compute the stop (section 8). If no usable pivot exists, the level survives.
7. If `risk < min_stop` or `risk > max_stop_atr × atr[i−1]`, **discard** the level.
8. Otherwise open the position and consume the level.

---

## 8. Stop and target

Using only bars **strictly before** the entry bar — specifically the pivot state as
of bar `i − 1`, and `atr[i − 1]`:

    long:  ref = price of the most recent confirmed pivot LOW  as of bar i-1
           stop = ref - buffer_atr * atr[i-1]
           risk = fill - stop
    short: ref = price of the most recent confirmed pivot HIGH as of bar i-1
           stop = ref + buffer_atr * atr[i-1]
           risk = stop - fill

The pivot is unusable if none exists or if `(i − 1) − pivot_index > stop_lookback`;
in that case no trade is taken.

    target = fill + rr * risk * direction

**Risk is measured from the fill, never from the level.** When a limit order fills
better than the level, measuring from the level quietly changes the reward-to-risk
ratio. A platform version that made this mistake produced a 36% win rate with a
profit factor of 1.45 — arithmetically impossible at 1:1, and the signature of a
much wider effective target.

---

## 9. Exit

The entry bar **is** checked for an exit. Evaluate on bar *j* (starting with the
entry bar) in this order:

    hit_stop   = low[j]  <= stop   (long)   |  high[j] >= stop   (short)
    hit_target = high[j] >= target (long)   |  low[j]  <= target (short)

    if hit_stop and hit_target:  exit at the STOP, reason "ambiguous_stop"
    elif hit_stop:               exit at the stop,   reason "stop"
    elif hit_target:             exit at the target, reason "target"
    elif j - entry_index >= max_hold: exit at close[j], reason "timeout"
    else: the position stays open

A single candle containing both the stop and the target is counted as a **loss**
because the intrabar order is unknowable. This affects 1.2% of trades and is
deliberately pessimistic.

When the exit reason is a stop (including the ambiguous case), apply slippage:

    exit_price -= stop_slip * direction

---

## 10. Costs

Bars are **bid** prices, so a long pays the spread on entry and a short pays it on
exit:

    spread_dollars = spread_points * point_size        (e.g. 15 * 0.01 = $0.15)
    bar_used = entry_index if direction == +1 else exit_index
    cost = spread_dollars[bar_used] + commission        (commission = $0.07/oz)

    gross_r = (exit_price - fill) * direction / risk
    r       = gross_r - cost / risk

In the reference data the median spread is **$0.15**, the mean **$0.18**, the 90th
percentile **$0.28**, and the realised cost averages **$0.24 per trade**, which is
**2.6% of risk**. If no spread column exists, use a flat **$0.30 round trip** and
expect slightly worse results.

---

## 11. Account layer (position sizing, daily stop, prop-firm limits)

Per trade:

    stake_dollars = equity * risk_pct          (risk_pct = 0.0075)
    position_size = stake_dollars / risk       (ounces; floor to the broker's step)

Daily loss stop:

    Reset the day's R counter at midnight BROKER time (UTC+3), not UTC.
    Once the day's realised R total is <= -2.0, take no further entries that day.
    Positions already open are NOT closed by this rule.

This exists because the worst single day in the reference data lost **5.26R**,
which at 0.6% risk is a 3.16% day against a 3% daily limit. The daily stop makes a
daily breach arithmetically impossible at sensible sizes. It does **not** improve
expectancy — the apparent improvement was confined to the training period.

Intraday equity modelling: with one position at a time and a hard stop, the
floating loss never exceeds 1R, so the worst point of any day is the running
realised total minus one stake.

---

## 12. Reference results — reproduce these exactly

Data: `xauusd_5m_fp.csv`, 100,000 bars, 2025-05-27 20:20 UTC to 2026-10-23 07:00 UTC.
Config: section 3.

```
trades            321
win_rate          0.5857          (188 targets, 128 stops, 4 ambiguous, 1 timeout)
mean_r            +0.14620
total_r           +46.93
profit_factor     1.3426
max_dd_r          -7.25
longs / shorts    159 / 162
avg_risk          $16.29
avg_bars_held     29.4
pct_ambiguous     0.0125
```

Split results (train = first 50% of bars, validate = next 25%, holdout = last 25%):

```
train      171 trades   win 0.5789   mean +0.1320R   total +22.57R
validate    68 trades   win 0.6029   mean +0.1796R   total +12.21R
holdout     80 trades   win 0.6000   mean +0.1774R   total +14.19R
```

Weekly distribution on a $50,000 account at 0.75% risk ($375 a trade), after the
daily stop: median week **+0.75R**, mean **+0.62R**, 48% of weeks negative, worst
week in the sample **−4.08R**, best **+5.84R**. Monthly mean **+2.50R**, 28% of
months negative.

---

## 13. Sample trades — unit-test against these

First eight trades, exactly as produced by the reference implementation. All times
UTC. `r` includes costs and stop slippage.

| signal | entry | dir | fill | stop | target | risk | bars to entry | exit | exit px | reason | cost | R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2025-05-28 16:45 | 2025-05-28 16:50 | −1 | 3291.65 | 3299.09 | 3284.21 | 7.44 | 1 | 2025-05-28 18:00 | 3299.19 | stop | 0.14 | −1.0323 |
| 2025-05-30 05:55 | 2025-05-30 06:10 | +1 | 3296.26 | 3290.19 | 3302.33 | 6.07 | 3 | 2025-05-30 07:10 | 3290.09 | stop | 0.14 | −1.0395 |
| 2025-05-30 16:55 | 2025-05-30 17:00 | +1 | 3291.71 | 3283.80 | 3299.62 | 7.91 | 1 | 2025-06-01 22:00 | 3299.62 | target | 0.14 | +0.9823 |
| 2025-06-05 05:50 | 2025-06-05 05:55 | −1 | 3363.41 | 3369.43 | 3357.39 | 6.02 | 1 | 2025-06-05 06:30 | 3369.53 | stop | 0.15 | −1.0415 |
| 2025-06-10 06:35 | 2025-06-10 06:55 | +1 | 3326.64 | 3309.42 | 3343.86 | 17.22 | 4 | 2025-06-10 13:20 | 3343.86 | target | 0.15 | +0.9913 |
| 2025-06-11 10:55 | 2025-06-11 11:05 | −1 | 3331.17 | 3336.99 | 3325.35 | 5.82 | 2 | 2025-06-11 12:15 | 3337.09 | stop | 0.15 | −1.0430 |
| 2025-06-12 02:30 | 2025-06-12 02:35 | +1 | 3374.09 | 3367.99 | 3380.19 | 6.10 | 1 | 2025-06-12 05:00 | 3367.89 | stop | 0.17 | −1.0443 |
| 2025-06-12 13:35 | 2025-06-12 13:50 | +1 | 3387.63 | 3379.31 | 3395.95 | 8.32 | 3 | 2025-06-12 15:10 | 3379.21 | stop | 0.15 | −1.0300 |

Read the arithmetic of row 1 as a worked example: a short filled at 3291.65 with the
most recent confirmed pivot high at 3299.09, so risk = $7.44 and the target sits
$7.44 below at 3284.21. The stop was hit; with 10c of slippage the exit is 3299.19,
a gross loss of $7.54, plus $0.14 of spread and commission, giving
−7.68 / 7.44 = **−1.0323R**.

Note that a losing trade is worse than −1.00R and a winner is less than +1.00R.
Any implementation producing exactly ±1.00R has forgotten costs or slippage.

---

## 14. Required tests

These are not optional; each one caught a real defect.

1. **No lookahead.** For every trade, re-run the engine on data truncated
   immediately after that trade's exit bar. The trade's entry, stop, target, exit
   and R must be identical. Run it across several parameter combinations.
2. **Malformed bars rejected** — a bar with low above high must raise, not trade.
3. **Wickless detection** — exact equality, and the tolerance behaving as specified.
4. **Level expiry** — a retest arriving on bar `signal + 8` with `wait_bars = 7`
   must not trade; on bar `signal + 7` it must.
5. **Ambiguous bar** — a candle spanning both stop and target yields exactly
   −1R before costs, never a win.
6. **Costs charged once** per round trip, and scaling with the spread.
7. **Entry-bar exits** — a trade whose target is reached on its entry candle must
   exit there. In the reference data **21% of trades resolve on their entry
   candle**, two thirds of them winners; losing those drags the win rate from
   57% to 54%.
8. **Level consumed exactly once**, including the same-candle open-and-close case.
9. **Daily stop** — after −2R, no further entries that day; a new broker day resets it.

---

## 15. Ideas already tested and rejected

Do not re-add these; each was tested on train and validate with the holdout reserved.

| Idea | Result |
|---|---|
| **Breakeven stop** at 0.3R / 0.5R / 0.75R / 1.0R | **Worse at every level.** Scratched trades cost more than the saved losses. |
| **Time stops** at 12 / 24 / 48 / 96 bars | Worse at every level; the longer the leash the better. |
| **Trailing from 0R, 0.5R or 1R** | Negative on train; strangles winners. |
| Trailing 2×ATR from 2–3R | Genuinely better per trade (+0.18R) but halves the win rate to 33% and doubles drawdown. Good for personal capital, bad for a prop evaluation. |
| Hour-of-day and session filters | Overfit; reversed out of sample. |
| **Requiring a "clean" trend** (efficiency ratio ≥ 0.3–0.5) | Big gains on train and validate, **zero to negative on holdout**. Classic overfitting gradient. |
| Minimum stop above $5 ($8, $12) | Better in-sample, negative on holdout. |
| Minimum wait of 3+ bars before the retest | Subgroup analysis suggested it; failed when tested. |
| Requiring an imbalance (fair value gap) | Looked strong, only ~31 validation trades. Unproven. |
| Stacking several filters together | Collapsed to 11 validation trades and lost money. |
| Wick tolerance above zero | Destroys the edge. This is the single most important parameter. |
| Removing the volatility filter | Destroys the edge. |

---

## 16. Honest caveats to carry forward

- Roughly **130 variations** were tested to arrive at this configuration. The
  out-of-sample checks guard the headline number but do not eliminate selection
  bias. **Expect live results below the backtest.**
- The edge is about **+0.15R per trade over 19 trades a month**. It is a grind:
  28% of months lose money, 48% of weeks lose money, and losing runs of six or
  more trades are normal.
- The holdout has been opened more than once across this work, which weakens it.
- One instrument, one 17-month period containing an exceptional gold rally and
  reversal (3,300 → 5,598 → 4,000).
- Entries assume a limit order filling at the level. Real fill rates are unknown
  and this is the most likely place live results fall short.
- The trend rule is a mechanical proxy for a human judgement. It marks some setups
  a discretionary trader would reject, and tightening it to match that judgement
  made out-of-sample results worse, not better.

---

## 17. Reproducing the reference implementation

A working Python implementation exists at
`github.com/jarryds54/something`, branch `claude/gifted-feynman-aqowzh`:

    src/engine.py          rules and trade simulation
    src/engine_fast.py     vectorised trend / signal / pivot precomputation
    src/metrics.py         statistics and bootstrap confidence intervals
    src/funded.py          prop-firm evaluation simulator
    src/load_mt5.py        MetaTrader export loader
    tests/                 the test suite described in section 14
    pine/                  TradingView implementation
    reports/FINDINGS.md    how every number above was arrived at

**The reference numbers in section 12 are specific to that exact CSV.** A different
broker's feed will find different wickless candles and produce different results;
that is expected, not a bug. To verify a new implementation, run it against the same
file and match section 13 trade for trade.
