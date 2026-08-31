"""
Measure what a SOXL straddle ACTUALLY costs to trade, intraday, from IBKR.

This closes gap #1 of V31. The straddle study assumed (A1) that every fill pays
the full quoted spread, and priced that spread from END-OF-DAY vendor snapshots
at a mean of 10.6 volatility points. Two things about that are unverified:

  1. Whether the midday spread is tighter than the end-of-day one. If it is
     materially tighter, the -2.94%/cycle verdict moves.
  2. Whether there is depth at the touch at all. A frozen quote pulled on
     2026-08-29 showed **bid size 1** on an ATM SOXL call, against V28's
     "28 bid / 30 ask" median from the vendor file.

WHY TICKS AND NOT BARS. `reqHistoricalData(whatToShow="BID_ASK")` is accepted by
the API (verified: `TWS API/source/pythonclient/ibapi/client.py:4242`) but its
OHLC-to-bid/ask field mapping is NOT documented anywhere in the copy of IBKR's
docs committed to this repo, and no sample in `TWS API/samples` uses it. Guessing
that mapping is exactly the class of assumption that has cost this project twice.
`reqHistoricalTicks(whatToShow="BID_ASK")` instead returns
`HistoricalTickBidAsk` with **named** fields — `priceBid`, `priceAsk`, `sizeBid`,
`sizeAsk` (`ibapi/common.py:279`) — so there is nothing to guess, and it carries
the sizes, which answers the depth question in the same pass.

    python3 band_lab/v2_dev/option_spread_probe.py --check
    python3 band_lab/v2_dev/option_spread_probe.py --collect --sessions 10
    python3 band_lab/v2_dev/option_spread_probe.py --analyse
    python3 band_lab/v2_dev/option_spread_probe.py --selftest

ON WINDOWS use `python`, not `python3`. Inside an activated venv, `pip` points
at the venv but `python3` usually resolves to the Microsoft Store shim or a
system Python, so `pip install ib_async` succeeds and the import still fails.
`python -m pip install ib_async` and `python ...` keep both on the same
interpreter. `--doctor` prints which interpreter you are actually on.

RUN IT WHERE TWS IS. This file was written in a container with no ib_async and
no reachable TWS on 7497/7496/4001, so **the IBKR half has never been executed.**
The analysis half has: `--selftest` exercises it on synthetic ticks with a known
answer. Treat the first `--check` run as a debugging session, not a measurement.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _reexec_in_venv() -> None:
    """If a venv is active but this interpreter is not it, re-run under it.

    On Windows `python3` resolves to the Python install-manager build (e.g.
    `pythoncore-3.14-64`) or the Store shim, NOT the activated venv, while
    `pip` does resolve to the venv. So `pip install X` reports success and the
    import still fails, and the fix -- "type `python`, not `python3`" -- is
    both invisible and easy to type past twice in a row. It cost two rounds
    here before this function existed.

    Rather than print advice, hand off to the right interpreter. `subprocess`
    and not `os.execv`, because on Windows exec replaces the process in a way
    that returns control to the shell before the child finishes.
    """
    venv = os.environ.get("VIRTUAL_ENV")
    if not venv or os.environ.get("_SPREAD_PROBE_REEXEC"):
        return                                  # no venv, or already handed off
    same = (os.path.normcase(os.path.abspath(sys.prefix))
            == os.path.normcase(os.path.abspath(venv)))
    if same:
        return
    for exe in (os.path.join(venv, "Scripts", "python.exe"),
                os.path.join(venv, "bin", "python")):
        if os.path.exists(exe):
            sys.stderr.write(
                f"[re-exec] this is {sys.executable}\n"
                f"[re-exec] the active venv is {venv}\n"
                f"[re-exec] re-running under {exe}\n\n")
            env = dict(os.environ, _SPREAD_PROBE_REEXEC="1")
            sys.exit(subprocess.run([exe, os.path.abspath(__file__)]
                                    + sys.argv[1:], env=env).returncode)
    # No interpreter inside VIRTUAL_ENV. Fall through; the import error below
    # reports the mismatch rather than this function guessing at it.


_reexec_in_venv()

import numpy as np                                                 # noqa: E402
import pandas as pd                                                # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import bs                                                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(_HERE))
NY = ZoneInfo("America/New_York")
OUT = os.path.join(_HERE, "out")
TICKS_CSV = os.path.join(OUT, "V32_option_ticks.csv")

# Match the straddle backtest so the measurement is comparable to what it costed.
TARGET_DTE = 37
DTE_WINDOW = 13
R, Q = 0.04, 0.0                    # bs.py best fit, V30 A12

#: What the backtest assumed, for the comparison this whole file exists to make.
EOD_MEAN_VOL_PTS = 10.6
EOD_MEDIAN_VOL_PTS = 6.0

#: Sample this many moments per session rather than every tick. A spread
#: distribution does not need every print, and IBKR paces historical requests
#: hard. Spread across the session so the open and the close are both seen.
SAMPLE_MINUTES = (10, 45, 90, 150, 210, 270, 330, 380)
TICKS_PER_SAMPLE = 40


# ------------------------------------------------------------------ IBKR half
def _connect(host, port, client_id):
    try:
        from ib_async import IB
    except ImportError:
        # This message used to say "run this on the machine with TWS", which is
        # wrong and wasted a user's time: on Windows `pip` resolves to the
        # ACTIVE VENV while `python3` resolves to the Microsoft Store shim or a
        # system Python. So `pip install ib_async` reports "already satisfied"
        # and the script still cannot import it. Print the interpreter rather
        # than guessing at the cause.
        venv = os.environ.get("VIRTUAL_ENV", "(none)")
        raise SystemExit(
            "ib_async is not importable from THIS interpreter.\n\n"
            f"  interpreter : {sys.executable}\n"
            f"  sys.prefix  : {sys.prefix}\n"
            f"  VIRTUAL_ENV : {venv}\n\n"
            "If VIRTUAL_ENV is set and sys.prefix does not match it, you are "
            "running the wrong Python.\n"
            "On Windows `python3` is often NOT the venv's interpreter while "
            "`pip` is. Use:\n\n"
            "    python band_lab/v2_dev/option_spread_probe.py --check\n"
            "    .\\.venv-live\\Scripts\\python.exe "
            "band_lab/v2_dev/option_spread_probe.py --check\n\n"
            "If the interpreter above IS the venv, then install it there: "
            "python -m pip install ib_async")
    ib = IB()
    print(f"connecting to {host}:{port} (clientId={client_id}) ...", flush=True)
    ib.connect(host, port, clientId=client_id, timeout=20)
    print(f"connected, server version {ib.client.serverVersion()}")
    return ib


def _atm_straddle(ib, when: datetime, target_dte: int):
    """The same contract the backtest would have picked, on `when`.

    Returns (call, put, strike, expiry, spot) or None. Selection rule copied
    from `straddle_backtest.pick`: expiry nearest the target DTE, then the
    listed strike nearest spot.
    """
    from ib_async import Option, Stock

    stk = ib.qualifyContracts(Stock("SOXL", "SMART", "USD", primaryExchange="ARCA"))
    if not stk:
        raise RuntimeError("could not qualify SOXL")
    stk = stk[0]

    bars = ib.reqHistoricalData(
        stk, endDateTime=when.strftime("%Y%m%d %H:%M:%S US/Eastern"),
        durationStr="1 D", barSizeSetting="1 min", whatToShow="TRADES",
        useRTH=True, formatDate=1, keepUpToDate=False)
    if not bars:
        return None
    spot = float(bars[-1].close)

    params = [p for p in ib.reqSecDefOptParams(stk.symbol, "", stk.secType,
                                               stk.conId)
              if p.exchange == "SMART"]
    if not params:
        raise RuntimeError("no SMART option parameters for SOXL")
    p = params[0]

    exps = []
    for e in p.expirations:
        d = datetime.strptime(e, "%Y%m%d").replace(tzinfo=NY)
        dte = (d.date() - when.date()).days
        if abs(dte - target_dte) <= DTE_WINDOW:
            exps.append((abs(dte - target_dte), e, dte))
    if not exps:
        return None
    _, expiry, dte = min(exps)

    # `reqSecDefOptParams` returns the UNION of strikes across every expiration
    # and trading class, so a strike it lists may not exist for the expiry we
    # picked. Taking the nearest one blindly asked for a 116.5 strike on the
    # 20261002 expiry, IBKR answered "Error 200 no security definition",
    # qualifyContracts returned None, and reading `.right` off None killed the
    # whole collection run on its third session.
    #
    # Ask which strikes that expiry actually lists, instead of guessing from
    # the union. One request, exact answer, no error spam.
    want = [float(k) for k in p.strikes if abs(float(k) / spot - 1.0) <= 0.05]
    if not want:
        return None
    try:
        det = ib.reqContractDetails(
            Option("SOXL", expiry, 0, "C", "SMART", tradingClass="SOXL"))
        listed = {float(d.contract.strike) for d in det}
        if listed:
            want = [k for k in want if k in listed]
    except Exception:                                   # noqa: BLE001
        pass                    # fall through to the nearest-first loop below
    if not want:
        return None

    # Nearest first, and keep going if one fails. `qualifyContracts` returns
    # None in place of a contract it could not resolve, so filter those out
    # rather than indexing into them.
    for strike in sorted(want, key=lambda k: abs(k / spot - 1.0)):
        legs = [c for c in ib.qualifyContracts(
            Option("SOXL", expiry, strike, "C", "SMART", tradingClass="SOXL"),
            Option("SOXL", expiry, strike, "P", "SMART", tradingClass="SOXL"))
            if c is not None]
        call = next((c for c in legs if c.right == "C"), None)
        put = next((c for c in legs if c.right == "P"), None)
        if call is not None and put is not None:
            return call, put, strike, expiry, dte, spot
    return None


def _last_weekday(d: datetime) -> datetime:
    """Walk back to Friday if handed a Saturday or Sunday.

    Contract resolution hides this: reqHistoricalData with a Saturday
    endDateTime happily returns Friday's bars, so the straddle resolves and
    only the TICK request comes back empty -- which then reads as a missing
    subscription. The date is trivially checkable, so check it.
    """
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _ticks(ib, contract, start: datetime, n: int):
    """BID_ASK ticks. Named fields, so nothing about the layout is guessed."""
    return ib.reqHistoricalTicks(
        contract, startDateTime=start.strftime("%Y%m%d %H:%M:%S US/Eastern"),
        endDateTime="", numberOfTicks=n, whatToShow="BID_ASK", useRth=True,
        ignoreSize=False)


def cmd_check(a) -> int:
    """One small request. Prove the subscription serves this before collecting."""
    ib = _connect(a.host, a.port, a.client_id)
    try:
        asked = datetime.now(NY) - timedelta(days=a.days_back)
        when = _last_weekday(asked)
        if when.date() != asked.date():
            print(f"\n{asked:%Y-%m-%d} is a {asked:%A}; using "
                  f"{when:%Y-%m-%d} ({when:%A}) instead")
        print(f"\nasking for the ATM straddle as of {when:%Y-%m-%d}")
        sel = _atm_straddle(ib, when, a.target_dte)
        if sel is None:
            print("[FAIL] no ATM straddle resolved. Either the date is a "
                  "holiday, or no expiry sits within "
                  f"{DTE_WINDOW} days of {a.target_dte} DTE.")
            return 1
        call, put, strike, expiry, dte, spot = sel
        print(f"  spot {spot:.2f}  strike {strike}  expiry {expiry} "
              f"({dte} DTE)")
        print(f"  call conId {call.conId}   put conId {put.conId}")

        for name, c in (("CALL", call), ("PUT", put)):
            t0 = when.replace(hour=12, minute=0, second=0, microsecond=0)
            print(f"\n  reqHistoricalTicks BID_ASK, {name}, from {t0:%H:%M}...")
            try:
                tk = _ticks(ib, c, t0, 10)
            except Exception as exc:                    # noqa: BLE001
                print(f"  [FAIL] request raised: {type(exc).__name__}: {exc}")
                return 1
            if not tk:
                # Do not blame the subscription until a control says so. The
                # same empty result comes from a holiday, a window with no
                # quotes, or a contract nobody quoted that day. Ask for TRADES
                # on the SAME contract and the SAME window: if that returns
                # data and BID_ASK does not, the difference is the entitlement.
                print(f"  [ ?? ] returned 0 ticks for BID_ASK.")
                try:
                    ctrl = ib.reqHistoricalTicks(
                        c, startDateTime=t0.strftime("%Y%m%d %H:%M:%S US/Eastern"),
                        endDateTime="", numberOfTicks=10, whatToShow="TRADES",
                        useRth=True, ignoreSize=False)
                except Exception as exc:                # noqa: BLE001
                    ctrl = []
                    print(f"         control TRADES request raised: {exc}")
                if ctrl:
                    print(f"  [FAIL] but TRADES on the same contract and window "
                          f"returned {len(ctrl)} ticks.\n"
                          f"         Same contract, same window, one works and "
                          f"one does not: that is an\n"
                          f"         entitlement problem. You need the OPRA "
                          f"top-of-book historical subscription.")
                else:
                    print(f"  [FAIL] and TRADES on the same window is also "
                          f"empty, so this is NOT about BID_ASK.\n"
                          f"         The window itself has no data: a holiday, "
                          f"a contract nobody quoted that\n"
                          f"         day, or a date outside IBKR's tick "
                          f"history. Try --days-back 3.")
                return 1
            print(f"  [PASS] {len(tk)} ticks")
            for t in tk[:5]:
                print(f"    {t.time}  bid {t.priceBid:8.2f} x{t.sizeBid:<6} "
                      f"ask {t.priceAsk:8.2f} x{t.sizeAsk:<6}  "
                      f"spread {t.priceAsk - t.priceBid:.2f}")
        print(f"\n  Subscription serves option BID_ASK history. "
              f"Run --collect next.")

        # The check already holds a full straddle quote. Do the arithmetic here
        # rather than leaving it to be done by hand.
        quotes = {}
        for right, c in (("CALL", call), ("PUT", put)):
            t0 = when.replace(hour=12, minute=0, second=0, microsecond=0)
            tk = _ticks(ib, c, t0, 5)
            if tk:
                quotes[right] = (float(tk[-1].priceBid), float(tk[-1].priceAsk),
                                 float(tk[-1].sizeBid), float(tk[-1].sizeAsk))
        if len(quotes) == 2:
            T = dte / 365.0
            tot_spread = tot_vega = 0.0
            print(f"\n  {'':<6}{'bid':>9}{'ask':>9}{'spread':>9}{'IV':>9}"
                  f"{'vol pts':>10}{'bid sz':>9}{'ask sz':>9}")
            print("  " + "-" * 64)
            for right, (b, k, bsz, asz) in quotes.items():
                mid = (b + k) / 2.0
                iv = float(bs.implied_vol(mid, spot, strike, T, R, Q, right))
                v = float(bs.vega(spot, strike, T, R, Q, iv))
                tot_spread += k - b
                tot_vega += v
                print(f"  {right:<6}{b:>9.2f}{k:>9.2f}{k-b:>9.2f}"
                      f"{iv*100:>8.1f}%{(k-b)/(v/100):>10.1f}"
                      f"{bsz:>9.0f}{asz:>9.0f}")
            vp = tot_spread / (tot_vega / 100.0) if tot_vega else float("nan")
            print("  " + "-" * 64)
            print(f"  {'STRADDLE':<6}{'':<18}{tot_spread:>9.2f}{'':>9}"
                  f"{vp:>10.1f}")
            print(f"\n  ONE SAMPLE, ONE MOMENT. Not a distribution — that is "
                  f"what --collect is for.")
            print(f"    measured here                    {vp:>6.1f} vol points")
            print(f"    V28 end-of-day mean (used by V31){EOD_MEAN_VOL_PTS:>6.1f}")
            print(f"    V31 net = edge 11.5 - spread     {11.5 - vp:>+6.1f} "
                  f"(V31 had +1.0)")
        return 0
    finally:
        ib.disconnect()


def cmd_collect(a) -> int:
    ib = _connect(a.host, a.port, a.client_id)
    rows = []
    try:
        day = datetime.now(NY) - timedelta(days=a.days_back)
        done = 0
        while done < a.sessions and day > datetime.now(NY) - timedelta(days=400):
            day = _last_weekday(day)
            try:
                sel = _atm_straddle(ib, day, a.target_dte)
            except Exception as exc:                    # noqa: BLE001
                # A single unresolvable session is not a reason to lose the
                # sessions already collected.
                print(f"  {day:%Y-%m-%d}: {type(exc).__name__}: {exc} — skipping")
                sel = None
            if sel is None:
                print(f"  {day:%Y-%m-%d}: no straddle, skipping")
                day -= timedelta(days=1)
                continue
            call, put, strike, expiry, dte, spot = sel
            print(f"  {day:%Y-%m-%d}: strike {strike} exp {expiry} "
                  f"({dte} DTE) spot {spot:.2f}", flush=True)
            for mins in SAMPLE_MINUTES:
                t0 = (day.replace(hour=9, minute=30, second=0, microsecond=0)
                      + timedelta(minutes=mins))
                for right, c in (("C", call), ("P", put)):
                    try:
                        tk = _ticks(ib, c, t0, TICKS_PER_SAMPLE)
                    except Exception as exc:            # noqa: BLE001
                        print(f"    {t0:%H:%M} {right}: {exc}")
                        time.sleep(a.pause * 2)
                        continue
                    for t in tk:
                        rows.append(dict(
                            session=day.date().isoformat(), right=right,
                            strike=strike, expiry=expiry, dte=dte, spot=spot,
                            ts=pd.Timestamp(t.time), bid=float(t.priceBid),
                            ask=float(t.priceAsk), bid_size=float(t.sizeBid),
                            ask_size=float(t.sizeAsk)))
                    time.sleep(a.pause)
            done += 1
            day -= timedelta(days=1)
    finally:
        ib.disconnect()

    if not rows:
        print("[FAIL] collected nothing. Run --check first.")
        return 1
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame(rows).to_csv(TICKS_CSV, index=False)
    print(f"\nwrote {TICKS_CSV} ({len(rows):,} ticks, {done} sessions)")
    return 0


# ------------------------------------------------- analysis half (testable)
def analyse(df: pd.DataFrame, verbose=True) -> dict:
    """Turn raw BID_ASK ticks into the number the backtest needs.

    Runs with no TWS and no network, which is why it is the half that has
    actually been tested.
    """
    d = df.copy()
    # [FOUND BY SELFTEST] An empty or partly-empty tick file arrives with object
    # dtypes and `np.isfinite` raises on those. An empty file is exactly what a
    # failed --collect produces, so the analyser has to report "nothing here"
    # rather than crash on the way to saying it.
    for col in ("bid", "ask", "bid_size", "ask_size", "strike", "spot", "dte"):
        if col in d:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    if d.empty or not {"bid", "ask"}.issubset(d.columns):
        return dict(n_ticks=0, n_obs=0, mean=np.nan, median=np.nan,
                    bid_size=np.nan, table=pd.DataFrame())
    d = d[(d.bid > 0) & (d.ask > d.bid)]
    d["ts"] = pd.to_datetime(d["ts"], utc=True, errors="coerce")
    d = d.dropna(subset=["ts"])
    if d.empty:
        return dict(n_ticks=0, n_obs=0, mean=np.nan, median=np.nan,
                    bid_size=np.nan, table=pd.DataFrame())
    d["mid"] = (d.bid + d.ask) / 2.0
    d["spread"] = d.ask - d.bid
    d["spread_pct"] = d.spread / d.mid
    T = d["dte"].to_numpy(float) / 365.0

    iv = np.full(len(d), np.nan)
    for right, tag in (("C", "CALL"), ("P", "PUT")):
        m = (d["right"] == right).to_numpy()
        if m.any():
            iv[m] = bs.implied_vol(d["mid"].to_numpy(float)[m],
                                   d["spot"].to_numpy(float)[m],
                                   d["strike"].to_numpy(float)[m], T[m],
                                   R, Q, tag)
    d["iv"] = iv
    d["vega"] = bs.vega(d["spot"].to_numpy(float), d["strike"].to_numpy(float),
                        T, R, Q, iv)
    # per 1.00 of vol -> per volatility point, matching V28's convention
    d["vol_pts"] = d["spread"] / (d["vega"] / 100.0)
    d = d[np.isfinite(d["vol_pts"]) & (d["vol_pts"] > 0)]

    ny = d["ts"].dt.tz_convert(NY)
    d["minute"] = ny.dt.hour * 60 + ny.dt.minute - (9 * 60 + 30)

    # A straddle pays BOTH legs. Pair them per (session, sample minute).
    d["bucket"] = (d["minute"] // 15) * 15
    leg = d.groupby(["session", "bucket", "right"]).agg(
        spread=("spread", "mean"), vega=("vega", "mean"),
        bid_size=("bid_size", "median"), ask_size=("ask_size", "median"))
    strad = leg.groupby(["session", "bucket"]).agg(
        spread=("spread", "sum"), vega=("vega", "sum"),
        legs=("spread", "size"), bid_size=("bid_size", "min"),
        ask_size=("ask_size", "min"))
    strad = strad[strad["legs"] == 2].copy()
    strad["vol_pts"] = strad["spread"] / (strad["vega"] / 100.0)

    out = dict(n_ticks=len(d), n_obs=len(strad),
               mean=float(strad.vol_pts.mean()) if len(strad) else np.nan,
               median=float(strad.vol_pts.median()) if len(strad) else np.nan,
               bid_size=float(strad.bid_size.median()) if len(strad) else np.nan,
               table=strad)
    if not verbose:
        return out

    w = 80
    print("=" * w)
    print("MEASURED INTRADAY STRADDLE SPREAD — from IBKR BID_ASK ticks")
    print("=" * w)
    print(f"  {len(d):,} ticks, {d.session.nunique()} sessions, "
          f"{len(strad)} straddle observations\n")
    print(f"  {'time':<10}{'obs':>6}{'spread $':>11}{'% of mid':>11}"
          f"{'VOL POINTS':>13}{'bid size':>10}")
    print("  " + "-" * 61)
    for b, g in strad.groupby("bucket"):
        hh, mm = divmod(int(b) + 9 * 60 + 30, 60)
        pct = d[d.bucket == b]["spread_pct"].mean() * 100
        print(f"  {hh:02d}:{mm:02d}{'':<5}{len(g):>6}{g.spread.mean():>11.2f}"
              f"{pct:>10.1f}%{g.vol_pts.mean():>13.1f}{g.bid_size.median():>10.0f}")
    print("  " + "-" * 61)
    print(f"  {'ALL':<10}{len(strad):>6}{strad.spread.mean():>11.2f}"
          f"{d.spread_pct.mean()*100:>10.1f}%{out['mean']:>13.1f}"
          f"{out['bid_size']:>10.0f}")

    print(f"\n  {'':<34}{'vol points':>12}")
    print("  " + "-" * 48)
    print(f"  {'measured intraday, mean':<34}{out['mean']:>12.1f}")
    print(f"  {'measured intraday, median':<34}{out['median']:>12.1f}")
    print(f"  {'V28 end-of-day, mean (used by V31)':<34}"
          f"{EOD_MEAN_VOL_PTS:>12.1f}")
    print(f"  {'V28 end-of-day, median':<34}{EOD_MEDIAN_VOL_PTS:>12.1f}")
    delta = EOD_MEAN_VOL_PTS - out["mean"]
    print(f"  {'DIFFERENCE (EOD minus intraday)':<34}{delta:>+12.1f}")

    print(f"""
  WHAT THIS DOES TO V31

  V31 measured the straddle's gross volatility edge at +11.5 points and its
  round-trip spread at {EOD_MEAN_VOL_PTS:.1f}, leaving +1.0 net, which came out to
  -2.94% of premium per cycle. Substituting the measured intraday spread:

    edge                      +11.5
    measured spread           {-out['mean']:+.1f}
    net                       {11.5 - out['mean']:+.1f}  (V31 had +1.0)

  That is {'BETTER' if delta > 0 else 'WORSE'} than the backtest assumed by {abs(delta):.1f} vol points.
  {'A positive net does not by itself overturn V31 -- the vol-point arithmetic ran 2.3x optimistic against the actual P&L (V31: predicted +$787, actual +$347), so scale accordingly.' if 11.5 - out['mean'] > 0 else 'This makes V31 an understatement of the loss, not an overstatement.'}

  DEPTH. Median size at the touch is {out['bid_size']:.0f} contracts. The backtest
  traded 10 per leg. {'That fits.' if out['bid_size'] >= 10 else 'That does NOT fit -- an order for 10 walks the book, so even this measured spread is optimistic for the size traded.'}
