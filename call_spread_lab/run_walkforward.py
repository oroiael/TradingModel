#!/usr/bin/env python3
"""
run_walkforward.py  --  is the trailing-stop edge REAL or fitted? Out-of-sample test.

The +71% trailing number picked the best (arm,trail) over the whole 2022-2026 sample
-- that is in-sample cheating. Here we never let the choice see the future:

  * candidates = {EOD close-harvest} U {trailing over an arm x trail grid}
  * timeline split into 6-month TEST windows (2023-01 .. 2026-07)
  * before each test window, SELECT the candidate with the best score on all PRIOR
    data only (expanding train), then trade that choice through the test window
  * chain the test windows into one out-of-sample equity curve

Two honest selection rules are shown: pick the past best RETURN (a return-chaser),
and pick the past best RETURN/DRAWDOWN (a risk-aware picker). Compared against the
same windowed scheme run with a FIXED EOD baseline and a FIXED trailing config, and
against the in-sample best (the cheating number). Real 2022-2026 intraday prices.
"""
from __future__ import annotations
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

from data_loader import load_options
from verticals import build_index
from strangle_harvest import HConfig, simulate, stats, compact_index

OUT = Path(__file__).resolve().parent / "outputs"
SCRATCH = Path("/tmp/claude-0/-home-user-TradingModel/3ee6862d-4424-5812-9b50-ba533ce0c5cb/scratchpad")
CACHE = SCRATCH / "real_hlc.pkl"
SLIP = 0.05
DTE = 60
BASE = dict(dte_target=DTE, dte_tol=15, dist=0.075, leg_frac=0.15)
pd.set_option("display.width", 220)


def hr(t): print("\n" + "=" * 88 + f"\n{t}\n" + "=" * 88)


# candidate strategies -----------------------------------------------------------
def candidates(real_hi, real_hilo):
    cs = [("EOD+50%", dict(cfg=HConfig(take=0.50, **BASE), kw={}))]
    for arm in (0.25, 0.50, 1.00):
        for tr in (0.15, 0.25, 0.40):
            cs.append((f"trail a{arm:.0%}/t{tr:.0%}",
                       dict(cfg=HConfig(harvest_mode="trailing", arm_pct=arm, trail_pct=tr, **BASE),
                            kw=dict(intraday=(None, None, SLIP), real_hilo=real_hilo))))
    return cs


def run_win(idx, compact, cand, start, end, cap0):
    c, s, q, tds = idx
    sl = (c, s, q, [t for t in tds if (start is None or t >= start) and t < end])
    cfg = cand["cfg"]
    cfg = HConfig(**{**cfg.__dict__, "cap0": cap0})
    return simulate(sl, cfg, compact, **cand["kw"])


def score(res, metric):
    s = stats(res, HConfig(**BASE))
    if not s or s.get("end_equity", 0) <= 0:
        return -9.99
    if metric == "return":
        return s["cagr"]
    return s["cagr"] / (abs(s["max_dd"]) + 0.05)      # return / drawdown


def chain(idx, compact, cands, windows, selector, metric=None):
    """Walk the windows. selector='fixed:<name>' or 'select'. Returns chained
    equity, dates, and the per-window choice."""
    cap = 100_000.0
    eq_all, dt_all, picks = [], [], []
    for (tr_start, te_start, te_end) in windows:
        if selector.startswith("fixed:"):
            name = selector.split(":", 1)[1]
            cand = dict(cands)[name]; pick = name
        else:
            # select on PRIOR data only (expanding train: everything before te_start)
            best, bestname = None, None
            for name, cand in cands:
                r = run_win(idx, compact, cand, tr_start, te_start, 100_000.0)
                sc = score(r, metric)
                if best is None or sc > best:
                    best, bestname = sc, name
            cand = dict(cands)[bestname]; pick = bestname
        # trade the choice through the test window, continuing the capital
        r = run_win(idx, compact, cand, te_start, te_end, cap)
        if len(r["equity"]):
            cap = float(r["equity"][-1])
            eq_all.extend(r["equity"]); dt_all.extend(r["dates"])
        picks.append((str(te_start)[:7], pick))
    return np.array(eq_all), dt_all, picks, cap


