#!/usr/bin/env python3
"""
run_real_harvest.py  --  continuous strangle harvest on REAL intraday option
prices, 2022-2026, now that the full 5-min option set is present.

Builds real_hi[(td,right,exp,strike)] = the option's OWN 5-min intraday HIGH that
day (from the 664 raw_data files, cached), and runs the harvest engine three ways
on the same config:
   EOD  : harvest only on the daily close
   BS   : Part-4 model (BS at the underlying 5-min extreme, prior-EOD IV)
   REAL : harvest on the option's real intraday high (exit high*(1-slip))
REAL is the ground truth; the comparison shows how much intraday harvesting adds
over EOD and whether BS matched REAL -- now across ALL regimes incl. 2022/2023/2026.
"""
from __future__ import annotations
import glob, pickle
from pathlib import Path
import numpy as np
import pandas as pd

from data_loader import load_options, load_5min
from verticals import build_index
from strangle_harvest import (HConfig, simulate, stats, compact_index,
                              build_hilo, build_iv_key)

OUT = Path(__file__).resolve().parent / "outputs"
SCRATCH = Path("/tmp/claude-0/-home-user-TradingModel/3ee6862d-4424-5812-9b50-ba533ce0c5cb/scratchpad")
CACHE = SCRATCH / "real_hi.pkl"
RAW = Path(__file__).resolve().parent.parent / "raw_data"
SLIP = 0.05
pd.set_option("display.width", 200)


def hr(t): print("\n" + "=" * 82 + f"\n{t}\n" + "=" * 82)


def build_real_hi():
    if CACHE.exists():
        print(f"loading cached real_hi from {CACHE}")
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    print("building real_hi from raw_data intraday files (file-by-file)...")
    files = [p for p in glob.glob(str(RAW / "SOXL_intraday_5m_exp_*.csv"))
             if Path(p).stat().st_size > 10_000]
    parts = []
    for i, p in enumerate(files):
        df = pd.read_csv(p, usecols=["expiration", "strike", "right", "timestamp",
                                     "high", "volume"])
        df = df[df["high"] > 0]
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(
            "America/New_York").dt.date
        df["right"] = df["right"].str.upper().str.strip()
        df["expiration"] = pd.to_datetime(df["expiration"]).dt.date
        g = df.groupby(["date", "right", "expiration", "strike"])["high"].max().reset_index()
        parts.append(g)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(files)} files")
    allg = pd.concat(parts, ignore_index=True)
    real_hi = {(r.date, r.right, r.expiration, float(r.strike)): float(r.high)
               for r in allg.itertuples(index=False)}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(real_hi, f)
    print(f"built {len(real_hi):,} (contract,day) real highs -> cached")
    return real_hi


def by_year(res):
    eq = pd.Series(res["equity"], index=pd.to_datetime(res["dates"]))
    yr = eq.groupby(eq.index.year).agg(["first", "last"])
    return (yr["last"] / yr["first"] - 1).round(3)


def hsplit(res):
    lg = res["log"]
    return {k: int((lg["action"] == k).sum()) for k in
            ("harvest_real", "harvest_intraday", "harvest")}


def main():
    hr("LOAD")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt)
    compact = compact_index(idx)
    fm = load_5min(); hilo = build_hilo(fm); ivk = build_iv_key(opt)
    real_hi = build_real_hi()
    rd = sorted({d for (d, *_r) in real_hi})
    print(f"real_hi covers {rd[0]} -> {rd[-1]}  ({len(real_hi):,} contract-days)")

    for dte in (60, 120):
        cfg = dict(dte_target=dte, dte_tol=(15 if dte < 90 else 20), dist=0.075,
                   take=0.50, leg_frac=0.15)
        hr(f"{dte} DTE strangle (7.5%, take +50%, leg_frac 15%)  --  EOD vs BS vs REAL")
        r_eod = simulate(idx, HConfig(**cfg), compact)
        r_bs = simulate(idx, HConfig(**cfg), compact, intraday=(hilo, ivk, SLIP))
        r_real = simulate(idx, HConfig(**cfg), compact, intraday=(None, None, SLIP),
                          real_hi=real_hi)
        for lbl, r in [("EOD (close only)", r_eod), ("BS (Part-4 model)", r_bs),
                       ("REAL (real intraday)", r_real)]:
            s = stats(r, HConfig(**cfg))
            print(f"  {lbl:22s}: end ${s['end_equity']:>12,.0f}  CAGR {s['cagr']:>+5.0%}  "
                  f"maxDD {s['max_dd']:>+5.0%}  harvests {hsplit(r)}")
        print("\n  by-year return (EOD / BS / REAL):")
        comp = pd.DataFrame({"EOD": by_year(r_eod), "BS": by_year(r_bs),
                             "REAL": by_year(r_real)})
        print(comp.to_string())
        if dte == 120:
            _plot(r_eod, r_bs, r_real, dte)

    hr("READ")
    print("REAL is the ground truth (option's own intraday high). Compare REAL vs EOD\n"
          "for the true value of intraday harvesting across ALL regimes, and REAL vs BS\n"
          "to see how faithful the Part-4 model was where the 5-min underlying existed.")


def _plot(r_eod, r_bs, r_real, dte):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for lbl, r, c in [("EOD (close only)", r_eod, "gray"),
                      ("BS model", r_bs, "tab:orange"),
                      ("REAL intraday", r_real, "tab:green")]:
        e = pd.Series(r["equity"], index=pd.to_datetime(r["dates"]))
        ax.plot(e.index, e.values, label=lbl, lw=1.4, color=c)
    ax.axhline(100_000, color="k", lw=0.6, ls="--")
    ax.set_yscale("log"); ax.set_ylabel("equity ($, log)")
    ax.set_title(f"{dte} DTE strangle harvest: real intraday vs BS vs EOD (2022-2026)")
    ax.legend()
    fig.tight_layout(); fig.savefig(OUT / "real_harvest_curves.png", dpi=110)


if __name__ == "__main__":
    main()
