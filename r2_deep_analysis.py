#!/usr/bin/env python3
"""
R2 deep dive: drawdown management + IBKR portfolio-margin estimation
====================================================================

Runs the R2 (PMCC) engine with drawdown-management overlays and reports:

  1. OVERLAY GRID -- each overlay vs the base PMCC and the benchmarks:
       * protective put wing (ratio x delta x tenor variants)
       * 50-day-SMA trend filter (halve exposure below trend)
       * high-water-mark de-risk (halve exposure while >20% under water)
       * lower deployment (invest 50%)
       * selected combinations
  2. RISK DIAGNOSTICS per run: calendar-year returns, drawdown episode
     anatomy (depth, length, recovery), the two crash episodes
     (Feb-May 2025, Jun 2026), weekly income regularity.
  3. IBKR PORTFOLIO-MARGIN ESTIMATE, week by week, from the actual
     positions held (Monday post-trade snapshots in the ledger):
       TIMS-style scan: revalue every leg at spot * (1 +/- 15/30/45%)
       -- IBKR scales the equity scan by the ETF's leverage factor, so a
       3x ETF scans +/-45%.  Requirement = worst scenario loss, floored
       at $37.50 per short contract.  Legs are valued at INTRINSIC in
       the scenarios (no residual time value), which overstates the loss
       on long options -> the estimate is deliberately CONSERVATIVE.
       House add-ons are NOT modeled; verify live in TWS "Check Margin".

Outputs:
    r2_dd_overlays.csv        overlay-grid summary + risk diagnostics
    r2_margin_weekly.csv      weekly margin requirement per key config
    qa/r2_deep_report.txt
"""

from pathlib import Path

import numpy as np
import pandas as pd

from soxl_options_loader import ROOT
from call_diagonal_backtest import CallMarket, CallDiagonalBacktest, Config

QA_DIR = Path(__file__).resolve().parent / "qa"
SCAN = (-0.45, -0.30, -0.15, 0.0, 0.15, 0.30, 0.45)
SHORT_MIN = 37.50   # TIMS minimum per short contract


# --------------------------------------------------------------------------
def risk_diagnostics(led):
    """Extra risk stats from a weekly ledger."""
    w = led.copy()
    w["date"] = pd.to_datetime(w["week_start"])
    wealth = w.set_index("date")["end_total_wealth"]
    peak = wealth.cummax()
    dd = wealth / peak - 1
    trough = dd.idxmin()
    peak_date = wealth.loc[:trough].idxmax()
    after = wealth.loc[trough:]
    rec = after[after >= peak.loc[trough]]
    recovery = rec.index[0] if len(rec) else None
    under = (dd < -0.005)
    # longest underwater stretch in weeks
    runs, cur = [], 0
    for v in under:
        cur = cur + 1 if v else 0
        runs.append(cur)
    yearly = {}
    for y, g in wealth.groupby(wealth.index.year):
        start = wealth[wealth.index < g.index[0]]
        base = start.iloc[-1] if len(start) else 150000.0
        yearly[y] = g.iloc[-1] / base - 1

    def episode(a, b):
        win = wealth[(wealth.index >= a) & (wealth.index <= b)]
        return win.iloc[-1] / win.iloc[0] - 1 if len(win) > 1 else np.nan

    inc = led["week_realized"]
    return {
        "maxDD_pct": round(dd.min() * 100, 1),
        "dd_peak": str(peak_date.date()), "dd_trough": str(trough.date()),
        "dd_recovered": str(recovery.date()) if recovery is not None
        else "NEVER (end of data)",
        "longest_underwater_wks": int(max(runs)),
        "ret_2024_pct": round(yearly.get(2024, np.nan) * 100, 1),
        "ret_2025_pct": round(yearly.get(2025, np.nan) * 100, 1),
        "ret_2026_pct": round(yearly.get(2026, np.nan) * 100, 1),
        "crash25_pct": round(episode("2025-02-01", "2025-05-31") * 100, 1),
        "crash26_pct": round(episode("2026-05-25", "2026-07-31") * 100, 1),
        "pct_weeks_income": round((inc > 0).mean() * 100, 0),
        "med_wk_realized": round(inc.median(), 0),
    }


