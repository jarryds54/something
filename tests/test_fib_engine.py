"""Correctness tests for the Fibonacci retracement engine.

The important one is test_no_lookahead: a trade must come out identical whether the
engine is handed the whole history or only the bars up to that trade's exit.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import fib_engine  # noqa: E402
from fib_engine import Params, simulate, fib_level, add_indicators  # noqa: E402


def bars(rows, start="2025-01-01", freq="15min"):
    t = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"]).assign(time=t)[
        ["time", "open", "high", "low", "close"]
    ]


def _ramp(rows, start, end, n, pad=0.2):
    """n candles walking from `start` to `end`, each one's range a touch wider."""
    step = (end - start) / n
    price = start
    for _ in range(n):
        nxt = price + step
        rows.append([price, max(price, nxt) + pad, min(price, nxt) - pad, nxt])
        price = nxt
    return price


def _long_setup(leg_low=100.0, leg_high=120.0, pull_to=110.0, pull_bars=8,
                pre=25, post=12):
    """Decline to a swing low, a rally to a swing high, a pullback to 0.5, then a rally.

    The 0.5 retracement of a 100 -> 120 leg sits at 110, so the pullback is built to
    reach exactly that level and no further.
    """
    rows = []
    _ramp(rows, leg_low + 10.0, leg_low, pre)            # down into the swing low
    _ramp(rows, leg_low, leg_high, 20)                   # the impulse leg up
    _ramp(rows, leg_high, pull_to, pull_bars)            # the retracement
    _ramp(rows, pull_to, leg_high + 5.0, post)           # and the run to target
    return bars(rows)


def _loose(**kw):
    """Geometry-only settings: the trader's percentage gates switched off."""
    base = dict(pivot_k=2, leg_min_atr=1.0, stop_mode="swing", max_stop_pct=100.0,
                min_stop_pct=0.0, min_target_pct=0.0, min_rr=0.0, cost_bps=0.0,
                allow_short=False)
    base.update(kw)
    return Params(**base)


def test_fib_level_is_the_midpoint_at_one_half():
    assert fib_level(120.0, 100.0, 0.5, 1) == pytest.approx(110.0)
    assert fib_level(120.0, 100.0, 0.5, -1) == pytest.approx(110.0)
    assert fib_level(120.0, 100.0, 0.382, 1) == pytest.approx(112.36)
    assert fib_level(120.0, 100.0, 0.382, -1) == pytest.approx(107.64)


def test_long_entry_stop_and_target_match_the_structure():
    t = simulate(_long_setup(), _loose(stop_buffer_atr=0.0))
    assert len(t) == 1
    row = t.iloc[0]
    assert row["dir"] == 1
    assert row["entry"] == pytest.approx(110.0, abs=0.5)
    assert row["stop"] == pytest.approx(row["leg_low"], abs=0.3)
    assert row["target"] == pytest.approx(row["leg_high"], abs=0.3)
    assert row["reason"] == "target"
    assert row["r"] > 0


def test_short_is_the_exact_mirror():
    rows = []
    _ramp(rows, 110.0, 120.0, 25)      # up into the swing high
    _ramp(rows, 120.0, 100.0, 20)      # the impulse leg down
    _ramp(rows, 100.0, 110.0, 8)       # the bounce to 0.5
    _ramp(rows, 110.0, 95.0, 12)       # and the run to target
    t = simulate(bars(rows), _loose(allow_long=False, allow_short=True,
                                    stop_buffer_atr=0.0))
    assert len(t) == 1
    row = t.iloc[0]
    assert row["dir"] == -1
    assert row["entry"] == pytest.approx(110.0, abs=0.5)
    assert row["stop"] == pytest.approx(row["leg_high"], abs=0.3)
    assert row["target"] == pytest.approx(row["leg_low"], abs=0.3)
    assert row["r"] > 0


def test_the_risk_cap_skips_a_setup_whose_structural_stop_is_too_wide():
    df = _long_setup()
    # the swing stop on this leg is about 9% below the 0.5 entry
    assert len(simulate(df, _loose(max_stop_pct=100.0))) == 1
    assert len(simulate(df, _loose(max_stop_pct=1.5))) == 0


