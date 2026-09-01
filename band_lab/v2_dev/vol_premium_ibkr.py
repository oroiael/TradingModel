"""
SMH's OWN volatility premium, from IBKR. The measurement V45 could only predict.

V43 measured the round-trip option spread across underlyings and found SOXL at
18.5 volatility points against **SMH at 2.9**. V44 then compared SOXL's +10.9
point edge against SMH's 2.9 point spread and called it favourable.

**That comparison was invalid** -- see V45_PREMIUM_SCALING_BAR.md. A volatility
point is not the same amount of money on two underlyings whose volatilities
differ by 3x, and SOXL's is 114.5% against SMH's 36.7%.

V45 established, from the leverage identity rather than a regression, that the
premium must scale with the volatility level, and therefore predicted:

    SMH edge ~ +3.7 volatility points against a 2.9 spread -- net ~ +0.8

That is a prediction carried 28 volatility points below anything in the fitted
sample. This file measures SMH directly, two independent ways.

    PART A  the same-moment cross-section. ATM implied vol on SOXL, SOXX and
            SMH at one expiry, one moment. Needs no forward data at all, and
            the SOXL/SOXX implied ratio is a direct test of V45's constraint:
            proportional predicts it equals the 2.98x realised ratio, additive
            predicts ~3.76x.

    PART B  the historical premium. IBKR serves both halves:
                TRADES                     -> daily closes -> forward realised
                OPTION_IMPLIED_VOLATILITY  -> the implied vol series
            Both `whatToShow` values are verified against the official client
            committed here (`TWS API/source/pythonclient/ibapi/client.py:4242`).

THE CONTROL, STATED BEFORE RUNNING AND NOT NEGOTIABLE
=====================================================
IBKR's `OPTION_IMPLIED_VOLATILITY` is a constant-maturity series whose exact
tenor is NOT documented in the material available here. So Part B's SMH number
is worthless on its own. The run measures **SOXL first**, by the same method and
**over the vendor files' own date span**, and compares to V37:

    SOXL, 1 month, vendor option files:   implied 99.2%, realised 110.2%, +10.9

**If this method does not reproduce that to within about 3 volatility points,
Part B is rejected and its SMH number is not reported as a measurement.**
Part A does not depend on that series and stands on its own either way.

    python band_lab/v2_dev/vol_premium_ibkr.py
    python band_lab/v2_dev/vol_premium_ibkr.py --skip-historical
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta


def _reexec_in_venv() -> None:
    """Hand off to the venv's interpreter. See option_spread_probe for why."""
    venv = os.environ.get("VIRTUAL_ENV")
    if not venv or os.environ.get("_VOLPREM_REEXEC"):
        return
    if (os.path.normcase(os.path.abspath(sys.prefix))
            == os.path.normcase(os.path.abspath(venv))):
        return
    for exe in (os.path.join(venv, "Scripts", "python.exe"),
                os.path.join(venv, "bin", "python")):
        if os.path.exists(exe):
            sys.stderr.write(f"[re-exec] under {exe}\n\n")
            sys.exit(subprocess.run(
                [exe, os.path.abspath(__file__)] + sys.argv[1:],
                env=dict(os.environ, _VOLPREM_REEXEC="1")).returncode)


_reexec_in_venv()

import numpy as np                                                 # noqa: E402
import pandas as pd                                                # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import bs                                                          # noqa: E402
from option_spread_probe import (NY, R, Q, SYMBOLS, _atm_straddle,  # noqa: E402
                                 _connect, _last_weekday, _ticks)

OUT = os.path.join(_HERE, "out")
TRADING_DAYS = 252

#: V43's measured round-trip spread, volatility points. A symbol's premium has
#: to clear its OWN spread, so the two are always printed together.
SPREAD_VOL_PTS = {"SMH": 2.9, "SOXX": 8.0, "SOXL": 18.5, "SOXS": 37.6}

#: V45, from IBKR daily closes 2021-09 to 2026-08. The leverage identity.
RV_MEASURED = {"SOXL": 114.5, "SOXX": 38.5, "SMH": 36.7}
LEVERAGE = RV_MEASURED["SOXL"] / RV_MEASURED["SOXX"]          # 2.98

