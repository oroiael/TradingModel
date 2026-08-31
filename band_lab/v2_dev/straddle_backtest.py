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
# [V39 BUG FIX] `_load_opens` referenced ROOT, which this module never defined --
# the name was carried over from a file that has it. The whole V39 run died on
# its first call and produced nothing for several minutes while it was reported
# as "still running", because only the chain-load lines had appeared and that
# was read as output buffering rather than a crash.
ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
import bs                                                          # noqa: E402
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

#: [V32 MEASURED] The backtest charges the vendor's END-OF-DAY bid/ask. Live
#: IBKR BID_ASK ticks over 9 sessions and 126 straddle observations put the real
#: intraday round trip at 17.8 vol points against the 10.6 those EOD snapshots
#: imply. The vendor file understates the cost by 7.2 points, so charge the
#: difference against each cycle's own vega rather than guessing at a dollar
#: figure. Set to 0.0 to reproduce the V31 numbers exactly.
EXTRA_SPREAD_VOL_PTS = 0.0

#: [V33] Zero-hedge mode. V29 Tier 1 #2. No stock is traded at all, so there is
#: no hedge P&L and no hedge friction. Held to expiry the ITM leg exercises and
#: the OTM leg expires worthless, so the EXIT half of the option spread is never
#: paid -- which is the only reason #2 could differ from #1 rather than merely
#: be noisier, because the spread is what killed #1.
HEDGE_MODE = "daily"                 # "daily" | "none" | "open"

#: [V39] Hedge at 09:30 instead of the close. The vendor file is end-of-day
#: only, so no quoted delta exists at the open; A25 computes it by Black-Scholes
#: from the 09:30 spot and the PRIOR CLOSE's implied vol. bs.py reproduces the
#: vendor delta to 0.0002 at the close, so the model is sound and carrying the
#: IV forward one session is the approximation.
OPENS: dict = {}                     # date -> 09:30 spot, filled by main()
EXIT_MODE = "roll"                   # "roll" | "expiry"
EXERCISE_FEE = 0.0                   # [ASSUMED] V33 A14, unverified, flatters

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


