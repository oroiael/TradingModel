#!/usr/bin/env python3
"""
Put Policy Lab -- what should we do with the protective put?
============================================================

Answers the question: the put is expensive insurance -- how should it be
used?  Three parts, all on REAL quotes from the merged raw ThetaData
exports:

PART 1 -- BACKTEST VARIANTS. Re-runs the full backtest (current optimized
configuration held fixed) under different put-management policies:

    baseline        hold; roll UP at +20%; conditional -15% exit (spec)
    no_hedge        no put at all -- what the insurance actually buys us
    no_rolls        buy the put, never roll, hold to expiration
    rolldown_10     also roll DOWN at -10% vs basis (harvest gain,
                    re-strike ATM); exit disabled
    rolldown_20     roll DOWN at -20%; exit disabled
    harvest_2x      sell + re-strike ATM whenever the put marks >= 2x cost
    exit_uncond_15  liquidate EVERYTHING at -15% vs basis (put, shares,
                    call buyback), restart the following Monday
    exit_uncond_20  same at -20%

PART 2 -- EXERCISE vs SELL. Across every ITM put row in the data: how much
time value does exercising forfeit versus selling at the bid, and how
often is the bid actually BELOW intrinsic (the only case where exercising
beats selling)?

PART 3 -- PUT SPREADS. At each put purchase date of the baseline run: what
would selling a lower-strike put (75% / 65% of the long strike, same
expiration, real bid) have recovered of the long put's cost, and what
protection would have been given up?

Output: printed report + qa/put_policy_report.txt + put_policy_results.csv
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

import soxl_weekly_income_backtest as bt
from soxl_options_loader import load_raw_options

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "qa" / "put_policy_report.txt"
OUT_CSV = ROOT / "put_policy_results.csv"

DEFAULTS = dict(ROLL_MOVE=0.20, ROLL_DOWN_MOVE=None, HARVEST_MULT=None,
                EXIT_MODE="conditional", EXIT_DROP=0.15, HEDGE_ENABLED=True)

POLICIES = {
    "baseline":       {},
    "no_hedge":       {"HEDGE_ENABLED": False, "EXIT_MODE": "off"},
    "no_rolls":       {"ROLL_MOVE": None, "EXIT_MODE": "off"},
    "no_rolls_cond_exit": {"ROLL_MOVE": None},
    "rolldown_10":    {"ROLL_DOWN_MOVE": 0.10, "EXIT_MODE": "off"},
    "rolldown_20":    {"ROLL_DOWN_MOVE": 0.20, "EXIT_MODE": "off"},
    "harvest_2x":     {"HARVEST_MULT": 2.0, "EXIT_MODE": "off"},
    "exit_uncond_15": {"EXIT_MODE": "unconditional", "EXIT_DROP": 0.15},
    "exit_uncond_20": {"EXIT_MODE": "unconditional", "EXIT_DROP": 0.20},
}

_lines = []


def emit(msg=""):
    print(msg)
    _lines.append(str(msg))


def metrics(df, name):
    bal = pd.to_numeric(df["end_total_with_side"])
    ret = bal.pct_change().dropna()
    dd = bal / bal.cummax() - 1
    prem = pd.to_numeric(df["call_premium_received"],
                         errors="coerce").fillna(0)
    put_costs = (pd.to_numeric(df["put_open_cost"], errors="coerce")
                 .fillna(0).sum()
                 + pd.to_numeric(df["put_roll_cost"], errors="coerce")
                 .fillna(0).sum())
    return {
        "policy": name,
        "end_total": round(bal.iloc[-1], 0),
        "total_ret_pct": round(100 * (bal.iloc[-1] / bt.START_CAPITAL - 1),
                               1),
        "cagr_pct": round(100 * ((bal.iloc[-1] / bt.START_CAPITAL)
                                 ** (52 / len(bal)) - 1), 1),
        "max_dd_pct": round(100 * dd.min(), 1),
        "ann_vol_pct": round(100 * ret.std() * 52 ** 0.5, 1),
        "worst_wk_pct": round(100 * ret.min(), 1),
        "call_premium": round(prem.sum(), 0),
        "put_prem_spent": round(put_costs, 0),
        "put_realized": round(pd.to_numeric(df["put_realized_pnl"],
                                            errors="coerce").sum(), 0),
        "rolls": int(df["put_action"].astype(str)
                     .str.contains("ROLLED|HARVESTED").sum()),
        "exits": int(df["put_action"].astype(str)
                     .str.contains("PROTECTIVE_EXIT").sum()),
        "income_weeks": int((prem > 0).sum()),
        "loss_weeks": int((pd.to_numeric(df["realized_gain_total"]) < 0)
                          .sum()),
    }


def part1(mkt):
    emit("=" * 78)
    emit("PART 1 -- PUT-MANAGEMENT POLICY BACKTESTS (all real quotes)")
    emit("=" * 78)
    results = []
    frames = {}
    for name, overrides in POLICIES.items():
        for k, v in {**DEFAULTS, **overrides}.items():
            setattr(bt, k, v)
        buf = io.StringIO()
        with redirect_stdout(buf):          # silence per-run noise
            df, warnings = bt.run(mkt)
        frames[name] = df
        m = metrics(df, name)
        m["warnings"] = len(warnings)
        results.append(m)
        emit(f"  {name:<15} end={m['end_total']:>10,.0f}  "
             f"ret={m['total_ret_pct']:>7.1f}%  maxDD={m['max_dd_pct']:>6.1f}%  "
             f"vol={m['ann_vol_pct']:>5.1f}%  rolls={m['rolls']:>2}  "
             f"exits={m['exits']:>2}")
    for k, v in DEFAULTS.items():           # restore module defaults
        setattr(bt, k, v)
    res = pd.DataFrame(results)
    res.to_csv(OUT_CSV, index=False)
    emit()
    emit(res.to_string(index=False))
    return res, frames


def part2():
    emit()
    emit("=" * 78)
    emit("PART 2 -- EXERCISE vs SELL (every ITM put row in the data)")
    emit("=" * 78)
    f = load_raw_options()
    itm = f[(f["right"] == "PUT")
            & (f["strike"] > f["underlying_price"])].copy()
    itm["intrinsic"] = itm["strike"] - itm["underlying_price"]
    itm["tv_at_bid"] = itm["bid"] - itm["intrinsic"]
    itm["depth"] = itm["intrinsic"] / itm["underlying_price"]
    emit(f"ITM put rows: {len(itm):,}")
    b = pd.cut(itm["depth"], [0, .05, .15, .30, .60, 10],
               labels=["0-5% ITM", "5-15%", "15-30%", "30-60%", ">60%"])
    g = itm.groupby(b, observed=True).agg(
        rows=("tv_at_bid", "size"),
        median_tv=("tv_at_bid", "median"),
        pct_bid_below_intrinsic=("tv_at_bid",
                                 lambda s: 100 * (s < 0).mean()))
    emit(g.round(3).to_string())
    emit()
    emit("Reading: tv_at_bid = what SELLING at the bid pays ABOVE exercise")
    emit("value. Positive median => selling captures time value that")
    emit("exercising burns. 'pct_bid_below_intrinsic' = share of rows where")
    emit("the bid is under intrinsic -- the only case where exercising (or")
    emit("selling shares via exercise) beats selling the put outright.")


def part3(frames):
    emit()
    emit("=" * 78)
    emit("PART 3 -- PUT SPREAD PRICING AT THE BASELINE'S PURCHASE DATES")
    emit("=" * 78)
    f = load_raw_options()
    df = frames["baseline"]
    buys = df[df["put_action"].astype(str).str.contains("BUY")]
    rows = []
    for r in buys.itertuples():
        d = pd.Timestamp(r.week_start).date()
        k_long = float(r.put_strike)
        exp = pd.Timestamp(r.put_expiration).date()
        px_long = float(r.put_open_price)
        ch = f[(f["trade_date"] == d) & (f["right"] == "PUT")
               & (f["expiration"] == exp) & (f["bid"] > 0)]
        row = {"date": d, "K_long": k_long, "exp": exp,
               "long_cost_ps": px_long}
        for frac in (0.75, 0.65):
            tgt = k_long * frac
            if ch.empty:
                continue
            s = ch.iloc[(ch["strike"] - tgt).abs().argsort()].iloc[0]
            credit = s["bid"] + bt.SPREAD_EXECUTION * (s["ask"] - s["bid"])
            row[f"K_short_{int(frac*100)}"] = s["strike"]
            row[f"credit_{int(frac*100)}"] = round(credit, 2)
            row[f"net_cost_reduction_{int(frac*100)}_pct"] = round(
                100 * credit / px_long, 1)
        rows.append(row)
    t = pd.DataFrame(rows)
    emit(t.to_string(index=False))
    emit()
    emit("Reading: selling the 75%-strike put against the long put would")
    emit("have recovered the 'net_cost_reduction' share of its cost, in")
    emit("exchange for giving up protection below that short strike (a")
    emit("crash through it leaves the shares unhedged below).")


def main():
    print("Loading market data once for all runs...")
    mkt = bt.Market()
    res, frames = part1(mkt)
    part2()
    part3(frames)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(_lines) + "\n")
    print(f"\nReport written to {REPORT.relative_to(ROOT)} and "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