#: V37's vendor-file result for SOXL at one month, and its date span. Part B's
#: control compares like with like or it is not a control.
CONTROL = {"symbol": "SOXL", "horizon": 21, "iv": 99.2, "rv": 110.2,
           "edge": 10.9, "tolerance": 3.0,
           "start": "2022-01-03", "end": "2026-07-02"}

HORIZONS = [("1 week", 5), ("1 month", 21), ("3 months", 63), ("6 months", 124)]


# --------------------------------------------------------------- part A
def cross_section(ib, syms, when, target_dte, pause) -> pd.DataFrame:
    """ATM implied vol on every symbol at ONE expiry, ONE moment.

    Reuses `option_spread_probe._atm_straddle`, which is the selection rule the
    backtest uses and the one V43 already ran against these same symbols --
    including the params[0] bug fix that silently dropped SPY and QQQ.
    """
    rows = []
    for sym in syms:
        try:
            sel = _atm_straddle(ib, when, target_dte, sym)
        except Exception as exc:                            # noqa: BLE001
            print(f"  {sym:<6} could not resolve: {type(exc).__name__}: {exc}")
            continue
        if sel is None:
            print(f"  {sym:<6} no ATM straddle near {target_dte} DTE")
            continue
        call, put, strike, expiry, dte, spot = sel
        t0 = when.replace(hour=12, minute=0, second=0, microsecond=0)
        ivs, spr = [], 0.0
        vg = 0.0
        for right, c in (("CALL", call), ("PUT", put)):
            try:
                tk = _ticks(ib, c, t0, 20)
            except Exception as exc:                        # noqa: BLE001
                print(f"  {sym:<6} {right} ticks failed: {exc}")
                tk = []
            if not tk:
                continue
            b, k = float(tk[-1].priceBid), float(tk[-1].priceAsk)
            T = dte / 365.0
            iv = float(bs.implied_vol((b + k) / 2.0, spot, strike, T, R, Q,
                                      right))
            ivs.append(iv)
            spr += k - b
            vg += float(bs.vega(spot, strike, T, R, Q, iv))
            time.sleep(pause)
        if len(ivs) != 2:
            print(f"  {sym:<6} incomplete quotes, skipping")
            continue
        rows.append(dict(symbol=sym, spot=spot, strike=strike, dte=dte,
                         expiry=expiry, iv=float(np.mean(ivs)) * 100,
                         spread=spr,
                         vol_pts=spr / (vg / 100.0) if vg else np.nan))
        print(f"  {sym:<6} spot {spot:>8.2f}  K {strike:>7.1f}  {dte:>3}d  "
              f"IV {rows[-1]['iv']:>6.1f}%  round trip "
              f"{rows[-1]['vol_pts']:>5.1f} vol pts")
    return pd.DataFrame(rows)


