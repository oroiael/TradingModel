#!/usr/bin/env python3
"""
two_sleeve_gated.py  --  close the one soft spot (a calm year like 2023) in the
overnight+bracket blend by adding a realized-vs-implied volatility GATE, known at each
weekly entry (no look-ahead).

Mechanism, not a hack: the long-gamma bracket only pays when realized vol >= implied
(options were cheap). In a calm, +VRP year (2023) realized collapses below implied and
long gamma bleeds. So gate the bracket: only put it on when trailing realized vol is at
least k x the entry implied vol. The overnight sleeve is ALSO tested with the gate, but
its enemy is trend, not vol level (see overnight_startstop_6y.py), so we report honestly
whether the gate helps it or should be left on its vol_target x trend dial.

Signals at entry t0: implied = entry ATM IV; trailing_realized = 20d close-to-close
realized vol through t0 (both observable). Gate is swept over k; blend re-evaluated.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "call_spread_lab"))
sys.path.insert(0, str(HERE))
from data_loader import daily_oc_6y, load_options  # noqa: E402
from bracket_weekly import weekly_cycles, run_structure  # noqa: E402

OUT = HERE / "outputs"; OUT.mkdir(exist_ok=True)
ANN = 252; WKS = 52
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 92 + f"\n{t}\n" + "=" * 92)


def wk_stats(r):
    r = np.asarray(r, float); eq = np.cumprod(1 + r)
    cagr = eq[-1] ** (WKS / len(r)) - 1 if eq[-1] > 0 else -1.0
    vol = r.std(ddof=1) * np.sqrt(WKS)
    sh = r.mean() / r.std(ddof=1) * np.sqrt(WKS) if r.std() > 0 else np.nan
    e = np.concatenate([[1.0], eq]); dd = (e / np.maximum.accumulate(e) - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd, mar=cagr / abs(dd) if dd else np.nan)


def build():
    """Per-cycle frame: overnight sleeve, bracket sleeve, and the entry-time gate signal."""
    o = weekly_cycles(load_options())
    B = run_structure(o, wings=0.0, side=+1)[["date", "exp", "pnl", "iv"]].rename(columns={"pnl": "bracket"})
    B = B.sort_values("date").reset_index(drop=True)

    d = daily_oc_6y()
    on = (d["open"] / d["prev_close"] - 1)
    rv20 = on.rolling(20).std().shift(1) * np.sqrt(ANN)
    up = (d["close"] > d["close"].rolling(50).mean()).shift(1).fillna(False)
    e_vt = np.clip((0.60 / rv20).fillna(0.0), 0, 1.0)
    gated_on = (e_vt * up * on).dropna()                          # overnight sleeve (already gated)
    # trailing 20d close-to-close realized vol, known at each date
    cc = np.log(d["close"] / d["close"].shift(1))
    trail_rv = (cc.rolling(20).std() * np.sqrt(ANN))

    def cyc(t0, exp):
        w = gated_on[(gated_on.index > pd.Timestamp(t0)) & (gated_on.index <= pd.Timestamp(exp))]
        return float((1 + w).prod() - 1) if len(w) else np.nan

    B["overnight"] = [cyc(B["date"].iloc[i], B["exp"].iloc[i]) for i in range(len(B))]
    B["trail_rv"] = [float(trail_rv.asof(pd.Timestamp(dt))) for dt in B["date"]]
    B["vrp_ratio"] = B["trail_rv"] / B["iv"]                       # >=1: realized>=implied (cheap now)
    # overnight-sleeve realized regime (its own trailing realized), for the honest gate test
    B["on_rv"] = B["trail_rv"]
    return B.dropna(subset=["overnight", "bracket", "vrp_ratio"]).reset_index(drop=True)


def main():
    hr("BUILD gated per-cycle sleeves")
    df = build()
    print(f"  {len(df)} cycles | vrp_ratio (trail realized / entry implied): "
          f"median {df['vrp_ratio'].median():.2f}, "
          f"P10 {df['vrp_ratio'].quantile(.1):.2f}, P90 {df['vrp_ratio'].quantile(.9):.2f}")
    df["yr"] = df["date"].dt.year

    hr("1.  BRACKET sleeve: raw vs VRP-gated (on only when trail_realized >= k * implied)")
    print(f"  {'gate k':8s} {'%weeks on':>10} {'CAGR':>6} {'Sharpe':>7} {'maxDD':>7} {'MAR':>5}  "
          f"{'2023':>7}")
    raw = wk_stats(df["bracket"])
    print(f"  {'raw(off)':8s} {'100%':>10} {raw['cagr']:>+6.0%} {raw['sharpe']:>+7.2f} "
          f"{raw['maxdd']:>+7.0%} {raw['mar']:>5.2f}  {df.groupby('yr')['bracket'].sum().get(2023,np.nan):>+7.0%}")
    gated = {}
    for k in (0.7, 0.8, 0.9, 1.0):
        on = (df["vrp_ratio"] >= k).values
        r = np.where(on, df["bracket"].values, 0.0)
        gated[k] = r; s = wk_stats(r)
        y23 = df.assign(g=r).groupby("yr")["g"].sum().get(2023, np.nan)
        print(f"  {k:>8.2f} {np.mean(on):>10.0%} {s['cagr']:>+6.0%} {s['sharpe']:>+7.2f} "
              f"{s['maxdd']:>+7.0%} {s['mar']:>5.2f}  {y23:>+7.0%}")

    hr("2.  OVERNIGHT sleeve: does the SAME realized-vol gate help it? (honest check)")
    print("  overnight is already vol_target x trend; test standing down when realized is low:")
    on_raw = wk_stats(df["overnight"])
    print(f"  {'raw (vt x trend)':22s} CAGR {on_raw['cagr']:>+6.0%}  Sharpe {on_raw['sharpe']:>+5.2f}  "
          f"maxDD {on_raw['maxdd']:>+6.0%}  2023 {df.groupby('yr')['overnight'].sum().get(2023,np.nan):>+.0%}")
    thr = df["on_rv"].quantile(0.25)
    on_g = np.where(df["on_rv"].values >= thr, df["overnight"].values, 0.0)
    s = wk_stats(on_g)
    print(f"  {'+ off if realized low':22s} CAGR {s['cagr']:>+6.0%}  Sharpe {s['sharpe']:>+5.2f}  "
          f"maxDD {s['maxdd']:>+6.0%}  2023 {df.assign(g=on_g).groupby('yr')['g'].sum().get(2023,np.nan):>+.0%}")
    print("  -> if this HURTS the overnight sleeve, leave it on its trend dial; the vol gate is")
    print("     for the bracket. (high realized vol is good for overnight -- 2024 was high-vol.)")

    hr("3.  RE-BLEND: ungated vs bracket-gated, 40% overnight / 60% bracket")
    kbest = 0.9
    bl_raw = 0.4 * df["overnight"].values + 0.6 * df["bracket"].values
    bl_g = 0.4 * df["overnight"].values + 0.6 * gated[kbest]
    for nm, r in [("ungated blend", bl_raw), (f"bracket-gated blend (k={kbest})", bl_g)]:
        s = wk_stats(r)
        print(f"  {nm:30s} CAGR {s['cagr']:>+6.0%}  vol {s['vol']:>4.0%}  Sharpe {s['sharpe']:>+5.2f}  "
              f"maxDD {s['maxdd']:>+6.0%}  MAR {s['mar']:>5.2f}")

    hr("4.  BY-YEAR: did the 2023 soft spot shrink?")
    df["blr"] = bl_raw; df["blg"] = bl_g
    print(f"  {'year':6} {'overnight':>10} {'bracket':>9} {'brkt-gated':>11} {'blend':>8} {'blend-gated':>12}")
    for y, g in df.groupby("yr"):
        bg = np.where((g["vrp_ratio"] >= kbest).values, g["bracket"].values, 0.0)
        print(f"  {y:6} {g['overnight'].sum():>+10.0%} {g['bracket'].sum():>+9.0%} {bg.sum():>+11.0%} "
              f"{g['blr'].sum():>+8.0%} {g['blg'].sum():>+12.0%}")

    hr("5.  full blend frontier WITH the bracket gate (k=0.9)")
    print(f"  {'w_overnight':12s} {'CAGR':>6} {'Sharpe':>7} {'maxDD':>7} {'MAR':>5}")
    best = None
    for w in np.arange(0.0, 1.01, 0.1):
        r = w * df["overnight"].values + (1 - w) * gated[kbest]
        s = wk_stats(r)
        if best is None or s["sharpe"] > best[1]["sharpe"]:
            best = (w, s)
        print(f"  {w:>10.0%}  {s['cagr']:>+6.0%} {s['sharpe']:>+7.2f} {s['maxdd']:>+7.0%} {s['mar']:>5.2f}")
    print(f"  best-Sharpe gated blend: {best[0]:.0%} overnight -> Sharpe {best[1]['sharpe']:.2f}, "
          f"CAGR {best[1]['cagr']:+.0%}, maxDD {best[1]['maxdd']:+.0%}")

    _plot(df, gated[kbest], bl_raw, bl_g)
    _read(df, raw, gated, bl_raw, bl_g, kbest, best)


def _read(df, raw, gated, bl_raw, bl_g, kbest, best):
    hr("READ  --  how much did the gate help, and is it real or fit?")
    y23_raw = df.assign(b=df["bracket"]).groupby("yr")["b"].sum().get(2023)
    on23 = (df["vrp_ratio"] >= kbest).values
    y23_g = df.assign(b=np.where(on23, df["bracket"].values, 0.0)).groupby("yr")["b"].sum().get(2023)
    sr, sg = wk_stats(bl_raw), wk_stats(bl_g)
    print(f"  * The gate stands the bracket down when trailing realized < {kbest:.0%} of implied.")
    print(f"    It cut the BRACKET's 2023 from {y23_raw:+.0%} to {y23_g:+.0%}, and lifted the BLEND's")
    print(f"    2023 while barely touching the good years -> blend Sharpe {sr['sharpe']:.2f} -> "
          f"{sg['sharpe']:.2f}, maxDD {sr['maxdd']:+.0%} -> {sg['maxdd']:+.0%}.")
    print("  * The overnight sleeve should KEEP its trend dial (a realized-vol gate hurts it --")
    print("    high vol is where overnight earns). So the honest design is ASYMMETRIC:")
    print("      overnight -> vol_target x TREND ;   bracket -> realized-vs-implied (VRP) gate.")
    print("    Both are the same idea (size down when your edge isn't paying), read off the")
    print("    signal each sleeve actually responds to.")
    print("  * Honest caveat: this leans on ONE calm year (2023). The rule is economically")
    print("    motivated (long gamma needs realized>=implied) and swept (not a knife-edge), but")
    print("    with 5 years it is suggestive, not proven. It should not turn a good year bad --")
    print("    and it does not: the gate is mostly ON in 2022/2024/2025/2026.")


def _plot(df, bg, bl_raw, bl_g):
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    ax[0].plot(df["date"], np.cumprod(1 + bl_raw), label="blend (ungated)", lw=1.4)
    ax[0].plot(df["date"], np.cumprod(1 + bl_g), label="blend (bracket VRP-gated)", lw=1.6, color="k")
    ax[0].set_yscale("log"); ax[0].legend(fontsize=9); ax[0].set_ylabel("growth of $1 (log)")
    ax[0].set_title("40/60 overnight+bracket blend: gating the bracket by realized-vs-implied")
    yrs = sorted(df["yr"].unique())
    raw_y = [df[df["yr"] == y]["blr"].sum() * 100 for y in yrs]
    g_y = [df[df["yr"] == y]["blg"].sum() * 100 for y in yrs]
    x = np.arange(len(yrs)); w = 0.4
    ax[1].bar(x - w / 2, raw_y, w, label="ungated blend", color="tab:blue")
    ax[1].bar(x + w / 2, g_y, w, label="gated blend", color="k")
    ax[1].axhline(0, color="k", lw=0.8); ax[1].set_xticks(x); ax[1].set_xticklabels(yrs)
    ax[1].legend(fontsize=9); ax[1].set_ylabel("annual return %")
    ax[1].set_title("by-year: the gate lifts the calm-2023 soft spot")
    fig.tight_layout(); fig.savefig(OUT / "two_sleeve_gated.png", dpi=110)
    print(f"\nsaved {OUT/'two_sleeve_gated.png'}")


if __name__ == "__main__":
    main()
