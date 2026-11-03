"""Run the Fibonacci retracement strategy once, or sweep the choices the rules left open.

    python3 src/run_fib.py --data data/btcusd_15m.csv
    python3 src/run_fib.py --data data/btcusd_15m.csv --sweep
"""
import argparse
import itertools
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fib_engine import Params, simulate  # noqa: E402
from metrics import summarise, format_summary  # noqa: E402

# Each of these was a judgement call in the description rather than a stated rule.
# A result that survives most of the grid is worth more than one that appears at a
# single setting.
GRID = {
    "high_mode": ["pivot", "running"],
    "pivot_k": [2, 3, 5],
    "leg_min_atr": [1.5, 3.0],
    "fib_entry": [0.382, 0.500, 0.618],
    "stop_mode": ["pct", "swing", "fib"],
    "target_mode": ["swing", "prior_high", "ext"],
    "trend": ["none", "ema"],
}

COLS = list(GRID) + ["trades", "win_rate", "mean_r", "total_r", "profit_factor",
                     "max_dd_r", "p_edge_positive"]


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"])
    keep = ["time", "open", "high", "low", "close"]
    return df[keep].sort_values("time").drop_duplicates("time").reset_index(drop=True)


def contiguity(df: pd.DataFrame) -> str:
    """How much of the series is missing. Holes in a feed flatter a backtest."""
    step = df["time"].diff().dt.total_seconds()
    typical = step.median()
    holes = step[step > typical * 1.5]
    if not len(holes):
        return f"bar size {typical / 60:.0f} min, no gaps"
    return (f"bar size {typical / 60:.0f} min, {len(holes)} gaps "
            f"({len(holes) / len(df):.1%} of bars), largest {holes.max() / 3600:.1f}h")


def skip_report(trades: pd.DataFrame) -> str:
    reasons = (trades.attrs or {}).get("skipped") or {}
    live = {k: v for k, v in reasons.items() if v}
    if not live:
        return ""
    return "\n  candidate entries refused: " + ", ".join(
        f"{k.replace('_', ' ')} {v}" for k, v in sorted(live.items(), key=lambda kv: -kv[1]))


def describe(trades: pd.DataFrame) -> str:
    if trades is None or len(trades) == 0:
        return "no trades" + skip_report(trades)
    s = summarise(trades)
    held = trades["exit_i"] - trades["entry_i"]
    return (
        format_summary(s)
        + f"\n  average winner {trades.loc[trades['r'] > 0, 'pct'].mean():+.2f}% | "
        f"average loser {trades.loc[trades['r'] <= 0, 'pct'].mean():+.2f}% | "
        f"risk per trade {trades['stop_pct'].mean():.2f}% of price"
        + f"\n  held {held.mean():.0f} bars on average, longest {held.max():.0f} | "
        f"{trades['reason'].value_counts().to_dict()}"
        + skip_report(trades)
    )


def sweep(df: pd.DataFrame, fixed: dict) -> pd.DataFrame:
    keys = list(GRID)
    clash = set(keys) & set(fixed)
    if clash:
        fixed = {k: v for k, v in fixed.items() if k not in clash}
    rows = []
    for combo in itertools.product(*(GRID[k] for k in keys)):
        cfg = dict(zip(keys, combo))
        # the grid wins over the command-line defaults: a swept key must actually vary
        p = Params(**{**fixed, **cfg})
        rows.append({**cfg, **summarise(simulate(df, p))})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--max-stop-pct", type=float, default=1.5)
    ap.add_argument("--min-target-pct", type=float, default=3.0)
    ap.add_argument("--longs-only", action="store_true")
    ap.add_argument("--high-mode", default="pivot", choices=["pivot", "running"])
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--trades-out", default=None)
    args = ap.parse_args()

    df = load(args.data)
    print(f"{df['time'].min()} to {df['time'].max()} ({len(df):,} bars)")
    print(contiguity(df))

    fixed = {
        "cost_bps": args.cost_bps,
        "max_stop_pct": args.max_stop_pct,
        "min_target_pct": args.min_target_pct,
        "allow_short": not args.longs_only,
        "high_mode": args.high_mode,
    }

    if not args.sweep:
        trades = simulate(df, Params(**fixed))
        print(describe(trades))
        if args.trades_out and len(trades):
            trades.to_csv(args.trades_out, index=False)
            print(f"trades written to {args.trades_out}")
        return

    res = sweep(df, fixed)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "reports", "fib_sweep.csv")
    res.to_csv(out, index=False)
    traded = res[res["trades"] >= 10].sort_values("mean_r", ascending=False)
    print(f"{len(res)} configurations, {len(traded)} of them took at least 10 trades\n")
    if not len(traded):
        print("Nothing reached ten trades. Either the gates are too tight for this "
              "sample, or the sample is too short.")
        print(f"total trades across the whole grid: {int(res['trades'].sum())}")
        return
    print("best:\n", traded[COLS].head(8).to_string(index=False))
    print("\nworst:\n", traded[COLS].tail(5).to_string(index=False))
    print(f"\nacross every configuration with at least ten trades: "
          f"median mean_r {traded['mean_r'].median():+.3f}, "
          f"{(traded['mean_r'] > 0).mean():.0%} of them profitable, "
          f"{int(traded['trades'].sum()):,} trades in total")
    print(f"\nfull grid written to {out}")


if __name__ == "__main__":
    main()
