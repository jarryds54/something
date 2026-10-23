"""Final comparison: the rules as described, against the rules plus a volatility filter."""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, "/home/user/something/src")
from engine import Params, simulate  # noqa: E402

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BASE_C, FILT_C = "#86b6ef", "#1c5cab"  # same hue, light = fewer filters
CFG = dict(trend="slope", trend_len=10, wick_tol=0.0, wait_bars=7,
           stop_mode="pivot", buffer_atr=0.0,
           use_bar_spread=True, commission=0.07, stop_slip=0.10)


def draw(df, out_path):
    runs = {
        "as described": simulate(df, Params(**CFG)),
        "+ volatility filter": simulate(df, Params(**CFG, atr_pct_min=0.4)),
    }
    bounds = [pd.to_datetime(df["time"]).iloc[int(len(df) * f)] for f in (0.50, 0.75)]

    fig, ax = plt.subplots(figsize=(10, 5.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.axhline(0, color=INK_2, linewidth=1, alpha=0.5)

    for b, label in zip(bounds, ("validate", "holdout")):
        ax.axvline(b, color=INK_2, linewidth=1, linestyle=(0, (4, 3)), alpha=0.55)
        ax.annotate(label, xy=(b, ax.get_ylim()[1]), xytext=(5, -4),
                    textcoords="offset points", color=INK_2, fontsize=9, va="top")

    for (name, t), colour in zip(runs.items(), (BASE_C, FILT_C)):
        x = pd.to_datetime(t["entry_time"])
        y = t["r"].cumsum()
        ax.plot(x, y, color=colour, linewidth=2, solid_capstyle="round", label=name)
        ax.annotate(f"{name}  {y.iloc[-1]:+.0f}R", xy=(x.iloc[-1], y.iloc[-1]),
                    xytext=(6, -3), textcoords="offset points", color=colour,
                    fontsize=9.5)

    ax.set_title("Cumulative result, charging the spread recorded on each bar "
                 "plus $7/lot and 10c of stop slippage",
                 color=INK, fontsize=11.5, loc="left", pad=10)
    ax.set_ylabel("cumulative R", color=INK_2, fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend(frameon=False, labelcolor=INK_2, fontsize=9.5, loc="upper left")
    ax.margins(x=0.14)
    fig.suptitle("Your rules on your own broker's data, with your own costs",
                 color=INK, fontsize=14.5, fontweight="bold", x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    print("wrote", out_path)


if __name__ == "__main__":
    data = pd.read_csv("/home/user/something/data/xauusd_5m_fp.csv", parse_dates=["time"])
    draw(data, "/home/user/something/reports/fundingpips_result.png")
