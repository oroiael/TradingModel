"""Where SOXL's volatility actually comes from, and what it takes to reproduce it.

Everything here is measured from the repo's 5-min files, not assumed:
  SOXL_5min_6Years.csv, SOXS_5min_6Years.csv, FAS_5min_6Years.csv (2020-07 -> 2026-07)
Fund facts are from SOXL-SOXS-Fact-Sheet.pdf / SAI_Combined3XShares.pdf.
"""
import os, sys
import numpy as np, pandas as pd

ROOT = "/home/user/TradingModel"
OUT = os.path.join(ROOT, "vol_anatomy/out")
A = 252


def load(name):
    df = pd.read_csv(os.path.join(ROOT, name))
    ts = df["Date"].str.replace(" America/New_York", "", regex=False)
    df["ts"] = pd.to_datetime(ts, format="%Y%m%d %H:%M:%S")
    df["date"] = df["ts"].dt.normalize()
    return df


def daily(name):
    d = load(name).groupby("date").agg(o=("Open", "first"), h=("High", "max"),
                                       l=("Low", "min"), c=("Close", "last"))
    d["intraday"] = d.c / d.o - 1                      # split-free by construction
    d["overnight"] = d.o / d.c.shift(1) - 1
    d["cc"] = d.c.pct_change()
    return d


def ann_vol(r):
    return float(np.std(r.dropna(), ddof=1) * np.sqrt(A))


def drag(r):
    """geometric minus arithmetic: the compounding cost of variance."""
    r = r.dropna()
    return float(np.mean(np.log1p(r)) * A - np.mean(r) * A)


