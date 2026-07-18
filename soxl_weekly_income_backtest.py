#!/usr/bin/env python3
"""
SOXL Weekly-Income Covered Call + Long-Dated Put Backtest  (Version 1)
======================================================================

Implements the "Trade to Model" in "Option Trading Project for SOXL.md":

    Part 1: Every Monday by 10:00 sell a call at the whole-number strike
            nearest to the share COST BASIS (user revision 2026-07-18;
            spec 2.a.i originally said nearest OTM to the current price),
            expiring that Friday.
    Part 2: Hold long SOXL shares (75% of capital, whole shares); shares only
            leave via call assignment or put exercise/sale.
    Part 3: Hold a long put, strike nearest whole dollar to the underlying
            purchase price, expiring ~6 months out (120-180 days), with the
            roll-up rule (+20%, upside only -- user revision of the
            original 10% either-way rule) and the 15% protective-exit
            rule.

Capital: start $150,000; invest 75%; sweep 25% of each week's positive
realized gain to a separate account; reinvest the remaining 75%.

----------------------------------------------------------------------
DATA LIMITATION -- READ THIS (required disclosure per spec parameter #7)
----------------------------------------------------------------------
The option file (SOXL_Master_Cleaned.csv) contains ONLY snapshots with
15-60 days to expiration (verified by data_evaluation.py).  It therefore has
NO market quotes for either leg of this trade:

    * the Monday->Friday weekly call (4 DTE)         -- nearest listed
      expiration on any Monday snapshot is 17-18 DTE;
    * the 120-180 DTE long put                        -- max DTE is 60.

Per spec parameter #7 those legs are priced with Black-Scholes using the
IMPLIED VOL FROM THE DATA FILE (same/nearest strike, nearest available
expiration on the same trade date).  Every priced leg in the output CSV
carries a `pricing_source` field naming the exact IV row used
(strike/expiration/DTE), so every estimate is auditable.  Known biases:

    * weekly call: 17-18 DTE IV applied to a 4 DTE option (term structure
      compressed);
    * long put: <=60 DTE IV applied to a ~180 DTE option;
    * option snapshots are end-of-day; trades happen 09:30/10:00 Monday.

Bid/ask handling (spec parameter #6): each BS mid is bracketed with the
relative bid/ask spread of the IV-source row from the file, then
    sell (write)  at synthetic bid + 20% of the spread,
    buy  (long)   at synthetic ask - 20% of the spread.

Long-put expirations beyond the data window are assumed to be the standard
third-Friday monthlies (flagged "assumed listing" in pricing_source).

Risk-free rate: constant 4.5% (documented assumption; not in the data files).

If 0-14 DTE and 61-200 DTE option snapshots can be provided, every
BS-estimated price in this backtest can be replaced with real quotes.
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

import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
STOCK_CSV = ROOT / "SOXL_5min_3Years.csv"
OPTION_CSV = ROOT / "SOXL_Master_Cleaned.csv"
OUT_CSV = ROOT / "soxl_weekly_backtest_results.csv"

# ------------------------- documented assumptions --------------------------
RISK_FREE = 0.045          # constant r for BS (not in data files)
START_CAPITAL = 150_000.0
INVEST_FRACTION = 0.75     # spec Capital #2
SWEEP_FRACTION = 0.10      # user revision 2026-07-18 (spec Capital #3 was 25%)
SPREAD_EXECUTION = 0.20    # spec parameter #6
PUT_TARGET_DAYS = 182      # "six months"
PUT_MIN_DAYS, PUT_MAX_DAYS = 120, 180
ROLL_MOVE = 0.20           # roll UP only, at +20% (user direction 2026-07-18;
                           # originally spec 2.c.iv: 10% either direction)
EXIT_DROP = 0.15           # spec 2.c.v


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


def third_friday(year, month):
    d = date(year, month, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def pick_put_expiration(entry):
    """Nearest assumed third-Friday monthly to ~6 months out, 120-180 DTE."""
    cands = []
    for add in range(3, 9):
        y, m = entry.year, entry.month + add
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        tf = third_friday(y, m)
        dte = (tf - entry).days
        if PUT_MIN_DAYS <= dte <= PUT_MAX_DAYS:
            cands.append((abs(dte - PUT_TARGET_DAYS), tf))
    if not cands:  # fall back to the third Friday closest to target
        for add in range(3, 9):
            y, m = entry.year, entry.month + add
            y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
            tf = third_friday(y, m)
            cands.append((abs((tf - entry).days - PUT_TARGET_DAYS), tf))
    return min(cands)[1]


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

        opt = pd.read_csv(OPTION_CSV, low_memory=False,
                          usecols=["expiration", "strike", "right", "bid",
                                   "ask", "implied_vol", "trade_date", "dte",
                                   "underlying_price"])
        opt["trade_date"] = pd.to_datetime(opt["trade_date"]).dt.date
        opt["expiration"] = pd.to_datetime(opt["expiration"]).dt.date
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

    # ---- options ----
    def chain(self, d):
        return self.opt_by_day.get(d)

    def call_strike_nearest(self, d, target):
        """Whole-number CALL strike nearest to `target` (user revision
        2026-07-18: anchor the weekly call to the share cost basis, not the
        current price).  The $1 whole-number grid is verified in the data
        (spec parameter #5).  The daily chain snapshot only lists strikes
        within ~+/-10% of that day's price, so when the basis-anchored
        strike falls outside the listed band it is still used -- real SOXL
        weeklies list far wider than the snapshot -- and the note flags
        that its IV comes from the nearest listed strike instead.
        Returns (strike, note)."""
        ch = self.chain(d)
        if ch is None:
            return None, ""
        k = float(math.floor(target + 0.5))
        ks = ch.loc[(ch["right"] == "CALL") & (ch["strike"] % 1 == 0),
                    "strike"]
        note = ""
        if not ks.empty and k not in set(ks):
            note = (f"; K={k} not in snapshot chain ({ks.min()}-{ks.max()} "
                    f"listed, ~+/-10% band artifact); IV taken from nearest "
                    f"listed strike")
        return k, note

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
def run():
    mkt = Market()

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
            if put else 0.0)
        r["begin_cash"] = round(cash, 2)
        begin_cash = cash
        r["begin_total_balance"] = round(cash + begin_positions, 2)
        r["begin_side_account"] = round(side_account, 2)
        realized = 0.0
        flows = 0.0   # independent tally of every cash movement (QA)

        # ---- Part 2: underlying entry / top-up ----
        r.update({"stock_action": "HELD", "stock_buy_units": 0,
                  "stock_buy_price": "", "stock_buy_cost": ""})
        if shares < 100:   # cannot support a single covered call
            target = INVEST_FRACTION * (cash + shares * s_entry)
            buy = int((target - shares * s_entry) // s_entry)
            if buy > 0:
                cost = buy * s_entry
                cash -= cost
                flows -= cost
                basis = ((shares * basis) + cost) / (shares + buy)
                shares += buy
                r.update({"stock_action": "BUY", "stock_buy_units": buy,
                          "stock_buy_price": round(s_entry, 4),
                          "stock_buy_cost": round(cost, 2)})

        # ---- Part 3: long put purchase (new position or post-expiry) ----
        r.update({"put_action": "HELD",
                  "put_open_price": "", "put_open_cost": "",
                  "put_sell_price": "", "put_sell_proceeds": "",
                  "put_roll_price": "", "put_roll_cost": "",
                  "put_realized_pnl": "", "put_pricing_source": ""})
        if put is None and shares >= 100:
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
        r["put_strike"] = put["strike"] if put else ""
        r["put_expiration"] = put["expiration"] if put else ""
        r["put_contracts"] = put["contracts"] if put else 0

        # ---- Part 1: sell the weekly call at 10:00 ----
        # Strike anchored to the share cost basis (user revision 2026-07-18),
        # priced off the 10:00 underlying.
        contracts = shares // 100
        k, capped = (mkt.call_strike_nearest(entry, basis)
                     if contracts else (None, ""))
        call_premium = 0.0
        r.update({"call_strike": "", "call_contracts": 0,
                  "call_sell_price": "", "call_premium_received": "",
                  "call_pricing_source": ""})
        if contracts > 0 and k is not None:
            t = max((settle - entry).days, 1) / 365.0
            got = mkt.iv_and_spread(entry, "CALL", k, want_long_dte=False)
            if got:
                iv, spread, src = got
                mid = bs_price("CALL", s_1000, k, t, iv)
                px = mkt.exec_price(mid, spread, "SELL")
                call_premium = px * contracts * 100
                cash += call_premium
                flows += call_premium
                realized += call_premium
                r.update({
                    "call_strike": k, "call_contracts": contracts,
                    "call_sell_price": round(px, 4),
                    "call_premium_received": round(call_premium, 2),
                    "call_pricing_source":
                        f"BS est (no <=7-DTE quotes in file); {src}; "
                        f"exp={settle} assumed weekly; K anchored to "
                        f"basis {basis:.2f}{capped}"})
            else:
                warnings.append(f"{entry}: no usable call IV at K={k}")
        elif contracts > 0:
            warnings.append(f"{entry}: no whole-number call strikes listed; "
                            f"NO CALL SOLD this week")

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

            if move <= -EXIT_DROP:
                # spec 2.c.v: only exit if the put's gain covers the loss
                stock_loss = (basis - s_1530) * shares
                if put_gain >= stock_loss:
                    px = mkt.exec_price(val_ps, put_spread(mkt, put, settle),
                                        "SELL")
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
                    shares, put, exited = 0, None, True
                else:
                    r["put_action"] = (r["put_action"] + "+HELD_15PCT_CHECK"
                                       ).replace("HELD+", "")
            elif move >= ROLL_MOVE and not exited:
                # roll UP only (user direction 2026-07-18): downside is
                # handled solely by the 15% protective-exit check above
                px = mkt.exec_price(val_ps, put_spread(mkt, put, settle),
                                    "SELL")
                proceeds = px * put["contracts"] * 100
                pnl = proceeds - put["cost_ps"] * put["contracts"] * 100
                cash += proceeds
                flows += proceeds
                realized += pnl
                old = f"K={put['strike']} exp={put['expiration']}"
                new_put, note = open_put(mkt, settle, s_1530,
                                         put["contracts"] * 100, cash)
                r.update({"put_action": r["put_action"].replace(
                              "HELD", "").replace("BUY", "BUY+") + "ROLLED",
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

        # ---- call settlement at Friday close ----
        r["friday_close_price"] = round(s_close, 4)
        r["call_outcome"] = ""
        if r["call_contracts"]:
            if not exited and s_close > r["call_strike"]:
                assigned = r["call_contracts"] * 100
                stock_pnl = (r["call_strike"] - basis) * assigned
                cash += r["call_strike"] * assigned
                flows += r["call_strike"] * assigned
                shares -= assigned
                realized += stock_pnl
                r.update({"call_outcome": "ASSIGNED",
                          "stock_action": (r["stock_action"] + "+ASSIGNED"
                                           ).replace("HELD+", ""),
                          "stock_assigned_units": assigned,
                          "stock_realized_pnl": round(stock_pnl, 2)})
            elif exited:
                # shares already sold at 15:30; call settles vs the close
                if s_close > r["call_strike"]:
                    owe = (s_close - r["call_strike"]) * \
                        r["call_contracts"] * 100
                    cash -= owe
                    flows -= owe
                    realized -= owe
                    r["call_outcome"] = "BOUGHT_BACK_AT_INTRINSIC"
                else:
                    r["call_outcome"] = "EXPIRED_WORTHLESS"
            else:
                r["call_outcome"] = "EXPIRED_WORTHLESS"
        r["call_pnl"] = round(call_premium
                              - (0 if r["call_outcome"] !=
                                 "BOUGHT_BACK_AT_INTRINSIC"
                                 else (s_close - r["call_strike"])
                                 * r["call_contracts"] * 100), 2) \
            if r["call_contracts"] else ""

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
        r["end_shares"] = shares
        r["end_share_value"] = round(shares * s_close, 2)
        r["end_put_value"] = round(put_val, 2)
        r["end_cash"] = round(cash, 2)
        end_bal = cash + shares * s_close + put_val
        r["end_total_balance"] = round(end_bal, 2)
        r["end_total_with_side"] = round(end_bal + side_account, 2)
        rows.append(r)

        if cash < 0:
            warnings.append(f"{settle}: cash went negative ({cash:,.2f})")

    return pd.DataFrame(rows), warnings


def put_spread(mkt, put, d):
    got = mkt.iv_and_spread(d, "PUT", put["strike"], want_long_dte=True)
    return got[1] if got else 0.14  # file-wide median spread as last resort


def put_value(mkt, put, d, spot):
    """Mark the held put with BS using the file's IV nearest strike/longest
    DTE on day d. Returns (PER-SHARE value, source string)."""
    t = max((put["expiration"] - d).days, 0) / 365.0
    got = mkt.iv_and_spread(d, "PUT", put["strike"], want_long_dte=True)
    if got is None:
        return (max(put["strike"] - spot, 0.0),
                "intrinsic only (no IV row)")
    iv, _, src = got
    mid = bs_price("PUT", spot, put["strike"], t, iv)
    return mid, f"BS est; {src}"


def open_put(mkt, d, spot, shares, cash_avail):
    """Buy protective puts: nearest whole-dollar strike to `spot`, assumed
    third-Friday expiration ~6 months out, BS-priced with file IV
    (longest DTE available, <=60 -- disclosed)."""
    contracts = shares // 100
    if contracts == 0:
        return None, "fewer than 100 shares"
    strike = float(round(spot))
    exp = pick_put_expiration(d)
    got = mkt.iv_and_spread(d, "PUT", strike, want_long_dte=True)
    if got is None:
        return None, "no put IV rows on trade date"
    iv, spread, src = got
    t = (exp - d).days / 365.0
    mid = bs_price("PUT", spot, strike, t, iv)
    px = mkt.exec_price(mid, spread, "BUY")
    cost = px * contracts * 100
    trimmed = ""
    while contracts > 1 and cost > cash_avail:   # flagged, not hidden
        contracts -= 1
        cost = px * contracts * 100
        trimmed = f"; TRIMMED to {contracts} contracts to fit cash"
    if cost > cash_avail:
        return None, "insufficient cash for even 1 contract"
    return ({"strike": strike, "expiration": exp, "contracts": contracts,
             "cost_ps": px},
            f"BS est (no 120-180 DTE quotes in file); {src}; "
            f"exp={exp} assumed 3rd-Friday listing, dte={(exp-d).days}"
            + trimmed)


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

    est = df["call_pricing_source"].astype(str).str.contains("BS est").sum()
    print(f"  weekly-call rows BS-estimated:           {est}/"
          f"{(df['call_contracts'] > 0).sum()} "
          f"(expected ALL -- file has no <=7 DTE quotes)")

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
    print(f"  Call premium collected:{prem.sum():>12,.2f} "
          f"(avg {prem[prem > 0].mean():,.2f}/wk on "
          f"{(prem > 0).sum()} weeks)")
    print(f"  Weeks assigned:        {(df['call_outcome'] == 'ASSIGNED').sum()}")
    print(f"  Put rolls:             "
          f"{df['put_action'].str.contains('ROLLED').sum()}")
    print(f"  Protective exits:      "
          f"{df['put_action'].str.contains('PROTECTIVE_EXIT').sum()}")
    neg = (df['realized_gain_total'] < 0).sum()
    print(f"  Weeks w/ realized loss:{neg} of {len(df)}")
    print(f"\n  ALL PRICES for the weekly call and long put are Black-Scholes"
          f"\n  estimates using IV from SOXL_Master_Cleaned.csv (see header"
          f"\n  disclosure) because the file contains only 15-60 DTE quotes."
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
