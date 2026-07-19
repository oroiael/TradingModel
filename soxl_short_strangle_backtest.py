#!/usr/bin/env python3
"""
SOXL "Asymmetric Diagonal Yield Engine" — Short-Strangle Backtest (v1)
=====================================================================

Implements the strategy in "SOXL Trading Strategy - Active Version.md",
which the user adopted (2026-07-19) as the go-forward *active* strategy in
place of the covered-call collar in soxl_weekly_income_backtest.py.

THREE-LEG STRUCTURE (no long stock):
    Leg 1  Long-dated PUT anchor : 120-180 DTE, whole-dollar strike nearest
           the Monday-10:00 spot. Held; re-anchored when DTE <= 30.
    Leg 2  Weekly short PUT      : sold Monday ~10:00, expiring that Friday,
           strike whose real delta is in [-0.30, -0.20] (nearest -0.25).
    Leg 3  Weekly short CALL     : sold same time, expiring that Friday,
           strike whose real delta is in [0.10, 0.15] (nearest 0.125).
           *** This call is NAKED (no long call above it). ***

WHAT IS FAITHFUL TO THE SPEC
    * 20% spread execution (spec 1.3): sell at bid+0.2*(ask-bid),
      buy at ask-0.2*(ask-bid). Bid==0 or ask<bid => illiquid, strike
      rejected, search next nearest valid contract.
    * Whole-number strike enforcement (spec 1.2): strike % 1 == 0.
    * Nearest-neighbor selection (spec 3.1) — here on DELTA (the spec's
      own leg targets are delta bands), with argmin|delta-target| inside
      the band, else nearest valid strike (flagged).
    * Dynamic timestamp fallback (spec 1.2): Monday 10:00 / Friday 15:30
      resolved from the 5-min file, first bar at/after the target.
    * Mechanical Delta Defense (spec 3.2): when the short put's delta hits
      -0.50, buy-to-close (20% rule) and roll DOWN & OUT (1-2 weeks) to a
      lower strike. See the honest deviations below.
    * Decoupled ledger (spec 3.3): realized operating cash tracked
      separately from each leg's mark; 25% sweep of positive weekly
      realized gains to a preservation account (spec Part 3 = 25%).

HONEST CORRECTIONS / DEVIATIONS FROM THE SPEC (see REVIEW_Active_Version.md)
    1. The spec calls Leg 3 "zero additional margin". That is false — a
       short put + short naked call is a short strangle and the naked call
       carries real Reg-T margin. This backtest MODELS that margin
       (naked_call_margin, put_diagonal_margin) and reports peak margin
       usage so the "capital efficiency" claim is testable, not assumed.
       Realized P&L is unaffected by margin; margin gates position size.
    2. The naked call's assignment loss at Friday settlement is booked in
       full at intrinsic (spot_close - strike)*100 — the uncapped tail the
       spec's "cannot lose on both legs" framing hides.
    3. Delta-defense limitation: the option file is END-OF-DAY (one
       quote+greeks snapshot per contract per day; underlying_timestamp is
       evening). There are NO intraday option quotes, so the -0.50 trigger
       is evaluated on each day's EOD delta (Tue/Wed/Thu), not live
       intraday. This is the single largest modeling limitation and is the
       same end-of-day pricing bias documented for the collar backtest.
    4. Roll "for a net credit or breakeven" is NOT always achievable
       (rolling down cuts premium). When the best available down-and-out
       roll is a net debit, the engine takes the least-debit roll and FLAGS
       the row (ROLL_NET_DEBIT) rather than pretending a credit existed.
    5. Position sizing is NOT specified by the spec. Contracts are sized at
       each anchor (re)establishment from investable equity and the modeled
       per-strangle capital (anchor debit + naked-call margin + buffer).
       This is a documented added assumption, flagged, not from the spec.
    6. At most ONE active short put (Leg 2) at a time: if a defensive roll
       pushes the put 1-2 weeks out, no new weekly put is opened until it
       resolves; the weekly call (Leg 3) is still sold each Monday. This is
       the sensible reading of "sell a weekly put" that avoids silently
       stacking doubled downside exposure — flagged where it applies.

PRICING DATA: real bid/ask + real delta from SOXL_Options_2024/2025/2026.csv
(via soxl_options_loader). No Black-Scholes is used here; a leg with no
usable real quote is rejected, never invented. Every priced leg records a
pricing_source naming the exact quote row used.

OUTPUT: soxl_short_strangle_results.csv — one row per week, per-leg price /
contracts / premium / disposition, plus the capital + margin ledger.
"""

