"""Tests for the prop-firm evaluation simulator."""
import sys
from datetime import date, timedelta

import numpy as np
import pytest

sys.path.insert(0, "/home/user/something/src")
from funded import Rules, run_account  # noqa: E402

ONE_PHASE = Rules("test", (0.10,), daily_loss=0.05, max_loss=0.10)


def days_from(n, same_day=False):
    d0 = date(2025, 1, 6)
    return np.array([d0 if same_day else d0 + timedelta(days=i) for i in range(n)])


def test_steady_winners_pass():
    r = np.ones(40)                      # +1R each, 1% risk
    out = run_account(r, days_from(40), ONE_PHASE, risk_pct=0.01)
    assert out["result"] == "passed"
    assert out["balance"] >= 110_000


def test_losses_trigger_the_overall_limit():
    r = -np.ones(40)
    out = run_account(r, days_from(40), ONE_PHASE, risk_pct=0.01)
    assert out["result"] == "max breach"
    # 10% of 100k at ~1% risk each: breached around the tenth trade
    assert 8 <= out["trades"] <= 12


def test_daily_limit_bites_before_the_overall_one():
    """Six losses in one day must stop at the 5% daily limit, not the 10% total."""
    r = -np.ones(20)
    out = run_account(r, days_from(20, same_day=True), ONE_PHASE, risk_pct=0.01)
    assert out["result"] == "daily breach"
    assert out["trades"] <= 7


def test_a_new_day_resets_the_daily_limit():
    # at 0.5% risk it takes ~21 losses to breach 10%, so give it room
    r = -np.ones(30)
    spread_out = run_account(r, days_from(30), ONE_PHASE, risk_pct=0.005)
    # at 0.5% risk, 5% daily is never reached on one trade per day; the overall
    # limit is what ends it
    assert spread_out["result"] == "max breach"


def test_two_phase_evaluation_restarts_the_balance():
    two = Rules("two", (0.05, 0.05), daily_loss=0.05, max_loss=0.10)
    r = np.ones(60)
    out = run_account(r, days_from(60), two, risk_pct=0.01)
    assert out["result"] == "passed"
    assert out["phase"] == 2


def test_minimum_trading_days_delays_the_pass():
    strict = Rules("strict", (0.05,), daily_loss=0.05, max_loss=0.10, min_days=10)
    r = np.ones(30)
    quick = run_account(r, days_from(30, same_day=True), strict, risk_pct=0.02)
    assert quick["result"] != "passed"      # all on one day: cannot satisfy 10 days
    spread = run_account(r, days_from(30), strict, risk_pct=0.02)
    assert spread["result"] == "passed"


def test_trailing_limit_is_stricter_than_static():
    rules_static = Rules("s", (0.50,), daily_loss=0.20, max_loss=0.10)
    rules_trail = Rules("t", (0.50,), daily_loss=0.20, max_loss=0.10, trailing=True)
    r = np.array([1.0] * 8 + [-1.0] * 12)   # run up, then give it all back
    static = run_account(r, days_from(20), rules_static, risk_pct=0.01)
    trail = run_account(r, days_from(20), rules_trail, risk_pct=0.01)
    assert trail["trades"] < static["trades"]


def test_day_bootstrap_keeps_trades_grouped_into_days():
    """Resampling must preserve multi-trade days, or the daily limit never binds."""
    import pandas as pd
    from funded import day_bootstrap
    stamps = pd.to_datetime(
        ["2025-01-06 10:00", "2025-01-06 11:00", "2025-01-06 12:00",  # three in a day
         "2025-01-07 10:00",                                           # one
         "2025-01-08 10:00", "2025-01-08 11:00"]                       # two
    , utc=True)
    trades = pd.DataFrame({"exit_time": stamps, "r": [-1.0, -1.0, -1.0, 1.0, -1.0, 1.0]})
    rng = np.random.default_rng(0)
    r, days = next(day_bootstrap(trades, 1, rng, block_days=2, target_trades=60,
                                 platform_offset_h=0))
    counts = pd.Series(days).value_counts()
    assert set(counts.unique()) <= {1, 2, 3}
    assert (counts == 3).any(), "the three-trade day must survive resampling"


def test_daily_stop_caps_the_loss_on_a_bad_day():
    """After the self-imposed daily stop, no further trades that day are taken."""
    r = np.array([-1.0] * 10)
    same = days_from(10, same_day=True)
    loose = Rules("loose", (0.50,), daily_loss=0.50, max_loss=0.50)
    with_stop = run_account(r, same, loose, risk_pct=0.01, daily_stop_r=2.0)
    without = run_account(r, same, loose, risk_pct=0.01, daily_stop_r=0.0)
    assert with_stop["balance"] > without["balance"]
    # stops after the loss passes -2R, so three trades at most
    assert with_stop["balance"] >= 100_000 * (1 - 0.01 * 3) - 1
