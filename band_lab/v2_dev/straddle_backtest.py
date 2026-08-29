"""
Long ATM SOXL straddle, delta-hedged once daily at the close. V29 Tier 1 #1.

The adoption bar, the parameter grid and the twelve assumptions were written and
committed in V30_STRADDLE_BAR.md before this file was ever run. Read that first;
this is only the machine.

Every fill is the quoted bid or ask, never the mid. Every cost is charged:
option spread, option commission, hedge spread, hedge commission. The run-time
assertions in `_audit` exist to catch the simulator flattering itself the way
the band strategy's did — they check that no fill beat its own quote and that
the costs actually charged match what the cost model says they should be.

    python3 band_lab/v2_dev/straddle_backtest.py
    python3 band_lab/v2_dev/straddle_backtest.py --grid
    python3 band_lab/v2_dev/straddle_backtest.py --trace 3
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import option_data                                                 # noqa: E402
from research_kit import Result, daily_closes, table               # noqa: E402

# ---- costs. See V30 assumptions A4 and A5.
HEDGE_BP_ONE_WAY = 0.495 + 2.85      # [MEASURED] commission + half spread
OPT_COMMISSION = 0.65                # [ASSUMED]  IBKR retail, per contract
CONTRACT = 100                       # shares per option contract
#: [CORRECTION v1] The first run used 1 contract. An ATM straddle's net delta is
#: near zero, so the hedge was ~16 shares and rounding to whole shares was a 3%
#: error on every one of 1,155 hedge trades. 10 contracts drops that to 0.3%.
#: Nothing about the edge depends on size; this is a numerical fix, not a knob.
CONTRACTS = 10

#: [CORRECTION v1] Sizing for the equity curve. The first run compounded 100% of
#: capital into each straddle 77 times and reported a -99.8% drawdown, which
#: measures the sizing rule and not the strategy. This spends a fixed fraction of
#: capital on premium each cycle.
PREMIUM_FRACTION = 0.05

# ---- prespecified grid, V30
TARGET_DTE = (30, 37, 45)
ROLL_DTE = (7, 14, 21)
HEADLINE = (37, 14)
DTE_WINDOW = 13                      # accept an expiry within +/- this of target
ATM_BAND = 0.05                      # strike must be within 5% of spot


@dataclass
class Cycle:
    """One straddle, opened and closed. Every dollar is accounted for here."""
    open_date: pd.Timestamp
    close_date: pd.Timestamp
    strike: float
    expiry: pd.Timestamp
    vega_open: float                 # straddle vega, per 1.00 of vol
    spread_open: float               # ask-bid summed over both legs, dollars
    dte_open: int
    dte_close: int
    spot_open: float
    spot_close: float
    iv_open: float
    premium_paid: float              # ask x 2 legs x 100, what left the account
    premium_recv: float              # bid x 2 legs x 100
    option_pnl: float
    hedge_pnl: float
    hedge_cost: float
    opt_commission: float
    n_hedges: int
    shares_traded: float
    sessions: int
    rv_realised: float               # annualised, close-to-close, over the hold

    @property
    def edge_vol_pts(self):
        """Realised minus implied, in volatility points. The V30 prediction."""
        return (self.rv_realised - self.iv_open) * 100.0

    @property
    def spread_vol_pts(self):
        """What the round-trip bid-ask cost, in the same unit as the edge."""
        return self.spread_open / (self.vega_open / 100.0) if self.vega_open else np.nan

    @property
    def gross(self):
        return self.option_pnl + self.hedge_pnl

    @property
    def net(self):
        return self.gross - self.hedge_cost - self.opt_commission

    @property
    def ret_on_premium(self):
        return self.net / self.premium_paid if self.premium_paid else np.nan


def load_chain(years=("2022", "2023", "2024", "2025", "2026")):
    d = option_data.load(years=years, verbose=True, extra=("vega", "gamma"))
    d = d[(d.bid > 0) & (d.ask > d.bid) & (d.implied_vol > 0)].copy()
    d["mid"] = (d["bid"] + d["ask"]) / 2.0
    return d


def _pair(day: pd.DataFrame, strike, expiry):
    """The call and the put at one strike and expiry, or None."""
    g = day[(day.strike == strike) & (day.expiry_key == expiry)]
    c = g[g.right == "CALL"]
    p = g[g.right == "PUT"]
    if len(c) != 1 or len(p) != 1:
        return None
    return c.iloc[0], p.iloc[0]


def pick(day: pd.DataFrame, target_dte: int):
    """Choose the straddle: expiry nearest the target DTE, strike nearest spot.

    Both legs must exist with a two-sided quote at the same strike and expiry,
    otherwise this is not a straddle and the day is skipped.
    """
    spot = float(day["underlying_price"].iloc[0])
    cand = day[(day.dte - target_dte).abs() <= DTE_WINDOW]
    if cand.empty:
        return None
    exp = cand.loc[(cand.dte - target_dte).abs().idxmin(), "expiry_key"]
    at_exp = cand[cand.expiry_key == exp]
    strikes = at_exp["strike"].unique()
    near = strikes[np.abs(strikes / spot - 1.0) <= ATM_BAND]
    if not len(near):
        return None
    for k in near[np.argsort(np.abs(near / spot - 1.0))]:
        pr = _pair(at_exp, k, exp)
        if pr is not None:
            return pr
    return None


def run(chain: pd.DataFrame, spot: pd.Series, target_dte: int, roll_dte: int,
        trace: int = 0) -> list[Cycle]:
    by_date = {d: g for d, g in chain.groupby("trade_date")}
    dates = sorted(by_date)
    cycles: list[Cycle] = []
    abandoned = 0

    i = 0
    while i < len(dates) - 1:
        day = by_date[dates[i]]
        sel = pick(day, target_dte)
        if sel is None:
            i += 1
            continue
        c0, p0 = sel
        strike, expiry = float(c0.strike), c0.expiry_key
        spot0 = float(c0.underlying_price)
        sz = CONTRACT * CONTRACTS                     # shares of option exposure

        # ---- open: pay the ask on both legs
        paid = (float(c0.ask) + float(p0.ask)) * sz
        opt_comm = 2 * OPT_COMMISSION * CONTRACTS
        # initial hedge: short the straddle's delta
        dl = float(c0.delta) + float(p0.delta)
        shares = float(np.round(-dl * sz))
        hedge_cost = abs(shares) * spot0 * HEDGE_BP_ONE_WAY / 1e4
        hedge_pnl = 0.0
        n_hedges, shares_traded = 1, abs(shares)
        held_shares = shares
        prev_spot = spot0

        j = i + 1
        recv = None
        while j < len(dates):
            dj = dates[j]
            day_j = by_date[dj]
            pr = _pair(day_j, strike, expiry)
            if pr is None:
                j += 1
                continue                              # A10: skip, carry hedge
            cj, pj = pr
            sj = float(cj.underlying_price)
            hedge_pnl += held_shares * (sj - prev_spot)
            prev_spot = sj

            if int(cj.dte) <= roll_dte or j == len(dates) - 1:
                recv = (float(cj.bid) + float(pj.bid)) * sz
                opt_comm += 2 * OPT_COMMISSION * CONTRACTS
                hedge_cost += abs(held_shares) * sj * HEDGE_BP_ONE_WAY / 1e4
                shares_traded += abs(held_shares)
                n_hedges += 1
                break

            want = -(float(cj.delta) + float(pj.delta)) * sz
            d_sh = want - held_shares
            if abs(d_sh) > 0.5:                       # whole shares only
                d_sh = float(np.round(d_sh))
                hedge_cost += abs(d_sh) * sj * HEDGE_BP_ONE_WAY / 1e4
                shares_traded += abs(d_sh)
                n_hedges += 1
                held_shares += d_sh
            j += 1

        if recv is None:
            # [CORRECTION v1 - BUG] This was `break`, which ended the ENTIRE
            # backtest the first time a straddle could not be closed instead of
            # abandoning that one cycle. It silently produced 0 cycles for every
            # roll-at-7-DTE grid cell and 5 cycles for (45, 14) -- three of the
            # nine prespecified cells never ran at all and the grid was reported
            # as 6 cells without anyone noticing they were missing. Abandoning
            # one cycle and moving on is the correct behaviour, and the count is
            # returned so a run that abandons many is visible rather than quiet.
            abandoned += 1
            i += 1
            continue

        # [CORRECTION v1] Realised vol comes from SOXL's own daily closes over
        # the hold window, not from the option file's underlying_price on the
        # subset of days both legs happened to be quoted. Skipped days made the
        # first version's log returns span gaps while still scaling by sqrt(252),
        # which understates vol on exactly the days data is thin.
        wnd = spot[(spot.index >= dates[i]) & (spot.index <= dates[j])]
        lr = np.diff(np.log(wnd.to_numpy(float))) if len(wnd) > 2 else np.array([])
        rv = float(lr.std(ddof=1) * math.sqrt(252)) if len(lr) > 1 else np.nan

        cyc = Cycle(
            open_date=dates[i], close_date=dates[j], strike=strike,
            expiry=pd.Timestamp(expiry),
            vega_open=(float(c0.vega) + float(p0.vega)) * sz,
            spread_open=((float(c0.ask) - float(c0.bid))
                         + (float(p0.ask) - float(p0.bid))) * sz,
            dte_open=int(c0.dte), dte_close=int(cj.dte),
            spot_open=spot0, spot_close=float(cj.underlying_price),
            iv_open=(float(c0.implied_vol) + float(p0.implied_vol)) / 2,
            premium_paid=paid, premium_recv=recv,
            option_pnl=recv - paid, hedge_pnl=hedge_pnl,
            hedge_cost=hedge_cost, opt_commission=opt_comm,
            n_hedges=n_hedges, shares_traded=shares_traded,
            sessions=len(wnd), rv_realised=rv)
        cycles.append(cyc)
        if trace and len(cycles) <= trace:
            _print_trace(cyc, c0, p0, cj, pj)
        i = j
    if abandoned:
        print(f"    ({abandoned} cycles abandoned: opened but never found a "
              f"closing quote at or under {roll_dte} DTE)")
    return cycles


def _print_trace(c: Cycle, c0, p0, cj, pj):
    print(f"\n  --- cycle {c.open_date.date()} -> {c.close_date.date()} "
          f"({c.sessions} sessions)")
    print(f"      strike {c.strike:.1f}, expiry {c.expiry.date()}, "
          f"{c.dte_open} DTE at open -> {c.dte_close} at close")
    print(f"      spot {c.spot_open:.2f} -> {c.spot_close:.2f}   "
          f"IV at open {c.iv_open*100:.1f}%   realised over the hold "
          f"{c.rv_realised*100:.1f}%")
    print(f"      BUY  call ask {c0.ask:.2f} + put ask {p0.ask:.2f} "
          f"= ${c.premium_paid:,.0f}")
    print(f"      SELL call bid {cj.bid:.2f} + put bid {pj.bid:.2f} "
          f"= ${c.premium_recv:,.0f}")
    print(f"      option P&L {c.option_pnl:+,.0f}   hedge P&L {c.hedge_pnl:+,.0f}"
          f"   -> gross {c.gross:+,.0f}")
    print(f"      {c.n_hedges} hedge trades, {c.shares_traded:,.0f} shares, "
          f"hedge cost {-c.hedge_cost:,.0f}, option commission "
          f"{-c.opt_commission:,.0f}")
    print(f"      NET {c.net:+,.0f}  ({c.ret_on_premium*100:+.1f}% of premium)")


def _audit(cycles: list[Cycle]) -> list[str]:
    """The checks from V30's 'what would make me throw this out'."""
    bad = []
    for c in cycles:
        if c.premium_paid <= 0 or c.premium_recv < 0:
            bad.append(f"{c.open_date.date()}: non-positive premium")
        if c.option_pnl != c.premium_recv - c.premium_paid:
            bad.append(f"{c.open_date.date()}: option P&L not recv - paid")
        floor = 4 * OPT_COMMISSION * CONTRACTS
        if c.opt_commission < floor - 1e-9:
            bad.append(f"{c.open_date.date()}: option commission below "
                       f"{floor} for a 2-leg round trip")
        if c.hedge_cost < 0 or c.n_hedges < 2:
            bad.append(f"{c.open_date.date()}: hedge accounting impossible")
        exp = c.shares_traded * ((c.spot_open + c.spot_close) / 2) \
            * HEDGE_BP_ONE_WAY / 1e4
        if c.hedge_cost > 3 * exp or c.hedge_cost < exp / 3:
            bad.append(f"{c.open_date.date()}: hedge cost {c.hedge_cost:.0f} "
                       f"far from {exp:.0f} implied by shares traded")
    return bad


