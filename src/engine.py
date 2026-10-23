"""Backtest engine for the wickless-candle retest strategy on XAUUSD 5m.

The rules as described:
  - in a trend, find a candle with no wick on the trend side
      (uptrend: bullish candle whose low equals its open)
  - mark that open as a level
  - if price returns to the level within a few candles, enter in the trend direction
  - stop beyond the most recent swing against you, target at 1:1

Everything the description left to judgement (what counts as a trend, which swing
the stop references, how much room it gets) is a parameter here, so the sweep can
show how much the result depends on those choices.
"""
from dataclasses import dataclass, asdict, field

import numpy as np
import pandas as pd

from engine_fast import (fvg_flags, htf_trend_series, last_pivot_arrays,
                         trend_series, wickless_flags)


@dataclass
class Params:
    # --- trend filter ---
    trend: str = "ema"          # none | ema | slope | structure
    trend_len: int = 20         # lookback for whichever trend test is used
    trend_thresh: float = 1.0   # slope mode: required move over the lookback, in ATR

    # --- signal ---
    wick_tol: float = 0.0       # how many dollars of wick still counts as "wickless"
    body_min_atr: float = 0.0   # optional minimum body size, in ATR

    # --- entry ---
    wait_bars: int = 10         # level expires if untouched after this many candles
    min_wait_bars: int = 1      # ignore retests that arrive sooner than this

    # --- stop ---
    stop_mode: str = "pivot"    # pivot | bars | atr
    pivot_k: int = 2            # bars either side that define a swing pivot
    stop_lookback: int = 20     # how far back to search for the swing
    atr_mult: float = 1.5       # atr mode only
    buffer_atr: float = 0.10    # the "little bit of space" beyond the swing
    min_stop: float = 0.50      # dollars; below this the trade is skipped
    max_stop_atr: float = 10.0  # skip absurdly wide stops

    # --- exit and costs ---
    rr: float = 1.0
    cost: float = 0.30          # flat round-trip cost in dollars per ounce
    use_bar_spread: bool = False  # charge the spread recorded on the bar instead
    commission: float = 0.07    # dollars per ounce, charged on top of a real spread
    spread_mult: float = 1.0    # stress factor on the recorded spread
    point_size: float = 0.01    # price move represented by one MT5 point
    stop_slip: float = 0.0      # dollars of adverse fill when a stop is hit

    # --- trade management (all off by default) ---
    be_trigger_r: float = 0.0   # move the stop to breakeven once this much is open
    be_offset_r: float = 0.0    # park it this far beyond entry, in R
    trail_mode: str = "none"    # none | atr | structure
    trail_start_r: float = 0.0  # only start trailing once this much is open
    trail_atr_mult: float = 2.0
    partial_r: float = 0.0      # take part of the position off here
    partial_frac: float = 0.0   # what share to take off
    time_stop_bars: int = 0     # abandon a trade that has gone nowhere
    tie_break: str = "stop"     # which fills first when one bar spans both
    max_hold: int = 288         # give up after a day of 5m bars
    allow_concurrent: bool = False

    atr_len: int = 14

    # --- optional context filters (None disables) ---
    hours_allowed: tuple = ()   # UTC hours in which an entry may be taken
    atr_pct_min: float = 0.0    # causal percentile rank of ATR, 0-1
    atr_pct_max: float = 1.0
    atr_rank_window: int = 2000
    require_fvg: bool = False   # the candle must leave an unfilled gap behind it
    htf_trend: str = "none"     # none | ema | structure, judged on htf_minutes bars
    htf_minutes: int = 60
    htf_len: int = 20


