"""Two panels for the Fibonacci strategy report: the equity path, and how much of it
depends on which reading of the rules you pick."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fib_engine import Params, simulate  # noqa: E402
from run_fib import load  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#dedcd6"
SERIES = {"pivot": "#2a78d6", "running": "#eb6834"}
LABEL = {"pivot": "confirmed swing", "running": "running high"}


def main(data: str, sweep_csv: str, out: str) -> None:
    df = load(data)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.8), facecolor=SURFACE)

    for ax in (ax1, ax2):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=INK_SOFT, labelsize=9, length=3)
        ax.grid(True, color=GRID, linewidth=0.6, alpha=0.9)
        ax.set_axisbelow(True)

    # --- left: the equity path under each reading of "the last high" ---
    for mode, colour in SERIES.items():
        t = simulate(df, Params(high_mode=mode))
        if not len(t):
            continue
        eq = np.concatenate([[0.0], np.cumsum(t["r"].to_numpy())])
        x = np.arange(len(eq))
        ax1.plot(x, eq, color=colour, linewidth=2.0, solid_capstyle="round",
                 label=f"{LABEL[mode]} ({len(t)} trades)")
        ax1.annotate(f"{eq[-1]:+.1f}R", (x[-1], eq[-1]), xytext=(6, 0),
                     textcoords="offset points", color=INK, fontsize=9,
                     va="center", fontweight="medium")
    ax1.axhline(0, color=INK_SOFT, linewidth=1.0, alpha=0.5)
    ax1.set_xlabel("trades taken", color=INK_SOFT, fontsize=9)
    ax1.set_ylabel("cumulative result (R)", color=INK_SOFT, fontsize=9)
    ax1.set_title("The same rules, two readings of \"the last high\"",
                  color=INK, fontsize=11, loc="left", pad=12)
    leg = ax1.legend(frameon=False, fontsize=9, loc="upper left")
    for text in leg.get_texts():
        text.set_color(INK_SOFT)
    ax1.set_xlim(left=0)
    ax1.margins(x=0.12)

    # --- right: the spread of outcomes across every reading of the rules ---
    res = pd.read_csv(sweep_csv)
    traded = res[res["trades"] >= 10]
    ax2.hist(traded["mean_r"], bins=24, color=SERIES["pivot"], alpha=0.85,
             edgecolor=SURFACE, linewidth=1.0)
    ax2.axvline(0, color=INK_SOFT, linewidth=1.2)
    median = traded["mean_r"].median()
    ax2.axvline(median, color=SERIES["running"], linewidth=2.0)
    ax2.annotate(f"median {median:+.2f}R", (median, ax2.get_ylim()[1] * 0.92),
                 xytext=(8, 0), textcoords="offset points",
                 color=INK, fontsize=9, va="top")
    share = (traded["mean_r"] > 0).mean()
    ax2.set_xlabel("average result per trade (R)", color=INK_SOFT, fontsize=9)
    ax2.set_ylabel("configurations", color=INK_SOFT, fontsize=9)
    ax2.set_title(f"{len(traded)} readings of the rules, {share:.0%} of them profitable",
                  color=INK, fontsize=11, loc="left", pad=12)

    fig.suptitle("Fibonacci 0.5 retracement continuation - BTCUSD, 4-hour bars, one year",
                 color=INK, fontsize=12.5, x=0.009, ha="left", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(f"wrote {out}")


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    main(os.path.join(base, "data/btcusd_4h.csv"),
         os.path.join(base, "reports/fib_sweep_4h.csv"),
         os.path.join(base, "reports/fib_result.png"))
