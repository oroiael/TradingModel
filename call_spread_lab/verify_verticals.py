#!/usr/bin/env python3
"""
verify_verticals.py  --  independent audit of the mirror-structure + signal round.

  CHECK A  Cross-engine: the general verticals.py engine must reproduce the
           original backtest.py bear_call numbers exactly (two independent code
           paths agreeing on the same trade stream).
  CHECK B  Raw recompute: sample bull_put (put credit) and bull_call (call debit)
           trades and recompute credit/debit and settlement P&L straight from the
           raw yearly CSVs (put & call intrinsic, 20% fills) -- match to a penny.
  CHECK C  No-look-ahead: recompute SMA50 and mom20 at sample dates by hand from
           the raw underlying series and confirm signals.py matches, and that the
           value at date t uses only data <= t.
  CHECK D  Structural claims: SOXL's mean VRP (implied-realized) is negative, and
           the long/debit structures have positive mean return-per-risk while the
           credit structures do not -- recomputed from the saved ledgers.

Run:  python3 call_spread_lab/verify_verticals.py   (non-zero exit on any failure)
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

from data_loader import load_options, underlying_daily_from_options
from backtest import run_backtest, SpreadConfig, build_day_index
from verticals import VConfig, build_index, run
from signals import build_signals

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "outputs"
RAW = {y: ROOT / f"SOXL_Options_{y}.csv" for y in range(2022, 2027)}
FAILS = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def _read_raw_year(y):
    cols = ["expiration", "strike", "right", "bid", "ask", "delta",
            "trade_date", "underlying_price"]
    df = pd.read_csv(RAW[y], low_memory=False, usecols=cols)
    for c in ("trade_date", "expiration"):
        fmt = "%m/%d/%y" if "/" in str(df[c].iloc[0]) else "%Y-%m-%d"
        df[c] = pd.to_datetime(df[c], format=fmt).dt.date
    df["right"] = df["right"].str.upper().str.strip()
    return df


def main():
    print("=" * 76)
    print("INDEPENDENT VERIFICATION -- verticals + signals")
    print("=" * 76)
    opt = load_options(whole_strikes_only=True)

    # ---------------------------------------------------------------- CHECK A
    print("\nCHECK A  cross-engine agreement on bear_call (backtest.py vs verticals.py)")
    idx_old = build_day_index(opt)
    idx_new = build_index(opt)
    for dte in (7, 14, 30):
        old = run_backtest(opt, SpreadConfig(target_dte=dte, dte_tol=(6 if dte == 30 else 4),
                           short_rule="otm_step", short_otm_step=1, width_steps=1),
                           prebuilt=idx_old)
        new = run(opt, VConfig(structure="bear_call", target_dte=dte,
                  dte_tol=(6 if dte == 30 else 4), primary_rule="otm_step",
                  primary_otm_step=1, width_steps=1), prebuilt=idx_new)
        same = (len(old) == len(new) and
                abs(old["pnl_share"].sum() - new["pnl_share"].sum()) < 1e-9 and
                abs(old["ror"].mean() - new["ror"].mean()) < 1e-9)
        check(f"bear_call dte~{dte}: engines agree",
              same, f"old n={len(old)} pnlΣ={old['pnl_share'].sum():+.4f} | "
                    f"new n={len(new)} pnlΣ={new['pnl_share'].sum():+.4f}")

    # ---------------------------------------------------------------- CHECK B
    print("\nCHECK B  independent raw recompute of put-credit & call-debit trades")
    for stru, led_path in [("bull_put", OUT / "vled_bull_put_best.csv"),
                           ("bull_call", OUT / "vled_bull_call_best.csv")]:
        if not led_path.exists():
            check(f"{stru} ledger present", False, "run run_verticals.py first"); continue
        led = pd.read_csv(led_path, parse_dates=["entry_date", "expiration"])
        raw = {y: _read_raw_year(y) for y in led["entry_date"].dt.year.unique()}
        smp = led.sample(min(20, len(led)), random_state=11)
        max_err = 0.0; n = 0
        right = "PUT" if stru == "bull_put" else "CALL"
        for _, t in smp.iterrows():
            df = raw[t["entry_date"].year]
            ed, exp = t["entry_date"].date(), t["expiration"].date()
            legs = df[(df["trade_date"] == ed) & (df["expiration"] == exp) &
                      (df["right"] == right)]
            lo = legs[legs["strike"] == t["k_lo"]]; hi = legs[legs["strike"] == t["k_hi"]]
            if lo.empty or hi.empty:
                continue
            lo, hi = lo.iloc[0], hi.iloc[0]
            def sfill(r): return r["bid"] + 0.20 * (r["ask"] - r["bid"])
            def bfill(r): return r["ask"] - 0.20 * (r["ask"] - r["bid"])
            # settlement underlying on expiration date
            exp_row = df[df["trade_date"] == exp]
            if exp_row.empty:
                for yy in raw:
                    r2 = raw[yy][raw[yy]["trade_date"] == exp]
                    if len(r2):
                        exp_row = r2; break
            S = exp_row["underlying_price"].iloc[0]
            if stru == "bull_put":
                net = sfill(hi) - bfill(lo)                     # credit>0
                owe = max(0.0, t["k_hi"] - S) - max(0.0, t["k_lo"] - S)
                pnl = net - owe
            else:  # bull_call: long lo call, short hi call -> debit
                net = -(bfill(lo) - sfill(hi))                  # net_cash<0 (debit)
                val = max(0.0, S - t["k_lo"]) - max(0.0, S - t["k_hi"])
                pnl = net + val
            # only compare trades that were held to expiration (exit_kind == 'expiry')
            if str(t.get("exit_kind", "expiry")) != "expiry":
                continue
            max_err = max(max_err, abs(pnl - t["pnl_share"])); n += 1
        check(f"{stru}: recomputed settlement P&L matches ({n} trades)",
              max_err < 1e-6, f"max abs err {max_err:.2e}")

    # ---------------------------------------------------------------- CHECK C
    print("\nCHECK C  signals have no look-ahead (recompute SMA50 / mom20 by hand)")
    u = underlying_daily_from_options(opt).set_index("trade_date")["close"]
    u.index = pd.to_datetime(u.index)
    sig = build_signals(opt)
    dates = [d for d in sig.index if pd.Timestamp(d) >= u.index[80]][::200][:5]
    errs = []
    for d in dates:
        dt = pd.Timestamp(d)
        past = u[u.index <= dt]
        sma50_manual = past.tail(50).mean()
        mom20_manual = past.iloc[-1] / past.iloc[-21] - 1
        errs.append(abs(sma50_manual - sig.loc[d, "sma20"] * 0 - sig.loc[d, "sma50"]))
        errs.append(abs(mom20_manual - sig.loc[d, "mom20"]))
    check("SMA50 & mom20 match a trailing hand-recompute (<=t only)",
          max(errs) < 1e-6, f"max abs err {max(errs):.2e}")

    # ---------------------------------------------------------------- CHECK D
    print("\nCHECK D  structural claims")
    vrp_mean = sig["vrp"].mean()
    check("SOXL mean VRP (implied - realized) is negative", vrp_mean < 0,
          f"mean VRP={vrp_mean:+.3f} (options chronically cheap vs realized)")
    sb = pd.read_csv(OUT / "verticals_scoreboard.csv")
    lc = sb[sb["structure"] == "long_call"]["mean_ror"]
    bc = sb[sb["structure"] == "bull_call"]["mean_ror"]
    bp = sb[sb["structure"] == "bull_put"]["mean_ror"]
    check("long_call: all configs positive expectancy", (lc > 0).all(),
          f"min mean_ror={lc.min():+.1%}")
    check("bull_call (debit): majority positive", (bc > 0).mean() > 0.5,
          f"{(bc>0).mean():.0%} positive")
    check("bull_put (credit): majority NOT positive", (bp > 0).mean() < 0.5,
          f"{(bp>0).mean():.0%} positive")

    print("\n" + "=" * 76)
    if FAILS:
        print(f"RESULT: {len(FAILS)} CHECK(S) FAILED -> {FAILS}"); sys.exit(1)
    print("RESULT: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
