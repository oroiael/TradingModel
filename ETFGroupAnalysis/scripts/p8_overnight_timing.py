"""Overnight trade: optimal entry and exit timing, SPXL and FAS independently.

Phase 1 established that ~68% (SPXL) and ~83% (FAS) of six-year return accrued
between the close and the next open, using a 15:55 -> 09:30-open convention.
That convention was assumed, not optimized.  This script asks where the money
actually sits, bar by bar, and whether a different entry/exit beats it.

Predictions recorded BEFORE running (T1.2 seasonality is the basis):
  P1. Entering later beats entering earlier. The 15:30 block had mean -0.42bp
      (SPXL) and -1.11bp (FAS, the only bootstrap-significant intraday block in
      the whole study). Holding through it should cost money.
  P2. Exiting slightly AFTER the open may beat exiting at the open, because the
      09:30 block was mildly positive (+0.56bp SPXL, +0.33bp FAS).
  P3. Both extensions dilute: intraday Sharpe was 0.22 (SPXL) / 0.10 (FAS), so
      any added intraday exposure should lower Sharpe even if it raises return.
  P4. The optimum will be a plateau, not a spike. A single standout cell in a
      54-cell grid would be selection noise.

Selection protocol: rank on TRAIN only (through 2023-12-31), evaluate on TEST.
The train->test rank correlation across all cells is reported -- that diagnostic
is what retracted the volatility gate in p7.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats

from common import OUT, TRADING_DAYS, banner, load_raw, max_drawdown, session_ohlc

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)

SYMS = ["SPXL", "FAS"]
TRAIN_END = pd.Timestamp("2023-12-31")
EULER = 0.5772156649015329

raw = {s: load_raw(s) for s in SYMS}
sess = {s: session_ohlc(raw[s]) for s in SYMS}
# drop SPXL's truncated final session (54 bars, ends 13:55) -- flagged in p0
for s in SYMS:
    sess[s] = sess[s][sess[s]["bars"] >= 42]
common = sorted(set(sess["SPXL"].index) & set(sess["FAS"].index))


def bar_panel(sym: str) -> pd.DataFrame:
    """One row per session, one column per bar time, holding that bar's CLOSE."""
    d = raw[sym].copy()
    d["t"] = d["ts"].dt.strftime("%H:%M")
    p = d.pivot_table(index="session", columns="t", values="Close", aggfunc="last")
    p.index = pd.to_datetime(p.index)
    return p.reindex(common)


def open_price(sym: str) -> pd.Series:
    """The 09:30 opening print -- the auction, not the 09:30 bar close."""
    d = raw[sym]
    o = d[d["tod"] == pd.Timestamp("09:30").time()].set_index("session")["Open"]
    o.index = pd.to_datetime(o.index)
    return o.reindex(common)


def sharpe(r):
    r = pd.Series(r).dropna()
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if len(r) > 5 and r.std() > 0 else np.nan


def dsr(r, n_trials):
    r = pd.Series(r).dropna(); n = len(r)
    if n < 30 or n_trials <= 1:
        return np.nan
    sr = r.mean() / r.std()
    g3, g4 = stats.skew(r), stats.kurtosis(r, fisher=False)
    se = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) / (n - 1))
    e_max = np.sqrt(1.0 / (n - 1)) * (
        (1 - EULER) * stats.norm.ppf(1 - 1 / n_trials)
        + EULER * stats.norm.ppf(1 - 1 / (n_trials * np.e)))
    return float(stats.norm.cdf((sr - e_max) / se))


panel = {s: bar_panel(s) for s in SYMS}
opens = {s: open_price(s) for s in SYMS}

# ------------------------------------------------------------------ profile
print(banner("A.  WHERE THE MONEY IS -- bar-by-bar mean return around the boundary"))
print("Mean log return per 5-min bar, in bp, with a 2,000-draw bootstrap 95% CI.")
print("'OVERNIGHT' is 15:55 close -> 09:30 opening print (a single jump, not a bar).\n")
rng = np.random.default_rng(3)
LATE = ["15:00", "15:05", "15:10", "15:15", "15:20", "15:25", "15:30",
        "15:35", "15:40", "15:45", "15:50", "15:55"]
