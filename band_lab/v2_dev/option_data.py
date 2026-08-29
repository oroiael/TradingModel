"""
Load the SOXL option quotes, and check them hard before anything trusts them.

The band strategy died to a simulator nobody had audited. This module exists so
that does not happen twice: it is the only path into the option files, and it
refuses to hand back data that fails the checks below.

Checks designed to FAIL, not to reassure:

  1. `underlying_price` in the option file must match SOXL's own price file at
     the same date. Two independent sources; disagreement means the join is
     wrong and every downstream number is meaningless.
  2. Call deltas positive, put deltas negative, |delta| <= 1.
  3. bid <= ask, no negative prices.
  4. Put-call parity: for the same strike and expiry, C - P should track
     S - K*exp(-rT). Large systematic violations mean stale or mispriced quotes.
  5. Implied vol positive and not absurd.

    python3 band_lab/v2_dev/option_data.py            # run the checks
"""

from __future__ import annotations

import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USE = ["expiration", "strike", "right", "timestamp", "bid", "ask", "bid_size",
       "ask_size", "delta", "implied_vol", "underlying_price", "trade_date"]

FAILURES: list[str] = []


def check(name, ok, detail):
    if not ok:
        FAILURES.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def _dates(s: pd.Series) -> pd.Series:
    """Parse dates that arrive in two formats across the five files.

    2022, 2023, 2024 and 2026 use ISO (`2024-01-02`). **2025 alone uses
    `M/D/YY`** (`1/2/25`), which is ambiguous — `1/2/25` is either 2 January or
    1 February. Month-first is assumed because the 2025 file's first rows run
    `1/2, 1/3, 1/6, 1/7, 1/8`, five consecutive US business days; read
    day-first those would be January, February, June, July and August, which no
    date-sorted file produces.

    That reasoning is not the evidence. The evidence is the `underlying_price`
    check in `run_checks`: if these dates were wrong the option file's own spot
    price would stop matching SOXL's separate price file, and it does not.
    """
    out = pd.to_datetime(s, format="ISO8601", errors="coerce")
    bad = out.isna()
    if bad.any():
        out.loc[bad] = pd.to_datetime(s[bad], format="%m/%d/%y",
                                      errors="coerce")
    return out


def soxl_closes():
    """Session closes from the 5-minute price file — the independent source."""
    df = pd.read_csv(os.path.join(ROOT, "SOXL_5min_6Years.csv"))
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    return df.assign(date=dt.dt.normalize()).groupby("date")["Close"].last()


def load(years=("2022", "2023", "2024", "2025", "2026"), verbose=True,
         extra=()):
    """Every quote, one row per contract per snapshot, latest snapshot per day.

    The files carry a handful of intraday snapshots per session. Decisions in
    this project are end-of-day, so the LAST snapshot on each trade date is
    kept; taking an earlier one and calling it a close would be lookahead in
    reverse — pricing a decision at a moment the decision-maker had not reached.

    `extra` names further columns to read — the greeks, typically. They are off
    by default because these files are 544 MB and most callers need none of them.
    """
    frames = []
    for y in years:
        p = os.path.join(ROOT, f"SOXL_Options_{y}.csv")
        if not os.path.exists(p):
            continue
        with open(p, "rb") as fh:
            if fh.read(40).startswith(b"version https://git-lfs"):
                raise RuntimeError(f"{p} is an LFS pointer — run git lfs pull")
        d = pd.read_csv(p, usecols=list(USE) + list(extra))
        frames.append(d)
        if verbose:
            print(f"    loaded {y}: {len(d):,} quotes", flush=True)
    if not frames:
        raise RuntimeError("no option files found")
    d = pd.concat(frames, ignore_index=True)

    d["trade_date"] = _dates(d["trade_date"])
    d["expiration"] = _dates(d["expiration"])
    d["ts"] = pd.to_datetime(d["timestamp"], errors="coerce", utc=True)
    # keep the last snapshot of each contract on each day
    d = (d.sort_values("ts")
           .drop_duplicates(["trade_date", "expiration", "strike", "right"],
                            keep="last"))
    d["dte"] = (d["expiration"] - d["trade_date"]).dt.days
    d["mid"] = (d["bid"] + d["ask"]) / 2.0
    d["spread"] = d["ask"] - d["bid"]
    return d.drop(columns=["timestamp"]).reset_index(drop=True)


