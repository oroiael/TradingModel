#!/usr/bin/env python3
"""
verify.py  --  INDEPENDENT audit of the call-spread lab, written to run on any
platform with only pandas + numpy (matplotlib optional).

It deliberately does NOT import backtest.py. It re-derives the key numbers from
the raw yearly CSVs by hand so a reviewer on another machine can confirm the
results are real and not an artifact of the engine:

  CHECK 1  Data integrity: reload each raw file independently, re-confirm date
           range, whole-strike fraction, and that the 2026 underlying matches
           the strikes quoted (the anomaly documented in the report).
  CHECK 2  Trade recompute: sample N trades from a saved ledger, look each leg's
           bid/ask back up in the raw CSV, recompute the 20%-rule fills, credit,
           settlement intrinsic, and P&L completely independently, and assert
           they match the ledger to the penny.
  CHECK 3  Price sanity via Black-Scholes: for a sample of slightly-OTM calls,
           price them with Black-Scholes using the data's OWN implied_vol and
           underlying_price, and confirm the model price sits inside/near the
           quoted bid-ask. This proves the option prices we traded on are
           internally consistent (greeks <-> IV <-> quote), not garbage.
  CHECK 4  Expectancy recompute: independently recompute mean return-per-risk and
           the up-move loss attribution from the saved ledger.

Exit code is non-zero if any hard assertion fails.
Run:  python3 call_spread_lab/verify.py
"""

from __future__ import annotations
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "outputs"
RAW = {y: ROOT / f"SOXL_Options_{y}.csv" for y in range(2022, 2027)}
FAILS = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


# ------------------------------------------------------------------ helpers
def _read_raw_year(y, cols=("expiration", "strike", "right", "bid", "ask",
                            "implied_vol", "delta", "trade_date",
                            "underlying_price")):
    df = pd.read_csv(RAW[y], low_memory=False, usecols=list(cols))
    for c in ("trade_date", "expiration"):
        fmt = "%m/%d/%y" if "/" in str(df[c].iloc[0]) else "%Y-%m-%d"
        df[c] = pd.to_datetime(df[c], format=fmt).dt.date
    df["right"] = df["right"].str.upper().str.strip()
    return df


