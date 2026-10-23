"""Phase two: combine the variants that survived, and see which combinations hold."""
import sys

import pandas as pd

sys.path.insert(0, "/home/user/something/src")
from engine import Params, simulate  # noqa: E402
from experiments import BASE  # noqa: E402
from metrics import summarise  # noqa: E402
from protocol import slice_of  # noqa: E402

TRAIL_ATR = dict(rr=10.0, trail_mode="atr", trail_atr_mult=2.0, trail_start_r=2.0)
TRAIL_STRUCT = dict(rr=10.0, trail_mode="structure", trail_start_r=2.0)

COMBOS = {
    "baseline (1:1)": {},
    "rr 2.0": dict(rr=2.0),
    "rr 2.5": dict(rr=2.5),
    "rr 1.5": dict(rr=1.5),
    "trail ATR from 2R": TRAIL_ATR,
    "trail structure from 2R": TRAIL_STRUCT,
    "rr2 + wide stop": dict(rr=2.0, stop_mode="bars", stop_lookback=50),
    "rr2 + imbalance": dict(rr=2.0, require_fvg=True),
    "rr2 + 15m structure": dict(rr=2.0, htf_trend="structure", htf_minutes=15),
    "trail ATR + imbalance": {**TRAIL_ATR, "require_fvg": True},
    "trail ATR + 15m structure": {**TRAIL_ATR, "htf_trend": "structure", "htf_minutes": 15},
    "trail struct + 15m struct": {**TRAIL_STRUCT, "htf_trend": "structure", "htf_minutes": 15},
    "trail ATR + 50% at 1.5R": {**TRAIL_ATR, "partial_r": 1.5, "partial_frac": 0.5},
    "trail ATR + 25% at 1.5R": {**TRAIL_ATR, "partial_r": 1.5, "partial_frac": 0.25},
    "rr3 + 50% at 1.5R": dict(rr=3.0, partial_r=1.5, partial_frac=0.5),
    "trail ATR + wide stop": {**TRAIL_ATR, "stop_mode": "bars", "stop_lookback": 50},
    "everything": {**TRAIL_ATR, "require_fvg": True, "htf_trend": "structure",
                   "htf_minutes": 15, "partial_r": 1.5, "partial_frac": 0.25},
    "rr2 + imbalance + 15m": dict(rr=2.0, require_fvg=True, htf_trend="structure",
                                  htf_minutes=15),
    "trail ATR, no vol filter": {**TRAIL_ATR, "atr_pct_min": 0.0},
    "rr2, no vol filter": dict(rr=2.0, atr_pct_min=0.0),
}


def evaluate(df, cfg, parts=("train", "validate")):
    return {part: summarise(simulate(slice_of(df, part), Params(**{**BASE, **cfg})))
            for part in parts}


if __name__ == "__main__":
    df = pd.read_csv("/home/user/something/data/xauusd_5m_fp.csv", parse_dates=["time"])
    rows = []
    for name, cfg in COMBOS.items():
        res = evaluate(df, cfg)
        rows.append({
            "combo": name,
            "tr_n": res["train"].get("trades", 0),
            "tr_win": res["train"].get("win_rate", float("nan")),
            "tr_r": res["train"].get("mean_r", float("nan")),
            "va_n": res["validate"].get("trades", 0),
            "va_win": res["validate"].get("win_rate", float("nan")),
            "va_r": res["validate"].get("mean_r", float("nan")),
            "tr_total": res["train"].get("total_r", float("nan")),
            "va_total": res["validate"].get("total_r", float("nan")),
        })
    out = pd.DataFrame(rows)
    out["worst"] = out[["tr_r", "va_r"]].min(axis=1)
    out = out.sort_values("worst", ascending=False)
    out.to_csv("/home/user/something/reports/combos.csv", index=False)
    pd.set_option("display.width", 200)
    print(out.round(3).to_string(index=False))
