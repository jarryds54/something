"""Pull IBKR price-history payloads out of the Claude Code session transcript.

The MCP tool returns bars as a JSON blob; the transcript on disk keeps a verbatim
copy, so we can recover the series without re-requesting it.
"""
import argparse
import glob
import json
import re

import pandas as pd

BLOB = re.compile(r'\{"chart_step".*?\"low\":\[[^\]]*\]\}', re.S)


def iter_payloads(transcript_glob):
    for path in glob.glob(transcript_glob):
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                for match in BLOB.finditer(line):
                    raw = match.group(0)
                    # transcript stores the blob inside a JSON string, so quotes are escaped
                    raw = raw.replace('\\"', '"').replace("\\n", "")
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        continue


def to_frame(payloads, step=None):
    """Combine payloads of a single bar size; mixing sizes would alias timestamps."""
    frames = []
    for p in payloads:
        if not p.get("time"):
            continue
        if step is not None and p.get("chart_step") != step:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "time": pd.to_datetime(p["time"], utc=True),
                    "open": p["open"],
                    "high": p["high"],
                    "low": p["low"],
                    "close": p["close"],
                    "step": p["chart_step"],
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "step"])
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", default="/root/.claude/projects/*/*.jsonl")
    ap.add_argument("--step", type=int, default=300, help="bar size in seconds to keep")
    ap.add_argument("--out", default="/home/user/something/data/xauusd_5m.csv")
    args = ap.parse_args()

    df = to_frame(iter_payloads(args.transcript), step=args.step).drop(columns=["step"])
    df.to_csv(args.out, index=False)
    print(f"{len(df)} bars -> {args.out}")
    if len(df):
        print(df["time"].min(), "->", df["time"].max())