EARLY = ["09:30", "09:35", "09:40", "09:45", "09:50", "09:55", "10:00",
         "10:15", "10:30", "11:00"]

for s in SYMS:
    P, O = panel[s], opens[s]
    rows = []
    # late-day bars: return INTO each bar's close
    for i, t in enumerate(LATE):
        prev = "14:55" if i == 0 else LATE[i - 1]
        r = np.log(P[t] / P[prev]).dropna()
        rows.append(("late", t, r))
    # the overnight jump
    rows.append(("JUMP", "OVERNIGHT", np.log(O.shift(-1) / P["15:55"]).dropna()))
    # morning bars: return into each bar's close, first one measured from the open
    for i, t in enumerate(EARLY):
        if i == 0:
            r = np.log(P[t] / O).dropna()
        else:
            r = np.log(P[t] / P[EARLY[i - 1]]).dropna()
        rows.append(("early", t, r))
    print(f"--- {s} ---")
    print(f"{'seg':6s} {'bar':10s} {'mean_bp':>9s} {'ci_lo':>8s} {'ci_hi':>8s} "
          f"{'vol_bp':>8s} {'t':>7s} {'sig':>4s}")
    for seg, t, r in rows:
        v = r.values
        bs = rng.choice(v, size=(2000, v.size), replace=True).mean(axis=1) * 1e4
        lo, hi = np.percentile(bs, [2.5, 97.5])
        tstat = v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))
        print(f"{seg:6s} {t:10s} {v.mean()*1e4:9.3f} {lo:8.3f} {hi:8.3f} "
              f"{v.std(ddof=1)*1e4:8.2f} {tstat:7.2f} "
              f"{'***' if (lo > 0 or hi < 0) else '':>4s}")
    print()

# ------------------------------------------------------------------ grid
print(banner("B.  ENTRY / EXIT GRID"))
print("Entry = close of the stated bar on day t. Exit = 'open' is the 09:30 auction")
print("print on day t+1; any other exit is that bar's close on day t+1.\n")

ENTRIES = ["15:00", "15:15", "15:30", "15:40", "15:50", "15:55"]
EXITS = ["open", "09:30", "09:35", "09:45", "10:00", "10:30", "11:00"]
N_CELLS = len(ENTRIES) * len(EXITS)

all_res = {}
for s in SYMS:
    P, O = panel[s], opens[s]
    recs = []
    for e in ENTRIES:
        for x in EXITS:
            entry_px = P[e]
            exit_px = O.shift(-1) if x == "open" else P[x].shift(-1)
            r = np.log(exit_px / entry_px).dropna()
            tr, te = r[r.index <= TRAIN_END], r[r.index > TRAIN_END]
            recs.append({
                "entry": e, "exit": x, "n": len(r),
                "ann_ret": r.mean() * TRADING_DAYS,
                "ann_vol": r.std() * np.sqrt(TRADING_DAYS),
                "sharpe": sharpe(r), "sr_train": sharpe(tr), "sr_test": sharpe(te),
                "max_dd": max_drawdown(r.cumsum()),
                "hit": (r > 0).mean(),
                "be_bp": r.mean() * TRADING_DAYS / 252 * 1e4,
                "dsr": dsr(r, N_CELLS),
            })
    g = pd.DataFrame(recs)
    all_res[s] = g
    print(f"===== {s} =====")
    print("Full-sample Sharpe:")
    print(g.pivot(index="entry", columns="exit", values="sharpe")
          .reindex(index=ENTRIES, columns=EXITS).to_string(float_format=lambda x: f"{x:.3f}"))
    print("\nAnnualized return:")
    print(g.pivot(index="entry", columns="exit", values="ann_ret")
          .reindex(index=ENTRIES, columns=EXITS).to_string(float_format=lambda x: f"{x:.2%}"))
    print("\nBreak-even cost, bp per round trip (252 round trips/yr):")
    print(g.pivot(index="entry", columns="exit", values="be_bp")
          .reindex(index=ENTRIES, columns=EXITS).to_string(float_format=lambda x: f"{x:.2f}"))

    # clean protocol
    gt = g.sort_values("sr_train", ascending=False)
    w = gt.iloc[0]
    rho = gt["sr_train"].corr(gt["sr_test"], method="spearman")
    base = g[(g["entry"] == "15:55") & (g["exit"] == "open")].iloc[0]
    print(f"\n  Baseline convention (15:55 -> open): SR {base['sharpe']:.3f} "
          f"(train {base['sr_train']:.3f}, test {base['sr_test']:.3f}), "
          f"ann {base['ann_ret']:.2%}, break-even {base['be_bp']:.2f}bp")
    print(f"  TRAIN-selected best cell: {w['entry']} -> {w['exit']}   "
          f"train SR {w['sr_train']:.3f}  ->  TEST SR {w['sr_test']:.3f}")
    print(f"  its full-sample: SR {w['sharpe']:.3f}  ann {w['ann_ret']:.2%}  "
          f"maxDD {w['max_dd']:.2%}  DSR {w['dsr']:.3f}")
    print(f"  Spearman corr(train SR, test SR) across {N_CELLS} cells: {rho:+.4f}")
    print(f"  test-SR spread across all cells: min {g['sr_test'].min():.3f} "
          f"median {g['sr_test'].median():.3f} max {g['sr_test'].max():.3f}")
    print()

