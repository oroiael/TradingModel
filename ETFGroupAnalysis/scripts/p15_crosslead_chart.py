"""Summary figure for the cross-instrument leading-indicator study."""

from __future__ import annotations

import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import OUT

warnings.filterwarnings("ignore")

R = pd.read_csv(OUT / "p12_scan_results.csv")
maxes = np.load(OUT / "p12_boot_maxt.npy")
crit = np.percentile(maxes, 95)

fig, ax = plt.subplots(2, 2, figsize=(15, 9))
fig.suptitle("Cross-instrument leading indicators — 816 specifications, "
             "HAR-RV-controlled, family-wise corrected", fontsize=13, weight="bold")

# 1. t-stat distributions, direction vs magnitude, against the FWER null
a = ax[0, 0]
bins = np.linspace(0, 9, 46)
a.hist(R.loc[R["kind"] == "direction", "t_hac"].abs(), bins=bins, alpha=0.65,
       color="#777777", label="direction targets (408)")
a.hist(R.loc[R["kind"] == "magnitude", "t_hac"].abs(), bins=bins, alpha=0.75,
       color="#3b6ea8", label="magnitude targets (408)")
a.axvline(1.96, color="k", ls=":", lw=1.2, label="nominal 5% (|t|=1.96)")
a.axvline(crit, color="#b23a3a", ls="--", lw=1.8,
          label=f"family-wise 5% (|t|={crit:.2f})")
a.set_xlabel("|HAC t-statistic|"); a.set_ylabel("specifications")
a.set_title("Direction is noise; magnitude is not")
a.legend(frameon=False, fontsize=8); a.grid(alpha=0.25)

# 2. source -> target heatmap, magnitude only
a = ax[0, 1]
mag = R[R["kind"] == "magnitude"]
piv = mag.pivot_table(index="src", columns="tgt", values="abs_t", aggfunc="mean")
order = ["SPXL", "FAS", "VXX"]
piv = piv.reindex(index=order, columns=order)
im = a.imshow(piv.values, cmap="Blues", vmin=0, vmax=2.8)
a.set_xticks(range(3), order); a.set_yticks(range(3), order)
a.set_xlabel("TARGET (next-day realized vol)"); a.set_ylabel("SOURCE (day t-1)")
for i in range(3):
    for j in range(3):
        v = piv.values[i, j]
        if np.isfinite(v):
            a.text(j, i, f"{v:.2f}", ha="center", va="center",
                   color="white" if v > 1.8 else "black", fontsize=11, weight="bold")
        else:
            a.text(j, i, "—", ha="center", va="center", color="#999")
a.set_title("mean |t| by direction of flow\n(0.8 = pure noise)")
plt.colorbar(im, ax=a, fraction=0.046)

# 3. out-of-sample R2 gain, from p13
a = ax[1, 0]
labels = ["SPXL\n← VXX", "FAS\n← VXX", "FAS\n← SPXL", "SPXL\n← FAS"]
m1 = [51.73, 54.31, 54.31, 51.73]
m2 = [53.13, 56.20, 55.45, 51.79]
x = np.arange(4); w = 0.36
a.bar(x - w/2, m1, w, color="#9aa7b4", label="M1: HAR + own leverage")
a.bar(x + w/2, m2, w, color="#3b6ea8", label="M2: + cross-instrument")
for i, (lo, hi) in enumerate(zip(m1, m2)):
    a.text(i + w/2, hi + 0.15, f"+{hi-lo:.2f}", ha="center", fontsize=9,
           color="#2f7d52" if hi - lo > 0.5 else "#999")
a.set_xticks(x, labels); a.set_ylabel("out-of-sample R² (%)")
a.set_ylim(48, 58); a.legend(frameon=False, fontsize=8)
a.set_title("Forecast improvement is real and out-of-sample\n"
            "(reverse direction SPXL←FAS adds nothing)")
a.grid(alpha=0.25, axis="y")

# 4. but it does not translate economically
a = ax[1, 1]
groups = ["SPXL vol-target", "FAS vol-target"]
sh_m1 = [0.5222, 0.5318]
sh_m2 = [0.5283, 0.5250]
x = np.arange(2); w = 0.34
a.bar(x - w/2, sh_m1, w, color="#9aa7b4", label="sized off M1")
a.bar(x + w/2, sh_m2, w, color="#3b6ea8", label="sized off M2")
for i, (v1, v2) in enumerate(zip(sh_m1, sh_m2)):
    a.text(i + w/2, v2 + 0.008, f"{v2-v1:+.4f}", ha="center", fontsize=9, color="#b23a3a")
a.set_xticks(x, groups); a.set_ylabel("Sharpe ratio"); a.set_ylim(0, 0.7)
a.legend(frameon=False, fontsize=8)
a.set_title("…but the better forecast is worth nothing\n"
            "in vol-targeted sizing (p = 0.71, 0.83)")
a.grid(alpha=0.25, axis="y")

plt.tight_layout()
p = OUT / "crosslead_summary.png"
plt.savefig(p, dpi=130, bbox_inches="tight")
print(f"[saved] {p}")
