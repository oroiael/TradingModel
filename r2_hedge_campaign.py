#!/usr/bin/env python3
"""
R2 hedge campaign: every drawdown/recovery lever, alone and combined
====================================================================

Goal (user brief): keep the basic R2 PMCC intact (deep-ITM 120-180 DTE
long call, share-replacement sizing, weekly 15-20d short call) and manage
max drawdown and/or accelerate recovery.  Also answer whether OTHER
instruments are needed to hedge.

Levers tested (each individually swept, then combined):

  A. SIZE          invest_frac 40/50/60/75%
  B. PUT WING      ratio x delta x tenor sweep (SOXL puts as the hedge)
  C. PUT MONETIZE  take-profit on the wing at 2/3/5x cost, re-buy fresh
  D. TREND CUT     SMA 30/50/100, cut to 50%/25% below trend
  E. DD CUT        de-risk trigger 10/15/20/30% below HWM, cut 50%/25%
  F. CALL SKIP     stop selling the weekly call below trend / after a
                   >10% down week (keeps the V-recovery upside)
  G. REPAIR        long-call re-strike at delta<=0.55 (adds contracts low)
  H. CASH YIELD    4% APY on idle cash (the "treasuries" instrument)
  I. INVERSE ETF   synthetic SOXS sleeve 5/10/20% (fee-free -1x SOXL
                   daily proxy; optimistic -- measures the decay penalty)

Metrics: end wealth, CAGR, maxDD, MAR (CAGR/|maxDD|), recovery date of
the deepest drawdown, longest underwater stretch, both crash episodes,
income regularity.  All runs pass cash-flow reconciliation.

Outputs:
    r2_hedge_campaign.csv     full results table
    qa/r2_hedge_report.txt
"""

from pathlib import Path

import pandas as pd

from soxl_options_loader import ROOT
from call_diagonal_backtest import CallMarket, CallDiagonalBacktest, Config
from r2_deep_analysis import risk_diagnostics

QA_DIR = Path(__file__).resolve().parent / "qa"


