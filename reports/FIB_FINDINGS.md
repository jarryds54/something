# What the Fibonacci retracement strategy did when tested

The rules are in `FIB_STRATEGY.md`. This is what happened when they were run, and what
the result is and is not evidence for.

## The data, and why it limits the conclusions

Price history came from the Interactive Brokers feed for BTC on Paxos, which caps every
request at 3,500 bars. Three series were pulled: fifteen-minute bars covering one month,
hourly bars covering three months, and four-hour bars covering one year. The one-year
four-hour series is the only one long enough to say anything at all, and even that is a
single instrument over a single year, most of which was one market regime.

The feeds are not continuous. The four-hour series has forty-one holes, the largest
thirty-nine hours long. This matters more than it sounds. The first version of the
engine filled entries at the bar's open whenever the open was better than the entry
level, which is correct behaviour for a genuine gap but turns a hole in the feed into a
free, unverifiable fill. That version reported winners averaging five percent against
risk of three-quarters of a percent, which the geometry of a midpoint entry cannot
produce. The engine now refuses to trade a bar that follows a hole, and refuses a fill
more than a quarter of an average true range beyond the level. Those two guards removed
the result entirely, which is the correct outcome: it was never there.

## The strategy barely exists below four-hour bars

The most immediate finding is that the strategy, as described, has almost nothing to do
on intraday crypto bars. Over the full grid of 648 rule variations, the fifteen-minute
month produced sixteen trades in total and no single variation reached ten. The
three-month hourly series produced 733 trades across the whole grid, but only three
variations reached ten trades each.

The reason is arithmetic rather than market behaviour. Entering at the midpoint of a leg
and targeting the high that leg came from means the reward is exactly half the leg. For
that reward to clear the trader's three percent floor, the leg itself has to be at least
six percent of price. Bitcoin legs of that size do not form often inside a fifteen-minute
chart. The engine's refusal counts say this directly: on fifteen-minute bars the binding
constraint, once the profit floor is relaxed, becomes the reward-to-risk test, which
fails 320 times. The trader's own numbers, 1.5 percent of risk against three to four
percent of profit, describe a trade with a four-hour or daily rhythm, not a scalp.

## On four-hour bars, the answer depends on a definition

Two readings of "the last high" were tested. The strict reading waits for a swing high
to be confirmed by three later bars. The running reading takes the highest price since
the swing low, which is what a person watching a chart sees.

Under the strict reading the strategy took eleven trades in a year, won 18.2 percent of
them, and lost 4.3R. Under the running reading it took forty-seven trades, won 31.9
percent, and made 6.1R. The 95 percent confidence interval on the running version runs
from -0.361R to +0.650R per trade, which includes zero comfortably; the profit factor
was 1.18 and the worst drawdown 7.5R.

The gap between eleven trades and forty-seven is the whole story of the confirmation
lag. Under the strict reading, the single most common reason for refusing a setup was
that price had already passed through the 0.5 level before the swing high was confirmed:
608 times on the four-hour series, 1,191 times on fifteen-minute bars. The trader's eye
is not better than the program at finding the level. It is earlier, and on this strategy
earlier is most of the difference.

## The payoff is real; the win rate is the question

The running version's arithmetic is sound and worth stating plainly, because it is the
part the trader got right. Winners averaged 4.02 percent and losers 1.60 percent, so the
strategy needs to win 28.5 percent of its trades to break even. It won 31.9 percent. The
cushion is three and a half percentage points, on forty-seven trades, which is not enough
to distinguish from luck.

The cadence matched the description closely. The median gap between trades was 3.8 days
and the longest was 31 days; seventeen of forty-three weeks produced no trade at all and
the busiest produced five. The description of two quiet days followed by four trades in
a row is an accurate account of how this strategy behaves. So is the part that was not
mentioned: the longest run of consecutive losses was seven.

## Most readings of the rules lose money

The sweep ran every combination of the six choices the description left open: 648
configurations, of which 229 took at least ten trades on the four-hour series. The median
configuration lost 0.179R per trade, and 28 percent were profitable. The distribution is
in `fib_result.png`.

The configurations at the top of that list share a shape: a 0.618 entry rather than 0.5,
a fixed percentage stop, and the leg's own high as the target. The configurations at the
bottom share one too: a Fibonacci extension target, which several variations never reached
once, producing a zero percent win rate across ten or more trades. A target beyond the
structure is not a more ambitious version of this strategy, it is a different and worse
one.

The best single row in the sweep made 14.0R over ten trades. Split into halves, it made
12.3R in the first six months and lost 2.7R in the second. The base running
configuration tells the same story more gently: 35 trades and +7.1R in the first half,
11 trades and exactly break-even in the second. Trade counts across the two halves do
not sum to the full-year count, because each half is run with its own warm-up and its own
swing context. The direction is what matters, and the direction is that the result came
from one half of one year.

## What this is and is not evidence for

It is evidence that the rules, written down carefully, describe a coherent strategy with
a sensible risk-reward shape and a trade frequency that matches what the trader
described. It is evidence that the strategy belongs on four-hour bars rather than
intraday ones, and that it depends far more on how the swing high is identified than on
the Fibonacci level chosen.

It is not evidence that the strategy makes money. One instrument, one year, forty-seven
trades, a confidence interval spanning zero, a result concentrated in the first half, and
a sweep in which most variations lose. Any of those alone would call for more data.
Together they mean the honest summary is that the edge, if there is one, has not been
demonstrated here.

The next step that would actually settle it is more history, from a charting platform
export rather than a broker feed capped at 3,500 bars, across several instruments. The
engine takes any CSV with `time, open, high, low, close`, so that test costs nothing but
the data.