def report_cross_section(d: pd.DataFrame) -> None:
    w = 92
    print("\n" + "=" * w)
    print("PART A — THE SAME-MOMENT CROSS-SECTION. V45's constraint, tested.")
    print("=" * w)
    have = set(d.symbol)
    if not {"SOXL", "SOXX"} <= have:
        print("\n  need both SOXL and SOXX for the ratio test; skipping.")
    else:
        ivl = float(d[d.symbol == "SOXL"].iv.iloc[0])
        ivx = float(d[d.symbol == "SOXX"].iv.iloc[0])
        obs = ivl / ivx
        add = ((RV_MEASURED["SOXL"] - CONTROL["edge"])
               / (RV_MEASURED["SOXX"] - CONTROL["edge"]))
        print(f"""
  SOXL is a {LEVERAGE:.2f}x daily-reset fund on the index SOXX tracks. If the
  volatility premium scales with the vol level, the market must price SOXL's
  implied vol at {LEVERAGE:.2f}x SOXX's. If the premium were a fixed {CONTROL['edge']:+.1f} points on
  both -- the model V44 assumed -- the ratio would have to be {add:.2f}x instead.

      proportional predicts   IV_SOXL / IV_SOXX = {LEVERAGE:.2f}
      additive     predicts   IV_SOXL / IV_SOXX = {add:.2f}
      **observed**            IV_SOXL / IV_SOXX = {obs:.2f}   ({ivl:.1f}% / {ivx:.1f}%)
""")
        near = "proportional" if abs(obs - LEVERAGE) < abs(obs - add) else \
               "ADDITIVE — which would overturn V45"
        print(f"  closer to: **{near}**   "
              f"(|obs-prop| {abs(obs - LEVERAGE):.2f} vs "
              f"|obs-add| {abs(obs - add):.2f})")

    print("\n  " + "-" * 78)
    print(f"\n  {'symbol':<8}{'implied':>10}{'realised':>10}{'edge':>8}"
          f"{'spread':>9}{'net':>8}{'clears?':>10}")
    print("  " + "-" * 63)
    for _, r in d.iterrows():
        rv = RV_MEASURED.get(r.symbol, np.nan)
        sp = SPREAD_VOL_PTS.get(r.symbol, np.nan)
        edge = rv - r.iv
        print(f"  {r.symbol:<8}{r.iv:>9.1f}%{rv:>9.1f}%{edge:>+8.1f}{sp:>9.1f}"
              f"{edge - sp:>+8.1f}{'YES' if edge > sp else 'no':>10}")
    print(f"""
  'realised' is the trailing 5-year figure from V45, NOT the forward realised
  vol these options will actually meet. So the 'edge' column here is a level
  check, not a premium measurement -- today's implied vol against a different
  period's realised. It says whether SMH's options are priced anywhere near
  where the proportional model puts them ({RV_MEASURED['SMH'] / (CONTROL['rv'] / CONTROL['iv']):.0f}%). Part B is the premium.
""")


# --------------------------------------------------------------- part B
def _series(ib, stk, what: str, years: str) -> pd.Series:
    """Daily bars for one `whatToShow`, indexed by date."""
    bars = ib.reqHistoricalData(
        stk, endDateTime="", durationStr=years, barSizeSetting="1 day",
        whatToShow=what, useRTH=True, formatDate=1, keepUpToDate=False)
    if not bars:
        return pd.Series(dtype=float)
    return pd.Series([float(b.close) for b in bars],
                     index=pd.to_datetime([b.date for b in bars])).sort_index()


def forward_rv(px: pd.Series, n: int) -> pd.Series:
    """Annualised realised vol over the NEXT n sessions. Strictly forward."""
    r2 = np.log(px / px.shift(1)) ** 2
    fwd = r2.shift(-1).rolling(n).sum().shift(-(n - 1))
    return np.sqrt(fwd / n * TRADING_DAYS)


def measure(px: pd.Series, iv: pd.Series, n: int, lo=None, hi=None):
    t = pd.DataFrame({"iv": iv, "rv": forward_rv(px, n)}).dropna()
    if lo is not None:
        t = t.loc[str(lo):str(hi)]
    if len(t) < 40:
        return None
    edge = (t["rv"] - t["iv"]) * 100
    # Overlap: consecutive windows share all but one session, so the
    # independent count is the span divided by the horizon. V37's correction.
    indep = max(len(t) / n, 1.0)
    se = edge.std(ddof=1) / math.sqrt(indep)
    return dict(n=len(t), indep=indep, iv=t["iv"].mean() * 100,
                rv=t["rv"].mean() * 100, edge=edge.mean(), se=se,
                t=edge.mean() / se if se else np.nan,
                pos=float((edge > 0).mean()))


