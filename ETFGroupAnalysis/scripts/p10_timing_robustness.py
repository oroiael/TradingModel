"""Robustness of the one positive claim: enter as late as possible.

p8 found Sharpe rising monotonically as entry moves from 15:00 to 15:55 in both
symbols.  A monotone gradient across six ordered cells is much harder to produce
by chance than a single winning cell -- but it still has to hold in each
sub-period separately, or it is a full-sample artifact.

Checks here:
  1. the entry gradient, computed independently in train and in test
  2. the exit comparison, same treatment
  3. year by year, to see whether any single year drives it
  4. the final net-of-cost table for the recommended trade
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats

from common import OUT, TRADING_DAYS, banner, load_raw, max_drawdown, session_ohlc

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)

SYMS = ["SPXL", "FAS"]
TRAIN_END = pd.Timestamp("2023-12-31")

raw = {s: load_raw(s) for s in SYMS}
sess = {s: session_ohlc(raw[s]) for s in SYMS}
for s in SYMS:
    sess[s] = sess[s][sess[s]["bars"] >= 42]
common = sorted(set(sess["SPXL"].index) & set(sess["FAS"].index))


def panel(sym):
    d = raw[sym].copy()
    d["t"] = d["ts"].dt.strftime("%H:%M")
    p = d.pivot_table(index="session", columns="t", values="Close", aggfunc="last")
    p.index = pd.to_datetime(p.index)
    return p.reindex(common)


def opening(sym):
    d = raw[sym]
    x = d[d["tod"] == pd.Timestamp("09:30").time()].set_index("session")["Open"]
    x.index = pd.to_datetime(x.index)
    return x.reindex(common)


def sharpe(r):
    r = pd.Series(r).dropna()
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if len(r) > 5 and r.std() > 0 else np.nan


P = {s: panel(s) for s in SYMS}
O = {s: opening(s) for s in SYMS}
ENTRIES = ["15:00", "15:15", "15:30", "15:40", "15:50", "15:55"]

print(banner("1.  ENTRY GRADIENT, TRAIN AND TEST COMPUTED SEPARATELY"))
print("Exit held fixed at the 09:30 opening print. If the gradient is real it")
print("should slope the same way in both halves, not just in the pooled sample.\n")
for s in SYMS:
    rows = []
    for e in ENTRIES:
        r = np.log(O[s].shift(-1) / P[s][e]).dropna()
        tr, te = r[r.index <= TRAIN_END], r[r.index > TRAIN_END]
        rows.append({"entry": e, "sr_full": sharpe(r), "sr_train": sharpe(tr),
                     "sr_test": sharpe(te),
                     "ann_full": r.mean() * TRADING_DAYS,
                     "ann_train": tr.mean() * TRADING_DAYS,
                     "ann_test": te.mean() * TRADING_DAYS})
    t = pd.DataFrame(rows).set_index("entry")
    print(f"===== {s} =====")
    print(t.to_string(float_format=lambda x: f"{x:.4f}"))
    order = np.arange(len(ENTRIES))
    for col in ("sr_train", "sr_test"):
        rho = stats.spearmanr(order, t[col].values).statistic
        print(f"  monotonicity of {col:9s} vs entry lateness: rho = {rho:+.3f}"
              f"{'  (perfectly monotone)' if abs(rho) == 1.0 else ''}")
    print()

print(banner("2.  EXIT COMPARISON, TRAIN AND TEST SEPARATELY"))
print("Entry held fixed at 15:55.\n")
EXITS = ["open", "09:30", "09:35", "09:45", "10:00", "10:30", "11:00"]
for s in SYMS:
    rows = []
    for x in EXITS:
        exit_px = O[s].shift(-1) if x == "open" else P[s][x].shift(-1)
        r = np.log(exit_px / P[s]["15:55"]).dropna()
        tr, te = r[r.index <= TRAIN_END], r[r.index > TRAIN_END]
        rows.append({"exit": x, "sr_full": sharpe(r), "sr_train": sharpe(tr),
                     "sr_test": sharpe(te), "ann_full": r.mean() * TRADING_DAYS,
                     "vol_full": r.std() * np.sqrt(TRADING_DAYS)})
    t = pd.DataFrame(rows).set_index("exit")
    print(f"===== {s} =====")
    print(t.to_string(float_format=lambda x: f"{x:.4f}"))
    best_tr = t["sr_train"].idxmax()
    print(f"  best exit on TRAIN: {best_tr}  -> its TEST Sharpe {t.loc[best_tr,'sr_test']:.4f}"
          f"   (best possible on test was {t['sr_test'].idxmax()} at {t['sr_test'].max():.4f})")
    print(f"  'open' exit on test: {t.loc['open','sr_test']:.4f}\n")

print(banner("3.  YEAR BY YEAR -- earliest vs latest entry, exit at the open"))
for s in SYMS:
    early = np.log(O[s].shift(-1) / P[s]["15:00"]).dropna()
    late = np.log(O[s].shift(-1) / P[s]["15:55"]).dropna()
    t = pd.DataFrame({
        "entry_15:00_ann": early.groupby(early.index.year).mean() * TRADING_DAYS,
        "entry_15:55_ann": late.groupby(late.index.year).mean() * TRADING_DAYS,
    })
    t["late_minus_early"] = t["entry_15:55_ann"] - t["entry_15:00_ann"]
    print(f"--- {s} ---")
    print(t.to_string(float_format=lambda x: f"{x:+.2%}"))
    n_pos = int((t["late_minus_early"] > 0).sum())
    print(f"  late entry beat early entry in {n_pos} of {len(t)} years\n")

print(banner("4.  RECOMMENDED TRADE, NET OF COST"))
print("Entry 15:55 close (MOC). Two exits shown. 252 round trips per year.")
print("Cost is charged per round trip; the break-even column is the number that")
print("decides viability, and this repo has no quote data to check it against.\n")
rows = []
for s in SYMS:
    for x, lab in [("open", "09:30 opening auction (MOO)"), ("09:30", "09:30 bar close")]:
        exit_px = O[s].shift(-1) if x == "open" else P[s][x].shift(-1)
        r = np.log(exit_px / P[s]["15:55"]).dropna()
        rec = {"sym": s, "exit": lab, "ann_ret": r.mean() * TRADING_DAYS,
               "ann_vol": r.std() * np.sqrt(TRADING_DAYS), "sharpe": sharpe(r),
               "max_dd": max_drawdown(r.cumsum()), "hit": (r > 0).mean(),
               "worst": r.min(), "be_bp": r.mean() * TRADING_DAYS / 252 * 1e4}
        for c in (1, 2, 3, 5, 8):
            rc = r - c / 1e4
            rec[f"SR@{c}bp"] = sharpe(rc)
        rows.append(rec)
t = pd.DataFrame(rows).set_index(["sym", "exit"])
print(t[["ann_ret", "ann_vol", "sharpe", "max_dd", "hit", "worst", "be_bp"]]
      .to_string(float_format=lambda x: f"{x:.4f}"))
print("\nSharpe net of round-trip cost:")
print(t[[c for c in t.columns if c.startswith("SR@")]].to_string(
    float_format=lambda x: f"{x:+.4f}"))
t.to_csv(OUT / "p10_recommended_net.csv")
print(f"\n[saved] {OUT}/p10_recommended_net.csv")
