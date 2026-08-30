"""
V23 — the PMCC, started on every trading day, benchmarked on every path.

See V23_OPTION_BACKTEST.md. The bar in that document was committed before this
file existed.

The structure (A5, declared in advance, not searched):

    long   call, 120-180 DTE, delta closest to 0.75, rolled when DTE <= 45
    short  call, 5-10 DTE, delta closest to 0.175, re-sold when it expires
    sizing 75% of capital into long premium, remainder cash at 0%
    fills  BUY at the ask, SELL at the bid — the full spread, every time

Every trading day in the sample starts a path. Every path records what
buy-and-hold SOXL did over the identical window. The number that matters is the
difference, not the strategy's return.

    python3 band_lab/v2_dev/option_backtest.py --run
    python3 band_lab/v2_dev/option_backtest.py --verify
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from option_data import load, soxl_closes                          # noqa: E402

OUT = os.path.join(_HERE, "out", "v23")

# --- A5: the configuration, fixed before the run --------------------------
LONG_DELTA, LONG_DTE_LO, LONG_DTE_HI, LONG_ROLL_DTE = 0.75, 120, 180, 45
SHORT_DELTA, SHORT_DTE_LO, SHORT_DTE_HI = 0.175, 3, 10
INVEST_FRAC = 0.75
START_CAPITAL = 100_000.0
HORIZON_DAYS = 252                     # one year of trading days
COMMISSION = 0.65                      # $/contract, IBKR options


def pick(chain, right, dlo, dhi, target_delta, spot):
    """Nearest-delta liquid contract in a DTE window. None if nothing qualifies."""
    c = chain[(chain["right"] == right)
              & (chain["dte"] >= dlo) & (chain["dte"] <= dhi)
              & (chain["bid"] > 0.0) & (chain["ask"] > chain["bid"])]
    if not len(c):
        return None
    i = (c["delta"].abs() - target_delta).abs().idxmin()
    return c.loc[i]


class Book:
    """One path. Cash, one long call, one short call, priced off the chain."""

    def __init__(self, capital):
        self.cash = capital
        self.long = None            # (expiration, strike, qty)
        self.short = None
        self.trades = []

    def _quote(self, by_key, date, exp, strike, right):
        return by_key.get((date, exp, strike, right))

    def log(self, date, action, right, exp, strike, qty, px):
        self.trades.append(dict(date=date, action=action, right=right,
                                expiration=exp, strike=strike, qty=qty,
                                price=px, cash=self.cash))

    def value(self, by_key, date, spot):
        """Mark to market: cash plus what the legs would fetch, at the bid for
        longs and the ask for shorts — the side you would actually trade out at."""
        v = self.cash
        stale = 0
        for leg, sign in ((self.long, +1), (self.short, -1)):
            if leg is None:
                continue
            exp, strike, qty = leg
            q = self._quote(by_key, date, exp, strike, "CALL")
            if q is None:
                # No quote today. Intrinsic is the honest floor; count it.
                px = max(0.0, spot - strike)
                stale += 1
            else:
                px = q[0] if sign > 0 else q[1]      # bid if long, ask if short
            v += sign * px * qty * 100.0
        return v, stale


def run_path(start, dates, chains, by_key, closes, horizon):
    """One start date. Returns (final value, n_trades, n_stale, path length)."""
    i0 = dates.get_loc(start)
    win = dates[i0:i0 + horizon + 1]
    if len(win) < horizon // 2:
        return None

    b = Book(START_CAPITAL)
    spot0 = closes.get(start, np.nan)
    if not np.isfinite(spot0):
        return None

    stale_total = 0
    for k, d in enumerate(win):
        chain = chains.get(d)
        spot = closes.get(d, np.nan)
        if chain is None or not np.isfinite(spot):
            continue

        # --- expire anything that has reached its expiration
        for name in ("long", "short"):
            leg = getattr(b, name)
            if leg is None:
                continue
            exp, strike, qty = leg
            if d >= exp:
                sign = 1 if name == "long" else -1
                intrinsic = max(0.0, spot - strike)
                b.cash += sign * intrinsic * qty * 100.0
                b.log(d, f"expire_{name}", "CALL", exp, strike, qty, intrinsic)
                setattr(b, name, None)

        # --- roll the long when it gets short-dated, or open it on day 0
        need_long = b.long is None or (b.long[0] - d).days <= LONG_ROLL_DTE
        if need_long:
            if b.long is not None:
                exp, strike, qty = b.long
                q = self_q = by_key.get((d, exp, strike, "CALL"))
                px = q[0] if q else max(0.0, spot - strike)
                b.cash += px * qty * 100.0 - COMMISSION * qty
                b.log(d, "sell_long", "CALL", exp, strike, qty, px)
                b.long = None
            row = pick(chain, "CALL", LONG_DTE_LO, LONG_DTE_HI, LONG_DELTA, spot)
            if row is not None:
                budget = (b.cash if b.long is None else 0.0) * INVEST_FRAC
                qty = int(budget // (row["ask"] * 100.0))
                if qty >= 1:
                    cost = row["ask"] * qty * 100.0 + COMMISSION * qty
                    b.cash -= cost
                    b.long = (row["expiration"], row["strike"], qty)
                    b.log(d, "buy_long", "CALL", row["expiration"],
                          row["strike"], qty, row["ask"])

        # --- sell a new weekly short against the long
        if b.short is None and b.long is not None:
            row = pick(chain, "CALL", SHORT_DTE_LO, SHORT_DTE_HI,
                       SHORT_DELTA, spot)
            if row is not None and row["strike"] > b.long[1]:
                qty = b.long[2]
                b.cash += row["bid"] * qty * 100.0 - COMMISSION * qty
                b.short = (row["expiration"], row["strike"], qty)
                b.log(d, "sell_short", "CALL", row["expiration"],
                      row["strike"], qty, row["bid"])

    # --- liquidate at the horizon
    d = win[-1]
    spot = closes.get(d, np.nan)
    for name, sign in (("long", +1), ("short", -1)):
        leg = getattr(b, name)
        if leg is None:
            continue
        exp, strike, qty = leg
        q = by_key.get((d, exp, strike, "CALL"))
        px = (q[0] if sign > 0 else q[1]) if q else max(0.0, spot - strike)
        if q is None:
            stale_total += 1
        b.cash += sign * px * qty * 100.0 - COMMISSION * qty
        b.log(d, f"close_{name}", "CALL", exp, strike, qty, px)
        setattr(b, name, None)

    bench = START_CAPITAL * (closes[win[-1]] / spot0)
    return dict(start=start, end=win[-1], days=len(win),
                strategy=b.cash, benchmark=bench,
                strat_ret=b.cash / START_CAPITAL - 1.0,
                bench_ret=closes[win[-1]] / spot0 - 1.0,
                trades=len(b.trades), stale=stale_total,
                year=start.year), b.trades


def main() -> int:
    ap = argparse.ArgumentParser(description="V23 option backtest")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--horizon", type=int, default=HORIZON_DAYS)
    ap.add_argument("--max-starts", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    if a.verify:
        return verify()

    print("loading option chains...", flush=True)
    d = load(verbose=False)
    closes = soxl_closes()
    closes = closes[(closes.index >= d.trade_date.min())
                    & (closes.index <= d.trade_date.max())]

    print("indexing...", flush=True)
    chains = {k: v for k, v in d.groupby("trade_date")}
    by_key = {}
    for r in d[["trade_date", "expiration", "strike", "right",
                "bid", "ask"]].itertuples(index=False):
        by_key[(r[0], r[1], r[2], r[3])] = (r[4], r[5])

    dates = pd.DatetimeIndex(sorted(chains))
    starts = [s for s in dates if dates.get_loc(s) + a.horizon < len(dates)]
    if a.max_starts:
        starts = starts[:a.max_starts]
    print(f"{len(starts)} start dates, horizon {a.horizon} trading days",
          flush=True)

    rows, alltrades = [], []
    for n, s in enumerate(starts, 1):
        out = run_path(s, dates, chains, by_key, closes, a.horizon)
        if out is None:
            continue
        rec, tr = out
        rows.append(rec)
        for t in tr:
            t["start"] = s
        alltrades.extend(tr)
        if n % 100 == 0:
            print(f"  {n}/{len(starts)}", flush=True)

    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(OUT, "paths.csv"), index=False)
    pd.DataFrame(alltrades).to_csv(os.path.join(OUT, "trades.csv"), index=False)
    report(res)
    return 0


def report(res):
    res = res.copy()
    res["excess"] = res["strat_ret"] - res["bench_ret"]
    w = 88
    print("\n" + "=" * w)
    print("V23 — PMCC vs BUY-AND-HOLD SOXL, every trading day an entry")
    print("=" * w)
    print(f"  {len(res)} paths, {res.start.min().date()} to {res.start.max().date()}")
    print(f"  fills cross the full spread; commission ${COMMISSION}/contract")

    print(f"\n  A3 — 2022 FIRST, before any total:")
    y22 = res[res.year == 2022]
    if len(y22):
        print(f"    {len(y22)} paths starting in 2022")
        print(f"      strategy  median {y22.strat_ret.median()*100:+7.1f}%   "
              f"benchmark median {y22.bench_ret.median()*100:+7.1f}%")
        print(f"      excess    median {y22.excess.median()*100:+7.1f}%   "
              f"strategy beat buy-and-hold in "
              f"{float((y22.excess > 0).mean())*100:.0f}% of them")

    print(f"\n  {'year':>6}{'paths':>7}{'strat med':>12}{'bench med':>12}"
          f"{'excess med':>12}{'win rate':>10}")
    for y, g in res.groupby("year"):
        print(f"  {y:>6}{len(g):>7}{g.strat_ret.median()*100:>+11.1f}%"
              f"{g.bench_ret.median()*100:>+11.1f}%"
              f"{g.excess.median()*100:>+11.1f}%"
              f"{float((g.excess > 0).mean())*100:>9.0f}%")
    print(f"  {'ALL':>6}{len(res):>7}{res.strat_ret.median()*100:>+11.1f}%"
          f"{res.bench_ret.median()*100:>+11.1f}%"
          f"{res.excess.median()*100:>+11.1f}%"
          f"{float((res.excess > 0).mean())*100:>9.0f}%")

    print(f"\n  excess-return distribution (strategy minus buy-and-hold):")
    for q in (0.05, 0.25, 0.50, 0.75, 0.95):
        print(f"    p{int(q*100):02d}  {res.excess.quantile(q)*100:+8.1f}%")

    yrs = sorted(res.year.unique())
    won = [int(res[res.year == y].excess.median() > 0) for y in yrs]
    print(f"\n  A2 — years where the MEDIAN path beat buy-and-hold: "
          f"{sum(won)} of {len(yrs)}  (adoption needs 4 of 5)")
    print(f"  stale marks (no quote, priced at intrinsic): "
          f"{int(res.stale.sum())} across {int(res.trades.sum()):,} trades")


def verify():
    p = os.path.join(OUT, "paths.csv")
    t = os.path.join(OUT, "trades.csv")
    if not (os.path.exists(p) and os.path.exists(t)):
        print("run --run first", file=sys.stderr)
        return 2
    res = pd.read_csv(p, parse_dates=["start", "end"])
    tr = pd.read_csv(t, parse_dates=["start", "date"])
    bad = 0
    n = tr.groupby("start").size()
    for _, r in res.iterrows():
        got = int(n.get(r["start"], 0))
        if got != int(r["trades"]):
            print(f"  MISMATCH {r['start'].date()}: paths says {int(r['trades'])} "
                  f"trades, trades.csv has {got}")
            bad += 1
    print(f"{'FAILED' if bad else 'OK'} — {len(res)} paths, "
          f"{len(tr):,} trade rows, {bad} mismatch(es)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
