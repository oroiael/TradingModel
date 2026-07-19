#!/usr/bin/env python3
"""
BLEND LAB -- combining the Defense income engine with the Active combo
======================================================================

Sleeves (exact configurations already validated in this repo):

  DEFENSE  R2 PMCC "Defense package": invest 50%, put wing 0.5x25d90
           monetized at 3x, weekly-call skips (below trend / after >10%
           drops), 4% cash yield.   (58% CAGR, -27.6% maxDD standalone)
  ACTIVE   Active-lab best combo: 100d-trend-switched deep-ITM calls
           (puts at half size below trend) + 120-DTE ATM straddle
           re-struck at 25% moves.  (152% CAGR, -54.6% maxDD standalone)

Method: run both engines once, take their weekly NAV return streams, and
simulate one account holding both as sub-portfolios under different
ALLOCATION POLICIES (weekly transfer granularity, frictionless -- both
sleeves already resize weekly internally, so this matches how a single
IBKR account would actually be run):

  S_*   static Active weight 0..100%, weekly-rebalanced vs drift
  R_*   regime-switched: Active weight depends on spot vs 100d SMA
        (both directions tested -- more active above trend, and the
        contrarian opposite)
  D_*   drawdown-responsive: shift weights when blended wealth falls x%
        below its high-water mark (both directions tested)
  V_*   volatility targeting: Active weight = target vol / trailing
        13-week realized vol of the Active sleeve (capped)
  F_*   cross-funding: Defense's positive weekly P&L tops up Active
        ("income buys convexity"); Active skims profits above its
        high-water mark back into Defense ("convexity pays income")

Also reports the sleeve correlation structure (overall, and conditional
on tail weeks) that makes the pairing complementary.

Outputs:
    blend_results.csv        all policies, ranked by MAR
    qa/blend_report.txt
"""

from pathlib import Path

import numpy as np
import pandas as pd

from soxl_options_loader import ROOT
from call_diagonal_backtest import CallMarket, CallDiagonalBacktest, Config
from active_lab import ActiveMarket, Book, Trend, Straddle, Combo, EPISODES

QA_DIR = Path(__file__).resolve().parent / "qa"
START = 150_000.0


# --------------------------------------------------------------------------
def sleeve_navs():
    mkt = ActiveMarket()          # superset of CallMarket
    defense_cfg = Config(invest_frac=0.50, put_ratio=0.5, put_dte=90,
                         put_tp_mult=3.0, skip_call_below_trend=True,
                         skip_call_after_drop=0.10, cash_apy=0.04)
    led_d, stats_d = CallDiagonalBacktest(mkt, defense_cfg).run()
    nav_d = led_d.set_index(pd.to_datetime(led_d["week_start"]))[
        "end_total_wealth"]
    pol = Combo(Trend(sma=100, down="put", frac=0.50, down_frac=0.25),
                Straddle(tenor=120, restrike=0.25, frac=0.25))
    led_a, stats_a = Book(mkt, pol).run()
    nav_a = led_a.set_index(pd.to_datetime(led_a["week_start"]))[
        "end_wealth"]
    df = pd.DataFrame({"defense": nav_d, "active": nav_a}).dropna()
    rets = df.pct_change().fillna(
        df.iloc[0] / START - 1)      # first week return vs starting capital
    # regime series: spot vs 100d SMA at each week start
    regime = pd.Series(
        {td: mkt.spot(pd.Timestamp(td)) >= mkt.sma(pd.Timestamp(td), 100)
         for td in df.index}, dtype=bool)
    assert stats_d["qa_recon"] == "PASS" and stats_a["qa_recon"] == "PASS"
    return rets, regime, stats_d, stats_a