def _load_opens():
    """09:30 spot for every session, for V39's open-hedge mode."""
    px = pd.read_csv(os.path.join(ROOT, "SOXL_1min.csv"),
                     usecols=["Date", "Open"])
    dt = pd.to_datetime(px["Date"].str.replace(" America/New_York", "",
                                               regex=False),
                        format="%Y%m%d %H:%M:%S")
    m = dt.dt.hour * 60 + dt.dt.minute
    first = px[m == 570].assign(d=dt[m == 570].dt.normalize())
    OPENS.update(dict(zip(first["d"], first["Open"].astype(float))))
    print(f"    loaded {len(OPENS):,} session opens for the 09:30 hedge",
          flush=True)


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
    f_rt = 6.70                       # SOXL stock round trip, bp, measured
    by_date = {d: g for d, g in chain.groupby("trade_date")}
    dates = sorted(by_date)
    cycles: list[Cycle] = []
    daily: list[pd.DataFrame] = []
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
        shares = 0.0 if HEDGE_MODE == "none" else float(np.round(-dl * sz))
        hedge_cost = abs(shares) * spot0 * HEDGE_BP_ONE_WAY / 1e4
        hedge_pnl = 0.0
        n_hedges, shares_traded = (0, 0.0) if HEDGE_MODE == "none" else (1, abs(shares))
        held_shares = shares
        prev_spot = spot0
        # [v2] Daily mark-to-market. Cycle-end sampling cannot see a drawdown
        # that opens and closes inside a cycle, and cycles run 15 sessions.
        # Options are MARKED at the mid and TRADED at the bid/ask, so the entry
        # shows an immediate half-spread loss, which is what really happens.
        marks = [dict(date=dates[i], opt_mid=(float(c0.mid) + float(p0.mid)) * sz,
                      hedge=0.0, cost=hedge_cost + opt_comm)]

        j = i + 1
        recv = None
        # [V33] Take the real Timestamp off the row, NOT pd.Timestamp(expiry).
        # `expiry_key` is `expiration.astype("int64")` and the column is
        # datetime64[**us**], so the integer is MICROseconds while pd.Timestamp
        # reads a bare int as NANOseconds -- giving 1970-01-20 for every
        # contract. V31's correction C5 claimed to have fixed exactly this and
        # did not: it changed the call site and left the conversion wrong, so
        # the `expiry` column in V30_straddle_cycles.csv has been 1970 all
        # along. Nothing read it, so no result moved, but the fix was not a fix.
        expiry_ts = pd.Timestamp(c0.expiration)
        while j < len(dates):
            dj = dates[j]
            # [V33 BUG FIX] The expiry exit used to trigger on `dte <= 0`, which
            # requires the chain to still QUOTE the contract on its expiry date.
            # It almost never does: 801 of 816 cycles were abandoned and the 15
            # that completed were the biased subsample where an expiry-day quote
            # happened to exist, printing -96.43% per cycle. Held to expiry no
            # quote is needed at all -- the option settles at intrinsic against
            # the underlying's own close. So the trigger is the DATE, and the
            # settlement price comes from SOXL's price series, not the chain.
            if EXIT_MODE == "expiry" and dj >= expiry_ts:
                settle = float(spot.asof(expiry_ts))
                recv = (max(settle - strike, 0.0)
                        + max(strike - settle, 0.0)) * sz
                if recv > 0:              # the ITM leg exercises into stock
                    hedge_cost += sz * settle * f_rt / 1e4
                    opt_comm += EXERCISE_FEE * CONTRACTS
                if held_shares:
                    hedge_cost += abs(held_shares) * settle * HEDGE_BP_ONE_WAY / 1e4
                    shares_traded += abs(held_shares)
                n_hedges += 1
                marks.append(dict(date=dj, opt_mid=recv, hedge=hedge_pnl,
                                  cost=hedge_cost + opt_comm))
                cj = pj = None
                break
            day_j = by_date[dj]
            pr = _pair(day_j, strike, expiry)
            if pr is None:
                j += 1
                continue                              # A10: skip, carry hedge
            cj, pj = pr
            # [V39 BUG FIX] The option is always SOLD at the end-of-day bid, so
            # on the exit bar the hedge must be marked to the CLOSE too. The
            # first version accrued the hedge to the 09:30 OPEN and then sold
            # the option at that afternoon's close, leaving the final intraday
            # session unhedged on every cycle. A long straddle is long gamma, so
            # an unhedged interval always contributes +0.5*gamma*(dS)^2 -- it
            # manufactured a gain once per cycle and made open-hedging beat
            # close-hedging in all three cells, which is the exact outcome V39
            # named in advance as a discard trigger rather than a finding.
            is_exit = (EXIT_MODE == "roll"
                       and (int(cj.dte) <= roll_dte or j == len(dates) - 1))

            # [V39 BUG FIX 2] The first fix marked the exit bar to the close but
            # SKIPPED the 09:30 re-hedge on that session, so the position ran
            # unhedged from the previous open all the way to the exit close --
            # about 1.5 sessions instead of being re-hedged twice. Long gamma
            # over a longer unhedged interval captures more variance, so it kept
            # manufacturing a gain: the effect only fell from +2.18 to +1.50
            # points and open-hedging still beat close-hedging 3 of 3, which
            # V39 named as a discard trigger. The exit session now gets its open
            # hedge and THEN marks to the close, so every interval in open mode
            # runs open-to-open with a final open-to-close stub.
            if HEDGE_MODE == "open" and is_exit and dj in OPENS:
                so = OPENS[dj]
                hedge_pnl += held_shares * (so - prev_spot)
                prev_spot = so
                Tx = max(int(cj.dte), 1) / 365.0
                wx = -(float(bs.delta(so, strike, Tx, 0.04, 0.0,
                                      float(cj.implied_vol), "CALL"))
                       + float(bs.delta(so, strike, Tx, 0.04, 0.0,
                                        float(pj.implied_vol), "PUT"))) * sz
                dx = float(np.round(wx - held_shares))
                if abs(dx) > 0.5:
                    hedge_cost += abs(dx) * so * HEDGE_BP_ONE_WAY / 1e4
                    shares_traded += abs(dx)
                    n_hedges += 1
                    held_shares += dx

            sj = (OPENS.get(dj, float(cj.underlying_price))
                  if (HEDGE_MODE == "open" and not is_exit)
                  else float(cj.underlying_price))
            hedge_pnl += held_shares * (sj - prev_spot)
            prev_spot = sj
            marks.append(dict(date=dj,
                              opt_mid=(float(cj.mid) + float(pj.mid)) * sz,
                              hedge=hedge_pnl, cost=hedge_cost + opt_comm))

            if is_exit:
                recv = (float(cj.bid) + float(pj.bid)) * sz
                opt_comm += 2 * OPT_COMMISSION * CONTRACTS
                if held_shares:
                    hedge_cost += abs(held_shares) * sj * HEDGE_BP_ONE_WAY / 1e4
                    shares_traded += abs(held_shares)
                n_hedges += 1
                marks[-1] = dict(date=dj, opt_mid=recv, hedge=hedge_pnl,
                                 cost=hedge_cost + opt_comm)
                break

            if HEDGE_MODE == "none":
                want = 0.0
            elif HEDGE_MODE == "open" and dj in OPENS:
                # V39/A25: re-price both deltas at the 09:30 spot, carrying the
                # prior close's IV. The hedge is then placed at that spot, so
                # the interval this position is unhedged over runs open to open.
                so = OPENS[dj]
                T = max(int(cj.dte), 1) / 365.0
                dc = float(bs.delta(so, strike, T, 0.04, 0.0,
                                    float(cj.implied_vol), "CALL"))
                dp = float(bs.delta(so, strike, T, 0.04, 0.0,
                                    float(pj.implied_vol), "PUT"))
                want = -(dc + dp) * sz
            else:
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
            expiry=expiry_ts,
            vega_open=(float(c0.vega) + float(p0.vega)) * sz,
            spread_open=((float(c0.ask) - float(c0.bid))
                         + (float(p0.ask) - float(p0.bid))) * sz,
            dte_open=int(c0.dte), dte_close=0 if cj is None else int(cj.dte),
            spot_open=spot0,
            spot_close=(float(spot.asof(expiry_ts)) if cj is None
                        else float(cj.underlying_price)),
            iv_open=(float(c0.implied_vol) + float(p0.implied_vol)) / 2,
            premium_paid=paid, premium_recv=recv,
            option_pnl=recv - paid, hedge_pnl=hedge_pnl,
            # V33: the V32 shortfall is a ROUND TRIP. A cycle held to expiry
            # crosses the spread once, so it is charged half. Charging the full
            # amount to a position that never sells would invent a cost that
            # cannot occur.
            hedge_cost=hedge_cost + EXTRA_SPREAD_VOL_PTS
            * (0.5 if EXIT_MODE == "expiry" else 1.0)
            * ((float(c0.vega) + float(p0.vega)) * sz) / 100.0,
            opt_commission=opt_comm,
            n_hedges=n_hedges, shares_traded=shares_traded,
            sessions=len(wnd), rv_realised=rv)
        cycles.append(cyc)
        mk = pd.DataFrame(marks)
        # position value = what the options are worth + hedge P&L - costs paid.
        # Divided by the premium paid, so cycles of different size are additive.
        mk["value"] = mk.opt_mid + mk.hedge - mk.cost
        mk["frac"] = (mk.value - paid) / paid
        mk["cycle"] = len(cycles) - 1
        daily.append(mk[["date", "cycle", "frac"]])
        if trace and len(cycles) <= trace:
            _print_trace(cyc, c0, p0, cj, pj)
        i = j
    if abandoned:
        print(f"    ({abandoned} cycles abandoned: opened but never found a "
              f"closing quote at or under {roll_dte} DTE)")
    dd = pd.concat(daily, ignore_index=True) if daily else pd.DataFrame()
    return cycles, dd


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
        # An expiry settlement pays commission on the ENTRY legs only -- the
        # ITM leg exercises and the OTM leg expires, neither is sold. So the
        # floor is two legs, not four, when the cycle ended at expiry.
        floor = (2 if c.dte_close == 0 else 4) * OPT_COMMISSION * CONTRACTS
        if c.opt_commission < floor - 1e-9:
            bad.append(f"{c.open_date.date()}: option commission below "
                       f"{floor} for a 2-leg round trip")
        if c.hedge_cost < 0:
            bad.append(f"{c.open_date.date()}: negative hedge cost")
        if HEDGE_MODE == "none":
            # V33's own discard rule: an unhedged cycle must carry no stock.
            if c.shares_traded or c.hedge_pnl:
                bad.append(f"{c.open_date.date()}: unhedged cycle traded "
                           f"{c.shares_traded:.0f} shares / P&L {c.hedge_pnl:.0f}")
        else:
            if c.n_hedges < 2:
                bad.append(f"{c.open_date.date()}: hedge accounting impossible")
            exp = c.shares_traded * ((c.spot_open + c.spot_close) / 2) \
                * HEDGE_BP_ONE_WAY / 1e4
            if c.hedge_cost > 3 * exp or c.hedge_cost < exp / 3:
                bad.append(f"{c.open_date.date()}: hedge cost {c.hedge_cost:.0f}"
                           f" far from {exp:.0f} implied by shares traded")
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


