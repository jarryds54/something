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
                start: float = 100_000.0, max_trades: int = 10_000):
    """Walk a trade sequence through one evaluation. Returns the outcome."""
    balance = start
    phase = 0
    phase_start = balance
    day_start_balance = balance
    current_day = days[0] if len(days) else None
    days_traded = set()
    peak = balance

    for n, (r, day) in enumerate(zip(r_values[:max_trades], days[:max_trades])):
        if day != current_day:
            current_day = day
            day_start_balance = balance

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
            days_traded = set()

    return {"result": "ran out of data", "trades": len(r_values), "phase": phase,
            "balance": balance, "days": len(days_traded)}


def block_bootstrap(r_values, days, n_paths, rng, block=20):
    """Resample in blocks so losing streaks survive the resampling."""
    n = len(r_values)
    starts = rng.integers(0, max(1, n - block), size=(n_paths, n // block + 1))
    for row in starts:
        idx = np.concatenate([np.arange(s, s + block) for s in row])[:n]
        idx = idx[idx < n]
        yield r_values[idx], days[idx]


def monte_carlo(trades: pd.DataFrame, rules: Rules, risk_pct: float,
                n_paths: int = 2000, seed: int = 0, platform_offset_h: int = 3):
    """platform_offset_h: the daily limit resets at midnight broker time, not UTC."""
    r_values = trades["r"].to_numpy()
    stamps = pd.to_datetime(trades["exit_time"]) + pd.Timedelta(hours=platform_offset_h)
    days = stamps.dt.date.to_numpy()
    rng = np.random.default_rng(seed)
    outcomes = []
    for rv, dv in block_bootstrap(r_values, days, n_paths, rng):
        outcomes.append(run_account(rv, dv, rules, risk_pct))
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
