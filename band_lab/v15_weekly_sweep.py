"""
V15 — week-by-week backtest of the SOXL+SOXS pair with a 5% profit sweep.

Rule: at the end of every WINNING week, 5% of that week's profit is
transferred to a cash-only account and never traded again. Losing weeks
sweep nothing. Everything else stays in the trading account and
compounds per the strategy.

Structure traded: the V14 walk-forward-validated pair — w=0.50 static
(SOXL/SOXS), locked rules, net of IBKR Pro Fixed costs derived per
instrument at current prices (SOXL $158.41, SOXS $51.61).

IMPORTANT PROPERTY: the sweep does not change the strategy's statistical
properties at all. The strategy trades a fraction of whatever the account
holds, so percentage returns — and therefore Sharpe and the *percentage*
drawdown of the trading account — are identical with or without the
sweep. What changes is the dollar path and how much wealth is protected.
The sweep is a wealth-allocation decision, not a trading decision.

Cash interest: modelled at 0% (base case) and 4%/yr (IBKR-like on idle
balances) — the assumption is flagged, not buried.

Outputs: band_lab/out/v15_weekly_sweep.csv (every week),
         band_lab/out/v15_sweep_summary.csv
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cycle_lab"))
sys.path.insert(0, HERE)
from v14_pair_protocol import sleeve, cost_bp, CURRENT_PX

OUT = os.path.join(HERE, "out")
START = 150_000.0
SWEEP = 0.05

def build_pair(w=0.50, mode="static"):
    dL, gL, soxl, _ = sleeve("SOXL")
    dX, gX, soxs, _ = sleeve("SOXS")
    cL = cost_bp(CURRENT_PX["SOXL"], 3.17)[1] / 1e4
    cX = cost_bp(CURRENT_PX["SOXS"], 3.36)[1] / 1e4
    nL, nX = soxl - cL, soxs - cX
    cal = pd.date_range(min(nL.index.min(), nX.index.min()),
                        max(nL.index.max(), nX.index.max()), freq="B")
    a = nL.reindex(cal).fillna(0.0); b = nX.reindex(cal).fillna(0.0)
    if mode == "static":
        return w * a + (1 - w) * b
    onL = pd.Series(0.0, index=cal); onL[nL.index] = 1.0
    onX = pd.Series(0.0, index=cal); onX[nX.index] = 1.0
    act = onL * w + onX * (1 - w)
    sc = pd.Series(np.where(act > 0, 1.0 / act.replace(0, np.nan), 0.0),
                   index=cal).fillna(0.0)
    return (w * a + (1 - w) * b) * sc

def run_sweep(daily_ret, sweep=SWEEP, cash_rate=0.0, start=START):
    """Compound daily; at each week end sweep `sweep` of that week's PROFIT."""
    eq = start; cash = 0.0; rows = []
    wk_r = daily_ret.groupby(pd.Grouper(freq="W"))
    weekly_cash_rate = (1 + cash_rate) ** (1 / 52) - 1
    for wk_end, grp in wk_r:
        if len(grp) == 0:
            continue
        open_eq = eq
        for r in grp.values:
            eq *= (1 + r)
        profit = eq - open_eq
        swept = sweep * profit if profit > 0 else 0.0
        eq -= swept
        cash = cash * (1 + weekly_cash_rate) + swept
        rows.append({"week_end": wk_end, "trading_days": int((grp != 0).sum()),
                     "week_ret_%": round((open_eq and (profit / open_eq) or 0) * 100, 3),
                     "open_equity": round(open_eq, 2), "profit": round(profit, 2),
                     "swept_to_cash": round(swept, 2),
                     "trading_equity": round(eq, 2), "cash_account": round(cash, 2),
                     "total_wealth": round(eq + cash, 2)})
    return pd.DataFrame(rows).set_index("week_end")

def stats(df, label, yrs):
    eq = df["trading_equity"]; tot = df["total_wealth"]
    pk = eq.cummax(); pkt = tot.cummax()
    return {"variant": label,
            "final_trading": round(eq.iloc[-1]),
            "cash_swept_total": round(df["swept_to_cash"].sum()),
            "final_cash_acct": round(df["cash_account"].iloc[-1]),
            "TOTAL_wealth": round(tot.iloc[-1]),
            "CAGR_total_%": round(((tot.iloc[-1] / START) ** (1 / yrs) - 1) * 100, 1),
            "maxDD_trading_%": round(((eq - pk) / pk).min() * 100, 1),
            "maxDD_total_%": round(((tot - pkt) / pkt).min() * 100, 1),
            "winning_weeks_%": round((df["profit"] > 0).mean() * 100, 1)}

