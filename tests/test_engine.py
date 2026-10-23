"""Correctness tests for the backtest engine.

The important one is test_no_lookahead: a trade must be identical whether the
engine is given the whole history or only the bars up to that trade's exit.
"""
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, "/home/user/something/src")
from engine import Params, simulate, is_wickless, add_indicators  # noqa: E402


def bars(rows, start="2025-01-01"):
    t = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"]).assign(time=t)[
        ["time", "open", "high", "low", "close"]
    ]


def test_wickless_detection():
    df = bars([[100, 102, 100, 101], [100, 102, 99, 101], [100, 100, 98, 99]])
    p = Params(atr_len=2)
    d = add_indicators(df, p)
    assert is_wickless(d, 0, 1, p)          # bullish, low == open
    assert not is_wickless(d, 1, 1, p)      # has a lower wick
    assert is_wickless(d, 2, -1, p)         # bearish, high == open


def test_wick_tolerance():
    df = bars([[100, 102, 99.95, 101]])
    d = add_indicators(df, Params(atr_len=2))
    assert not is_wickless(d, 0, 1, Params(wick_tol=0.0))
    assert is_wickless(d, 0, 1, Params(wick_tol=0.10))


def _uptrend_then_retest():
    """40 rising bars, a wickless bullish bar, a pullback to its open, then a rally."""
    rows = []
    price = 100.0
    for _ in range(40):
        rows.append([price, price + 1.0, price - 0.5, price + 0.8])
        price += 0.8
    level = price
    rows.append([level, level + 2.0, level, level + 1.8])   # wickless bullish signal
    rows.append([level + 1.8, level + 2.0, level + 1.0, level + 1.2])
    rows.append([level + 1.2, level + 1.4, level + 0.6, level + 0.8])
    rows.append([level + 0.8, level + 1.0, level - 0.2, level + 0.3])  # touches, 3 bars later
    price = level + 0.3
    for _ in range(20):                                      # then runs up
        rows.append([price, price + 3.0, price - 0.2, price + 2.5])
        price += 2.5
    return bars(rows), level


def test_entry_stop_and_target_are_consistent():
    df, level = _uptrend_then_retest()
    t = simulate(df, Params(trend="slope", trend_thresh=0.5, stop_mode="bars",
                            stop_lookback=10, cost=0.0))
    assert len(t) == 1
    tr = t.iloc[0]
    assert tr["dir"] == 1
    assert tr["entry"] == pytest.approx(level, abs=1e-9)
    assert tr["stop"] < tr["entry"] < tr["target"]
    # 1:1 by construction
    assert (tr["target"] - tr["entry"]) == pytest.approx(tr["entry"] - tr["stop"], rel=1e-9)
    assert tr["r"] == pytest.approx(1.0, rel=1e-9)


def test_cost_is_charged_once_per_trade():
    df, _ = _uptrend_then_retest()
    free = simulate(df, Params(trend="slope", trend_thresh=0.5, stop_mode="bars", cost=0.0))
    paid = simulate(df, Params(trend="slope", trend_thresh=0.5, stop_mode="bars", cost=0.40))
    assert free.iloc[0]["pnl"] - paid.iloc[0]["pnl"] == pytest.approx(0.40)


def test_level_expires_after_wait_bars():
    df, _ = _uptrend_then_retest()
    # the retest arrives 3 bars after the signal, so a 2-bar window must miss it
    assert len(simulate(df, Params(trend="slope", trend_thresh=0.5, stop_mode="bars",
                                   wait_bars=2))) == 0
    assert len(simulate(df, Params(trend="slope", trend_thresh=0.5, stop_mode="bars",
                                   wait_bars=10))) == 1


