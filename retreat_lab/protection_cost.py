"""What overnight put protection on SOXL actually cost, 2021-2026.

The retreat study showed stop slippage concentrates overnight: at 5%/2%, 52% of
all slippage comes from the ~11% of episodes whose retreat crosses a session
close, and a 0.5% stop actually fills 0.80% below the peak. A put is
enforceable across a close where a stop is not. This prices that put.

Method — buy at the last print of the session, sell at the first print of the
next, per contract:
  entry  15:55 trade print on day D   (16:00 bars exist but NEVER carry a trade)
  exit   09:30 trade print on day D+1
  cost   (entry - exit) / spot_at_D_close, in bps of the underlying notional
         the put protects -- positive = protection cost you, negative = it paid

Data: raw_data/SOXL_intraday_5m_exp_*.csv, 736 files, Polygon-style 5-min
option TRADE aggregates. These are PRINTS, NOT QUOTES, so a measured cost is a
LOWER BOUND: you would buy nearer the ask and sell nearer the bid, and the
half-spread on both sides is not in these numbers.

Usage:  python3 retreat_lab/protection_cost.py
"""
import json, csv, datetime as dt, os, sys
from statistics import mean, median
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT, pct

CACHE = "/tmp/claude-0/-home-user-TradingModel/50ac25d8-892f-559b-b09e-cc99c4333d8d/scratchpad/puts.json"


def underlying():
    close, opn = {}, {}
    with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
        r = csv.reader(f); next(r)
        for a in r:
            t = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            d = t.date()
            if d not in opn:
                opn[d] = float(a[1])
            close[d] = float(a[4])
    return close, opn


def main():
    close, opn = underlying()
    days = sorted(close)
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}

    px = defaultdict(dict)
    for exp, K, d, hm, p, cnt, vol in json.load(open(CACHE)):
        px[(exp, K)][(d, hm)] = (p, cnt)

    trades = []
    for (exp, K), v in px.items():
        E = dt.date.fromisoformat(exp)
        for (d, hm), (p, cnt) in v.items():
            if hm != "15:55":
                continue
            D = dt.date.fromisoformat(d)
            if D not in nxt or D not in close:
                continue
            D2 = nxt[D]
            dte = (E - D).days
            if dte < 1:                       # must survive the night
                continue
            k2 = (D2.isoformat(), "09:30")
            if k2 not in v:
                continue
            S, S2 = close[D], opn[D2]
            trades.append(dict(D=D, dte=dte, K=K, S=S,
                               m=K / S - 1, entry=p, exit=v[k2][0],
                               gap=S2 / S - 1, cnt=cnt))
    print(f"paired 15:55 → next-09:30 put trades: {len(trades):,}")
    print(f"distinct overnights: {len(set(t['D'] for t in trades)):,}   "
          f"{min(t['D'] for t in trades)} → {max(t['D'] for t in trades)}\n")

    def show(rows, lbl):
        if len(rows) < 25:
            print(f"  {lbl:<26} n={len(rows):<5} (too thin)"); return
        # cost in bps of the underlying notional the put protects
        bps = [(t["entry"] - t["exit"]) / t["S"] * 10000 for t in rows]
        ret = [(t["exit"] - t["entry"]) / t["entry"] for t in rows]
        prem = [t["entry"] / t["S"] * 10000 for t in rows]
        paid = sum(1 for b in bps if b < 0)
        print(f"  {lbl:<26} n={len(rows):<5} prem {median(prem):>6.0f}bp  "
              f"cost/night med {median(bps):>6.1f}bp mean {mean(bps):>7.1f}bp  "
              f"p10 {pct(bps,10):>7.1f} p90 {pct(bps,90):>6.1f}  "
              f"paid-off {paid/len(rows):>5.1%}  putret med {median(ret):>7.1%}")

    MB = [("ATM  |m|<1%", -0.01, 0.01), ("OTM 1-3%", -0.03, -0.01),
          ("OTM 3-7%", -0.07, -0.03), ("OTM 7-15%", -0.15, -0.07)]
    DB = [("1-2 DTE", 1, 2), ("3-7 DTE", 3, 7), ("8-14 DTE", 8, 14),
          ("15-45 DTE", 15, 45)]

    print("COST OF ONE NIGHT OF PUT PROTECTION, in basis points of the SOXL")
    print("notional protected (positive = it cost you; negative = it paid off)\n")
    for dl, lo, hi in DB:
        print(f"--- {dl} ---")
        for ml, mlo, mhi in MB:
            rows = [t for t in trades if lo <= t["dte"] <= hi and mlo <= t["m"] < mhi]
            show(rows, ml)
        print()

    print("SPLIT BY WHAT THE NIGHT ACTUALLY DID (3-7 DTE, ATM ±1%)")
    base = [t for t in trades if 3 <= t["dte"] <= 7 and -0.01 <= t["m"] < 0.01]
    for lbl, f in (("gap down > 2%", lambda t: t["gap"] < -0.02),
                   ("gap down 0-2%", lambda t: -0.02 <= t["gap"] < 0),
                   ("gap up 0-2%", lambda t: 0 <= t["gap"] < 0.02),
                   ("gap up > 2%", lambda t: t["gap"] >= 0.02)):
        show([t for t in base if f(t)], lbl)

    print("\nBY YEAR (3-7 DTE, ATM ±1%)")
    for y in sorted(set(t["D"].year for t in base)):
        show([t for t in base if t["D"].year == y], str(y))

    print("\nSPREAD SENSITIVITY — prints are not quotes. You buy nearer the ask and")
    print("sell nearer the bid, so add the round-trip spread as a % of premium:")
    pop = [t for t in trades if 3 <= t["dte"] <= 7 and -0.07 <= t["m"] < 0.01]
    mc = mean([(t["entry"] - t["exit"]) / t["S"] * 10000 for t in pop])
    mp = median([t["entry"] / t["S"] * 10000 for t in pop])
    print(f"  population 3-7 DTE, 0 to -7% OTM: n={len(pop)}, median premium "
          f"{mp:.0f} bp of notional")
    print(f"  measured mean cost/night at zero spread: {mc:.1f} bp")
    for sp in (2, 5, 10, 20):
        print(f"    + {sp:>2}% round-trip spread -> {mc + mp * sp / 100:>6.1f} bp/night")


if __name__ == "__main__":
    main()