# --------------------------------------------------------------------------
def simulate(rets, weights_fn, label):
    """One account, two sub-portfolios; weekly returns then transfer to
    the policy's target Active weight (None = let it drift)."""
    wA = START * 1.0   # placeholder, set below
    state = {"hwm": START}
    w0 = weights_fn(rets.index[0], None, state)
    wB = START * w0
    wA = START - wB
    path, wts = [], []
    for td, r in rets.iterrows():
        wA *= 1 + r["defense"]
        wB *= 1 + r["active"]
        tot = wA + wB
        state["hwm"] = max(state["hwm"], tot)
        tgt = weights_fn(td, tot, state)
        if tgt is not None:
            wB = tot * tgt
            wA = tot - wB
        path.append(tot)
        wts.append(wB / tot if tot > 0 else np.nan)
    w = pd.Series(path, index=rets.index)
    wk = w.pct_change().dropna()
    dd_series = w / w.cummax() - 1
    dd = dd_series.min()
    trough = dd_series.idxmin()
    after = w.loc[trough:]
    rec = after[after >= w.cummax().loc[trough]]
    yrs = len(w) / 52
    cagr = ((w.iloc[-1] / START) ** (1 / yrs) - 1) * 100
    out = {"policy": label, "end_wealth": round(w.iloc[-1], 0),
           "cagr_pct": round(cagr, 1), "max_dd_pct": round(dd * 100, 1),
           "MAR": round(cagr / abs(dd * 100), 2),
           "worst_wk_pct": round(wk.min() * 100, 1),
           "dd_recovered": str(rec.index[0].date()) if len(rec)
           else "NEVER (end of data)",
           "avg_active_wt_pct": round(np.nanmean(wts) * 100, 0)}
    for name, (a, b) in EPISODES.items():
        win = w[(w.index >= a) & (w.index <= b)]
        out[name] = round((win.iloc[-1] / win.iloc[0] - 1) * 100, 1) \
            if len(win) > 1 else np.nan
    return out


# --------------------------------------------------------------------------
def build_policies(regime):
    P = {}
    # S: static, weekly rebalanced
    for w in (0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.70, 1.0):
        P[f"S_static{int(w * 100)}_rebal"] = (
            lambda td, tot, st, w=w: w)
    # S: drift (set once, never rebalance)
    for w in (0.20, 0.30, 0.50):
        P[f"S_static{int(w * 100)}_drift"] = (
            lambda td, tot, st, w=w: w if tot is None else None)
    # R: regime-switched on the 100d trend
    for wa, wb in ((0.50, 0.10), (0.30, 0.10), (0.50, 0.0),
                   (0.70, 0.30), (0.10, 0.50)):
        P[f"R_above{int(wa * 100)}_below{int(wb * 100)}"] = (
            lambda td, tot, st, wa=wa, wb=wb:
            wa if regime.get(td, True) else wb)
    # D: drawdown-responsive (15% trigger, both directions)
    for trig, base, under in ((0.15, 0.30, 0.10), (0.15, 0.30, 0.60),
                              (0.20, 0.50, 0.20)):
        P[f"D_dd{int(trig * 100)}_{int(base * 100)}to{int(under * 100)}"] = (
            lambda td, tot, st, t=trig, b=base, u=under:
            b if tot is None or tot >= st["hwm"] * (1 - t) else u)
    # F: cross-funding is handled by a dedicated simulator below
    return P


