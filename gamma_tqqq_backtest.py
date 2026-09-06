#!/usr/bin/env python3
"""
R5c -- the gamma trade on TQQQ: an out-of-sample instrument test
================================================================

R5 (gamma_scalp_backtest.py) and R5b (gamma_ladder_backtest.py) found a
delta-hedged long-gamma edge on SOXL. Every honest limitation listed in
harvest_blueprint/GAMMA.md reduced to the same one: it is ONE INSTRUMENT over
ONE 2.5-year path. Staggered ladders could not fix that, because overlapping
rungs are not independent draws.

A second instrument can. TQQQ's option chains cover exactly the same window
(2024-01-02 -> 2026-07-02) with an identical schema, so the same engines run
on it with NO code changes -- this file only supplies data.

THE PREDICTION, STATED BEFORE THE RUN (vol_anatomy/harvestability.py):

    TQQQ's variance risk premium is negative at the same tenors and by
    almost the same margin as SOXL's -- 30d: -9.9 pts vs SOXL's -10.3;
    90d: -15.7 vs -15.9. The premium is nearly instrument-independent while
    the VOL LEVEL is not (TQQQ ~56% vs SOXL ~93% ATM).

    Gamma P&L ~ (1/2) Gamma S^2 (rv^2 - iv^2), and rv^2 - iv^2 factors as
    (rv - iv)(rv + iv). The first factor is about equal across the two; the
    second is roughly half on TQQQ.

    => TQQQ should be POSITIVE but materially SMALLER per dollar of premium.

That is a falsifiable prediction, not a description. If TQQQ comes back
negative, the SOXL result is much more likely to be a 2.5-year artifact than
a property of negative-VRP leveraged ETFs.

QA: `load_chains` below is a generic re-implementation of
volatility_pricing_lab.load_options. `verify_loader()` runs it against the
SOXL files and asserts it reproduces that function's output exactly, so TQQQ
is provably normalized by the same rules as SOXL rather than by lookalike code.

Only the DAILY hedge schedule is run. There are no intraday TQQQ bars in this
repository, and daily is both the winning schedule on SOXL and the one that
uses the real EOD delta column with no model at all.

Outputs:
    gamma_tqqq_grid.csv        scalp + ladder grid, TQQQ
    gamma_tqqq_strands.csv     12 staggered entry timings
    qa/gamma_tqqq_report.txt
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

import gamma_scalp_backtest as gs
import gamma_ladder_backtest as gl
from volatility_pricing_lab import load_options as load_soxl_options

ROOT = Path(__file__).resolve().parent
QA_DIR = ROOT / "qa"

USECOLS = ["expiration", "strike", "right", "bid", "ask", "implied_vol",
           "trade_date", "underlying_price", "delta", "volume"]


def load_chains(files):
    """Generic form of volatility_pricing_lab.load_options -- same columns,
    same date handling, same duplicate rule, same derived fields."""
    frames = []
    for p in files:
        p = Path(p)
        if not p.exists() or p.stat().st_size < 1000:
            raise FileNotFoundError(f"{p} missing -- run 'git lfs pull'")
        df = pd.read_csv(p, low_memory=False, usecols=USECOLS)
        for c in ("trade_date", "expiration"):
            fmt = "%m/%d/%y" if "/" in str(df[c].iloc[0]) else "%Y-%m-%d"
            df[c] = pd.to_datetime(df[c], format=fmt)
        frames.append(df)
    f = pd.concat(frames, ignore_index=True)
    f = f.drop_duplicates(["trade_date", "expiration", "strike", "right"],
                          keep="first")
    f["dte"] = (f["expiration"] - f["trade_date"]).dt.days
    f["mid"] = (f["bid"] + f["ask"]) / 2
    f["spread"] = f["ask"] - f["bid"]
    f["liquid"] = (f["bid"] > 0) & (f["ask"] >= f["bid"])
    f["sell_px"] = f["bid"] + 0.20 * f["spread"]
    f["buy_px"] = f["ask"] - 0.20 * f["spread"]
    f["mness"] = f["strike"] / f["underlying_price"]
    return f


def verify_loader():
    """The generic loader must reproduce load_options() on SOXL exactly."""
    mine = load_chains([ROOT / n for n in ("SOXL_Options_2024.csv",
                                           "SOXL_Options_2025.csv",
                                           "SOXL_Options_2026.csv")])
    theirs = load_soxl_options()
    ok = (len(mine) == len(theirs)
          and set(mine.columns) == set(theirs.columns))
    if ok:
        a = mine.sort_values(["trade_date", "expiration", "strike", "right"]
                             ).reset_index(drop=True)
        b = theirs.sort_values(["trade_date", "expiration", "strike", "right"]
                               ).reset_index(drop=True)
        num = [c for c in a.columns
               if pd.api.types.is_numeric_dtype(a[c])
               and not pd.api.types.is_bool_dtype(a[c])]
        boolc = [c for c in a.columns if pd.api.types.is_bool_dtype(a[c])]
        ok = bool(np.allclose(a[num].astype(float).fillna(-9e9),
                              b[num].astype(float).fillna(-9e9)))
        ok = ok and all(a[c].equals(b[c]) for c in boolc)
    return ok, len(mine), len(theirs)


def load_daily_bars(path):
    """EOD bars shaped the way the engines expect (they need `dt` + `Close`)."""
    b = pd.read_csv(path)
    b["dt"] = pd.to_datetime(b["Date"])
    b["date"] = b["dt"].dt.normalize()
    return b[["dt", "date", "Open", "High", "Low", "Close", "Volume"]]


def spot_bars_from_chain(opt):
    """Spot series taken from the chain's OWN underlying_price.

    This is not a stylistic choice. TQQQ_IBKR_3YR_EOD.csv is split- and
    dividend-ADJUSTED while the chain's underlying_price and its strikes are
    RAW traded levels: the two disagree by a factor of 2.0533 before
    2025-11-20 and 1.0000 after it. Hedging on the adjusted series while
    settling against raw strikes picks a $48 strike and settles it at $23,
    which fabricates an enormous fake profit. The chain's own spot is
    consistent with its strikes by construction, so it is the only safe
    source. (SOXL is unaffected -- its two sources agree to 1.0001.)
    """
    u = opt.groupby("trade_date")["underlying_price"].first().sort_index()
    b = pd.DataFrame({"dt": u.index, "Close": u.to_numpy()})
    b["date"] = b["dt"].dt.normalize()
    b["Open"] = b["High"] = b["Low"] = b["Close"]
    b["Volume"] = 0
    return b[["dt", "date", "Open", "High", "Low", "Close", "Volume"]]


def find_splits(opt, adj_bars, thresh=0.05):
    """Days where chain_spot / adjusted_close steps -- i.e. a share split.

    Comparing the two sources is what separates a split from a real move:
    2025-04-09's +30% appears in BOTH series (real), while 2025-11-20's -77%
    appears only in the raw one (a 2:1 split).
    """
    u = opt.groupby("trade_date")["underlying_price"].first()
    b = adj_bars.set_index("date")["Close"]
    j = pd.concat([u.rename("c"), b.rename("b")], axis=1, sort=True).dropna()
    ratio = j.c / j.b
    return list(ratio.index[ratio.diff().abs() > thresh])


def run_all(opt, bars, tag):
    rows = []
    base = gs.Config(hedge="daily")
    cfgs = [base]
    for t, lo, hi in [(30, 21, 45), (90, 60, 120)]:
        cfgs.append(replace(base, dte=t, dte_lo=lo, dte_hi=hi))
    for s in ("call", "put"):
        cfgs.append(replace(base, structure=s))
    cfgs.append(replace(base, costs=False))
    for cfg in cfgs:
        bt = gs.GammaScalp(opt, bars, cfg)
        cyc = bt.run()
        if cyc.empty:
            continue
        s = gs.summarize(bt, cyc)
        s["engine"], s["symbol"] = "scalp", tag
        rows.append(s)
    lbase = gl.Config()
    for lcfg in (lbase, replace(lbase, step=5), replace(lbase, step=20),
                 replace(lbase, dte=90, dte_lo=60, dte_hi=120)):
        bt = gl.GammaLadder(opt, bars, lcfg)
        eq = bt.run()
        s = gl.summarize(bt, eq)
        s["engine"], s["symbol"] = "ladder", tag
        rows.append(s)
    return rows


def strand_sweep(opt, bars, tag, offsets=range(0, 48, 4)):
    out = []
    for off in offsets:
        bt = gs.GammaScalp(opt, bars, gs.Config(hedge="daily",
                                                start_offset=off))
        c = bt.run()
        if c.empty:
            continue
        out.append(dict(symbol=tag, offset=off, cycles=len(c),
                        pnl=round(c.total_pnl.sum(), 0),
                        pct_prem=round(c.pnl_pct_prem.mean(), 2),
                        win=round(100 * (c.total_pnl > 0).mean(), 1),
                        first=c.entry.iloc[0]))
    return out


def main():
    ok, n_mine, n_theirs = verify_loader()
    print(f"loader verification vs load_options() on SOXL: "
          f"{'PASS' if ok else 'FAIL'}  ({n_mine:,} vs {n_theirs:,} rows)")
    if not ok:
        raise SystemExit("generic loader does not reproduce load_options()")

    topt = load_chains([ROOT / "raw_data" / f"TQQQ_Options_{y}.csv"
                        for y in (2024, 2025, 2026)])
    tadj = load_daily_bars(ROOT / "TQQQ_IBKR_3YR_EOD.csv")
    splits = find_splits(topt, tadj)
    print(f"TQQQ: {len(topt):,} option rows, {topt.trade_date.nunique()} dates "
          f"{topt.trade_date.min().date()} -> {topt.trade_date.max().date()}")
    print(f"      share splits detected: "
          f"{[str(d.date()) for d in splits] or 'none'}")

    # Run either side of the split. No cycle may span it, because option
    # contracts are themselves adjusted at a split and the engine does not
    # model that; filtering the chain enforces it without touching the engine.
    rows, strands = [], []
    cut = splits[-1] if splits else None
    segments = []
    if cut is not None:
        pre = topt[(topt.trade_date < cut) & (topt.expiration < cut)]
        post = topt[(topt.trade_date > cut) & (topt.expiration > cut)]
        segments = [("TQQQ_pre", pre), ("TQQQ_post", post)]
    else:
        segments = [("TQQQ", topt)]
    for tag, seg in segments:
        if seg.empty or seg.trade_date.nunique() < 80:
            print(f"      {tag}: {seg.trade_date.nunique()} dates -- too short, "
                  f"skipped")
            continue
        sb = spot_bars_from_chain(seg)
        print(f"      {tag}: {seg.trade_date.nunique()} dates "
              f"{seg.trade_date.min().date()} -> {seg.trade_date.max().date()}, "
              f"spot {sb.Close.iloc[0]:.2f} -> {sb.Close.iloc[-1]:.2f}")
        rows += run_all(seg, sb, tag)
        strands += strand_sweep(seg, sb, tag)

    # SOXL side by side, daily schedule only, same window
    soxl_opt = load_soxl_options()
    from volatility_pricing_lab import load_bars as load_soxl_bars
    srows = run_all(soxl_opt, load_soxl_bars(), "SOXL")
    sstr = strand_sweep(soxl_opt, load_soxl_bars(), "SOXL")

    g = pd.DataFrame(rows + srows)
    st = pd.DataFrame(strands + sstr)
    g.to_csv(ROOT / "gamma_tqqq_grid.csv", index=False)
    st.to_csv(ROOT / "gamma_tqqq_strands.csv", index=False)

    pd.set_option("display.width", 250)
    sc = g[g.engine == "scalp"][["symbol", "config", "cycles", "total_pnl",
                                 "mean_pct_prem", "t_stat", "pnl_ex_best",
                                 "win_rate_pct", "mean_entry_iv",
                                 "mean_realized_vol", "qa_recon"]]
    ld = g[g.engine == "ladder"][["symbol", "config", "rungs", "pnl",
                                  "cagr_pct", "max_dd_pct", "sharpe",
                                  "ann_vol_pct", "beta_to_underlying",
                                  "mean_prem_at_risk", "qa_recon"]]
    print("\n--- SCALP (daily hedge, real EOD deltas) ---")
    print(sc.to_string(index=False))
    print("\n--- LADDER ---")
    print(ld.to_string(index=False))
    print("\n--- STRANDS (entry-timing robustness) ---")
    for sym in sorted(st.symbol.unique()):
        d = st[st.symbol == sym]
        if d.empty:
            continue
        print(f"  {sym}: {len(d)} strands, positive {int((d.pnl>0).sum())}/{len(d)}, "
              f"pnl {d.pnl.min():+,.0f} .. {d.pnl.max():+,.0f}, "
              f"mean %prem {d.pct_prem.mean():+.2f}")

    QA_DIR.mkdir(exist_ok=True)
    fails = int((g["qa_recon"] != "PASS").sum())
    with open(QA_DIR / "gamma_tqqq_report.txt", "w") as f:
        f.write("R5c GAMMA ON TQQQ -- OUT-OF-SAMPLE INSTRUMENT TEST\n")
        f.write(f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}\n")
        f.write("Same engines as R5/R5b, unchanged; this file supplies data only.\n")
        f.write(f"Generic loader reproduces load_options() on SOXL: "
                f"{'PASS' if ok else 'FAIL'}\n")
        f.write("Daily hedge only -- no intraday TQQQ bars exist here, and daily\n")
        f.write("is the schedule that uses the real EOD delta with no model.\n\n")
        f.write("--- SCALP ---\n")
        f.write(sc.to_string(index=False))
        f.write("\n\n--- LADDER ---\n")
        f.write(ld.to_string(index=False))
        f.write("\n\n--- STRANDS ---\n")
        f.write(st.to_string(index=False))
        f.write(f"\n\nQA reconciliation failures: {fails} of {len(g)}\n")
    print(f"\nwrote gamma_tqqq_grid.csv, gamma_tqqq_strands.csv, "
          f"qa/gamma_tqqq_report.txt  (QA fails: {fails}/{len(g)})")


if __name__ == "__main__":
    main()
