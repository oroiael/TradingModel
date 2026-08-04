"""
What actually precedes a UVXY move?

Four questions, measured rather than asserted:

  1. Does UVXY mean-revert against an SMA?
  2. Does the VIX futures term structure predict it?
  3. Does it track FX?
  4. How much of it is just the equity market?

**The confound that ruins naive versions of all four.** UVXY loses ~67%/yr.
Any long-only statistic looks terrible and any short-only statistic looks
brilliant, regardless of whether the signal has information. So every result
below is reported as a *spread* between buckets of the same signal, or against
the unconditional mean of the same sample. A bucket earning -30 bp/day when
the unconditional mean is -42 is a *positive* result, and is labelled that way.

Run:
    python3 vix_lab/drivers.py
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


def hdr(s: str) -> None:
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


def uvxy_daily() -> pd.DataFrame:
    df = load_raw(os.path.join(ROOT, "UVXY_1min.csv"))
    d = df.groupby("date").agg(o=("Open", "first"), h=("High", "max"),
                               l=("Low", "min"), c=("Close", "last"),
                               v=("Volume", "sum"))
    d["ret"] = d["c"].pct_change()
    d["intraday"] = d["c"] / d["o"] - 1
    d["overnight"] = d["o"] / d["c"].shift(1) - 1
    return d


def bucket_table(sig: pd.Series, fwd: pd.Series, n: int, label: str,
                 unit: str = "bp") -> None:
    """Forward return by signal quantile, with the sample mean as the ruler."""
    j = pd.DataFrame({"sig": sig, "fwd": fwd}).dropna()
    if len(j) < n * 10:
        print(f"  {label}: too few observations ({len(j)})")
        return
    q = pd.qcut(j["sig"], n, labels=False, duplicates="drop")
    mu = j["fwd"].mean()
    print(f"\n{label}   (n={len(j)}, unconditional mean {mu * 1e4:+.0f} {unit})")
    print(f"{'  bucket':<10}{'signal range':>20}{'n':>6}{'fwd ret':>10}"
          f"{'vs mean':>10}{'t':>7}")
    for k in sorted(set(q.dropna())):
        g = j[q == k]
        ex = g["fwd"].mean() - mu
        t = ex / (g["fwd"].std() / np.sqrt(len(g))) if g["fwd"].std() else np.nan
        print(f"{'  Q' + str(int(k) + 1):<10}"
              f"{f'{g.sig.min():+.2f} .. {g.sig.max():+.2f}':>20}{len(g):>6}"
              f"{g.fwd.mean() * 1e4:>10.0f}{ex * 1e4:>+10.0f}{t:>7.2f}")
    lo, hi = j[q == q.min()]["fwd"], j[q == q.max()]["fwd"]
    sp = hi.mean() - lo.mean()
    tsp = sp / np.sqrt(hi.var() / len(hi) + lo.var() / len(lo))
    print(f"{'  TOP-BOT':<10}{'':>20}{'':>6}{sp * 1e4:>10.0f}{'':>10}{tsp:>7.2f}")


# ------------------------------------------------------------ 1. mean reversion
def mean_reversion(d: pd.DataFrame) -> None:
    hdr("1. Does UVXY mean-revert against an SMA?")
    print("Signal: z = (close - SMA_N) / rolling sd_N, computed on data")
    print("strictly before the forward window. If UVXY mean-reverts, high z")
    print("should be followed by weak returns and low z by strong ones, and")
    print("the TOP-BOT spread should be reliably negative.\n")

    for N in (10, 20, 50, 200):
        sma = d["c"].rolling(N).mean()
        sd = d["c"].rolling(N).std()
        z = ((d["c"] - sma) / sd).shift(1)          # known at today's open
        for h in (1, 5, 20):
            fwd = d["c"].shift(-h) / d["c"] - 1
            bucket_table(z, fwd, 5, f"SMA{N}, {h}-day forward")
        print()

    hdr("1b. The same question with the drift removed entirely")
    print("Comparing UVXY to its own 1x sibling isolates *leverage decay* from")
    print("*direction*. If the SMA signal is real it should also predict VIXY,")
    print("which has no 1.5x drag. 5-day forward, SMA20 z-score.\n")
    vy = load_ref("VIXY")["Close"]
    vr = vy.pct_change()
    z20 = ((vy - vy.rolling(20).mean()) / vy.rolling(20).std()).shift(1)
    fwd5 = vy.shift(-5) / vy - 1
    bucket_table(z20, fwd5, 5, "VIXY SMA20 z -> 5-day forward VIXY")

    hdr("1c. Reversion at the daily scale — autocorrelation")
    print("A cleaner form of the same question: does yesterday's return")
    print("predict today's, and does a big move reverse?\n")
    r = d["ret"].dropna()
    print(f"{'lag':<6}{'autocorr of daily return':>28}")
    for lag in (1, 2, 3, 5, 10):
        print(f"{lag:<6}{r.autocorr(lag):>28.4f}")
    print("\nBy size of yesterday's move:")
    prev = r.shift(1)
    bucket_table(prev, r, 5, "yesterday's return -> today's return")


# --------------------------------------------------------- 2. term structure
def term_structure(d: pd.DataFrame) -> None:
    hdr("2. The VIX futures term structure")
    print("VIXY holds ~1-month VIX futures; VIXM holds ~5-month. Their ratio")
    print("moves with the slope of the curve: contango (the normal state)")
    print("bleeds the front, backwardation lifts it. The ratio's own level is")
    print("meaningless -- both are decaying ETFs -- so use its 60-day z-score.\n")
    vy, vm = load_ref("VIXY")["Close"], load_ref("VIXM")["Close"]
    ratio = (vy / vm).dropna()
    z = ((ratio - ratio.rolling(60).mean()) / ratio.rolling(60).std()).shift(1)

    for h in (1, 5, 20):
        fwd = d["c"].shift(-h) / d["c"] - 1
        bucket_table(z, fwd, 5, f"term-structure z -> {h}-day forward UVXY")

    print("\nAlso the contemporaneous relation — how much of a day's UVXY move")
    print("is the curve moving on the same day (not a forecast, a decomposition):")
    dz = ratio.pct_change()
    j = pd.DataFrame({"dz": dz, "u": d["ret"]}).dropna()
    print(f"  corr(d UVXY, d(VIXY/VIXM)) = {j.dz.corr(j.u):+.4f}   n={len(j)}")


# --------------------------------------------------------------------- 3. FX
def fx(d: pd.DataFrame) -> None:
    hdr("3. Does UVXY track FX?")
    print("UUP is a dollar-index ETF, FXY a yen ETF. Contemporaneous first,")
    print("then lead/lag, then controlled for the equity market -- because a")
    print("raw FX/vol correlation is mostly both reacting to SPY.\n")
    spy = load_ref("SPY")["Close"].pct_change()
    uup = load_ref("UUP")["Close"].pct_change()
    fxy = load_ref("FXY")["Close"].pct_change()
    j = pd.DataFrame({"u": d["ret"], "spy": spy, "uup": uup, "fxy": fxy}).dropna()
    print(f"sample: {len(j)} sessions, {j.index.min().date()} -> {j.index.max().date()}\n")

    print(f"{'pair':<26}{'raw corr':>11}{'partial (SPY out)':>20}")
    for nm, col in (("UVXY vs SPY", "spy"), ("UVXY vs UUP (dollar)", "uup"),
                    ("UVXY vs FXY (yen)", "fxy")):
        raw = j["u"].corr(j[col])
        if col == "spy":
            print(f"{nm:<26}{raw:>11.4f}{'--':>20}")
            continue
        # partial correlation of u and col, controlling for spy
        ru = j["u"] - j["spy"] * (j["u"].cov(j["spy"]) / j["spy"].var())
        rc = j[col] - j["spy"] * (j[col].cov(j["spy"]) / j["spy"].var())
        print(f"{nm:<26}{raw:>11.4f}{ru.corr(rc):>20.4f}")

    print("\nLead/lag: does FX move BEFORE UVXY? corr(UVXY_t, FX_{t-k}).")
    print("A real leading indicator shows a non-zero value at k=+1.")
    print(f"{'lag k':<8}{'UUP':>10}{'FXY':>10}{'SPY':>10}")
    for k in (-2, -1, 0, 1, 2):
        row = f"{k:<8}"
        for col in ("uup", "fxy", "spy"):
            row += f"{j['u'].corr(j[col].shift(k)):>10.4f}"
        print(row)
    print("k=0 contemporaneous; k=+1 means FX yesterday vs UVXY today.")

    print("\nForward test — does a big FX day predict tomorrow's UVXY?")
    for col, nm in (("uup", "dollar"), ("fxy", "yen")):
        bucket_table(j[col], j["u"].shift(-1), 5, f"today's {nm} move -> tomorrow's UVXY")


# ---------------------------------------------------------------- 4. the market
def equity(d: pd.DataFrame) -> None:
    hdr("4. How much of UVXY is simply the equity market?")
    spy = load_ref("SPY")["Close"].pct_change()
    j = pd.DataFrame({"u": d["ret"], "spy": spy}).dropna()
    beta = float((j.u * j.spy).sum() / (j.spy ** 2).sum())
    r2 = j.u.corr(j.spy) ** 2
    print(f"  beta of UVXY to SPY   {beta:+.2f}")
    print(f"  R^2                   {r2:.3f}   (n={len(j)})")
    print(f"  -> {r2:.0%} of UVXY's daily variance is same-day SPY.")

    print("\nAsymmetry — the reason a vol product is not just a short index:")
    up, dn = j[j.spy > 0], j[j.spy < 0]
    bu = float((up.u * up.spy).sum() / (up.spy ** 2).sum())
    bd = float((dn.u * dn.spy).sum() / (dn.spy ** 2).sum())
    print(f"  beta on SPY-up days    {bu:+.2f}  (n={len(up)})")
    print(f"  beta on SPY-down days  {bd:+.2f}  (n={len(dn)})")
    print(f"  ratio                  {bd / bu:.2f}x")

    print("\nThe 12 largest UVXY up-days in the sample, with SPY alongside:")
    print(f"{'date':<12}{'UVXY %':>9}{'SPY %':>8}{'ratio':>8}")
    for dt in j.u.nlargest(12).index:
        rr = j.loc[dt, "u"] / j.loc[dt, "spy"] if j.loc[dt, "spy"] else np.nan
        print(f"{str(dt.date()):<12}{j.loc[dt, 'u'] * 100:>9.1f}"
              f"{j.loc[dt, 'spy'] * 100:>8.2f}{rr:>8.1f}")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    d = uvxy_daily()
    print(f"UVXY daily: {len(d)} sessions, {d.index.min().date()} -> "
          f"{d.index.max().date()}")
    print(f"unconditional mean daily return: {d['ret'].mean() * 1e4:+.0f} bp")
    mean_reversion(d)
    term_structure(d)
    fx(d)
    equity(d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
