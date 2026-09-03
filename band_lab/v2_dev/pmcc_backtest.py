"""
PMCC / call diagonal on SOXL, measured. The bar is V60_PMCC_BAR.md.

V22 found R2 at MAR 1.61 against buy-and-hold's 0.98 and observed it "was never
presented that way because the benchmark was never computed." This computes it,
inside the same harness as the benchmark, against a bar committed first.

Structure, fixed by V60
-----------------------
  LONG   one call, delta nearest target, 120-180 DTE, rolled when DTE <= 45
  SHORT  one call, delta nearest target, nearest expiry at 3-10 DTE, held to
         expiry and settled at intrinsic. Strictly 1:1, never naked.

Sizing is DELTA-MATCHED, so the PMCC carries the same initial delta as the share
benchmark and a lower drawdown cannot be an artifact of a smaller position:

    contracts = floor(equity / (spot * 100 * long_delta))

Costs
-----
  open a leg     pay the ASK          close a leg   receive the BID
  expiry         settle at intrinsic, no closing spread and no commission
  commission     $0.65 per contract per side
  marking        positions are marked at the MID; bid/ask applies to real trades
                 only, so a held position is not charged an exit it did not make

    python3 band_lab/v2_dev/pmcc_backtest.py
    python3 band_lab/v2_dev/pmcc_backtest.py --cash-apy 0.045
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from short_vol_backtest import COMMISSION, load_chain, soxl_daily  # noqa: E402

START = 100_000.0
LONG_DTE = (120, 180)
LONG_ROLL = 45
SHORT_DTE = (3, 10)
LONG_DELTAS = (0.70, 0.75, 0.80)
SHORT_DELTAS = (0.10, 0.175, 0.25)


class Book:
    """Per-date quote lookup, built lazily and cached."""

    def __init__(self, chain):
        self.by_date = {d: g for d, g in chain.groupby("trade_date")}
        self.dates = np.array(sorted(self.by_date))
        self._idx = {}

    def day(self, d):
        return self.by_date.get(d)

    def quote(self, d, exp, strike, right):
        if d not in self._idx:
            g = self.by_date.get(d)
            self._idx = {d: ({} if g is None else
                             {(e, k, r): (b, a) for e, k, r, b, a in
                              zip(g.expiration, g.strike, g.right, g.bid, g.ask)})}
        return self._idx[d].get((exp, strike, right))


def pick_long(day, delta_target):
    g = day[(day.right == "C") & day.dte.between(*LONG_DTE) & (day.delta > 0)]
    if g.empty:
        return None
    return g.loc[(g.delta - delta_target).abs().idxmin()]


def pick_short(day, delta_target):
    g = day[(day.right == "C") & day.dte.between(*SHORT_DTE) & (day.delta > 0)]
    if g.empty:
        return None
    g = g[g.expiration == g.expiration.min()]        # nearest expiry in the band
    return g.loc[(g.delta - delta_target).abs().idxmin()]


def run(book, spot_px, long_delta, short_delta, mode="pmcc", cash_apy=0.0):
    """mode: pmcc | long_only | covered_call | buy_hold."""
    cash, shares = START, 0
    lng = sht = None                   # dicts: exp, strike, qty, entry
    marks, rows, trades = [], [], []
    stale = binding = naked = 0
    prev_mark = {}

    for i, d in enumerate(book.dates):
        day = book.day(d)
        spot = day.underlying_price.iloc[0]
        if cash_apy and i:
            cash *= (1 + cash_apy / 252.0)

        # ---- benchmark: buy once, hold
        if mode == "buy_hold":
            if not shares:
                shares = int(cash // spot)
                cash -= shares * spot
            marks.append((d, cash + shares * spot, spot))
            continue

        # ---- short leg settles at its expiry, at intrinsic, no spread, no fee
        if sht is not None and d >= sht["exp"]:
            s = spot_px.get(sht["exp"], spot)
            intr = max(s - sht["strike"], 0.0)
            cash -= intr * 100 * sht["qty"]
            trades.append(dict(date=d, leg="short", act="expire", px=intr,
                               qty=sht["qty"], fee=0.0))
            sht = None

        # ---- long leg: open, or roll when it gets too short
        want_roll = lng is not None and (lng["exp"] - d).days <= LONG_ROLL
        if mode != "covered_call" and (lng is None or want_roll):
            if lng is not None:                       # close the old one at BID
                q = book.quote(d, lng["exp"], lng["strike"], "C")
                if q is not None:
                    cash += q[0] * 100 * lng["qty"] - COMMISSION * lng["qty"]
                    trades.append(dict(date=d, leg="long", act="close", px=q[0],
                                       qty=lng["qty"], fee=COMMISSION * lng["qty"]))
                    lng = None
                else:
                    stale += 1
            if lng is None:
                r = pick_long(day, long_delta)
                if r is not None:
                    eq = cash + _mv(book, d, None, sht, prev_mark)
                    # delta-matched sizing, then cut to what cash can pay for
                    qty = int(eq // (spot * 100 * long_delta))
                    cost = r.ask * 100 + COMMISSION
                    afford = int(cash // cost) if cost > 0 else 0
                    if afford < qty:
                        binding += 1
                    qty = max(min(qty, afford), 0)
                    if qty:
                        cash -= r.ask * 100 * qty + COMMISSION * qty
                        lng = dict(exp=r.expiration, strike=r.strike, qty=qty,
                                   entry=r.ask)
                        trades.append(dict(date=d, leg="long", act="open",
                                           px=r.ask, qty=qty, fee=COMMISSION * qty,
                                           delta=r.delta, target=long_delta))

        # ---- covered_call holds shares instead of a long call
        if mode == "covered_call" and not shares:
            shares = int(cash // spot)
            cash -= shares * spot

        # ---- short leg, strictly 1:1 against whatever is covering it
        cover = (lng["qty"] if lng else 0) if mode != "covered_call" else shares // 100
        if mode in ("pmcc", "covered_call") and sht is None and cover > 0:
            r = pick_short(day, short_delta)
            if r is not None:
                if lng is not None and r.strike <= lng["strike"]:
                    naked += 1                        # would not be covered
                else:
                    cash += r.bid * 100 * cover - COMMISSION * cover
                    sht = dict(exp=r.expiration, strike=r.strike, qty=cover,
                               entry=r.bid)
                    trades.append(dict(date=d, leg="short", act="open", px=r.bid,
                                       qty=cover, fee=COMMISSION * cover,
                                       delta=r.delta, target=short_delta))

        mv, st = _mv(book, d, lng, sht, prev_mark, count=True)
        stale += st
        eq = cash + shares * spot + mv
        marks.append((d, eq, spot))
        rows.append(dict(date=d, equity=eq, cash=cash, spot=spot,
                         long_qty=lng["qty"] if lng else 0,
                         short_qty=sht["qty"] if sht else 0))

    m = pd.DataFrame(marks, columns=["date", "equity", "spot"]).set_index("date")
    return m, pd.DataFrame(trades), dict(stale=stale, binding=binding, naked=naked)


def _mv(book, d, lng, sht, prev, count=False):
    """Mark open option legs at the mid, carrying the last mark if a quote is gone."""
    tot, stale = 0.0, 0
    for pos, sign in ((lng, +1), (sht, -1)):
        if not pos:
            continue
        q = book.quote(d, pos["exp"], pos["strike"], "C")
        if q is None:
            px = prev.get((sign, pos["exp"], pos["strike"]))
            if px is None:
                px = pos["entry"]
            stale += 1
        else:
            px = 0.5 * (q[0] + q[1])
        prev[(sign, pos["exp"], pos["strike"])] = px
        tot += sign * px * 100 * pos["qty"]
    return (tot, stale) if count else tot


def metrics(m):
    eq = m.equity.to_numpy(float)
    if len(eq) < 2 or eq[0] <= 0:
        return None
    yrs = (m.index[-1] - m.index[0]).days / 365.25
    total = eq[-1] / eq[0] - 1
    cagr = (eq[-1] / eq[0]) ** (1 / yrs) - 1 if eq[-1] > 0 else -1.0
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    w = m.equity.resample("W").last().pct_change().dropna()
    return dict(total=total, cagr=cagr, dd=dd,
                mar=cagr / abs(dd) if dd else np.nan,
                wk_mean=w.mean(), wk_se=w.std(ddof=1) / np.sqrt(len(w)),
                n_wk=len(w), final=eq[-1])


def by_year(m):
    out = {}
    for y, g in m.groupby(m.index.year):
        e = g.equity.to_numpy(float)
        d = float((e / np.maximum.accumulate(e) - 1).min())
        out[y] = (e[-1] / e[0] - 1) / abs(d) if d else np.nan
    return out


def quarter_share(m):
    """B8: largest single calendar quarter as a share of total P&L."""
    pnl = m.equity.diff().dropna()
    q = pnl.groupby(pnl.index.to_period("Q")).sum()
    tot = m.equity.iloc[-1] - m.equity.iloc[0]
    return (q.max() / tot) if tot > 0 else np.nan


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cash-apy", type=float, default=0.0,
                   help="yield on idle cash; 0.0 is the headline, V60 sensitivity only")
    p.add_argument("--since", default=None,
                   help="restrict the window, e.g. 2024-01-02 to reconcile against V22")
    p.add_argument("--until", default=None)
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    chain = load_chain()
    spot = soxl_daily()
    if a.since:
        chain = chain[chain.trade_date >= pd.Timestamp(a.since)]
    if a.until:
        chain = chain[chain.trade_date <= pd.Timestamp(a.until)]
    book = Book(chain)
    print(f"\nloaded {len(chain):,} quotes, {len(book.dates)} dates, "
          f"{pd.Timestamp(book.dates[0]).date()} -> {pd.Timestamp(book.dates[-1]).date()}")
    print(f"PMCC — delta-matched, full spread crossed, cash at {a.cash_apy:.1%}\n")

    bh, _, _ = run(book, spot, 0.75, 0.175, "buy_hold", a.cash_apy)
    bm = metrics(bh)
    print(f"  BENCHMARK buy-and-hold SOXL: total {bm['total']*100:+,.0f}%  "
          f"CAGR {bm['cagr']*100:+.1f}%  maxDD {bm['dd']*100:.1f}%  "
          f"MAR {bm['mar']:.2f}")
    bh_yr = by_year(bh)
    print(f"  benchmark's own largest-quarter share of its P&L: "
          f"{quarter_share(bh)*100:.0f}%   <- B8 read against this, not against 50% in a vacuum")

    rows, curves = [], {"buy_hold": bh}
    print(f"\n  {'config':<22}{'total':>10}{'CAGR':>9}{'maxDD':>9}{'MAR':>7}"
          f"{'vs BH':>8}{'yrs>BH':>8}{'maxQ':>7}")
    for mode in ("pmcc", "long_only", "covered_call"):
        grid = [(ld, sd) for ld in LONG_DELTAS for sd in SHORT_DELTAS] \
            if mode == "pmcc" else [(ld, 0.175) for ld in LONG_DELTAS] \
            if mode == "long_only" else [(0.75, sd) for sd in SHORT_DELTAS]
        for ld, sd in grid:
            m, tr, diag = run(book, spot, ld, sd, mode, a.cash_apy)
            s = metrics(m)
            if s is None:
                continue
            yr = by_year(m)
            wins = sum(1 for y in yr if y in bh_yr and yr[y] > bh_yr[y])
            qs = quarter_share(m)
            name = (f"{mode} L{ld:.2f}/S{sd:.3f}" if mode == "pmcc"
                    else f"{mode} L{ld:.2f}" if mode == "long_only"
                    else f"{mode} S{sd:.3f}")
            rows.append(dict(mode=mode, long_delta=ld, short_delta=sd, **s,
                             yrs_beat=wins, n_yrs=len(yr), max_q=qs,
                             fees=tr.fee.sum() if len(tr) else 0.0, **diag))
            curves[name] = m
            print(f"  {name:<22}{s['total']*100:>9,.0f}%{s['cagr']*100:>8.1f}%"
                  f"{s['dd']*100:>8.1f}%{s['mar']:>7.2f}"
                  f"{'YES' if s['mar'] > bm['mar'] else 'no':>8}"
                  f"{f'{wins}/{len(yr)}':>8}{qs*100:>6.0f}%")

    g = pd.DataFrame(rows)
    os.makedirs(a.outdir, exist_ok=True)
    tag = ("" if a.cash_apy == 0 else f"_cash{a.cash_apy:.3f}") + \
          ("" if not a.since else f"_from{a.since}")
    g.to_csv(os.path.join(a.outdir, f"V61_pmcc_grid{tag}.csv"), index=False)
    pd.DataFrame({k: v.equity for k, v in curves.items()}).to_csv(
        os.path.join(a.outdir, f"V61_pmcc_curves{tag}.csv"))
    print(f"\n  grid -> {a.outdir}/V61_pmcc_grid{tag}.csv")
    return g, bm, bh_yr


if __name__ == "__main__":
    main()