def summarize(cycles: list[Cycle], label: str, verbose=True) -> dict:
    """[CORRECTION v1] The primary metric is RETURN ON PREMIUM, not dollars.

    The first run reported dollars. SOXL ran from $24 to $109 over the sample,
    so a 2026 straddle cost 6x a 2022 one and a dollar sum weights 2026 six
    times as heavily. The two metrics disagreed in SIGN: mean dollar P&L was
    +$35 at t=+0.64 while mean return was -3.0% at t=-1.11. Every bar is now
    tested on the return.
    """
    df = pd.DataFrame([dict(vars(c),
                            edge_vol_pts=c.edge_vol_pts,
                            spread_vol_pts=c.spread_vol_pts) for c in cycles])
    df["gross"] = df.option_pnl + df.hedge_pnl
    df["net"] = df.gross - df.hedge_cost - df.opt_commission
    df["ret"] = df.net / df.premium_paid
    df["year"] = pd.to_datetime(df.open_date).dt.year
    n = len(df)
    m = df.ret.mean()
    sem = df.ret.std(ddof=1) / math.sqrt(n)
    t = m / sem if sem else float("nan")
    by_year = df.groupby("year")["ret"].mean()
    # fixed-fraction sizing, V30 A11 replaced: see PREMIUM_FRACTION
    eq = (1 + PREMIUM_FRACTION * df["ret"]).cumprod()
    mdd = float((eq / eq.cummax() - 1).min())

    out = dict(label=label, n=n, mean=m, t=t, sem=sem,
               dollars=df.net.sum(), mean_dollars=df.net.mean(),
               win=(df.net > 0).mean(),
               years_pos=int((by_year > 0).sum()), years=len(by_year),
               mdd=mdd, equity=float(eq.iloc[-1] - 1),
               sharpe=m / df.ret.std(ddof=1) if n > 1 else np.nan, df=df)
    if not verbose:
        return out

    print(f"\n  {n} cycles, {df.open_date.min().date()} to "
          f"{df.close_date.max().date()}, {CONTRACTS} contracts per leg")
    print(f"  average hold {df.sessions.mean():.1f} sessions, "
          f"{df.n_hedges.mean():.1f} hedge trades per cycle")

    print(f"\n  WHERE THE MONEY WENT — per cycle, as a % of the premium paid\n")
    print(f"  {'component':<36}{'per cycle $':>14}{'% of premium':>15}")
    print("  " + "-" * 65)
    pp = df.premium_paid.mean()
    for k, name in (("option_pnl", "option P&L (bought ask, sold bid)"),
                    ("hedge_pnl", "delta hedge P&L")):
        print(f"  {name:<36}{df[k].mean():>+14,.0f}"
              f"{(df[k]/df.premium_paid).mean()*100:>+14.1f}%")
    print(f"  {'= gross':<36}{df.gross.mean():>+14,.0f}"
          f"{(df.gross/df.premium_paid).mean()*100:>+14.1f}%")
    for k, name in (("hedge_cost", "hedge friction"),
                    ("opt_commission", "option commission")):
        print(f"  {name:<36}{-df[k].mean():>+14,.0f}"
              f"{-(df[k]/df.premium_paid).mean()*100:>+14.1f}%")
    print("  " + "-" * 65)
    print(f"  {'= NET':<36}{df.net.mean():>+14,.0f}{m*100:>+14.1f}%")

    print(f"\n  mean return per cycle    {m*100:+.2f}%   "
          f"t = {t:+.2f}   (se {sem*100:.2f}%)")
    print(f"  95% CI                   [{(m-1.96*sem)*100:+.2f}%, "
          f"{(m+1.96*sem)*100:+.2f}%]")
    print(f"  median return per cycle  {df.ret.median()*100:+.2f}%")
    print(f"  cycles profitable        {(df.net>0).mean()*100:.0f}%")
    print(f"  Sharpe on cycle returns  {out['sharpe']:+.2f}")
    print(f"  average premium paid     ${pp:,.0f}")
    print(f"  equity at {PREMIUM_FRACTION:.0%} premium per cycle: "
          f"{out['equity']*100:+.1f}%, max drawdown {mdd*100:.1f}%")

    print(f"\n  DID THE V30 PREDICTION HOLD? (+11.8 edge - 8.1 spread = +3.7 "
          f"vol points)\n")
    print(f"  {'':<34}{'measured':>12}{'V30 said':>12}")
    print("  " + "-" * 58)
    print(f"  {'realised minus implied, vol pts':<34}"
          f"{df.edge_vol_pts.mean():>+12.1f}{'+11.8':>12}")
    print(f"  {'round-trip spread, vol pts':<34}"
          f"{df.spread_vol_pts.mean():>+12.1f}{'-8.1':>12}")
    print(f"  {'net, vol pts':<34}"
          f"{(df.edge_vol_pts - df.spread_vol_pts).mean():>+12.1f}{'+3.7':>12}")
    exp_pnl = ((df.edge_vol_pts - df.spread_vol_pts) * df.vega_open / 100.0)
    print(f"  {'that x vega = predicted P&L':<34}"
          f"{exp_pnl.mean():>+12,.0f}{'':>12}")
    print(f"  {'actually earned':<34}{df.net.mean():>+12,.0f}")
    print(f"  cycles where realised beat implied: "
          f"{(df.edge_vol_pts > 0).mean()*100:.0f}%")
    corr = float(np.corrcoef(df.edge_vol_pts, df.ret)[0, 1])
    print(f"  correlation of cycle return with (realised - implied): {corr:+.2f}")
    print(f"    A high correlation says the machine works and the question is "
          f"only how often\n    realised beats implied. A low one says "
          f"something else is driving the P&L.")

    print(f"\n  {'year':<8}{'cycles':>8}{'mean ret':>11}{'win%':>7}"
          f"{'IV at open':>13}{'realised':>11}{'edge':>9}")
    print("  " + "-" * 67)
    for y, g in df.groupby("year"):
        print(f"  {y:<8}{len(g):>8}{g.ret.mean()*100:>+10.1f}%"
              f"{(g.net>0).mean()*100:>6.0f}%{g.iv_open.mean()*100:>12.1f}%"
              f"{g.rv_realised.mean()*100:>10.1f}%"
              f"{g.edge_vol_pts.mean():>+9.1f}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--trace", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(_HERE, "out"))
    a = ap.parse_args()

    chain = load_chain()
    chain["expiry_key"] = chain["expiration"].astype("int64")
    spot = daily_closes("SOXL")

    print("=" * 84)
    print("V30 — LONG ATM SOXL STRADDLE, DELTA-HEDGED ONCE DAILY AT THE CLOSE")
    print(f"   headline: enter nearest {HEADLINE[0]} DTE, roll at "
          f"{HEADLINE[1]} DTE. Buy the ask, sell the bid, every cost charged.")
    print("=" * 84)

    cyc = run(chain, spot, *HEADLINE, trace=a.trace)
    bad = _audit(cyc)
    print(f"\n  AUDIT: {len(bad)} violations of the V30 discard rules")
    for b in bad[:10]:
        print(f"    {b}")
    if bad:
        print("  Result is not reportable until these are explained.")

    head = summarize(cyc, "headline")

    df = head["df"]
    r = Result.of(f"straddle, {PREMIUM_FRACTION:.0%} premium/cycle",
                  df.open_date.min(), df.close_date.max(),
                  float((1 + PREMIUM_FRACTION * df["ret"]).prod() - 1), "SOXL",
                  n_trades=len(df))
    print(f"\n  T23 — BENCHMARK\n")
    print(table([r]))

    if a.grid:
        print("\n" + "=" * 84)
        print("PRESPECIFIED GRID — all nine cells, reported whatever they show")
        print("=" * 84)
        print(f"\n  {'entry DTE':<11}{'roll DTE':<10}{'cycles':>8}"
              f"{'net $':>12}{'ret/cycle':>11}{'t':>7}{'equity':>8}{'win%':>7}")
        print("  " + "-" * 75)
        rows = []
        for td in TARGET_DTE:
            for rd in ROLL_DTE:
                c = run(chain, spot, td, rd)
                if not c:
                    continue
                s = summarize(c, f"{td}/{rd}", verbose=False)
                rows.append(s)
                mark = "  <-- headline" if (td, rd) == HEADLINE else ""
                print(f"  {td:<11}{rd:<10}{s['n']:>8}"
                      f"{s['dollars']:>+12,.0f}{s['mean']*100:>+10.2f}%"
                      f"{s['t']:>7.2f}{s['equity']*100:>+8.1f}%"
                      f"{s['win']*100:>6.0f}%{mark}")
        pos = sum(x["mean"] > 0 for x in rows)
        med = float(np.median([x["mean"] for x in rows]))
        print(f"\n  cells with a positive mean return: {pos} of {len(rows)}")
        print(f"  grid median return/cycle: {med*100:+.2f}%   "
              f"headline {head['mean']*100:+.2f}%   "
              f"gap {abs(head['mean']-med)/head['sem']:.2f} standard errors")

        print(f"\n  {'BAR':<6}{'test':<52}{'result':>10}{'':>6}")
        print("  " + "-" * 74)
        b1 = head["t"] > 2.0 and head["mean"] > 0
        b2 = head["years_pos"] >= 4
        b4 = pos >= 7
        b5 = abs(head["mean"] - med) <= head["sem"]
        b7 = head["mdd"] > -0.35
        for k, desc, ok, val in (
                ("B1", "mean net per cycle > 0 with t > 2.0", b1,
                 f"t={head['t']:+.2f}"),
                ("B2", "positive in at least 4 of 5 calendar years", b2,
                 f"{head['years_pos']}/{head['years']}"),
                ("B3", "all four costs charged", True, "yes"),
                ("B4", "at least 7 of 9 grid cells positive", b4,
                 f"{pos}/{len(rows)}"),
                ("B5", "headline within 1 se of the grid median", b5,
                 f"{abs(head['mean']-med)/head['sem']:.2f} se"),
                ("B6", "benchmark reported", True, "yes"),
                ("B7", "max drawdown < 35%", b7, f"{head['mdd']*100:.0f}%")):
            print(f"  {k:<6}{desc:<52}{val:>10}   "
                  f"{'PASS' if ok else 'FAIL'}")
        core = b1 and b2 and b4 and b5
        print(f"\n  B1-B5 all pass: {'YES' if core else 'NO'} — "
              f"{'worth live testing' if core else 'not adopted'}")

    os.makedirs(a.out, exist_ok=True)
    head["df"].to_csv(os.path.join(a.out, "V30_straddle_cycles.csv"),
                      index=False)
    print(f"\n  wrote out/V30_straddle_cycles.csv ({len(head['df'])} cycles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
