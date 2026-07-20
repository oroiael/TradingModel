#!/usr/bin/env python3
"""
run_signals.py  --  "when is the trade going against us?" indicators + what to do.

Three questions, answered from the data:
  A. DIAGNOSTIC  -- which trailing indicator, known at entry, best separates the
     winning trades from the losing ones for each structure (the early warning)?
  B. ACT: "exit and wait" -- does GATING entries on the favorable regime improve
     return and, more importantly, cut drawdown?
  C. ACT: "invert the trade" -- does a trend-following system that flips between
     long-upside (bull_call) in uptrends and long-downside (long_put) in
     downtrends beat either alone?
  D. MID-TRADE STOP -- for the short-premium bull_put, does exiting at the EOD
     mark when the short strike is breached help, or just lock in slippage?

All indicators are trailing (no look-ahead, see signals.py). Weekly tenor is used
throughout so every structure shares the same entry-date sequence and the
switching systems are apples-to-apples.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

from data_loader import load_options
from verticals import VConfig, build_index, run
from signals import build_signals, attach
from capital_models import full_risk_curve

OUT = Path(__file__).resolve().parent / "outputs"
CAP0 = 100_000.0
CONTRACT = 100.0
pd.set_option("display.width", 210); pd.set_option("display.max_columns", 40)


def hr(t): print("\n" + "=" * 84 + f"\n{t}\n" + "=" * 84)


# weekly reference configs (shared cadence) -------------------------------------
CFGS = {
    "bull_call": VConfig(structure="bull_call", target_dte=7, primary_rule="delta",
                         primary_delta=0.50, width_steps=3),
    "long_call": VConfig(structure="long_call", target_dte=7, primary_rule="delta",
                         primary_delta=0.40),
    "long_put":  VConfig(structure="long_put", target_dte=7, primary_rule="delta",
                         primary_delta=0.40),
    "bull_put":  VConfig(structure="bull_put", target_dte=7, primary_rule="delta",
                         primary_delta=0.20, width_steps=3),
    "bear_call": VConfig(structure="bear_call", target_dte=7, primary_rule="otm_step",
                         primary_otm_step=1, width_steps=1),
}


def frac_equity(pnl, maxloss, mask=None, cap0=CAP0, risk=0.10):
    """Compound fractional-risk sizing over aligned per-trade arrays; mask=None
    trades every row, else only where mask is True (else hold cash)."""
    cap = cap0; eq = []
    for i in range(len(pnl)):
        take = True if mask is None else bool(mask[i])
        ml = maxloss[i] * CONTRACT
        if take and np.isfinite(ml) and ml > 0:
            n = int((risk * cap) // ml)
            cap = max(cap + n * pnl[i] * CONTRACT, 0.0)
        eq.append(cap)
    return np.array(eq)


def dd(equity, cap0=CAP0):
    e = np.concatenate([[cap0], equity]); peak = np.maximum.accumulate(e)
    return float((e / peak - 1).min())


def main():
    hr("LOAD + build signals")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt)
    sig = build_signals(opt)

    leds = {k: attach(run(opt, c, prebuilt=idx), sig) for k, c in CFGS.items()}
    for k, l in leds.items():
        print(f"  {k:10s}: {len(l)} weekly trades")

    # ---------------------------------------------------------------- A. DIAGNOSTIC
    hr("A.  DIAGNOSTIC -- mean return per $ risked by regime state (entry-time signal)")
    def cond(led, mask):
        s = led[mask]
        return f"{s['ror'].mean():+.1%} (n={len(s)}, win {s['win'].mean():.0%})"
    for name in ["bull_call", "long_call", "bull_put", "bear_call"]:
        L = leds[name]
        print(f"\n{name}:")
        print(f"   uptrend spot>SMA50 : {cond(L, L['uptrend']==True)}")
        print(f"   downtr  spot<SMA50 : {cond(L, L['uptrend']==False)}")
        print(f"   mom20 > 0          : {cond(L, L['mom20']>0)}")
        print(f"   mom20 < 0          : {cond(L, L['mom20']<=0)}")
        print(f"   RSI14 > 55         : {cond(L, L['rsi14']>55)}")
        print(f"   RSI14 < 45         : {cond(L, L['rsi14']<45)}")
        print(f"   VRP>0 (iv>realized): {cond(L, L['vrp']>0)}")
        print(f"   VRP<0 (iv<realized): {cond(L, L['vrp']<=0)}")

    # rank single indicators by how well they separate ror (spearman) for bull_call
    hr("A2.  indicator vs outcome correlation (Spearman) -- higher |rho| = stronger warning")
    for name in ["bull_call", "bull_put"]:
        L = leds[name]
        rows = []
        for c in ["px_vs_sma50", "px_vs_sma20", "sma20_vs_sma50", "mom10", "mom20",
                  "mom60", "rsi14", "rvol20", "dd60", "iv_atm", "vrp", "iv_chg20"]:
            r = L[[c, "ror"]].dropna()
            rho = r[c].rank().corr(r["ror"].rank()) if len(r) > 5 else np.nan
            rows.append((c, rho))
        rk = pd.DataFrame(rows, columns=["indicator", "spearman_rho"]).sort_values(
            "spearman_rho", key=lambda s: s.abs(), ascending=False)
        print(f"\n{name} (positive rho = higher indicator -> better trade):")
        print(rk.to_string(index=False))

    # ---------------------------------------------------------------- align weekly
    aligned = None
    for k, l in leds.items():
        a = l.set_index("entry_date")[["pnl_share", "max_loss_share"]].add_prefix(k + "_")
        aligned = a if aligned is None else aligned.join(a, how="outer")
    up = leds["bull_call"].set_index("entry_date")["uptrend"].reindex(aligned.index)
    aligned = aligned.assign(uptrend=up.values)
    aligned["year"] = pd.to_datetime(aligned.index).year

    def series(col):
        return aligned[col].values

    # ---------------------------------------------------------------- B. GATING
    hr("B.  'EXIT AND WAIT' -- gate entries: trend (spot>SMA50) vs buy-weakness (RSI<50)")
    systems = {}
    upmask = aligned["uptrend"].fillna(False).values.astype(bool)
    rsi = leds["bull_call"].set_index("entry_date")["rsi14"].reindex(aligned.index).values
    weakmask = np.where(np.isfinite(rsi), rsi < 50, False)   # standard oversold-ish gate
    for name in ["bull_call", "long_call", "bull_put"]:
        pnl, ml = series(name + "_pnl_share"), series(name + "_max_loss_share")
        e_all = frac_equity(pnl, ml)
        e_gate = frac_equity(pnl, ml, mask=upmask)
        e_weak = frac_equity(pnl, ml, mask=weakmask)
        systems[name + " (always)"] = e_all
        systems[name + " (uptrend only)"] = e_gate
        systems[name + " (RSI<50 only)"] = e_weak
        print(f"  {name:10s} always       : end ${e_all[-1]:>12,.0f}  maxDD {dd(e_all):+.0%}  trades {int(np.isfinite(ml).sum())}")
        print(f"  {name:10s} uptrend-only : end ${e_gate[-1]:>12,.0f}  maxDD {dd(e_gate):+.0%}  trades {int(upmask.sum())}")
        print(f"  {name:10s} buy-weakness : end ${e_weak[-1]:>12,.0f}  maxDD {dd(e_weak):+.0%}  trades {int(weakmask.sum())}")

    # ---------------------------------------------------------------- C. INVERSION
    hr("C.  'INVERT THE TRADE' -- trend-following: bull_call in uptrend, long_put in downtrend")
    bc_pnl, bc_ml = series("bull_call_pnl_share"), series("bull_call_max_loss_share")
    lp_pnl, lp_ml = series("long_put_pnl_share"), series("long_put_max_loss_share")
    # per-trade switched arrays
    sw_pnl = np.where(upmask, bc_pnl, lp_pnl)
    sw_ml = np.where(upmask, bc_ml, lp_ml)
    e_switch = frac_equity(sw_pnl, sw_ml)
    e_bc = frac_equity(bc_pnl, bc_ml)
    systems["trend-switch (bull_call/long_put)"] = e_switch
    print(f"  bull_call always           : end ${e_bc[-1]:>12,.0f}  maxDD {dd(e_bc):+.0%}")
    print(f"  trend-switch (up=BC/dn=LP)  : end ${e_switch[-1]:>12,.0f}  maxDD {dd(e_switch):+.0%}")
    # also switch to bear_call (credit) on downtrend instead of long_put
    becl_pnl, becl_ml = series("bear_call_pnl_share"), series("bear_call_max_loss_share")
    sw2_pnl = np.where(upmask, bc_pnl, becl_pnl)
    sw2_ml = np.where(upmask, bc_ml, becl_ml)
    e_switch2 = frac_equity(sw2_pnl, sw2_ml)
    systems["trend-switch (bull_call/bear_call)"] = e_switch2
    print(f"  trend-switch (up=BC/dn=bearC): end ${e_switch2[-1]:>12,.0f}  maxDD {dd(e_switch2):+.0%}")

    # by-year for the switch system
    swdf = pd.DataFrame({"year": aligned["year"].values, "pnl": sw_pnl, "ml": sw_ml,
                         "up": upmask})
    swdf["ror"] = swdf["pnl"] / swdf["ml"]
    print("\n  trend-switch by year (mean RoR / trades / % uptrend):")
    print(swdf.groupby("year").agg(mean_ror=("ror", "mean"), trades=("ror", "size"),
                                   pct_up=("up", "mean")).round(3).to_string())

    # ---------------------------------------------------------------- D. STOPS
    hr("D.  MID-TRADE STOP on bull_put (weekly, delta .20, w3) -- exit at EOD mark")
    base = CFGS["bull_put"]
    variants = {
        "no stop": None,
        "stop: short strike breached": {"type": "breach_primary"},
        "stop: SOXL down 5% intra-hold": {"type": "move_pct", "thresh": 0.05},
        "stop: SOXL down 10% intra-hold": {"type": "move_pct", "thresh": 0.10},
    }
    for label, st in variants.items():
        cfg = VConfig(structure="bull_put", target_dte=7, primary_rule="delta",
                      primary_delta=0.20, width_steps=3, stop=st)
        L = run(opt, cfg, prebuilt=idx)
        stopped = (L["exit_kind"] == "stop").mean() if "exit_kind" in L else 0.0
        print(f"  {label:32s}: mean_ror {L['ror'].mean():+.1%}  win {L['win'].mean():.0%}  "
              f"worst {L['ror'].min():+.0%}  stopped {stopped:.0%}  n={len(L)}")

    _plots(systems)
    print(f"\nsaved outputs/signals_systems.png")


def _plots(systems):
    fig, ax = plt.subplots(figsize=(13, 6))
    keys = ["bull_call (always)", "bull_call (uptrend only)",
            "trend-switch (bull_call/long_put)", "trend-switch (bull_call/bear_call)",
            "bull_put (always)", "bull_put (uptrend only)"]
    for k in keys:
        if k in systems:
            ax.plot(systems[k], label=k, lw=1.3)
    ax.axhline(CAP0, color="k", lw=0.6, ls="--")
    ax.set_yscale("log"); ax.set_ylabel("equity ($, log)")
    ax.set_xlabel("weekly trade #")
    ax.set_title("Regime-gated / trend-switch systems (risk 10%/trade, weekly)")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "signals_systems.png", dpi=110)


if __name__ == "__main__":
    main()
