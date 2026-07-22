#!/usr/bin/env python3
"""
eval_overnight.py  --  EVALUATE finding B': is SOXL's return concentrated overnight,
and is capturing it (hold close->open, flat intraday) actually better than holding?

Tested on the data we HAVE (5-min underlying, 2023-07..2026-07). Everything that is
a proxy/assumption is labelled inline and summarized at the end, with the extra data
that would strengthen the test and its expected impact.

Strategies (daily, long SOXL, no extra leverage beyond SOXL's built-in 3x):
  BUY&HOLD   : hold continuously (close->close). Trades ~once; no daily cost.
  OVERNIGHT  : long from close to next open, flat during the day. 2 fills/day.
  INTRADAY   : long from open to close, flat overnight. 2 fills/day.
Costs are modelled as `c` bps per side (spread + commission + auction impact),
swept, because the daily-trading strategies must overcome ~2*c*252 per year that
buy&hold does not pay.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import load_5min  # noqa: E402

OUT = Path(__file__).resolve().parent / "outputs"; OUT.mkdir(exist_ok=True)
ANN = 252
pd.set_option("display.width", 200)


def hr(t): print("\n" + "=" * 86 + f"\n{t}\n" + "=" * 86)


def curve_stats(r):
    r = np.asarray(r)
    eq = np.cumprod(1 + r)
    cagr = eq[-1] ** (ANN / len(r)) - 1
    vol = r.std(ddof=1) * np.sqrt(ANN)
    sharpe = r.mean() / r.std(ddof=1) * np.sqrt(ANN) if r.std() > 0 else np.nan
    dd = (np.concatenate([[1.0], eq]) / np.maximum.accumulate(np.concatenate([[1.0], eq])) - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sharpe, maxdd=dd, end=eq[-1]), eq


def main():
    hr("LOAD 5-min underlying -> daily open/close")
    fm = load_5min(); fm["ts"] = pd.to_datetime(fm["ts"]); fm["date"] = fm["ts"].dt.date
    day = fm.groupby("date").agg(open=("Open", "first"), close=("Close", "last")).reset_index()
    day["prev_close"] = day["close"].shift(1)
    day = day.dropna().reset_index(drop=True)
    day["overnight"] = day["open"] / day["prev_close"] - 1     # PROXY: 15:55 close -> 09:30 open
    day["intraday"] = day["close"] / day["open"] - 1
    day["buyhold"] = day["close"] / day["prev_close"] - 1
    day["year"] = pd.to_datetime(day["date"]).dt.year
    n = len(day)
    print(f"{n} days | {day['date'].min()} -> {day['date'].max()}")
    print("NOTE proxies: 'close'=15:55 last bar (not the 16:00 auction); 'open'=09:30 first "
          "bar.\n     overnight = 15:55->09:30 (omits 15:55-16:00). MOC/MOO fills would differ.")

    # ---------------------------------------------------------------- headline (0 cost)
    hr("1.  HEADLINE (0 cost): does the return live overnight, risk-adjusted?")
    print(f"  {'strategy':10s} {'CAGR':>7} {'ann vol':>8} {'Sharpe':>7} {'maxDD':>7} {'end x':>7}")
    curves = {}
    for name, col in [("BUY&HOLD", "buyhold"), ("OVERNIGHT", "overnight"), ("INTRADAY", "intraday")]:
        s, eq = curve_stats(day[col].values); curves[name] = eq
        print(f"  {name:10s} {s['cagr']:>+7.0%} {s['vol']:>8.0%} {s['sharpe']:>+7.2f} "
              f"{s['maxdd']:>+7.0%} {s['end']:>6.1f}x")
    print("\n  -> OVERNIGHT vs BUY&HOLD: the key is Sharpe & drawdown (same instrument, less time exposed).")

    # ---------------------------------------------------------------- drag decomposition
    hr("2.  WHY overnight can WIN despite less exposure: it dodges the volatility drag")
    print("  variance drain = (mean simple return) - (mean log return) per day, annualized")
    print("  (this is the exact compounding tax; ~0.5*sigma^2, and always >= 0):")
    for name, col in [("BUY&HOLD", "buyhold"), ("OVERNIGHT", "overnight"), ("INTRADAY", "intraday")]:
        r = day[col].values
        geo = np.expm1(np.mean(np.log1p(r)) * ANN)
        drain = (r.mean() - np.mean(np.log1p(r))) * ANN          # exact, >= 0
        print(f"  {name:10s}: compounded {geo:+.0%}/yr  ann vol {r.std()*np.sqrt(ANN):.0%}  "
              f"variance drain {drain:.0%}/yr  (~0.5*sig^2 = {0.5*(r.std()*np.sqrt(ANN))**2:.0%})")
    drO = (day['overnight'].mean() - np.mean(np.log1p(day['overnight']))) * ANN
    drB = (day['buyhold'].mean() - np.mean(np.log1p(day['buyhold']))) * ANN
    print(f"  -> OVERNIGHT bleeds ~{drO:.0%}/yr to drag vs BUY&HOLD's ~{drB:.0%}/yr: it SAVES "
          f"~{drB-drO:.0%}/yr\n     because it is exposed only to the lower-vol overnight session.")

    # ---------------------------------------------------------------- cost sensitivity
    hr("3.  TRADING-COST SENSITIVITY (the real hurdle: ~504 fills/yr vs buy&hold's ~1)")
    print(f"  {'c (bps/side)':>12} | {'OVERNIGHT CAGR':>15} {'Sharpe':>7} | {'INTRADAY CAGR':>14} | {'B&H CAGR':>9}")
    bh_cagr = curve_stats(day['buyhold'].values)[0]['cagr']
    for c in (0, 1, 2, 3, 5):
        on = day["overnight"].values - 2 * c / 10000
        idr = day["intraday"].values - 2 * c / 10000
        so = curve_stats(on)[0]; si = curve_stats(idr)[0]
        print(f"  {c:>12} | {so['cagr']:>+15.0%} {so['sharpe']:>+7.2f} | {si['cagr']:>+14.0%} | {bh_cagr:>+9.0%}")
    print("  (SOXL ETF spread is ~1-3 bps; MOC/MOO auctions usually fill near the print.)")

    # ---------------------------------------------------------------- by year
    hr("4.  BY YEAR (does the overnight drift survive down/choppy years?)")
    print(f"  {'year':>4} | {'B&H':>6} {'OVERNIGHT':>10} {'INTRADAY':>9} | {'ON Sharpe':>10}")
    for y, g in day.groupby("year"):
        b = np.cumprod(1 + g['buyhold'].values)[-1] - 1
        o = np.cumprod(1 + g['overnight'].values)[-1] - 1
        i = np.cumprod(1 + g['intraday'].values)[-1] - 1
        osh = g['overnight'].mean() / g['overnight'].std() * np.sqrt(ANN)
        print(f"  {y:>4} | {b:>+6.0%} {o:>+10.0%} {i:>+9.0%} | {osh:>+10.2f}")

    # ---------------------------------------------------------------- robustness: down days
    hr("5.  ROBUSTNESS: overnight edge conditioned on regime")
    # is overnight positive even when buy&hold is negative that day? and in down months?
    dm = day.copy(); dm["ym"] = pd.to_datetime(dm["date"]).dt.to_period("M")
    mon = dm.groupby("ym").agg(bh=("buyhold", lambda s: np.prod(1+s)-1),
                               on=("overnight", lambda s: np.prod(1+s)-1)).reset_index()
    down = mon["bh"] < 0
    print(f"  months where BUY&HOLD was DOWN (n={down.sum()}): overnight mean {mon.loc[down,'on'].mean():+.1%}/mo, "
          f"positive {np.mean(mon.loc[down,'on']>0):.0%} of them")
    print(f"  months where BUY&HOLD was UP   (n={(~down).sum()}): overnight mean {mon.loc[~down,'on'].mean():+.1%}/mo")
    # overnight return correlation with buyhold (is it just beta?)
    print(f"  corr(overnight daily, buy&hold daily) = {np.corrcoef(day['overnight'], day['buyhold'])[0,1]:+.2f} "
          f"(high = mostly beta; the edge is the DRAG/Sharpe difference, not independence)")

    _plot(day, curves)
    _caveats()
    print(f"\nsaved {OUT/'eval_overnight.png'}")


def _plot(day, curves):
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    x = pd.to_datetime(day["date"])
    for name, eq in curves.items():
        ax[0].plot(x, eq, label=f"{name} ({eq[-1]:.1f}x)", lw=1.4)
    ax[0].set_yscale("log"); ax[0].legend(); ax[0].set_ylabel("growth of $1 (log)")
    ax[0].set_title("Overnight vs Intraday vs Buy&Hold (0 cost), 2023-07..2026-07")
    # overnight CAGR vs cost
    cs = np.arange(0, 6)
    oc = [curve_stats(day["overnight"].values - 2*c/10000)[0]["cagr"] for c in cs]
    bh = curve_stats(day["buyhold"].values)[0]["cagr"]
    ax[1].plot(cs, np.array(oc)*100, "o-", label="OVERNIGHT")
    ax[1].axhline(bh*100, c="gray", ls="--", label=f"BUY&HOLD ({bh:.0%})")
    ax[1].set_xlabel("cost (bps per side)"); ax[1].set_ylabel("CAGR %")
    ax[1].set_title("overnight CAGR vs trading cost"); ax[1].legend()
    fig.tight_layout(); fig.savefig(OUT / "eval_overnight.png", dpi=110)


def _caveats():
    hr("PROXIES / ASSUMPTIONS  &  ADDITIONAL DATA NEEDED")
    print("""  PROXIES & ASSUMPTIONS (all in-sample, honestly limited):
   - Window 2023-07..2026-07 only (5-min underlying start). Misses the 2022 bear
     (-87%) and early-2023. Overnight drift being positive here partly coincides
     with a net-up period -- the by-year & down-month checks probe this but cannot
     replace a full-cycle test.
   - 'close' = 15:55 last 5-min bar, NOT the 16:00 closing auction; 'open' = 09:30
     first bar. True MOC/MOO fills differ (the 15:55-16:00 move is unmeasured).
   - No financing/borrow modelled; the ~6.5h/day of intraday CASH could earn the
     risk-free rate (~5% in 2023-25) -> a small TAILWIND for OVERNIGHT that is
     omitted (conservative).
   - Costs modelled as flat bps/side; real auction impact varies with size.
   - This is a KNOWN anomaly (the 'overnight/night effect'); measured, not proven
     to persist forward.

  ADDITIONAL DATA THAT WOULD STRENGTHEN THIS TEST (and its impact):
   1. Daily OPEN prices for SOXL 2022-01..2023-06 (or 5-min back to 2022): extends
      the test across the 2022 BEAR + 2021 -- decisive for 'is overnight drift a
      persistent premium or a bull-period artifact?'. HIGHEST value.
   2. Official 16:00 close & 09:30 open auction prints: removes the 15:55 proxy,
      makes fills exact. MODERATE value.
   3. Overnight index-futures / after-hours SOXL prints: to see if the gap is
      continuous drift or a discrete open jump (affects executability). LOW-MOD.
   4. Financing/borrow + risk-free series: to net the cash-leg carry. LOW value
      (small, and currently omitted conservatively).""")


if __name__ == "__main__":
    main()
