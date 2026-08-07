"""Equity curves, drawdown, and the sticky-strike mechanism."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib; matplotlib.use("Agg")
matplotlib.rcParams["text.parse_math"] = False
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np, pandas as pd
import backtest as bt

OUT = bt.OUT
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2de"
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"


def load(n):
    return pd.read_csv(f"{OUT}/{n}.csv", parse_dates=["date"]).set_index("date")["equity"]


def spread(vals, gap):
    """Push label positions apart (axes fraction) keeping order, min separation `gap`."""
    order = np.argsort(vals)[::-1]
    out = np.array(vals, dtype=float)
    for i in range(1, len(order)):
        a, b = order[i - 1], order[i]
        if out[a] - out[b] < gap:
            out[b] = out[a] - gap
    return out


series = [
    ("Covered call + long put", "as specified", load("equity_base"), S1, 2.5),
    ("Covered call only", "no put", load("equity_cc_only"), S2, 1.5),
    ("Shares + long put only", "no calls", load("equity_put_only"), S3, 1.5),
    ("Buy & hold SOXL", "benchmark", load("equity_buyhold"), S4, 1.5),
]
led = pd.read_csv(f"{OUT}/ledger_base.csv", parse_dates=["date"])

fig = plt.figure(figsize=(14, 13), facecolor=SURF)
gs = fig.add_gridspec(3, 1, height_ratios=[2.4, 1.1, 1.3], hspace=0.42,
                      left=0.078, right=0.700, top=0.855, bottom=0.05)

# ---------- A: equity ----------
ax = fig.add_subplot(gs[0]); ax.set_facecolor(SURF)
for lab, sub, s, c, lw in series:
    ax.plot(s.index, s.values, color=c, lw=lw, solid_capstyle="round", zorder=3)
    ax.plot([s.index[-1]], [s.iloc[-1]], "o", ms=6.5, color=c, mec=SURF, mew=2, zorder=5)
ax.axhline(100_000, color=INK2, lw=1, ls=(0, (4, 4)), alpha=.5, zorder=2)
ax.set_yscale("log")
ax.set_ylim(8_500, 780_000)
ax.set_yticks([10_000, 25_000, 50_000, 100_000, 250_000, 500_000])
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"${v/1000:,.0f}k"))
ax.annotate("$100,000 start", xy=(series[0][2].index[3], 100_000), xytext=(2, 7),
            textcoords="offset points", fontsize=8.5, color=INK2)
# de-collided right-margin labels
ys = [(np.log10(s.iloc[-1]) - np.log10(8_500)) / (np.log10(780_000) - np.log10(8_500))
      for _, _, s, _, _ in series]
ys = spread(ys, 0.115)
for (lab, sub, s, c, lw), y in zip(series, ys):
    ax.annotate(f"{lab}\n${s.iloc[-1]:,.0f}  ·  {sub}",
                xy=(1.005, y), xycoords="axes fraction", va="center",
                fontsize=10, color=INK, linespacing=1.6)
    ax.annotate("", xy=(1.0, y), xytext=(1.0, ys[0] * 0 + y), xycoords="axes fraction")
    ax.plot([1.0], [y], "s", ms=7, color=c, transform=ax.transAxes,
            clip_on=False, zorder=6)
ax.set_title("Equity, $100,000 start   ·   log scale", fontsize=13, color=INK,
             loc="left", pad=12, fontweight="bold")

# ---------- B: drawdown ----------
ax2 = fig.add_subplot(gs[1]); ax2.set_facecolor(SURF)
dds = []
for lab, sub, s, c, lw in series:
    dd = (s / s.cummax() - 1) * 100
    ax2.plot(dd.index, dd.values, color=c, lw=lw, solid_capstyle="round", zorder=3)
    dds.append((lab, dd.min(), c))
ax2.set_ylim(-100, 8)
ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:.0f}%"))
for i, (lab, worst, c) in enumerate(sorted(dds, key=lambda t: -t[1])):
    y = 0.86 - i * 0.24
    ax2.plot([1.0], [y], "s", ms=7, color=c, transform=ax2.transAxes, clip_on=False, zorder=6)
    ax2.annotate(f"{lab}\nworst {worst:.0f}%", xy=(1.005, y), xycoords="axes fraction",
                 va="center", fontsize=9.5, color=INK, linespacing=1.6)
ax2.set_title("Drawdown from peak", fontsize=13, color=INK, loc="left",
              pad=12, fontweight="bold")

# ---------- C: mechanism ----------
ax3 = fig.add_subplot(gs[2]); ax3.set_facecolor(SURF)
w = led[led.act == "SELL_CALL"].copy()
fr, st = w[w.sticky_write == 0], w[w.sticky_write == 1]
ax3.scatter(st.date, st.otm_pct, s=20, color=S2, alpha=.8, edgecolors=SURF,
            linewidths=.6, zorder=3)
ax3.scatter(fr.date, fr.otm_pct, s=26, color=S1, edgecolors=SURF, linewidths=.9, zorder=4)
ax3.axhline(0, color=INK2, lw=1, alpha=.5, zorder=2)
ax3.set_yscale("symlog", linthresh=8)
ax3.set_ylim(-9, 2600)
ax3.set_yticks([0, 4, 8, 25, 100, 400])
ax3.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:.0f}%"))
for i, (c, ttl, sub) in enumerate([
        (S2, "Sticky re-write at the stranded old strike",
         "180 of 235 weeks · median +21.8% OTM\npremium 0.26% of spot"),
        (S1, "Fresh write after being called out",
         "55 weeks · median +3.4% OTM\npremium 3.10% of spot")]):
    y = 0.86 - i * 0.34
    ax3.plot([1.0], [y], "s", ms=7, color=c, transform=ax3.transAxes, clip_on=False, zorder=6)
    ax3.annotate(f"{ttl}\n{sub}", xy=(1.005, y), xycoords="axes fraction", va="center",
                 fontsize=9.5, color=INK, linespacing=1.6)
ax3.annotate("the income engine switches off exactly when the stock has fallen",
             xy=(0.012, 0.94), xycoords="axes fraction", fontsize=9.5, color=S2,
             linespacing=1.6, fontweight="bold")
ax3.set_title("Why the income dries up — how far OTM each weekly call was written",
              fontsize=13, color=INK, loc="left", pad=12, fontweight="bold")

for a in (ax, ax2, ax3):
    a.grid(axis="y", color=GRID, lw=.8, zorder=0)
    a.set_axisbelow(True)
    for sp in ("top", "right", "left"): a.spines[sp].set_visible(False)
    a.spines["bottom"].set_color(GRID)
    a.tick_params(colors=INK2, labelsize=9.5, length=0)
    a.set_xlim(pd.Timestamp("2021-12-20"), pd.Timestamp("2026-07-20"))

fig.text(0.078, 0.968, "SOXL covered call + long-dated protective put",
         ha="left", fontsize=17, color=INK, fontweight="bold")
fig.text(0.078, 0.940, "2022-01-03 → 2026-07-02  ·  235 weekly cycles  ·  $100,000 start, reinvested weekly",
         ha="left", fontsize=11, color=INK)
fig.text(0.078, 0.916, "Weekly call sold 2 listed strikes OTM at Monday 10:00 ET, same strike rewritten until called out  ·  "
         "~3-month put 2 strikes OTM, held to expiry",
         ha="left", fontsize=9.5, color=INK2)
fig.text(0.078, 0.896, "Real 5-min SOXL bars + real 5-min option trade prints  ·  $0.65/contract, $0.005/share and "
         "measured half-spread applied", ha="left", fontsize=9.5, color=INK2)
fig.savefig(f"{OUT}/cc_long_put.png", dpi=145, facecolor=SURF)
print("wrote", f"{OUT}/cc_long_put.png")
