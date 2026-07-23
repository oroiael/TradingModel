#!/usr/bin/env python3
"""
bracket_reality.py  --  the CORRECTED bracket + blend after the audit. Bounds the truth
between two honest exit assumptions and fixes the annualization, so nothing is quoted on
a rose-tinted basis.

Errors this corrects (found when the user asked why the numbers didn't reconcile):
  E1  bracket_weekly annualized ARITHMETICALLY (mean/wk x52 = +41%); geometric CAGR is +38%.
  E2  it settled at INTRINSIC at expiry. On expiry day mid ~ intrinsic but the BID is
      ~1-2%/wk below it (wide, thin). Intrinsic is only realized by EXERCISING the ITM
      leg; if you instead SELL at the bid the edge nearly vanishes. So the true range is
      [close-at-bid ... exercise-at-intrinsic], not the single optimistic number.
  E3  my reconcile.py over-corrected: it closed EARLY at 3 DTE at the bid (-37%), which is
      too pessimistic. The fair comparison holds to expiry.

Bracket sleeve computed per weekly cycle under BOTH exits; overnight sleeve (gated) per
cycle; blend under both. Geometric CAGR, Sharpe, weekly-sampled maxDD (noted vs daily).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "call_spread_lab"))
sys.path.insert(0, str(HERE))
from data_loader import daily_oc_6y  # noqa: E402
from debug_bracket import cycles, run  # validated per-cycle bracket P&L  # noqa: E402

ANN = 252; WKS = 52
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 92 + f"\n{t}\n" + "=" * 92)


def wk(r):
    r = np.asarray(r, float); eq = np.cumprod(1 + r)
    cagr = eq[-1] ** (WKS / len(r)) - 1 if eq[-1] > 0 else -1.0
    sh = r.mean() / r.std(ddof=1) * np.sqrt(WKS) if r.std() > 0 else np.nan
    e = np.concatenate([[1.0], eq]); dd = (e / np.maximum.accumulate(e) - 1).min()
    return dict(cagr=cagr, vol=r.std(ddof=1) * np.sqrt(WKS), sharpe=sh, maxdd=dd,
                mar=cagr / abs(dd) if dd else np.nan)


def main():
    o = cycles()
    b_intr = run(o, "expiry_intrinsic")[["date", "exp", "pnl"]].rename(columns={"pnl": "b"})
    b_bid = run(o, "expiry_bid")[["date", "exp", "pnl"]].rename(columns={"pnl": "b"})

    # overnight sleeve (gated vt x trend), compounded per cycle -- same as two_sleeve
    d = daily_oc_6y()
    on = (d["open"] / d["prev_close"] - 1)
    rv = on.rolling(20).std().shift(1) * np.sqrt(ANN)
    up = (d["close"] > d["close"].rolling(50).mean()).shift(1).fillna(False)
    e_vt = np.clip((0.60 / rv).fillna(0.0), 0, 1.0)
    gated = (e_vt * up * on).dropna()

    def cyc(t0, exp):
        w = gated[(gated.index > pd.Timestamp(t0)) & (gated.index <= pd.Timestamp(exp))]
        return float((1 + w).prod() - 1) if len(w) else np.nan

    base = b_intr.copy()
    base["on"] = [cyc(base["date"].iloc[i], base["exp"].iloc[i]) for i in range(len(base))]
    base["b_intr"] = b_intr["b"].values
    base["b_bid"] = b_bid["b"].values
    df = base.dropna(subset=["on", "b_intr", "b_bid"]).reset_index(drop=True)
    df["yr"] = df["date"].dt.year

    hr("1.  BRACKET sleeve alone, honest exit BOUNDS (geometric, per weekly cycle)")
    for nm, col in [("exercise ITM @ intrinsic (optimistic)", "b_intr"),
                    ("sell @ bid (pessimistic)", "b_bid")]:
        s = wk(df[col])
        print(f"  {nm:38s} CAGR {s['cagr']:>+6.0%}  Sharpe {s['sharpe']:>+5.2f}  "
              f"maxDD {s['maxdd']:>+6.0%}  MAR {s['mar']:>5.2f}")
    print("  -> the whole edge is the expiry-day spread you save by EXERCISING vs selling.")

    hr("2.  OVERNIGHT sleeve (gated) for reference")
    s = wk(df["on"])
    print(f"  gated overnight (vt x trend)          CAGR {s['cagr']:>+6.0%}  Sharpe {s['sharpe']:>+5.2f}  "
          f"maxDD {s['maxdd']:>+6.0%}  MAR {s['mar']:>5.2f}")

    hr("3.  40/60 BLEND under both bracket exits (was Sharpe 1.17 / CAGR +37%)")
    for nm, col in [("blend, bracket @ intrinsic", "b_intr"), ("blend, bracket @ bid", "b_bid")]:
        r = 0.4 * df["on"].values + 0.6 * df[col].values
        s = wk(r)
        print(f"  {nm:30s} CAGR {s['cagr']:>+6.0%}  vol {s['vol']:>4.0%}  Sharpe {s['sharpe']:>+5.2f}  "
              f"maxDD {s['maxdd']:>+6.0%}  MAR {s['mar']:>5.2f}")

    hr("4.  is the CRASH-HEDGE property real under the pessimistic exit? (the one thing that may survive)")
    corr_i = df["on"].corr(df["b_intr"]); corr_b = df["on"].corr(df["b_bid"])
    q = df["on"].quantile(0.10); tail = df[df["on"] <= q]
    print(f"  corr(overnight, bracket): intrinsic {corr_i:+.2f}  |  bid {corr_b:+.2f}")
    print(f"  in overnight's worst-decile weeks: bracket@intrinsic {tail['b_intr'].mean():+.1%}, "
          f"bracket@bid {tail['b_bid'].mean():+.1%}")
    print("  by year (bracket@bid): does it still pay in the 2022 crash even at the pessimistic exit?")
    print(f"  {'year':6} {'overnight':>10} {'brkt@intr':>10} {'brkt@bid':>10}")
    for y, g in df.groupby("yr"):
        print(f"  {y:6} {g['on'].sum():>+10.0%} {g['b_intr'].sum():>+10.0%} {g['b_bid'].sum():>+10.0%}")

    hr("READ")
    si, sb = wk(df["b_intr"]), wk(df["b_bid"])
    bi = wk(0.4 * df["on"].values + 0.6 * df["b_intr"].values)
    bb = wk(0.4 * df["on"].values + 0.6 * df["b_bid"].values)
    print(f"  * The bracket is NOT a clean +41% winner. Corrected, it is a RANGE: "
          f"CAGR {sb['cagr']:+.0%} (sell@bid) .. {si['cagr']:+.0%} (exercise@intrinsic), Sharpe "
          f"{sb['sharpe']:+.2f} .. {si['sharpe']:+.2f}.")
    print("    The entire edge is the expiry-day bid-ask you avoid BY EXERCISING. If you close by")
    print("    selling (most systematic setups), it is roughly breakeven -- my earlier +41% was")
    print("    optimistic (intrinsic settlement) AND arithmetically annualized.")
    print(f"  * The 40/60 BLEND: CAGR {bb['cagr']:+.0%}..{bi['cagr']:+.0%}, Sharpe "
          f"{bb['sharpe']:+.2f}..{bi['sharpe']:+.2f}, maxDD {bb['maxdd']:+.0%}..{bi['maxdd']:+.0%}.")
    print(f"  * What SURVIVES even at the pessimistic exit: the crash hedge. corr ~ {corr_b:+.2f}, and")
    print(f"    in overnight's worst weeks the bracket still returns {tail['b_bid'].mean():+.1%}. So the")
    print("    bracket is better justified as cheap TAIL INSURANCE for the overnight sleeve than as")
    print("    a standalone alpha engine -- its average return is fragile, its crash payoff is robust.")


if __name__ == "__main__":
    main()