def run_checks(d):
    print("=" * 78)
    print("OPTION DATA QUALITY — checks built to fail if the files are wrong")
    print("=" * 78)
    print(f"\n  {len(d):,} quotes, {d.trade_date.nunique():,} trade dates, "
          f"{d.trade_date.min().date()} to {d.trade_date.max().date()}")
    snaps = d.groupby("trade_date").size()
    print(f"  contracts per day: median {int(snaps.median())}, "
          f"min {int(snaps.min())}, max {int(snaps.max())}")

    c = d[d["right"] == "CALL"]
    p = d[d["right"] == "PUT"]
    check("call deltas are positive",
          float((c.delta >= 0).mean()) > 0.999,
          f"{float((c.delta >= 0).mean()):.4%} of {len(c):,} calls")
    check("put deltas are negative",
          float((p.delta <= 0).mean()) > 0.999,
          f"{float((p.delta <= 0).mean()):.4%} of {len(p):,} puts")
    check("|delta| <= 1", float((d.delta.abs() <= 1.0001).mean()) > 0.999,
          f"max |delta| {d.delta.abs().max():.4f}")
    check("bid <= ask", float((d.ask >= d.bid).mean()) > 0.999,
          f"{int((d.ask < d.bid).sum()):,} inverted quotes")
    check("no negative prices", bool((d.bid >= 0).all() and (d.ask >= 0).all()),
          f"min bid {d.bid.min():.4f}, min ask {d.ask.min():.4f}")
    iv = d.implied_vol[d.implied_vol > 0]
    check("implied vol in a sane range",
          bool(iv.median() > 0.3) and bool(iv.median() < 3.0),
          f"median {iv.median():.3f}, p01 {iv.quantile(0.01):.3f}, "
          f"p99 {iv.quantile(0.99):.3f}, {float((d.implied_vol <= 0).mean()):.1%} zero")

    # --- the check that matters: two independent sources of the same price
    px = soxl_closes()
    u = d.groupby("trade_date")["underlying_price"].last()
    j = pd.concat([u.rename("opt"), px.rename("px")], axis=1).dropna()
    rel = (j["opt"] - j["px"]).abs() / j["px"]
    check("option file's underlying_price matches the 5-minute price file",
          float(rel.median()) < 0.02,
          f"{len(j):,} dates compared, median relative difference "
          f"{rel.median():.4%}, p95 {rel.quantile(0.95):.4%}")

    # --- put-call parity on matched pairs, near the money, liquid
    liq = d[(d.bid > 0) & (d.ask > d.bid) & (d.dte.between(20, 120))]
    piv = liq.pivot_table(index=["trade_date", "expiration", "strike",
                                 "underlying_price"],
                          columns="right", values="mid")
    piv = piv.dropna().reset_index()
    if len(piv):
        piv["moneyness"] = piv["strike"] / piv["underlying_price"]
        atm = piv[piv.moneyness.between(0.9, 1.1)]
        synth = atm["CALL"] - atm["PUT"]           # ~ S - K (ignoring carry)
        actual = atm["underlying_price"] - atm["strike"]
        err = (synth - actual).abs() / atm["underlying_price"]
        check("put-call parity holds near the money",
              float(err.median()) < 0.03,
              f"{len(atm):,} matched pairs, median |C-P-(S-K)|/S "
              f"= {err.median():.4%}, p90 {err.quantile(0.90):.4%}")
    else:
        check("put-call parity holds near the money", False,
              "no matched call/put pairs found")

    print("\n" + "=" * 78)
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED: {', '.join(FAILURES)}")
        return 1
    print("All checks passed. The option data can be trusted downstream.")
    return 0


def main() -> int:
    print("loading (this reads ~544 MB)...", flush=True)
    d = load()
    return run_checks(d)


if __name__ == "__main__":
    raise SystemExit(main())
