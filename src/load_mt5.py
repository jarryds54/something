"""Read a MetaTrader 5 bar export into the engine's CSV format.

MT5 exports are tab-separated with a header like:
    <DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>
Older builds and the chart "Save As" route use slightly different headers, and
some exports put date and time in one column, so detection is kept flexible.

Timestamps are broker server time. --tz-shift converts them to UTC; the
inspect mode guesses the offset from where the weekend gap falls.
"""
import argparse

import numpy as np
import pandas as pd


def _clean(name: str) -> str:
    return name.strip().strip("<>").lower()


def read_mt5(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [_clean(c) for c in df.columns]

    if "date" in df.columns and "time" in df.columns:
        stamp = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
    elif "datetime" in df.columns:
        stamp = df["datetime"].astype(str)
    elif "time" in df.columns:
        stamp = df["time"].astype(str)
    else:
        raise ValueError(f"no date/time column found in {list(df.columns)}")

    out = pd.DataFrame({"time": pd.to_datetime(stamp.str.replace(".", "-", regex=False),
                                               format="mixed", utc=True)})
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"missing {col!r}; found {list(df.columns)}")
        out[col] = pd.to_numeric(df[col], errors="coerce")
    if "tickvol" in df.columns:
        out["tickvol"] = pd.to_numeric(df["tickvol"], errors="coerce")
    if "spread" in df.columns:
        out["spread"] = pd.to_numeric(df["spread"], errors="coerce")

    out = out.dropna(subset=["open", "high", "low", "close"])
    return out.sort_values("time").drop_duplicates("time").reset_index(drop=True)


def guess_server_offset(df: pd.DataFrame) -> int:
    """Infer the broker's UTC offset from where the weekly gap sits.

    The market closes 21:00 UTC Friday and reopens 21:00 UTC Sunday, so the last
    bar of the broker's trading week tells us the shift.
    """
    t = df["time"]
    friday_last = t[t.dt.dayofweek == 4].dt.hour
    if friday_last.empty:
        return 0
    typical_close_hour = int(friday_last.mode().iat[0])
    return int((typical_close_hour + 1 - 21) % 24)


def report(df: pd.DataFrame) -> str:
    gaps = df["time"].diff().dropna()
    step = gaps.mode().iat[0]
    big = gaps[gaps > step * 3]
    return (
        f"{len(df):,} bars, {df['time'].min()} to {df['time'].max()}\n"
        f"modal spacing {step}, {len(big)} gaps longer than 3 bars "
        f"(weekends account for about {len(df) // (5 * 288)} of them)\n"
        f"apparent broker offset from UTC: +{guess_server_offset(df)}h\n"
        f"price range {df['low'].min():.2f} to {df['high'].max():.2f}"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--out", default="/home/user/something/data/xauusd_5m_mt5.csv")
    ap.add_argument("--tz-shift", type=int, default=None,
                    help="hours to subtract to reach UTC; omit to auto-detect")
    args = ap.parse_args()

    df = read_mt5(args.path)
    shift = args.tz_shift if args.tz_shift is not None else guess_server_offset(df)
    df["time"] = df["time"] - pd.Timedelta(hours=shift)
    print(report(df))
    df.to_csv(args.out, index=False)
    print(f"-> {args.out} (shifted {shift}h to UTC)")
