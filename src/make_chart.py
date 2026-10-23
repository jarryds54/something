"""Equity curves at several cost levels, plus the cost-sensitivity curve."""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, "/home/user/something/src")
from engine import Params, simulate  # noqa: E402
from metrics import summarise  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
# ordered magnitude -> one hue, light to dark (ordinal steps 250/400/550/700)
RAMP = {0.00: "#86b6ef", 0.15: "#3987e5", 0.30: "#1c5cab", 0.50: "#0d366b"}

CFG = dict(trend="slope", trend_len=10, wick_tol=0.0, wait_bars=7,
           stop_mode="pivot", buffer_atr=0.0)


def build(df):
    curves, costs, means = {}, [], []
    for cost in RAMP:
        t = simulate(df, Params(**CFG, cost=cost))
        curves[cost] = (pd.to_datetime(t["entry_time"]), t["r"].cumsum())
    for cost in [c / 100 for c in range(0, 55, 5)]:
        costs.append(cost)
        means.append(summarise(simulate(df, Params(**CFG, cost=cost)))["mean_r"])
    return curves, costs, means


def draw(df, out_path):
    curves, costs, means = build(df)
    split_at = pd.to_datetime(df["time"]).iloc[int(len(df) * 0.6)]

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(10, 9), height_ratios=[1.45, 1], facecolor=SURFACE
    )

    for a in (ax, ax2):
        a.set_facecolor(SURFACE)
        a.grid(True, color=GRID, linewidth=0.8)
        a.set_axisbelow(True)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            a.spines[side].set_color(GRID)
        a.tick_params(colors=INK_2, labelsize=9)

    # --- equity curves ---
    ax.axhline(0, color=INK_2, linewidth=1, alpha=0.5)
    ax.axvline(split_at, color=INK_2, linewidth=1, linestyle=(0, (4, 3)), alpha=0.6)
    top = max(y.max() for _, y in curves.values())
    ax.annotate("out-of-sample from here", xy=(split_at, top), xytext=(6, -2),
                textcoords="offset points", color=INK_2, fontsize=9, va="top")
    for cost, colour in RAMP.items():
        x, y = curves[cost]
        ax.plot(x, y, color=colour, linewidth=2, solid_capstyle="round",
                label=f"${cost:.2f} round trip")
        ax.annotate(f"${cost:.2f}", xy=(x.iloc[-1], y.iloc[-1]), xytext=(6, -3),
                    textcoords="offset points", color=colour, fontsize=9.5,
                    fontweight="medium")
    ax.set_title("Cumulative result, in units of risk per trade",
                 color=INK, fontsize=13, fontweight="semibold", loc="left", pad=12)
    ax.set_ylabel("cumulative R", color=INK_2, fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend(frameon=False, labelcolor=INK_2, fontsize=9, loc="upper left")
    ax.margins(x=0.06)

    # --- cost sensitivity ---
    ax2.axhline(0, color=INK_2, linewidth=1, alpha=0.5)
    ax2.plot(costs, means, color="#1c5cab", linewidth=2, marker="o",
             markersize=5, solid_capstyle="round")
    breakeven = None  # interpolate the actual zero crossing, not the first negative sample
    for (c0, m0), (c1, m1) in zip(zip(costs, means), zip(costs[1:], means[1:])):
        if m0 >= 0 > m1:
            breakeven = c0 + (c1 - c0) * m0 / (m0 - m1)
            break
    if breakeven is not None:
        ax2.axvline(breakeven, color="#d03b3b", linewidth=1.5, linestyle=(0, (4, 3)))
        ax2.annotate(f"edge disappears near ${breakeven:.2f}", xy=(breakeven, max(means)),
                     xytext=(-8, -4), textcoords="offset points", ha="right",
                     color="#d03b3b", fontsize=9.5)
    ax2.set_title("Average result per trade against trading cost",
                  color=INK, fontsize=13, fontweight="semibold", loc="left", pad=12)
    ax2.set_xlabel("round-trip cost, dollars per ounce", color=INK_2, fontsize=10)
    ax2.set_ylabel("mean R per trade", color=INK_2, fontsize=10)

    fig.suptitle("Wickless retest on XAUUSD 5m: the edge is real but small, and costs consume it",
                 color=INK, fontsize=14.5, fontweight="bold", x=0.02, ha="left", y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    print("wrote", out_path)


if __name__ == "__main__":
    data = pd.read_csv("/home/user/something/data/xauusd_5m_mt5.csv", parse_dates=["time"])
    draw(data, "/home/user/something/reports/equity_curve.png")