def campaign_configs():
    cfgs = [("BASE_PMCC", Config()),
            ("BUYHOLD", Config(long_kind="shares", no_short=True)),
            ("LONGONLY", Config(no_short=True))]

    # A. size
    for f in (0.40, 0.50, 0.60):
        cfgs.append((f"A_inv{int(f * 100)}", Config(invest_frac=f)))
    # B. put wing full sweep
    for ratio in (0.25, 0.5, 1.0):
        for delta in (0.15, 0.25, 0.35):
            for dte in (60, 90, 120):
                cfgs.append((f"B_pw{ratio:g}x{int(delta * 100)}d{dte}",
                             Config(put_ratio=ratio, put_delta=delta,
                                    put_dte=dte)))
    # C. wing monetization on the best-tenor wing
    for tp in (2.0, 3.0, 5.0):
        cfgs.append((f"C_pw.5x25d90_tp{tp:g}",
                     Config(put_ratio=0.5, put_dte=90, put_tp_mult=tp)))
    # D. trend variants
    for sma in (30, 50, 100):
        for cut in (0.5, 0.25):
            cfgs.append((f"D_trend{sma}@{cut:g}",
                         Config(trend_filter=True, trend_sma=sma,
                                trend_cut=cut)))
    # E. drawdown de-risk variants
    for trig in (0.10, 0.15, 0.20, 0.30):
        cfgs.append((f"E_dd{int(trig * 100)}@.5",
                     Config(dd_derisk=trig)))
    cfgs.append(("E_dd20@.25", Config(dd_derisk=0.20, dd_cut=0.25)))
    # F. call-skip rules (recovery accelerators)
    cfgs.append(("F_nocall_belowtrend", Config(skip_call_below_trend=True)))
    cfgs.append(("F_nocall_after10drop",
                 Config(skip_call_after_drop=0.10)))
    cfgs.append(("F_both_skips", Config(skip_call_below_trend=True,
                                        skip_call_after_drop=0.10)))
    # G. repair re-strike
    cfgs.append(("G_repair55", Config(restrike_lo=0.55)))
    # H. cash yield
    cfgs.append(("H_apy4", Config(cash_apy=0.04)))
    # I. inverse-ETF sleeve (synthetic SOXS)
    for f in (0.05, 0.10, 0.20):
        cfgs.append((f"I_soxs{int(f * 100)}", Config(soxs_frac=f)))

    # -- COMBINATIONS ----------------------------------------------------
    combos = {
        "X_inv50+pw.5x25d90": Config(invest_frac=0.50, put_ratio=0.5,
                                     put_dte=90),
        "X_inv50+pw+tp3": Config(invest_frac=0.50, put_ratio=0.5,
                                 put_dte=90, put_tp_mult=3.0),
        "X_inv50+pw+tp3+apy4": Config(invest_frac=0.50, put_ratio=0.5,
                                      put_dte=90, put_tp_mult=3.0,
                                      cash_apy=0.04),
        "X_inv50+dd20": Config(invest_frac=0.50, dd_derisk=0.20),
        "X_pw+dd20": Config(put_ratio=0.5, put_dte=90, dd_derisk=0.20),
        "X_pw+tp3+nocallBT": Config(put_ratio=0.5, put_dte=90,
                                    put_tp_mult=3.0,
                                    skip_call_below_trend=True),
        "X_pw+tp3+nocallD10": Config(put_ratio=0.5, put_dte=90,
                                     put_tp_mult=3.0,
                                     skip_call_after_drop=0.10),
        "X_pw+tp3+repair": Config(put_ratio=0.5, put_dte=90,
                                  put_tp_mult=3.0, restrike_lo=0.55),
        "X_recovery_kit": Config(put_ratio=0.5, put_dte=90, put_tp_mult=3.0,
                                 skip_call_below_trend=True,
                                 restrike_lo=0.55, cash_apy=0.04),
        "X_inv50+pw+tp3+skips+apy4": Config(
            invest_frac=0.50, put_ratio=0.5, put_dte=90, put_tp_mult=3.0,
            skip_call_below_trend=True, skip_call_after_drop=0.10,
            cash_apy=0.04),
        "X_inv60+pw.25x25d90+tp3+apy4": Config(
            invest_frac=0.60, put_ratio=0.25, put_dte=90, put_tp_mult=3.0,
            cash_apy=0.04),
        "X_pw+soxs10": Config(put_ratio=0.5, put_dte=90, soxs_frac=0.10),
        "X_inv50+apy4": Config(invest_frac=0.50, cash_apy=0.04),
    }
    cfgs += list(combos.items())
    return cfgs


def main():
    QA_DIR.mkdir(exist_ok=True)
    print("loading data ...")
    mkt = CallMarket()
    rows = []
    for label, cfg in campaign_configs():
        led, stats = CallDiagonalBacktest(mkt, cfg).run()
        d = risk_diagnostics(led)
        mar = (stats["cagr_pct"] / abs(d["maxDD_pct"])
               if d["maxDD_pct"] else float("nan"))
        rows.append({"label": label} | stats | d | {"MAR": round(mar, 2)})
        print(f"  {label:<32} end={stats['end_wealth']:>10,.0f} "
              f"DD={d['maxDD_pct']:>6.1f}% MAR={mar:4.2f} "
              f"rec={d['dd_recovered']:<12} QA={stats['qa_recon']}")
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "r2_hedge_campaign.csv", index=False)

    cols = ["label", "end_wealth", "cagr_pct", "maxDD_pct", "MAR",
            "dd_recovered", "longest_underwater_wks", "worst_wk_pct",
            "crash25_pct", "crash26_pct", "pct_weeks_income",
            "put_realized", "soxs_realized", "sweep_final", "qa_recon"]
    top = df.sort_values("MAR", ascending=False)
    lines = ["R2 HEDGE CAMPAIGN -- LEVERS ALONE AND COMBINED",
             f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}",
             "sorted by MAR (CAGR / |maxDD|); base PMCC and benchmarks "
             "included", ""]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        lines.append(top[cols].to_string(index=False))
    qa_fail = df["qa_recon"].ne("PASS").sum()
    lines += ["", f"QA reconciliation failures: {qa_fail} of {len(df)}"]
    (QA_DIR / "r2_hedge_report.txt").write_text("\n".join(lines) + "\n")
    print(f"\nresults -> r2_hedge_campaign.csv ({len(df)} runs); "
          f"QA failures: {qa_fail}")


if __name__ == "__main__":
    main()
