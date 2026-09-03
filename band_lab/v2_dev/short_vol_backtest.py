"""
Short volatility on SOXL, measured. The bar is V53_SHORT_VOL_BAR.md.

Long vol was backtested five times in this project and short vol never once.
Every short structure was retired on a volatility-point screen, and V31 showed
that screen can be wrong by more than its own answer. This measures it.

The rule
--------
Sell an ATM straddle, or a 25-delta strangle, at a target days-to-expiry. One
position at a time; the next cycle starts only after the current one closes, so
cycles are independent rather than overlapping.

Costs, every one charged
------------------------
  entry        sold at the BID, crossing the whole spread
  early exit   bought back at the ASK, crossing it again
  expiry exit  settled at intrinsic against SOXL's close, NO closing spread
  commission   $0.65 per contract per side

Holding to expiry genuinely avoids a closing spread. That is a real property of
the exit, not an accounting shortcut, and it is why the expiry column is
expected to beat the managed ones on cost alone.

`--fill k` varies that convention -- k = 1.0 is the touch and the default, so
the published result is unchanged; see V58_OPTION_FILL_LADDER.md. Read sell_px
for what k means and what it cannot model.

Return convention
-----------------
P&L per straddle over 100 x the spot at entry -- the notional the contract
controls. Scale-free across a file whose underlying ranges from $6 to $180, and
directly comparable to holding the shares, which is what B7 requires.

    python3 band_lab/v2_dev/short_vol_backtest.py
    python3 band_lab/v2_dev/short_vol_backtest.py --structure strangle
    python3 band_lab/v2_dev/short_vol_backtest.py --side long --fill 0.0
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
YEARS = ("2022", "2023", "2024", "2025", "2026")
TENORS = ((21, 30, "21-30d"), (31, 45, "31-45d"), (46, 60, "46-60d"))
EXITS = ("expiry", "tp50", "roll21")
COMMISSION = 0.65
TICK_BREAK, TICK_LO, TICK_HI = 3.00, 0.01, 0.05
EPS = 1e-9


def tick_size(bid, ask):
    """SOXL options quote in $0.01 under $3.00 and $0.05 at or above it.

    Measured on the file rather than assumed: at a mid below $3.00, 100% of
    bids sit on the penny grid and only 20% on the nickel; at or above $3.00,
    99.4% of bids and 100% of asks sit on the nickel grid.
    """
    return TICK_LO if 0.5 * (bid + ask) < TICK_BREAK else TICK_HI


def sell_px(bid, ask, k=1.0):
    """Price received on a sale, k half-spreads on the wrong side of the mid.

    k = 1 is the bid -- cross the whole spread, which is what every published
    result in this project assumes. k = 0 is the mid, k > 1 is worse than the
    bid, k = -1 is the ask and cannot happen.

    The price is snapped to a whole tick measured FROM THE BID, so k = 1
    returns the bid exactly (the regression against the published numbers is
    exact) and a market only one tick wide has nothing inside it to fill at.
    """
    half = 0.5 * (ask - bid)
    t = tick_size(bid, ask)
    n = np.floor((1.0 - k) * half / t + EPS)
    return max(bid + n * t, 0.0)


def buy_px(bid, ask, k=1.0):
    """Price paid on a purchase, k half-spreads on the wrong side of the mid.

    Mirror of sell_px: k = 1 is the ask, k = 0 the mid, k = -1 the bid.
    """
    half = 0.5 * (ask - bid)
    t = tick_size(bid, ask)
    n = np.ceil(-(1.0 - k) * half / t - EPS)
    return max(ask + n * t, 0.0)


def parse_dates(s, year):
    """The files disagree on date format: 2025 is m/d/yy, the rest ISO.

    Guessing is how a backtest silently trades the wrong expiry, so the format
    is chosen from the data and the result is checked against the file's own
    year before it is returned.
    """
    txt = s.astype(str)
    if txt.str.contains("/").any():
        first = txt.str.split("/").str[0].astype(int)
        second = txt.str.split("/").str[1].astype(int)
        if first.max() > 12 and second.max() <= 12:
            fmt = "%d/%m/%y"          # day first
        elif second.max() > 12:
            fmt = "%m/%d/%y"          # month first, the US convention
        else:
            raise ValueError(f"{year}: m/d order is ambiguous, refusing to guess")
        return pd.to_datetime(txt, format=fmt)
    return pd.to_datetime(txt, format="%Y-%m-%d")


def load_chain():
    use = ["expiration", "strike", "right", "bid", "ask", "delta",
           "implied_vol", "underlying_price", "trade_date"]
    parts = []
    for y in YEARS:
        p = os.path.join(ROOT, f"SOXL_Options_{y}.csv")
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p, usecols=use, low_memory=False)
        d["trade_date"] = parse_dates(d.trade_date, y)
        d["expiration"] = parse_dates(d.expiration, y)
        bad = (d.trade_date.dt.year != int(y)).mean()
        if bad > 0.01:
            raise ValueError(f"{y}: {bad:.1%} of trade_dates fall outside {y} "
                             f"— date parsing is wrong, refusing to continue")
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    d["dte"] = (d.expiration - d.trade_date).dt.days
    # A quote needs two live sides. Sub-nickel bids are not tradeable.
    d = d[(d.bid > 0.05) & (d.ask > d.bid) & d.delta.notna()
          & (d.underlying_price > 0)]
    d["right"] = d.right.str.upper().str[0]
    return d.sort_values("trade_date").reset_index(drop=True)


def soxl_daily():
    df = pd.read_csv(os.path.join(ROOT, "SOXL_1min.csv"))
    dt = pd.to_datetime(df["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    return df.assign(d=dt.dt.normalize()).groupby("d").Close.last()


def pick_legs(day, structure):
    """Return (call_row, put_row) for the chosen structure, or None."""
    spot = day.underlying_price.iloc[0]
    c, p = day[day.right == "C"], day[day.right == "P"]
    if c.empty or p.empty:
        return None
    if structure == "straddle":
        k = c.strike.iloc[(c.strike - spot).abs().argmin()]
        cl = c[c.strike == k]
        pl = p[p.strike == k]
    else:                                     # 25-delta strangle
        cl = c.iloc[[(c.delta.abs() - 0.25).abs().argmin()]]
        pl = p.iloc[[(p.delta.abs() - 0.25).abs().argmin()]]
    if cl.empty or pl.empty:
        return None
    return cl.iloc[0], pl.iloc[0]


def run(chain, spot_px, structure, lo, hi, exit_rule, side='short', fill=1.0):
    """Walk the file, one non-overlapping cycle at a time."""
    dates = np.array(sorted(chain.trade_date.unique()))
    by_date = {d: g for d, g in chain.groupby("trade_date")}
    rows, i = [], 0

    while i < len(dates):
        d0 = dates[i]
        day = by_date[d0]
        cand = day[day.dte.between(lo, hi)]
        if cand.empty:
            i += 1
            continue
        # nearest expiry inside the window, so the tenor is what it says
        exp = cand.expiration.min()
        legs = pick_legs(cand[cand.expiration == exp], structure)
        if legs is None:
            i += 1
            continue
        cl, pl = legs
        spot0 = cl.underlying_price
        # short sells, long buys. At fill=1.0 that is the bid and the ask --
        # the trader on the losing side of the whole quote, which is the
        # published convention. Lower fill rests the order inside the spread.
        if side == "short":
            credit = (sell_px(cl.bid, cl.ask, fill)
                      + sell_px(pl.bid, pl.ask, fill))
        else:
            credit = -(buy_px(cl.bid, cl.ask, fill)
                       + buy_px(pl.bid, pl.ask, fill))
        fees_in = 2 * COMMISSION
        # Skip a position whose premium is too small to be worth trading.
        # `credit` is a debit (negative) on the long side, so test magnitude.
        if abs(credit) <= 0.10:
            i += 1
            continue

        # walk forward to the exit
        fwd = [d for d in dates if d0 < d <= exp]
        exit_d, cost, fees_out, why = None, None, 0.0, ""
        for d1 in fwd:
            g = by_date[d1]
            cc = g[(g.expiration == exp) & (g.strike == cl.strike) & (g.right == "C")]
            pp = g[(g.expiration == exp) & (g.strike == pl.strike) & (g.right == "P")]
            if cc.empty or pp.empty:
                continue
            # short buys back, long sells out; same fill convention as entry.
            c1, p1 = cc.iloc[0], pp.iloc[0]
            if side == "short":
                buyback = (buy_px(c1.bid, c1.ask, fill)
                           + buy_px(p1.bid, p1.ask, fill))
            else:
                buyback = -(sell_px(c1.bid, c1.ask, fill)
                            + sell_px(p1.bid, p1.ask, fill))
            dte_now = (exp - d1).days
            # "Take half the profit off." For a short that means buying back
            # at half the credit taken in. The mirror for a long is selling out
            # at 1.5x the debit paid -- NOT at half of it, which is a stop-loss
            # and fires on almost every cycle.
            take = ((buyback <= 0.50 * credit) if side == "short"
                    else (-buyback >= 1.50 * -credit))
            if exit_rule == "tp50" and take:
                exit_d, cost, fees_out, why = d1, buyback, 2 * COMMISSION, "tp50"
                break
            if exit_rule == "roll21" and dte_now <= 21:
                exit_d, cost, fees_out, why = d1, buyback, 2 * COMMISSION, "roll21"
                break
        if exit_d is None:                             # ran to expiry
            s = spot_px.get(exp)
            if s is None or np.isnan(s):
                i += 1
                continue
            intr = max(s - cl.strike, 0) + max(pl.strike - s, 0)
            cost = intr if side == "short" else -intr
            exit_d, fees_out, why = exp, 0.0, "expiry"             # no closing spread

        pnl = (credit - cost) * 100 - fees_in - fees_out
        rows.append(dict(entry=d0, exit=exit_d, exp=exp, why=why,
                         spot0=spot0, kc=cl.strike, kp=pl.strike,
                         credit=credit, cost=cost,
                         fees=fees_in + fees_out, pnl=pnl,
                         ret=pnl / (100 * spot0),
                         iv=(cl.implied_vol + pl.implied_vol) / 2))
        nxt = np.searchsorted(dates, exit_d, side="right")
        i = max(nxt, i + 1)

    return pd.DataFrame(rows)


def stats(t):
    if t.empty:
        return None
    r = t.ret.to_numpy(float)
    eq = np.cumprod(1 + r)
    peak = np.maximum.accumulate(eq)
    return dict(n=len(r), mean=r.mean(), t=r.mean() / r.std(ddof=1) * np.sqrt(len(r))
                if r.std(ddof=1) else np.nan,
                total=eq[-1] - 1, dd=float((eq / peak - 1).min()),
                win=(r > 0).mean(), worst=r.min(), best=r.max(),
                fees=t.fees.sum())


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--structure", default="straddle", choices=["straddle", "strangle"])
    p.add_argument("--side", default="short", choices=["short", "long"])
    p.add_argument("--fill", type=float, default=1.0,
                   help="half-spreads given up per fill: 1.0 cross (published), "
                        "0.0 mid, -1.0 the far touch (impossible)")
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    chain = load_chain()
    spot = soxl_daily()
    print(f"\nloaded {len(chain):,} quotes, {chain.trade_date.nunique()} dates, "
          f"{chain.trade_date.min().date()} -> {chain.trade_date.max().date()}")
    print(f"{a.side.upper()} {a.structure.upper()}   fill={a.fill:+.2f} half-spreads "
          f"({'cross the whole quote' if a.fill == 1.0 else 'inside the quote' if a.fill < 1.0 else 'worse than the touch'})\n")

    print(f"  {'tenor':<9}{'exit':<9}{'n':>5}{'mean/cycle':>12}{'t':>7}"
          f"{'total':>10}{'maxDD':>9}{'win%':>7}{'worst':>9}")
    grid, ledgers = [], []
    for lo, hi, tl in TENORS:
        for ex in EXITS:
            t = run(chain, spot, a.structure, lo, hi, ex, a.side, a.fill)
            s = stats(t)
            if s is None:
                print(f"  {tl:<9}{ex:<9}    no cycles")
                continue
            grid.append(dict(tenor=tl, exit=ex, **s))
            ledgers.append(t.assign(tenor=tl, exit_rule=ex))
            print(f"  {tl:<9}{ex:<9}{s['n']:>5}{s['mean']*100:>11.3f}%{s['t']:>7.2f}"
                  f"{s['total']*100:>9.1f}%{s['dd']*100:>8.1f}%"
                  f"{s['win']*100:>6.0f}%{s['worst']*100:>8.1f}%")
    g = pd.DataFrame(grid)
    os.makedirs(a.outdir, exist_ok=True)
    # a non-default fill must not overwrite the published baseline
    tag = "" if a.fill == 1.0 else f"_k{a.fill:+.2f}"
    stem = f"short_vol_{a.side}_{a.structure}{tag}"
    pd.concat(ledgers).to_csv(os.path.join(a.outdir, f"{stem}_ledger.csv"), index=False)
    g.to_csv(os.path.join(a.outdir, f"{stem}_grid.csv"), index=False)
    print(f"\n  ledger -> {a.outdir}/{stem}_ledger.csv")
    return g, pd.concat(ledgers), spot


if __name__ == "__main__":
    main()
