#!/usr/bin/env python3
"""
No-Underlying Lab -- what happens if we never hold SOXL shares?
===============================================================

The covered-call strategy's whole architecture (assignment, basis-anchored
strikes, protective puts, hedge-priority sizing) exists because we own
shares.  This lab tests two ways to run the same weekly-income idea with
NO stock position, on the same real quotes and the same window, plus a
buy-and-hold reference:

  A) CSP  -- cash-secured weekly short puts. Every Monday sell the listed
     weekly put at the strike nearest spot, sized so cash fully covers
     assignment (strike x 100 x contracts). Cash earns CASH_YIELD. If the
     Friday close is below the strike the loss is cash-settled (we never
     take delivery -- that is the point of the test) and the position is
     re-sold the next Monday.

  B) PMCC -- "poor man's covered call": stock replaced by a long call.
     Buy the listed call nearest spot at the cheapest cost-per-day in the
     120-180 DTE window (same scan logic as the put leg), hold it to
     expiration, and sell weekly calls against it at the nearest listed
     strike >= spot. Weekly short calls are cash-settled against the long
     call's intrinsic, so no shares ever change hands.

  C) SOXL buy-and-hold, for reference.

Sizing: both option strategies commit the same INVEST_FRACTION of the
balance as the share strategy does, so the comparison is capital-matched.
All prices are REAL bid/ask with the spec #6 20%-of-spread execution rule;
any BS fallback is impossible here because a missing quote simply means the
trade is skipped and flagged.

Output: printed table + qa/no_underlying_report.txt
"""

import io
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import soxl_weekly_income_backtest as bt

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "qa" / "no_underlying_report.txt"
_lines = []


def emit(m=""):
    print(m)
    _lines.append(str(m))


def weeks_of(mkt):
    lo, hi = mkt.opt_dates[0], mkt.opt_dates[-1]
    days = [d for d in mkt.trading_days if lo <= d <= hi]
    wk = {}
    for d in days:
        wk.setdefault(d.isocalendar()[:2], []).append(d)
    return [sorted(v) for _, v in sorted(wk.items())]


def stats(bal, label, extra=None):
    bal = pd.Series(bal)
    ret = bal.pct_change().dropna()
    dd = bal / bal.cummax() - 1
    n = len(bal)
    out = {
        "strategy": label,
        "end": round(bal.iloc[-1], 0),
        "ret%": round(100 * (bal.iloc[-1] / bt.START_CAPITAL - 1), 1),
        "CAGR%": round(100 * ((bal.iloc[-1] / bt.START_CAPITAL)
                              ** (52 / n) - 1), 1),
        "maxDD%": round(100 * dd.min(), 1),
        "vol%": round(100 * ret.std() * 52 ** 0.5, 1),
        "worstWk%": round(100 * ret.min(), 1),
    }
    out["CAGR/|DD|"] = round(out["CAGR%"] / abs(out["maxDD%"]), 2) \
        if out["maxDD%"] else float("nan")
    if extra:
        out.update(extra)
    return out


def weekly_expiration(mkt, d):
    """The real listed expiration for the week containing d (Friday, or
    Thursday on holiday weeks)."""
    friday = d + timedelta(days=(4 - d.weekday()) % 7)
    got = mkt.expiration_near(d, (friday - d).days)
    if got is None:
        return None
    exp, _ = got
    return exp if exp <= friday else None


def sell_leg(row):
    b, a = float(row["bid"]), float(row["ask"])
    return b + bt.SPREAD_EXECUTION * (a - b)


def buy_leg(row):
    b, a = float(row["bid"]), float(row["ask"])
    return a - bt.SPREAD_EXECUTION * (a - b)


