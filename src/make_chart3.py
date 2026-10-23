"""Three ways to manage the same entries, on FundingPips data with real costs."""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/something/src")
from engine import Params, simulate  # noqa: E402
from experiments import BASE  # noqa: E402

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
VARIANTS = {
    "your rules, 1:1": ({}, "#2a78d6"),
    "target 2.5R": (dict(rr=2.5), "#eb6834"),
    "trail 2xATR from 2.5R": (dict(rr=10.0, trail_mode="atr", trail_atr_mult=2.0,
                                   trail_start_r=2.5), "#1baf7a"),
}


def draw(df, out_path):
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 8.4), height_ratios=[1.5, 1],
                                  facecolor=SURFACE, sharex=True)
    for a in (ax, ax2):
        a.set_facecolor(SURFACE)
        a.grid(True, color=GRID, linewidth=0.8)
        a.set_axisbelow(True)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            a.spines[side].set_color(GRID)
        a.tick_params(colors=INK_2, labelsize=9)
        a.axhline(0, color=INK_2, linewidth=1, alpha=0.5)

    for name, (cfg, colour) in VARIANTS.items():
        t = simulate(df, Params(**{**BASE, **cfg}))
        x = pd.to_datetime(t["entry_time"])
        eq = t["r"].cumsum().to_numpy()
        peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
        ax.plot(x, eq, color=colour, linewidth=2, solid_capstyle="round", label=name)
        ax.annotate(f"{eq[-1]:+.0f}R", xy=(x.iloc[-1], eq[-1]), xytext=(6, -3),
                    textcoords="offset points", color=colour, fontsize=9.5)
        ax2.plot(x, eq - peak, color=colour, linewidth=1.6, solid_capstyle="round")

    ax.set_title("Cumulative result, with your measured spreads and commission",
                 color=INK, fontsize=12, loc="left", pad=10)
    ax.set_ylabel("cumulative R", color=INK_2, fontsize=10)
    ax.legend(frameon=False, labelcolor=INK_2, fontsize=9.5, loc="upper left")
    ax2.set_title("Drawdown — the price of the extra return",
                  color=INK, fontsize=12, loc="left", pad=10)
    ax2.set_ylabel("R below peak", color=INK_2, fontsize=10)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.margins(x=0.1)
    fig.suptitle("Wider targets earn more and hurt more", color=INK, fontsize=14.5,
                 fontweight="bold", x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    print("wrote", out_path)


if __name__ == "__main__":
    data = pd.read_csv("/home/user/something/data/xauusd_5m_fp.csv", parse_dates=["time"])
    draw(data, "/home/user/something/reports/variants.png")
