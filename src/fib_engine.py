"""Backtest engine for the Fibonacci retracement continuation strategy (crypto, intraday).

The strategy as described by the trader:

  - a move runs from a swing low up to a swing high
  - draw a Fibonacci retracement across that leg (high to low; the levels are the
    same either way, since 0.5 is simply the midpoint)
  - enter when price pulls back to the 0.5 level
  - target the high the leg came from
  - risk never more than 1.5% of price on a single trade
  - take profit at more than 3-4%
  - sit out when there is no setup, even for days at a time

Every part of that description which was a judgement call rather than a rule is a
parameter here, so the sweep can show how much of any result depends on the choice.
The trader's one openly discretionary act -- entering on a "gut feeling" while the
RSI reading did not support it -- is deliberately not reproducible: the RSI filter
is a hard gate when enabled, and nothing can override it.

Shorts are the exact mirror: a leg down from a swing high to a swing low, entered
on a bounce back up to the 0.5 level.
"""
import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import validate_bars  # noqa: E402
from engine_fast import last_pivot_arrays  # noqa: E402


@dataclass
class Params:
    # --- swing structure: what counts as the "last high" and "that low" ---
    pivot_k: int = 3            # bars either side that confirm a swing pivot
    high_mode: str = "pivot"    # how the end of the leg is identified:
                                #   pivot   -- a confirmed swing, known k bars late
                                #   running -- the highest high since the swing low,
                                #              known at once, which is what a trader
                                #              watching the chart actually uses
    high_age_min: int = 1       # running mode: the extreme must be this many bars old,
                                # so the leg has visibly turned before it is traded
    leg_min_atr: float = 2.0    # the leg must be this big to count as a real move
    leg_min_pct: float = 0.0    # alternative size floor, in percent of price
    leg_max_bars: int = 120     # ignore legs whose high was confirmed longer ago

    # --- entry ---
    fib_entry: float = 0.500    # 0.382 | 0.500 | 0.618
    wait_bars: int = 60         # the level expires if untouched after this long
    min_wait_bars: int = 1      # ignore a touch on the signal bar itself

    # --- stop ---
    stop_mode: str = "pct"      # pct | swing | fib
    stop_fib: float = 0.786     # fib mode: the deeper level the stop sits beyond
    stop_buffer_atr: float = 0.25   # the bit of space beyond the structure
    stop_pct: float = 1.5       # pct mode: stop this far from entry, in percent
    max_stop_pct: float = 1.5   # the trader's hard risk cap; wider setups are skipped
    min_stop_pct: float = 0.10  # below this the stop is inside the noise

    # --- target ---
    target_mode: str = "swing"  # swing (the leg's high) | prior_high (the next
                                #   structural high beyond it) | ext (a fib extension)
    target_ext: float = 1.272   # ext mode only, measured on the retraced leg
    min_target_pct: float = 3.0 # the trader's "more than 3-4%" profit rule
    min_rr: float = 1.5         # skip a setup whose reward does not justify the risk

    # --- filters ---
    trend: str = "none"         # none | ema
    trend_len: int = 50
    rsi_len: int = 14
    rsi_long_max: float = 100.0 # longs need RSI at or below this (100 disables)
    rsi_short_min: float = 0.0  # shorts need RSI at or above this (0 disables)
    allow_long: bool = True
    allow_short: bool = True

    # --- execution ---
    cost_bps: float = 10.0      # round-trip fees plus slippage, in basis points
    max_gap_atr: float = 0.25   # a bar opening further than this beyond the level is a
                                # gap: a resting limit would have filled at a price the
                                # feed does not contain, so the setup is skipped
    skip_gap_bars: bool = True  # refuse to trade a bar that follows a hole in the feed
    tie_break: str = "stop"     # a bar spanning both levels resolves to this one
    max_hold: int = 480         # abandon a trade that has not resolved
    atr_len: int = 14