def report_historical(data, syms, iv_scale=1.0) -> bool:
    w = 92
    if iv_scale != 1.0:
        print(f"\n  [scaled] IV series multiplied by {iv_scale:.4f} "
              f"(--iv-scale). The control below is what validates it.")
    px, iv = data[CONTROL["symbol"]]
    c = measure(px, iv, CONTROL["horizon"], CONTROL["start"], CONTROL["end"])
    print("\n" + "=" * w)
    print("PART B CONTROL — does IBKR's IV series reproduce the vendor answer?")
    print("=" * w)
    if c is None:
        print("\n  not enough matched dates in the vendor span. "
              "Part B rejected.")
        return False
    gap = abs(c["edge"] - CONTROL["edge"])
    ok = gap <= CONTROL["tolerance"]
    print(f"\n  SOXL, 1 month, restricted to the vendor files' own span "
          f"{CONTROL['start']} to {CONTROL['end']} ({c['n']:,} dates)\n")
    print(f"  {'':30}{'implied':>10}{'realised':>11}{'edge':>9}")
    print("  " + "-" * 60)
    print(f"  {'V37, vendor option files':<30}{CONTROL['iv']:>9.1f}%"
          f"{CONTROL['rv']:>10.1f}%{CONTROL['edge']:>+9.1f}")
    print(f"  {'this method, IBKR IV series':<30}{c['iv']:>9.1f}%"
          f"{c['rv']:>10.1f}%{c['edge']:>+9.1f}")
    print(f"\n  gap {gap:.1f} volatility points against a "
          f"{CONTROL['tolerance']:.0f}-point tolerance")
    verdict = ("the two sources agree; the method carries to other symbols"
               if ok else
               "the sources DISAGREE. Everything below is printed only so the "
               "disagreement is visible, and is NOT a measurement.")
    print(f"\n  [{'PASS' if ok else 'FAIL'}] {verdict}")
    if not ok:
        ratio = CONTROL["iv"] / c["iv"] if c["iv"] else float("nan")
        print(f"\n  The gap is a FACTOR of {ratio:.2f}, not an offset — "
              f"{CONTROL['iv']:.1f} / {c['iv']:.1f}. That is a units problem "
              f"in\n  IBKR's volatility encoding, not a disagreement about "
              f"volatility. Identify it:\n\n"
              f"      python band_lab/v2_dev/vol_premium_ibkr.py --diagnose\n")

    print("\n" + "=" * w)
    print("PART B — VOLATILITY PREMIUM BY SYMBOL, realised minus implied")
    print("=" * w)
    print(f"\n  {'symbol':<7}{'tenor':<10}{'dates':>7}{'indep':>7}"
          f"{'implied':>9}{'realised':>10}{'edge':>8}{'se':>7}{'t':>7}"
          f"{'spread':>9}{'clears?':>9}")
    print("  " + "-" * 89)
    rows = []
    for sym in syms:
        if sym not in data:
            continue
        px, iv = data[sym]
        sp = SPREAD_VOL_PTS.get(sym, np.nan)
        for label, n in HORIZONS:
            m = measure(px, iv, n)
            if m is None:
                continue
            clears = ("YES" if np.isfinite(sp) and m["edge"] > sp else
                      "no" if np.isfinite(sp) else "-")
            rows.append(dict(symbol=sym, tenor=label, spread=sp, **m))
            print(f"  {sym:<7}{label:<10}{m['n']:>7,}{m['indep']:>7.1f}"
                  f"{m['iv']:>8.1f}%{m['rv']:>9.1f}%{m['edge']:>+8.1f}"
                  f"{m['se']:>7.1f}{m['t']:>7.2f}{sp:>9.1f}{clears:>9}")
        print()

    print(f"""  'spread' is V43's measured round-trip cost for that symbol, same unit.
  'clears?' is edge > spread -- the necessary condition before any structure
  can work, and the one SOXL failed at +10.9 against 18.5.

  Standard errors use NON-OVERLAPPING windows. At six months a 5-year sample
  gives about 10 independent observations, so those t-statistics are weak by
  construction and are not evidence on their own.

  V45 predicted SMH at +3.7 against 2.9, net +0.8, from the leverage identity.
  The 1-month SMH row above is the measurement that prediction was standing in
  for. If it lands near +3.7 the chain of reasoning holds; if it lands near
  +10.9 then V45's leverage argument is wrong and I want to know why.
""")
    if rows:
        os.makedirs(OUT, exist_ok=True)
        pd.DataFrame(rows).to_csv(
            os.path.join(OUT, "V46_premium_by_symbol.csv"), index=False)
        print("  wrote out/V46_premium_by_symbol.csv")
    return ok


#: Candidate unit conventions for IBKR's volatility series, and what each would
#: mean. The diagnostic picks between them against MEASURED references; it does
#: not assume one. V28's vega error was exactly this kind of mistake -- a factor
#: nobody checked -- and it made every option strategy look free.
IV_SCALES = [
    (1.0, "already annualised, decimal (1.0 = 100%)"),
    (math.sqrt(TRADING_DAYS), "DAILY sigma; annualise by sqrt(252)"),
    (math.sqrt(365.0), "daily sigma on calendar days; sqrt(365)"),
    (100.0, "percent-vs-decimal mixup"),
]