def simulate_crossfund(rets, w0, skim, label):
    """Defense's positive weekly P&L tops up Active by `skim` of the gain;
    Active skims `skim` of any new profit above its own HWM back."""
    wB = START * w0
    wA = START - wB
    hwmB = wB
    path = []
    wts = []
    for td, r in rets.iterrows():
        gA = wA * r["defense"]
        wA += gA
        wB *= 1 + r["active"]
        if gA > 0:                      # income buys convexity
            move = min(skim * gA, wA)
            wA -= move
            wB += move
        if wB > hwmB:                   # convexity pays income
            move = skim * (wB - hwmB)
            wB -= move
            wA += move
            hwmB = wB + move * 0        # new high after skim
            hwmB = max(hwmB, wB)
        hwmB = max(hwmB, wB)
        path.append(wA + wB)
        wts.append(wB / (wA + wB))
    w = pd.Series(path, index=rets.index)
    wk = w.pct_change().dropna()
    dd = (w / w.cummax() - 1).min()
    yrs = len(w) / 52
    cagr = ((w.iloc[-1] / START) ** (1 / yrs) - 1) * 100
    out = {"policy": label, "end_wealth": round(w.iloc[-1], 0),
           "cagr_pct": round(cagr, 1), "max_dd_pct": round(dd * 100, 1),
           "MAR": round(cagr / abs(dd * 100), 2),
           "worst_wk_pct": round(wk.min() * 100, 1),
           "dd_recovered": "", "avg_active_wt_pct":
               round(np.nanmean(wts) * 100, 0)}
    for name, (a, b) in EPISODES.items():
        win = w[(w.index >= a) & (w.index <= b)]
        out[name] = round((win.iloc[-1] / win.iloc[0] - 1) * 100, 1) \
            if len(win) > 1 else np.nan
    return out


def vol_target_policy(rets, target_ann, wmax):
    trail = rets["active"].rolling(13).std() * np.sqrt(52)

    def fn(td, tot, st):
        v = trail.get(td, np.nan)
        if not np.isfinite(v) or v <= 0:
            return 0.30
        return float(np.clip(target_ann / v, 0.05, wmax))
    return fn


# --------------------------------------------------------------------------
def main():
    QA_DIR.mkdir(exist_ok=True)
    print("building sleeve NAV streams ...")
    rets, regime, sd, sa = sleeve_navs()
    print(f"  defense standalone: end={sd['end_wealth']:,.0f}; "
          f"active standalone: end={sa['end_wealth']:,.0f}; "
          f"{len(rets)} weeks aligned")

    # complementarity structure
    c_all = rets["defense"].corr(rets["active"])
    tailA = rets[rets["active"] < -0.05]
    tailD = rets[rets["defense"] < -0.05]
    corr_lines = [
        f"weekly return correlation (all {len(rets)} wks): {c_all:+.2f}",
        f"defense return in active's worst weeks (<-5%, n={len(tailA)}): "
        f"avg {tailA['defense'].mean():+.2%}",
        f"active return in defense's worst weeks (<-5%, n={len(tailD)}): "
        f"avg {tailD['active'].mean():+.2%}",
        f"weeks BOTH sleeves down >5%: "
        f"{((rets < -0.05).all(axis=1)).sum()} of {len(rets)}"]

    rows = []
    for label, fn in build_policies(regime).items():
        rows.append(simulate(rets, fn, label))
    for tgt, wmax in ((0.25, 0.60), (0.35, 0.70)):
        rows.append(simulate(rets, vol_target_policy(rets, tgt, wmax),
                             f"V_target{int(tgt * 100)}_max"
                             f"{int(wmax * 100)}"))
    for w0, skim in ((0.15, 0.25), (0.15, 0.50), (0.30, 0.25)):
        rows.append(simulate_crossfund(rets, w0, skim,
                                       f"F_start{int(w0 * 100)}_skim"
                                       f"{int(skim * 100)}"))
    df = pd.DataFrame(rows).sort_values("MAR", ascending=False)
    df.to_csv(ROOT / "blend_results.csv", index=False)

    lines = ["BLEND LAB -- DEFENSE + ACTIVE ALLOCATION POLICIES",
             f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}", "",
             "SLEEVE COMPLEMENTARITY"] + corr_lines + ["",
             "POLICIES (sorted by MAR; S_static0=pure Defense, "
             "S_static100=pure Active)"]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        lines.append(df.to_string(index=False))
    (QA_DIR / "blend_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[3:8]))
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(df.to_string(index=False))
    print(f"\nresults -> blend_results.csv ({len(df)} policies)")


if __name__ == "__main__":
    main()
