#!/usr/bin/env python3
"""
intraday_microstructure.py  --  NEUTRAL intraday fingerprint (5-min, 2023-07..2026-07).

A daily-rebalanced 3x ETF must trade in the direction of the day's move near the
close to reset its leverage -- a mechanical flow that should leave footprints. We
look for them without assuming a trade:

  1. OVERNIGHT vs INTRADAY: where does return and risk actually live (gap vs session)?
  2. TIME-OF-DAY volatility profile: when in the session does SOXL move?
  3. END-OF-DAY REBALANCING momentum: does the last ~25 min continue the day's move
     (the leverage-reset flow)? -- and is it tradeable?
  4. 5-min autocorrelation / variance ratio: momentum or reversion intraday?
Outputs a printed report + outputs/intraday_microstructure.png.
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
pd.set_option("display.width", 200)


def hr(t): print("\n" + "=" * 84 + f"\n{t}\n" + "=" * 84)


def main():
    hr("LOAD 5-min underlying")
    fm = load_5min()
    fm["ts"] = pd.to_datetime(fm["ts"]); fm["date"] = fm["ts"].dt.date
    fm["t"] = fm["ts"].dt.time
    print(f"{len(fm):,} bars | {fm['date'].min()} -> {fm['date'].max()} | {fm['date'].nunique()} days")

    # daily open (first bar open) / close (last bar close)
    day = fm.groupby("date").agg(open=("Open", "first"), close=("Close", "last"),
                                 high=("High", "max"), low=("Low", "min")).reset_index()
    day["prev_close"] = day["close"].shift(1)
    day = day.dropna()
    overnight = day["open"] / day["prev_close"] - 1        # close -> next open
    intraday = day["close"] / day["open"] - 1              # open -> close
    total = day["close"] / day["prev_close"] - 1

    # ---------------------------------------------------------------- 1 overnight/intraday
    hr("1.  OVERNIGHT (gap) vs INTRADAY (session) -- where return & risk live")
    def stat(x): return (x.mean(), x.std(), x.mean() / x.std() * np.sqrt(252))
    for lbl, x in [("overnight close->open", overnight), ("intraday  open->close", intraday),
                   ("total     close->close", total)]:
        m, s, sh = stat(x)
        print(f"  {lbl}: mean {m:+.3%}/day  vol {s:.2%}/day ({s*np.sqrt(252):.0%}/yr)  "
              f"ann.Sharpe {sh:+.2f}  sum {(x).sum():+.1%}")
    print(f"\n  share of total variance: overnight {overnight.var()/(overnight.var()+intraday.var()):.0%}  "
          f"intraday {intraday.var()/(overnight.var()+intraday.var()):.0%}")
    print(f"  corr(overnight, same-day intraday): {np.corrcoef(overnight, intraday)[0,1]:+.2f}  "
          f"(negative = gaps partly reverse during the day)")

    # ---------------------------------------------------------------- 2 time of day
    hr("2.  TIME-OF-DAY VOLATILITY PROFILE (avg |5-min return| by bar)")
    fm = fm.sort_values("ts")
    fm["ret5"] = fm.groupby("date")["Close"].pct_change()
    prof = fm.dropna(subset=["ret5"]).groupby("t")["ret5"].agg(
        absmean=lambda s: s.abs().mean(), n="size")
    prof = prof[prof["n"] > 100]
    peak_t = prof["absmean"].idxmax(); open_v = prof["absmean"].iloc[0]; close_v = prof["absmean"].iloc[-1]
    mid = prof["absmean"].iloc[len(prof)//2]
    print(f"  open (09:35) |ret| {prof['absmean'].iloc[0]:.3%}   midday {mid:.3%}   "
          f"close (15:55) {close_v:.3%}   peak at {peak_t} ({prof['absmean'].max():.3%})")
    print(f"  open/midday ratio {open_v/mid:.1f}x   close/midday ratio {close_v/mid:.1f}x  "
          f"(>1 = U-shape / active open & close)")

    # ---------------------------------------------------------------- 3 EOD rebalancing
    hr("3.  END-OF-DAY REBALANCING MOMENTUM (the leverage-reset flow)")
    # split each day: early (open->15:30) vs last (15:30->close)
    def window_ret(g, t0, t1):
        gg = g[(g["t"] >= t0) & (g["t"] <= t1)]
        if len(gg) < 2:
            return np.nan
        return gg["Close"].iloc[-1] / gg["Open"].iloc[0] - 1
    import datetime as dt
    early, last = [], []
    for d, g in fm.groupby("date"):
        early.append(window_ret(g, dt.time(9, 30), dt.time(15, 30)))
        last.append(window_ret(g, dt.time(15, 30), dt.time(15, 55)))
    e = pd.Series(early); l = pd.Series(last)
    ok = e.notna() & l.notna(); e, l = e[ok], l[ok]
    print(f"  corr(early-day return, last-25min return) = {np.corrcoef(e, l)[0,1]:+.2f}  "
          f"(+ = last bars CONTINUE the day = rebalancing momentum)")
    up = e > 0
    print(f"  last-25min mean when day was UP so far:   {l[up].mean():+.3%}  (n={up.sum()})")
    print(f"  last-25min mean when day was DOWN so far: {l[~up].mean():+.3%}  (n={(~up).sum()})")
    print(f"  spread (up minus down): {l[up].mean()-l[~up].mean():+.3%} per day  "
          f"-- a directional close-tilt in the day's direction")

    # ---------------------------------------------------------------- 4 5-min AC
    hr("4.  5-MIN autocorrelation (intraday momentum vs reversion)")
    x = fm.dropna(subset=["ret5"])["ret5"].values
    x = x - x.mean(); den = np.sum(x * x)
    for k in (1, 2, 3, 6, 12):
        ac = np.sum(x[k:] * x[:-k]) / den
        print(f"    lag {k:2d} ({k*5:2d} min): {ac:+.3f}")
    print(f"    (95% band +/-{1.96/np.sqrt(len(x)):.3f})   negative lag-1 = bid/ask bounce / micro-reversion")

    _plot(prof, overnight, intraday, e, l)
    print(f"\nsaved {OUT/'intraday_microstructure.png'}")


def _plot(prof, overnight, intraday, e, l):
    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    ax[0, 0].plot([str(t)[:5] for t in prof.index], prof["absmean"].values * 100)
    ax[0, 0].set_title("time-of-day |5-min return| (%) — vol profile")
    ax[0, 0].set_xticks(ax[0, 0].get_xticks()[::6]); ax[0, 0].tick_params(axis="x", rotation=45)
    ax[0, 1].hist(overnight, bins=60, alpha=0.5, label="overnight", density=True)
    ax[0, 1].hist(intraday, bins=60, alpha=0.5, label="intraday", density=True)
    ax[0, 1].set_yscale("log"); ax[0, 1].legend(); ax[0, 1].set_title("overnight vs intraday return dist")
    ax[1, 0].scatter(e, l, s=4, alpha=0.3)
    ax[1, 0].set_xlabel("early-day return"); ax[1, 0].set_ylabel("last-25min return")
    ax[1, 0].set_title(f"EOD rebalancing: corr {np.corrcoef(e,l)[0,1]:+.2f}")
    ax[1, 0].axhline(0, c="k", lw=.5); ax[1, 0].axvline(0, c="k", lw=.5)
    ax[1, 1].plot(overnight.cumsum().values, label="overnight cum")
    ax[1, 1].plot(intraday.cumsum().values, label="intraday cum")
    ax[1, 1].legend(); ax[1, 1].set_title("cumulative overnight vs intraday return")
    fig.tight_layout(); fig.savefig(OUT / "intraday_microstructure.png", dpi=110)


if __name__ == "__main__":
    main()