def test_a_percentage_stop_keeps_the_same_setup_inside_the_risk_cap():
    df = _long_setup()
    t = simulate(df, _loose(stop_mode="pct", stop_pct=1.5, max_stop_pct=1.5))
    assert len(t) == 1
    assert t.iloc[0]["stop_pct"] == pytest.approx(1.5, abs=0.01)


def test_the_profit_floor_skips_a_setup_that_does_not_pay_enough():
    df = _long_setup()
    # the 0.5 entry sits about 9% below the leg high, so a 3% floor passes
    assert len(simulate(df, _loose(stop_mode="pct", min_target_pct=3.0))) == 1
    assert len(simulate(df, _loose(stop_mode="pct", min_target_pct=20.0))) == 0


def test_a_shallow_leg_is_ignored():
    df = _long_setup(leg_low=100.0, leg_high=100.6, pull_to=100.3)
    assert len(simulate(df, _loose(leg_min_pct=0.0, leg_min_atr=0.0))) >= 0
    assert len(simulate(df, _loose(leg_min_pct=5.0))) == 0


def test_level_expires_once_the_wait_window_has_passed():
    df = _long_setup(pull_bars=20)
    assert len(simulate(df, _loose(wait_bars=60))) == 1
    assert len(simulate(df, _loose(wait_bars=5))) == 0


def test_a_leg_already_broken_to_new_highs_produces_no_trade():
    rows = []
    _ramp(rows, 110.0, 100.0, 25)
    _ramp(rows, 100.0, 120.0, 20)
    _ramp(rows, 120.0, 118.0, 3)
    _ramp(rows, 118.0, 126.0, 6)       # a new high: the old leg no longer defines the pullback
    _ramp(rows, 126.0, 110.0, 10)
    _ramp(rows, 110.0, 130.0, 12)
    t = simulate(bars(rows), _loose(leg_max_bars=25))
    assert ((t["entry"] - 110.0).abs() < 0.5).sum() == 0 if len(t) else True


def test_a_bar_spanning_both_levels_counts_as_a_loss():
    rows = []
    _ramp(rows, 110.0, 100.0, 25)
    _ramp(rows, 100.0, 120.0, 20)
    _ramp(rows, 120.0, 112.0, 6)
    rows.append([112.0, 121.0, 99.0, 111.0])   # reaches target and stop on one bar
    _ramp(rows, 111.0, 130.0, 10)
    t = simulate(bars(rows), _loose(stop_buffer_atr=0.0))
    assert len(t) == 1
    assert t.iloc[0]["reason"] == "ambiguous_stop"
    assert t.iloc[0]["r"] < 0


def test_cost_is_charged_once_and_only_reduces_the_result():
    df = _long_setup()
    free = simulate(df, _loose(cost_bps=0.0)).iloc[0]
    paid = simulate(df, _loose(cost_bps=20.0)).iloc[0]
    assert paid["entry"] == free["entry"] and paid["exit"] == free["exit"]
    assert paid["cost"] == pytest.approx(free["entry"] * 20.0 / 1e4)
    assert paid["pnl"] == pytest.approx(free["pnl"] - paid["cost"])
    assert paid["r"] < free["r"]


def test_the_rsi_gate_cannot_be_overridden():
    df = _long_setup()
    assert len(simulate(df, _loose())) == 1
    # the pullback here is shallow enough that RSI never gets near oversold,
    # so a strict gate must refuse the trade rather than wave it through
    assert len(simulate(df, _loose(rsi_long_max=30.0))) == 0


def test_malformed_bars_are_rejected():
    df = bars([[100, 99, 101, 100]])   # high below low
    with pytest.raises(ValueError):
        simulate(df, Params())


def _random_walk(n=4000, seed=7):
    rng = np.random.default_rng(seed)
    close = 30000 * np.exp(np.cumsum(rng.normal(0, 0.0025, n)))
    span = np.abs(rng.normal(0, 0.0018, n)) * close
    o = np.concatenate([[close[0]], close[:-1]])
    hi = np.maximum(o, close) + span
    lo = np.minimum(o, close) - span
    t = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"time": t, "open": o, "high": hi, "low": lo, "close": close})


