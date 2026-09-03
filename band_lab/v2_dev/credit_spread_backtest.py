"""
Defined-risk credit spreads on SOXL. The bar is V55_CREDIT_SPREAD_BAR.md.

V54 measured naked short vol and it lost on every gate: median credit 21.0% of
spot against a median cost of 22.2%, and six cycles in 680 losing more than the
notional the position controlled. Defining the risk truncates that tail and
shrinks the credit at the same time, which is why it needs measuring rather
than screening.

Structures
----------
  put_cs     sell the 25-delta put,  buy the 10-delta put
  call_cs    sell the 25-delta call, buy the 10-delta call
  condor     both at once

The width is set by delta rather than dollars, because a $5 wing means something
different when the underlying is $9 than when it is $164, and this file spans
both.

Every leg crosses its spread
-----------------------------
Shorts are SOLD at the bid and BOUGHT BACK at the ask; longs are BOUGHT at the
ask and SOLD at the bid. A condor therefore crosses four spreads to open and
four to close, and pays eight commissions a round trip. Holding to expiry
settles at intrinsic and pays no closing spread, which is a real property of
that exit rather than an accounting convenience.

`--fill k` varies that convention -- k = 1.0 is the touch and the default, so
the published result is unchanged; see V58_OPTION_FILL_LADDER.md. Four legs
makes this the structure most sensitive to it, and the one that clears the bar
at no rung at all, the impossible one included.

Return is P&L over max loss -- the capital a defined-risk spread commits, and
directly comparable to buy-and-hold on the share price.

    python3 band_lab/v2_dev/credit_spread_backtest.py
    python3 band_lab/v2_dev/credit_spread_backtest.py --fill 0.0
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from short_vol_backtest import (COMMISSION, TENORS, buy_px, load_chain,  # noqa: E402
                                sell_px, underlying_daily)

EXITS = ("expiry", "tp50", "roll21")
SHORT_DELTA, LONG_DELTA = 0.25, 0.10


def nearest_delta(df, target):
    if df.empty:
        return None
    return df.iloc[[(df.delta.abs() - target).abs().argmin()]].iloc[0]


def build(day, structure):
    """Legs as (row, qty). qty −1 is short, +1 is long."""
    c = day[day.right == "C"]
    p = day[day.right == "P"]
    legs = []
    if structure in ("put_cs", "condor"):
        s, l = nearest_delta(p, SHORT_DELTA), nearest_delta(p, LONG_DELTA)
        if s is None or l is None or s.strike <= l.strike:
            return None            # a put credit spread needs K_short > K_long
        legs += [(s, -1), (l, +1)]
    if structure in ("call_cs", "condor"):
        s, l = nearest_delta(c, SHORT_DELTA), nearest_delta(c, LONG_DELTA)
        if s is None or l is None or s.strike >= l.strike:
            return None            # a call credit spread needs K_short < K_long
        legs += [(s, -1), (l, +1)]
    return legs or None


def open_credit(legs, fill=1.0):
    """Sell the shorts, buy the longs. At fill=1.0 that is bid and ask."""
    return sum((-q) * (sell_px(r.bid, r.ask, fill) if q < 0
                       else buy_px(r.bid, r.ask, fill)) for r, q in legs)


def close_debit(rows, fill=1.0):
    """Buy the shorts back, sell the longs. At fill=1.0 that is ask and bid."""
    return sum((-q) * (buy_px(r.bid, r.ask, fill) if q < 0
                       else sell_px(r.bid, r.ask, fill)) for r, q in rows)


def max_loss(legs, credit):
    """Widest wing that can be breached, less the credit taken in."""
    widths = []
    for right in ("P", "C"):
        side = [(r, q) for r, q in legs if r.right == right]
        if len(side) == 2:
            widths.append(abs(side[0][0].strike - side[1][0].strike))
    return max(widths) - credit if widths else np.nan


def intrinsic(legs, s):
    v = 0.0
    for r, q in legs:
        pay = max(s - r.strike, 0) if r.right == "C" else max(r.strike - s, 0)
        v += (-q) * pay          # what the position owes, sign as a debit
    return v


def run(chain, spot_px, structure, lo, hi, exit_rule, fill=1.0):
    dates = np.array(sorted(chain.trade_date.unique()))
    by_date = {d: g for d, g in chain.groupby("trade_date")}
    rows, i = [], 0

    while i < len(dates):
        d0 = dates[i]
        cand = by_date[d0]
        cand = cand[cand.dte.between(lo, hi)]
        if cand.empty:
            i += 1
            continue
        exp = cand.expiration.min()
        legs = build(cand[cand.expiration == exp], structure)
        if legs is None:
            i += 1
            continue
        credit = open_credit(legs, fill)
        ml = max_loss(legs, credit)
        if credit <= 0.05 or not np.isfinite(ml) or ml <= 0:
            i += 1
            continue
        spot0 = legs[0][0].underlying_price
        n_legs = len(legs)
        fees_in = n_legs * COMMISSION

        exit_d, debit, fees_out, why = None, None, 0.0, ""
        for d1 in [d for d in dates if d0 < d <= exp]:
            g = by_date[d1]
            cur = []
            for r, q in legs:
                m = g[(g.expiration == exp) & (g.strike == r.strike)
                      & (g.right == r.right)]
                if m.empty:
                    cur = None
                    break
                cur.append((m.iloc[0], q))
            if cur is None:
                continue
            db = close_debit(cur, fill)
            if exit_rule == "tp50" and db <= 0.50 * credit:
                exit_d, debit, fees_out, why = d1, db, n_legs * COMMISSION, "tp50"
                break
            if exit_rule == "roll21" and (exp - d1).days <= 21:
                exit_d, debit, fees_out, why = d1, db, n_legs * COMMISSION, "roll21"
                break
        if exit_d is None:
            s = spot_px.get(exp)
            if s is None or np.isnan(s):
                i += 1
                continue
            debit, exit_d, fees_out, why = intrinsic(legs, s), exp, 0.0, "expiry"

        pnl = (credit - debit) * 100 - fees_in - fees_out
        rows.append(dict(entry=d0, exit=exit_d, exp=exp, why=why, spot0=spot0,
                         credit=credit, debit=debit, max_loss=ml * 100,
                         fees=fees_in + fees_out, pnl=pnl,
                         ret=pnl / (ml * 100),
                         ret_notional=pnl / (100 * spot0),
                         cw=credit / (ml + credit)))
        nxt = np.searchsorted(dates, exit_d, side="right")
        i = max(nxt, i + 1)
    return pd.DataFrame(rows)


def stats(t):
    if t.empty:
        return None
    r = t.ret.to_numpy(float)
    eq = np.cumsum(r)
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    # B8: a defined-risk spread cannot lose more than its width less the credit
    breaches = int((t.pnl < -t.max_loss - 1e-6).sum())
    return dict(n=len(r), mean=r.mean(),
                t=r.mean() / r.std(ddof=1) * np.sqrt(len(r)) if r.std(ddof=1) else np.nan,
                total=eq[-1], dd=float((eq - peak).min()), win=(r > 0).mean(),
                worst=r.min(), cw=t.cw.median(), breaches=breaches,
                fees=t.fees.sum())


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SOXL",
                   help="underlying; needs {SYMBOL}_Options_YYYY.csv to exist")
    p.add_argument("--fill", type=float, default=1.0,
                   help="half-spreads given up per fill: 1.0 cross (published), "
                        "0.0 mid, -1.0 the far touch (impossible)")
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    chain = load_chain(a.symbol)
    spot = underlying_daily(a.symbol)
    print(f"\nloaded {len(chain):,} quotes, {chain.trade_date.nunique()} dates, "
          f"{chain.trade_date.min().date()} -> {chain.trade_date.max().date()}")
    print(f"DEFINED-RISK CREDIT SPREADS  25-delta short / 10-delta long\n")
    print(f"  {'structure':<9}{'tenor':<9}{'exit':<8}{'n':>5}{'mean':>9}{'t':>7}"
          f"{'total':>9}{'maxDD':>9}{'win%':>6}{'worst':>8}{'cr/wid':>8}{'B8':>5}")
    grid, led = [], []
    for st in ("put_cs", "call_cs", "condor"):
        for lo, hi, tl in TENORS:
            for ex in EXITS:
                t = run(chain, spot, st, lo, hi, ex, a.fill)
                s = stats(t)
                if s is None:
                    print(f"  {st:<9}{tl:<9}{ex:<8}   no cycles")
                    continue
                grid.append(dict(structure=st, tenor=tl, exit=ex, **s))
                led.append(t.assign(structure=st, tenor=tl, exit_rule=ex))
                print(f"  {st:<9}{tl:<9}{ex:<8}{s['n']:>5}{s['mean']*100:>8.2f}%"
                      f"{s['t']:>7.2f}{s['total']*100:>8.0f}%{s['dd']*100:>8.0f}%"
                      f"{s['win']*100:>5.0f}%{s['worst']*100:>7.0f}%"
                      f"{s['cw']*100:>7.0f}%{'ok' if s['breaches']==0 else 'X':>5}")
    g = pd.DataFrame(grid)
    os.makedirs(a.outdir, exist_ok=True)
    tag = ("" if a.fill == 1.0 else f"_k{a.fill:+.2f}") + \
          ("" if a.symbol == "SOXL" else f"_{a.symbol}")
    pd.concat(led).to_csv(os.path.join(a.outdir, f"credit_spread{tag}_ledger.csv"), index=False)
    g.to_csv(os.path.join(a.outdir, f"credit_spread{tag}_grid.csv"), index=False)
    print(f"\n  cells positive: {(g['mean']>0).sum()} of {len(g)}"
          f"     B8 breaches across all cells: {g.breaches.sum()}")
    print(f"  ledger -> {a.outdir}/credit_spread_ledger.csv\n")


if __name__ == "__main__":
    main()