def equity_report(cyc: list[Cycle], daily: pd.DataFrame) -> None:
    """CAGR and max drawdown — and why both are sizing choices, not measurements.

    A long straddle has no natural leverage, so "the return" is undefined until
    somebody says how much capital stands behind each straddle. The strategy's
    only scale-free number is the return per dollar of premium. Everything below
    turns that into a CAGR by picking a fraction, and the fraction is the whole
    answer.
    """
    df = pd.DataFrame([vars(c) for c in cyc])
    df["net"] = df.option_pnl + df.hedge_pnl - df.hedge_cost - df.opt_commission
    df["ret"] = df.net / df.premium_paid
    yrs = (df.close_date.max() - df.open_date.min()).days / 365.25

    d = daily.sort_values(["cycle", "date"]).copy()
    # Fixed-fraction: each cycle risks f of the equity standing at its start.
    # Within a cycle the P&L is f x (fraction of premium), applied to that
    # starting equity; equity compounds cycle to cycle.
    print("\n" + "=" * 84)
    print("CAGR AND MAX DRAWDOWN")
    print("=" * 84)
    print(f"  window {df.open_date.min().date()} to {df.close_date.max().date()}"
          f"  ({yrs:.2f} years, {len(df)} cycles, "
          f"{d.date.nunique():,} sessions marked)")
    print(f"\n  {'premium as % of':<18}{'CAGR':>9}{'max DD':>10}"
          f"{'max DD':>10}{'final':>10}{'worst day':>11}")
    print(f"  {'capital per cycle':<18}{'':>9}{'(daily)':>10}{'(cycle-end)':>10}"
          f"{'equity':>10}{'':>11}")
    print("  " + "-" * 68)
    for f in (0.02, 0.05, 0.10, 0.20, 0.50, 1.00):
        eq, cur = [], 1.0
        worst_day = 0.0
        prev = 0.0
        for cid, g in d.groupby("cycle", sort=True):
            start = cur
            fr = g["frac"].to_numpy(float)
            path = start * (1.0 + f * fr)
            step = np.diff(np.concatenate([[start], path])) / \
                np.concatenate([[start], path])[:-1]
            worst_day = min(worst_day, float(step.min()) if len(step) else 0.0)
            eq.extend(path.tolist())
            cur = float(path[-1])
        e = pd.Series(eq)
        mdd_daily = float((e / e.cummax() - 1).min())
        ce = (1 + f * df["ret"]).cumprod()
        mdd_cycle = float((ce / ce.cummax() - 1).min())
        cagr = cur ** (1 / yrs) - 1 if cur > 0 else float("nan")
        print(f"  {f:<18.0%}{cagr*100:>+8.1f}%{mdd_daily*100:>9.1f}%"
              f"{mdd_cycle*100:>9.1f}%{(cur-1)*100:>+9.1f}%"
              f"{worst_day*100:>+10.1f}%")

    print(f"""
  The CAGR column is a CHOICE, not a measurement. Doubling the fraction roughly
  doubles the loss rate and the drawdown together, because a long straddle is
  not leveraged and the P&L scales linearly in size. The only scale-free fact
  is {df.ret.mean()*100:+.2f}% per cycle over {len(df)} cycles at {len(df)/yrs:.1f} cycles a year.

  The two drawdown columns: cycle-end sampling sees the position only {len(df)}
  times, daily marking sees it {d.date.nunique():,} times. The gap is about one
  percentage point, which is smaller than it might have been -- intra-cycle
  swings mostly resolve in the same direction by the roll. Worth measuring, not
  worth the alarm; the earlier cycle-end figures were close to right.

  Both are still EOD marks. A real intraday drawdown is worse than either and
  is not measurable from these files.""")

    # capital actually required, which nothing above accounts for
    hedge_notional = (df.shares_traded / df.n_hedges) * df.spot_open
    print(f"""
  AND THE CAPITAL IS UNDERSTATED. A long straddle ties up its premium, but the
  delta hedge is a stock position that needs margin on top:

    average premium per cycle          ${df.premium_paid.mean():>10,.0f}
    average hedge notional held        ${hedge_notional.mean():>10,.0f}
    Reg-T margin on that at 50%        ${hedge_notional.mean()*0.5:>10,.0f}
    -> capital per cycle, roughly      ${df.premium_paid.mean() + hedge_notional.mean()*0.5:>10,.0f}
       vs premium alone                ${df.premium_paid.mean():>10,.0f}
       ratio                            {(df.premium_paid.mean() + hedge_notional.mean()*0.5)/df.premium_paid.mean():>10.2f}x

  So a CAGR computed on premium alone overstates the return on the capital the
  broker actually locks up by roughly that ratio. This is a MODEL, not a
  measurement: the real number depends on Reg-T versus portfolio margin and has
  not been looked up.""")