def validate_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Reject impossible candles; a feed with bad bars produces fictional signals."""
    required = {"time", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    bad = (
        (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
        | (df["high"] < df["low"])
        | df[["open", "high", "low", "close"]].isna().any(axis=1)
    )
    if bad.any():
        raise ValueError(f"{int(bad.sum())} malformed bars, first at index {int(bad.idxmax())}")
    if not df["time"].is_monotonic_increasing:
        raise ValueError("bars are not in chronological order")
    return df


def add_indicators(df: pd.DataFrame, p: Params) -> pd.DataFrame:
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
    # where does current volatility sit against the recent past? strictly backward-looking
    out["atr_pct"] = (
        out["atr"].rolling(p.atr_rank_window, min_periods=200)
        .rank(pct=True)
        .shift(1)
    )
    return out


def trend_side(df: pd.DataFrame, i: int, p: Params) -> int:
    """+1 uptrend, -1 downtrend, 0 no trend, judged using bars up to and including i."""
    if p.trend == "none":
        return 0  # caller treats 0 as "either direction allowed"
    n = p.trend_len
    if i < n + 1:
        return 0

    if p.trend == "ema":
        ema_now, ema_then = df["ema"].iat[i], df["ema"].iat[i - n]
        if df["close"].iat[i] > ema_now and ema_now > ema_then:
            return 1
        if df["close"].iat[i] < ema_now and ema_now < ema_then:
            return -1
        return 0

    if p.trend == "slope":
        move = df["close"].iat[i] - df["close"].iat[i - n]
        atr = df["atr"].iat[i]
        if atr <= 0:
            return 0
        if move > p.trend_thresh * atr:
            return 1
        if move < -p.trend_thresh * atr:
            return -1
        return 0

    if p.trend == "structure":
        half = max(2, n // 2)
        recent_hi = df["high"].iloc[i - half + 1 : i + 1].max()
        prior_hi = df["high"].iloc[i - n + 1 : i - half + 1].max()
        recent_lo = df["low"].iloc[i - half + 1 : i + 1].min()
        prior_lo = df["low"].iloc[i - n + 1 : i - half + 1].min()
        if recent_hi > prior_hi and recent_lo > prior_lo:
            return 1
        if recent_hi < prior_hi and recent_lo < prior_lo:
            return -1
        return 0

    raise ValueError(f"unknown trend mode {p.trend}")


def is_wickless(df: pd.DataFrame, i: int, direction: int, p: Params) -> bool:
    o, h, l, c = (df[k].iat[i] for k in ("open", "high", "low", "close"))
    atr = df["atr"].iat[i]
    if p.body_min_atr and (atr <= 0 or abs(c - o) < p.body_min_atr * atr):
        return False
    if direction == 1:
        return c > o and (o - l) <= p.wick_tol
    return c < o and (h - o) <= p.wick_tol


def _recent_pivot(df: pd.DataFrame, upto: int, direction: int, p: Params):
    """Most recent swing confirmed by bar `upto` (a pivot needs pivot_k bars after it)."""
    k = p.pivot_k
    lo = max(k, upto - p.stop_lookback)
    for idx in range(upto - k, lo - 1, -1):
        if direction == 1:
            v = df["low"].iat[idx]
            left = df["low"].iloc[idx - k : idx]
            right = df["low"].iloc[idx + 1 : idx + k + 1]
            if len(left) == k and len(right) == k and (left > v).all() and (right > v).all():
                return v
        else:
            v = df["high"].iat[idx]
            left = df["high"].iloc[idx - k : idx]
            right = df["high"].iloc[idx + 1 : idx + k + 1]
            if len(left) == k and len(right) == k and (left < v).all() and (right < v).all():
                return v
    return None


def stop_reference(df: pd.DataFrame, entry_i: int, direction: int, p: Params):
    """Structure level the stop sits beyond, using only bars strictly before entry."""
    upto = entry_i - 1
    if upto < 1:
        return None
    if p.stop_mode == "pivot":
        return _recent_pivot(df, upto, direction, p)
    if p.stop_mode == "bars":
        lo = max(0, upto - p.stop_lookback + 1)
        window = df.iloc[lo : upto + 1]
        return window["low"].min() if direction == 1 else window["high"].max()
    if p.stop_mode == "atr":
        return None  # handled by caller, distance-based rather than structural
    raise ValueError(f"unknown stop mode {p.stop_mode}")


def _try_exit(t: dict, d: pd.DataFrame, i: int, p: Params):
    """Close `t` on bar i if it is resolved there. Returns the finished trade or None."""
    hi, lo = d["high"].iat[i], d["low"].iat[i]
    hit_stop = lo <= t["stop"] if t["dir"] == 1 else hi >= t["stop"]
    hit_target = hi >= t["target"] if t["dir"] == 1 else lo <= t["target"]
    if hit_stop and hit_target:
        # one bar spanning both: we cannot know the order, so assume the worse case
        exit_price = t["stop"] if p.tie_break == "stop" else t["target"]
        reason = "ambiguous_" + p.tie_break
    elif hit_stop:
        exit_price, reason = t["stop"], "stop"
    elif hit_target:
        exit_price, reason = t["target"], "target"
    elif i - t["entry_i"] >= p.max_hold:
        exit_price, reason = d["close"].iat[i], "timeout"
    else:
        return None
    gross = (exit_price - t["entry"]) * t["dir"]
    t.update(
        exit_i=i,
        exit_time=d["time"].iat[i],
        exit=exit_price,
        reason=reason,
        pnl=gross - p.cost,
        r=(gross - p.cost) / t["risk"],
    )
    return t


def simulate(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Walk the bars once, opening and closing trades. No bar ever sees its own future."""
    d = add_indicators(validate_bars(df), p)
    n = len(d)
    o = d["open"].to_numpy()
    hi = d["high"].to_numpy()
    lo = d["low"].to_numpy()
    atr_arr = d["atr"].to_numpy()
    atr_pct = d["atr_pct"].to_numpy()
    times = d["time"].to_numpy()
    hours = d["time"].dt.hour.to_numpy()
    if p.use_bar_spread:
        if "spread" not in d.columns:
            raise ValueError("use_bar_spread needs a 'spread' column of MT5 points")
        spread_px = d["spread"].to_numpy() * p.point_size * p.spread_mult
    hours_allowed = set(p.hours_allowed)

    side = trend_series(d, p)
    htf = htf_trend_series(d, p)
    bull, bear = wickless_flags(d, p)
    fvg_bull, fvg_bear = fvg_flags(d)
    piv_lo_idx, piv_hi_idx, low_arr, high_arr = last_pivot_arrays(d, p.pivot_k)
    roll_low = d["low"].rolling(p.stop_lookback, min_periods=1).min().to_numpy()
    roll_high = d["high"].rolling(p.stop_lookback, min_periods=1).max().to_numpy()

    pending = []
    trades = []
    open_trade = None

    def trade_cost(t, exit_i):
        """Bars are bid prices: a long pays the spread entering, a short exiting."""
        if not p.use_bar_spread:
            return p.cost
        bar = t["entry_i"] if t["dir"] == 1 else exit_i
        return float(spread_px[bar]) + p.commission

    def manage(t, i):
        """Update a live trade's stop using bars up to and including i."""
        open_r = ((hi[i] - t["entry"]) if t["dir"] == 1 else (t["entry"] - lo[i])) / t["risk"]
        t["peak_r"] = max(t.get("peak_r", 0.0), open_r)

        if p.be_trigger_r and not t.get("be_done") and t["peak_r"] >= p.be_trigger_r:
            level = t["entry"] + p.be_offset_r * t["risk"] * t["dir"]
            better = level > t["stop"] if t["dir"] == 1 else level < t["stop"]
            if better:
                t["stop"] = level
            t["be_done"] = True

        if p.trail_mode != "none" and t["peak_r"] >= p.trail_start_r:
            if p.trail_mode == "atr":
                ref = (hi[i] - p.trail_atr_mult * atr_arr[i]) if t["dir"] == 1 else \
                      (lo[i] + p.trail_atr_mult * atr_arr[i])
            else:  # structure: the most recent confirmed swing behind price
                pidx = (piv_lo_idx if t["dir"] == 1 else piv_hi_idx)[i]
                if pidx < 0:
                    return
                ref = (low_arr if t["dir"] == 1 else high_arr)[pidx]
            better = ref > t["stop"] if t["dir"] == 1 else ref < t["stop"]
            if better:
                t["stop"] = ref

    def close_out(t, i):
        h_, l_ = hi[i], lo[i]
        hit_stop = l_ <= t["stop"] if t["dir"] == 1 else h_ >= t["stop"]
        hit_target = h_ >= t["target"] if t["dir"] == 1 else l_ <= t["target"]
        if hit_stop and hit_target:
            price = t["stop"] if p.tie_break == "stop" else t["target"]
            reason = "ambiguous_" + p.tie_break
        elif hit_stop:
            price, reason = t["stop"], "stop"
        elif hit_target:
            price, reason = t["target"], "target"
        elif p.time_stop_bars and i - t["entry_i"] >= p.time_stop_bars:
            price, reason = d["close"].iat[i], "time_stop"
        elif i - t["entry_i"] >= p.max_hold:
            price, reason = d["close"].iat[i], "timeout"
        else:
            return None
        if p.stop_slip and reason.startswith(("stop", "ambiguous_stop")):
            price -= p.stop_slip * t["dir"]  # stops fill worse than the level
        gross = (price - t["entry"]) * t["dir"]
        remainder = 1.0 - t.get("booked_frac", 0.0)
        gross_r = gross / t["risk"] * remainder + t.get("booked_r", 0.0)
        cost = trade_cost(t, i) * (1.0 + t.get("booked_frac", 0.0))
        t.update(exit_i=i, exit_time=times[i], exit=price, reason=reason,
                 cost=cost, pnl=gross_r * t["risk"] - cost,
                 r=gross_r - cost / t["risk"])
        return t

    for i in range(n):
        if open_trade is not None:
            t = open_trade
            stop_first = lo[i] <= t["stop"] if t["dir"] == 1 else hi[i] >= t["stop"]
            if p.partial_frac and not t.get("booked_frac") and not stop_first:
                lvl = t["entry"] + p.partial_r * t["risk"] * t["dir"]
                hit = hi[i] >= lvl if t["dir"] == 1 else lo[i] <= lvl
                if hit:
                    t["booked_frac"] = p.partial_frac
                    t["booked_r"] = p.partial_r * p.partial_frac
            done = close_out(t, i)
            if done is not None:
                trades.append(done)
                open_trade = None
            else:
                manage(t, i)

        if pending:
            still = []
            for lv in pending:
                age = i - lv["signal_i"]
                if age <= 0:
                    still.append(lv)
                    continue
                if age > p.wait_bars:
                    continue
                if age < p.min_wait_bars:
                    still.append(lv)
                    continue
                touched = lo[i] <= lv["level"] if lv["dir"] == 1 else hi[i] >= lv["level"]
                if not touched:
                    still.append(lv)
                    continue
                if open_trade is not None and not p.allow_concurrent:
                    still.append(lv)
                    continue
                if hours_allowed and hours[i] not in hours_allowed:
                    still.append(lv)
                    continue
                if p.atr_pct_min > 0.0 or p.atr_pct_max < 1.0:
                    rank = atr_pct[i]
                    if not np.isfinite(rank) or not (p.atr_pct_min <= rank <= p.atr_pct_max):
                        still.append(lv)
                        continue

                direction = lv["dir"]
                fill = min(lv["level"], o[i]) if direction == 1 else max(lv["level"], o[i])
                atr = atr_arr[i - 1]
                if p.stop_mode == "atr":
                    risk = p.atr_mult * atr
                else:
                    if p.stop_mode == "pivot":
                        pidx = (piv_lo_idx if direction == 1 else piv_hi_idx)[i - 1]
                        if pidx < 0 or (i - 1 - pidx) > p.stop_lookback:
                            still.append(lv)
                            continue
                        ref = (low_arr if direction == 1 else high_arr)[pidx]
                    else:  # "bars"
                        ref = roll_low[i - 1] if direction == 1 else roll_high[i - 1]
                    stop_px = ref - p.buffer_atr * atr if direction == 1 else ref + p.buffer_atr * atr
                    risk = (fill - stop_px) * direction
                if not np.isfinite(risk) or risk < p.min_stop or risk > p.max_stop_atr * atr:
                    continue
                open_trade = {
                    "signal_time": times[lv["signal_i"]],
                    "entry_time": times[i],
                    "entry_i": i,
                    "dir": direction,
                    "entry": fill,
                    "stop": fill - risk * direction,
                    "target": fill + p.rr * risk * direction,
                    "risk": risk,
                    "bars_to_entry": age,
                    "atr": atr,
                }
                done = close_out(open_trade, i)
                if done is not None:
                    trades.append(done)
                    open_trade = None
                else:
                    manage(open_trade, i)
            pending = still

        for direction in (1, -1):
            flag = bull[i] if direction == 1 else bear[i]
            if not flag:
                continue
            if p.trend != "none" and side[i] != direction:
                continue
            if p.htf_trend != "none" and htf[i] != direction:
                continue
            if p.require_fvg:
                # the gap is only visible after the following bar closes
                if i + 1 >= n:
                    continue
                gap = fvg_bull[i] if direction == 1 else fvg_bear[i]
                if not gap:
                    continue
            pending.append({"signal_i": i, "level": o[i], "dir": direction})

    return pd.DataFrame(trades)