# --------------------------------------------------------------------------
def pm_margin_weekly(led, label):
    """TIMS-style portfolio-margin scan from Monday post-trade snapshots."""
    rows = []
    for r in led.itertuples():
        S = getattr(r, "snap_spot", np.nan)
        if not np.isfinite(S):
            continue
        legs = []          # (right, strike, n, current_mark, sign)
        shares = getattr(r, "snap_shares", np.nan)
        if np.isfinite(shares) and shares > 0:
            legs.append(("S", 0.0, shares / 100, S, +1))
        for pre, right, sgn in (("snap_long", "C", +1),
                                ("snap_short", "C", -1),
                                ("snap_put", "P", +1)):
            n = getattr(r, f"{pre}_n", np.nan)
            if np.isfinite(n) and n > 0:
                legs.append((right, getattr(r, f"{pre}_k"), n,
                             getattr(r, f"{pre}_mark"), sgn))
        if not legs:
            continue
        worst = 0.0
        for mv in SCAN:
            Sx = S * (1 + mv)
            pnl = 0.0
            for right, k, n, mark, sgn in legs:
                if right == "S":
                    val = Sx
                elif right == "C":
                    val = max(Sx - k, 0.0)
                else:
                    val = max(k - Sx, 0.0)
                pnl += sgn * (val - mark) * 100 * n
            worst = min(worst, pnl)
        short_n = getattr(r, "snap_short_n", 0)
        short_n = short_n if np.isfinite(short_n) else 0
        req = max(-worst, SHORT_MIN * short_n)
        eq = r.snap_equity
        rows.append({"config": label, "week_start": r.week_start,
                     "spot": S, "pm_requirement": round(req, 0),
                     "equity": eq,
                     "utilization_pct": round(req / eq * 100, 1),
                     "excess_liquidity": round(eq - req, 0)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
def main():
    QA_DIR.mkdir(exist_ok=True)
    print("loading data ...")
    mkt = CallMarket()

    configs = [
        ("BASE_PMCC", Config()),
        ("BUYHOLD", Config(long_kind="shares", no_short=True)),
        ("LONGONLY", Config(no_short=True)),
        # -- drawdown-management overlays on the base PMCC ---------------
        ("TREND_FILTER", Config(trend_filter=True)),
        ("DD_DERISK_20", Config(dd_derisk=0.20)),
        ("TREND+DD", Config(trend_filter=True, dd_derisk=0.20)),
        ("INVEST_50", Config(invest_frac=0.50)),
        ("PUTWING_0.5x25d60", Config(put_ratio=0.5)),
        ("PUTWING_1x25d60", Config(put_ratio=1.0)),
        ("PUTWING_1x15d60", Config(put_ratio=1.0, put_delta=0.15)),
        ("PUTWING_0.5x25d90", Config(put_ratio=0.5, put_dte=90)),
        ("PUTWING_0.5+TREND", Config(put_ratio=0.5, trend_filter=True)),
        ("C10_PUTWING_0.5", Config(short_delta=0.10, put_ratio=0.5)),
        ("C30_HARVEST+PW", Config(short_delta=0.30, put_ratio=0.5,
                                  restrike_hi=0.93)),
        # margin illustration: leveraged premium sizing
        ("PREMIUM_SIZING", Config(sizing="premium")),
    ]
    rows, ledgers = [], {}
    for label, cfg in configs:
        led, stats = CallDiagonalBacktest(mkt, cfg).run()
        ledgers[label] = led
        stats = {"label": label} | stats | risk_diagnostics(led)
        rows.append(stats)
        print(f"  {label:<20} end={stats['end_wealth']:>12,.0f}  "
              f"maxDD={stats['maxDD_pct']:>6.1f}%  "
              f"2025 crash={stats['crash25_pct']:>6.1f}%  "
              f"2026 crash={stats['crash26_pct']:>6.1f}%  "
              f"QA={stats['qa_recon']}")
    summary = pd.DataFrame(rows)
    summary.to_csv(ROOT / "r2_dd_overlays.csv", index=False)

    # margin estimation for the runs a trader would actually consider
    print("\nestimating weekly IBKR portfolio margin ...")
    margin_frames = []
    for label in ("BASE_PMCC", "PUTWING_0.5x25d60", "TREND+DD",
                  "PREMIUM_SIZING", "BUYHOLD"):
        margin_frames.append(pm_margin_weekly(ledgers[label], label))
    marg = pd.concat(margin_frames, ignore_index=True)
    marg.to_csv(ROOT / "r2_margin_weekly.csv", index=False)
    msum = marg.groupby("config").agg(
        weeks=("pm_requirement", "size"),
        avg_req=("pm_requirement", "mean"),
        p95_req=("pm_requirement", lambda s: s.quantile(.95)),
        max_req=("pm_requirement", "max"),
        avg_util_pct=("utilization_pct", "mean"),
        max_util_pct=("utilization_pct", "max"),
        min_excess_liq=("excess_liquidity", "min")).round(0)

    lines = ["R2 DEEP DIVE -- DRAWDOWN MANAGEMENT & PORTFOLIO MARGIN",
             f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}", ""]
    cols = ["label", "end_wealth", "total_ret_pct", "cagr_pct", "maxDD_pct",
            "longest_underwater_wks", "worst_wk_pct", "ret_2024_pct",
            "ret_2025_pct", "ret_2026_pct", "crash25_pct", "crash26_pct",
            "pct_weeks_income", "med_wk_realized", "sweep_final",
            "put_realized", "qa_recon"]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        lines += ["OVERLAY GRID + DIAGNOSTICS",
                  summary[cols].to_string(index=False), "",
                  "PORTFOLIO MARGIN (TIMS +/-45% scan, intrinsic "
                  "revaluation = conservative; house add-ons not modeled)",
                  msum.to_string(), ""]
    qa_fail = summary["qa_recon"].ne("PASS").sum()
    lines.append(f"QA reconciliation failures: {qa_fail} of {len(summary)}")
    txt = "\n".join(lines)
    (QA_DIR / "r2_deep_report.txt").write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