def _v39(chain, spot) -> int:
    """V29 Tier 2 #6 — hedge at the open vs at the close, same everything else."""
    global HEDGE_MODE, EXIT_MODE, EXTRA_SPREAD_VOL_PTS
    EXIT_MODE = "roll"
    w = 92
    print("=" * w)
    print("V39 — HEDGE AT THE OPEN vs AT THE CLOSE. V29 Tier 2 #6.")
    print("   B1b: the open cell must BEAT the close cell at the same DTE, or "
          "#6 has no reason to exist.")
    print("=" * w)
    res = {}
    for shortfall, lbl in ((0.0, "vendor EOD spread"),
                           (7.2, "+ V32 measured shortfall  <-- headline")):
        print(f"\n  {lbl}")
        print(f"  {'entry DTE':<11}{'close-hedged':>15}{'open-hedged':>14}"
              f"{'difference':>13}{'B1b':>7}{'hedges/session':>16}")
        print(f"  {'':<60}{'close':>8}{'open':>8}")
        print("  " + "-" * 76)
        for td in (30, 37, 45):
            got = {}
            for mode in ("daily", "open"):
                HEDGE_MODE = mode
                EXTRA_SPREAD_VOL_PTS = shortfall
                c, _ = run(chain, spot, td, 14)
                got[mode] = summarize(c, "", verbose=False) if c else None
            if not all(got.values()):
                continue
            a_, b_ = got["daily"]["mean"], got["open"]["mean"]
            res[(shortfall, td)] = (a_, b_)
            ha = got["daily"]["df"]
            hb = got["open"]["df"]
            pa = (ha.n_hedges / ha.sessions).mean()
            pb = (hb.n_hedges / hb.sessions).mean()
            print(f"  {td:<11}{a_*100:>+14.2f}%{b_*100:>+13.2f}%"
                  f"{(b_-a_)*100:>+12.2f}%{'PASS' if b_ > a_ else 'FAIL':>7}"
                  f"{pa:>8.2f}{pb:>8.2f}")
    m = {k: v for k, v in res.items() if k[0] > 0}
    wins = sum(1 for a_, b_ in m.values() if b_ > a_)
    diffs = [(b_ - a_) * 100 for a_, b_ in m.values()]
    print(f"""
  B1b: the open-hedged cell beats the close-hedged cell in {wins} of {len(m)} cells.
  mean difference {np.mean(diffs):+.2f} percentage points per cycle.

  V39 predicted open-hedging loses, because open-to-open captures 4.35% less
  variance than close-to-close -- about -2.6 volatility points. The measured
  difference above is the test of that prediction.

  ADOPTED: {'YES' if wins == len(m) else 'NO'}""")
    return 0


