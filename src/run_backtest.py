"""Run one configuration, or sweep the parameters the strategy description left open."""
import argparse
import itertools
import sys

import pandas as pd

sys.path.insert(0, "/home/user/something/src")
from engine import Params, simulate  # noqa: E402
from metrics import summarise, format_summary  # noqa: E402

# the choices the trader could not pin down, each spanning plausible readings of the rules
GRID = {
    "trend": ["none", "ema", "slope", "structure"],
    "trend_len": [10, 20, 40],
    "wick_tol": [0.0, 0.05, 0.20],
    "wait_bars": [7, 10],
    "stop_mode": ["pivot", "bars", "atr"],
    "buffer_atr": [0.0, 0.25],
}


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"])
    return df.sort_values("time").reset_index(drop=True)


def sweep(df: pd.DataFrame, fixed: dict) -> pd.DataFrame:
    keys = list(GRID)
    rows = []
    for combo in itertools.product(*(GRID[k] for k in keys)):
        cfg = dict(zip(keys, combo))
        if cfg["trend"] == "none" and cfg["trend_len"] != GRID["trend_len"][0]:
            continue  # trend_len is meaningless without a trend filter
        if cfg["stop_mode"] == "atr" and cfg["buffer_atr"] != GRID["buffer_atr"][0]:
            continue  # buffer only applies to structural stops
        p = Params(**{**cfg, **fixed})
        rows.append({**cfg, **summarise(simulate(df, p))})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/home/user/something/data/xauusd_5m.csv")
    ap.add_argument("--cost", type=float, default=0.30)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--out", default="/home/user/something/reports/sweep.csv")
    args = ap.parse_args()

    df = load(args.data)
    span = f"{df['time'].min()} to {df['time'].max()} ({len(df):,} bars)"

    if args.sweep:
        res = sweep(df, {"cost": args.cost})
        res.to_csv(args.out, index=False)
        traded = res[res["trades"] >= 10].sort_values("mean_r", ascending=False)
        print(span)
        print(f"{len(res)} configurations, {len(traded)} with at least 10 trades\n")
        cols = ["trend", "trend_len", "wick_tol", "wait_bars", "stop_mode", "buffer_atr",
                "trades", "win_rate", "mean_r", "total_r", "p_edge_positive"]
        if len(traded):
            print("best:\n", traded[cols].head(8).to_string(index=False))
            print("\nworst:\n", traded[cols].tail(5).to_string(index=False))
            print(f"\nacross all configurations with >=10 trades: "
                  f"median mean_r {traded['mean_r'].median():+.3f}, "
                  f"{(traded['mean_r'] > 0).mean():.0%} profitable, "
                  f"total trades {int(traded['trades'].sum()):,}")
    else:
        p = Params(cost=args.cost)
        print(span)
        print(format_summary(summarise(simulate(df, p))))
