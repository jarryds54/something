"""Systematic exploration of entry, exit and management variations.

Everything is judged on train and validate. A variant counts as surviving only if
it beats the baseline on BOTH, which kills most of them. The holdout stays shut.
"""
import itertools
import sys

import pandas as pd

sys.path.insert(0, "/home/user/something/src")
from engine import Params, simulate  # noqa: E402
from metrics import summarise  # noqa: E402
from protocol import slice_of  # noqa: E402

COSTS = dict(use_bar_spread=True, commission=0.07, stop_slip=0.10)
BASE = dict(trend="slope", trend_len=10, wick_tol=0.0, wait_bars=7,
            stop_mode="pivot", buffer_atr=0.0, atr_pct_min=0.4, **COSTS)


def families():
    f = {}

    f["baseline"] = [("as it stands", {})]

    f["target size"] = [(f"rr {rr}", dict(rr=rr))
                        for rr in (0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)]

    f["stop geometry"] = (
        [(f"pivot k={k}", dict(pivot_k=k)) for k in (2, 3, 5)]
        + [(f"buffer {b} ATR", dict(buffer_atr=b)) for b in (0.1, 0.25, 0.5, 1.0)]
        + [(f"lookback {lb}", dict(stop_lookback=lb)) for lb in (10, 30, 50)]
        + [(f"atr stop {m}x", dict(stop_mode="atr", atr_mult=m)) for m in (1.0, 1.5, 2.0, 3.0)]
        + [(f"bars stop {lb}", dict(stop_mode="bars", stop_lookback=lb)) for lb in (10, 20, 50)]
    )

    f["breakeven"] = [
        (f"BE at {t}R offset {o}", dict(be_trigger_r=t, be_offset_r=o))
        for t, o in itertools.product((0.3, 0.5, 0.75, 1.0), (0.0, 0.1))
    ]

    f["trailing"] = (
        [(f"ATR trail {m}x from {s}R", dict(trail_mode="atr", trail_atr_mult=m,
                                            trail_start_r=s, rr=5.0))
         for m, s in itertools.product((1.0, 1.5, 2.0, 3.0), (0.0, 0.5, 1.0, 2.0))]
        + [(f"structure trail from {s}R", dict(trail_mode="structure",
                                               trail_start_r=s, rr=5.0))
           for s in (0.0, 0.5, 1.0, 2.0)]
    )

    f["partials"] = [
        (f"{int(fr*100)}% at {pr}R, rest to {rr}R",
         dict(partial_r=pr, partial_frac=fr, rr=rr))
        for pr, fr, rr in itertools.product((0.5, 1.0, 1.5), (0.25, 0.5, 0.75), (2.0, 3.0))
    ] + [
        (f"{int(fr*100)}% at {pr}R, rest trailing",
         dict(partial_r=pr, partial_frac=fr, rr=10.0, trail_mode="atr",
              trail_atr_mult=2.0, trail_start_r=pr))
        for pr, fr in itertools.product((0.5, 1.0, 1.5), (0.25, 0.5, 0.75))
    ]

    f["time stop"] = [(f"give up after {n} bars", dict(time_stop_bars=n))
                      for n in (12, 24, 48, 96)]

    f["entry context"] = (
        [("require imbalance", dict(require_fvg=True))]
        + [(f"{tf}m {kind} trend", dict(htf_trend=kind, htf_minutes=tf))
           for kind, tf in itertools.product(("ema", "structure"), (15, 60, 240))]
        + [(f"body >= {b} ATR", dict(body_min_atr=b)) for b in (0.25, 0.5, 0.75)]
        + [(f"wick tol {w}", dict(wick_tol=w)) for w in (0.01, 0.02)]
        + [(f"wait {w} candles", dict(wait_bars=w)) for w in (3, 5, 10, 15)]
        + [(f"trend {t}", dict(trend=t)) for t in ("ema", "structure")]
        + [(f"trend_len {n}", dict(trend_len=n)) for n in (5, 15, 20, 30)]
        + [(f"vol band {lo}-{hi}", dict(atr_pct_min=lo, atr_pct_max=hi))
           for lo, hi in ((0.3, 1.0), (0.5, 1.0), (0.4, 0.9), (0.6, 1.0))]
        + [("allow overlapping trades", dict(allow_concurrent=True))]
    )
    return f


def run(df, variants, label):
    rows = []
    for name, kw in variants:
        cfg = {**BASE, **kw}
        out = {"family": label, "variant": name}
        for part in ("train", "validate"):
            s = summarise(simulate(slice_of(df, part), Params(**cfg)))
            out[f"{part}_trades"] = s.get("trades", 0)
            out[f"{part}_win"] = s.get("win_rate", float("nan"))
            out[f"{part}_mean_r"] = s.get("mean_r", float("nan"))
            out[f"{part}_total_r"] = s.get("total_r", float("nan"))
        rows.append(out)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = pd.read_csv("/home/user/something/data/xauusd_5m_fp.csv", parse_dates=["time"])
    all_rows = [run(df, v, name) for name, v in families().items()]
    res = pd.concat(all_rows, ignore_index=True)
    res.to_csv("/home/user/something/reports/experiments.csv", index=False)

    base = res[res.variant == "as it stands"].iloc[0]
    print(f"baseline: train {base.train_mean_r:+.4f}R ({int(base.train_trades)} trades), "
          f"validate {base.validate_mean_r:+.4f}R ({int(base.validate_trades)} trades)\n")

    res["beats_both"] = ((res.train_mean_r > base.train_mean_r)
                         & (res.validate_mean_r > base.validate_mean_r)
                         & (res.train_trades >= 60) & (res.validate_trades >= 30))
    for fam in res.family.unique():
        sub = res[res.family == fam].sort_values("validate_mean_r", ascending=False)
        print(f"=== {fam} ===")
        for _, r in sub.head(6).iterrows():
            mark = "  <-- beats baseline on both" if r.beats_both else ""
            print(f"  {r.variant:34s} train {r.train_mean_r:+.4f}R ({int(r.train_trades):4d}) | "
                  f"validate {r.validate_mean_r:+.4f}R ({int(r.validate_trades):4d}){mark}")
        print()
    print("SURVIVORS (better than baseline on both splits):")
    surv = res[res.beats_both].sort_values("validate_mean_r", ascending=False)
    for _, r in surv.iterrows():
        print(f"  {r.family:16s} {r.variant:34s} "
              f"train {r.train_mean_r:+.4f}R | validate {r.validate_mean_r:+.4f}R")
    print(f"\n{len(surv)} survivors out of {len(res)} variants tested")