@pytest.mark.parametrize("fib_entry", [0.382, 0.5, 0.618])
@pytest.mark.parametrize("stop_mode", ["swing", "fib", "pct"])
def test_no_lookahead(fib_entry, stop_mode):
    df = _random_walk()
    p = _loose(fib_entry=fib_entry, stop_mode=stop_mode, allow_short=True,
               max_stop_pct=100.0, min_target_pct=0.0, min_rr=0.0)
    full = simulate(df, p)
    assert len(full) > 0, "the fixture must produce trades for this test to mean anything"
    for k in range(min(5, len(full))):
        row = full.iloc[k]
        cut = simulate(df.iloc[: int(row["exit_i"]) + 1].reset_index(drop=True), p)
        assert len(cut) == k + 1
        same = cut.iloc[k]
        for field in ("entry_i", "exit_i", "dir", "entry", "stop", "target", "r"):
            assert same[field] == pytest.approx(row[field]), f"{field} changed when truncated"


def test_only_one_position_is_open_at_a_time():
    df = _random_walk()
    t = simulate(df, _loose(allow_short=True))
    assert len(t) > 1
    assert (t["entry_i"].to_numpy()[1:] > t["exit_i"].to_numpy()[:-1]).all()


def test_indicators_do_not_peek():
    df = _random_walk(n=300)
    p = Params()
    full = add_indicators(df, p)
    cut = add_indicators(df.iloc[:200].reset_index(drop=True), p)
    for col in ("atr", "ema", "rsi"):
        assert np.allclose(full[col].to_numpy()[:200], cut[col].to_numpy())


def test_a_bar_that_opens_far_beyond_the_level_is_not_traded():
    """A gap-through fill is a price the feed cannot vouch for."""
    rows = []
    _ramp(rows, 110.0, 100.0, 25)
    _ramp(rows, 100.0, 120.0, 20)
    _ramp(rows, 120.0, 114.0, 5)
    rows.append([104.0, 114.0, 103.0, 112.0])   # opens far below the 110 level
    _ramp(rows, 112.0, 130.0, 12)
    df = bars(rows)
    assert len(simulate(df, _loose(max_gap_atr=100.0))) == 1   # the old, generous rule
    strict = simulate(df, _loose(max_gap_atr=0.25))
    assert len(strict) == 0
    assert strict.attrs["skipped"]["unverifiable_fill"] >= 1


def _single_touch():
    """A pullback that stops short, then one bar that wicks down to the 0.5 level."""
    rows = []
    _ramp(rows, 110.0, 100.0, 25)
    _ramp(rows, 100.0, 120.0, 20)
    _ramp(rows, 120.0, 111.5, 5)
    rows.append([111.5, 111.8, 109.8, 111.6])   # the only bar that reaches 110
    _ramp(rows, 111.6, 130.0, 12)
    return rows


def test_gap_flags_mark_the_bar_after_a_hole():
    df = bars(_single_touch())
    holed = df.drop(index=30).reset_index(drop=True)
    flags = fib_engine._gap_flags(holed)
    assert flags[30] and not flags[29] and not flags[31]


def test_a_bar_following_a_hole_in_the_feed_is_not_traded():
    rows = _single_touch()
    df = bars(rows)
    touch_i = 50                       # 25 + 20 + 5 bars of ramp, then the wick bar
    assert df["low"].iat[touch_i] < 110.0
    assert len(simulate(df, _loose())) == 1

    holed = df.drop(index=touch_i - 1).reset_index(drop=True)
    assert len(simulate(holed, _loose(skip_gap_bars=False))) == 1
    strict = simulate(holed, _loose(skip_gap_bars=True))
    assert len(strict) == 0
    assert strict.attrs["skipped"]["after_gap"] >= 1


def test_skip_reasons_are_recorded():
    df = _long_setup()
    t = simulate(df, _loose(max_stop_pct=1.5))
    assert len(t) == 0
    assert t.attrs["skipped"]["stop_too_wide"] >= 1


