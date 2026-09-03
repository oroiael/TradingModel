import sys, os
sys.path.insert(0, "band_lab/v2_dev")
import numpy as np, pandas as pd
import short_vol_backtest as sv
import option_fill_ladder as fl

c = pd.read_csv("band_lab/v2_dev/out/V58_option_fill_cells.csv")

# ---- 1. regression: does the k=1.0 rung match the committed V54/V56/V57 grids?
print("REGRESSION — the k=+1.00 rung against the published grids")
for side, path, fam in [("short", "short_vol_short_straddle_grid.csv", "straddle"),
                        ("long",  "short_vol_long_straddle_grid.csv",  "straddle")]:
    pub = pd.read_csv(f"band_lab/v2_dev/out/{path}").sort_values(["tenor","exit"])
    lad = c[(c.k == 1.0) & (c.family == fam) & (c.side == side)].sort_values(["tenor","exit"])
    d = np.abs(pub["mean"].to_numpy() - lad["mean"].to_numpy()).max()
    dn = int(np.abs(pub["n"].to_numpy() - lad["n"].to_numpy()).max())
    print(f"  {side:<6} straddle vs {path:<36} max |dmean| {d:.2e}   max |dn| {dn}"
          f"   {'PASS' if d < 1e-12 and dn == 0 else 'FAIL'}")
pub = pd.read_csv("band_lab/v2_dev/out/credit_spread_grid.csv").sort_values(["structure","tenor","exit"])
lad = c[(c.k == 1.0) & (c.family == "credit_spread")].sort_values(["structure","tenor","exit"])
d = np.abs(pub["mean"].to_numpy() - lad["mean"].to_numpy()).max()
print(f"  credit spreads vs credit_spread_grid.csv (V56)        max |dmean| {d:.2e}"
      f"                {'PASS' if d < 1e-12 else 'FAIL'}")

# ---- 2. joint by exit rule, V57's cut
st = c[c.family == "straddle"]
w = st.pivot_table(index=["k","exit","tenor"], columns="side", values="mean")
w["joint"] = w["short"] + w["long"]
j = w.groupby(level=["k","exit"]).joint.mean().unstack()
print("\n\nJOINT short+long straddle by exit rule, mean over the three tenors")
print("  V57 measured -2.40% (expiry) and -5.05% (roll21) at k=+1.00, ratio 2.11x")
print(f"\n  {'k':>6}{'expiry':>10}{'roll21':>10}{'ratio':>9}{'tp50*':>10}")
for k in sorted(j.index):
    r = j.loc[k]
    print(f"  {k:>+6.2f}{r['expiry']*100:>9.2f}%{r['roll21']*100:>9.2f}%"
          f"{r['roll21']/r['expiry']:>8.2f}x{r['tp50']*100:>9.2f}%")
print("  * tp50 pairs are NOT matched: the take-profit fires on different dates")
print("    for the short and the long, so those two columns are different cycles.")

# ---- 3. does any rung clear V53's bar B1 (mean>0, t>2) and B5 (best within 1 SE of median)?
print("\n\nTHE BAR, at each rung.  B1: best cell mean>0 and t>2.0."
      "  B5: best within 1 SE of the grid median")
for fam, side, lab in [("straddle","short","short straddle"),
                       ("straddle","long","long straddle"),
                       ("credit_spread","short","credit spread")]:
    g = c[(c.family == fam) & (c.side == side)]
    print(f"\n  {lab.upper()}")
    print(f"    {'k':>6}{'best':>9}{'t':>7}{'SE':>8}{'median':>9}{'gap/SE':>8}"
          f"{'B1':>6}{'B5':>6}")
    for k in sorted(g.k.unique()):
        s = g[g.k == k]
        b = s.loc[s["mean"].idxmax()]
        se = abs(b["mean"] / b["t"]) if b["t"] else np.nan
        gap = (b["mean"] - s["mean"].median()) / se if se else np.nan
        b1 = "PASS" if (b["mean"] > 0 and b["t"] > 2.0) else "fail"
        b5 = "PASS" if gap <= 1.0 else "fail"
        print(f"    {k:>+6.2f}{b['mean']*100:>8.2f}%{b['t']:>7.2f}{se*100:>7.2f}%"
              f"{s['mean'].median()*100:>8.2f}%{gap:>8.2f}{b1:>6}{b5:>6}")

# ---- 4. corrected realised-improvement table, on the legs actually traded
chain = sv.load_chain()
legs = fl.traded_legs(chain)
print(f"\n\nWHAT EACH RUNG ACTUALLY BUYS — corrected to the {len(legs):,} straddle legs")
print(f"  the structures actually select (not every quote in the tenor window)")
half = 0.5 * (legs[:,1] - legs[:,0])
mid = 0.5 * (legs[:,1] + legs[:,0])
print(f"  mean half-spread on those legs {half.mean()*100:.1f}c, median {np.median(half)*100:.1f}c;"
      f"  mean mid ${mid.mean():.2f}")
print(f"  half-spread as % of the option's own mid: median {np.median(half/mid)*100:.1f}%")
print(f"\n  {'rung':<5}{'k':>6}{'improvement/leg':>18}{'of the half-spread':>21}")
for k, name in fl.RUNGS:
    cts, frac, _ = fl.fill_realised(legs, k)
    print(f"  {name[0]:<5}{k:>+6.2f}{cts*100:>17.2f}c{frac*100:>20.0f}%")

# Run as:  python3 band_lab/v2_dev/v58_checks.py
# Verifies the k=+1.00 rung against the published V54/V56/V57 grids, prints the
# joint-by-exit table, applies V53's B1/B5 to every rung, and re-measures what
# each rung actually delivers on the legs the structures select.
