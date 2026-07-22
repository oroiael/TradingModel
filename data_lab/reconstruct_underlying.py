#!/usr/bin/env python3
"""
reconstruct_underlying.py  --  rebuild the intraday underlying (09:30 open & 15:55
close) for 2022-2026 from the intraday OPTION files via PUT-CALL PARITY, so the
overnight test can run through the 2022 bear (no ETF 5-min data exists before
2023-07).

Method: at each (date, timestamp), for every strike with both a call and a put
print, the parity forward is  S ~= Call - Put + K  (r,q ~ 0 for short tenors; the
American early-exercise wedge is minimal near ATM). We take the 5 most-ATM strikes
(smallest |Call-Put|, across the nearest expirations) and use their median S.

Then VALIDATE against ground truth where we have it:
  - vs the real 5-min feed (2023-07+) at 15:55 and 09:30
  - vs the daily options underlying_price (2022-2026) at the close
If the reconstruction is accurate, 2022 becomes usable and we save open/close/day
to outputs/underlying_reconstructed.csv.
"""
from __future__ import annotations
import sys, glob
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import load_options, underlying_daily_from_options, load_5min  # noqa: E402

OUT = Path(__file__).resolve().parent / "outputs"; OUT.mkdir(exist_ok=True)
RAW = Path(__file__).resolve().parent.parent / "raw_data"
pd.set_option("display.width", 200)


def hr(t): print("\n" + "=" * 84 + f"\n{t}\n" + "=" * 84)


def parity_bar(df_ts, price_col):
    """df_ts: rows for one (date, timestamp) with columns right, strike, <price_col>.
    Returns reconstructed S via median of the 5 most-ATM (K + C - P)."""
    c = df_ts[df_ts["right"] == "CALL"].set_index("strike")[price_col]
    p = df_ts[df_ts["right"] == "PUT"].set_index("strike")[price_col]
    common = c.index.intersection(p.index)
    if len(common) < 3:
        return np.nan
    cp = (c[common] - p[common])                      # C - P per strike
    s_k = cp + common.to_series(index=common)         # S = C - P + K
    atm = cp.abs().nsmallest(5).index                 # most-ATM strikes
    return float(np.median(s_k[atm]))


def main():
    hr("RECONSTRUCT open/close underlying from intraday options (put-call parity)")
    files = [p for p in glob.glob(str(RAW / "SOXL_intraday_5m_exp_*.csv"))
             if Path(p).stat().st_size > 10_000]
    rows = []
    for i, fp in enumerate(files):
        df = pd.read_csv(fp, usecols=["expiration", "strike", "right", "timestamp",
                                      "open", "close", "volume"])
        df = df[df["volume"] > 0]
        if df.empty:
            continue
        ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
        df["date"] = ts.dt.date; df["hm"] = ts.dt.strftime("%H:%M")
        df["right"] = df["right"].str.upper()
        df["dte"] = (pd.to_datetime(df["expiration"]).dt.date - df["date"]).apply(lambda x: x.days)
        df = df[(df["dte"] >= 3) & (df["dte"] <= 60)]        # near expiries = tight parity
        for hm, pcol in [("09:30", "open"), ("15:55", "close")]:
            sub = df[(df["hm"] == hm) & (df[pcol] > 0)]
            for d, g in sub.groupby("date"):
                s = parity_bar(g, pcol)
                if np.isfinite(s):
                    rows.append((d, hm, s))
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(files)}")
    rec = pd.DataFrame(rows, columns=["date", "hm", "S"])
    # if multiple expirations gave an estimate for a (date,hm), median them
    rec = rec.groupby(["date", "hm"])["S"].median().unstack()
    rec.columns = ["open" if "09:30" in str(c) else "close" for c in rec.columns]
    rec = rec.rename(columns={"09:30": "open", "15:55": "close"})
    rec = rec[["open", "close"]].dropna(how="all")
    rec.index = pd.to_datetime(rec.index)
    print(f"reconstructed {len(rec)} days | {rec.index.min().date()} -> {rec.index.max().date()}")

    # ---------------------------------------------------------------- validate
    hr("VALIDATION vs ground truth")
    # (a) vs daily options underlying_price at close (2022-2026)
    u = underlying_daily_from_options(load_options()).set_index("trade_date")["close"]
    j = rec.join(u.rename("daily_close"), how="inner").dropna(subset=["close", "daily_close"])
    err = (j["close"] / j["daily_close"] - 1)
    print(f"(a) reconstructed CLOSE vs daily EOD underlying ({len(j)} days, 2022-2026):")
    print(f"     median abs error {err.abs().median():.2%}  corr {j['close'].corr(j['daily_close']):.4f}  "
          f"within 1%: {(err.abs()<0.01).mean():.0%}")
    # by year
    j["year"] = j.index.year
    print("     median abs error by year: " +
          "  ".join(f"{y}:{g['close'].div(g['daily_close']).sub(1).abs().median():.1%}" for y, g in j.groupby('year')))
    # (b) vs real 5-min feed at 09:30 and 15:55 (2023-07+)
    fm = load_5min(); fm["ts"] = pd.to_datetime(fm["ts"]); fm["date"] = fm["ts"].dt.date
    fm["hm"] = fm["ts"].dt.strftime("%H:%M")
    o5 = fm[fm["hm"] == "09:30"].groupby("date")["Open"].first()
    c5 = fm[fm["hm"] == "15:55"].groupby("date")["Close"].first()
    truth = pd.DataFrame({"open5": o5, "close5": c5}); truth.index = pd.to_datetime(truth.index)
    k = rec.join(truth, how="inner").dropna()
    print(f"\n(b) reconstructed vs real 5-min feed ({len(k)} overlap days, 2023-07+):")
    print(f"     OPEN : median abs err {(k['open']/k['open5']-1).abs().median():.2%}  corr {k['open'].corr(k['open5']):.4f}")
    print(f"     CLOSE: median abs err {(k['close']/k['close5']-1).abs().median():.2%}  corr {k['close'].corr(k['close5']):.4f}")

    # ---------------------------------------------------------------- save + 2022 overnight preview
    rec.to_csv(OUT / "underlying_reconstructed.csv")
    print(f"\nsaved {OUT/'underlying_reconstructed.csv'}")
    hr("2022 OVERNIGHT PREVIEW (using reconstructed open/close)")
    r22 = rec[(rec.index.year == 2022)].copy()
    r22["prev_close"] = r22["close"].shift(1)
    r22 = r22.dropna()
    on = (r22["open"] / r22["prev_close"] - 1)
    bh = (r22["close"] / r22["prev_close"] - 1)
    idr = (r22["close"] / r22["open"] - 1)
    print(f"  2022 ({len(r22)} days): overnight sum {(np.prod(1+on)-1):+.0%}  "
          f"intraday sum {(np.prod(1+idr)-1):+.0%}  buy&hold {(np.prod(1+bh)-1):+.0%}")
    print(f"  overnight Sharpe {on.mean()/on.std()*np.sqrt(252):+.2f}  vs buy&hold {bh.mean()/bh.std()*np.sqrt(252):+.2f}")
    print("  (2022 was the -87% bear -- this is the missing regime for the overnight test.)")


if __name__ == "__main__":
    main()
