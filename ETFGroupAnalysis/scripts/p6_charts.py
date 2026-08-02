"""Summary figure for the ETF group analysis."""

from __future__ import annotations

import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import OUT, SYMBOLS, TRADING_DAYS, load_raw, session_ohlc

warnings.filterwarnings("ignore")

raw = {s: load_raw(s) for s in SYMBOLS}
sess = {s: session_ohlc(raw[s]) for s in SYMBOLS}
common = sorted(set.intersection(*[set(sess[s].index) for s in SYMBOLS]))
k = {s: sess[s].loc[common] for s in SYMBOLS}
ov = {s: np.log(k[s]["open"] / k[s]["close"].shift(1)).dropna() for s in SYMBOLS}
idy = {s: np.log(k[s]["close"] / k[s]["open"]).loc[ov[s].index] for s in SYMBOLS}
full = {s: np.log(k[s]["close"] / k[s]["close"].shift(1)).dropna() for s in SYMBOLS}
rv21 = full["SPXL"].rolling(21).std() * np.sqrt(TRADING_DAYS)
gate = (rv21.shift(1) < 0.45).reindex(ov["SPXL"].index).fillna(False)

C = {"SPXL": "#3b6ea8", "FAS": "#c47b20", "VXX": "#8b3a3a",
     "gate": "#2f7d52", "bh": "#777777"}
fig, ax = plt.subplots(2, 3, figsize=(17, 9))
fig.suptitle("SPXL / FAS / VXX — 5-minute data, 2020-07-23 to 2026-07-22 (1,506 sessions)",
             fontsize=13, weight="bold")

# 1. price paths, log scale, normalized
a = ax[0, 0]
for s in SYMBOLS:
    a.plot(k[s].index, k[s]["close"] / k[s]["close"].iloc[0], color=C[s], lw=1.2, label=s)
a.set_yscale("log"); a.legend(frameon=False); a.set_title("Cumulative growth of $1 (log)")
a.axhline(1, color="k", lw=0.5, ls=":"); a.grid(alpha=0.25)

# 2. overnight vs intraday
a = ax[0, 1]
for s in SYMBOLS:
    a.plot(ov[s].index, ov[s].cumsum(), color=C[s], lw=1.3, label=f"{s} overnight")
    a.plot(idy[s].index, idy[s].cumsum(), color=C[s], lw=1.0, ls="--", alpha=0.7,
           label=f"{s} intraday")
a.legend(frameon=False, fontsize=7, ncol=2); a.axhline(0, color="k", lw=0.5)
a.set_title("Overnight vs intraday, cumulative log return"); a.grid(alpha=0.25)

# 3. rolling correlation
a = ax[0, 2]
rd = pd.DataFrame({s: full[s] for s in SYMBOLS}).dropna()
a.plot(rd.index, rd["SPXL"].rolling(60).corr(rd["FAS"]), color="#3b6ea8", lw=1.1,
       label="SPXL~FAS")
a.plot(rd.index, rd["SPXL"].rolling(60).corr(rd["VXX"]), color="#8b3a3a", lw=1.1,
       label="SPXL~VXX")
a.plot(rd.index, rd["FAS"].rolling(60).corr(rd["VXX"]), color="#c47b20", lw=1.1,
       label="FAS~VXX")
a.axhline(0, color="k", lw=0.5); a.legend(frameon=False, fontsize=8)
a.set_title("60-day rolling correlation"); a.set_ylim(-1, 1); a.grid(alpha=0.25)

# 4. VXX holding-period distribution
a = ax[1, 0]
v = k["VXX"]["close"]
hs = [1, 5, 10, 20, 40, 60]
data = [(v.shift(-h) / v - 1).dropna().values * 100 for h in hs]
bp = a.boxplot(data, showfliers=False, patch_artist=True, tick_labels=[f"{h}d" for h in hs])
for b in bp["boxes"]:
    b.set_facecolor("#8b3a3a"); b.set_alpha(0.45)
a.axhline(0, color="k", lw=0.8)
a.set_title("VXX holding-period return (%)\nmedian negative at every horizon")
a.grid(alpha=0.25, axis="y")

# 5. VXX hedge sweep
a = ax[1, 1]
base = 0.5 * full["SPXL"] + 0.5 * full["FAS"]
ws = np.array([0, .01, .02, .03, .05, .075, .10, .15, .20, .33])
shp, dds = [], []
for w in ws:
    r = (1 - w) * base + w * full["VXX"]
    shp.append(r.mean() / r.std() * np.sqrt(TRADING_DAYS))
    eq = np.exp(r.cumsum()); dds.append((eq / eq.cummax() - 1).min())
a.plot(ws * 100, shp, "o-", color="#3b6ea8", label="Sharpe")
a.set_xlabel("VXX weight (%)"); a.set_ylabel("Sharpe", color="#3b6ea8")
a2 = a.twinx(); a2.plot(ws * 100, np.array(dds) * 100, "s--", color="#8b3a3a",
                        label="max drawdown")
a2.set_ylabel("max drawdown (%)", color="#8b3a3a")
a.set_title("VXX as a hedge: Sharpe falls,\ndrawdown barely improves"); a.grid(alpha=0.25)

# 6. strategy equity curves
a = ax[1, 2]
curves = {
    "SPXL buy & hold": full["SPXL"],
    "SPXL overnight only": ov["SPXL"],
    "SPXL overnight, vol-gated": ov["SPXL"].where(gate, 0.0),
    "SPXL+FAS+VXX equal wt": (full["SPXL"] + full["FAS"] + full["VXX"]) / 3,
}
for (nm, r), col in zip(curves.items(), [C["bh"], C["SPXL"], C["gate"], C["VXX"]]):
    a.plot(r.index, r.cumsum(), lw=1.4, color=col, label=nm)
a.axvline(pd.Timestamp("2023-12-31"), color="k", ls=":", lw=1)
a.text(pd.Timestamp("2024-01-15"), a.get_ylim()[0] + 0.1, "out-of-sample →", fontsize=7)
a.legend(frameon=False, fontsize=8); a.axhline(0, color="k", lw=0.5)
a.set_title("Cumulative log return by strategy"); a.grid(alpha=0.25)

plt.tight_layout()
p = OUT / "summary.png"
plt.savefig(p, dpi=130, bbox_inches="tight")
print(f"[saved] {p}")