def diagnose_iv(ib, sym, years, when, target_dte, pause) -> int:
    """Why did the Part B control fail by a factor of ~16?

    The control caught that IBKR's OPTION_IMPLIED_VOLATILITY series reports SOXL
    at 6.2% where the vendor files and the live chain both say ~99%. That is a
    units question, and it is settled by measurement, not by multiplying until
    the number looks right.

    TWO INDEPENDENT REFERENCES, both on MATCHED DATES:

      1. OPTION_IMPLIED_VOLATILITY  vs  the live ATM chain IV computed here
         from bid/ask through Black-Scholes. Same symbol, same session, two
         completely different paths through the API.

      2. HISTORICAL_VOLATILITY      vs  trailing 30-session realised vol
         computed here from the TRADES bars. Same idea, and it does not involve
         options at all -- so if both series need the same factor, the factor is
         a property of IBKR's volatility encoding rather than of one field.

    A correction that only fits one reference is not adopted.
    """
    from ib_async import Stock
    w = 92
    print("\n" + "=" * w)
    print("DIAGNOSTIC — what unit is IBKR's volatility series in?")
    print("=" * w)

    q = ib.qualifyContracts(
        Stock(sym, "SMART", "USD", primaryExchange=SYMBOLS.get(sym, "ARCA")))
    if not q:
        print(f"  could not qualify {sym}")
        return 1
    stk = q[0]

    px = _series(ib, stk, "TRADES", years)
    time.sleep(pause)
    iv = _series(ib, stk, "OPTION_IMPLIED_VOLATILITY", years)
    time.sleep(pause)
    hv = _series(ib, stk, "HISTORICAL_VOLATILITY", years)
    time.sleep(pause)
    if px.empty or iv.empty:
        print(f"  TRADES {len(px)} bars, IV {len(iv)} bars — nothing to do")
        return 1

    print(f"\n  raw OPTION_IMPLIED_VOLATILITY bars, last 5 — the actual "
          f"numbers, unscaled:")
    for d, v in iv.tail(5).items():
        print(f"      {d.date()}   close = {v!r}")

    # ---- reference 1: the live ATM chain, same session
    xs = cross_section(ib, [sym], when, target_dte, pause)
    r1 = None
    if not xs.empty:
        live = float(xs.iloc[0]["iv"]) / 100.0        # back to decimal
        near = iv.index[iv.index <= pd.Timestamp(when.date())]
        if len(near):
            d0 = near[-1]
            r1 = live / float(iv.loc[d0])
            print(f"\n  reference 1 — live ATM chain vs the IV series, "
                  f"{d0.date()}")
            print(f"      live chain, Black-Scholes from bid/ask : "
                  f"{live*100:>8.2f}%")
            print(f"      OPTION_IMPLIED_VOLATILITY series       : "
                  f"{float(iv.loc[d0])*100:>8.2f}%")
            print(f"      ratio                                  : "
                  f"{r1:>8.3f}")

    # ---- reference 2: trailing realised vol, no options involved
    r2 = None
    if not hv.empty:
        lr = np.log(px / px.shift(1))
        trail = lr.rolling(30).std(ddof=1) * math.sqrt(TRADING_DAYS)
        j = pd.DataFrame({"hv": hv, "mine": trail}).dropna()
        if len(j) > 50:
            r2 = float((j["mine"] / j["hv"]).median())
            print(f"\n  reference 2 — HISTORICAL_VOLATILITY vs 30-session "
                  f"realised computed here ({len(j):,} matched dates)")
            print(f"      my trailing realised, annualised, median : "
                  f"{j['mine'].median()*100:>8.2f}%")
            print(f"      HISTORICAL_VOLATILITY series, median     : "
                  f"{j['hv'].median()*100:>8.2f}%")
            print(f"      ratio, median                            : "
                  f"{r2:>8.3f}")
    else:
        print("\n  reference 2 — HISTORICAL_VOLATILITY returned no bars")

    print(f"\n  {'candidate convention':<46}{'factor':>9}"
          f"{'fits ref 1':>12}{'fits ref 2':>12}")
    print("  " + "-" * 79)
    best, best_err = None, None
    for f, label in IV_SCALES:
        e1 = abs(r1 - f) / f if r1 else np.nan
        e2 = abs(r2 - f) / f if r2 else np.nan
        errs = [e for e in (e1, e2) if e == e]
        tot = max(errs) if errs else np.nan
        print(f"  {label:<46}{f:>9.3f}"
              f"{('%.1f%%' % (e1*100)) if e1 == e1 else '-':>12}"
              f"{('%.1f%%' % (e2*100)) if e2 == e2 else '-':>12}")
        if tot == tot and (best_err is None or tot < best_err):
            best, best_err = f, tot

    print()
    if best is None:
        print("  [FAIL] neither reference resolved. No correction adopted.")
        return 1
    agree = best_err <= 0.05
    print(f"  [{'PASS' if agree else 'FAIL'}] best candidate {best:.4f} — "
          f"worst-case error across BOTH references {best_err*100:.1f}%")
    if agree:
        print(f"\n  Both independent references agree, so the convention is "
              f"identified, not guessed.\n  Re-run Part B with it, and the "
              f"CONTROL is what validates it:\n\n"
              f"      python band_lab/v2_dev/vol_premium_ibkr.py "
              f"--iv-scale {best:.4f}\n")
    else:
        print(f"\n  The two references DISAGREE (worst error "
              f"{best_err*100:.1f}%). A factor that fits one and not the\n"
              f"  other is not a unit convention, it is a coincidence. "
              f"Not adopted.\n")
    return 0 if agree else 1


