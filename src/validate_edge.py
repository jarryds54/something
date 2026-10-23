"""Honest tests of the leading configuration: out-of-sample, by period, by subgroup.

Picking the best of a large sweep guarantees a flattering number. These checks ask
whether anything survives when the choice is made without seeing the answer.
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/something/src")
from engine import Params, simulate  # noqa: E402
from metrics import summarise  # noqa: E402


def split_test(df, params_kwargs, train_frac=0.6):
    cut = int(len(df) * train_frac)
    train, test = df.iloc[:cut].copy(), df.iloc[cut:].copy()
    out = {}
    for name, part in (("in-sample", train), ("out-of-sample", test)):
        out[name] = summarise(simulate(part, Params(**params_kwargs)))
        out[name]["span"] = f"{part['time'].min():%Y-%m-%d} to {part['time'].max():%Y-%m-%d}"
    return out


def by_period(trades, freq="QE"):
    t = trades.copy()
    t["period"] = pd.to_datetime(t["entry_time"]).dt.to_period(
        {"QE": "Q", "ME": "M"}[freq]
    )
    g = t.groupby("period").agg(trades=("r", "size"), win=("r", lambda s: (s > 0).mean()),
                                mean_r=("r", "mean"), total_r=("r", "sum"))
    return g.round(3)


def by_subgroup(trades):
    t = trades.copy()
    t["hour"] = pd.to_datetime(t["entry_time"]).dt.hour
    t["session"] = pd.cut(t["hour"], [-1, 6, 11, 15, 23],
                          labels=["asia", "london_am", "overlap", "us_pm"])
    t["stop_bucket"] = pd.qcut(t["risk"], 4, labels=["tightest", "tight", "wide", "widest"])
    t["entry_speed"] = pd.cut(t["bars_to_entry"], [0, 2, 4, 10],
                              labels=["1-2 bars", "3-4 bars", "5+ bars"])
    frames = {}
    for key in ("session", "stop_bucket", "entry_speed", "dir"):
        frames[key] = t.groupby(key, observed=True).agg(
            trades=("r", "size"), win=("r", lambda s: (s > 0).mean()), mean_r=("r", "mean")
        ).round(3)
    return frames
