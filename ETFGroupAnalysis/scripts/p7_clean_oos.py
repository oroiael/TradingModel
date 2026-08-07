"""Clean out-of-sample protocol for the vol gate.

p3 selected the best gate by FULL-SAMPLE Sharpe and then quoted that same
variant's test-period Sharpe as if it were out-of-sample.  It is not: the test
period participated in the selection.  This script fixes the protocol --

    1. rank all 22 gate variants using TRAIN data only (through 2023-12-31)
    2. freeze the winner
    3. report its TEST performance, untouched

That number is the only honest out-of-sample estimate in this analysis.
Also reports what a train-selected variant does versus the full grid's test
distribution, so selection luck is visible rather than assumed away.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from common import OUT, SYMBOLS, TRADING_DAYS, banner, load_raw, max_drawdown, session_ohlc

warnings.filterwarnings("ignore")
pd.set_option("display.width", 230)

raw = {s: load_raw(s) for s in SYMBOLS}
sess = {s: session_ohlc(raw[s]) for s in SYMBOLS}
common = sorted(set.intersection(*[set(sess[s].index) for s in SYMBOLS]))
TRAIN_END = pd.Timestamp("2023-12-31")

k = {s: sess[s].loc[common] for s in SYMBOLS}
ov = {s: np.log(k[s]["open"] / k[s]["close"].shift(1)).dropna() for s in SYMBOLS}
full = {s: np.log(k[s]["close"] / k[s]["close"].shift(1)).dropna() for s in SYMBOLS}


def sharpe(r):
    r = r.dropna()
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if len(r) > 2 and r.std() > 0 else np.nan


idx = ov["SPXL"].index
vxx_c = k["VXX"]["close"]
rv_spxl = full["SPXL"].rolling(21).std() * np.sqrt(TRADING_DAYS)

gates = {}
for lb in (5, 10, 21, 63):
    z = (np.log(vxx_c) - np.log(vxx_c).rolling(lb).mean()) / np.log(vxx_c).rolling(lb).std()
    for thr in (-0.5, 0.0, 0.5, 1.0):
        gates[f"VXXz({lb})<{thr}"] = (z.shift(1) < thr).reindex(idx).fillna(False)
for lb in (10, 21):
    rv = full["SPXL"].rolling(lb).std() * np.sqrt(TRADING_DAYS)
    for thr in (0.30, 0.45, 0.60):
        gates[f"SPXLrv({lb})<{thr:.2f}"] = (rv.shift(1) < thr).reindex(idx).fillna(False)

for base_name, base in [("ON_SPXL", ov["SPXL"]),
                        ("ON_5050", 0.5 * ov["SPXL"] + 0.5 * ov["FAS"])]:
    print(banner(f"CLEAN OOS PROTOCOL -- {base_name}"))
    rows = []
    for nm, g in gates.items():
        r = base.where(g, 0.0)
        rows.append({"gate": nm,
                     "sr_train": sharpe(r[r.index <= TRAIN_END]),
                     "sr_test": sharpe(r[r.index > TRAIN_END]),
                     "exposure_train": g[g.index <= TRAIN_END].mean(),
                     "ret_test": r[r.index > TRAIN_END].mean() * TRADING_DAYS,
                     "dd_test": max_drawdown(r[r.index > TRAIN_END].cumsum())})
    t = pd.DataFrame(rows).sort_values("sr_train", ascending=False)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    win = t.iloc[0]
    ung_tr = sharpe(base[base.index <= TRAIN_END])
    ung_te = sharpe(base[base.index > TRAIN_END])
    print(f"\n  Train-selected winner : {win['gate']}")
    print(f"  its TRAIN Sharpe      : {win['sr_train']:.4f}  (ungated train {ung_tr:.4f})")
    print(f"  its TEST Sharpe       : {win['sr_test']:.4f}  (ungated test  {ung_te:.4f})"
          f"   <-- the honest OOS number")
    print(f"  test-period ann return: {win['ret_test']:+.2%}   maxDD {win['dd_test']:.2%}")
    print(f"\n  Test-Sharpe distribution across ALL {len(t)} variants "
          f"(is the winner special, or is the whole grid good?):")
    print(f"    mean {t['sr_test'].mean():.4f}  median {t['sr_test'].median():.4f}  "
          f"min {t['sr_test'].min():.4f}  max {t['sr_test'].max():.4f}")
    print(f"    winner's rank in TEST: "
          f"{int((t['sr_test'] > win['sr_test']).sum()) + 1} of {len(t)}")
    rho = t["sr_train"].corr(t["sr_test"], method="spearman")
    print(f"    Spearman corr(train Sharpe, test Sharpe) across variants: {rho:+.4f}")
    print("    A positive rank correlation means train performance carries information")
    print("    about test performance. Near zero means the selection is noise.")

print(banner("SIMPLE PRE-SPECIFIED ALTERNATIVE -- no grid, no selection"))
print("If the gate is chosen with no search at all -- 'hold overnight only when")
print("21-day realized vol is below its own trailing median' -- there is nothing")
print("to deflate, because nothing was tried.\n")
med = rv_spxl.rolling(252).median()
g = (rv_spxl.shift(1) < med.shift(1)).reindex(idx).fillna(False)
for nm, base in [("ON SPXL", ov["SPXL"]), ("ON 50/50", 0.5 * ov["SPXL"] + 0.5 * ov["FAS"])]:
    r = base.where(g, 0.0)
    tr, te = r[r.index <= TRAIN_END], r[r.index > TRAIN_END]
    rt = g.sum() / (len(r) / TRADING_DAYS)
    print(f"  {nm}: exposure {g.mean():.1%}  full SR {sharpe(r):.4f}  "
          f"train {sharpe(tr):.4f}  TEST {sharpe(te):.4f}  "
          f"ann {r.mean()*TRADING_DAYS:+.2%}  maxDD {max_drawdown(r.cumsum()):.2%}")
    print(f"           round-trips/yr {rt:.0f}  break-even "
          f"{r.mean()*TRADING_DAYS/rt*1e4:.2f} bp")
print(f"\n  ungated ON SPXL : SR {sharpe(ov['SPXL']):.4f}   "
      f"ungated ON 50/50: SR {sharpe(0.5*ov['SPXL']+0.5*ov['FAS']):.4f}")
