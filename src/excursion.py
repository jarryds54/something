"""Where do these trades actually go?

For every entry the baseline rules produce, measure how far price travelled in
favour (MFE) and against (MAE) over a fixed horizon, expressed in units of the
initial risk. This says what targets and stops are even available, before any
management rule is invented.
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/something/src")
from engine import Params, add_indicators, simulate, validate_bars  # noqa: E402


def excursions(df: pd.DataFrame, p: Params, horizon: int = 288) -> pd.DataFrame:
    """Re-walk each trade's entry, ignoring its exit, for `horizon` bars."""
    trades = simulate(df, p)
    if trades.empty:
        return trades
    d = add_indicators(validate_bars(df), p)
    hi, lo = d["high"].to_numpy(), d["low"].to_numpy()
    n = len(d)

    rows = []
    for _, t in trades.iterrows():
        i = int(t["entry_i"])
        j = min(n, i + horizon + 1)
        direction, entry, risk = int(t["dir"]), float(t["entry"]), float(t["risk"])
        fav = (hi[i:j] - entry) if direction == 1 else (entry - lo[i:j])
        adv = (entry - lo[i:j]) if direction == 1 else (hi[i:j] - entry)
        # running extremes, so we can ask "did it reach X R before falling Y R?"
        run_fav = np.maximum.accumulate(fav) / risk
        run_adv = np.maximum.accumulate(adv) / risk
        row = {"entry_time": t["entry_time"], "dir": direction, "risk": risk,
               "mfe": run_fav[-1], "mae": run_adv[-1]}
        # first bar at which each threshold was reached (inf if never)
        for lvl in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0):
            reach = np.argmax(run_fav >= lvl) if (run_fav >= lvl).any() else -1
            row[f"bars_to_{lvl}R"] = reach if reach >= 0 else np.inf
            stopped = np.argmax(run_adv >= 1.0) if (run_adv >= 1.0).any() else -1
            row["bars_to_stop"] = stopped if stopped >= 0 else np.inf
            row[f"reached_{lvl}R"] = bool((run_fav >= lvl).any())
        rows.append(row)
    return pd.DataFrame(rows)


def summarise_excursions(ex: pd.DataFrame) -> str:
    out = [f"{len(ex)} entries, horizon-bounded excursions in units of initial risk", ""]
    out.append(f"  MFE: median {ex['mfe'].median():.2f}R, mean {ex['mfe'].mean():.2f}R, "
               f"75th {ex['mfe'].quantile(.75):.2f}R, 90th {ex['mfe'].quantile(.90):.2f}R")
    out.append(f"  MAE: median {ex['mae'].median():.2f}R, mean {ex['mae'].mean():.2f}R, "
               f"75th {ex['mae'].quantile(.75):.2f}R")
    out.append("")
    out.append("  reached before the horizon ran out:")
    for lvl in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0):
        share = ex[f"reached_{lvl}R"].mean()
        # of those that got there, how many got there before taking a full 1R hit?
        got = ex[ex[f"reached_{lvl}R"]]
        first = (got[f"bars_to_{lvl}R"] < got["bars_to_stop"]).mean() if len(got) else np.nan
        out.append(f"    {lvl:.1f}R: {share:6.1%} of trades   "
                   f"(of those, {first:5.1%} reached it before a 1R adverse move)")
    return "\n".join(out)