def curve_stats(eq, dts):
    if len(eq) == 0:
        return dict(cagr=np.nan, maxdd=np.nan, end=np.nan)
    e = np.concatenate([[100_000.0], eq])
    dd = (e / np.maximum.accumulate(e) - 1).min()
    yrs = (pd.Timestamp(dts[-1]) - pd.Timestamp(dts[0])).days / 365.25
    cagr = (eq[-1] / 100_000.0) ** (1 / yrs) - 1 if eq[-1] > 0 and yrs > 0 else np.nan
    return dict(cagr=cagr, maxdd=dd, end=eq[-1])


def main():
    hr(f"LOAD  ({DTE} DTE strangle, walk-forward OOS)")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt); compact = compact_index(idx)
    with open(CACHE, "rb") as f:
        hlc = pickle.load(f)
    real_hi = {k: v[0] for k, v in hlc.items()}
    real_hilo = {k: (v[0], v[1]) for k, v in hlc.items()}
    cands = candidates(real_hi, real_hilo)

    # 6-month test windows, expanding train (min ~12mo of history before first test)
    starts = pd.date_range("2023-01-01", "2026-07-01", freq="6MS")
    windows = []
    for s in starts:
        te_end = (s + pd.DateOffset(months=6)).date()
        windows.append((None, s.date(), min(te_end, pd.Timestamp("2026-07-03").date())))
    print(f"OOS test windows: {[str(w[1])[:7] for w in windows]}")
    print(f"candidates: {len(cands)}  (EOD + {len(cands)-1} trailing configs)")

    hr("IN-SAMPLE (cheating) reference: best single config over the WHOLE period")
    best_is, best_is_name = None, None
    for name, cand in cands:
        r = run_win(idx, compact, cand, None, pd.Timestamp("2026-07-03").date(), 100_000.0)
        s = stats(r, HConfig(**BASE))
        if best_is is None or s["cagr"] > best_is:
            best_is, best_is_name = s["cagr"], name
    print(f"  in-sample best: {best_is_name}  CAGR {best_is:+.0%}  (this is the number to beat honestly)")

    hr("OUT-OF-SAMPLE walk-forward (choice never sees the future)")
    schemes = {
        "WF select by RETURN": ("select", "return"),
        "WF select by RETURN/DD": ("select", "riskadj"),
        "FIXED EOD+50% (windowed)": ("fixed:EOD+50%", None),
        "FIXED trail a25%/t25% (windowed)": ("fixed:trail a25%/t25%", None),
    }
    results = {}
    for label, (sel, metric) in schemes.items():
        eq, dts, picks, cap = chain(idx, compact, cands, windows, sel, metric)
        cs = curve_stats(eq, dts)
        results[label] = (eq, dts, picks, cs)
        print(f"\n  {label}")
        print(f"     OOS CAGR {cs['cagr']:+.0%}   maxDD {cs['maxdd']:+.0%}   end ${cs['end']:,.0f}")
        if sel == "select":
            print("     picks per window: " + ", ".join(f"{d}:{p}" for d, p in picks))

    hr("VERDICT")
    wf = results["WF select by RETURN"][3]["cagr"]
    fx = results["FIXED EOD+50% (windowed)"][3]["cagr"]
    print(f"  in-sample best (cheating):        {best_is:+.0%} CAGR")
    print(f"  walk-forward, return-selected:    {wf:+.0%} CAGR  (honest, out-of-sample)")
    print(f"  fixed EOD baseline (windowed):    {fx:+.0%} CAGR")
    print(f"\n  If WF ~ in-sample best -> the edge is REAL. If WF collapses toward (or below)")
    print(f"  the EOD baseline -> the +71% was largely FITTED. The gap is the honesty tax.")

    _plot(results)
    print(f"\n  saved outputs/walkforward.png")


def _plot(results):
    fig, ax = plt.subplots(figsize=(12, 5.5))
    colors = {"WF select by RETURN": "tab:green", "WF select by RETURN/DD": "tab:olive",
              "FIXED EOD+50% (windowed)": "tab:blue", "FIXED trail a25%/t25% (windowed)": "tab:red"}
    for label, (eq, dts, picks, cs) in results.items():
        if len(eq):
            ax.plot(pd.to_datetime(dts), eq, label=f"{label}  ({cs['cagr']:+.0%})",
                    lw=1.5, color=colors.get(label))
    ax.axhline(100_000, color="k", lw=0.6, ls="--")
    ax.set_yscale("log"); ax.set_ylabel("equity ($, log)")
    ax.set_title(f"{DTE} DTE trailing stop: walk-forward (out-of-sample) vs baselines, 2023-2026")
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(OUT / "walkforward.png", dpi=110)


if __name__ == "__main__":
    main()
