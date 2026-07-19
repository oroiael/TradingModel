#!/usr/bin/env python3
"""
SOXL Weekly-Income Covered Call + Long-Dated Put Backtest  (Version 1)
======================================================================

Implements the "Trade to Model" in "Option Trading Project for SOXL.md":

    Part 1: When no short call is outstanding, sell a call Monday by 10:00
            at the nearest LISTED strike to the share COST BASIS (user
            revision 2026-07-18; spec 2.a.i originally said nearest OTM to
            the current price), expiring at the REAL listed weekly
            expiration for that week -- Friday, or Thursday on holiday
            weeks (spec 2.a: "Short calls expire that Friday"). If no
            strike within 2.5% of basis is listed (deep drawdowns), the
            sale is skipped and flagged. Settles at expiration; early
            exercise is not modeled.
    Part 2: Hold long SOXL shares (75% of capital, whole shares); shares only
            leave via call assignment or put exercise/sale.
    Part 3: Hold a long put, strike nearest whole dollar to the underlying
            purchase price, at the OPTIMAL listed expiration scanned over
            60-180 DTE -- lowest executed premium per protected day (user
            revision 2026-07-18; spec 1.c/e originally said ~6 months,
            120-180 days) -- with the roll-up rule (+20%, upside only,
            user revision of the original 10% either-way rule) and the
            15% protective-exit rule.

Capital: start $150,000; invest 75%; sweep 10% (user revision 2026-07-18;
spec said 25%) of each week's positive realized gain to a separate account;
reinvest the rest.

----------------------------------------------------------------------
PRICING DATA (disclosure per spec parameter #7)
----------------------------------------------------------------------
Options are priced from the merged raw ThetaData exports
(SOXL_Options_2024/2025/2026.csv via soxl_options_loader), which cover the
full window 2024-01-02 -> 2026-07-02 with 0-DTE-and-up expirations and the
full strike range (verified by data_evaluation.py, section 4).  BOTH legs
are therefore priced from REAL bid/ask quotes:

    * SHORT CALL (weekly): the REAL listed weekly expiring that week,
      real quote at the basis-anchored strike when listed;
    * LONG PUT (optimal-expiry scan, 60-180 DTE): every listed
      expiration in the window is priced from real quotes at the listed
      whole-dollar strike nearest the purchase price; the cheapest per
      protected day is bought and the scan recorded per row;
    * marks/rolls/buybacks: real quote for the exact contract on that day.

Black-Scholes with file IV survives only as a per-row-flagged fallback for
contracts with no usable quote.  Every priced leg in the output CSV carries
a `pricing_source` field naming the exact quote/IV row used.  Remaining
bias: option snapshots are end-of-day; trades happen 09:30/10:00 Monday.

Bid/ask handling (spec parameter #6), applied to the REAL spread (or, for
BS-fallback rows, a synthetic spread bracketing the BS mid):
    sell (write)  at bid + 20% of the spread,
    buy  (long)   at ask - 20% of the spread.

Risk-free rate for BS fallbacks: constant 4.5% (documented assumption; not
in the data files).
----------------------------------------------------------------------

Timing conventions (from the 5-minute file, verified present for every week):
    * share purchase        : entry-day 09:30 bar CLOSE (executed "moments
                              after the open", spec parameter #4)
    * put purchase          : same time as the shares
    * call sale             : entry-day 10:00 bar OPEN ("by 10:00am")
    * roll-up / 15% checks  : settlement-day 15:30 bar CLOSE ("3:30pm Friday")
    * weekly close / assign : settlement-day last bar CLOSE (15:55 bar)
    * entry day = first trading day of the week (Monday, or Tuesday when
      Monday is a holiday); settlement day = last trading day of the week.

Output: soxl_weekly_backtest_results.csv -- one row per week with price,
cost, units, P&L and disposition for each leg, plus the capital ledger.
"""

import bisect
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from soxl_options_loader import load_raw_options

ROOT = Path(__file__).resolve().parent
STOCK_CSV = ROOT / "SOXL_5min_3Years.csv"
OUT_CSV = ROOT / "soxl_weekly_backtest_results.csv"

# ------------------------- documented assumptions --------------------------
RISK_FREE = 0.045          # constant r for BS (not in data files)
CASH_YIELD = 0.045         # opt #1a (2026-07-18): T-bill-proxy interest
                           # accrued on idle trading cash, calendar-day
                           # basis on the week's opening cash. Documented
                           # constant -- replace with a real rate series
                           # when provided. Excluded from the sweep base.
WEEKLY_TOPUP = True        # opt #1b: every Monday, top share sleeve back
                           # up to INVEST_FRACTION of the trading balance
                           # (was: only at re-entry after assignment/exit).
                           # Extra put contracts are bought at the same
                           # strike/expiration to keep the hedge ratio.
DRAWDOWN_CALL_OTM = 0.10   # opt #2: when no strike within 2.5% of basis is
                           # listed (deep drawdown), sell the nearest
                           # listed strike >= spot*(1+10%) instead of
                           # skipping -- income with 10% recovery headroom.
DRAWDOWN_CALL_MIN_PREM = 0.05   # ...but only if it fetches at least
                                # $0.05/share; below that, still skip.
START_CAPITAL = 150_000.0
INVEST_FRACTION = 0.75     # spec Capital #2
SWEEP_FRACTION = 0.10      # user revision 2026-07-18 (spec Capital #3 was 25%)
SPREAD_EXECUTION = 0.20    # spec parameter #6
WEEKLY_CALLS = True        # original spec 2.a: sell Monday, expires that
                           # Friday (the listed weekly; Thursday on holiday
                           # weeks). Reverted from the 21-DTE variant per
                           # user direction 2026-07-18.
PUT_SCAN_MIN = 120         # user revision 2026-07-18 (floor raised from 60
                           # after the 88-DTE pick showed per-day cost is
                           # blind to repurchase churn): instead of a fixed