def test_ambiguous_bar_resolves_to_the_stop():
    """A bar spanning both stop and target must be counted as a loss, not a win."""
    df, level = _uptrend_then_retest()
    rows = df[["open", "high", "low", "close"]].values.tolist()
    # make the entry bar itself span a huge range in both directions
    entry_bar = 43
    rows[entry_bar] = [rows[entry_bar][0], level + 50.0, level - 50.0, level + 1.0]
    wide = bars(rows)
    t = simulate(wide, Params(trend="slope", trend_thresh=0.5, stop_mode="bars", cost=0.0))
    assert len(t) == 1
    assert t.iloc[0]["reason"].startswith("ambiguous")
    assert t.iloc[0]["r"] == pytest.approx(-1.0, rel=1e-9)


def _random_walk(n=4000, seed=7):
    rng = np.random.default_rng(seed)
    close = 2000 + np.cumsum(rng.normal(0, 1.2, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.6, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.6, n))
    # force some exactly-wickless bars so the strategy has signals to find
    idx = rng.choice(n, size=n // 20, replace=False)
    for i in idx:
        if close[i] > open_[i]:
            low[i] = open_[i]
        else:
            high[i] = open_[i]
    return bars(np.round(np.c_[open_, high, low, close], 2).tolist())


@pytest.mark.parametrize("trend,stop_mode", [("slope", "pivot"), ("ema", "bars"), ("none", "atr")])
def test_no_lookahead(trend, stop_mode):
    """Truncating history after a trade closes must not change that trade."""
    df = _random_walk()
    p = Params(trend=trend, stop_mode=stop_mode, wick_tol=0.0)
    full = simulate(df, p)
    assert len(full) > 5, "need trades to make this test meaningful"
    for _, tr in full.head(15).iterrows():
        cut = simulate(df.iloc[: int(tr["exit_i"]) + 1].copy(), p)
        match = cut[cut["entry_time"] == tr["entry_time"]]
        assert len(match) == 1, "trade vanished when future bars were removed"
        m = match.iloc[0]
        for col in ("entry", "stop", "target", "exit", "r"):
            assert m[col] == pytest.approx(tr[col], rel=1e-12), f"{col} changed with hindsight"


def test_malformed_bars_are_rejected():
    from engine import validate_bars
    df = bars([[100, 102, 99, 101], [100, 99, 101, 100]])  # second bar: low above high
    with pytest.raises(ValueError, match="malformed"):
        validate_bars(df)


def test_bar_spread_cost_is_charged_from_the_right_bar():
    """A long pays the spread where it entered; a short where it exited."""
    df, _ = _uptrend_then_retest()
    df = df.assign(spread=5)                      # 5 points = $0.05 at 2 decimals
    df.loc[df.index >= 44, "spread"] = 100        # $1.00 later on
    p = dict(trend="slope", trend_thresh=0.5, stop_mode="bars",
             use_bar_spread=True, commission=0.02)
    t = simulate(df, Params(**p))
    assert len(t) == 1
    tr = t.iloc[0]
    assert tr["dir"] == 1
    entry_spread = df["spread"].iloc[int(tr["entry_i"])] * 0.01
    assert tr["cost"] == pytest.approx(entry_spread + 0.02)


def test_spread_mult_scales_the_cost():
    df, _ = _uptrend_then_retest()
    df = df.assign(spread=20)
    p = dict(trend="slope", trend_thresh=0.5, stop_mode="bars",
             use_bar_spread=True, commission=0.0)
    one = simulate(df, Params(**p, spread_mult=1.0)).iloc[0]["cost"]
    two = simulate(df, Params(**p, spread_mult=2.0)).iloc[0]["cost"]
    assert two == pytest.approx(2 * one)


def test_stop_slippage_only_worsens_losing_exits():
    df, _ = _uptrend_then_retest()
    rows = df[["open", "high", "low", "close"]].values.tolist()
    clean = simulate(df, Params(trend="slope", trend_thresh=0.5, stop_mode="bars",
                                cost=0.0, stop_slip=0.0))
    slipped = simulate(df, Params(trend="slope", trend_thresh=0.5, stop_mode="bars",
                                  cost=0.0, stop_slip=1.0))
    # this fixture resolves at the target, so slippage must change nothing
    assert clean.iloc[0]["reason"] == "target"
    assert slipped.iloc[0]["pnl"] == pytest.approx(clean.iloc[0]["pnl"])