# ------------------------------------------------------------------ plateau
print(banner("C.  IS THE OPTIMUM A PLATEAU OR A SPIKE?"))
print("Sharpe of each cell minus the grid median, in units of the grid's own")
print("cross-cell standard deviation. A lone spike >2 sd is a selection-noise flag.\n")
for s in SYMS:
    g = all_res[s]
    z = (g["sharpe"] - g["sharpe"].median()) / g["sharpe"].std()
    gz = g.assign(z=z).pivot(index="entry", columns="exit", values="z")
    print(f"--- {s} ---")
    print(gz.reindex(index=ENTRIES, columns=EXITS).to_string(float_format=lambda x: f"{x:+.2f}"))
    print(f"  cells within 0.5 sd of the max: "
          f"{int((z >= z.max() - 0.5).sum())} of {N_CELLS}\n")

# ------------------------------------------------------------------ decomposition
print(banner("D.  MARGINAL VALUE OF EACH EXTRA SEGMENT"))
print("Starting from 15:55 -> open, what does each extension add or destroy?\n")
for s in SYMS:
    P, O = panel[s], opens[s]
    core = np.log(O.shift(-1) / P["15:55"]).dropna()
    print(f"--- {s} --- core 15:55->open: SR {sharpe(core):.3f}, "
          f"ann {core.mean()*TRADING_DAYS:+.2%}, vol {core.std()*np.sqrt(TRADING_DAYS):.2%}")
    print("  extending the ENTRY earlier (adds late-day intraday exposure):")
    for e in ["15:50", "15:40", "15:30", "15:15", "15:00"]:
        add = np.log(P["15:55"] / P[e]).dropna()
        tot = np.log(O.shift(-1) / P[e]).dropna()
        print(f"    from {e}: added leg ann {add.mean()*TRADING_DAYS:+7.2%} "
              f"(SR {sharpe(add):+6.3f})  ->  total SR {sharpe(tot):+6.3f}")
    print("  extending the EXIT later (adds morning intraday exposure):")
    for x in ["09:30", "09:35", "09:45", "10:00", "10:30", "11:00"]:
        add = np.log(P[x] / O).dropna()
        tot = np.log(P[x].shift(-1) / P["15:55"]).dropna()
        print(f"    to   {x}: added leg ann {add.mean()*TRADING_DAYS:+7.2%} "
              f"(SR {sharpe(add):+6.3f})  ->  total SR {sharpe(tot):+6.3f}")
    print()

for s in SYMS:
    all_res[s].to_csv(OUT / f"p8_grid_{s}.csv", index=False)
print(f"[saved] {OUT}/p8_grid_SPXL.csv, p8_grid_FAS.csv")
