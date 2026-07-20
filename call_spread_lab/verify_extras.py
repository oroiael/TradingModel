#!/usr/bin/env python3
"""
verify_extras.py  --  independent audit of the intraday + rotation additions.

  CHECK A  Black-Scholes sanity: put-call parity (C - P == S - K at r=0) and a
           reference value.
  CHECK B  Cash reconciliation WITH the new actions (harvest_intraday, rotate_out):
           rebuild end cash from the trade log and match the engine.
  CHECK C  Intraday integrity: intraday harvests occur ONLY on 5-min days, and a
           sampled intraday exit price reproduces BS(day-extreme, prior-EOD IV) *
           (1-slip) independently.
  CHECK D  Rotation integrity + no look-ahead: while a side is de-selected by the
           vol regime it is never re-armed (no 'open' of that side), and the
           regime at day t uses only realized vol computable from data <= t.
  CHECK E  Determinism.

Run:  python3 call_spread_lab/verify_extras.py   (non-zero exit on any failure)
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

from data_loader import load_options, load_5min, underlying_daily_from_options
from verticals import build_index
from signals import build_signals
from strangle_harvest import (HConfig, simulate, compact_index, build_hilo,
                              build_iv_key, CONTRACT)
from bs import bs_call, bs_put
from run_rotation import regime_sides

FAILS = []
BEST = dict(dte_target=120, dte_tol=20, dist=0.075, take=0.50, leg_frac=0.15)


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    print("=" * 76 + "\nINDEPENDENT VERIFICATION -- intraday + rotation\n" + "=" * 76)

    # ---------------------------------------------------------------- CHECK A
    print("\nCHECK A  Black-Scholes sanity")
    S, K, T, sig = 50.0, 55.0, 0.33, 0.9
    parity = (bs_call(S, K, T, sig) - bs_put(S, K, T, sig)) - (S - K)
    check("put-call parity holds (r=0)", abs(parity) < 1e-9, f"resid {parity:.2e}")
    check("ATM call price in sane range", 0 < bs_call(50, 50, 0.33, 0.9) < 50,
          f"{bs_call(50,50,0.33,0.9):.2f}")

    # ---------------------------------------------------------------- setup
    opt = load_options(whole_strikes_only=True)
    idx = build_index(opt)
    compact = compact_index(idx)
    fm = load_5min()
    hilo = build_hilo(fm)
    ivk = build_iv_key(opt)
    tds = idx[3]
    prev = {tds[i]: tds[i - 1] for i in range(1, len(tds))}
    win = [t for t in tds if min(hilo) <= t <= max(hilo)]
    sidx = (idx[0], idx[1], idx[2], win)
    slip = 0.05
    res = simulate(sidx, HConfig(**BEST), compact, intraday=(hilo, ivk, slip))
    log = res["log"]

    # ---------------------------------------------------------------- CHECK B
    print("\nCHECK B  cash reconciliation incl. harvest_intraday / rotate_out")
    outs = log[log["action"] == "open"]
    outsum = (outs["n"] * outs["px"] * CONTRACT).sum()
    ins = log[log["action"].isin(["harvest", "harvest_intraday", "expire", "rotate_out"])]
    insum = (ins["n"] * ins["px"] * CONTRACT).sum()
    recon = 100_000.0 + insum - outsum
    check("reconstructed end cash == engine end cash",
          abs(recon - res["end_cash"]) < 1e-6,
          f"log ${recon:,.2f} vs engine ${res['end_cash']:,.2f}")

    # ---------------------------------------------------------------- CHECK C
    print("\nCHECK C  intraday harvests: 5-min-only + reproducible BS exit price")
    intr = log[log["action"] == "harvest_intraday"]
    on_5min = intr["date"].apply(lambda d: d in hilo).all() if len(intr) else True
    check("all intraday harvests fall on 5-min days", bool(on_5min), f"{len(intr)} events")
    smp = intr.sample(min(15, len(intr)), random_state=4) if len(intr) else intr
    max_err, n = 0.0, 0
    for _, r in smp.iterrows():
        td = r["date"]; ptd = prev.get(td)
        iv = ivk.get((ptd, r["right"], r["exp"], r["strike"])) if ptd else None
        if iv is None:
            continue
        hi, lo = hilo[td]
        T = max((pd.Timestamp(r["exp"]) - pd.Timestamp(td)).days, 0) / 365.0
        peak = (bs_call(hi, r["strike"], T, iv) if r["right"] == "CALL"
                else bs_put(lo, r["strike"], T, iv))
        max_err = max(max_err, abs(peak * (1 - slip) - r["px"])); n += 1
    check(f"intraday exit px == BS(extreme, prior-EOD IV)*(1-slip) ({n} events)",
          max_err < 1e-6, f"max abs err {max_err:.2e}")

    # ---------------------------------------------------------------- CHECK D
    print("\nCHECK D  rotation: de-selected side never re-armed + trailing signal")
    sig = build_signals(opt)
    rs = regime_sides(sig, 0.90, "trend")
    rres = simulate(idx, HConfig(**BEST), compact, regime_sides=rs)
    rlog = rres["log"]
    opens = rlog[rlog["action"] == "open"]
    bad = 0
    for _, o in opens.iterrows():
        allowed = rs.get(o["date"], frozenset({"CALL", "PUT"}))
        if o["right"] not in allowed:
            bad += 1
    check("no leg opened on a side the regime de-selected that day", bad == 0,
          f"{bad} violations of {len(opens)} opens")
    # no look-ahead: regime at t reproduces from trailing realized vol only
    u = underlying_daily_from_options(opt).set_index("trade_date")["close"]
    u.index = pd.to_datetime(u.index)
    logret = np.log(u / u.shift(1))
    rv_manual = (logret.rolling(20).std() * np.sqrt(252))
    sample_days = [d for d in list(rs)[80::200]][:5]
    ok = True
    for d in sample_days:
        rvm = rv_manual.loc[pd.Timestamp(d)]
        both = rs[d] == frozenset({"CALL", "PUT"})
        if rvm == rvm:               # not warm-up NaN
            expect_both = rvm >= 0.90
            if both != expect_both:
                ok = False
    check("regime(t) matches trailing rvol computed from data<=t only", ok)

    # ---------------------------------------------------------------- CHECK E
    print("\nCHECK E  determinism")
    r2 = simulate(sidx, HConfig(**BEST), compact, intraday=(hilo, ivk, slip))
    check("intraday sim reproducible", abs(r2["equity"][-1] - res["equity"][-1]) < 1e-9)

    print("\n" + "=" * 76)
    if FAILS:
        print(f"RESULT: {len(FAILS)} CHECK(S) FAILED -> {FAILS}"); sys.exit(1)
    print("RESULT: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
