"""
Is the STRUCTURE of UVXY's volatility forecastable? — the question the
directional tests never asked.

Everything in `drivers.py` and `two_sigma.py` tested one thing: does the price
go up. That is the delta-one question. It is not the question an option
answers. An option pays on *magnitude*, *convexity*, *carry* and *skew*, and
none of those were measured.

This module measures the one input every option strategy depends on:
**how predictable is realised variance?** If it is not forecastable, no vol
strategy has an edge beyond harvesting the risk premium. If it is, the size
and horizon of that predictability bound what any structure can earn.

Realised variance is computed from the 1-minute file — sum of squared
intraday log returns — which is a far better estimator than close-to-close
and is the reason having the 1-minute data matters here.

Benchmark model is HAR-RV (Corsi 2009): tomorrow's log RV on today's, the
trailing week's and the trailing month's. Out-of-sample R^2 comes from an
expanding window, refit annually, never using future data.

Run:
    python3 vix_lab/vol_forecast.py
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

OUT = os.path.join(_HERE, "out")

#: Live IBKR snapshot, UVXY, 2026-08-04. Recorded because the comparison of
#: implied against realised is the whole variance-risk-premium question and
#: this is the only implied number available in this environment.
LIVE = {"spot": 23.11, "bid": 23.11, "ask": 23.21,
        "hist_vol_annual": 0.8480, "implied_vol_annual": 0.8449,
        "iv_pctile_52w": 0.236}


def hdr(s: str) -> None:
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


def realised_variance(sym: str = "UVXY") -> pd.DataFrame:
    """Daily realised variance from 1-minute returns, plus the overnight gap."""
    df = load_raw(os.path.join(ROOT, f"{sym}_1min.csv"))
    df["lr"] = np.log(df["Close"]).diff()
    # first bar of each session is an overnight jump, not an intraday return
    first = df.groupby("date")["dt"].transform("min") == df["dt"]
    overnight = df.loc[first, "lr"]
    intr = df.loc[~first]
    rv = intr.groupby("date")["lr"].apply(lambda s: (s ** 2).sum())
    on = overnight.groupby(df.loc[first, "date"]).first()
    cc = df.groupby("date")["Close"].last()
    out = pd.DataFrame({"rv": rv, "overnight": on, "close": cc}).dropna(subset=["rv"])
    out["rv_ann"] = np.sqrt(out["rv"] * 252)
    out["rv_tot"] = out["rv"] + out["overnight"].fillna(0.0) ** 2
    out["rv_tot_ann"] = np.sqrt(out["rv_tot"] * 252)
    return out


def har_design(lrv: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({
        "d": lrv,
        "w": lrv.rolling(5).mean(),
        "m": lrv.rolling(22).mean(),
    })


def ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(np.column_stack([np.ones(len(X)), X]), y, rcond=None)[0]


def r2(y: np.ndarray, yhat: np.ndarray) -> float:
    ss = ((y - yhat) ** 2).sum()
    return 1 - ss / ((y - y.mean()) ** 2).sum()


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    d = realised_variance("UVXY")
    print(f"UVXY realised variance from 1-minute bars: {len(d)} sessions, "
          f"{d.index.min().date()} -> {d.index.max().date()}")

    # ------------------------------------------------------------- levels
    hdr("1. What realised volatility actually looks like")
    a = d["rv_ann"]
    at = d["rv_tot_ann"]
    print(f"{'':<28}{'intraday only':>16}{'incl. overnight':>18}")
    for nm, q in (("median", .5), ("25th pct", .25), ("75th pct", .75),
                  ("90th pct", .90), ("99th pct", .99)):
        print(f"{nm:<28}{a.quantile(q):>16.2f}{at.quantile(q):>18.2f}")
    print(f"{'mean':<28}{a.mean():>16.2f}{at.mean():>18.2f}")
    print(f"{'min / max':<28}{f'{a.min():.2f} / {a.max():.2f}':>16}"
          f"{f'{at.min():.2f} / {at.max():.2f}':>18}")
    print("\nAnnualised. The overnight column matters: UVXY gaps, and an")
    print("option holder owns those gaps while an intraday sleeve does not.")

    # ---------------------------------------------------------- forecast
    hdr("2. Is it forecastable? HAR-RV, in and out of sample")
    print("log RV_{t+h} regressed on log RV today, the trailing 5 days and")
    print("the trailing 22. Out-of-sample refits each January on prior data")
    print("only, then predicts that year — the same protocol band_lab uses.\n")
    lrv = np.log(d["rv_tot"].replace(0, np.nan)).dropna()
    X = har_design(lrv).dropna()
    print(f"{'horizon':<12}{'n':>7}{'in-sample R2':>15}{'OOS R2':>10}"
          f"{'OOS R2 vs':>12}{'corr(pred,act)':>16}")
    print(f"{'':<12}{'':>7}{'':>15}{'':>10}{'random walk':>12}{'':>16}")
    rows = []
    for h in (1, 5, 22):
        tgt = np.log(
            d["rv_tot"].rolling(h).mean().shift(-h).replace(0, np.nan)).dropna()
        j = X.join(tgt.rename("y"), how="inner").dropna()
        Xa, ya = j[["d", "w", "m"]].to_numpy(), j["y"].to_numpy()
        b = ols(Xa, ya)
        ins = r2(ya, np.column_stack([np.ones(len(Xa)), Xa]) @ b)

        # expanding-window OOS, refit each January
        pred = np.full(len(j), np.nan)
        yrs = sorted({t.year for t in j.index})
        for y_ in yrs[1:]:
            tr = j.index.year < y_
            te = j.index.year == y_
            if tr.sum() < 250 or te.sum() == 0:
                continue
            bb = ols(j.loc[tr, ["d", "w", "m"]].to_numpy(), j.loc[tr, "y"].to_numpy())
            Xt = j.loc[te, ["d", "w", "m"]].to_numpy()
            pred[te] = np.column_stack([np.ones(len(Xt)), Xt]) @ bb
        m = ~np.isnan(pred)
        oos = r2(ya[m], pred[m])
        # random walk benchmark: predict tomorrow's log RV as today's
        rw = r2(ya[m], j["d"].to_numpy()[m])
        c = np.corrcoef(pred[m], ya[m])[0, 1]
        print(f"{f'h = {h}d':<12}{int(m.sum()):>7}{ins:>15.3f}{oos:>10.3f}"
              f"{rw:>12.3f}{c:>16.3f}")
        rows.append({"h": h, "in_sample_r2": ins, "oos_r2": oos,
                     "rw_r2": rw, "corr": c, "n": int(m.sum())})
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "har_rv.csv"), index=False)

    print("\nCompare this with DRIVERS.md §1.1, which reported corr 0.152")
    print("between trailing and forward 20-day close-to-close vol and was read")
    print("as 'vol is barely forecastable'. That reading was too harsh: it")
    print("used a noisy estimator at the single hardest horizon. Measured")
    print("properly, volatility is the most forecastable thing about UVXY —")
    print("far more so than its direction, which was not forecastable at all.")

    # ----------------------------------------------------- what it implies
    hdr("3. The variance risk premium — the one number that decides it")
    print("A short-vol structure earns implied minus subsequent realised.")
    print("A long-vol structure earns the reverse. So the question is not")
    print("'is vol forecastable' but 'is it forecastable better than the")
    print("option market already forecasts it'.\n")
    iv = LIVE["implied_vol_annual"]
    print(f"IBKR snapshot, UVXY, 2026-08-04 (spot {LIVE['spot']:.2f}):")
    print(f"  implied vol (annual)          {iv:>8.1%}")
    print(f"  30-day historical vol         {LIVE['hist_vol_annual']:>8.1%}")
    print(f"  implied minus historical      "
          f"{iv - LIVE['hist_vol_annual']:>+8.1%}   <- the premium, right now")
    print(f"  IV 52-week percentile         {LIVE['iv_pctile_52w']:>8.1%}")
    print(f"\nWhere that IV sits against the realised distribution measured above:")
    print(f"  percentile of {iv:.1%} in realised (incl. overnight): "
          f"{(at < iv).mean():.1%}")
    print(f"  median realised                {at.median():>8.1%}")
    print(f"  mean realised                  {at.mean():>8.1%}")
    print("\n**This is ONE snapshot, not a study.** It is enough to show the")
    print("premium is not obviously large on this name today, and not enough")
    print("to conclude anything about its average. That needs an IV history,")
    print("which this repository does not have for UVXY.")

    # ------------------------------------------------- breakeven straddle
    hdr("4. Model-free: what a short straddle had to collect")
    print("Independent of any option data. For each session, the |move| over")
    print("the next N days is what a straddle sold at the money pays out. The")
    print("premium a seller needed to break even is that expectation.\n")
    c = d["close"]
    print(f"{'holding period':<18}{'mean |move|':>13}{'median':>10}{'p90':>9}"
          f"{'p99':>9}{'max':>9}")
    for n in (1, 5, 10, 22):
        mv = (c.shift(-n) / c - 1).abs().dropna()
        print(f"{f'{n} sessions':<18}{mv.mean():>13.1%}{mv.median():>10.1%}"
              f"{mv.quantile(.9):>9.1%}{mv.quantile(.99):>9.1%}{mv.max():>9.1%}")
    print("\nRead the 22-session row as the monthly ATM straddle: a seller")
    print("needed to collect more than the mean |move| to break even before")
    print("costs, and faced the max column as the tail. The gap between the")
    print("median and the mean is the skew that kills naive premium selling.")

    print("\nDirectional split of that move — puts and calls are not symmetric:")
    print(f"{'holding period':<18}{'mean up move':>14}{'mean down move':>16}"
          f"{'P(up)':>8}{'up tail p99':>13}{'down tail p99':>15}")
    for n in (5, 22):
        r = (c.shift(-n) / c - 1).dropna()
        up, dn = r[r > 0], r[r < 0]
        print(f"{f'{n} sessions':<18}{up.mean():>14.1%}{dn.mean():>16.1%}"
              f"{(r > 0).mean():>8.1%}{up.quantile(.99):>13.1%}"
              f"{dn.quantile(.01):>15.1%}")
    print("\nUVXY goes up less than half the time and further when it does.")
    print("That is the entire options problem in one line: the side that")
    print("wins most often is the side that loses most per event.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