def main():
    r = build_pair(0.50, "static")
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    print("=" * 96)
    print("V15 — WEEK-BY-WEEK, SOXL+SOXS PAIR (w=0.50 static, net of costs), $150,000")
    print("=" * 96)
    print(f"span {r.index[0].date()} → {r.index[-1].date()} ({yrs:.1f}y)\n")

    base = run_sweep(r, sweep=0.0)
    sw0 = run_sweep(r, sweep=SWEEP, cash_rate=0.0)
    sw4 = run_sweep(r, sweep=SWEEP, cash_rate=0.04)
    rows = [stats(base, "no sweep (reference)", yrs),
            stats(sw0, "5% sweep, cash @0%", yrs),
            stats(sw4, "5% sweep, cash @4%", yrs)]
    summ = pd.DataFrame(rows)
    print(summ.to_string(index=False))
    summ.to_csv(os.path.join(OUT, "v15_sweep_summary.csv"), index=False)
    sw0.to_csv(os.path.join(OUT, "v15_weekly_sweep.csv"))

    print("\n--- weekly distribution (5% sweep, cash @0%) ---")
    p = sw0["profit"]
    print(f"  weeks: {len(sw0)} | winning {int((p>0).sum())} ({(p>0).mean()*100:.0f}%) | "
          f"flat/no-trade {int((p==0).sum())}")
    print(f"  weekly profit: mean ${p.mean():,.0f} | median ${p.median():,.0f} | "
          f"best ${p.max():,.0f} | worst ${p.min():,.0f}")
    s = sw0["swept_to_cash"]
    print(f"  weekly sweep:  mean ${s.mean():,.0f} | median ${s[s>0].median():,.0f} (winning weeks) | "
          f"max ${s.max():,.0f}")

    print("\n--- by calendar year (5% sweep, cash @0%) ---")
    yr = sw0.groupby(sw0.index.year).agg(
        weeks=("profit", "size"), profit=("profit", "sum"),
        swept=("swept_to_cash", "sum"))
    yr["trading_equity_end"] = sw0.groupby(sw0.index.year)["trading_equity"].last()
    yr["cash_end"] = sw0.groupby(sw0.index.year)["cash_account"].last()
    yr["total_end"] = sw0.groupby(sw0.index.year)["total_wealth"].last()
    print(yr.round(0).to_string())

    print("\n--- first 6 and last 6 weeks (5% sweep) ---")
    cols = ["week_ret_%", "open_equity", "profit", "swept_to_cash",
            "trading_equity", "cash_account", "total_wealth"]
    print(pd.concat([sw0[cols].head(6), sw0[cols].tail(6)]).to_string())

    cost = base["trading_equity"].iloc[-1] - sw0["total_wealth"].iloc[-1]
    print(f"\n--- what the sweep costs and buys ---")
    print(f"  terminal wealth WITHOUT sweep: ${base['trading_equity'].iloc[-1]:,.0f}")
    print(f"  terminal wealth WITH 5% sweep: ${sw0['total_wealth'].iloc[-1]:,.0f} "
          f"(${sw0['trading_equity'].iloc[-1]:,.0f} trading + ${sw0['cash_account'].iloc[-1]:,.0f} cash)")
    print(f"  compounding given up: ${cost:,.0f} ({cost/base['trading_equity'].iloc[-1]*100:.1f}% of terminal)")
    prot = sw0["cash_account"] / sw0["total_wealth"] * 100
    print(f"  share of wealth protected in cash: {prot.iloc[len(prot)//4]:.1f}% at 25% through, "
          f"{prot.iloc[len(prot)//2]:.1f}% at halfway, {prot.iloc[-1]:.1f}% at the end")
    print(f"  worst peak-to-trough on TOTAL wealth {stats(sw0,'x',yrs)['maxDD_total_%']}% "
          f"vs {stats(base,'x',yrs)['maxDD_trading_%']}% on the un-swept account")

if __name__ == "__main__":
    main()