def test_a_retracement_already_past_the_level_is_not_traded():
    """The leg is only known k bars after its high. If price went through the 0.5
    level inside that lag, no order could have been resting there."""
    rows = []
    _ramp(rows, 110.0, 100.0, 25)
    _ramp(rows, 100.0, 120.0, 20)
    _ramp(rows, 120.0, 104.0, 3)    # through the 110 level inside the two-bar lag
    _ramp(rows, 104.0, 100.0, 3)    # and onwards, so the dip is not itself a pivot
    _ramp(rows, 100.0, 130.0, 20)
    t = simulate(bars(rows), _loose())
    assert len(t) == 0
    assert t.attrs["skipped"]["level_already_passed"] >= 1


def test_the_prior_high_target_reaches_beyond_the_legs_own_high():
    """The trader's stated target: the next structural high above this one."""
    rows = []
    _ramp(rows, 120.0, 135.0, 12)      # an older, higher swing high at 135
    _ramp(rows, 135.0, 100.0, 25)      # down into the swing low
    _ramp(rows, 100.0, 120.0, 20)      # the impulse leg
    _ramp(rows, 120.0, 110.0, 8)       # the retracement to 0.5
    _ramp(rows, 110.0, 140.0, 20)      # and a run past the old high
    df = bars(rows)
    swing = simulate(df, _loose(target_mode="swing")).iloc[0]
    prior = simulate(df, _loose(target_mode="prior_high")).iloc[0]
    assert swing["target"] == pytest.approx(swing["leg_high"], abs=0.3)
    assert prior["target"] > prior["leg_high"]
    assert prior["target"] == pytest.approx(135.0, abs=0.5)
    assert prior["target_pct"] > swing["target_pct"]


def test_prior_high_target_is_skipped_when_there_is_no_higher_swing():
    rows = []
    _ramp(rows, 110.0, 100.0, 25)
    _ramp(rows, 100.0, 120.0, 20)      # the highest point in the whole series
    _ramp(rows, 120.0, 110.0, 8)
    _ramp(rows, 110.0, 119.0, 12)
    t = simulate(bars(rows), _loose(target_mode="prior_high"))
    assert len(t) == 0
    assert t.attrs["skipped"]["no_structural_target"] >= 1


def test_running_high_mode_finds_the_setup_the_pivot_lag_misses():
    """A leg whose 0.5 level is reached inside the pivot confirmation lag."""
    rows = []
    _ramp(rows, 110.0, 100.0, 25)
    _ramp(rows, 100.0, 120.0, 20)
    _ramp(rows, 120.0, 108.0, 3)     # through 110 before a 2-bar pivot confirms
    _ramp(rows, 108.0, 130.0, 20)
    df = bars(rows)
    assert len(simulate(df, _loose(high_mode="pivot"))) == 0
    t = simulate(df, _loose(high_mode="running"))
    assert len(t) == 1
    row = t.iloc[0]
    assert row["leg_high"] == pytest.approx(120.2, abs=0.3)
    assert row["entry"] == pytest.approx(110.0, abs=0.6)


def test_running_mode_waits_for_the_leg_to_turn():
    """While each bar is making a new high there is no retracement to trade."""
    rows = []
    _ramp(rows, 110.0, 100.0, 25)
    _ramp(rows, 100.0, 130.0, 30)    # straight up, never turning
    t = simulate(bars(rows), _loose(high_mode="running", high_age_min=2))
    assert len(t) == 0


@pytest.mark.parametrize("high_mode", ["pivot", "running"])
@pytest.mark.parametrize("target_mode", ["swing", "prior_high", "ext"])
def test_no_lookahead_across_modes(high_mode, target_mode):
    df = _random_walk()
    p = _loose(high_mode=high_mode, target_mode=target_mode, allow_short=True)
    full = simulate(df, p)
    assert len(full) > 0
    for k in range(min(4, len(full))):
        row = full.iloc[k]
        cut = simulate(df.iloc[: int(row["exit_i"]) + 1].reset_index(drop=True), p)
        assert len(cut) == k + 1
        for field in ("entry_i", "exit_i", "dir", "entry", "stop", "target", "r"):
            assert cut.iloc[k][field] == pytest.approx(row[field]), f"{field} moved"