def _selftest() -> int:
    """Offline checks on the arithmetic. No IBKR, no network.

    Built to fail: each case has an answer known independently of this file.
    """
    fails = []

    def ok(name, cond, detail=""):
        if not cond:
            fails.append(name)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
              f"{': ' + detail if detail else ''}")

    print("=" * 78)
    print("SELFTEST — the arithmetic, offline")
    print("=" * 78 + "\n")

    # 1. forward_rv on a series with a KNOWN constant daily move.
    #    A fixed +/-1% alternating log-return has daily sd |r| = 0.01, so the
    #    annualised vol must be 0.01*sqrt(252) = 15.87%.
    n = 400
    r = np.where(np.arange(n) % 2 == 0, 0.01, -0.01)
    px = pd.Series(np.exp(np.cumsum(r)),
                   index=pd.bdate_range("2020-01-01", periods=n))
    got = forward_rv(px, 21).dropna()
    want = 0.01 * math.sqrt(TRADING_DAYS)
    ok("forward_rv recovers a known constant volatility",
       abs(got.mean() - want) < 1e-6,
       f"{got.mean()*100:.4f}% vs {want*100:.4f}%")

    # 2. forward_rv must look FORWARD only. Put a single huge move at a known
    #    date; windows ENDING before it must be unaffected, and the window
    #    starting the day before must contain it.
    px2 = pd.Series(1.0, index=pd.bdate_range("2020-01-01", periods=200))
    px2.iloc[100:] = 2.0                       # one +100% jump at index 100
    f = forward_rv(px2, 5)
    ok("forward_rv is strictly forward-looking",
       f.iloc[94] == 0 and f.iloc[99] > 0,
       f"window ending before the jump {f.iloc[94]:.4f}, "
       f"window starting the day before {f.iloc[99]:.4f}")

    # 3. measure() must return the edge as realised MINUS implied, in points.
    idx = pd.bdate_range("2020-01-01", periods=400)
    px3 = pd.Series(np.exp(np.cumsum(np.where(np.arange(400) % 2 == 0,
                                              0.01, -0.01))), index=idx)
    iv3 = pd.Series(0.10, index=idx)           # flat 10% implied
    m = measure(px3, iv3, 21)
    ok("measure() returns realised minus implied in vol points",
       m is not None and abs(m["edge"] - (want - 0.10) * 100) < 1e-4,
       f"edge {m['edge']:+.4f} vs {(want - 0.10)*100:+.4f}")

    # 4. The overlap correction must SHRINK the independent count.
    ok("overlap correction divides by the horizon",
       m is not None and abs(m["indep"] - m["n"] / 21) < 1e-9,
       f"{m['n']} rows -> {m['indep']:.1f} independent windows")

    # 5. The two competing model predictions must actually differ, or Part A's
    #    ratio test discriminates nothing.
    add = ((RV_MEASURED["SOXL"] - CONTROL["edge"])
           / (RV_MEASURED["SOXX"] - CONTROL["edge"]))
    ok("the additive and proportional IV ratios are distinguishable",
       abs(add - LEVERAGE) > 0.5,
       f"additive {add:.2f}x vs proportional {LEVERAGE:.2f}x, "
       f"apart by {abs(add - LEVERAGE):.2f}")

    print(f"\n  {'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="offline arithmetic checks, no IBKR connection")
    ap.add_argument("--diagnose", action="store_true",
                    help="identify the unit convention of IBKR's vol series")
    ap.add_argument("--iv-scale", type=float, default=1.0,
                    help="multiply the IV series by this before measuring. "
                         "Only ever a value --diagnose has verified against "
                         "BOTH of its independent references; the Part B "
                         "control is what validates it.")
    ap.add_argument("--symbols", default="SOXL,SOXX,SMH")
    ap.add_argument("--years", default="5 Y")
    ap.add_argument("--target-dte", type=int, default=37)
    ap.add_argument("--days-back", type=int, default=1)
    ap.add_argument("--skip-historical", action="store_true")
    ap.add_argument("--skip-cross-section", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497)
    ap.add_argument("--client-id", type=int, default=99)
    ap.add_argument("--pause", type=float, default=2.0)
    a = ap.parse_args()

    if a.selftest:
        return _selftest()

    from ib_async import Stock
    syms = [x.strip().upper() for x in a.symbols.split(",") if x.strip()]
    for need in ("SOXL", "SOXX"):          # the control and the ratio test
        if need not in syms:
            syms.insert(0, need)

    ib = _connect(a.host, a.port, a.client_id)
    xs, data = pd.DataFrame(), {}
    try:
        if a.diagnose:
            when = _last_weekday(datetime.now(NY) - timedelta(days=a.days_back))
            return diagnose_iv(ib, CONTROL["symbol"], a.years, when,
                               a.target_dte, a.pause)

        if not a.skip_cross_section:
            when = _last_weekday(datetime.now(NY) - timedelta(days=a.days_back))
            print(f"\n  cross-section as of {when:%Y-%m-%d} ({when:%A}), "
                  f"nearest {a.target_dte} DTE\n")
            xs = cross_section(ib, syms, when, a.target_dte, a.pause)

        if not a.skip_historical:
            print(f"\n  daily series, {a.years}\n")
            for sym in syms:
                q = ib.qualifyContracts(
                    Stock(sym, "SMART", "USD",
                          primaryExchange=SYMBOLS.get(sym, "ARCA")))
                if not q:
                    print(f"  {sym}: could not qualify")
                    continue
                px = _series(ib, q[0], "TRADES", a.years)
                time.sleep(a.pause)
                iv = _series(ib, q[0], "OPTION_IMPLIED_VOLATILITY",
                             a.years) * a.iv_scale
                time.sleep(a.pause)
                if px.empty or iv.empty:
                    print(f"  {sym}: TRADES {len(px)} bars, IV {len(iv)} bars "
                          f"— cannot measure")
                    continue
                data[sym] = (px, iv)
                print(f"  {sym}: {len(px):,} price bars, {len(iv):,} IV bars, "
                      f"{px.index.min().date()} to {px.index.max().date()}")
    finally:
        ib.disconnect()

    ok = True
    if not xs.empty:
        report_cross_section(xs)
        os.makedirs(OUT, exist_ok=True)
        xs.to_csv(os.path.join(OUT, "V46_cross_section.csv"), index=False)
        print("  wrote out/V46_cross_section.csv")
    if data:
        if CONTROL["symbol"] not in data:
            print(f"\n[FAIL] control symbol {CONTROL['symbol']} returned no "
                  f"data; Part B is not reportable.")
            ok = False
        else:
            ok = report_historical(data, syms, a.iv_scale)
    if xs.empty and not data:
        print("\n  nothing resolved. Run "
              "`option_spread_probe.py --check` first.")
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