if __name__ == "__main__":
    L, S, F = daily("SOXL_5min_6Years.csv"), daily("SOXS_5min_6Years.csv"), daily("FAS_5min_6Years.csv")
    W = pd.Timestamp("2022-01-01")

    print("=" * 104)
    print("1. THE LEVERAGE IS REAL AND IT IS DAILY  --  SOXL vs SOXS on the same index")
    print("=" * 104)
    j = pd.DataFrame({"L": L.intraday, "S": S.intraday}).dropna()
    j = j[(j.index >= W)]
    b, a = np.polyfit(j.L, j.S, 1)
    print(f"regress SOXS intraday return on SOXL intraday return, {len(j)} sessions 2022-2026")
    print(f"   slope {b:+.4f}  (theory -1.000: both are +/-3x the SAME index, so they are")
    print(f"   mechanically the same bet)   R^2 {np.corrcoef(j.L, j.S)[0,1]**2:.4f}")
    idx_from_L, idx_from_S = j.L / 3, -j.S / 3
    print(f"   index return implied by SOXL/3 vs by -SOXS/3: corr {np.corrcoef(idx_from_L, idx_from_S)[0,1]:.4f},"
          f" median abs diff {np.median(np.abs(idx_from_L-idx_from_S)):.5f}")
    print(f"\n   INTRADAY (open->close, split-free) basis:")
    print(f"      implied 1x NYSE Semiconductor index vol: {ann_vol(idx_from_L):.1%}")
    print(f"      SOXL realised vol:                       {ann_vol(j.L):.1%}  "
          f"(ratio {ann_vol(j.L)/ann_vol(idx_from_L):.2f}x)")
    lc = L[L.index >= W].cc
    print(f"   CLOSE-TO-CLOSE (the fund's actual daily return, incl. overnight gaps):")
    print(f"      implied 1x index vol: {ann_vol(lc)/3:.1%}      SOXL: {ann_vol(lc):.1%}"
          f"  (ratio 3.00x by construction)")
    print("   Both bases give exactly 3x. The gap between them IS the overnight gap risk.")

    print("\n" + "=" * 104)
    print("2. VOLATILITY BY YEAR, AND WHERE IN THE DAY IT HAPPENS")
    print("=" * 104)
    rows = []
    for y, g in L[L.index >= W].groupby(L[L.index >= W].index.year):
        rows.append(dict(year=y, cc_vol=ann_vol(g.cc), intraday_vol=ann_vol(g.intraday),
                         overnight_vol=ann_vol(g.overnight),
                         worst_day=g.cc.min(), best_day=g.cc.max(),
                         days_gt_5pct=int((g.cc.abs() > .05).sum()),
                         days_gt_10pct=int((g.cc.abs() > .10).sum()), n=len(g)))
    r = pd.DataFrame(rows).set_index("year")
    print(r.to_string(formatters={"cc_vol": "{:.1%}".format, "intraday_vol": "{:.1%}".format,
                                  "overnight_vol": "{:.1%}".format, "worst_day": "{:+.1%}".format,
                                  "best_day": "{:+.1%}".format}))
    o, i = L[L.index >= W].overnight, L[L.index >= W].intraday
    print(f"\n   overnight variance share: {ann_vol(o)**2/(ann_vol(o)**2+ann_vol(i)**2):.0%}"
          f"  -- gaps you cannot trade through carry a large part of the risk")

    print("\n" + "=" * 104)
    print("2b. DOES THE FUND'S OWN CLOSING REBALANCE AMPLIFY THE MOVE?  (commonly claimed)")
    print("=" * 104)
    uu = load("SOXL_5min_6Years.csv"); uu = uu[uu.date >= W]
    uu["minute"] = uu.ts.dt.hour * 60 + uu.ts.dt.minute
    dd = pd.DataFrame({"o": uu.groupby("date").Open.first(),
                       "pre": uu[uu.minute <= 925].groupby("date").Close.last(),
                       "c": uu.groupby("date").Close.last()}).dropna()
    dd["day_move"] = dd.pre / dd.o - 1
    dd["last30"] = dd.c / dd.pre - 1
    print(f"   A 3x fund MUST buy into strength / sell into weakness at the close to restore")
    print(f"   3x exposure, and the required trade is proportional to the day's move. But:")
    print(f"     corr(day move to 15:25, final 30 min) = {dd.day_move.corr(dd.last30):+.4f}  n={len(dd)}")
    q = pd.qcut(dd.day_move, 5, labels=["Q1 most down", "Q2", "Q3", "Q4", "Q5 most up"])
    print(dd.groupby(q, observed=True).agg(mean_day=("day_move", "mean"),
                                           mean_last30=("last30", "mean"), n=("last30", "size")
          ).to_string(formatters={"mean_day": "{:+.2%}".format, "mean_last30": "{:+.3%}".format}))
    print("   -> NOT amplification. If anything the last 30 min mean-reverts slightly.")
    print("      The rebalance flow is real but small against the underlying megacaps'")
    print("      liquidity, and is anticipated. Do not attribute SOXL's vol to it.")

    print("\n" + "=" * 104)
    print("3. VOLATILITY DRAG  --  why 3x daily is not 3x cumulative")
    print("=" * 104)
    idx = (1 + L.intraday / 3).cumprod()
    print("   For a daily-rebalanced k-times fund on an index with vol s:")
    print("     log-growth = k*mu - (k*s)^2/2   ->   drag vs k*(index) = (k^2-k)/2 * s^2")
    s1 = ann_vol(L[L.index >= W].intraday / 3)
    for k in (1, 2, 3, 5):
        print(f"     k={k}:  fund vol {k*s1:5.1%}   annual drag from variance "
              f"{(k*k-k)/2*s1**2:6.1%}")
    print(f"\n   measured on this data (2022-2026, intraday returns):")
    print(f"     SOXL geometric-minus-arithmetic drag {drag(L[L.index>=W].intraday):+.1%}/yr")
    print(f"     SOXS                                 {drag(S[S.index>=W].intraday):+.1%}/yr")
    print(f"\n   fact sheet, as of 2026-06-30: index ICESEMIT 1Y +170.76%, SOXL NAV +967.32%,")
    print(f"   SOXS NAV -97.86%; SOXS 10Y and since-inception both -100.00%.")
    print(f"   3 x 170.76 = 512%, yet SOXL made 967%: in a persistent TREND daily rebalancing")
    print(f"   compounds in your favour. The same mechanism is what destroyed SOXS.")

    print("\n" + "=" * 104)
    print("4. CAN THE VOLATILITY BE REPRODUCED WITHOUT SEMIS?")
    print("=" * 104)
    tgt = ann_vol(L[L.index >= W].cc)
    tbl = []
    for nm, d in [("SOXL 3x semis", L), ("SOXS -3x semis", S), ("FAS 3x financials", F)]:
        v = ann_vol(d[d.index >= W].cc)
        tbl.append(dict(instrument=nm, ann_vol=v, implied_1x=v / 3,
                        lev_to_match_SOXL=tgt / v))
    fin1x = ann_vol(F[F.index >= W].cc) / 3
    for nm, v in [("1x semis index (implied)", ann_vol(L[L.index >= W].cc) / 3),
                  ("1x financials (implied)", fin1x)]:
        tbl.append(dict(instrument=nm, ann_vol=v, implied_1x=v, lev_to_match_SOXL=tgt / v))
    t = pd.DataFrame(tbl).set_index("instrument")
    print(t.to_string(formatters={"ann_vol": "{:.1%}".format, "implied_1x": "{:.1%}".format,
                                  "lev_to_match_SOXL": "{:.2f}x".format}))
    print(f"\n   SOXL target vol = {tgt:.1%}. Volatility is LINEAR in leverage, so any asset")
    print(f"   reaches it at leverage = {tgt:.2f} / (its own vol). Nothing about semis is")
    print(f"   required -- semis only reduce the leverage needed.")

    # synthetic k-times daily-rebalanced FAS, vol-matched to SOXL
    k = tgt / ann_vol(F[F.index >= W].cc)
    fs = F[F.index >= W].cc.dropna()
    syn = (1 + k * fs).cumprod()
    print(f"\n   synthetic {k:.2f}x daily-rebalanced FAS (= {k*3:.1f}x financials):")
    print(f"     realised vol {ann_vol(k*fs):.1%} vs SOXL {tgt:.1%}")
    print(f"     variance drag {(k*k-k)/2*ann_vol(fs)**2 + drag(fs)*0:.1%}/yr extra vs 1x FAS")
    print(f"     correlation of daily returns with SOXL: "
          f"{np.corrcoef(*pd.DataFrame({'a':k*fs,'b':L[L.index>=W].cc}).dropna().T.values)[0,1]:.3f}")
    print("\n   -> same VOLATILITY, different RISK: vol matches, but the return stream is a")
    print("      different bet. Matching a number is not matching an exposure.")
    t.to_csv(f"{OUT}/instrument_vol.csv"); r.to_csv(f"{OUT}/soxl_vol_by_year.csv")
