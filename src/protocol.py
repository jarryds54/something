"""Three-way split so that searching for a better configuration stays honest.

train      explore freely here
validate   confirm anything that looked good; most ideas die at this step
holdout    touched once, at the end, for the final configuration only

An idea that works on train and fails on validate is noise, not a finding.
"""
import sys

import pandas as pd

sys.path.insert(0, "/home/user/something/src")
from engine import Params, simulate  # noqa: E402
from metrics import summarise  # noqa: E402

SPLITS = {"train": (0.00, 0.50), "validate": (0.50, 0.75), "holdout": (0.75, 1.00)}


def slice_of(df: pd.DataFrame, name: str) -> pd.DataFrame:
    lo, hi = SPLITS[name]
    return df.iloc[int(len(df) * lo): int(len(df) * hi)].copy()


def evaluate(df: pd.DataFrame, cfg: dict, parts=("train", "validate")) -> dict:
    out = {}
    for name in parts:
        out[name] = summarise(simulate(slice_of(df, name), Params(**cfg)))
    return out


def line(name: str, s: dict) -> str:
    if not s.get("trades"):
        return f"{name:9s} no trades"
    return (f"{name:9s} {s['trades']:5d} trades | win {s['win_rate']:.3f} | "
            f"mean {s['mean_r']:+.4f}R | total {s['total_r']:+7.1f}R | "
            f"p(edge) {s['p_edge_positive']:.2f}")


def show(df, cfg, label, parts=("train", "validate")):
    res = evaluate(df, cfg, parts)
    print(f"-- {label}")
    for name, s in res.items():
        print("   " + line(name, s))
    return res