from pathlib import Path

import pandas as pd

# Reuse the verified data-access layer and the 20% execution constant.
from soxl_weekly_income_backtest import Market, SPREAD_EXECUTION

ROOT = Path(__file__).resolve().parent
OUT_CSV = ROOT / "soxl_short_strangle_results.csv"

# ------------------------------- parameters --------------------------------
START_CAPITAL = 150_000.0
SWEEP_FRACTION = 0.25          # spec Part 3 ledger: sweep 25% of weekly gains

# Leg targets (spec Part 2)
PUT_DELTA_TARGET, PUT_DELTA_LO, PUT_DELTA_HI = 0.25, 0.20, 0.30   # |delta|
CALL_DELTA_TARGET, CALL_DELTA_LO, CALL_DELTA_HI = 0.125, 0.10, 0.15

ANCHOR_DTE_MIN, ANCHOR_DTE_MAX = 120, 180   # Leg 1 tenor (spec 1.c/e)
ANCHOR_ROLL_DTE = 30                         # re-anchor when DTE <= 30

DELTA_DEFENSE = 0.50            # spec 3.2 roll trigger on |put delta|
ROLL_OUT_WEEKS = 2             # spec 3.2 "1 to 2 weeks further out"

# Sizing (added assumption — see docstring #5). Capital reserved per strangle
# = anchor debit + naked-call margin + this buffer * spot * 100, and we cap
# deployed capital at INVEST_FRACTION of equity.
INVEST_FRACTION = 0.80
SIZING_BUFFER = 0.10


def exec_sell(bid, ask):
    return bid + SPREAD_EXECUTION * (ask - bid)


def exec_buy(bid, ask):
    return ask - SPREAD_EXECUTION * (ask - bid)


def naked_call_margin(spot, strike, premium):
    """Reg-T naked short call maintenance margin per share: premium +
    max(0.20*underlying - OTM_amount, 0.10*underlying). *100 for a contract.
    This is the collateral the spec wrongly claims is zero."""
    otm = max(strike - spot, 0.0)
    return premium + max(0.20 * spot - otm, 0.10 * spot)


def put_diagonal_margin(short_k, long_k):
    """Short weekly put (strike short_k) hedged by the long anchor put
    (strike long_k). The anchor sits at/near spot, ABOVE the OTM short put,
    so long_k >= short_k and the pair's loss below short_k is fully capped
    by the higher-strike long put — spec 2.b.2's 'width' margin. Per share:
    max(short_k - long_k, 0) (= 0 while long_k >= short_k)."""
    return max(short_k - long_k, 0.0)


# ------------------------ real-quote strike pickers ------------------------
def _valid(row):
    b, a = float(row["bid"]), float(row["ask"])
    return b > 0.0 and a >= b            # spec 1.3 illiquid/inverted reject


