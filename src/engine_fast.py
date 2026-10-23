"""Vectorised precomputation for the engine's hot paths.

Same rules as engine.py, but trend state, wickless flags and swing pivots are
computed once over the whole series instead of recomputed inside the bar loop.
engine.simulate delegates here; the test suite checks both agree.
"""
import numpy as np
import pandas as pd


def trend_series(d: pd.DataFrame, p) -> np.ndarray:
    """+1 / -1 / 0 per bar, using only information available at that bar."""
    n = len(d)
    side = np.zeros(n, dtype=np.int8)
    if p.trend == "none":
        return side
    k = p.trend_len
    close, atr, ema = d["close"].to_numpy(), d["atr"].to_numpy(), d["ema"].to_numpy()

    if p.trend == "ema":
        prev_ema = np.concatenate([np.full(k, np.nan), ema[:-k]])
        side[(close > ema) & (ema > prev_ema)] = 1
        side[(close < ema) & (ema < prev_ema)] = -1
    elif p.trend == "slope":
        prev_close = np.concatenate([np.full(k, np.nan), close[:-k]])
        move = close - prev_close
        with np.errstate(invalid="ignore"):
            side[move > p.trend_thresh * atr] = 1
            side[move < -p.trend_thresh * atr] = -1
    elif p.trend == "structure":
        half = max(2, k // 2)
        hi, lo = d["high"], d["low"]
        recent_hi = hi.rolling(half).max().to_numpy()
        recent_lo = lo.rolling(half).min().to_numpy()
        prior_hi = hi.rolling(k - half).max().shift(half).to_numpy()
        prior_lo = lo.rolling(k - half).min().shift(half).to_numpy()
        with np.errstate(invalid="ignore"):
            side[(recent_hi > prior_hi) & (recent_lo > prior_lo)] = 1
            side[(recent_hi < prior_hi) & (recent_lo < prior_lo)] = -1
    else:
        raise ValueError(f"unknown trend mode {p.trend}")

    side[: k + 1] = 0  # not enough history to judge
    return side


def wickless_flags(d: pd.DataFrame, p):
    o, h, l, c = (d[x].to_numpy() for x in ("open", "high", "low", "close"))
    atr = d["atr"].to_numpy()
    body_ok = np.ones(len(d), dtype=bool)
    if p.body_min_atr:
        with np.errstate(invalid="ignore"):
            body_ok = np.abs(c - o) >= p.body_min_atr * atr
    bull = (c > o) & ((o - l) <= p.wick_tol) & body_ok
    bear = (c < o) & ((h - o) <= p.wick_tol) & body_ok
    return bull, bear


def last_pivot_arrays(d: pd.DataFrame, k: int):
    """For each bar j: index and value of the most recent swing confirmed by j."""
    low, high = d["low"].to_numpy(), d["high"].to_numpy()
    n = len(d)
    is_low = np.zeros(n, dtype=bool)
    is_high = np.zeros(n, dtype=bool)
    if k >= 1 and n > 2 * k:
        # a pivot low is strictly lower than the k bars on each side
        roll_min = pd.Series(low).rolling(2 * k + 1, center=True).min().to_numpy()
        roll_max = pd.Series(high).rolling(2 * k + 1, center=True).max().to_numpy()
        is_low[k:-k] = (low[k:-k] == roll_min[k:-k])
        is_high[k:-k] = (high[k:-k] == roll_max[k:-k])

    def confirmed(flags):
        idx = np.full(n, -1, dtype=np.int64)
        last = -1
        for j in range(n):
            cand = j - k  # a pivot at cand is only confirmed k bars later
            if cand >= 0 and flags[cand]:
                last = cand
            idx[j] = last
        return idx

    return confirmed(is_low), confirmed(is_high), low, high
