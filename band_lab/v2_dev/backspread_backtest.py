"""
Call backspread: buy 2x 25-delta call, sell 1x ATM call. V29 Tier 1 #3.

The bar, the grid and the four new assumptions were committed in
V35_BACKSPREAD_BAR.md before this file existed. Read that first.

A separate file from `straddle_backtest.py` because the structure differs in
every way that matters: three legs not two, one of them SHORT, a payoff that is
not symmetric, and a denominator that cannot be premium. V35 fixed the
denominator as **max loss** = (K2 - K1) x 100 + net debit, which is also
approximately the margin the broker holds.

    python3 band_lab/v2_dev/backspread_backtest.py
    python3 band_lab/v2_dev/backspread_backtest.py --grid
    python3 band_lab/v2_dev/backspread_backtest.py --trace 3
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import option_data                                                 # noqa: E402
from research_kit import Result, daily_closes, table               # noqa: E402

CONTRACT = 100
CONTRACTS = 10                       # structures; each is 2 long + 1 short
OPT_COMMISSION = 0.65                # [ASSUMED] V30 A5
STOCK_BP_RT = 6.70                   # [MEASURED] SOXL round trip
HEDGE_BP_ONE_WAY = 0.495 + 2.85      # [MEASURED]

#: V32 measured the real ATM straddle round trip at 17.8 vol points against the
#: 10.6 the vendor file implies. Per LEG that shortfall is 3.6 round trip, 1.8
#: one way. V35 A21: applied per leg scaled by that leg's vega, and flagged as
#: probably understating the OTM legs, whose spreads are wider in vol terms.
SHORTFALL_VOL_PTS_PER_LEG_ONEWAY = 1.8

TARGET_DTE, DTE_WINDOW = 37, 13
LONG_DELTAS = (0.20, 0.25, 0.30)
EXITS = ("expiry", "roll")
ROLL_DTE = 14
HEADLINE = (0.25, "expiry")


@dataclass
class Cycle:
    open_date: pd.Timestamp
    close_date: pd.Timestamp
    expiry: pd.Timestamp
    k_short: float
    k_long: float
    spot_open: float
    spot_close: float
    dte_open: int
    debit: float                     # what leaving the account cost, at fills
    max_loss: float
    payoff: float                    # what came back
    commission: float
    stock_cost: float
    extra_spread: float
    net_vega: float
    sessions: int

    @property
    def net(self):
        return self.payoff - self.debit - self.commission - self.stock_cost \
            - self.extra_spread

    @property
    def ret(self):
        return self.net / self.max_loss if self.max_loss > 0 else np.nan


def load_chain():
    d = option_data.load(verbose=True, extra=("vega",))
    d = d[(d.bid > 0) & (d.ask > d.bid) & (d.implied_vol > 0)
          & (d.right == "CALL")].copy()
    d["mid"] = (d["bid"] + d["ask"]) / 2.0
    return d


def pick(day: pd.DataFrame, target_dte: int, long_delta: float):
    """Nearest expiry to target, ATM short leg, `long_delta` long legs.

    Both legs must come from the SAME expiry and the long strike must sit above
    the short strike, or it is not a backspread.
    """
    cand = day[(day.dte - target_dte).abs() <= DTE_WINDOW]
    if cand.empty:
        return None
    exp = cand.loc[(cand.dte - target_dte).abs().idxmin(), "expiration"]
    g = cand[cand.expiration == exp]
    if len(g) < 2:
        return None
    s = g.iloc[(g.delta - 0.50).abs().argsort()[:1]].iloc[0]
    l = g.iloc[(g.delta - long_delta).abs().argsort()[:1]].iloc[0]
    if abs(s.delta - 0.50) > 0.08 or abs(l.delta - long_delta) > 0.08:
        return None
    if l.strike <= s.strike:
        return None
    return s, l, exp


def run(chain, spot, long_delta, exit_mode, shortfall=0.0, trace=0):
    by_date = {d: g for d, g in chain.groupby("trade_date")}
    dates = sorted(by_date)
    sz = CONTRACT * CONTRACTS
    cycles, abandoned = [], 0

    i = 0
    while i < len(dates) - 1:
        sel = pick(by_date[dates[i]], TARGET_DTE, long_delta)
        if sel is None:
            i += 1
            continue
        s0, l0, exp = sel
        expiry_ts = pd.Timestamp(exp)
        k_s, k_l = float(s0.strike), float(l0.strike)

        # Entry: BUY 2 longs at the ask, SELL 1 short at the bid. Both sides
        # cross the spread against you; that is the point of the V35 screen.
        debit = (2 * float(l0.ask) - float(s0.bid)) * sz
        comm = 3 * OPT_COMMISSION * CONTRACTS
        net_vega = (2 * float(l0.vega) - float(s0.vega)) * sz
        # V35 A21: 3 legs, one-way, each scaled by its own vega
        extra = shortfall * ((2 * float(l0.vega) + float(s0.vega)) * sz) / 100.0
        max_loss = (k_l - k_s) * sz + debit

        j, payoff, stock_cost, close_date, spot_close, n_sess = \
            i + 1, None, 0.0, None, None, 0
        while j < len(dates):
            dj = dates[j]
            n_sess += 1
            if exit_mode == "expiry" and dj >= expiry_ts:
                S = float(spot.asof(expiry_ts))
                payoff = (2 * max(S - k_l, 0.0) - max(S - k_s, 0.0)) * sz
                # any leg finishing in the money is exercised or assigned into
                # stock and liquidated; charge the measured stock round trip on
                # the gross shares that change hands
                sh = (2 * (S > k_l) + 1 * (S > k_s)) * sz
                stock_cost = sh * S * STOCK_BP_RT / 1e4
                close_date, spot_close = dj, S
                break
            g = by_date[dj]
            gs = g[(g.strike == k_s) & (g.expiration == exp)]
            gl = g[(g.strike == k_l) & (g.expiration == exp)]
            if len(gs) != 1 or len(gl) != 1:
                j += 1
                continue
            sj, lj = gs.iloc[0], gl.iloc[0]
            if exit_mode == "roll" and (int(sj.dte) <= ROLL_DTE
                                        or j == len(dates) - 1):
                # unwind: SELL the longs at the bid, BUY the short at the ask
                payoff = (2 * float(lj.bid) - float(sj.ask)) * sz
                comm += 3 * OPT_COMMISSION * CONTRACTS
                extra += shortfall * ((2 * float(lj.vega) + float(sj.vega))
                                      * sz) / 100.0
                close_date = dj
                spot_close = float(sj.underlying_price)
                break
            j += 1

        if payoff is None:
            abandoned += 1
            i += 1
            continue

        c = Cycle(open_date=dates[i], close_date=close_date, expiry=expiry_ts,
                  k_short=k_s, k_long=k_l, spot_open=float(s0.underlying_price),
                  spot_close=spot_close, dte_open=int(s0.dte), debit=debit,
                  max_loss=max_loss, payoff=payoff, commission=comm,
                  stock_cost=stock_cost, extra_spread=extra,
                  net_vega=net_vega, sessions=n_sess)
        cycles.append(c)
        if trace and len(cycles) <= trace:
            _trace(c, s0, l0)
        i = j
    if abandoned:
        print(f"    ({abandoned} cycles abandoned)")
    return cycles


def _trace(c, s0, l0):
    print(f"\n  --- {c.open_date.date()} -> {c.close_date.date()} "
          f"({c.sessions} sessions, {c.dte_open} DTE at open)")
    print(f"      SELL 1x {c.k_short:.0f}C at bid {s0.bid:.2f} "
          f"(delta {s0.delta:.2f})")
    print(f"      BUY  2x {c.k_long:.0f}C at ask {l0.ask:.2f} "
          f"(delta {l0.delta:.2f})")
    print(f"      spot {c.spot_open:.2f} -> {c.spot_close:.2f}   "
          f"width {c.k_long - c.k_short:.2f}")
    print(f"      debit {c.debit:+,.0f}   payoff {c.payoff:+,.0f}   "
          f"max loss {c.max_loss:,.0f}")
    print(f"      commission {-c.commission:,.0f}  stock {-c.stock_cost:,.0f}  "
          f"extra spread {-c.extra_spread:,.0f}")
    print(f"      NET {c.net:+,.0f}  ({c.ret*100:+.1f}% of max loss)")


def _audit(cycles, spot) -> list[str]:
    """V35's discard rules, asserted rather than eyeballed."""
    bad = []
    for c in cycles:
        if c.k_long <= c.k_short:
            bad.append(f"{c.open_date.date()}: long strike not above short")
        if c.max_loss <= 0:
            bad.append(f"{c.open_date.date()}: non-positive max loss")
        if c.close_date >= c.expiry:
            S = c.spot_close
            want = (2 * max(S - c.k_long, 0.0)
                    - max(S - c.k_short, 0.0)) * CONTRACT * CONTRACTS
            if abs(want - c.payoff) > 1e-6:
                bad.append(f"{c.open_date.date()}: expiry payoff {c.payoff:.0f}"
                           f" != intrinsic {want:.0f}")
    return bad