# --------------------------------------------------------------------------
def run_csp(mkt, invest=0.85):
    """A) cash-secured weekly short puts, never take delivery."""
    cash = bt.START_CAPITAL
    bal, prev, skipped, weeks_sold, assigned = [], None, 0, 0, 0
    prem_total = loss_total = 0.0
    for wk in weeks_of(mkt):
        entry, settle = wk[0], wk[-1]
        s0 = mkt.bar_open(entry, "10:00")
        if s0 is None:
            continue
        cash += cash * bt.CASH_YIELD * ((settle - (prev or entry)).days) / 365
        exp = weekly_expiration(mkt, entry)
        ch = mkt.chain(entry)
        if exp is not None and ch is not None:
            rows = ch[(ch["right"] == "PUT") & (ch["expiration"] == exp)
                      & (ch["strike"] % 1 == 0) & (ch["ask"] > 0)]
            if not rows.empty:
                row = rows.iloc[(rows["strike"] - s0).abs().argsort().iloc[0]]
                k = float(row["strike"])
                # contracts fully cash-secured within the invest budget
                n = int((invest * cash) // (k * 100))
                if n > 0:
                    px = sell_leg(row)
                    prem = px * n * 100
                    cash += prem
                    prem_total += prem
                    weeks_sold += 1
                    s_close = mkt.day_close(settle)
                    if s_close < k:          # cash-settle the assignment
                        loss = (k - s_close) * n * 100
                        cash -= loss
                        loss_total += loss
                        assigned += 1
                else:
                    skipped += 1
            else:
                skipped += 1
        else:
            skipped += 1
        bal.append(cash)
        prev = settle
    return bal, {"weeks_sold": weeks_sold, "assigned": assigned,
                 "skipped": skipped, "premium": round(prem_total, 0),
                 "settle_losses": round(loss_total, 0)}


# --------------------------------------------------------------------------
def run_pmcc(mkt, invest=0.85):
    """B) long 120-180 DTE call as stock replacement + weekly short calls."""
    cash = bt.START_CAPITAL
    long_call = None      # dict(strike, exp, contracts, cost_ps)
    bal, prev, sold_weeks, skipped = [], None, 0, 0
    prem_total = 0.0
    for wk in weeks_of(mkt):
        entry, settle = wk[0], wk[-1]
        s0 = mkt.bar_open(entry, "10:00")
        s_entry = mkt.bar_close(entry, "09:30")
        if s0 is None or s_entry is None:
            continue
        cash += cash * bt.CASH_YIELD * ((settle - (prev or entry)).days) / 365
        ch = mkt.chain(entry)

        # settle an expired long call at intrinsic
        if long_call and long_call["exp"] <= settle:
            intr = max(mkt.day_close(settle) - long_call["strike"], 0.0)
            cash += intr * long_call["contracts"] * 100
            long_call = None

        # open / replace the long call: cheapest cost-per-day, 120-180 DTE
        if long_call is None and ch is not None:
            best = None
            exps = ch[["expiration", "dte"]].drop_duplicates()
            exps = exps[(exps["dte"] >= bt.PUT_SCAN_MIN)
                        & (exps["dte"] <= bt.PUT_SCAN_MAX)]
            for exp, dte in exps.itertuples(index=False):
                rows = ch[(ch["right"] == "CALL") & (ch["expiration"] == exp)
                          & (ch["strike"] % 1 == 0) & (ch["ask"] > 0)]
                if rows.empty:
                    continue
                row = rows.iloc[(rows["strike"]
                                 - s_entry).abs().argsort().iloc[0]]
                px = buy_leg(row)
                cd = px / int(dte)
                if best is None or cd < best[0]:
                    best = (cd, float(row["strike"]), exp, px)
            if best:
                _, k, exp, px = best
                # EXPOSURE-matched sizing: the long call controls 100 shares
                # per contract, so match the share strategy's notional
                # (invest x balance / spot), NOT the premium budget --
                # sizing by premium would lever this ~6x and is not a
                # like-for-like comparison.
                n = int((invest * cash) / (s_entry * 100))
                if n > 0 and px * n * 100 <= cash:
                    cash -= px * n * 100
                    long_call = {"strike": k, "exp": exp, "contracts": n,
                                 "cost_ps": px}

        # sell the weekly call against it (never more than the long leg)
        if long_call:
            exp_w = weekly_expiration(mkt, entry)
            if exp_w is not None and ch is not None:
                rows = ch[(ch["right"] == "CALL")
                          & (ch["expiration"] == exp_w)
                          & (ch["strike"] % 1 == 0) & (ch["ask"] > 0)
                          & (ch["strike"] >= s0)]
                if not rows.empty:
                    row = rows.loc[rows["strike"].idxmin()]
                    k_s = float(row["strike"])
                    px = sell_leg(row)
                    n = long_call["contracts"]
                    cash += px * n * 100
                    prem_total += px * n * 100
                    sold_weeks += 1
                    s_close = mkt.day_close(settle)
                    if s_close > k_s:      # cash-settle the short call
                        cash -= (s_close - k_s) * n * 100
                else:
                    skipped += 1

        lc_val = 0.0
        if long_call:
            q = mkt.quote(settle, "CALL", long_call["strike"],
                          long_call["exp"])
            s_close = mkt.day_close(settle)
            lc_val = ((float(q["bid"]) + float(q["ask"])) / 2
                      if q is not None and q["ask"] > 0
                      else max(s_close - long_call["strike"], 0.0)) \
                * long_call["contracts"] * 100
        bal.append(cash + lc_val)
        prev = settle
    return bal, {"weeks_sold": sold_weeks, "skipped": skipped,
                 "premium": round(prem_total, 0)}


# --------------------------------------------------------------------------
def run_buyhold(mkt):
    bal = []
    first = None
    for wk in weeks_of(mkt):
        entry, settle = wk[0], wk[-1]
        s = mkt.bar_close(entry, "09:30")
        if s is None:
            continue
        if first is None:
            first = s
            sh = int(bt.START_CAPITAL // s)
            rest = bt.START_CAPITAL - sh * s
        bal.append(sh * mkt.day_close(settle) + rest)
    return bal, {}


def main():
    mkt = bt.Market()
    emit("=" * 78)
    emit("NO-UNDERLYING LAB -- window "
         f"{mkt.opt_dates[0]} -> {mkt.opt_dates[-1]}")
    emit("=" * 78)
    rows = []

    b, x = run_csp(mkt)
    rows.append(stats(b, "A) cash-secured weekly puts", x))
    b, x = run_pmcc(mkt)
    rows.append(stats(b, "B) PMCC (long call + weekly)", x))
    b, x = run_buyhold(mkt)
    rows.append(stats(b, "C) SOXL buy & hold", x))

    # D/E) engine runs: with shares, and signal-gated de-risking
    saved = {k: getattr(bt, k) for k in
             ("PUT_SPREAD_SHORT_FRAC", "INVEST_FRACTION", "SWEEP_FRACTION",
              "REGIME_RULE", "NO_STOCK_ON_STRESS")}
    for label, ov in [
            ("D) shares+put (plain, 85/5)",
             dict(PUT_SPREAD_SHORT_FRAC=None, INVEST_FRACTION=0.85,
                  SWEEP_FRACTION=0.05, REGIME_RULE=None,
                  NO_STOCK_ON_STRESS=False)),
            ("E) shares, cash when SOX<200dma",
             dict(PUT_SPREAD_SHORT_FRAC=None, INVEST_FRACTION=0.85,
                  SWEEP_FRACTION=0.05, REGIME_RULE="ma200",
                  NO_STOCK_ON_STRESS=True)),
            ("E2) shares, cash when SOX rv>45%",
             dict(PUT_SPREAD_SHORT_FRAC=None, INVEST_FRACTION=0.85,
                  SWEEP_FRACTION=0.05, REGIME_RULE="rv45",
                  NO_STOCK_ON_STRESS=True))]:
        for k, v in ov.items():
            setattr(bt, k, v)
        with redirect_stdout(io.StringIO()):
            df, _ = bt.run(mkt)
        extra = {}
        if "regime_note" in df.columns:
            extra["cash_weeks"] = int(df["regime_note"].astype(str)
                                      .str.contains("DE-RISKED").sum())
        rows.append(stats(pd.to_numeric(df["end_total_with_side"]).tolist(),
                          label, extra))
    for k, v in saved.items():
        setattr(bt, k, v)

    t = pd.DataFrame(rows)
    cols = ["strategy", "end", "ret%", "CAGR%", "maxDD%", "vol%",
            "worstWk%", "CAGR/|DD|"]
    emit(t[cols].to_string(index=False))
    emit()
    emit("Detail:")
    for r in rows:
        d = {k: v for k, v in r.items() if k not in cols}
        if d:
            emit(f"  {r['strategy']}: {d}")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(_lines) + "\n")
    print(f"\nReport -> {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
