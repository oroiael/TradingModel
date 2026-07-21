#!/usr/bin/env python3
"""
options_surface.py  --  NEUTRAL fingerprint of the SOXL options (daily, 2022-2026).

What is priced, and is it priced right? No trade assumed.
  1. VOLATILITY RISK PREMIUM: ATM implied vol vs the realized vol that FOLLOWS it,
     by DTE and by year -- are options systematically rich or cheap?
  2. TERM STRUCTURE: ATM IV by DTE -- contango (up) or backwardation (inverted)?
  3. SKEW: IV of ~25-delta puts vs calls vs ATM -- how is crash risk priced?
  4. VOL-OF-VOL & the IV/spot relationship (does IV spike when SOXL drops?)
Outputs a printed report + outputs/options_surface.png.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import load_options, underlying_daily_from_options  # noqa: E402

OUT = Path(__file__).resolve().parent / "outputs"; OUT.mkdir(exist_ok=True)
pd.set_option("display.width", 200)
ANN = 252


def hr(t): print("\n" + "=" * 84 + f"\n{t}\n" + "=" * 84)


def atm_iv_by_day_dte(opt):
    """ATM (nearest-strike-to-spot) call IV per (trade_date, dte-bucket)."""
    c = opt[(opt["right"] == "CALL") & (opt["implied_vol"] > 0)].copy()
    c["m"] = (c["strike"] / c["underlying_price"] - 1).abs()
    atm = c.sort_values("m").groupby(["trade_date", "expiration"]).first().reset_index()
    return atm


def main():
    hr("LOAD options + daily underlying 2022-2026")
    opt = load_options()
    u = underlying_daily_from_options(opt).sort_values("trade_date").reset_index(drop=True)
    u["ret"] = np.log(u["close"]).diff()
    u["year"] = u["trade_date"].dt.year
    atm = atm_iv_by_day_dte(opt)
    atm["trade_date"] = pd.to_datetime(atm["trade_date"])
    print(f"{len(opt):,} option rows | {atm['trade_date'].nunique()} days with ATM IV")

    # ---------------------------------------------------------------- 1 VRP
    hr("1.  VOLATILITY RISK PREMIUM: implied vs the realized vol that FOLLOWS")
    # realized vol over the next H trading days (annualized), aligned by date
    ret = u.set_index("trade_date")["ret"]
    for H, lo, hi in [(30, 20, 45), (14, 9, 20), (60, 45, 90)]:
        fwd_rv = ret[::-1].rolling(H).std()[::-1].shift(-1) * np.sqrt(ANN)   # next-H realized
        sub = atm[(atm["dte"] >= lo) & (atm["dte"] <= hi)]
        day_iv = sub.groupby("trade_date")["implied_vol"].median()
        df = pd.DataFrame({"iv": day_iv}).join(fwd_rv.rename("rv")).dropna()
        vrp = df["iv"] - df["rv"]
        print(f"  ~{H}d tenor: median IV {df['iv'].median():.0%}  median next-{H}d realized "
              f"{df['rv'].median():.0%}  ->  VRP median {vrp.median():+.0%}  mean {vrp.mean():+.0%}  "
              f"(IV>RV on {np.mean(vrp>0):.0%} of days)")
    # VRP by year (30d)
    fwd30 = ret[::-1].rolling(30).std()[::-1].shift(-1) * np.sqrt(ANN)
    iv30 = atm[(atm["dte"].between(20, 45))].groupby("trade_date")["implied_vol"].median()
    d = pd.DataFrame({"iv": iv30}).join(fwd30.rename("rv")).dropna()
    d["year"] = d.index.year
    print("\n  30d VRP (IV - next-30d realized) by year  (negative = options were CHEAP):")
    print("    " + "  ".join(f"{y}:{(g['iv']-g['rv']).mean():+.0%}"
                             for y, g in d.groupby("year")))

    # ---------------------------------------------------------------- 2 term structure
    hr("2.  TERM STRUCTURE: ATM IV by DTE (contango vs backwardation)")
    buckets = [(5, 10, "~7d"), (11, 18, "~14d"), (25, 38, "~30d"), (50, 75, "~60d"),
               (80, 110, "~90d"), (110, 200, "120d+")]
    print("  median ATM IV by tenor:")
    prev = None
    for lo, hi, lbl in buckets:
        iv = atm[(atm["dte"] >= lo) & (atm["dte"] <= hi)]["implied_vol"].median()
        arrow = "" if prev is None else ("  UP" if iv > prev else "  down")
        print(f"    {lbl:6s}: {iv:.0%}{arrow}")
        prev = iv
    # how often inverted (short IV > long IV) = stress
    piv = atm.assign(b=pd.cut(atm["dte"], [4, 18, 200], labels=["short", "long"]))
    wide = piv.groupby(["trade_date", "b"], observed=True)["implied_vol"].median().unstack()
    inv = (wide["short"] > wide["long"]).mean()
    print(f"  short-tenor IV > long-tenor IV (inverted / stressed) on {inv:.0%} of days "
          f"(normal market = mostly contango)")

    # ---------------------------------------------------------------- 3 skew
    hr("3.  SKEW: how crash risk is priced (25d put vs ATM vs 25d call)")
    m = opt[(opt["implied_vol"] > 0) & (opt["dte"].between(20, 45)) & (opt["delta"].notna())].copy()
    m["adelta"] = m["delta"].abs()
    def near_delta(g, right, target):
        s = g[g["right"] == right]
        if len(s) == 0:
            return np.nan
        return s.iloc[(s["adelta"] - target).abs().argmin()]["implied_vol"]
    rows = []
    for td, g in m.groupby("trade_date"):
        p25 = near_delta(g, "PUT", 0.25); c50 = near_delta(g, "CALL", 0.50)
        c25 = near_delta(g, "CALL", 0.25)
        if np.isfinite(p25) and np.isfinite(c50) and np.isfinite(c25):
            rows.append((p25, c50, c25))
    sk = pd.DataFrame(rows, columns=["p25", "atm", "c25"])
    print(f"  median IV: 25d-put {sk['p25'].median():.0%}  ATM {sk['atm'].median():.0%}  "
          f"25d-call {sk['c25'].median():.0%}")
    print(f"  PUT skew  (25d put - ATM):  {(sk['p25']-sk['atm']).median():+.0%}  "
          f"(positive = downside puts richer -> crash fear priced)")
    print(f"  CALL skew (25d call - ATM): {(sk['c25']-sk['atm']).median():+.0%}  "
          f"(positive = upside calls richer -> 'melt-up'/right-tail demand)")
    print(f"  -> {'CALL-skewed (right tail bid)' if (sk['c25']-sk['atm']).median() > (sk['p25']-sk['atm']).median() else 'PUT-skewed (left tail bid)'}")

    # ---------------------------------------------------------------- 4 vol of vol
    hr("4.  VOL-OF-VOL & IV/spot relationship")
    ivd = atm[atm["dte"].between(20, 45)].groupby("trade_date")["implied_vol"].median()
    ivchg = ivd.diff()
    print(f"  ATM IV: mean {ivd.mean():.0%}  std {ivd.std():.0%}  range {ivd.min():.0%}-{ivd.max():.0%}")
    print(f"  daily IV change std (vol-of-vol): {ivchg.std():.1%}")
    j = pd.DataFrame({"ivchg": ivchg}).join(u.set_index("trade_date")["ret"]).dropna()
    print(f"  corr(IV change, same-day return): {j['ivchg'].corr(j['ret']):+.2f}  "
          f"(negative = IV jumps when SOXL FALLS = classic fear bid)")

    _plot(atm, sk, ivd, d)
    print(f"\nsaved {OUT/'options_surface.png'}")


def _plot(atm, sk, ivd, vrp_df):
    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    buckets = [(5, 10, 7), (11, 18, 14), (25, 38, 30), (50, 75, 60), (80, 110, 90), (110, 200, 150)]
    xs = [b[2] for b in buckets]
    ys = [atm[(atm["dte"] >= lo) & (atm["dte"] <= hi)]["implied_vol"].median() * 100 for lo, hi, _ in buckets]
    ax[0, 0].plot(xs, ys, "o-"); ax[0, 0].set_xlabel("DTE"); ax[0, 0].set_ylabel("ATM IV %")
    ax[0, 0].set_title("term structure (ATM IV by DTE)")
    ax[0, 1].hist((sk["p25"] - sk["atm"]) * 100, bins=40, alpha=0.5, label="put skew")
    ax[0, 1].hist((sk["c25"] - sk["atm"]) * 100, bins=40, alpha=0.5, label="call skew")
    ax[0, 1].axvline(0, c="k", lw=.6); ax[0, 1].legend(); ax[0, 1].set_title("skew: 25d wing IV minus ATM (pts)")
    ax[1, 0].plot(pd.to_datetime(ivd.index), ivd.values * 100)
    ax[1, 0].set_title("ATM ~30d IV over time"); ax[1, 0].set_ylabel("%")
    ax[1, 1].scatter(vrp_df["iv"] * 100, vrp_df["rv"] * 100, s=4, alpha=0.3)
    lim = [0, max(vrp_df["iv"].max(), vrp_df["rv"].max()) * 100]
    ax[1, 1].plot(lim, lim, "r--"); ax[1, 1].set_xlabel("implied vol %"); ax[1, 1].set_ylabel("next-30d realized %")
    ax[1, 1].set_title("VRP: implied vs realized (points above line = cheap options)")
    fig.tight_layout(); fig.savefig(OUT / "options_surface.png", dpi=110)


if __name__ == "__main__":
    main()