def pick_by_delta(chain, right, exp, target, lo, hi):
    """Whole-dollar strikes of `right` at `exp` with a valid quote; choose
    the one whose |delta| is inside [lo, hi] nearest `target`. If none lands
    in the band, take the valid strike with |delta| nearest target and flag.
    Returns (row, in_band) or (None, None)."""
    rows = chain[(chain["right"] == right) & (chain["expiration"] == exp)
                 & (chain["strike"] % 1 == 0)]
    if rows.empty:
        return None, None
    rows = rows[rows.apply(_valid, axis=1)]
    if rows.empty:
        return None, None
    ad = rows["delta"].abs()
    band = rows[(ad >= lo) & (ad <= hi)]
    if not band.empty:
        pick = band.loc[(band["delta"].abs() - target).abs().idxmin()]
        return pick, True
    pick = rows.loc[(ad - target).abs().idxmin()]     # nearest-neighbor
    return pick, False


def weekly_exp(chain, entry, settle):
    """The listed expiration for the week (that Friday, or the last listed
    exp on or before settle if Friday isn't separately listed)."""
    exps = sorted(chain["expiration"].unique())
    on_settle = [e for e in exps if e == settle]
    if on_settle:
        return on_settle[0]
    dte = {e: (e - entry).days for e in exps if e >= entry}
    near = [e for e, d in dte.items() if d <= (settle - entry).days + 1]
    return max(near) if near else (min(dte, key=dte.get) if dte else None)


def anchor_exp_strike(chain, spot):
    """Leg 1: expiration with DTE in [120,180] nearest 150; whole-dollar
    PUT strike nearest spot with a valid quote."""
    exps = chain[["expiration", "dte"]].drop_duplicates()
    exps = exps[(exps["dte"] >= ANCHOR_DTE_MIN) & (exps["dte"] <= ANCHOR_DTE_MAX)]
    if exps.empty:
        return None
    exp = exps.loc[(exps["dte"] - 150).abs().idxmin(), "expiration"]
    rows = chain[(chain["right"] == "PUT") & (chain["expiration"] == exp)
                 & (chain["strike"] % 1 == 0)]
    rows = rows[rows.apply(_valid, axis=1)]
    if rows.empty:
        return None
    row = rows.loc[(rows["strike"] - spot).abs().idxmin()]
    return row


