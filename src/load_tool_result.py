"""Turn saved IBKR price-history payloads into tidy CSV bars."""
import argparse
import glob
import json
import os

import pandas as pd


def payload_to_frame(path: str) -> pd.DataFrame:
    with open(path) as fh:
        d = json.load(fh)
    df = pd.DataFrame(
        {
            "time": pd.to_datetime(d["time"], utc=True),
            "open": d["open"],
            "high": d["high"],
            "low": d["low"],
            "close": d["close"],
        }
    )
    df["source_file"] = os.path.basename(path)
    df["step"] = d["chart_step"]
    return df


def combine(paths, step=300) -> pd.DataFrame:
    frames = [payload_to_frame(p) for p in paths]
    frames = [f for f in frames if not f.empty and f["step"].iat[0] == step]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).drop(columns=["step"])
    return df.sort_values("time").drop_duplicates("time", keep="first").reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    paths = sorted(glob.glob(args.glob))
    df = combine(paths)
    df.to_csv(args.out, index=False)
    print(f"{len(paths)} files -> {len(df):,} bars -> {args.out}")
    if len(df):
        print(df["time"].min(), "->", df["time"].max())
