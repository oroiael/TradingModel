"""
The four layers between "volatility" and UVXY, each one measured.

VIX is a statistic. UVXY is a fund. Between them sit four transformations,
and every one of them is a wedge:

    VIX (index)  ->  VIX futures  ->  constant-30-day index  ->  1.5x ETF
              [1]              [2]                        [3]           [4]

  [1] you cannot hold the index; you hold futures on it
  [2] futures are dampened and carry a risk premium
  [3] the index rolls daily, turning the premium into a realised cost
  [4] the fund levers the DAILY return, adding variance drag and fees

This module quantifies each. Where the CBOE spot index is needed it is not
available -- IBKR returns "Details currently unavailable" for conid 13455763
and the proxy denies cdn.cboe.com and FRED -- so layer [1] is described from
the published methodology and layers [2]-[4] are measured from real VIX
futures and the fund series.

Run:
    python3 vix_lab/manufacture.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
from dq_uvxy import load_raw  # noqa: E402
from fetch_refs import load as load_ref  # noqa: E402

OUT = os.path.join(_HERE, "out")
DATA = os.path.join(_HERE, "data")

#: The CFE VIX futures curve as of the 2026-08-04 close, from IBKR
#: `get_price_history` (delayed 600s). Settlement dates are the contracts'
#: `last_trading_date`. Stored inline because it is five numbers and the
#: point is the shape, not the series.
CURVE_DATE = pd.Timestamp("2026-08-04")
CURVE = [           # (last trading date, settlement price)
    ("2026-08-19", 18.00),
    ("2026-09-16", 19.20),
    ("2026-10-21", 20.20),
    ("2026-11-18", 20.65),
    ("2026-12-16", 20.70),
]

#: Daily closes of the front (Aug-26) and 5th (Dec-26) contracts over the same
#: 40 sessions, for the volatility-of-volatility term structure.
M1_CLOSES = [20.95, 21.05, 21.85, 21.20, 20.70, 19.75, 19.85, 20.25, 19.85,
             19.65, 20.20, 19.85, 19.70, 19.80, 19.30, 18.95, 19.15, 18.95,
             18.55, 18.70, 18.85, 18.60, 18.30, 18.75, 18.50, 18.10, 18.60,
             19.30, 18.95, 18.40, 18.35, 19.40, 19.25, 19.10, 18.95, 20.50,
             18.65, 18.15, 17.90, 18.00]
M5_CLOSES = [22.05, 22.10, 22.45, 22.05, 21.95, 21.60, 21.80, 21.90, 21.70,
             21.60, 21.60, 21.40, 21.15, 21.20, 20.95, 20.75, 20.75, 20.75,
             20.55, 20.65, 20.70, 20.60, 20.65, 20.70, 20.65, 20.55, 20.75,
             21.00, 20.80, 20.75, 20.90, 21.10, 21.20, 21.00, 20.95, 21.40,
             21.00, 20.85, 20.75, 20.70]

EXPENSE_UVXY = 0.0095      # ProShares stated annual expense ratio
EXPENSE_VIXY = 0.0085


def hdr(s: str) -> None:
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


def uvxy_close() -> pd.Series:
    df = load_raw(os.path.join(ROOT, "UVXY_1min.csv"))
    return df.groupby("date")["Close"].last()


def cagr(s: pd.Series) -> float:
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1


# ------------------------------------------------------ [2] futures vs index
def layer_futures() -> float:
    hdr("[2] VIX futures are not VIX — they are dampened, and they cost more")
    print(f"The CFE curve at the {CURVE_DATE.date()} close:\n")
    print(f"{'settles':<14}{'days out':>10}{'price':>9}{'vs front':>10}")
    d0 = CURVE_DATE
    front = CURVE[0][1]
    for ltd, px in CURVE:
        dte = (pd.Timestamp(ltd) - d0).days
        print(f"{ltd:<14}{dte:>10}{px:>9.2f}{px - front:>+10.2f}")
    print("\nUpward sloping — contango. This is the normal state: sellers of")
    print("volatility insurance demand a premium, so the futures sit above")
    print("where spot is expected to be. It is a risk premium, not a forecast.")

    m1 = pd.Series(M1_CLOSES).pct_change().dropna()
    m5 = pd.Series(M5_CLOSES).pct_change().dropna()
    print(f"\nVolatility of volatility, same 40 sessions:")
    print(f"{'contract':<20}{'daily sd':>11}{'annualised':>13}")
    print(f"{'Aug-26 (front)':<20}{m1.std():>11.4f}{m1.std() * np.sqrt(252):>13.2f}")
    print(f"{'Dec-26 (5th)':<20}{m5.std():>11.4f}{m5.std() * np.sqrt(252):>13.2f}")
    print(f"{'ratio front/5th':<20}{m1.std() / m5.std():>11.2f}")
    print(f"\nThe front contract moves {m1.std() / m5.std():.1f}x the fifth, and spot VIX")
    print("moves more still. Mean reversion is why: a spike today is not")
    print("expected to survive to December, so December barely reprices.")
    print("**A '30% VIX spike' is never a 30% move in anything you can own.**")

    # roll cost implied by the current slope
    d1 = (pd.Timestamp(CURVE[0][0]) - d0).days
    d2 = (pd.Timestamp(CURVE[1][0]) - d0).days
    p1, p2 = CURVE[0][1], CURVE[1][1]
    per_day = (p2 - p1) / (d2 - d1)
    level = p1 + (p2 - p1) * (30 - d1) / (d2 - d1)
    roll_daily = per_day / level
    print(f"\nThe roll cost this slope implies:")
    print(f"  front {p1:.2f} at {d1}d, second {p2:.2f} at {d2}d")
    print(f"  slope                        {per_day:+.4f} points/day")
    print(f"  constant-30-day level        {level:.2f}")
    print(f"  daily roll drag              {-roll_daily * 100:.3f}%/day")
    print(f"  compounded over a year       {(1 - roll_daily) ** 252 - 1:.1%}")
    print(f"  the same at 1.5x (UVXY)      "
          f"{(1 - 1.5 * roll_daily) ** 252 - 1:.1%}")
    print("\nNothing has to happen to volatility for that to be paid. It is")
    print("paid on a day when VIX does not move at all.")
    return roll_daily


# --------------------------------------------------- [3]+[4] fund vs index
def layer_fund() -> None:
    hdr("[3]+[4] What the fund adds on top: leverage, drag, fees")
    u = uvxy_close()
    vy = load_ref("VIXY")["Close"]
    j = pd.DataFrame({"u": u, "v": vy}).dropna()
    ru, rv = j["u"].pct_change().dropna(), j["v"].pct_change().dropna()

    beta = float((ru * rv).sum() / (rv ** 2).sum())
    print(f"Daily-return beta of UVXY to VIXY   {beta:.4f}   (target 1.50)")
    print(f"corr                                {ru.corr(rv):.5f}")
    print("\nThe 1.5x is exact, and it is exact **daily**. Over any longer")
    print("window it is not 1.5x anything — that is the whole story:\n")

    print(f"{'window':<22}{'UVXY':>12}{'VIXY':>12}{'1.5x VIXY':>12}{'gap':>10}")
    for label, s in (("full sample", j), ("2022", j[j.index.year == 2022]),
                     ("2023", j[j.index.year == 2023]),
                     ("2024", j[j.index.year == 2024]),
                     ("2025", j[j.index.year == 2025])):
        if len(s) < 20:
            continue
        cu = s["u"].iloc[-1] / s["u"].iloc[0] - 1
        cv = s["v"].iloc[-1] / s["v"].iloc[0] - 1
        print(f"{label:<22}{cu:>+12.1%}{cv:>+12.1%}{1.5 * cv:>+12.1%}"
              f"{cu - 1.5 * cv:>+10.1%}")
    print("\n'1.5x VIXY' is what a naive reading of the prospectus suggests.")
    print("The gap column is what daily rebalancing actually delivered.")

    # decomposition
    hdr("The decay, decomposed")
    yrs = (j.index[-1] - j.index[0]).days / 365.25
    cu, cv = cagr(j["u"]), cagr(j["v"])
    sigma = rv.std() * np.sqrt(252)
    drag = 0.375 * sigma ** 2
    print(f"sample {j.index[0].date()} -> {j.index[-1].date()}  ({yrs:.2f} years)\n")
    print(f"  UVXY realised CAGR                    {cu:>8.1%}")
    print(f"  VIXY realised CAGR                    {cv:>8.1%}")
    print()
    print(f"  1.5 x VIXY's log decay                "
          f"{np.exp(1.5 * np.log(1 + cv)) - 1:>8.1%}   <- leverage on the index")
    print(f"  minus variance drag 0.375*sigma^2     {-drag:>8.1%}   "
          f"(sigma = {sigma:.2f})")
    print(f"  minus the extra expense ratio         "
          f"{-(EXPENSE_UVXY - EXPENSE_VIXY):>8.1%}")
    pred = (np.exp(1.5 * np.log(1 + cv) - drag) - 1
            - (EXPENSE_UVXY - EXPENSE_VIXY))
    print(f"  {'':38}{'-' * 8}")
    print(f"  predicted UVXY CAGR                   {pred:>8.1%}")
    print(f"  actual                                {cu:>8.1%}")
    print(f"  unexplained                           {cu - pred:>+8.1%}")
    print("\nVIXY's own decay is layer [2]+[3] — the roll. UVXY's extra decay")
    print("is layer [4] — leverage applied to a falling series, plus the")
    print("rebalancing drag, plus fees. Neither has anything to do with a")
    print("view on volatility.")


# ------------------------------------------------------------- units matter
def layer_units() -> None:
    hdr("The unit trap: VIX moves in points, UVXY moves in percent")
    print("VIX is an annualised standard deviation quoted in percentage")
    print("points. UVXY is a share price. 'VIX went from 18 to 20' is a")
    print("+2-point move, an +11% move in the index, and neither number is")
    print("what UVXY does.\n")
    m1 = pd.Series(M1_CLOSES).pct_change().dropna()
    m5 = pd.Series(M5_CLOSES).pct_change().dropna()
    d1 = (pd.Timestamp(CURVE[0][0]) - CURVE_DATE).days
    d2 = (pd.Timestamp(CURVE[1][0]) - CURVE_DATE).days
    p1, p2 = CURVE[0][1], CURVE[1][1]
    w1 = (d2 - 30) / (d2 - d1)
    print(f"Worked through today's curve. The index holds the front and")
    print(f"second contracts weighted to 30 days: {w1:.0%} Aug + {1 - w1:.0%} Sep,")
    print(f"a blended level of {w1 * p1 + (1 - w1) * p2:.2f}.\n")
    print(f"{'if spot VIX moves':<22}{'assumed pass-thru':>19}"
          f"{'-> index':>10}{'-> UVXY':>10}")
    for shock, passthru in ((0.10, 0.55), (0.20, 0.50), (0.50, 0.40),
                            (-0.10, 0.55)):
        fut = shock * passthru
        print(f"{f'{shock:+.0%}':<22}{passthru:>19.2f}{fut:>+10.1%}"
              f"{1.5 * fut:>+10.1%}")
    print("\n**The pass-through column is ASSUMED, not measured.** Spot VIX is")
    print("not obtainable in this environment (see the module docstring), so")
    print("this table illustrates the shape of the wedge, not its size. The")
    print("direction is not in doubt -- the 40-session vol-of-vol ratio above")
    print(f"({m1.std() / m5.std():.1f}x front vs fifth) shows the damping is real and large --")
    print("but treat the specific numbers here as a worked example only.")

    print("\nWhat IS measured, from the files in this repo:")
    u = uvxy_close()
    ur = u.pct_change()
    vy = load_ref("VIXY")["Close"].pct_change()
    sp = load_ref("SPY")["Close"].pct_change()
    j = pd.DataFrame({"u": ur, "v": vy, "s": sp}).dropna()
    print(f"  UVXY daily sd            {j.u.std():.4f}  "
          f"({j.u.std() * np.sqrt(252):.2f} annualised)")
    print(f"  VIXY daily sd            {j.v.std():.4f}  "
          f"({j.v.std() * np.sqrt(252):.2f} annualised)")
    print(f"  SPY  daily sd            {j.s.std():.4f}  "
          f"({j.s.std() * np.sqrt(252):.2f} annualised)")
    print(f"  UVXY beta to SPY         {float((j.u * j.s).sum() / (j.s ** 2).sum()):+.2f}")
    ann_u = j.u.std() * np.sqrt(252)
    ann_s = j.s.std() * np.sqrt(252)
    print("\nA 1.5x fund on a 1x index that is itself a damped derivative of")
    print(f"a mean-reverting statistic ends up running {ann_u:.0%} annualised")
    print(f"volatility against the S&P's {ann_s:.0%} — {ann_u / ann_s:.0f}x — while the")
    print("leverage the ticker advertises is 1.5x. That factor is the")
    print("smallest of the multipliers involved, and the only one disclosed")
    print("in the fund's name.")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    layer_futures()
    layer_fund()
    layer_units()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
