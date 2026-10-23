"""Does this strategy actually pass a prop-firm evaluation?

Expectancy is not the question a funded account asks. The question is whether the
equity path breaches a daily or overall loss limit before it reaches the target.
That depends on risk per trade and on the order losses happen to arrive in, so the
answer is a probability, not a number.

Intraday equity is modelled properly: one position at a time with a hard stop means
the floating loss never exceeds one risk unit, so the worst equity within a day is
the running realised total minus 1R while a trade is open.
"""
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/something/src")


@dataclass
class Rules:
    name: str
    phase_targets: tuple          # fraction of starting balance per phase
    daily_loss: float             # fraction of the day's starting balance
    max_loss: float               # fraction of the starting balance
    trailing: bool = False        # does the overall limit follow equity up?
    min_days: int = 0             # minimum distinct trading days per phase


TWO_STEP = Rules("2-Step Standard", (0.08, 0.05), 0.05, 0.10, min_days=0)
TWO_STEP_PRO = Rules("2-Step Pro", (0.06, 0.06), 0.03, 0.06, min_days=0)
FUNDED = Rules("funded (payout at 5%)", (0.05,), 0.05, 0.10, min_days=0)
FUNDED_PRO = Rules("funded Pro (payout at 5%)", (0.05,), 0.03, 0.06, min_days=0)


def run_account(r_values, days, rules: Rules, risk_pct: float,
                start: float = 100_000.0, max_trades: int = 10_000,
                daily_stop_r: float = 0.0):
    """daily_stop_r: self-imposed rule, stop trading for the day after losing this
    many R. Caps the worst day by construction, which is what the daily limit kills."""
    """Walk a trade sequence through one evaluation. Returns the outcome."""
    balance = start
    phase = 0
    phase_start = balance
    day_start_balance = balance
    day_r = 0.0
    current_day = days[0] if len(days) else None
    days_traded = set()
    peak = balance

    for n, (r, day) in enumerate(zip(r_values[:max_trades], days[:max_trades])):
        if day != current_day:
            current_day = day
            day_start_balance = balance
            day_r = 0.0
        if daily_stop_r and day_r <= -daily_stop_r:
            continue  # sitting out the rest of this day

        risk = balance * risk_pct
        # worst point while this trade is open: a full stop-out on top of the day so far
        equity_low = balance - risk
        if equity_low <= day_start_balance * (1 - rules.daily_loss):
            return {"result": "daily breach", "trades": n + 1, "phase": phase,
                    "balance": balance, "days": len(days_traded)}
        floor = (peak if rules.trailing else start) * (1 - rules.max_loss)
        if equity_low <= floor:
            return {"result": "max breach", "trades": n + 1, "phase": phase,
                    "balance": balance, "days": len(days_traded)}

        balance += risk * r
        day_r += r
        peak = max(peak, balance)
        days_traded.add(day)

        if balance >= phase_start * (1 + rules.phase_targets[phase]):
            if len(days_traded) < rules.min_days:
                continue
            phase += 1
            if phase >= len(rules.phase_targets):
                return {"result": "passed", "trades": n + 1, "phase": phase,
                        "balance": balance, "days": len(days_traded)}
            balance = start          # each phase restarts from the nominal balance
            phase_start = start
            peak = start
            day_start_balance = start
            day_r = 0.0
            days_traded = set()

    return {"result": "ran out of data", "trades": len(r_values), "phase": phase,
            "balance": balance, "days": len(days_traded)}


def day_bootstrap(trades: pd.DataFrame, n_paths, rng, block_days=10,
                  target_trades=2500, platform_offset_h=3):
    """Resample whole trading days, in blocks of consecutive days.

    Resampling individual trades would scatter them evenly across the calendar and
    hide the daily loss limit, which only bites when several losses land on one day.
    The real distribution is uneven: 1 to 9 trades a day, and the worst day in the
    sample lost over 5R.
    """
    stamps = pd.to_datetime(trades["exit_time"]) + pd.Timedelta(hours=platform_offset_h)
    frame = trades.assign(_day=stamps.dt.date)
    days = [g["r"].to_numpy() for _, g in frame.groupby("_day", sort=True)]
    n_days = len(days)
    per_path = int(target_trades / max(1e-9, len(frame) / n_days)) + block_days

    for _ in range(n_paths):
        starts = rng.integers(0, max(1, n_days - block_days),
                              size=per_path // block_days + 1)
        chosen = []
        for s0 in starts:
            chosen.extend(days[s0: s0 + block_days])
        r_values, day_ids = [], []
        for k, day in enumerate(chosen):
            r_values.extend(day)
            day_ids.extend([k] * len(day))
        yield np.asarray(r_values), np.asarray(day_ids)


def monte_carlo(trades: pd.DataFrame, rules: Rules, risk_pct: float,
                n_paths: int = 2000, seed: int = 0, platform_offset_h: int = 3,
                length: int = None, daily_stop_r: float = 0.0):
    """platform_offset_h: the daily limit resets at midnight broker time, not UTC."""
    rng = np.random.default_rng(seed)
    outcomes = []
    for rv, dv in day_bootstrap(trades, n_paths, rng,
                                target_trades=length or 2500,
                                platform_offset_h=platform_offset_h):
        outcomes.append(run_account(rv, dv, rules, risk_pct,
                                    daily_stop_r=daily_stop_r))
    out = pd.DataFrame(outcomes)
    counts = out["result"].value_counts(normalize=True)
    return {
        "pass": float(counts.get("passed", 0.0)),
        "daily_breach": float(counts.get("daily breach", 0.0)),
        "max_breach": float(counts.get("max breach", 0.0)),
        "incomplete": float(counts.get("ran out of data", 0.0)),
        "median_trades_to_pass": float(
            out.loc[out.result == "passed", "trades"].median()
        ) if (out.result == "passed").any() else float("nan"),
    }
