# The Fibonacci retracement continuation strategy

This document turns a spoken description of a discretionary trade into a set of rules
precise enough that a machine can follow them without asking a question. It is written
for crypto on intraday bars, and it is the specification that `src/fib_engine.py`
implements. What the rules produced when tested is a separate matter, recorded in
`reports/FIB_FINDINGS.md`; this document is only concerned with what the rules are.

## The description it came from

The trader described a single trade. Price had made a low, marked by a candle with a
long wick. From there it rallied to a high. He drew a Fibonacci retracement across that
move, from the high down to the low, and placed his entry at the 0.5 level, which is
simply the midpoint of the move. He then held the position until price returned to the
high it had come from. He added four things about how he manages the strategy as a
whole: he never risks more than 1.5 percent on a trade, he takes profit at more than
three or four percent, he had two days with no trade at all followed by four trades in
quick succession, and two of those four were losses.

He also said one thing that is deliberately not reproduced here. He took the trade on a
gut feeling, and noted that his RSI was not oversold at the time, which means he entered
against his own filter. A discretionary override is not a rule, and a rule that can be
overridden is not a rule, so the version below has no override in it. Where RSI appears
it is a gate that refuses trades, and nothing can wave a trade past it.

## What had to be decided

Three things in that description were not precise enough to act on, and each had to be
settled before the strategy could be written down at all.

The first is what counts as "the last high". A person looking at a chart sees the high
as soon as price turns away from it. A program cannot: it can only call a bar a swing
high once some number of later bars have failed to exceed it, and until then the high is
provisional. This is not a small distinction. On the data tested, waiting for a
three-bar confirmation meant the 0.5 level had usually already been reached and passed
before the swing high was confirmed, so the trade was never available. The strategy
therefore carries both readings as a setting: `pivot`, which waits for confirmation and
is strict, and `running`, which treats the highest price since the swing low as the end
of the leg and is what a person watching the chart actually does. Neither is a cheat;
the running reading looks only at bars that have already closed. But they are different
strategies with different trade counts, and the difference belongs on the record.

The second is where the stop sits. The trader gave a percentage, not a place. He said
he allows up to 1.5 percent, which is a cap on risk rather than a description of
structure, so the default here is a stop exactly 1.5 percent from the entry price. The
alternatives, a stop beyond the swing low that started the move or beyond a deeper
retracement level such as 0.786, are both available, and both are subject to the same
1.5 percent cap: if the structural stop is wider than that, the trade is not taken at
all rather than taken with more risk than the rule allows.

The third is what "the next last high, all the way up there" means as a target. It may
mean the high the retracement came from, or an older and higher swing beyond it. Both
are implemented, as `swing` and `prior_high`, along with a Fibonacci extension as a
third option.

## The rules

A long trade and a short trade are mirror images, so the long is given in full and the
short follows by reversing every comparison.

1. Find the leg. Locate a confirmed swing low, meaning a bar whose low is lower than the
   three bars either side of it. From that low, identify the end of the upward move:
   either the next confirmed swing high, or, under the running reading, the highest
   price reached since the low, provided at least one bar has since failed to exceed it.

2. Check the leg is worth trading. The distance from low to high must be at least two
   times the current average true range. A move smaller than that is noise, and the
   retracement levels drawn across it are meaningless.

3. Draw the retracement and mark the entry. The entry level is the midpoint of the leg:
   the low plus half the distance to the high. The 0.382 and 0.618 levels are available
   as alternatives.

4. Wait. The level stays live for sixty bars. If price has not reached it by then, the
   setup is abandoned. If price makes a new high above the leg's high first, the leg has
   extended and the whole setup is redrawn from scratch. If price passed through the
   entry level before the leg was confirmed, the trade is not taken, because no order
   could have been resting there yet.

5. Enter when price trades at the level. The fill is the level itself, or the bar's open
   if the bar opened below it, but only if that open is within a quarter of an average
   true range of the level. A bar that opens further below than that has gapped, and the
   price at which an order would have filled is not something the data can show, so the
   trade is skipped rather than assumed.

6. Place the stop 1.5 percent below the entry.

7. Set the target at the high the leg came from, or at the next structural high above it.
   The trade is only taken if the target is more than three percent away from the entry
   after costs, and if that reward is at least one and a half times the risk. If either
   test fails, the setup is passed over.

8. Hold until one of three things happens: price reaches the target, price reaches the
   stop, or four hundred and eighty bars elapse, at which point the position is closed at
   the market. If a single bar covers both the stop and the target, the trade is recorded
   as a loss, because the order in which the two were touched inside that bar is not
   knowable from the data.

9. Hold one position at a time. A setup that appears while a trade is open is ignored
   rather than queued. This is the mechanical form of the patience the trader described:
   the strategy does not look for something to do.

Round-trip costs of ten basis points, covering exchange fees and slippage, are charged
against every trade.

## What the rules do not include

The wick the trader pointed to is not part of the rules. He used it to find the low, and
the swing-low definition above does the same job more precisely, so adding a separate
wick condition would be redundant rather than additive.

There is no moving-average filter by default, no higher-timeframe confirmation, no
trailing stop, no partial profit-taking and no break-even stop. Each of those is a real
technique, and none of them was in the description. Adding them would be designing a new
strategy rather than writing down this one, and every addition is another parameter that
can be tuned until the backtest looks good.

## Position sizing

The rules above describe one trade's shape, not how much money to put behind it. If the
stop is 1.5 percent from the entry and the intention is to lose one percent of the
account when it is hit, the position is worth two-thirds of the account, which on most
crypto venues means borrowing. That is a decision about leverage, with consequences such
as funding costs and liquidation prices that this document does not model and that the
backtest does not include. The results in `reports/FIB_FINDINGS.md` are quoted in R, the
multiple of whatever is risked on one trade, precisely so that they stay true whatever
sizing is chosen.

## Running it

    python3 -m pytest tests/test_fib_engine.py -q
    python3 src/run_fib.py --data data/btcusd_4h.csv
    python3 src/run_fib.py --data data/btcusd_4h.csv --high-mode running
    python3 src/run_fib.py --data data/btcusd_4h.csv --sweep

A single run prints the result and, importantly, a count of the setups it refused and
why. That count is usually more informative than the result itself: a strategy that
takes eleven trades in a year because it rejected six hundred candidates is telling you
something about its rules, not about the market.

The sweep runs every combination of the choices this document had to make and reports the
spread of outcomes. A result that appears at one setting and nowhere else is an artefact
of that setting.
