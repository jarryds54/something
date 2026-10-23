"""Performance statistics, including how confident we can be that an edge is real."""
import numpy as np
import pandas as pd


def summarise(trades: pd.DataFrame, n_boot: int = 4000, seed: int = 0) -> dict:
    if trades is None or len(trades) == 0:
        return {"trades": 0}
    r = trades["r"].to_numpy(dtype=float)
    wins, losses = r[r > 0], r[r <= 0]
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    drawdown = equity - peak

    rng = np.random.default_rng(seed)
    boot = rng.choice(r, size=(n_boot, len(r)), replace=True).mean(axis=1)

    se = r.std(ddof=1) / np.sqrt(len(r)) if len(r) > 1 else np.nan
    return {
        "trades": int(len(r)),
        "win_rate": float((r > 0).mean()),
        "mean_r": float(r.mean()),
        "total_r": float(r.sum()),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else np.inf,
        "max_dd_r": float(drawdown.min()),
        "t_stat": float(r.mean() / se) if se and se > 0 else np.nan,
        "ci_low": float(np.quantile(boot, 0.025)),
        "ci_high": float(np.quantile(boot, 0.975)),
        "p_edge_positive": float((boot > 0).mean()),
        "longs": int((trades["dir"] == 1).sum()),
        "shorts": int((trades["dir"] == -1).sum()),
        "avg_risk": float(trades["risk"].mean()),
        "avg_bars_held": float((trades["exit_i"] - trades["entry_i"]).mean()),
        "pct_ambiguous": float(trades["reason"].str.startswith("ambiguous").mean()),
    }


def format_summary(s: dict) -> str:
    if not s.get("trades"):
        return "no trades"
    return (
        f"{s['trades']} trades | win {s['win_rate']:.1%} | mean {s['mean_r']:+.3f}R "
        f"[95% CI {s['ci_low']:+.3f} to {s['ci_high']:+.3f}] | total {s['total_r']:+.1f}R | "
        f"PF {s['profit_factor']:.2f} | maxDD {s['max_dd_r']:.1f}R | "
        f"avg stop ${s['avg_risk']:.2f}"
    )
