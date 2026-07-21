#!/usr/bin/env python3
"""
verify_strangle.py  --  independent audit of the strangle-harvesting engine.

  CHECK A  Raw-quote consistency: sample opens & harvests from the engine's trade
           log and recompute each fill (20% rule) straight from the raw yearly CSV
           for that (date, right, expiration, strike) -- must match to a penny.
  CHECK B  Cash reconciliation: rebuild end cash & equity purely from the trade
           log's cash flows (opens out, harvests/expiries in) + the marked value
           of the legs still open at the end -- must equal the engine's numbers.
  CHECK C  Structural sanity: harvests really cleared the take threshold; expiries
           settle at non-negative intrinsic; nothing trades after its expiration;
           peak deployment in [0,1]; the sim is deterministic.
  CHECK D  Study claim: at the best cell, active harvesting reduces drawdown vs the
           no-harvest baseline.

Run:  python3 call_spread_lab/verify_strangle.py   (non-zero exit on any failure)
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

from data_loader import load_options
from verticals import build_index
from strangle_harvest import HConfig, simulate, stats, compact_index, CONTRACT

ROOT = Path(__file__).resolve().parent.parent
RAW = {y: ROOT / f"SOXL_Options_{y}.csv" for y in range(2022, 2027)}
FAILS = []
BEST = dict(dte_target=120, dte_tol=20, dist=0.075, take=0.50, leg_frac=0.15)


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def _read_raw_year(y):
    df = pd.read_csv(RAW[y], low_memory=False,
                     usecols=["expiration", "strike", "right", "bid", "ask",
                              "trade_date", "underlying_price"])
    for c in ("trade_date", "expiration"):
        fmt = "%m/%d/%y" if "/" in str(df[c].iloc[0]) else "%Y-%m-%d"
        df[c] = pd.to_datetime(df[c], format=fmt).dt.date
    df["right"] = df["right"].str.upper().str.strip()
    return df


def main():
    print("=" * 76)
    print("INDEPENDENT VERIFICATION -- strangle harvesting engine")
    print("=" * 76)
    opt = load_options(whole_strikes_only=True)
    idx = build_index(opt)
    compact = compact_index(idx)
    res = simulate(idx, HConfig(**BEST), compact)
    log = res["log"]

    # ---------------------------------------------------------------- CHECK A
    print("\nCHECK A  raw-quote fill consistency (opens & harvests vs raw CSV)")
    raw = {}
    max_err = 0.0
    n = 0
    ev = log[log["action"].isin(["open", "harvest"])]
    smp = ev.sample(min(30, len(ev)), random_state=5)
    for _, r in smp.iterrows():
        y = pd.Timestamp(r["date"]).year
        if y not in raw:
            raw[y] = _read_raw_year(y)
        df = raw[y]
        row = df[(df["trade_date"] == pd.Timestamp(r["date"]).date()) &
                 (df["right"] == r["right"]) &
                 (df["expiration"] == pd.Timestamp(r["exp"]).date()) &
                 (df["strike"] == r["strike"])]
        if row.empty:
            continue
        bid, ask = float(row["bid"].iloc[0]), float(row["ask"].iloc[0])
        if r["action"] == "open":
            fill = ask - 0.20 * (ask - bid)      # buy
        else:
            fill = bid + 0.20 * (ask - bid)      # sell (harvest)
        max_err = max(max_err, abs(fill - r["px"]))
        n += 1
    check(f"engine fills == raw 20%-rule fills ({n} events)", max_err < 1e-9,
          f"max abs err {max_err:.2e}")

    # ---------------------------------------------------------------- CHECK B
    print("\nCHECK B  cash & equity reconciliation from the trade log")
    opens = log[log["action"] == "open"]
    outs = (opens["n"] * opens["px"] * CONTRACT).sum()
    ins = log[log["action"].isin(["harvest", "expire"])]
    ins_cash = (ins["n"] * ins["px"] * CONTRACT).sum()
    recon_cash = 100_000.0 + ins_cash - outs
    open_marks = sum(l["n"] * l["last_mark"] * CONTRACT for l in res["end_legs"])
    recon_equity = recon_cash + open_marks
    check("reconstructed end cash == engine end cash",
          abs(recon_cash - res["end_cash"]) < 1e-6,
          f"log ${recon_cash:,.2f} vs engine ${res['end_cash']:,.2f}")
    check("reconstructed end equity == engine end equity",
          abs(recon_equity - res["equity"][-1]) < 1e-6,
          f"log ${recon_equity:,.2f} vs engine ${res['equity'][-1]:,.2f}")

    # ---------------------------------------------------------------- CHECK C
    print("\nCHECK C  structural sanity")
    harv = log[log["action"] == "harvest"]
    check("all harvests cleared the take threshold", bool((harv["leg_ret"] >= BEST["take"] - 1e-9).all()),
          f"min harvest leg_ret {harv['leg_ret'].min():+.2%} (take {BEST['take']:.0%})")
    exp = log[log["action"] == "expire"]
    check("all expiries settle at non-negative intrinsic", bool((exp["px"] >= -1e-12).all()),
          f"min expiry px {exp['px'].min():.4f}")
    bad = ((pd.to_datetime(log["date"]) > pd.to_datetime(log["exp"])) &
           (log["action"] != "expire")).sum()
    check("no leg trades after its expiration (open/harvest)", bad == 0, f"{bad} violations")
    check("peak deployment within [0,1]", 0 <= res["peak_deploy"] <= 1.0001,
          f"{res['peak_deploy']:.1%}")
    res2 = simulate(idx, HConfig(**BEST), compact)
    check("deterministic (re-run identical end equity)",
          abs(res2["equity"][-1] - res["equity"][-1]) < 1e-9)

    # ---------------------------------------------------------------- CHECK D
    print("\nCHECK D  study claim: harvesting reduces drawdown vs no-harvest")
    s_h = stats(res, HConfig(**BEST))
    nh = {**BEST, "take": 999}
    s_n = stats(simulate(idx, HConfig(**nh), compact), HConfig(**nh))
    check("harvest maxDD is shallower than no-harvest maxDD",
          s_h["max_dd"] > s_n["max_dd"],
          f"harvest {s_h['max_dd']:+.0%} vs no-harvest {s_n['max_dd']:+.0%}")

    print("\n" + "=" * 76)
    if FAILS:
        print(f"RESULT: {len(FAILS)} CHECK(S) FAILED -> {FAILS}"); sys.exit(1)
    print("RESULT: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