PUT_SCAN_MAX = 180         # ~6-month put, scan ALL real listed expirations
                           # with 60-180 DTE at purchase time and buy the
                           # one with the lowest COST PER PROTECTED DAY
                           # (executed premium / DTE) at the listed
                           # whole-dollar strike nearest the purchase
                           # price. The scan is recorded per row in
                           # put_pricing_source.
ROLL_MOVE = None           # roll-ups DISABLED (user-approved 2026-07-18
                           # after the put-policy lab showed rolling up
                           # doubles hedge spend for zero extra drawdown
                           # protection: sell-low/buy-high every roll).
                           # The put is bought and HELD TO EXPIRATION.
                           # Set to e.g. 0.20 to re-enable the old rule.
ROLL_DOWN_MOVE = None      # put-policy lab: roll DOWN (harvest the put's
                           # gain, re-strike ATM) when move <= -x vs basis.
                           # None (default) = off, current behavior.
HARVEST_MULT = None        # put-policy lab: sell + re-strike ATM when the
                           # put's mark reaches this multiple of its cost
                           # (e.g. 2.0 = harvest at 2x). None = off.
EXIT_MODE = "conditional"  # "conditional" (spec 2.c.v: exit at -15% only
                           # if the put's gain covers the stock loss),
                           # "unconditional" (exit at -15% regardless),
                           # "off" (never exit).
EXIT_DROP = 0.15           # spec 2.c.v
HEDGE_ENABLED = True       # put-policy lab: False runs the covered-call
                           # machine with NO protective put at all.
PUT_SPREAD_SHORT_FRAC = None   # put-spread strategy (2026-07-18): sell a
                               # put at ~this fraction of the long strike,
                               # SAME expiration, real quote (e.g. 0.75).
                               # Recovers part of the hedge cost; downside
                               # protection stops below the short strike.
                               # None = plain long put (default).


# ------------------------------ Black-Scholes ------------------------------
def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(right, s, k, t_years, sigma, r=RISK_FREE):
    """Plain Black-Scholes. Returns intrinsic value when t or sigma ~ 0."""
    if t_years <= 0 or sigma <= 0:
        return max(s - k, 0.0) if right == "CALL" else max(k - s, 0.0)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t_years) / (
        sigma * math.sqrt(t_years))
    d2 = d1 - sigma * math.sqrt(t_years)
    if right == "CALL":
        return s * _ncdf(d1) - k * math.exp(-r * t_years) * _ncdf(d2)
    return k * math.exp(-r * t_years) * _ncdf(-d2) - s * _ncdf(-d1)


# ------------------------------- data access -------------------------------
class Market:
    """Verified lookups into the two data files. No repairs, no invention:
    every IV/spread comes from a concrete row and is reported back to the
    caller as a pricing_source string."""

    def __init__(self):
        st = pd.read_csv(STOCK_CSV)
        dt = pd.to_datetime(
            st["Date"].str.replace(" America/New_York", "", regex=False),
            format="%Y%m%d %H:%M:%S")
        st["date"] = dt.dt.date
        st["time"] = dt.dt.strftime("%H:%M")
        self.stock = st
        self.bars = {(d, t): row for d, t, row in zip(
            st["date"], st["time"],
            st[["Open", "High", "Low", "Close"]].itertuples(index=False))}
        self.day_last = st.groupby("date").last()[["Close", "time"]]
        self.trading_days = sorted(st["date"].unique())

        opt = load_raw_options()
        self.opt_by_day = dict(tuple(opt.groupby("trade_date")))
        self.opt_dates = sorted(self.opt_by_day)

    # ---- stock ----
    def bar_close(self, d, hhmm):
        row = self.bars.get((d, hhmm))
        return None if row is None else row.Close

    def bar_open(self, d, hhmm):
        row = self.bars.get((d, hhmm))
        return None if row is None else row.Open

    def day_close(self, d):
        return self.day_last.loc[d, "Close"]

    def pre_close_price(self, d):
        """Price ~30 min before the day's last bar (handles half days)."""
        last = self.day_last.loc[d, "time"]
        hh, mm = map(int, last.split(":"))
        mins = hh * 60 + mm - 30
        p = self.bar_close(d, f"{mins // 60:02d}:{mins % 60:02d}")
        return p if p is not None else self.day_close(d)

    def last_trading_on_or_before(self, d):
        i = bisect.bisect_right(self.trading_days, d)
        return self.trading_days[i - 1] if i else None

    # ---- options ----
    def chain(self, d):
        return self.opt_by_day.get(d)

    def expiration_near(self, d, target_dte):
        """The REAL expiration listed on day d with DTE nearest target."""
        ch = self.chain(d)
        if ch is None:
            return None
        g = ch[["expiration", "dte"]].drop_duplicates()
        row = g.loc[(g["dte"] - target_dte).abs().idxmin()]
        return row["expiration"], int(row["dte"])

    def quote(self, d, right, strike, exp):
        """The actual quote row for (right, strike, exp) on day d, or None."""
        ch = self.chain(d)
        if ch is None:
            return None
        m = ch[(ch["right"] == right) & (ch["strike"] == strike)
               & (ch["expiration"] == exp)]
        return None if m.empty else m.iloc[0]

    def scan_put_candidates(self, d, spot):
        """Scan every REAL listed expiration with PUT_SCAN_MIN-PUT_SCAN_MAX
        DTE on day d.  For each, take the listed whole-dollar strike
        nearest `spot` with a live ask and compute the executed buy price
        (spec #6) and its cost per protected day.  Returns a list of dicts
        sorted cheapest-per-day first (possibly empty)."""
        ch = self.chain(d)
        if ch is None:
            return []
        cands = []
        exps = ch[["expiration", "dte"]].drop_duplicates()
        exps = exps[(exps["dte"] >= PUT_SCAN_MIN)
                    & (exps["dte"] <= PUT_SCAN_MAX)]
        for exp, dte in exps.itertuples(index=False):
            rows = ch[(ch["right"] == "PUT") & (ch["expiration"] == exp)
                      & (ch["strike"] % 1 == 0) & (ch["ask"] > 0)]
            if rows.empty:
                continue
            row = rows.loc[(rows["strike"] - spot).abs().idxmin()]
            bid, ask = float(row["bid"]), float(row["ask"])
            px = ask - SPREAD_EXECUTION * (ask - bid)
            cands.append({"exp": exp, "dte": int(dte),
                          "strike": float(row["strike"]),
                          "bid": bid, "ask": ask, "px": px,
                          "cost_per_day": px / int(dte)})
        return sorted(cands, key=lambda c: c["cost_per_day"])

    def iv_and_spread(self, d, right, strike, want_long_dte):
        """IV + relative spread from the file: rows of `right` on day d with
        iv>0, strike nearest to `strike`; among those, min DTE for the weekly
        call (want_long_dte=False) or max DTE for the long put (True).
        Returns (iv, spread_frac, source_str) or None."""
        ch = self.chain(d)
        if ch is None:
            return None
        rows = ch[(ch["right"] == right) & (ch["implied_vol"] > 0)]
        if rows.empty:
            return None
        near = rows.iloc[(rows["strike"] - strike).abs().argsort()]
        best_k = near["strike"].iloc[0]
        at_k = near[near["strike"] == best_k]
        row = at_k.loc[at_k["dte"].idxmax() if want_long_dte
                       else at_k["dte"].idxmin()]
        if row["bid"] > 0 and row["ask"] >= row["bid"]:
            mid = (row["bid"] + row["ask"]) / 2
            spread_frac = (row["ask"] - row["bid"]) / mid
        else:  # zero-bid row: use that day's median spread (data-driven)
            ok = ch[(ch["bid"] > 0)]
            m = (ok["bid"] + ok["ask"]) / 2
            spread_frac = ((ok["ask"] - ok["bid"]) / m).median()
        src = (f"IV={row['implied_vol']:.3f} from {right} K={row['strike']} "
               f"exp={row['expiration']} dte={int(row['dte'])}")
        return float(row["implied_vol"]), float(spread_frac), src

    def exec_price(self, mid, spread_frac, side):
        """Spec parameter #6 around a BS mid bracketed by the file's spread:
        sell at bid + 20% of spread; buy at ask - 20% of spread."""
        half = mid * spread_frac / 2
        bid, ask = max(mid - half, 0.0), mid + half
        if side == "SELL":
            return bid + SPREAD_EXECUTION * (ask - bid)
        return ask - SPREAD_EXECUTION * (ask - bid)


