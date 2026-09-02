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

Return convention
-----------------
P&L per straddle over 100 x the spot at entry -- the notional the contract
controls. Scale-free across a file whose underlying ranges from $6 to $180, and
directly comparable to holding the shares, which is what B7 requires.

    python3 band_lab/v2_dev/short_vol_backtest.py
    python3 band_lab/v2_dev/short_vol_backtest.py --structure strangle
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


def run(chain, spot_px, structure, lo, hi, exit_rule, side='short'):
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
        # short sells at the bid; long buys at the ask. Either way the
        # trader is on the losing side of the quote at entry.
        credit = (cl.bid + pl.bid) if side == "short" else -(cl.ask + pl.ask)
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
            # short buys back at the ask; long sells out at the bid.
            buyback = ((cc.ask.iloc[0] + pp.ask.iloc[0]) if side == "short"
                       else -(cc.bid.iloc[0] + pp.bid.iloc[0]))
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
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    chain = load_chain()
    spot = soxl_daily()
    print(f"\nloaded {len(chain):,} quotes, {chain.trade_date.nunique()} dates, "
          f"{chain.trade_date.min().date()} -> {chain.trade_date.max().date()}")
    print(f"{a.side.upper()} {a.structure.upper()} — the trader always crosses: "
          f"short sells the bid and buys the ask, long buys the ask and sells the bid\n")

    print(f"  {'tenor':<9}{'exit':<9}{'n':>5}{'mean/cycle':>12}{'t':>7}"
          f"{'total':>10}{'maxDD':>9}{'win%':>7}{'worst':>9}")
    grid, ledgers = [], []
    for lo, hi, tl in TENORS:
        for ex in EXITS:
            t = run(chain, spot, a.structure, lo, hi, ex, a.side)
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
    pd.concat(ledgers).to_csv(
        os.path.join(a.outdir, f"short_vol_{a.side}_{a.structure}_ledger.csv"), index=False)
    g.to_csv(os.path.join(a.outdir, f"short_vol_{a.side}_{a.structure}_grid.csv"), index=False)
    print(f"\n  ledger -> {a.outdir}/short_vol_{a.side}_{a.structure}_ledger.csv")
    return g, pd.concat(ledgers), spot


if __name__ == "__main__":
    main()
