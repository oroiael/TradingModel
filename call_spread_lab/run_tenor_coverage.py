#!/usr/bin/env python3
"""
run_tenor_coverage.py  --  did we drop 90-180 DTE for the trailing stop because
they FAIL, or because the intraday DATA can't cover them? Answers both, with data.

1. Intraday LOOKBACK: for each expiration, how many days before expiry does the
   5-min option data actually start? -> implied % of a T-day hold that the trailing
   signal can even see.
2. Tenor comparison: EOD close-harvest vs trailing (arm25%/trail15%) at
   30/45/60/90/120/150/180 DTE over 2022-2026, plus the share of trailing exits
   that actually fired (vs legs that just expired because no intraday data covered
   them). If trailing barely fires at long tenors, that's a coverage artifact, not
   a verdict that long tenors don't work.
"""
from __future__ import annotations
import pickle
from pathlib import Path
import numpy as np
import pandas as pd

from data_loader import load_options
from verticals import build_index
from strangle_harvest import HConfig, simulate, stats, compact_index

SCRATCH = Path("/tmp/claude-0/-home-user-TradingModel/3ee6862d-4424-5812-9b50-ba533ce0c5cb/scratchpad")
CACHE = SCRATCH / "real_hlc.pkl"
SLIP = 0.05
pd.set_option("display.width", 220)


def hr(t): print("\n" + "=" * 88 + f"\n{t}\n" + "=" * 88)


def main():
    hr("LOAD")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt); compact = compact_index(idx)
    with open(CACHE, "rb") as f:
        hlc = pickle.load(f)
    real_hilo = {k: (v[0], v[1]) for k, v in hlc.items()}

    # --- 1. intraday lookback per expiration -----------------------------------
    hr("1.  INTRADAY LOOKBACK: how many days before expiry does the 5-min data start?")
    first_seen = {}
    for (d, r, exp, k) in hlc:
        if exp not in first_seen or d < first_seen[exp]:
            first_seen[exp] = d
    look = pd.Series({exp: (pd.Timestamp(exp) - pd.Timestamp(d0)).days
                      for exp, d0 in first_seen.items()})
    print(f"expirations with intraday data: {len(look)}")
    print(f"lookback (days before expiry) — median {look.median():.0f}, "
          f"25th {look.quantile(.25):.0f}, 75th {look.quantile(.75):.0f}, max {look.max():.0f}")
    print("\nimplied trailing-signal coverage of a T-day hold (median lookback / T, capped 100%):")
    med = look.median()
    for T in (30, 45, 60, 90, 120, 150, 180):
        print(f"   {T:3d} DTE: ~{min(med / T, 1.0):.0%} of the hold has intraday data "
              f"(fraction of expirations with >= {T}d lookback: {(look >= T).mean():.0%})")

    # --- 2. tenor comparison: EOD vs trailing, + how often trailing fired -------
    hr("2.  EOD close-harvest vs TRAILING (arm 25%, trail 15%) by tenor, 2022-2026")
    print(f"  {'DTE':>4} | {'EOD CAGR':>8} {'EOD DD':>7} | {'TRAIL CAGR':>10} {'TRAIL DD':>8} "
          f"| {'trail-exits':>11} {'expired':>8} {'trail-fired%':>12}")
    for T in (30, 45, 60, 90, 120, 150, 180):
        base = dict(dte_target=T, dte_tol=(12 if T <= 45 else (15 if T < 90 else 20)),
                    dist=0.075, leg_frac=0.15)
        eod = simulate(idx, HConfig(take=0.50, **base), compact)
        tr = simulate(idx, HConfig(harvest_mode="trailing", arm_pct=0.25, trail_pct=0.15, **base),
                      compact, intraday=(None, None, SLIP), real_hilo=real_hilo)
        se, st = stats(eod, HConfig(**base)), stats(tr, HConfig(**base))
        lg = tr["log"]
        n_trail = int((lg["action"] == "harvest_trail").sum()) if len(lg) else 0
        n_exp = int((lg["action"] == "expire").sum()) if len(lg) else 0
        fired = n_trail / (n_trail + n_exp) if (n_trail + n_exp) else 0.0
        print(f"  {T:>4} | {se['cagr']:>+8.0%} {se['max_dd']:>+7.0%} | "
              f"{st['cagr']:>+10.0%} {st['max_dd']:>+8.0%} | {n_trail:>11} {n_exp:>8} {fired:>11.0%}")

    hr("READ")
    print("If 'trail-fired%' stays high at 90-180 DTE, the trailing signal is covering")
    print("those holds and the CAGR is a fair verdict. If it DROPS at long tenors, the")
    print("intraday data can't see the early part of the hold -> those tenors are")
    print("data-handicapped for trailing, NOT proven to fail. (EOD uses full daily data")
    print("at every tenor, so the EOD column is always a fair comparison.)")


if __name__ == "__main__":
    main()
