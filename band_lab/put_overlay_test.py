"""
Documented negative: long-dated protective put overlay on the day sleeve.

Question (2026-07-28): does a rolling LEAP-style protective put help the
sleeve through multi-day/multi-week drawdowns?

Method: real SOXL EOD chains 2022-01..2026-07 (bought at ask, sold at
bid, marked at mid). Policy: hold puts covering sleeve equity notionally
(contracts = equity / (100 x spot)), expiry nearest 180 DTE (120-400
window), strike nearest 0.8 x spot, roll when DTE < 60. Sleeve = locked
core, f=1.0 compounded from $150K.

Result: CAGR 146.1% -> 125.0%, max drawdown -36.5% -> -60.0% (WORSE),
overlay net P&L -$2.85M (~-$634K/yr at compounded size); during the
Nov-2025..Mar-2026 sleeve drawdown the overlay LOST a further $1.6M.
Mechanism: SOXL ROSE +11.9% during that drawdown — the sleeve's losing
streaks are chop, not slides (corr(sleeve pnl, SOXL return) = 0.4), so a
put hedges a risk the sleeve does not have while paying 80-110% IV.
Third independent confirmation that bought options are structurally
unprofitable in this system (round-1 cycle puts, V8 shorts, this).
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars, load_opts
from v5_corrected_rerun import sim_trades_fixed, day_pnl

OUT = os.path.join(HERE, "out")

def core_series():
    bars = load_bars(); g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["range_pct"] = (daily["h"] - daily["l"]) / daily["o"] * 100
    daily["atr5"] = daily["range_pct"].rolling(5).mean().shift()
    or30, pos10 = {}, {}
    for d, gb in g:
        hh = gb["High"].to_numpy()[:6]; ll = gb["Low"].to_numpy()[:6]
        cc = gb["Close"].to_numpy()
        orh, orl = hh.max(), ll.min()
        or30[d] = (orh - orl) / gb["Open"].iloc[0] * 100
        pos10[d] = (cc[5] - orl) / (orh - orl) if orh > orl and len(cc) > 5 else .5
    daily["or30"] = pd.Series(or30); daily["pos10"] = pd.Series(pos10)
    daily["thr80"] = daily["or30"].shift(1).rolling(504, min_periods=120).quantile(.8)
    on = ((daily["or30"] < daily["thr80"]) |
          ((daily["or30"] >= daily["thr80"]) & (daily["pos10"] >= 2/3))) \
         & (daily["atr5"] >= 6)
    pnl = {}
    for dd, gb in g:
        if not on.get(dd, False) or len(gb) < 20:
            continue
        o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
        pnl[dd] = day_pnl(sim_trades_fixed(o, h, l, c, 18))
    return daily, pd.Series(pnl).reindex(daily.index).fillna(0.0)

def main():
    daily, full = core_series()
    puts = load_opts()
    puts = puts[puts["right"] == "PUT"]
    by_day = {d: grp for d, grp in puts.groupby("trade_date")}
    start, end = pd.Timestamp("2022-01-03"), pd.Timestamp("2026-07-02")
    days = [d for d in daily.index if start <= d <= end]
    E = 150000.0; pos = None; cash = 0.0; rows = []
    for d in days:
        E *= (1 + full.get(d, 0.0))
        spot = daily.loc[d, "c"]
        ch = by_day.get(d)
        if ch is not None and (pos is None or (pos["exp"] - d).days < 60):
            if pos is not None:
                m = ch[(ch["expiration"] == pos["exp"]) & (ch["strike"] == pos["strike"])]
                px = m.iloc[0]["bid"] if len(m) else max(pos["strike"] - spot, 0)
                cash += pos["n"] * 100 * px
                pos = None
            cand = ch[(ch["expiration"] > d + pd.Timedelta(days=120)) &
                      (ch["expiration"] < d + pd.Timedelta(days=400)) & (ch["ask"] > 0)]
            if len(cand):
                texp = cand.loc[((cand["expiration"] - d).dt.days - 180).abs().idxmin(),
                                "expiration"]
                cc2 = cand[cand["expiration"] == texp]
                srow = cc2.loc[(cc2["strike"] - 0.8 * spot).abs().idxmin()]
                n = E / (100 * spot)
                cash -= n * 100 * srow["ask"]
                pos = {"exp": texp, "strike": srow["strike"], "n": n,
                       "last": srow["ask"]}
        v = 0.0
        if pos is not None:
            if ch is not None:
                m = ch[(ch["expiration"] == pos["exp"]) & (ch["strike"] == pos["strike"])]
                if len(m):
                    b, a = m.iloc[0]["bid"], m.iloc[0]["ask"]
                    pos["last"] = (b + a) / 2 if a > 0 and b > 0 else max(b, 0.0)
            v = pos["n"] * 100 * max(pos["last"], 0)
        rows.append({"date": d, "sleeve": E, "overlay": cash + v})
    df = pd.DataFrame(rows).set_index("date")
    df["combined"] = df["sleeve"] + df["overlay"]
    df.to_csv(os.path.join(OUT, "put_overlay_curves.csv"))
    yrs = (days[-1] - days[0]).days / 365.25
    for nm, col in [("sleeve alone", df["sleeve"]),
                    ("sleeve + LEAP put overlay", df["combined"])]:
        pk = col.cummax()
        print(f"{nm:28s} final ${col.iloc[-1]:>12,.0f}  "
              f"CAGR {((col.iloc[-1]/col.iloc[0])**(1/yrs)-1)*100:5.1f}%  "
              f"maxDD {((col-pk)/pk).min()*100:6.1f}%")
    print(f"overlay net P&L: ${df['overlay'].iloc[-1]:,.0f}")

if __name__ == "__main__":
    main()