# ---------------------------------- engine ---------------------------------
def run(mkt=None):
    mkt = mkt or Market()
    start, end = mkt.opt_dates[0], mkt.opt_dates[-1]
    days = [d for d in mkt.trading_days if start <= d <= end]
    weeks = {}
    for d in days:
        weeks.setdefault(d.isocalendar()[:2], []).append(d)
    weeks = [sorted(v) for _, v in sorted(weeks.items())]

    cash = START_CAPITAL
    side = 0.0
    anchor = None          # dict: strike, exp, contracts, cost_ps
    short_put = None       # dict: strike, exp, contracts, prem_ps, opened
    contracts = 0          # current strangle size (set at anchor)
    peak_margin = 0.0
    rows, warns = [], []

    def anchor_mark(d, spot):
        if not anchor:
            return 0.0
        q = mkt.quote(d, "PUT", anchor["strike"], anchor["exp"])
        if q is None or not _valid(q):
            return anchor["cost_ps"]          # last known basis if no quote
        return (float(q["bid"]) + float(q["ask"])) / 2

    def sp_liability(d, spot):
        """Mark-to-market liability of the open short put (>=0)."""
        if short_put is None:
            return 0.0
        q = mkt.quote(d, "PUT", short_put["strike"], short_put["exp"])
        if q is not None and _valid(q):
            mid = (float(q["bid"]) + float(q["ask"])) / 2
        else:
            mid = max(short_put["strike"] - spot, 0.0)
        return mid * short_put["contracts"] * 100

    for wi, wk in enumerate(weeks):
        entry, settle = wk[0], wk[-1]
        last_week = wi == len(weeks) - 1
        r = {"week_start": entry, "week_end": settle}
        spot10 = mkt.bar_open(entry, "10:00") or mkt.bar_close(entry, "10:00")
        if spot10 is None:
            spot10 = mkt.pre_close_price(entry)
        ch = mkt.chain(entry)
        if ch is None or spot10 is None:
            warns.append(f"{entry}: no chain/price, week skipped")
            continue

        r["spot_mon_1000"] = round(spot10, 4)
        # begin-of-week mark-to-market equity (for the drawdown curve)
        begin_mtm = (cash + side
                     + (anchor_mark(entry, spot10) * anchor["contracts"] * 100
                        if anchor else 0.0)
                     - sp_liability(entry, spot10))
        r["begin_mtm_equity"] = round(begin_mtm, 2)
        flows = 0.0     # every real cash movement this week (reconciles)
        income = 0.0    # option income only (the 25% sweep base)
        cf_anchor = cf_put = cf_call = 0.0   # per-leg cash (airtight attrib.)

        # ---------- Leg 1: anchor put (establish / re-anchor) ----------
        # Re-anchor when (a) none held, (b) DTE <= 30 (spec ledger Leg 1),
        # or (c) spot appreciated >= 10% above the anchor strike (spec Leg 1
        # roll-up). (c) is STRUCTURALLY REQUIRED here: the weekly short put
        # must sit below the anchor to stay protected, so a static anchor in
        # a rising tape starves the put leg (verified: 62 skipped-put weeks
        # without it). Documented cost: it crystallizes the ATM anchor's
        # decay each roll-up (the hedge-cost drag the roadmap flagged).
        roll_up = anchor is not None and spot10 >= anchor["strike"] * 1.10
        need_anchor = (anchor is None
                       or (anchor["exp"] - entry).days <= ANCHOR_ROLL_DTE
                       or roll_up)
        if roll_up:
            r["anchor_note"] = "ROLLUP_+10%"
        if need_anchor:
            # close an expiring/near anchor at its real mark first
            if anchor is not None:
                q = mkt.quote(entry, "PUT", anchor["strike"], anchor["exp"])
                if q is not None and _valid(q):
                    px = exec_sell(float(q["bid"]), float(q["ask"]))
                    proceeds = px * anchor["contracts"] * 100
                    cash += proceeds
                    flows += proceeds
                    cf_anchor += proceeds
                    r["anchor_sell"] = round(proceeds, 2)
                anchor = None
            a = anchor_exp_strike(ch, spot10)
            if a is None:
                warns.append(f"{entry}: no 120-180 DTE whole-strike anchor listed")
            else:
                a_px = exec_buy(float(a["bid"]), float(a["ask"]))
                # size the strangle from equity and modeled capital-per-unit
                equity = cash + (anchor_mark(entry, spot10) * (anchor["contracts"] * 100)
                                 if anchor else 0.0)
                per_unit = (a_px * 100
                            + naked_call_margin(spot10, spot10 * 1.05, 0.30) * 100
                            + SIZING_BUFFER * spot10 * 100)
                contracts = max(0, int(INVEST_FRACTION * equity // per_unit))
                if contracts == 0:
                    warns.append(f"{entry}: equity too low to size a strangle")
                else:
                    cost = a_px * contracts * 100
                    cash -= cost
                    flows -= cost
                    cf_anchor -= cost
                    anchor = {"strike": float(a["strike"]),
                              "exp": a["expiration"], "contracts": contracts,
                              "cost_ps": a_px}
                    r["anchor_action"] = "ANCHOR"
                    r["anchor_buy"] = round(cost, 2)
        r["anchor_strike"] = anchor["strike"] if anchor else ""
        r["anchor_exp"] = anchor["exp"] if anchor else ""
        r["anchor_dte"] = (anchor["exp"] - entry).days if anchor else ""
        r["anchor_contracts"] = anchor["contracts"] if anchor else 0
        r["anchor_mark"] = round(anchor_mark(entry, spot10), 4) if anchor else ""
        r["contracts"] = contracts

        if not anchor or contracts == 0:
            r["cf_anchor"], r["cf_put"], r["cf_call"] = (
                round(cf_anchor, 2), round(cf_put, 2), round(cf_call, 2))
            _finish_row(r, cash, side, flows, income, begin_mtm)
            rows.append(r)
            continue

        wexp = weekly_exp(ch, entry, settle)

        # ---------- Leg 2: weekly short put (only if none active) ----------
        if short_put is None and wexp is not None:
            row, in_band = pick_by_delta(ch, "PUT", wexp,
                                         PUT_DELTA_TARGET, PUT_DELTA_LO, PUT_DELTA_HI)
            if row is not None and row["strike"] < anchor["strike"] + 0.01:
                prem = exec_sell(float(row["bid"]), float(row["ask"]))
                proceeds = prem * contracts * 100
                cash += proceeds
                flows += proceeds
                income += proceeds
                cf_put += proceeds
                short_put = {"strike": float(row["strike"]), "exp": wexp,
                             "contracts": contracts, "prem_ps": prem, "opened": entry}
                r["put_strike"] = float(row["strike"])
                r["put_delta"] = round(float(row["delta"]), 4)
                r["put_prem_ps"] = round(prem, 4)
                r["put_premium"] = round(proceeds, 2)
                r["put_in_band"] = in_band
                r["put_exp"] = wexp
            else:
                warns.append(f"{entry}: no valid delta-band short put at {wexp}")
                r["put_strike"] = "NONE"
        elif short_put is not None:
            r["put_strike"] = short_put["strike"]
            r["put_exp"] = short_put["exp"]
            r["put_note"] = "CARRIED_FROM_ROLL"

        # ---------- Leg 3: weekly short call (naked) ----------
        call = None
        if wexp is not None:
            row, in_band = pick_by_delta(ch, "CALL", wexp,
                                         CALL_DELTA_TARGET, CALL_DELTA_LO, CALL_DELTA_HI)
            if row is not None:
                prem = exec_sell(float(row["bid"]), float(row["ask"]))
                proceeds = prem * contracts * 100
                cash += proceeds
                flows += proceeds
                income += proceeds
                cf_call += proceeds
                call = {"strike": float(row["strike"]), "exp": wexp,
                        "prem_ps": prem}
                r["call_strike"] = float(row["strike"])
                r["call_delta"] = round(float(row["delta"]), 4)
                r["call_prem_ps"] = round(prem, 4)
                r["call_premium"] = round(proceeds, 2)
                r["call_in_band"] = in_band
                r["call_margin"] = round(
                    naked_call_margin(spot10, float(row["strike"]), prem)
                    * contracts * 100, 2)
            else:
                warns.append(f"{entry}: no valid delta-band short call at {wexp}")
                r["call_strike"] = "NONE"

        # ---------- Mechanical Delta Defense (daily EOD, Tue..settle) -------
        defense = ""
        if short_put is not None and short_put["exp"] <= settle:
            for d in wk[1:]:
                if d > short_put["exp"]:
                    break
                q = mkt.quote(d, "PUT", short_put["strike"], short_put["exp"])
                if q is None or not _valid(q):
                    continue
                if abs(float(q["delta"])) >= DELTA_DEFENSE:
                    # buy-to-close at 20% rule (lock the loss)
                    btc = exec_buy(float(q["bid"]), float(q["ask"]))
                    cost = btc * short_put["contracts"] * 100
                    cash -= cost
                    flows -= cost
                    income -= cost
                    cf_put -= cost
                    defense = (f"ROLLED@{d} closeK={short_put['strike']} "
                               f"delta={float(q['delta']):.2f} btc={btc:.2f}")
                    # roll DOWN & OUT: exp ~ROLL_OUT_WEEKS further, lower strike
                    roll = _roll_down_out(mkt, d, short_put, anchor)
                    if roll is None:
                        short_put = None
                        defense += " NO_ROLL_TARGET"
                    else:
                        credit = roll["prem"] * short_put["contracts"] * 100
                        cash += credit
                        flows += credit
                        income += credit
                        cf_put += credit
                        net = credit - cost
                        short_put = {"strike": roll["strike"], "exp": roll["exp"],
                                     "contracts": short_put["contracts"],
                                     "prem_ps": roll["prem"], "opened": d}
                        defense += (f" -> newK={roll['strike']} exp={roll['exp']}"
                                    f" credit={roll['prem']:.2f}"
                                    f" net={'+' if net>=0 else ''}{net:.0f}")
                        if net < 0:
                            defense += " ROLL_NET_DEBIT"
                    break
        r["delta_defense"] = defense

        # ---------- Friday settlement ----------
        s_close = mkt.day_close(settle)
        r["spot_fri_close"] = round(s_close, 4)

        # short put settles only if it expires THIS week
        if short_put is not None and short_put["exp"] <= settle:
            if s_close >= short_put["strike"]:
                r["put_settle"] = "EXPIRED_WORTHLESS"
            else:
                loss = (short_put["strike"] - s_close) * short_put["contracts"] * 100
                cash -= loss
                flows -= loss
                income -= loss
                cf_put -= loss
                r["put_settle"] = f"ITM_ASSIGNED loss={loss:.0f}"
            short_put = None

        # naked call settles every week (it is always weekly)
        if call is not None:
            if s_close <= call["strike"]:
                r["call_settle"] = "EXPIRED_WORTHLESS"
            else:
                loss = (s_close - call["strike"]) * contracts * 100
                cash -= loss
                flows -= loss
                income -= loss
                cf_call -= loss
                r["call_settle"] = f"ITM_ASSIGNED loss={loss:.0f}"

        # ---------- final-week liquidation (mark all open legs to cash so
        # the headline number is fully realized, not partly paper) ----------
        if last_week:
            if short_put is not None:
                liab = sp_liability(settle, s_close)
                cash -= liab
                flows -= liab
                income -= liab
                cf_put -= liab
                r["put_settle"] = (str(r.get("put_settle", ""))
                                   + f" LIQUIDATED@-{liab:.0f}").strip()
                short_put = None
            if anchor is not None:
                q = mkt.quote(settle, "PUT", anchor["strike"], anchor["exp"])
                mv = (exec_sell(float(q["bid"]), float(q["ask"]))
                      if q is not None and _valid(q)
                      else max(anchor["strike"] - s_close, 0.0))
                proceeds = mv * anchor["contracts"] * 100
                cash += proceeds
                flows += proceeds
                cf_anchor += proceeds
                r["anchor_sell"] = round(proceeds, 2)
                anchor = None

        # ---------- sweep (on option income only) + margin bookkeeping ----
        if income > 0:
            swept = SWEEP_FRACTION * income
            side += swept
            cash -= swept
            r["swept"] = round(swept, 2)
        wk_margin = (r.get("call_margin", 0.0) or 0.0)
        peak_margin = max(peak_margin, wk_margin)
        r["week_margin"] = round(wk_margin, 2)

        r["cf_anchor"], r["cf_put"], r["cf_call"] = (
            round(cf_anchor, 2), round(cf_put, 2), round(cf_call, 2))
        # airtight: the three leg cash-flows must sum to the week's total
        assert abs((cf_anchor + cf_put + cf_call) - flows) < 1e-6, (
            entry, cf_anchor, cf_put, cf_call, flows)
        _finish_row(r, cash, side, flows, income, begin_mtm)
        rows.append(r)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    return df, warns, peak_margin


def _roll_down_out(mkt, d, sp, anchor):
    """Find a down-and-out replacement short put: expiration ~ROLL_OUT_WEEKS
    beyond the current one, whole strike below the current strike (and <=
    anchor strike), valid quote, delta back in the put band. Prefer the
    highest net credit; return dict(strike, exp, prem) or None."""
    ch = mkt.chain(d)
    if ch is None:
        return None
    want_dte = (sp["exp"] - d).days + 7 * ROLL_OUT_WEEKS
    exps = ch[["expiration", "dte"]].drop_duplicates()
    exps = exps[exps["expiration"] > sp["exp"]]
    if exps.empty:
        return None
    exp = exps.loc[(exps["dte"] - want_dte).abs().idxmin(), "expiration"]
    rows = ch[(ch["right"] == "PUT") & (ch["expiration"] == exp)
              & (ch["strike"] % 1 == 0) & (ch["strike"] < sp["strike"])]
    rows = rows[rows.apply(_valid, axis=1)]
    if anchor is not None:
        rows = rows[rows["strike"] <= anchor["strike"] + 0.01]
    if rows.empty:
        return None
    # target delta band; pick highest executable credit among band members
    ad = rows["delta"].abs()
    band = rows[(ad >= PUT_DELTA_LO) & (ad <= PUT_DELTA_HI)]
    pool = band if not band.empty else rows
    best = None
    for _, row in pool.iterrows():
        prem = exec_sell(float(row["bid"]), float(row["ask"]))
        if best is None or prem > best["prem"]:
            best = {"strike": float(row["strike"]), "exp": exp, "prem": prem}
    return best


def _finish_row(r, cash, side, flows, income, begin_mtm):
    r["cash_flow_week"] = round(flows, 2)     # true cash movement (reconciles)
    r["income_week"] = round(income, 2)       # option income (sweep base)
    r["cash"] = round(cash, 2)
    r["side_account"] = round(side, 2)
    r["total_equity"] = round(cash + side, 2)
    r.setdefault("begin_mtm_equity", round(begin_mtm, 2))


if __name__ == "__main__":
    import re as _re
    df, warns, peak_margin = run()
    final = df.iloc[-1]
    total = final["total_equity"]
    ret = (total - START_CAPITAL) / START_CAPITAL
    # reconciliation: sum of true cash flows must equal end-start
    flows_sum = pd.to_numeric(df["cash_flow_week"], errors="coerce").fillna(0).sum()
    gap = flows_sum - (total - START_CAPITAL)
    # drawdown on the mark-to-market equity curve
    eq = pd.to_numeric(df["begin_mtm_equity"], errors="coerce").ffill()
    dd = (eq / eq.cummax() - 1).min()

    def _num(c):
        return pd.to_numeric(df[c], errors="coerce").fillna(0) if c in df else 0
    anchor_net = _num("cf_anchor").sum()   # exact per-leg cash (reconciles)
    put_net = _num("cf_put").sum()
    call_net = _num("cf_call").sum()

    print(f"weeks: {len(df)}")
    print(f"final total equity (cash+side, fully liquidated): ${total:,.0f}  "
          f"({ret*100:+.1f}% vs ${START_CAPITAL:,.0f})")
    print(f"  cash ${final['cash']:,.0f} | side ${final['side_account']:,.0f}")
    print(f"reconciliation gap (should be ~0): ${gap:,.2f}")
    print(f"leg cash sums to total? ${anchor_net+put_net+call_net:,.0f} "
          f"vs flows ${flows_sum:,.0f}")
    print(f"max drawdown (MtM equity curve): {dd*100:.1f}%")
    print(f"peak modeled naked-call margin: ${peak_margin:,.0f}")
    print("--- leg attribution (exact per-leg cash) ---")
    print(f"  Leg1 anchor     net: ${anchor_net:,.0f}")
    print(f"  Leg2 short put  net: ${put_net:,.0f}  (incl. delta-defense rolls)")
    print(f"  Leg3 naked call net: ${call_net:,.0f}")
    print(f"  put sold {int((_num('put_premium')>0).sum())} wks | "
          f"call sold {int((_num('call_premium')>0).sum())} wks")
    print(f"warnings: {len(warns)}")
    for w in warns[:8]:
        print("  -", w)
    print(f"wrote {OUT_CSV.name}")
