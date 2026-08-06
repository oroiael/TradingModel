"""Is high volatility harvestable? Measure the premium, not the level.

Selling options pays only if IMPLIED exceeds SUBSEQUENTLY REALISED volatility.
That is a spread, and a spread is not implied by a high level. Measured
identically on SOXL and TQQQ from the yearly option CSVs.
"""
import os, sys
import numpy as np, pandas as pd

ROOT = "/home/user/TradingModel"
OUT = os.path.join(ROOT, "vol_anatomy/out")
COLS = ["expiration", "strike", "right", "bid", "ask", "implied_vol",
        "underlying_price", "trade_date"]
TENORS = [(7, 4, 12), (30, 20, 45), (90, 70, 120)]      # target, min, max DTE


def chain(files):
    parts = []
    for f in files:
        d = pd.read_csv(f, usecols=COLS)
        d["date"] = pd.to_datetime(d["trade_date"]).dt.normalize()
        d["exp"] = pd.to_datetime(d["expiration"]).dt.normalize()
        parts.append(d.drop(columns=["trade_date", "expiration"]))
    d = pd.concat(parts, ignore_index=True)
    d["dte"] = (d["exp"] - d["date"]).dt.days
    return d[d.implied_vol.notna() & (d.implied_vol > 0.01) & (d.implied_vol < 5)]


def vrp(d, label):
    spot = d.groupby("date")["underlying_price"].median().sort_index()
    ret = np.log(spot).diff()
    rows = []
    for tgt, lo, hi in TENORS:
        sub = d[d.dte.between(lo, hi)].copy()
        sub["mny"] = (sub.strike / sub.underlying_price - 1).abs()
        atm = sub[sub.mny < 0.03]
        iv = atm.groupby("date")["implied_vol"].median()
        n = max(int(round(tgt * 252 / 365)), 2)
        # realised vol over the NEXT n trading days
        fwd = ret.shift(-1).rolling(n).std().shift(-(n - 1)) * np.sqrt(252)
        j = pd.DataFrame({"iv": iv, "rv": fwd}).dropna()
        if not len(j):
            continue
        j["vrp"] = j.iv - j.rv
        rows.append(dict(instrument=label, tenor=f"{tgt}d", n=len(j),
                         mean_iv=j.iv.mean(), mean_rv=j.rv.mean(),
                         mean_vrp=j.vrp.mean(), med_vrp=j.vrp.median(),
                         pct_pos=(j.vrp > 0).mean(),
                         vrp_as_pct_of_iv=j.vrp.mean() / j.iv.mean()))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    yrs = [2024, 2025]
    s = chain([f"{ROOT}/SOXL_Options_{y}.csv" for y in yrs])
    t = chain([f"{ROOT}/raw_data/TQQQ_Options_{y}.csv" for y in yrs])
    print(f"SOXL rows {len(s):,}  dates {s.date.min().date()}..{s.date.max().date()}")
    print(f"TQQQ rows {len(t):,}  dates {t.date.min().date()}..{t.date.max().date()}\n")
    r = pd.concat([vrp(s, "SOXL"), vrp(t, "TQQQ")], ignore_index=True)
    r.to_csv(f"{OUT}/vrp_compare.csv", index=False)
    print("=" * 104)
    print("VARIANCE RISK PREMIUM  (ATM implied at t, minus volatility actually realised over the tenor)")
    print("Positive = option sellers were overpaid. This is the ONLY thing a short-vol harvest collects.")
    print("=" * 104)
    print(r.set_index(["instrument", "tenor"]).to_string(formatters={
        "mean_iv": "{:.1%}".format, "mean_rv": "{:.1%}".format,
        "mean_vrp": "{:+.1%}".format, "med_vrp": "{:+.1%}".format,
        "pct_pos": "{:.0%}".format, "vrp_as_pct_of_iv": "{:+.1%}".format}))
    print("\nBoth instruments, 2024-2025, identical method. Compare the SIZE of the premium")
    print("to the LEVEL of implied vol: the level differs a lot, the premium does not.")