""")
    return out


def cmd_analyse(a) -> int:
    if not os.path.exists(TICKS_CSV):
        print(f"[FAIL] {TICKS_CSV} not found. Run --collect first.")
        return 1
    analyse(pd.read_csv(TICKS_CSV))
    return 0


# --------------------------------------------------------------- self-test
def _selftest() -> int:
    """Exercise the analysis on ticks with a spread whose answer is known.

    Builds a synthetic ATM option where vega is computable by hand, so a wrong
    unit conversion in `vol_pts` shows up as a number that is 100x off — the
    exact error V28 shipped once already.
    """
    print("=" * 72)
    print("SELF-TEST — the half that does not need TWS")
    print("=" * 72)
    fails = 0

    def ok(name, cond, detail=""):
        nonlocal fails
        if not cond:
            fails += 1
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}{'  ' + detail if detail else ''}")

    S, K, dte = 100.0, 100.0, 37
    T = dte / 365.0
    sigma = 1.00
    fair_c = float(bs.price(S, K, T, R, Q, sigma, "CALL"))
    fair_p = float(bs.price(S, K, T, R, Q, sigma, "PUT"))
    v = float(bs.vega(S, K, T, R, Q, sigma))          # per 1.00 of vol
    half = 0.05 * v                                    # spread worth 10 vol pts

    rows = []
    base = pd.Timestamp("2026-08-25 14:00:00", tz="UTC")
    for i in range(20):
        for right, fair in (("C", fair_c), ("P", fair_p)):
            rows.append(dict(session="2026-08-25", right=right, strike=K,
                             expiry="20261001", dte=dte, spot=S,
                             ts=base + pd.Timedelta(seconds=i),
                             bid=fair - half, ask=fair + half,
                             bid_size=7, ask_size=9))
    got = analyse(pd.DataFrame(rows), verbose=False)

    # both legs, each 10 vol points -> straddle spread / straddle vega is still
    # 10 vol points, because both scale together
    ok("vol points recovered from a known spread",
       abs(got["mean"] - 10.0) < 0.5, f"got {got['mean']:.2f}, expected 10.00")
    ok("a 100x unit error would be caught",
       not (90 < got["mean"] < 110) and not (0.05 < got["mean"] < 0.15))
    ok("both legs paired into one straddle observation",
       got["n_obs"] == 1, f"n_obs={got['n_obs']}")
    ok("depth is the MINIMUM across legs, not the mean",
       abs(got["bid_size"] - 7) < 1e-9, f"got {got['bid_size']}")

    empty = analyse(pd.DataFrame(columns=list(rows[0])), verbose=False)
    ok("an empty file yields NaN, not zero",
       np.isnan(empty["mean"]), "zero would read as a free straddle")

    bad = pd.DataFrame(rows).assign(ask=lambda x: x.bid - 0.01)
    ok("inverted quotes are dropped",
       analyse(bad, verbose=False)["n_ticks"] == 0)

    print("\n" + "=" * 72)
    print("FAILURES: 0" if not fails else f"FAILURES: {fails}")
    print("""
  NOT tested here, because this machine has no TWS: _connect, _atm_straddle,
  _ticks, cmd_check, cmd_collect. Every one of those is IBKR I/O and the first
  real run should be treated as a debugging session.""")
    return 1 if fails else 0


def cmd_doctor() -> int:
    """Which Python is this, and can it see what it needs?"""
    print("=" * 72)
    print("INTERPRETER CHECK")
    print("=" * 72)
    print(f"  executable  {sys.executable}")
    print(f"  version     {sys.version.split()[0]}")
    print(f"  sys.prefix  {sys.prefix}")
    venv = os.environ.get("VIRTUAL_ENV", "(none)")
    print(f"  VIRTUAL_ENV {venv}")
    if venv != "(none)":
        match = os.path.normcase(os.path.abspath(sys.prefix)) == \
            os.path.normcase(os.path.abspath(venv))
        print(f"  {'[PASS]' if match else '[FAIL]'} sys.prefix "
              f"{'matches' if match else 'DOES NOT MATCH'} VIRTUAL_ENV")
        if not match:
            print("         You are running a different Python from the one "
                  "pip installs into.\n"
                  "         On Windows use `python`, not `python3`.")
    print()
    for mod in ("numpy", "pandas", "ib_async"):
        try:
            m = __import__(mod)
            v = getattr(m, "__version__", "?")
            print(f"  [PASS] {mod:<10} {v:<10} {getattr(m, '__file__', '')}")
        except ImportError as exc:
            print(f"  [FAIL] {mod:<10} {exc}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--doctor", action="store_true",
                    help="which interpreter am I on and can it import ib_async")
    ap.add_argument("--check", action="store_true",
                    help="one small request: does the subscription serve this?")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sessions", type=int, default=10)
    ap.add_argument("--days-back", type=int, default=1,
                    help="start this many days before today")
    ap.add_argument("--target-dte", type=int, default=TARGET_DTE)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497, help="7497 TWS paper")
    ap.add_argument("--client-id", type=int, default=98)
    ap.add_argument("--pause", type=float, default=2.0,
                    help="seconds between requests (IBKR pacing)")
    a = ap.parse_args()

    if a.doctor:
        return cmd_doctor()
    if a.selftest:
        return _selftest()
    if a.check:
        return cmd_check(a)
    if a.collect:
        return cmd_collect(a)
    if a.analyse:
        return cmd_analyse(a)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