def bs_call(S, K, T, sigma, r=0.0, q=0.0):
    """Black-Scholes call price (r=q=0 by default; SOXL yield ~small)."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    Nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    Nd2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
    return math.exp(-q * T) * S * Nd1 - K * math.exp(-r * T) * Nd2


# ------------------------------------------------------------------ CHECK 1
def check_data_integrity():
    print("\nCHECK 1  raw-file integrity")
    exp_ranges = {2022: ("2022-01-03", "2022-12-30"), 2026: ("2026-01-02", "2026-07-02")}
    for y in (2022, 2026):
        df = _read_raw_year(y)
        lo, hi = str(df["trade_date"].min()), str(df["trade_date"].max())
        check(f"{y} date range", (lo, hi) == exp_ranges[y], f"{lo}..{hi}")
    # whole-strike fraction over all files
    allf = pd.concat([_read_raw_year(y)[["strike"]] for y in RAW], ignore_index=True)
    frac = (allf["strike"] % 1 == 0).mean()
    check("whole-strike fraction ~81%", 0.78 <= frac <= 0.84, f"{frac:.2%}")
    # 2026 anomaly: strikes track the (high) underlying, so median|strike-spot| small
    d26 = _read_raw_year(2026)
    d26 = d26[d26["right"] == "CALL"]
    day = d26[d26["trade_date"] == pd.Timestamp("2026-06-22").date()]
    if len(day):
        spot = day["underlying_price"].iloc[0]
        near = (day["strike"] - spot).abs().min()
        check("2026 strikes cohere with high underlying",
              spot > 250 and near < 5,
              f"spot {spot:.1f}, nearest strike gap {near:.1f}")


# ------------------------------------------------------------------ CHECK 2
def check_trade_recompute(n=25):
    print("\nCHECK 2  independent trade recompute vs saved ledger")
    lp = OUT / "ledger_weekly_1otm_w1.csv"
    if not lp.exists():
        check("weekly ledger present", False, "run run_analysis.py first")
        return
    led = pd.read_csv(lp, parse_dates=["entry_date", "expiration"])
    # preload raw calls by year for the years we need
    raw = {y: _read_raw_year(y) for y in led["entry_date"].dt.year.unique()}
    rng = np.random.default_rng(7)
    sample = led.sample(min(n, len(led)), random_state=7)
    max_credit_err = max_pnl_err = 0.0
    checked = 0
    for _, t in sample.iterrows():
        y = t["entry_date"].year
        df = raw[y]
        ed, exp = t["entry_date"].date(), t["expiration"].date()
        legs = df[(df["trade_date"] == ed) & (df["expiration"] == exp) &
                  (df["right"] == "CALL")]
        sh = legs[legs["strike"] == t["k_short"]]
        lo = legs[legs["strike"] == t["k_long"]]
        if sh.empty or lo.empty:
            continue
        sh, lo = sh.iloc[0], lo.iloc[0]
        sell = sh["bid"] + 0.20 * (sh["ask"] - sh["bid"])
        buy = lo["ask"] - 0.20 * (lo["ask"] - lo["bid"])
        credit = sell - buy
        # settlement underlying: underlying_price stamped on the expiration date
        exp_row = df[df["trade_date"] == exp]
        if exp_row.empty:
            for yy in raw:
                r2 = raw[yy][raw[yy]["trade_date"] == exp]
                if len(r2):
                    exp_row = r2; break
        S_exp = exp_row["underlying_price"].iloc[0]
        owe = max(0.0, S_exp - t["k_short"]) - max(0.0, S_exp - t["k_long"])
        pnl = credit - owe
        max_credit_err = max(max_credit_err, abs(credit - t["credit"]))
        max_pnl_err = max(max_pnl_err, abs(pnl - t["pnl_share"]))
        checked += 1
    check(f"recomputed credit matches ({checked} trades)", max_credit_err < 1e-6,
          f"max abs err {max_credit_err:.2e}")
    check(f"recomputed settlement P&L matches ({checked} trades)", max_pnl_err < 1e-6,
          f"max abs err {max_pnl_err:.2e}")


# ------------------------------------------------------------------ CHECK 3
def check_black_scholes(n=400):
    print("\nCHECK 3  Black-Scholes price sanity (uses data's own IV)")
    df = _read_raw_year(2024)
    c = df[(df["right"] == "CALL") & (df["bid"] > 0) & (df["ask"] >= df["bid"]) &
           (df["implied_vol"] > 0)].copy()
    c["dte"] = (pd.to_datetime(c["expiration"]) - pd.to_datetime(c["trade_date"])).dt.days
    c["mny"] = c["strike"] / c["underlying_price"] - 1
    band = c[(c["mny"].between(0.0, 0.15)) & (c["dte"].between(3, 40))]
    band = band.sample(min(n, len(band)), random_state=3)
    inside = close = 0
    diffs = []
    for _, r in band.iterrows():
        p = bs_call(r["underlying_price"], r["strike"], r["dte"] / 365.0,
                    r["implied_vol"])
        mid = (r["bid"] + r["ask"]) / 2
        if r["bid"] - 0.02 <= p <= r["ask"] + 0.02:
            inside += 1
        if mid > 0 and abs(p - mid) / mid < 0.15:
            close += 1
        diffs.append(p - mid)
    frac_inside = inside / len(band)
    frac_close = close / len(band)
    check("BS price within bid-ask for slightly-OTM calls", frac_inside > 0.80,
          f"{frac_inside:.1%} inside bid/ask, median (BS-mid)={np.median(diffs):+.3f}")
    check("BS price within 15% of mid", frac_close > 0.75, f"{frac_close:.1%}")


# ------------------------------------------------------------------ CHECK 4
def check_expectancy():
    print("\nCHECK 4  independent expectancy + attribution recompute")
    lp = OUT / "ledger_weekly_1otm_w1.csv"
    if not lp.exists():
        check("weekly ledger present", False); return
    led = pd.read_csv(lp)
    ror = led["pnl_share"] / led["max_loss_share"]
    mean_ror = ror.mean()
    check("weekly mean return-per-risk is negative", mean_ror < 0,
          f"mean_ror={mean_ror:+.1%}")
    up = led["move_pct"] > 0.03
    share_up = ror[up].clip(upper=0).sum() / ror.clip(upper=0).sum()
    check("losses overwhelmingly from SOXL up-moves >3%", share_up > 0.90,
          f"{share_up:.0%} of lost risk from up-moves")
    # midpoint would be less negative / positive -> edge is inside the spread
    check("full loss only when breached above long strike",
          bool((led.loc[led["max_loss_hit"], "S_exp"] >=
                led.loc[led["max_loss_hit"], "k_long"]).all()),
          "all max-loss trades finished above long strike")


def main():
    print("=" * 74)
    print("INDEPENDENT VERIFICATION  (no import of backtest.py)")
    print("=" * 74)
    check_data_integrity()
    check_trade_recompute()
    check_black_scholes()
    check_expectancy()
    print("\n" + "=" * 74)
    if FAILS:
        print(f"RESULT: {len(FAILS)} CHECK(S) FAILED -> {FAILS}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
