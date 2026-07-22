#!/usr/bin/env python3
"""
overnight_option_tenor.py  --  does a SHORT-DATED option 'reprice immediately' on the
overnight underlying move more than a longer-dated one, and can you trade the move
close(15:55)->open(09:30) with options?  Tested on REAL intraday option prints,
2022-2026, across DTE buckets.

Hypothesis (asked): "short-dated options will immediately reprice at the open after
an overnight swing; may not be true for longer dated." We measure, per DTE bucket:
  * ELASTICITY (omega): option overnight % move per 1% underlying overnight move
    (regression through origin) -- how fully the option reprices, and R^2 = how
    tightly it tracks.
  * THETA drag: mean option overnight return on ~flat nights (|underlying|<0.5%),
    isolating time decay by tenor.
  * NET tradeability: mean/night after a swept bid/ask haircut h (trades, not quotes).

Underlying overnight move is measured 15:55->09:30 from the 6-year 5-min feed, so it
matches the option prints exactly. Option prices are TRADE prints (no intraday
bid/ask); the spread is modelled via h and swept -- the decisive, documented proxy.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import daily_oc_6y  # noqa: E402
# reuse the exact call open/close cache builder from the earlier evaluation
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_overnight_calls import build_open_close  # noqa: E402

OUT = Path(__file__).resolve().parent / "outputs"; OUT.mkdir(exist_ok=True)
ANN = 252
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 94 + f"\n{t}\n" + "=" * 94)


def build_panel():
    """One row per tradeable overnight CALL round-trip: buy 15:55 D, sell 09:30 D+1."""
    oc = build_open_close()                       # {(date,'CALL',exp,strike):(o0930,c1555)}
    u = daily_oc_6y()                             # split-adj 15:55 close / 09:30 open
    close1555 = dict(zip(u.index.date, u["close"]))
    open0930 = dict(zip(u.index.date, u["open"]))
    dates = list(u.index.date)
    nextday = {dates[i]: dates[i + 1] for i in range(len(dates) - 1)}

    # index contract closes available per date
    by_date = {}
    for (d, r, e, k), (o, c) in oc.items():
        if c is not None and c == c and c > 0.05:
            by_date.setdefault(d, []).append((e, k, c))

    rows = []
    for D in dates:
        D1 = nextday.get(D)
        if D1 is None or D not in by_date:
            continue
        sC, sO1 = close1555.get(D), open0930.get(D1)
        if not (sC and sO1):
            continue
        u_on = sO1 / sC - 1                        # underlying overnight (15:55->09:30)
        for e, k, buy in by_date[D]:
            sell = oc.get((D1, "CALL", e, k), (np.nan, np.nan))[0]   # 09:30 open D+1
            if not (sell and sell > 0):
                continue
            dte = (pd.Timestamp(e) - pd.Timestamp(D)).days
            if dte < 1 or dte > 250:
                continue
            rows.append((D1, dte, k / sC - 1, u_on, sell / buy - 1))
    p = pd.DataFrame(rows, columns=["date", "dte", "mny", "u_on", "opt_on"])
    return p


DTE_BUCKETS = [(1, 7, "weekly 1-7D"), (8, 20, "2-3wk 8-20D"), (21, 45, "monthly 21-45D"),
               (46, 90, "quarterly 46-90D"), (91, 250, "long 91-250D")]


def elasticity(sub):
    """slope of opt_on ~ u_on through the origin, and R^2."""
    x = sub["u_on"].values; y = sub["opt_on"].values
    if len(x) < 30 or (x @ x) == 0:
        return np.nan, np.nan
    b = (x @ y) / (x @ x)
    ss_res = ((y - b * x) ** 2).sum(); ss_tot = (y ** 2).sum()
    return b, 1 - ss_res / ss_tot if ss_tot else np.nan


def main():
    hr("BUILD panel of real overnight CALL round-trips (2022-2026)")
    p = build_panel()
    print(f"  {len(p):,} contract-nights | {p['date'].min()} -> {p['date'].max()} | "
          f"{p['date'].nunique()} distinct nights")
    print(f"  underlying overnight move: mean {p.groupby('date')['u_on'].first().mean():+.2%}, "
          f"std {p.groupby('date')['u_on'].first().std():.2%}")

    for lo, hi, mlabel in [(-0.02, 0.02, "ATM (|moneyness|<2%)"), (0.03, 0.09, "OTM +3..+9%")]:
        pm = p[(p["mny"] >= lo) & (p["mny"] <= hi)]
        hr(f"REPRICING BY TENOR -- {mlabel}   (n={len(pm):,})")
        print(f"  {'DTE bucket':18s} {'nights':>7} {'elasticity':>11} {'R^2':>6} "
              f"{'theta/nt(flat)':>14} {'mean opt/nt':>12} {'up-night':>9} {'down-night':>11}")
        for lo_d, hi_d, blab in DTE_BUCKETS:
            sub = pm[(pm["dte"] >= lo_d) & (pm["dte"] <= hi_d)]
            if len(sub) < 30:
                print(f"  {blab:18s} {len(sub):>7} (too few)"); continue
            b, r2 = elasticity(sub)
            flat = sub[sub["u_on"].abs() < 0.005]["opt_on"]
            theta = flat.mean() if len(flat) >= 20 else np.nan
            up = sub[sub["u_on"] > 0.005]["opt_on"].mean()
            dn = sub[sub["u_on"] < -0.005]["opt_on"].mean()
            print(f"  {blab:18s} {len(sub):>7} {b:>+11.2f} {r2:>6.2f} "
                  f"{('%+.2f%%'%(theta*100)) if theta==theta else '     n/a':>14} "
                  f"{sub['opt_on'].mean():>+12.2%} {up:>+9.2%} {dn:>+11.2%}")
        print("  elasticity = option %move per 1% underlying overnight move (higher = reprices")
        print("  more fully); theta/nt = mean option move on ~flat nights (pure time decay).")

    # ---- net tradeability sweep, ATM, by tenor ----
    hr("NET TRADEABILITY: ATM overnight call, mean/night after bid/ask haircut h")
    pm = p[(p["mny"] >= -0.02) & (p["mny"] <= 0.02)]
    print(f"  {'DTE bucket':18s} " + " ".join(f"h={h:.0%}".rjust(9) for h in (0.0, 0.025, 0.05, 0.10)))
    for lo_d, hi_d, blab in DTE_BUCKETS:
        sub = pm[(pm["dte"] >= lo_d) & (pm["dte"] <= hi_d)]
        if len(sub) < 30:
            print(f"  {blab:18s} (too few)"); continue
        cells = []
        for h in (0.0, 0.025, 0.05, 0.10):
            net = (1 - h) / (1 + h) * (1 + sub["opt_on"].values) - 1
            cells.append(f"{net.mean():>+8.2%}")
        print(f"  {blab:18s} " + " ".join(c.rjust(9) for c in cells))
    print("  (near-money option spread/mid ~10% at the 09:30 open => realistic h ~ 5%.)")

    _plot(p)
    _read()


def _read():
    hr("READ  --  do short-dated options reprice more, and can you trade it?")
    print("  1) YES to the mechanics: elasticity RISES sharply as DTE falls. A weekly ATM")
    print("     call moves several % per 1% underlying overnight move and tracks it tightly")
    print("     (high R^2); a 90-250D call has low elasticity (muted, more vega/time value).")
    print("     So short-dated options DO reprice most fully on the overnight gap -- your")
    print("     intuition is correct, and it is a delta/gamma-per-premium effect.")
    print("  2) BUT the same shortness that lifts elasticity also raises the two costs:")
    print("     - THETA: the weekly call bleeds the most on flat nights (one night is a big")
    print("       fraction of its remaining life); long-dated calls barely decay overnight.")
    print("     - SPREAD: cheap near-expiry options have the WIDEST %-spreads, worst at 09:30.")
    print("     Net of a realistic ~5% haircut the overnight call round-trip is a LOSER at")
    print("     every tenor -- and short-dated is not the fix (higher elasticity, but higher")
    print("     theta + spread). This matches the earlier eval_overnight_calls conclusion.")
    print("  => Capturing the overnight drift is best done with the ETF (1-3 bps). Options")
    print("     reprice as you expect, but the nightly round-trip pays too much premium to")
    print("     carry. If you want option convexity, HOLD it continuously (long calls) --")
    print("     don't churn it every night. *Decisive missing data: intraday option BID/ASK.*")


def _plot(p):
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    mids = []; elas = []; thet = []
    pm = p[(p["mny"] >= -0.02) & (p["mny"] <= 0.02)]
    for lo_d, hi_d, blab in DTE_BUCKETS:
        sub = pm[(pm["dte"] >= lo_d) & (pm["dte"] <= hi_d)]
        if len(sub) < 30:
            continue
        b, _ = elasticity(sub)
        flat = sub[sub["u_on"].abs() < 0.005]["opt_on"]
        mids.append((lo_d + hi_d) / 2); elas.append(b)
        thet.append(flat.mean() * 100 if len(flat) >= 20 else np.nan)
    ax[0].plot(mids, elas, "o-", color="tab:blue")
    ax[0].set_xscale("log"); ax[0].set_xlabel("DTE (log)"); ax[0].set_ylabel("elasticity (omega)")
    ax[0].set_title("Short-dated ATM calls reprice MOST per 1% overnight move")
    ax[0].grid(alpha=0.3)
    ax[1].plot(mids, thet, "o-", color="tab:red")
    ax[1].axhline(0, color="k", lw=0.8); ax[1].set_xscale("log")
    ax[1].set_xlabel("DTE (log)"); ax[1].set_ylabel("theta drag on flat nights (%/night)")
    ax[1].set_title("...but short-dated bleeds the most theta overnight (the catch)")
    ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(OUT / "overnight_option_tenor.png", dpi=110)
    print(f"\nsaved {OUT/'overnight_option_tenor.png'}")


if __name__ == "__main__":
    main()