def add_indicators(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Everything here looks strictly backwards; no column sees its own bar's future."""
    out = df.copy()
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.ewm(alpha=1 / p.atr_len, adjust=False).mean()
    out["ema"] = out["close"].ewm(span=p.trend_len, adjust=False).mean()

    delta = out["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / p.rsi_len, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / p.rsi_len, adjust=False).mean()
    rs = gain / loss.replace(0.0, np.nan)
    out["rsi"] = (100 - 100 / (1 + rs)).fillna(50.0)
    return out


def trend_series(d: pd.DataFrame, p: Params) -> np.ndarray:
    """+1 / -1 / 0 per bar. 0 means the filter is off or undecided."""
    n = len(d)
    side = np.zeros(n, dtype=np.int8)
    if p.trend == "none":
        return side
    if p.trend != "ema":
        raise ValueError(f"unknown trend mode {p.trend}")
    k = p.trend_len
    close, ema = d["close"].to_numpy(), d["ema"].to_numpy()
    prev_ema = np.concatenate([np.full(k, np.nan), ema[:-k]])
    with np.errstate(invalid="ignore"):
        side[(close > ema) & (ema > prev_ema)] = 1
        side[(close < ema) & (ema < prev_ema)] = -1
    side[: k + 1] = 0
    return side


def fib_level(high: float, low: float, frac: float, direction: int) -> float:
    """The retracement level `frac` of the way back into a leg.

    A long retraces down from the high, a short retraces up from the low, so the
    same fraction is measured from opposite ends of the same leg.
    """
    span = high - low
    return high - frac * span if direction == 1 else low + frac * span


def _setup(i: int, direction: int, piv_lo_idx, piv_hi_idx, low_arr, high_arr,
           hi, lo, atr, p: Params):
    """The live setup at bar i, judged only on pivots already confirmed by bar i.

    Returns either (leg_low, leg_high, anchor_i, entry_level) and the reason "ok", or
    None and a short reason the setup does not exist. `anchor_i` is the bar at which
    the leg became known, which is what the wait window is measured from.
    """
    jl, jh = piv_lo_idx[i], piv_hi_idx[i]
    if p.high_mode == "running":
        # The start of the leg is a confirmed swing; its end is simply the furthest
        # price has travelled since, which needs no confirmation lag.
        start = jl if direction == 1 else jh
        if start < 0 or start + p.high_age_min >= i:
            return None, "no_pivots_yet"
        window = slice(start, i - p.high_age_min + 1)
        if direction == 1:
            jh = start + int(np.argmax(hi[window]))
            jl = start
        else:
            jl = start + int(np.argmin(lo[window]))
            jh = start
        if (jh if direction == 1 else jl) == start:
            return None, "leg_has_not_turned"
    elif p.high_mode != "pivot":
        raise ValueError(f"unknown high mode {p.high_mode}")
    if jl < 0 or jh < 0:
        return None, "no_pivots_yet"
    # a long needs the low first and the high second: an upward impulse
    if direction == 1 and not jl < jh:
        return None, "wrong_pivot_order"
    if direction == -1 and not jh < jl:
        return None, "wrong_pivot_order"

    leg_low, leg_high = (lo[jl], hi[jh]) if p.high_mode == "running" else \
                        (low_arr[jl], high_arr[jh])
    span = leg_high - leg_low
    if span <= 0:
        return None, "degenerate_leg"
    if atr > 0 and p.leg_min_atr and span < p.leg_min_atr * atr:
        return None, "leg_too_small"
    if p.leg_min_pct and span < p.leg_min_pct / 100.0 * leg_high:
        return None, "leg_too_small"

    # the leg is only known once its second pivot is confirmed, k bars after it formed
    second = max(jl, jh)
    anchor_i = second + (0 if p.high_mode == "running" else p.pivot_k)
    if i - anchor_i > p.wait_bars:
        return None, "level_expired"
    if i - anchor_i < p.min_wait_bars:
        return None, "not_yet_confirmed"
    if i - second > p.leg_max_bars:
        return None, "leg_too_old"

    level = fib_level(leg_high, leg_low, p.fib_entry, direction)

    # if price has already run past the end of the leg, the leg is stale: the next
    # pivot will redefine it, and until then there is no retracement to trade
    if second + 1 < i:
        window = slice(second + 1, i)
        if direction == 1 and hi[window].max() > leg_high:
            return None, "leg_extended"
        if direction == -1 and lo[window].min() < leg_low:
            return None, "leg_extended"
        # and if the retracement went through the level before the leg was confirmed,
        # the trade was never available: no order could have been resting there yet
        if direction == 1 and lo[window].min() <= level:
            return None, "level_already_passed"
        if direction == -1 and hi[window].max() >= level:
            return None, "level_already_passed"

    return (leg_low, leg_high, anchor_i, level), "ok"


def _pivot_flags(d: pd.DataFrame, k: int):
    """Which bars are swing pivots. A pivot at j is only confirmed at bar j + k."""
    n = len(d)
    low, high = d["low"].to_numpy(), d["high"].to_numpy()
    is_low = np.zeros(n, dtype=bool)
    is_high = np.zeros(n, dtype=bool)
    if k >= 1 and n > 2 * k:
        roll_min = pd.Series(low).rolling(2 * k + 1, center=True).min().to_numpy()
        roll_max = pd.Series(high).rolling(2 * k + 1, center=True).max().to_numpy()
        is_low[k:-k] = low[k:-k] == roll_min[k:-k]
        is_high[k:-k] = high[k:-k] == roll_max[k:-k]
    return is_low, is_high


def _next_structural_level(is_pivot, values, before_i: int, confirmed_by: int,
                           beyond: float, direction: int, k: int):
    """The nearest confirmed pivot beyond `beyond`: the trader's "next last high".

    For a long, the closest swing high above the leg's own high; for a short, the
    closest swing low below the leg's low. Only pivots already confirmed at bar
    `confirmed_by` are eligible.
    """
    best = None
    for j in range(min(before_i, confirmed_by - k), -1, -1):
        if not is_pivot[j]:
            continue
        v = values[j]
        if direction == 1 and v > beyond and (best is None or v < best):
            best = v
        if direction == -1 and v < beyond and (best is None or v > best):
            best = v
    return best


def _gap_flags(d: pd.DataFrame) -> np.ndarray:
    """Which bars follow a hole in the feed?

    An exchange outage or an aggregated feed leaves missing bars behind. Price can
    move a long way inside one, and a backtest that treats the bar after it as
    ordinary will book entries at prices nobody could have been filled at.
    """
    n = len(d)
    flags = np.zeros(n, dtype=bool)
    if n < 3:
        return flags
    step = d["time"].diff().dt.total_seconds().to_numpy()
    typical = np.nanmedian(step[1:])
    if not np.isfinite(typical) or typical <= 0:
        return flags
    flags[1:] = step[1:] > typical * 1.5
    return flags


def simulate(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Walk the bars once. One position at a time, and no bar ever sees its own future."""
    d = add_indicators(validate_bars(df), p)
    n = len(d)
    o = d["open"].to_numpy()
    hi = d["high"].to_numpy()
    lo = d["low"].to_numpy()
    atr_arr = d["atr"].to_numpy()
    rsi_arr = d["rsi"].to_numpy()
    times = d["time"].to_numpy()

    side = trend_series(d, p)
    piv_lo_idx, piv_hi_idx, low_arr, high_arr = last_pivot_arrays(d, p.pivot_k)
    after_gap = _gap_flags(d) if p.skip_gap_bars else np.zeros(n, dtype=bool)

    trades = []
    open_trade = None
    is_piv_lo, is_piv_hi = _pivot_flags(d, p.pivot_k)
    skipped = {"after_gap": 0, "level_already_passed": 0, "leg_extended": 0,
               "leg_has_not_turned": 0,
               "level_expired": 0, "unverifiable_fill": 0, "no_structural_target": 0,
               "stop_too_wide": 0, "stop_too_tight": 0, "target_too_small": 0,
               "reward_risk_too_low": 0}

    def close_out(t, i):
        hit_stop = lo[i] <= t["stop"] if t["dir"] == 1 else hi[i] >= t["stop"]
        hit_target = hi[i] >= t["target"] if t["dir"] == 1 else lo[i] <= t["target"]
        if hit_stop and hit_target:
            # the order within the bar is unknowable, so assume the worse one
            price = t["stop"] if p.tie_break == "stop" else t["target"]
            reason = "ambiguous_" + p.tie_break
        elif hit_stop:
            price, reason = t["stop"], "stop"
        elif hit_target:
            price, reason = t["target"], "target"
        elif i - t["entry_i"] >= p.max_hold:
            price, reason = d["close"].iat[i], "timeout"
        else:
            return None
        gross = (price - t["entry"]) * t["dir"]
        t.update(exit_i=i, exit_time=times[i], exit=price, reason=reason,
                 cost=t["cost"], pnl=gross - t["cost"],
                 r=(gross - t["cost"]) / t["risk"],
                 pct=(gross - t["cost"]) / t["entry"] * 100.0)
        return t

    for i in range(n):
        if open_trade is not None:
            done = close_out(open_trade, i)
            if done is not None:
                trades.append(done)
                open_trade = None
            continue  # one position at a time: no new entry on an occupied bar

        if i < 2 or not np.isfinite(atr_arr[i - 1]):
            continue
        if after_gap[i]:
            skipped["after_gap"] += 1
            continue
        atr = atr_arr[i - 1]          # the previous bar's ATR: this bar is still forming

        for direction in (1, -1):
            if direction == 1 and not p.allow_long:
                continue
            if direction == -1 and not p.allow_short:
                continue
            if p.trend != "none" and side[i - 1] != direction:
                continue
            if direction == 1 and rsi_arr[i - 1] > p.rsi_long_max:
                continue
            if direction == -1 and rsi_arr[i - 1] < p.rsi_short_min:
                continue

            found, why = _setup(i, direction, piv_lo_idx, piv_hi_idx, low_arr,
                                high_arr, hi, lo, atr, p)
            if found is None:
                if why in skipped:
                    skipped[why] += 1
                continue
            leg_low, leg_high, anchor_i, level = found
            # search for an older structural level strictly before this leg
            leg_start = piv_lo_idx[i] if direction == 1 else piv_hi_idx[i]
            jl_jh = (leg_start, leg_start)

            touched = lo[i] <= level if direction == 1 else hi[i] >= level
            if not touched:
                continue
            # a resting limit order fills at the level, or better if the bar opened past
            # it -- but only by a plausible amount. A bar that opens far beyond the level
            # means the fill happened somewhere the feed cannot show us.
            overshoot = (level - o[i]) * direction
            if overshoot > p.max_gap_atr * atr:
                skipped["unverifiable_fill"] += 1
                continue
            fill = min(level, o[i]) if direction == 1 else max(level, o[i])

            if p.stop_mode == "swing":
                ref = leg_low if direction == 1 else leg_high
                stop = ref - p.stop_buffer_atr * atr * direction
            elif p.stop_mode == "fib":
                ref = fib_level(leg_high, leg_low, p.stop_fib, direction)
                stop = ref - p.stop_buffer_atr * atr * direction
            elif p.stop_mode == "pct":
                stop = fill * (1 - p.stop_pct / 100.0 * direction)
            else:
                raise ValueError(f"unknown stop mode {p.stop_mode}")

            risk = (fill - stop) * direction
            if not np.isfinite(risk) or risk <= 0:
                continue
            stop_pct = risk / fill * 100.0
            # a hair of tolerance, so a stop set to exactly the cap is not rejected
            # by floating-point noise
            if stop_pct > p.max_stop_pct + 1e-9:
                skipped["stop_too_wide"] += 1
                continue
            if stop_pct < p.min_stop_pct - 1e-9:
                skipped["stop_too_tight"] += 1
                continue

            if p.target_mode == "swing":
                target = leg_high if direction == 1 else leg_low
            elif p.target_mode == "prior_high":
                # "the next last high, all the way up there": the nearest earlier
                # swing beyond the leg's own extreme
                flags = is_piv_hi if direction == 1 else is_piv_lo
                vals = high_arr if direction == 1 else low_arr
                beyond = leg_high if direction == 1 else leg_low
                target = _next_structural_level(flags, vals, min(jl_jh), i, beyond,
                                                direction, p.pivot_k)
                if target is None:
                    skipped["no_structural_target"] += 1
                    continue
            elif p.target_mode == "ext":
                target = fib_level(leg_high, leg_low, 1.0 - p.target_ext, direction)
            else:
                raise ValueError(f"unknown target mode {p.target_mode}")

            reward = (target - fill) * direction
            if reward <= 0:
                continue
            cost = fill * p.cost_bps / 1e4
            if (reward - cost) / fill * 100.0 < p.min_target_pct:
                skipped["target_too_small"] += 1
                continue
            if (reward - cost) / risk < p.min_rr:
                skipped["reward_risk_too_low"] += 1
                continue

            open_trade = {
                "signal_time": times[anchor_i],
                "entry_time": times[i],
                "entry_i": i,
                "dir": direction,
                "entry": fill,
                "stop": stop,
                "target": target,
                "risk": risk,
                "cost": cost,
                "stop_pct": stop_pct,
                "target_pct": reward / fill * 100.0,
                "leg_low": leg_low,
                "leg_high": leg_high,
                "bars_to_entry": i - anchor_i,
                "atr": atr,
                "rsi": rsi_arr[i - 1],
            }
            done = close_out(open_trade, i)
            if done is not None:
                trades.append(done)
                open_trade = None
            break  # a bar cannot open two positions

    out = pd.DataFrame(trades)
    out.attrs["skipped"] = skipped   # why candidate entries were refused
    return out