# --------------------------------- backtest --------------------------------
def run(mkt=None):
    mkt = mkt or Market()

    # Weeks = ISO weeks restricted to the overlap of both files.
    start, end = mkt.opt_dates[0], mkt.opt_dates[-1]
    days = [d for d in mkt.trading_days if start <= d <= end]
    weeks = {}
    for d in days:
        weeks.setdefault(d.isocalendar()[:2], []).append(d)
    weeks = [sorted(v) for _, v in sorted(weeks.items())]

    cash = START_CAPITAL
    side_account = 0.0
    shares = 0
    basis = 0.0            # per-share purchase price of the current lot
    put = None             # dict(strike, expiration, contracts, cost_ps)
    call = None            # dict(strike, expiration, contracts, premium_ps)
    prev_settle = None
    rows = []
    warnings = []

    for wk in weeks:
        entry, settle = wk[0], wk[-1]
        r = {"week_start": entry, "week_end": settle}
        s_entry = mkt.bar_close(entry, "09:30")
        s_1000 = mkt.bar_open(entry, "10:00")
        if s_entry is None or s_1000 is None:
            warnings.append(f"{entry}: missing entry bars, week skipped")
            continue

        begin_positions = shares * s_entry + (
            put_value(mkt, put, entry, s_entry)[0] * put["contracts"] * 100
            if put else 0.0) - (
            call_mark(mkt, call, entry, s_entry)[0] * call["contracts"] * 100
            if call else 0.0)
        r["begin_cash"] = round(cash, 2)
        begin_cash = cash
        r["begin_total_balance"] = round(cash + begin_positions, 2)
        r["begin_side_account"] = round(side_account, 2)
        realized = 0.0
        flows = 0.0   # independent tally of every cash movement (QA)

        # ---- opt #1a: interest on idle cash (calendar days since the
        # previous settlement, on the week's opening cash; not swept) ----
        accrual_days = (settle - (prev_settle or entry)).days
        interest = cash * CASH_YIELD * accrual_days / 365.0
        cash += interest
        flows += interest
        r["cash_interest"] = round(interest, 2)

        # ---- Part 2: underlying entry / weekly top-up (opt #1b) ----
        r.update({"stock_action": "HELD", "stock_buy_units": 0,
                  "stock_buy_price": "", "stock_buy_cost": ""})
        if shares < 100 or WEEKLY_TOPUP:
            target = INVEST_FRACTION * (cash + shares * s_entry)
            buy = int((target - shares * s_entry) // s_entry)
            if buy > 0:
                cost = buy * s_entry
                cash -= cost
                flows -= cost
                basis = ((shares * basis) + cost) / (shares + buy)
                was_entry = shares < 100
                shares += buy
                r.update({"stock_action": "BUY" if was_entry else "TOPUP",
                          "stock_buy_units": buy,
                          "stock_buy_price": round(s_entry, 4),
                          "stock_buy_cost": round(cost, 2)})

        # ---- Part 3: long put purchase (new position or post-expiry) ----
        r.update({"put_action": "HELD",
                  "put_open_price": "", "put_open_cost": "",
                  "put_sell_price": "", "put_sell_proceeds": "",
                  "put_roll_price": "", "put_roll_cost": "",
                  "put_realized_pnl": "", "put_pricing_source": ""})
        if put is None and shares >= 100 and HEDGE_ENABLED:
            put, note = open_put(mkt, entry, s_entry, shares, cash)
            if put:
                cost = put["cost_ps"] * put["contracts"] * 100
                cash -= cost
                flows -= cost
                r.update({"put_action": "BUY",
                          "put_open_price": round(put["cost_ps"], 4),
                          "put_open_cost": round(cost, 2),
                          "put_pricing_source": note})
            else:
                warnings.append(f"{entry}: could not price put ({note})")
        # opt #1b: keep the hedge ratio when weekly top-ups add a new
        # round lot -- buy additional contracts of the SAME put.
        if put is not None and shares // 100 > put["contracts"]:
            add = shares // 100 - put["contracts"]
            rq = mkt.quote(entry, "PUT", put["strike"], put["expiration"])
            rq_s = (mkt.quote(entry, "PUT", put["short_strike"],
                              put["expiration"])
                    if put.get("short_strike") else None)
            if rq is not None and rq["ask"] > 0 and (
                    put.get("short_strike") is None
                    or (rq_s is not None and rq_s["ask"] > 0)):
                bid, ask = float(rq["bid"]), float(rq["ask"])
                px = ask - SPREAD_EXECUTION * (ask - bid)
                short_note = ""
                if rq_s is not None:
                    sbid, sask = float(rq_s["bid"]), float(rq_s["ask"])
                    scredit = sbid + SPREAD_EXECUTION * (sask - sbid)
                    px -= scredit
                    short_note = (f", short K={put['short_strike']} sold @ "
                                  f"{scredit:.2f} (bid={sbid} ask={sask})")
                cost = px * add * 100
                if cost <= cash:
                    cash -= cost
                    flows -= cost
                    tot = put["contracts"] + add
                    put["cost_ps"] = (put["cost_ps"] * put["contracts"]
                                      + px * add) / tot
                    put["contracts"] = tot
                    r["put_action"] = (r["put_action"]
                                       + f"+ADD{add}").replace("HELD+", "")
                    r["put_open_price"] = round(px, 4)
                    r["put_open_cost"] = round(cost, 2)
                    r["put_pricing_source"] = (
                        str(r["put_pricing_source"]) + f"; add {add} "
                        f"contracts @ REAL QUOTE bid={bid} ask={ask}"
                        + short_note
                    ).lstrip("; ")
                else:
                    warnings.append(f"{entry}: hedge top-up ({add} "
                                    f"contracts, {cost:,.0f}) exceeds cash")
            else:
                warnings.append(f"{entry}: hedge top-up skipped, no quote "
                                f"K={put['strike']} exp={put['expiration']}")
        r["put_strike"] = put["strike"] if put else ""
        r["put_expiration"] = put["expiration"] if put else ""
        r["put_contracts"] = put["contracts"] if put else 0

        # ---- Part 1: short call management at Monday 10:00 ----
        # Weekly call at the whole strike nearest the cost basis
        # (user variant 2026-07-18). A new call is sold only when none is
        # outstanding; premium P&L is REALIZED at settlement, though the
        # cash arrives at sale.
        contracts = shares // 100
        r.update({"call_action": "NONE", "call_strike": "",
                  "call_expiration": "", "call_contracts": 0,
                  "call_sell_price": "", "call_premium_received": "",
                  "call_close_cost": "", "call_realized_pnl": "",
                  "call_outcome": "", "call_pricing_source": ""})
        if call is None and contracts > 0:
            call, note = open_call(mkt, entry, s_1000, basis, contracts)
            if call:
                prem = call["premium_ps"] * call["contracts"] * 100
                cash += prem
                flows += prem
                r.update({"call_action": "SOLD",
                          "call_sell_price": round(call["premium_ps"], 4),
                          "call_premium_received": round(prem, 2),
                          "call_pricing_source": note})
            else:
                warnings.append(f"{entry}: call not sold ({note})")
        elif call is not None:
            r["call_action"] = "HELD"
        if call:
            r.update({"call_strike": call["strike"],
                      "call_expiration": call["expiration"],
                      "call_contracts": call["contracts"]})

        # ---- Friday 15:30: put management checks ----
        s_1530 = mkt.pre_close_price(settle)
        s_close = mkt.day_close(settle)
        move = (s_1530 - basis) / basis if shares else 0.0
        r["basis_price"] = round(basis, 4) if shares else ""
        r["friday_1530_price"] = round(s_1530, 4)
        r["move_vs_basis_pct"] = round(100 * move, 2) if shares else ""
        exited = False

        if put and shares:
            val_ps, mark_src = put_value(mkt, put, settle, s_1530)
            put_gain = (val_ps - put["cost_ps"]) * put["contracts"] * 100

            if EXIT_MODE != "off" and move <= -EXIT_DROP:
                # spec 2.c.v: exit at -15%; "conditional" mode (spec) only
                # if the put's gain covers the loss, "unconditional" always
                stock_loss = (basis - s_1530) * shares
                if EXIT_MODE == "unconditional" or put_gain >= stock_loss:
                    px, mark_src = close_put(mkt, put, settle, s_1530)
                    proceeds = px * put["contracts"] * 100
                    pnl = proceeds - put["cost_ps"] * put["contracts"] * 100
                    cash += proceeds
                    flows += proceeds
                    realized += pnl
                    stock_pnl = (s_1530 - basis) * shares
                    cash += s_1530 * shares
                    flows += s_1530 * shares
                    realized += stock_pnl
                    r.update({"put_action": "SOLD_PROTECTIVE_EXIT",
                              "put_sell_price": round(px, 4),
                              "put_sell_proceeds": round(proceeds, 2),
                              "put_realized_pnl": round(pnl, 2),
                              "put_pricing_source": mark_src,
                              "stock_action": "SOLD_PROTECTIVE_EXIT",
                              "stock_sell_price": round(s_1530, 4),
                              "stock_realized_pnl": round(stock_pnl, 2)})
                    if call:   # shares gone -> close the short call too
                        mid, spr, vsrc = call_mark(mkt, call, settle, s_1530)
                        buy_px = mkt.exec_price(mid, spr, "BUY")
                        cost_c = buy_px * call["contracts"] * 100
                        prem = call["premium_ps"] * call["contracts"] * 100
                        cash -= cost_c
                        flows -= cost_c
                        realized += prem - cost_c
                        r.update({"call_outcome": "BOUGHT_BACK_ON_EXIT",
                                  "call_close_cost": round(cost_c, 2),
                                  "call_realized_pnl": round(prem - cost_c, 2),
                                  "call_pricing_source":
                                      (str(r["call_pricing_source"])
                                       + f"; buyback: {vsrc}").lstrip("; ")})
                        call = None
                    shares, put, exited = 0, None, True
                else:
                    r["put_action"] = (r["put_action"] + "+HELD_15PCT_CHECK"
                                       ).replace("HELD+", "")
            elif not exited and (
                    (ROLL_MOVE is not None and move >= ROLL_MOVE)
                    or (ROLL_DOWN_MOVE is not None
                        and move <= -ROLL_DOWN_MOVE)
                    or (HARVEST_MULT is not None
                        and val_ps >= HARVEST_MULT * put["cost_ps"])):
                # Roll: sell the held put at its real mark, re-strike ATM.
                # Direction/trigger recorded in put_action: roll-UP on
                # +move (user rule), roll-DOWN / profit-HARVEST are
                # put-policy-lab variants (off by default).
                roll_tag = ("ROLLED" if move >= (ROLL_MOVE or 9e9)
                            else ("HARVESTED" if HARVEST_MULT is not None
                                  and val_ps >= HARVEST_MULT
                                  * put["cost_ps"]
                                  else "ROLLED_DOWN"))
                px, mark_src = close_put(mkt, put, settle, s_1530)
                proceeds = px * put["contracts"] * 100
                pnl = proceeds - put["cost_ps"] * put["contracts"] * 100
                cash += proceeds
                flows += proceeds
                realized += pnl
                old = f"K={put['strike']} exp={put['expiration']}"
                new_put, note = open_put(mkt, settle, s_1530,
                                         put["contracts"] * 100, cash)
                r.update({"put_action": r["put_action"].replace(
                              "HELD", "").replace("BUY", "BUY+") + roll_tag,
                          "put_sell_price": round(px, 4),
                          "put_sell_proceeds": round(proceeds, 2),
                          "put_realized_pnl": round(pnl, 2)})
                if new_put:
                    new_cost = new_put["cost_ps"] * new_put["contracts"] * 100
                    cash -= new_cost
                    flows -= new_cost
                    put = new_put
                    r.update({"put_roll_price": round(new_put["cost_ps"], 4),
                              "put_roll_cost": round(new_cost, 2),
                              "put_pricing_source":
                                  f"sold {old} ({mark_src}); {note}",
                              "put_strike": new_put["strike"],
                              "put_expiration": new_put["expiration"]})
                else:
                    put = None
                    r["put_action"] += "_REBUY_FAILED"
                    warnings.append(f"{settle}: roll failed ({note})")

        # ---- put expiration on/before this settlement day ----
        if put and put["expiration"] <= settle:
            intrinsic = max(put["strike"] - s_close, 0.0)
            if put.get("short_strike"):
                # spread: cash-settle the NET intrinsic (short leg owed)
                intrinsic -= max(put["short_strike"] - s_close, 0.0)
            proceeds = intrinsic * put["contracts"] * 100
            pnl = proceeds - put["cost_ps"] * put["contracts"] * 100
            cash += proceeds
            flows += proceeds
            realized += pnl
            r.update({"put_action": "EXPIRED"
                      + ("_ITM_SOLD_AT_INTRINSIC" if intrinsic
                         else "_WORTHLESS"),
                      "put_sell_price": round(intrinsic, 4),
                      "put_sell_proceeds": round(proceeds, 2),
                      "put_realized_pnl": round(pnl, 2)})
            put = None   # replaced next Monday (spec 2.c.iii)

        # ---- call settlement when its expiration falls in this week ----
        # The weekly call settles at the last trading day on/before its
        # expiration (American early exercise is not modeled -- documented
        # simplification).
        r["friday_close_price"] = round(s_close, 4)
        if call and not exited:
            exp_day = mkt.last_trading_on_or_before(call["expiration"])
            if exp_day is not None and exp_day <= settle:
                s_exp = mkt.day_close(exp_day)
                prem = call["premium_ps"] * call["contracts"] * 100
                r.update({"call_strike": call["strike"],
                          "call_expiration": call["expiration"],
                          "call_contracts": call["contracts"],
                          "call_realized_pnl": round(prem, 2)})
                if s_exp > call["strike"]:
                    assigned = min(call["contracts"] * 100, shares)
                    stock_pnl = (call["strike"] - basis) * assigned
                    cash += call["strike"] * assigned
                    flows += call["strike"] * assigned
                    shares -= assigned
                    realized += stock_pnl + prem
                    r.update({"call_outcome":
                                  f"ASSIGNED@{exp_day}(close {s_exp:.2f})",
                              "stock_action": (r["stock_action"]
                                               + "+ASSIGNED").replace(
                                                   "HELD+", ""),
                              "stock_assigned_units": assigned,
                              "stock_realized_pnl": round(stock_pnl, 2)})
                else:
                    realized += prem
                    r["call_outcome"] = (f"EXPIRED_WORTHLESS@{exp_day}"
                                         f"(close {s_exp:.2f})")
                call = None   # a new call is sold next Monday

        # ---- weekly sweep (spec Capital #3) ----
        r["realized_gain_total"] = round(realized, 2)
        sweep = SWEEP_FRACTION * realized if realized > 0 else 0.0
        cash -= sweep
        flows -= sweep
        side_account += sweep
        r["swept_to_side_account"] = round(sweep, 2)
        r["side_account_balance"] = round(side_account, 2)

        # QA: every cash movement was tallied independently in `flows`;
        # the ledger must reconcile to the penny.
        recon_err = abs((begin_cash + flows) - cash)
        r["cash_ledger_reconciled"] = recon_err < 0.01
        if recon_err >= 0.01:
            warnings.append(f"{settle}: CASH LEDGER MISMATCH {recon_err:.2f}")

        # ---- end-of-week valuation ----
        put_val = (put_value(mkt, put, settle, s_close)[0]
                   * put["contracts"] * 100) if put else 0.0
        call_liab = (call_mark(mkt, call, settle, s_close)[0]
                     * call["contracts"] * 100) if call else 0.0
        r["end_shares"] = shares
        r["end_share_value"] = round(shares * s_close, 2)
        r["end_put_value"] = round(put_val, 2)
        r["call_liability_value"] = round(call_liab, 2)
        r["end_cash"] = round(cash, 2)
        end_bal = cash + shares * s_close + put_val - call_liab
        r["end_total_balance"] = round(end_bal, 2)
        r["end_total_with_side"] = round(end_bal + side_account, 2)
        rows.append(r)
        prev_settle = settle

        if cash < 0:
            warnings.append(f"{settle}: cash went negative ({cash:,.2f})")

    return pd.DataFrame(rows), warnings


def _leg_mark(mkt, d, strike, exp, spot, t_years):
    """(mid, spread_frac, src) for one put leg: REAL quote when the row
    exists, else BS with file IV (flagged)."""
    row = mkt.quote(d, "PUT", strike, exp)
    if row is not None and row["ask"] > 0:
        bid, ask = float(row["bid"]), float(row["ask"])
        mid = (bid + ask) / 2
        spread = (ask - bid) / mid if mid > 0 else 0.14
        return mid, spread, (f"REAL QUOTE bid={bid} ask={ask}"
                             + ("; ZERO BID" if bid == 0 else ""))
    got = mkt.iv_and_spread(d, "PUT", strike, want_long_dte=True)
    if got is None:
        return max(strike - spot, 0.0), 0.14, "intrinsic (no quote/IV row)"
    iv, spread, src = got
    return bs_price("PUT", spot, strike, t_years, iv), spread, \
        f"BS est (no quote row); {src}"


def put_value(mkt, put, d, spot):
    """NET mark of the held put position (long leg minus short leg when a
    spread is on). Returns (PER-SHARE mid, source string)."""
    t = max((put["expiration"] - d).days, 0) / 365.0
    v_l, _, src_l = _leg_mark(mkt, d, put["strike"], put["expiration"],
                              spot, t)
    if put.get("short_strike"):
        v_s, _, src_s = _leg_mark(mkt, d, put["short_strike"],
                                  put["expiration"], spot, t)
        return v_l - v_s, (f"long: {src_l}; "
                           f"short K={put['short_strike']}: {src_s}")
    return v_l, src_l


def close_put(mkt, put, d, spot):
    """Unwind the put position at executable prices (spec #6 per leg):
    sell the long leg, buy back the short leg if a spread is on.
    Returns (NET proceeds per share, source string)."""
    t = max((put["expiration"] - d).days, 0) / 365.0
    v_l, sp_l, src_l = _leg_mark(mkt, d, put["strike"], put["expiration"],
                                 spot, t)
    proceeds = mkt.exec_price(v_l, sp_l, "SELL")
    src = f"sold long ({src_l})"
    if put.get("short_strike"):
        v_s, sp_s, src_s = _leg_mark(mkt, d, put["short_strike"],
                                     put["expiration"], spot, t)
        proceeds -= mkt.exec_price(v_s, sp_s, "BUY")
        src += f"; bought back short K={put['short_strike']} ({src_s})"
    return proceeds, src


def open_call(mkt, d, spot, basis, contracts):
    """Sell the WEEKLY covered call (original spec 2.a: sold Monday,
    expires that Friday) at the whole strike nearest the cost basis.
    Expiration is the REAL listed weekly expiring this week -- Friday, or
    Thursday on holiday weeks.  If the strike is listed there, the REAL
    bid/ask is used with the spec #6 execution rule; otherwise BS with the
    nearest listed strike's IV, flagged."""
    friday = d + timedelta(days=(4 - d.weekday()) % 7)
    got = mkt.expiration_near(d, (friday - d).days)
    if got is None:
        return None, "no option chain on entry day"
    exp, dte = got
    if exp > friday:
        return None, f"no expiration this week listed (nearest is {exp})"
    holiday_note = "" if exp == friday else f"; {exp} weekly (holiday week)"
    # Nearest LISTED strike to the cost basis (spec #5: use file strikes --
    # the real grid is $1 at low prices, $2.50/$5 above ~$200). If nothing
    # within 2.5% (min $2.50) of basis is listed, the strike the strategy
    # wants does not exist that week: skip the sale rather than invent it.
    ch = mkt.chain(d)
    ks = ch.loc[(ch["right"] == "CALL") & (ch["expiration"] == exp),
                "strike"]
    if ks.empty:
        return None, f"no call strikes listed at weekly exp {exp}"
    k = float(ks.iloc[(ks - basis).abs().argsort().iloc[0]])
    drawdown_note = ""
    if abs(k - basis) > max(0.025 * basis, 2.5):
        # opt #2 (2026-07-18): deep drawdown -- no strike near basis.
        # Instead of skipping, sell the nearest listed strike at least
        # DRAWDOWN_CALL_OTM above spot: income now, 10% recovery headroom.
        # Risk accepted: a >10% rally into expiration assigns below basis.
        otm = ks[ks >= spot * (1 + DRAWDOWN_CALL_OTM)]
        if otm.empty:
            return None, (f"no listed strike near basis {basis:.2f} nor "
                          f">= spot+{DRAWDOWN_CALL_OTM:.0%} at weekly exp "
                          f"{exp}; CALL SKIPPED this week")
        k = float(otm.min())
        drawdown_note = (f"; DRAWDOWN OTM SALE: no strike near basis "
                         f"{basis:.2f}, K={k} >= "
                         f"spot {spot:.2f} +{DRAWDOWN_CALL_OTM:.0%}")
    row = mkt.quote(d, "CALL", k, exp)
    if row is not None and row["ask"] > 0:
        bid, ask = float(row["bid"]), float(row["ask"])
        px = bid + SPREAD_EXECUTION * (ask - bid)
        src = (f"REAL QUOTE bid={bid} ask={ask} K={k} exp={exp} dte={dte}"
               + ("; ZERO BID (deep OTM)" if bid == 0 else "") + holiday_note)
    else:
        ch = mkt.chain(d)
        rows = ch[(ch["right"] == "CALL") & (ch["expiration"] == exp)
                  & (ch["implied_vol"] > 0)]
        if rows.empty:
            rows = ch[(ch["right"] == "CALL") & (ch["implied_vol"] > 0)]
        if rows.empty:
            return None, "no call IV rows on entry day"
        near = rows.iloc[(rows["strike"] - k).abs().argsort().iloc[0]]
        iv = float(near["implied_vol"])
        if near["bid"] > 0:
            m = (near["bid"] + near["ask"]) / 2
            spread = (near["ask"] - near["bid"]) / m
        else:
            ok = ch[ch["bid"] > 0]
            mm = (ok["bid"] + ok["ask"]) / 2
            spread = ((ok["ask"] - ok["bid"]) / mm).median()
        mid = bs_price("CALL", spot, k, dte / 365.0, iv)
        px = mkt.exec_price(mid, spread, "SELL")
        src = (f"BS est (K={k} not listed at exp={exp}, chain band artifact);"
               f" IV={iv:.3f} from nearest listed K={near['strike']}")
    if drawdown_note:
        if px < DRAWDOWN_CALL_MIN_PREM:
            return None, (f"drawdown OTM candidate K={k} fetches only "
                          f"{px:.3f}/sh (< {DRAWDOWN_CALL_MIN_PREM}); "
                          f"CALL SKIPPED this week")
        src += drawdown_note
    return ({"strike": k, "expiration": exp, "contracts": contracts,
             "premium_ps": px, "entry": d}, src)


def call_mark(mkt, call, d, spot):
    """Current value of the outstanding short call: REAL quote mid when the
    row exists on day d, else BS with the nearest listed call IV.
    Returns (per-share mid, spread_frac, source)."""
    row = mkt.quote(d, "CALL", call["strike"], call["expiration"])
    if row is not None and row["ask"] > 0 and row["bid"] > 0:
        bid, ask = float(row["bid"]), float(row["ask"])
        mid = (bid + ask) / 2
        return mid, (ask - bid) / mid, f"REAL QUOTE bid={bid} ask={ask}"
    t = max((call["expiration"] - d).days, 0) / 365.0
    got = mkt.iv_and_spread(d, "CALL", call["strike"], want_long_dte=False)
    if got is None:
        return max(spot - call["strike"], 0.0), 0.14, "intrinsic (no IV row)"
    iv, spread, src = got
    return bs_price("CALL", spot, call["strike"], t, iv), spread, \
        f"BS est; {src}"


def open_put(mkt, d, spot, shares, cash_avail):
    """Buy protective puts at the OPTIMAL real listed expiration in the
    60-180 DTE scan window: lowest executed premium per protected day at
    the listed whole-dollar strike nearest `spot` (spec 1.d / parameter
    #5), priced from the file's actual bid/ask with the spec #6 long-side
    rule.  The full scan outcome is recorded in pricing_source."""
    contracts = shares // 100
    if contracts == 0:
        return None, "fewer than 100 shares"
    cands = mkt.scan_put_candidates(d, spot)
    if not cands:
        return None, (f"no quoted whole-dollar puts listed with "
                      f"{PUT_SCAN_MIN}-{PUT_SCAN_MAX} DTE on {d}")
    best, worst = cands[0], cands[-1]
    strike, exp, dte = best["strike"], best["exp"], best["dte"]
    px = best["px"]
    src = (f"OPTIMAL SCAN of {len(cands)} exps {PUT_SCAN_MIN}-"
           f"{PUT_SCAN_MAX}d: chose dte={dte} K={strike} "
           f"cost/day={best['cost_per_day']:.4f} "
           f"(worst: dte={worst['dte']} {worst['cost_per_day']:.4f}); "
           f"REAL QUOTE bid={best['bid']} ask={best['ask']} exp={exp}"
           + ("; ZERO BID" if best["bid"] == 0 else ""))

    # Put-spread variant: sell a put at ~PUT_SPREAD_SHORT_FRAC of the long
    # strike, same expiration, real quote. cost_ps becomes the NET debit.
    short_strike = None
    if PUT_SPREAD_SHORT_FRAC:
        ch = mkt.chain(d)
        srows = ch[(ch["right"] == "PUT") & (ch["expiration"] == exp)
                   & (ch["bid"] > 0)
                   & (ch["strike"] < strike)]
        if not srows.empty:
            tgt = strike * PUT_SPREAD_SHORT_FRAC
            sr = srows.iloc[(srows["strike"] - tgt).abs().argsort().iloc[0]]
            sbid, sask = float(sr["bid"]), float(sr["ask"])
            credit = sbid + SPREAD_EXECUTION * (sask - sbid)
            short_strike = float(sr["strike"])
            px -= credit
            src += (f"; SPREAD: sold K={short_strike} same exp @ "
                    f"{credit:.2f}/sh (REAL QUOTE bid={sbid} ask={sask}), "
                    f"net debit {px:.2f}/sh")
        else:
            src += "; SPREAD short leg SKIPPED (no bid>0 strikes below long)"

    cost = px * contracts * 100
    trimmed = ""
    while contracts > 1 and cost > cash_avail:   # flagged, not hidden
        contracts -= 1
        cost = px * contracts * 100
        trimmed = f"; TRIMMED to {contracts} contracts to fit cash"
    if cost > cash_avail:
        return None, "insufficient cash for even 1 contract"
    return ({"strike": strike, "expiration": exp, "contracts": contracts,
             "short_strike": short_strike,
             "cost_ps": px}, src + trimmed)


# ------------------------------ QA / summary -------------------------------
def qa_and_summary(df, warnings):
    print("\n" + "=" * 72)
    print("QA CHECKS (spec Quality Control #1-2)")
    print("=" * 72)
    ok = True

    # 1. Cash ledger: every movement re-tallied independently each week.
    recon = df["cash_ledger_reconciled"].all()
    print(f"  cash ledger reconciles every week:       "
          f"{'PASS' if recon else 'FAIL'} ({len(df)} weeks)")
    ok &= recon

    cash_neg = (df["end_cash"] < -0.01).any()
    print(f"  cash never negative:                     "
          f"{'PASS' if not cash_neg else 'FAIL'}")
    ok &= not cash_neg

    total_sweep = df["swept_to_side_account"].sum()
    side_final = df["side_account_balance"].iloc[-1]
    # per-week sweeps are rounded to cents in the CSV; allow half a cent
    # of drift per row against the full-precision running balance
    m = abs(total_sweep - side_final) <= 0.005 * len(df) + 0.01
    print(f"  sweep sum == final side account:         "
          f"{'PASS' if m else 'FAIL'} "
          f"({total_sweep:,.2f} vs {side_final:,.2f})")
    ok &= m

    pos_sw = df[df["realized_gain_total"] > 0]
    m = np.allclose(pos_sw["swept_to_side_account"],
                    SWEEP_FRACTION * pos_sw["realized_gain_total"], atol=0.01)
    print(f"  sweep == {SWEEP_FRACTION:.0%} of positive realized gains: "
          f"{'PASS' if m else 'FAIL'}")
    ok &= m

    sold = df[df["call_action"] == "SOLD"]
    real = sold["call_pricing_source"].astype(str).str.startswith(
        "REAL QUOTE").sum()
    print(f"  call sales priced from REAL quotes:      {real}/{len(sold)}")
    pbuys = df[df["put_action"].astype(str).str.contains("BUY|ROLLED",
                                                         regex=True)]
    preal = pbuys["put_pricing_source"].astype(str).str.contains(
        "REAL QUOTE").sum()
    print(f"  put purchases priced from REAL quotes:   {preal}/{len(pbuys)}")

    print(f"  warnings during run:                     {len(warnings)}")
    for w in warnings[:10]:
        print(f"    - {w}")

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    first, last = df.iloc[0], df.iloc[-1]
    print(f"  Window:                {first['week_start']} -> "
          f"{last['week_end']}  ({len(df)} weeks)")
    print(f"  Start capital:         {START_CAPITAL:>12,.2f}")
    print(f"  End trading balance:   {last['end_total_balance']:>12,.2f}")
    print(f"  Side (swept) account:  {last['side_account_balance']:>12,.2f}")
    print(f"  End total:             {last['end_total_with_side']:>12,.2f}")
    tot_ret = last["end_total_with_side"] / START_CAPITAL - 1
    print(f"  Total return:          {tot_ret:>12.1%}")
    prem = pd.to_numeric(df["call_premium_received"],
                         errors="coerce").fillna(0)
    print(f"  Call premium collected:{prem.sum():>12,.2f} over "
          f"{(df['call_action'] == 'SOLD').sum()} weekly "
          f"sales (avg {prem[prem > 0].mean():,.2f})")
    print(f"  Cash interest earned:  "
          f"{df['cash_interest'].sum():>12,.2f}  (opt #1a, {CASH_YIELD:.1%})")
    print(f"  Weekly top-up buys:    "
          f"{df['stock_action'].astype(str).str.contains('TOPUP').sum()} "
          f"(opt #1b)")
    print(f"  Drawdown OTM sales:    "
          f"{df['call_pricing_source'].astype(str).str.contains('DRAWDOWN OTM').sum()} "
          f"(opt #2)")
    print(f"  Calls assigned:        "
          f"{df['call_outcome'].astype(str).str.startswith('ASSIGNED').sum()}")
    print(f"  Put rolls:             "
          f"{df['put_action'].str.contains('ROLLED').sum()}")
    chosen = (df["put_pricing_source"].astype(str)
              .str.extract(r"chose dte=(\d+)")[0].dropna().astype(int))
    if len(chosen):
        print(f"  Put DTEs chosen ({PUT_SCAN_MIN}-{PUT_SCAN_MAX} scan): "
              f"{sorted(chosen.tolist())}")
    print(f"  Protective exits:      "
          f"{df['put_action'].str.contains('PROTECTIVE_EXIT').sum()}")
    neg = (df['realized_gain_total'] < 0).sum()
    print(f"  Weeks w/ realized loss:{neg} of {len(df)}")
    print(f"\n  Both legs are priced from REAL file quotes (raw ThetaData"
          f"\n  exports, full window). BS-with-file-IV survives only as a"
          f"\n  per-row-flagged fallback where the exact strike is not"
          f"\n  listed. Check pricing_source per row."
          f"\n  Overall QA: {'PASS' if ok else 'FAIL -- see above'}")
    return ok


def main():
    df, warnings = run()
    df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {OUT_CSV.name}: {len(df)} weekly rows, "
          f"{len(df.columns)} columns")
    qa_and_summary(df, warnings)


if __name__ == "__main__":
    main()