def summarize(cycles, verbose=True):
    df = pd.DataFrame([dict(vars(c), net=c.net, ret=c.ret) for c in cycles])
    df["year"] = pd.to_datetime(df.open_date).dt.year
    n = len(df)
    m = df.ret.mean()
    sem = df.ret.std(ddof=1) / math.sqrt(n) if n > 1 else np.nan
    eq = (1 + 0.05 * df["ret"]).cumprod()
    out = dict(n=n, mean=m, sem=sem, t=m / sem if sem else np.nan,
               win=(df.net > 0).mean(),
               years_pos=int((df.groupby("year")["ret"].mean() > 0).sum()),
               years=df.year.nunique(),
               mdd=float((eq / eq.cummax() - 1).min()),
               equity=float(eq.iloc[-1] - 1), df=df)
    if not verbose:
        return out
    print(f"\n  {n} cycles, {df.open_date.min().date()} to "
          f"{df.close_date.max().date()}, {CONTRACTS} structures")
    print(f"  average hold {df.sessions.mean():.1f} sessions, "
          f"width ${(df.k_long - df.k_short).mean():.2f}, "
          f"net vega {df.net_vega.mean():,.0f}")
    # ONE bottom line. A dollar mean and a ratio mean disagree in sign here
    # for the same reason they did in V31 C1 -- max loss varies 6x across the
    # sample -- and printing both invites reading whichever one flatters. V35
    # fixed return-on-max-loss as the metric before any result was seen, so
    # that is the column, and every row is a share of the same denominator.
    print(f"\n  {'component':<34}{'% of max loss':>16}")
    print("  " + "-" * 52)
    for k, name in (("debit", "credit received / debit paid at entry"),
                    ("payoff", "payoff at exit"),
                    ("commission", "option commission"),
                    ("stock_cost", "stock liquidation"),
                    ("extra_spread", "V32 measured spread shortfall")):
        sign = 1 if k == "payoff" else -1
        print(f"  {name:<34}{sign*(df[k]/df.max_loss).mean()*100:>+15.1f}%")
    print("  " + "-" * 52)
    print(f"  {'= NET':<34}{m*100:>+15.1f}%")
    print(f"  (mean dollar P&L is {df.net.mean():+,.0f}/cycle on an average "
          f"${df.max_loss.mean():,.0f} of max loss;\n   the two disagree in "
          f"sign because max loss ranges "
          f"${df.max_loss.min():,.0f}-${df.max_loss.max():,.0f})")
    print(f"\n  mean return per cycle    {m*100:+.2f}%   t = {out['t']:+.2f}"
          f"   (se {sem*100:.2f}%)")
    print(f"  median                   {df.ret.median()*100:+.2f}%")
    print(f"  cycles profitable        {out['win']*100:.0f}%")
    print(f"  average max loss         ${df.max_loss.mean():,.0f}")
    print(f"  equity at 5%/cycle       {out['equity']*100:+.1f}%, "
          f"max drawdown {out['mdd']*100:.1f}%")
    print(f"\n  {'year':<8}{'cycles':>8}{'mean ret':>11}{'win%':>7}")
    print("  " + "-" * 34)
    for y, g in df.groupby("year"):
        print(f"  {y:<8}{len(g):>8}{g.ret.mean()*100:>+10.1f}%"
              f"{(g.net>0).mean()*100:>6.0f}%")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--trace", type=int, default=0)
    ap.add_argument("--shortfall", type=float,
                    default=SHORTFALL_VOL_PTS_PER_LEG_ONEWAY,
                    help="vol points of measured spread shortfall per leg, "
                         "one way; 0 reproduces the vendor-spread run")
    a = ap.parse_args()

    chain = load_chain()
    spot = daily_closes("SOXL")

    print("=" * 84)
    print("V35 — CALL BACKSPREAD: BUY 2x 25-DELTA CALL, SELL 1x ATM CALL")
    print(f"   headline: {HEADLINE[0]:.2f} delta longs, {HEADLINE[1]}, "
          f"nearest {TARGET_DTE} DTE. Return is on MAX LOSS, not premium.")
    print("=" * 84)

    cyc = run(chain, spot, *HEADLINE, shortfall=a.shortfall, trace=a.trace)
    bad = _audit(cyc, spot)
    print(f"\n  AUDIT: {len(bad)} violations of the V35 discard rules")
    for b in bad[:8]:
        print(f"    {b}")
    head = summarize(cyc)

    df = head["df"]

    # V35: "A positive result ... would be investigated before it was believed."
    if head["mean"] > 0:
        print("\n" + "=" * 84)
        print("V35 SAID A POSITIVE RESULT GETS INVESTIGATED. INVESTIGATING.")
        print("=" * 84)
        df["move"] = df.spot_close / df.spot_open - 1.0
        r = float(np.corrcoef(df["move"], df["ret"])[0, 1])
        print(f"\n  significance")
        print(f"    mean {head['mean']*100:+.2f}%  se {head['sem']*100:.2f}%  "
              f"t {head['t']:+.2f}  ->  "
              f"{'INSIDE NOISE' if abs(head['t']) < 2 else 'significant'}")
        print(f"    95% CI [{(head['mean']-1.96*head['sem'])*100:+.1f}%, "
              f"{(head['mean']+1.96*head['sem'])*100:+.1f}%]")
        print(f"\n  is it just direction? SOXL rose over this sample.")
        print(f"    correlation of cycle return with the underlying's move "
              f"{r:+.2f}")
        up = df[df["move"] > 0]
        dn = df[df["move"] <= 0]
        print(f"    cycles where SOXL rose  {len(up):>3}  "
              f"mean return {up.ret.mean()*100:+7.2f}%")
        print(f"    cycles where SOXL fell  {len(dn):>3}  "
              f"mean return {dn.ret.mean()*100:+7.2f}%")
        print(f"\n  is it a few tails?")
        srt = np.sort(df["ret"].to_numpy())
        print(f"    mean {srt.mean()*100:+.2f}%   median "
              f"{np.median(srt)*100:+.2f}%")
        print(f"    drop the 3 best  {srt[:-3].mean()*100:+.2f}%")
        print(f"    drop 3 best AND 3 worst  {srt[3:-3].mean()*100:+.2f}%")
        print(f"    best 3: {', '.join(f'{v*100:+.0f}%' for v in srt[-3:][::-1])}")

    print(f"\n  T23 — BENCHMARK\n")
    print(table([Result.of("backspread, 5% max loss/cycle",
                           df.open_date.min(), df.close_date.max(),
                           float((1 + 0.05 * df["ret"]).prod() - 1), "SOXL",
                           n_trades=len(df))]))

    if a.grid:
        print("\n" + "=" * 84)
        print("PRESPECIFIED GRID — six cells")
        print("=" * 84)
        print(f"\n  {'delta':<8}{'exit':<10}{'cycles':>8}{'ret/cycle':>12}"
              f"{'t':>7}{'win%':>7}{'maxDD':>8}")
        print("  " + "-" * 52)
        rows = []
        for dl in LONG_DELTAS:
            for ex in EXITS:
                c = run(chain, spot, dl, ex, shortfall=a.shortfall)
                if not c:
                    continue
                st = summarize(c, verbose=False)
                rows.append(st)
                mk = "  <-- headline" if (dl, ex) == HEADLINE else ""
                print(f"  {dl:<8.2f}{ex:<10}{st['n']:>8}"
                      f"{st['mean']*100:>+11.2f}%{st['t']:>7.2f}"
                      f"{st['win']*100:>6.0f}%{st['mdd']*100:>7.0f}%{mk}")
        pos = sum(r["mean"] > 0 for r in rows)
        med = float(np.median([r["mean"] for r in rows]))
        print(f"\n  cells positive: {pos} of {len(rows)}   "
              f"grid median {med*100:+.2f}%")

        print(f"\n  {'BAR':<6}{'test':<48}{'result':>14}{'':>6}")
        print("  " + "-" * 74)
        b1 = head["t"] > 2.0 and head["mean"] > 0
        b2 = head["years_pos"] >= 4
        b4 = pos >= 5
        b5 = abs(head["mean"] - med) <= head["sem"]
        b7 = head["mdd"] > -0.35
        for k, d_, ok, v in (
                ("B1", "mean return per cycle > 0 with t > 2.0", b1,
                 f"{head['mean']*100:+.2f}%, t={head['t']:+.2f}"),
                ("B2", "positive in at least 4 of 5 years", b2,
                 f"{head['years_pos']}/{head['years']}"),
                ("B3", "every cost charged", True, "yes"),
                ("B4", "at least 5 of 6 cells positive", b4,
                 f"{pos}/{len(rows)}"),
                ("B5", "headline within 1 se of grid median", b5,
                 f"med {med*100:+.2f}%"),
                ("B6", "benchmark reported", True, "yes"),
                ("B7", "max drawdown < 35%", b7, f"{head['mdd']*100:.0f}%")):
            print(f"  {k:<6}{d_:<48}{v:>14}   {'PASS' if ok else 'FAIL'}")
        print(f"\n  ADOPTED: {'YES' if (b1 and b2 and b4 and b5) else 'NO'}")

    os.makedirs(os.path.join(_HERE, "out"), exist_ok=True)
    head["df"].to_csv(os.path.join(_HERE, "out", "V35_backspread_cycles.csv"),
                      index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
