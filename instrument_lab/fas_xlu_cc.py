"""Weekly covered call on FAS and XLU -- the part that can be backtested honestly.

There is NO option chain for FAS or XLU in this repo, so the premium cannot be
observed. But the other half CAN: at a delta-targeted strike the weekly payout
max(0, S_T - K) is computed from the real price path, week by week. That gives
the exact premium the instrument had to pay to break even, and therefore the
implied vol it had to be quoted at. The only unknown left is whether the market
would have quoted that -- which is a single, stated number rather than a hidden
modelling choice.

Validation of the harness is in the docstring of cc_backtest.run: the share leg
reproduces cc_lp_lab's real-quote result to $8 on SOXL; the model-priced option
leg does NOT (it is ~5 CAGR points optimistic), which is exactly why the option
leg is reported as a required premium here rather than as a P&L.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from scipy.optimize import brentq
import screen as sc, cc_backtest as cb
from ibkr_weekly import SPY, XLU

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
T = 1 / 52


def realised_cc(wk, delta=0.30, vol_lb=13, grid=0.5, label=""):
    """Week-by-week realised cap cost at a delta-targeted strike. No option data used."""
    r = wk["close"] / wk["entry"] - 1
    rv_tr = r.rolling(vol_lb).std().shift(1) * np.sqrt(52)
    rows = []
    for i, row in wk.iterrows():
        rv = rv_tr.iloc[i]
        if not np.isfinite(rv) or rv <= 0:
            continue
        S, C = row.entry, row.close
        K = np.round(sc.strike_for_delta(S, T, rv, delta) / grid) * grid
        if K <= S: K = S + grid
        rows.append(dict(wk=row.wk_start, S=S, C=C, K=K, rv=rv,
                         otm=K / S - 1, ret=C / S - 1,
                         payout=max(0.0, C - K) / S,          # what the call cost, % of spot
                         assigned=C > K))
    d = pd.DataFrame(rows)
    mean_payout = d.payout.mean()
    # the IV at which BS would pay exactly that premium
    S0, rvm = 100.0, d.rv.mean()
    Km = S0 * (1 + d.otm.mean())
    try:
        iv_req = brentq(lambda s: sc.bs_call(S0, Km, T, s) / S0 - mean_payout, 1e-4, 8.0)
    except ValueError:
        iv_req = np.nan
    return d, dict(instrument=label, weeks=len(d), ann_vol=rvm,
                   mean_otm=d.otm.mean(), assign_rate=d.assigned.mean(),
                   payout_wk=mean_payout, payout_ann=mean_payout * 52,
                   iv_req=iv_req, vrp_req=iv_req - rvm,
                   worst_wk=d.payout.max(), top5=d.payout.nlargest(5).sum())


if __name__ == "__main__":
    W, E = pd.Timestamp("2022-01-01"), pd.Timestamp("2026-07-02")
    fas = cb.weekly_series_from_5min("FAS_5min_6Years.csv")
    fas = fas[(fas.wk_start >= W) & (fas.wk_start <= E)].reset_index(drop=True)
    soxl = cb.weekly_series_from_5min("SOXL_5min_6Years.csv")
    soxl = soxl[(soxl.wk_start >= W) & (soxl.wk_start <= E)].reset_index(drop=True)
    xlu = cb.weekly_series_from_closes(XLU)
    xlu = xlu[(xlu.wk_start >= W) & (xlu.wk_start <= E)].reset_index(drop=True)
    spy = cb.weekly_series_from_closes(SPY)
    spy = spy[(spy.wk_start >= W) & (spy.wk_start <= E)].reset_index(drop=True)

    res, det = [], {}
    for lab, wk, g, dl in [("FAS  3x financials", fas, 1.0, 0.30),
                           ("XLU  utilities", xlu, 0.5, 0.30),
                           ("SPY  S&P 500", spy, 1.0, 0.30),
                           ("SOXL 3x semis", soxl, 0.5, 0.30)]:
        d, s = realised_cc(wk, delta=dl, grid=g, label=lab)
        res.append(s); det[lab] = d
    t = pd.DataFrame(res).set_index("instrument")
    print("=" * 128)
    print("WHAT THE CALL ACTUALLY COST, week by week, from real prices. 0.30-delta strike,")
    print("2022-01 -> 2026-07. No option data used anywhere in this table.")
    print("=" * 128)
    print(t.to_string(formatters={
        "ann_vol": "{:.1%}".format, "mean_otm": "{:.2%}".format, "assign_rate": "{:.1%}".format,
        "payout_wk": "{:.3%}".format, "payout_ann": "{:.1%}".format, "iv_req": "{:.1%}".format,
        "vrp_req": lambda v: f"{v*100:+.1f}pp", "worst_wk": "{:.1%}".format, "top5": "{:.1%}".format}))
    print("\n  payout_wk  = mean weekly cost of the short call, % of spot -- the premium you")
    print("               must collect just to break even against holding the shares")
    print("  iv_req     = the implied vol at which that premium would be quoted")
    print("  vrp_req    = iv_req minus realised vol: the variance premium the instrument")
    print("               MUST earn. Negative = it breaks even even if options are CHEAP.")
    print("  top5       = share of the total cost concentrated in the 5 worst weeks")

    print("\n" + "=" * 128)
    print("CONCENTRATION -- how much of the cost is in a handful of weeks")
    print("=" * 128)
    for lab, d in det.items():
        tot = d.payout.sum()
        print(f"  {lab:20s} total cost {tot*100:6.1f}% of spot over {len(d)} wks | "
              f"top 5 weeks = {d.payout.nlargest(5).sum()/tot:5.1%} of it | "
              f"worst single week {d.payout.max():.1%} | assigned {d.assigned.sum():3d}")
    print("\n" + "=" * 128)
    print("EDGE OVER BUY & HOLD as a function of the one unmeasured input.")
    print("edge = premium collected - realised payout, annualised. The payout column above is")
    print("measured; the premium is BS at (realised vol + VRP). Break-even VRP is where it crosses 0.")
    print("=" * 128)
    rows = []
    for lab, d in det.items():
        S0, rvm, Km = 100.0, d.rv.mean(), 100.0 * (1 + d.otm.mean())
        row = dict(instrument=lab, income_wk=sc.bs_call(S0, Km, T, rvm) / S0,
                   breakeven_vrp=t.loc[lab, "vrp_req"])
        for vp in (-0.02, 0.0, 0.02, 0.04):
            row[f"VRP{vp*100:+.0f}pp"] = (sc.bs_call(S0, Km, T, rvm + vp) / S0
                                          - d.payout.mean()) * 52
        rows.append(row)
    ed = pd.DataFrame(rows).set_index("instrument")
    print(ed.to_string(formatters={"income_wk": "{:.3%}".format,
        "breakeven_vrp": lambda v: f"{v*100:+.1f}pp",
        **{c: "{:+.1%}".format for c in ed.columns if c.startswith("VRP")}}))
    ed.to_csv(f"{OUT}/fas_xlu_edge.csv")
    t.to_csv(f"{OUT}/fas_xlu_cc.csv")
    for lab, d in det.items():
        d.to_csv(f"{OUT}/weeks_{lab.split()[0]}.csv", index=False)