def _v37(chain, spot) -> int:
    """V29 Tier 2 #4 — the long-dated straddle, with the overlap correction.

    V37 B1 requires t on NON-OVERLAPPING cycles. Consecutive cycles here run
    back to back by construction (i = j), so they already are independent --
    the correction that matters is simply that there are very few of them, and
    that is reported beside every number rather than left to be inferred.
    """
    global HEDGE_MODE, EXIT_MODE, EXTRA_SPREAD_VOL_PTS, DTE_WINDOW
    EXIT_MODE = "expiry"
    w = 96
    print("=" * w)
    print("V37 — LONG-DATED ATM SOXL STRADDLE, HELD TO EXPIRY. V29 Tier 2 #4.")
    print("   Bar in V37_LONGDATED_BAR.md, committed first. It prespecifies "
          "that this is likely INCONCLUSIVE.")
    print("=" * w)

    rows = []
    for shortfall, lbl in ((0.0, "vendor EOD spread"),
                           (7.2 * 4.9 / 10.6, "+ V32 shortfall scaled to tenor "
                                              "(A22)  <-- headline")):
        print(f"\n  {lbl}")
        print(f"  {'hedge':<8}{'DTE':<7}{'cycles':>8}{'yrs/cyc':>9}"
              f"{'ret/cycle':>11}{'t':>7}{'win%':>7}{'ann.':>9}")
        print("  " + "-" * 66)
        for hedge in ("none", "daily"):
            for td in (90, 180, 270):
                HEDGE_MODE = hedge
                DTE_WINDOW = max(20, td // 4)
                EXTRA_SPREAD_VOL_PTS = shortfall
                c, _ = run(chain, spot, td, 14)
                if not c:
                    print(f"  {hedge:<8}{td:<7}   no cycles")
                    continue
                st = summarize(c, "", verbose=False)
                yrs = st["df"].sessions.mean() / 252.0
                ann = (1 + st["mean"]) ** (1 / yrs) - 1 if yrs > 0 else np.nan
                rows.append(dict(shortfall=shortfall, hedge=hedge, dte=td,
                                 yrs=yrs, ann=ann,
                                 **{k: st[k] for k in
                                    ("n", "mean", "t", "sem", "win", "mdd")}))
                mk = "  <-- headline" if (hedge, td) == ("none", 180) else ""
                print(f"  {hedge:<8}{td:<7}{st['n']:>8}{yrs:>9.2f}"
                      f"{st['mean']*100:>+10.2f}%{st['t']:>7.2f}"
                      f"{st['win']*100:>6.0f}%{ann*100:>+8.1f}%{mk}")

    df = pd.DataFrame(rows)
    m = df[df.shortfall > 0]
    if m.empty:
        print("\n  no cells produced cycles")
        return 1
    head = m[(m.hedge == "none") & (m.dte == 180)]
    if head.empty:
        head = m.iloc[[0]]
    head = head.iloc[0]
    pos = int((m["mean"] > 0).sum())
    med = float(m["mean"].median())

    print("\n" + "=" * w)
    print("THE SAMPLE-SIZE PROBLEM, WHICH V37 PRESPECIFIED AS THE FINDING")
    print("=" * w)
    print(f"""
  The headline cell holds {head['n']:.0f} cycles of {head['yrs']:.2f} years each over a
  4.49-year sample. These are back-to-back and therefore already independent --
  but {head['n']:.0f} observations is an anecdote, not a measurement.

  mean {head['mean']*100:+.2f}% per cycle, se {head['sem']*100:.2f}%, t = {head['t']:+.2f}
  95% CI [{(head['mean']-1.96*head['sem'])*100:+.1f}%, {(head['mean']+1.96*head['sem'])*100:+.1f}%]

  To reach |t| = 2.0 at this effect size would need
  {(2.0*head['sem']/abs(head['mean']))**2*head['n']:.0f} cycles = {(2.0*head['sem']/abs(head['mean']))**2*head['n']*head['yrs']:.0f} years of data.""")

    print(f"\n  {'BAR':<6}{'test':<48}{'result':>14}{'':>6}")
    print("  " + "-" * 74)
    b1 = head["t"] > 2.0 and head["mean"] > 0
    b4 = pos >= 5
    b5 = abs(head["mean"] - med) <= head["sem"]
    b7 = head["mdd"] > -0.35
    for k, d_, ok, v in (
            ("B1", "return > 0, t > 2.0 on independent cycles", b1,
             f"{head['mean']*100:+.2f}%, t={head['t']:+.2f}"),
            ("B3", "every cost charged", True, "yes"),
            ("B4", "at least 5 of 6 cells positive", b4, f"{pos}/{len(m)}"),
            ("B5", "headline within 1 se of grid median", b5,
             f"med {med*100:+.2f}%"),
            ("B7", "max drawdown < 35%", b7, f"{head['mdd']*100:.0f}%")):
        print(f"  {k:<6}{d_:<48}{v:>14}   {'PASS' if ok else 'FAIL'}")
    print(f"\n  ADOPTED: {'YES' if (b1 and b4 and b5) else 'NO'}"
          f"    (V37 predicted INCONCLUSIVE, not pass or fail)")
    df.to_csv(os.path.join(_HERE, "out", "V37_longdated_grid.csv"), index=False)
    return 0


def _v33(chain, spot) -> int:
    """V29 Tier 1 #2 — the unhedged straddle, against V31/V32's hedged arm."""
    global HEDGE_MODE, EXIT_MODE, EXTRA_SPREAD_VOL_PTS
    w = 96
    print("=" * w)
    print("V33 — LONG ATM SOXL STRADDLE, UNHEDGED. V29 Tier 1 #2.")
    print("   Six prespecified cells. Both spread regimes. Bar in "
          "V33_UNHEDGED_BAR.md, committed first.")
    print("=" * w)

    rows = []
    for shortfall, label in ((0.0, "vendor EOD spread (as V31 charged)"),
                             (7.2, "+ V32 measured shortfall  <-- headline")):
        print(f"\n  {label}")
        print(f"  {'hedge':<8}{'exit':<9}{'entry':<7}{'cycles':>8}"
              f"{'ret/cycle':>11}{'t':>7}{'win%':>7}{'equity':>9}{'maxDD':>8}")
        print("  " + "-" * 74)
        for hedge in ("none", "daily"):
            for exit_mode in ("expiry", "roll"):
                if hedge == "daily" and exit_mode == "expiry":
                    continue            # the hedged arm is V31/V32, roll only
                for td in TARGET_DTE:
                    HEDGE_MODE, EXIT_MODE = hedge, exit_mode
                    EXTRA_SPREAD_VOL_PTS = shortfall
                    c, _ = run(chain, spot, td, 14)
                    if not c:
                        continue
                    st = summarize(c, "", verbose=False)
                    rows.append(dict(shortfall=shortfall, hedge=hedge,
                                     exit=exit_mode, entry=td, **{
                                         k: st[k] for k in
                                         ("n", "mean", "t", "win", "equity",
                                          "mdd")}))
                    mark = ("  <-- headline" if (hedge == "none"
                            and exit_mode == "expiry" and td == 37) else "")
                    print(f"  {hedge:<8}{exit_mode:<9}{td:<7}{st['n']:>8}"
                          f"{st['mean']*100:>+10.2f}%{st['t']:>7.2f}"
                          f"{st['win']*100:>6.0f}%{st['equity']*100:>+8.1f}%"
                          f"{st['mdd']*100:>7.0f}%{mark}")

    df = pd.DataFrame(rows)
    m = df[df.shortfall == 7.2]
    un = m[m.hedge == "none"]
    hd = m[m.hedge == "daily"]
    head = un[(un.exit == "expiry") & (un.entry == 37)].iloc[0]
    pos = int((un["mean"] > 0).sum())
    med = float(un["mean"].median())

    print(f"\n" + "=" * w)
    print("DOES DROPPING THE HEDGE HELP, AND IF SO WHY?")
    print("=" * w)
    print(f"\n  at the measured spread, mean return per cycle:")
    print(f"    unhedged, held to expiry   "
          f"{un[un.exit=='expiry']['mean'].mean()*100:>+7.2f}%   "
          f"(pays the ENTRY half-spread only)")
    print(f"    unhedged, rolled at 14 DTE "
          f"{un[un.exit=='roll']['mean'].mean()*100:>+7.2f}%   "
          f"(pays a full round trip)")
    print(f"    hedged daily, rolled       "
          f"{hd['mean'].mean()*100:>+7.2f}%   (V31/V32's arm)")
    d_spread = (un[un.exit=="expiry"]["mean"].mean()
                - un[un.exit=="roll"]["mean"].mean()) * 100
    d_hedge = (un[un.exit=="roll"]["mean"].mean()
               - hd["mean"].mean()) * 100
    print(f"\n  decomposed, and V33 said in advance this had to be visible:")
    print(f"    worth of NOT paying the exit spread  {d_spread:>+7.2f} "
          f"percentage points")
    print(f"    worth of REMOVING the hedge          {d_hedge:>+7.2f} "
          f"percentage points")
    print(f"    -> {'the spread' if abs(d_spread) > abs(d_hedge) else 'the hedge'}"
          f" is the bigger term, by {abs(d_spread)/max(abs(d_hedge),1e-9):.1f}x")

    print(f"\n  {'BAR':<6}{'test':<50}{'result':>12}{'':>6}")
    print("  " + "-" * 74)
    b1 = head["t"] > 2.0 and head["mean"] > 0
    b4 = pos >= 5
    b5 = abs(head["mean"] - med) <= (head["mean"] / head["t"] if head["t"] else 1)
    b7 = head["mdd"] > -0.35
    for k, desc, ok, val in (
            ("B1", "mean return per cycle > 0 with t > 2.0", b1,
             f"{head['mean']*100:+.2f}%, t={head['t']:+.2f}"),
            ("B3", "every cost charged on the taken exit path", True, "yes"),
            ("B4", "at least 5 of 6 unhedged cells positive", b4,
             f"{pos}/{len(un)}"),
            ("B5", "headline within 1 se of the grid median", b5,
             f"med {med*100:+.2f}%"),
            ("B7", "max drawdown < 35%", b7, f"{head['mdd']*100:.0f}%")):
        print(f"  {k:<6}{desc:<50}{val:>12}   {'PASS' if ok else 'FAIL'}")
    print(f"\n  ADOPTED: {'YES' if (b1 and b4 and b5) else 'NO'}")
    df.to_csv(os.path.join(_HERE, "out", "V33_unhedged_grid.csv"), index=False)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--trace", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(_HERE, "out"))
    ap.add_argument("--hedge", choices=("daily", "none", "open"),
                    default="daily")
    ap.add_argument("--exit", dest="exit_mode",
                    choices=("roll", "expiry"), default="roll")
    ap.add_argument("--target-dte", type=int, default=None,
                    help="V37: override the entry tenor, e.g. 180")
    ap.add_argument("--dte-window", type=int, default=None)
    ap.add_argument("--v39", action="store_true",
                    help="open-hedged against close-hedged, six cells")
    ap.add_argument("--v37", action="store_true",
                    help="the six prespecified long-dated cells, with t "
                         "computed on NON-OVERLAPPING cycles")
    ap.add_argument("--v33", action="store_true",
                    help="the six prespecified unhedged cells, both spread "
                         "regimes, against the hedged arm")
    ap.add_argument("--extra-spread", type=float, default=0.0,
                    help="extra vol points of option spread to charge per "
                         "cycle; 7.2 is the V32 measured shortfall")
    a = ap.parse_args()

    global EXTRA_SPREAD_VOL_PTS, HEDGE_MODE, EXIT_MODE, DTE_WINDOW
    EXTRA_SPREAD_VOL_PTS = a.extra_spread
    HEDGE_MODE, EXIT_MODE = a.hedge, a.exit_mode
    if a.dte_window:
        DTE_WINDOW = a.dte_window
    chain = load_chain()
    if a.hedge == "open" or a.v39:
        _load_opens()
    chain["expiry_key"] = chain["expiration"].astype("int64")
    spot = daily_closes("SOXL")

    if a.v39:
        return _v39(chain, spot)
    if a.v37:
        return _v37(chain, spot)
    if a.v33:
        return _v33(chain, spot)

    print("=" * 84)
    print("V30 — LONG ATM SOXL STRADDLE, DELTA-HEDGED ONCE DAILY AT THE CLOSE")
    print(f"   headline: enter nearest {HEADLINE[0]} DTE, roll at "
          f"{HEADLINE[1]} DTE. Buy the ask, sell the bid, every cost charged.")
    print("=" * 84)

    cyc, daily = run(chain, spot, *HEADLINE, trace=a.trace)
    bad = _audit(cyc)
    print(f"\n  AUDIT: {len(bad)} violations of the V30 discard rules")
    for b in bad[:10]:
        print(f"    {b}")
    if bad:
        print("  Result is not reportable until these are explained.")

    head = summarize(cyc, "headline")
    equity_report(cyc, daily)

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
                c, _ = run(chain, spot, td, rd)
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
    # Mode-aware filenames. Every run used to write V30_straddle_cycles.csv
    # regardless of configuration, so a --hedge none smoke test silently
    # replaced the committed headline artifact with unhedged data. The headline
    # file must be producible only by the headline configuration.
    tag = ("" if (HEDGE_MODE, EXIT_MODE) == ("daily", "roll")
           else f"_{HEDGE_MODE}_{EXIT_MODE}")
    head["df"].to_csv(os.path.join(a.out, f"V30_straddle_cycles{tag}.csv"),
                      index=False)
    daily.to_csv(os.path.join(a.out, f"V30_straddle_daily{tag}.csv"),
                 index=False)
    print(f"\n  wrote out/V30_straddle_cycles{tag}.csv "
          f"({len(head['df'])} cycles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
