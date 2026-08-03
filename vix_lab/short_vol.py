"""
The short-side-VIX question, answered with the cheapest sufficient data.

SOXL/SOXS work as a pair because *both* legs are dip-buyable: the strategy is
long-only, so a second leg has to be a security that rises, not a short. The
VIX analogue of that pair is UVXY (long vol) beside a short-vol ETF — SVXY
(-0.5x) or SVIX (-1x).

That question does not need 1-minute bars to answer, because the thing that
decides it is defined on *daily* bars: §2.2's gate is ATR5 >= 6.0, where ATR5
is the mean of (High-Low)/Open over the prior 5 sessions. If a candidate's
daily band is structurally too narrow to clear 6%, the sleeve never turns on
and no amount of intraday resolution changes that.

Daily bars come from IBKR (independent of the repository's CSVs).

Run:
    python3 vix_lab/short_vol.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
from dq_uvxy import load_raw  # noqa: E402

OUT = os.path.join(_HERE, "out")

TOOL = ("/root/.claude/projects/-home-user-TradingModel/"
        "36405402-2c9f-56a7-a70f-f169d7eb5d65/tool-results")
IBKR_FILES = {
    "SVXY": f"{TOOL}/mcp-Interactive_Brokers_IBKR-get_price_history-1785753583699.txt",
    "SVIX": f"{TOOL}/mcp-Interactive_Brokers_IBKR-get_price_history-1785753587632.txt",
    "VIXY": f"{TOOL}/mcp-Interactive_Brokers_IBKR-get_price_history-1785753003320.txt",
}


def hdr(s: str) -> None:
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


def ibkr_daily(path: str) -> pd.DataFrame:
    d = json.load(open(path))
    idx = pd.to_datetime(d["time"]).tz_convert("America/New_York").tz_localize(None).normalize()
    df = pd.DataFrame({"o": d["open"], "h": d["high"], "l": d["low"],
                       "c": d["close"], "v": d["volume"]}, index=idx).sort_index()
    return df[~df.index.duplicated()]


def csv_daily(symbol: str) -> pd.DataFrame:
    df = load_raw(os.path.join(ROOT, f"{symbol}_1min.csv"))
    return df.groupby("date").agg(o=("Open", "first"), h=("High", "max"),
                                  l=("Low", "min"), c=("Close", "last"),
                                  v=("Volume", "sum"))


def gate_profile(name: str, df: pd.DataFrame, since: pd.Timestamp) -> dict:
    df = df[df.index >= since]
    rng = (df["h"] - df["l"]) / df["o"] * 100
    atr5 = rng.rolling(5).mean().shift(1).dropna()
    return {
        "name": name, "n": len(df),
        "from": df.index.min().date(), "to": df.index.max().date(),
        "med_range": rng.median(), "p90_range": rng.quantile(0.90),
        "med_atr5": atr5.median(), "on6": (atr5 >= 6).mean(),
        "on4": (atr5 >= 4).mean(), "on3": (atr5 >= 3).mean(),
        "max_atr5": atr5.max(),
    }


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    since = pd.Timestamp("2022-01-01")

    series = {}
    for sym, path in IBKR_FILES.items():
        if os.path.exists(path):
            series[sym] = ibkr_daily(path)
    for sym in ("SOXL", "SOXS", "UVXY"):
        series[sym] = csv_daily(sym)

    hdr("1. Would the §2.2 gate (ATR5 >= 6.0) ever turn on for a short-vol ETF?")
    print("ATR5 and the daily band are scale-free, so daily bars settle this")
    print("completely — no 1-minute data required. Window 2022+.\n")
    print(f"{'symbol':<8}{'n':>6}{'med band%':>11}{'p90 band%':>11}"
          f"{'med ATR5':>10}{'ATR5>=6':>9}{'ATR5>=4':>9}{'ATR5>=3':>9}")
    rows = []
    order = ["SOXL", "SOXS", "UVXY", "VIXY", "SVXY", "SVIX"]
    for sym in order:
        if sym not in series:
            continue
        g = gate_profile(sym, series[sym], since)
        rows.append(g)
        print(f"{sym:<8}{g['n']:>6}{g['med_range']:>11.2f}{g['p90_range']:>11.2f}"
              f"{g['med_atr5']:>10.2f}{g['on6']:>9.1%}{g['on4']:>9.1%}"
              f"{g['on3']:>9.1%}")
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "gate_profile.csv"), index=False)

    print("\nkey: 'ATR5>=6' is the fraction of sessions the locked gate is ON.")
    print("The two traded sleeves sit near 75%. Anything in low single digits")
    print("is a security the strategy would essentially never trade.")

    hdr("2. Why — the leverage ladder on one index")
    print("All of UVXY, VIXY, SVXY and SVIX track the same S&P 500 VIX")
    print("Short-Term Futures index; they differ only in multiplier. Daily")
    print("band scales with |multiplier|, so the ladder is mechanical:\n")
    print(f"{'symbol':<8}{'multiplier':>12}{'med band%':>11}{'band/|mult|':>13}")
    mult = {"UVXY": 1.5, "VIXY": 1.0, "SVXY": -0.5, "SVIX": -1.0}
    for sym in ("UVXY", "VIXY", "SVXY", "SVIX"):
        g = next((r for r in rows if r["name"] == sym), None)
        if g is None:
            continue
        print(f"{sym:<8}{mult[sym]:>12.1f}{g['med_range']:>11.2f}"
              f"{g['med_range'] / abs(mult[sym]):>13.2f}")
    print("\nThe last column is the same number four times, which is the point:")
    print("there is no short-vol product with UVXY's band. SVXY is a -0.5x")
    print("product and carries roughly a third of UVXY's daily range.")

    hdr("3. What a 1%/1%/4% trade grid needs")
    print("Entry triggers on a 1% dip off the session high; the target is +1%.")
    print("Both have to fit inside the day's band several times over for the")
    print("5-fill cap to be reachable. Sessions whose whole band is under 2%")
    print("cannot round-trip a single trade:\n")
    print(f"{'symbol':<8}{'band<2%':>10}{'band<3%':>10}{'band>=6%':>10}")
    for sym in order:
        if sym not in series:
            continue
        d = series[sym][series[sym].index >= since]
        r = (d["h"] - d["l"]) / d["o"] * 100
        print(f"{sym:<8}{(r < 2).mean():>10.1%}{(r < 3).mean():>10.1%}"
              f"{(r >= 6).mean():>10.1%}")

    hdr("4. Anti-correlation is NOT the disqualifier — the band width is")
    print("The tempting argument against a short-vol leg is that it is just")
    print("the mirror of the long-vol leg. That argument is wrong, and the")
    print("existing pair is the proof: SOXL and SOXS are near-perfectly")
    print("anti-correlated too, and the strategy is profitable on both. It")
    print("harvests churn, and churn is direction-free.\n")
    u = csv_daily("UVXY")["c"].pct_change()
    lg = csv_daily("SOXL")["c"].pct_change()
    sg = csv_daily("SOXS")["c"].pct_change()
    j = pd.concat([lg.rename("a"), sg.rename("b")], axis=1).dropna()
    j = j[j.index >= since]
    print(f"  SOXL vs SOXS (the APPROVED pair):  corr {j.a.corr(j.b):+.4f}"
          f"   <- already ~ -1")
    for sym in ("SVXY", "SVIX", "VIXY"):
        if sym not in series:
            continue
        s = series[sym]["c"].pct_change()
        k = pd.concat([u.rename("u"), s.rename("s")], axis=1).dropna()
        k = k[k.index >= since]
        beta = float((k.u * k.s).sum() / (k.s ** 2).sum())
        print(f"  UVXY vs {sym}: n={len(k)}  corr {k.u.corr(k.s):+.4f}  "
              f"beta {beta:+.3f}  (multiplier ratio {1.5 / mult[sym]:+.2f})")
    print("\nSo the short-vol leg is not rejected for being a mirror. It is")
    print("rejected because a -0.5x product cannot produce a 1% dip and a")
    print("subsequent 1% recovery often enough: SVXY clears the gate on 1.9%")
    print("of sessions and spends over half of them inside a 2% band.")
    print("SVIX (-1x) is the only short-vol candidate with a real band, and it")
    print("still clears the gate less than a quarter as often as SOXL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
