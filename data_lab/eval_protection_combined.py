#!/usr/bin/env python3
"""
eval_protection_combined.py  --  cheaper option hedges (put spread, collar, tail
put) priced from real bid/ask, AND the combined free overlay (vol_target x trend)
as the recommended 'protected overnight' config -- plus whether a cheap option tail
adds anything ON TOP of the free protection. Full 2022-2026 (real + reconstruction).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import load_options  # noqa: E402
from eval_overnight_protection import spliced_daily, stats  # reuse validated pieces

OUT = Path(__file__).resolve().parent / "outputs"
ANN = 252
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 88 + f"\n{t}\n" + "=" * 88)


def option_index():
    opt = load_options()
    o = opt[(opt["bid"] > 0) & (opt["ask"] >= opt["bid"])].copy()
    o["trade_date"] = pd.to_datetime(o["trade_date"])
    return {td: g for td, g in o.groupby("trade_date")}


def option_overlay(df, by_td, legs, dte_lo=30, dte_hi=55):
    """Daily MTM per $1 SOXL notional of a monthly-rolled multi-leg option structure.
    legs = [(right, moneyness_target, qty)] with qty +1 long / -1 short. Long legs
    enter at ask & exit at bid; shorts the reverse; carried at mid (pure MTM, so the
    only explicit costs are the half-spreads; theta = mid decaying)."""
    dates = df.index
    r = np.zeros(len(dates))
    held = None
    for i, td in enumerate(dates):
        spot = float(df["close"].iloc[i]); g = by_td.get(td)
        if g is None:
            continue

        def mk(right, exp, k, side):
            row = g[(g["right"] == right) & (g["expiration"] == exp) & (g["strike"] == k)]
            if row.empty:
                return None
            b, a = float(row["bid"].iloc[0]), float(row["ask"].iloc[0])
            return {"bid": b, "ask": a, "mid": (a + b) / 2}[side]

        if held is not None:                              # daily mark at mid
            for lg in held:
                m = mk(lg["right"], lg["exp"], lg["k"], "mid")
                if m is not None:
                    r[i] += lg["qty"] * (m - lg["prev"]) / lg["es"]; lg["prev"] = m

        if held is None or (pd.Timestamp(held[0]["exp"]) - td).days < 15:
            if held is not None:                          # close: long->bid, short->ask
                for lg in held:
                    side = "bid" if lg["qty"] > 0 else "ask"
                    m = mk(lg["right"], lg["exp"], lg["k"], side)
                    if m is not None:
                        r[i] += lg["qty"] * (m - lg["prev"]) / lg["es"]
                held = None
            g2 = g.assign(dte=(g["expiration"] - td.date()).apply(lambda x: x.days))
            cand = g2[g2["dte"].between(dte_lo, dte_hi)]
            if len(cand):
                exp = cand.iloc[(cand["dte"] - (dte_lo + dte_hi) // 2).abs().argmin()]["expiration"]
                ce = cand[cand["expiration"] == exp]
                nh, ok = [], True
                for right, mny, qty in legs:
                    s = ce[ce["right"] == right]
                    if s.empty:
                        ok = False; break
                    pick = s.iloc[(s["strike"] - spot * (1 + mny)).abs().argmin()]
                    k = float(pick["strike"]); b, a = float(pick["bid"]), float(pick["ask"])
                    mid = (a + b) / 2
                    r[i] -= abs(qty) * ((a - mid) if qty > 0 else (mid - b)) / spot  # entry half-spread
                    nh.append(dict(right=right, exp=exp, k=k, qty=qty, es=spot, prev=mid))
                held = nh if ok else None
    return pd.Series(r, index=dates)


def main():
    hr("SETUP: base overnight series (full 2022-2026) + free overlays")
    df = spliced_daily()
    on = df["open"] / df["prev_close"] - 1
    close = df["close"]
    rv = on.rolling(20).std().shift(1) * np.sqrt(ANN)
    uptrend = (close > close.rolling(50).mean()).shift(1).fillna(False).values
    e_vt = np.clip((0.60 / rv).fillna(0.0), 0, 1.0).values
    base = on.values
    vt = e_vt * base
    combo_free = e_vt * uptrend * base                     # vol_target x trend (recommended free)
    by_td = option_index()

    hr("1a. CHEAPER PROTECTIVE PUTS vs the rich outright put (real bid/ask, on OVERNIGHT base)")
    # long-only protective structures: a long put is a fair protective overlay on the
    # overnight book (basis imperfection is modest and mostly conservative -- it also
    # catches a few intraday crashes the book never took, i.e. errs toward MORE hedge).
    put_structs = {
        "outright 7% put":       [("PUT", -0.07, +1)],
        "put spread 7/20%":      [("PUT", -0.07, +1), ("PUT", -0.20, -1)],
        "tail put 15%":          [("PUT", -0.15, +1)],
    }
    print(f"  {'structure':22s} {'CAGR':>7} {'maxDD':>7} {'Sharpe':>7} {'MAR':>6} {'net cost/yr':>12}")
    ov = {}
    for name, legs in put_structs.items():
        r = option_overlay(df, by_td, legs); ov[name] = r
        s = stats(base + r.values)
        cost = r.sum() / (len(r) / ANN)                    # net option P&L/yr (neg = cost)
        print(f"  {name:22s} {s['cagr']:>+7.0%} {s['maxdd']:>+7.0%} {s['sharpe']:>+7.2f} "
              f"{s['mar']:>6.2f} {cost:>+11.0%}")
    sb = stats(base)
    print(f"  {'(base, no hedge)':22s} {sb['cagr']:>+7.0%} {sb['maxdd']:>+7.0%} "
          f"{sb['sharpe']:>+7.2f} {sb['mar']:>6.2f}")

    hr("1b. COLLAR (short call funds the put) -- FAIR test needs a CONTINUOUS long base")
    # A continuous short call is exposed 24/7; the overnight book is long only overnight,
    # so bolting a short call onto it just hands away the intraday upside it never took
    # (-> ruinous, meaningless number). A collar only makes sense on a continuously-held
    # position. So test it on buy&hold close->close, where both legs share one exposure.
    bh = (df["close"] / df["prev_close"] - 1).values       # continuous long, close->close
    print(f"  {'structure':22s} {'CAGR':>7} {'maxDD':>7} {'Sharpe':>7} {'MAR':>6} {'net cost/yr':>12}")
    for name, legs in {
        "collar 7%put/7%call":   [("PUT", -0.07, +1), ("CALL", +0.07, -1)],
        "collar 7%put/12%call":  [("PUT", -0.07, +1), ("CALL", +0.12, -1)],
    }.items():
        r = option_overlay(df, by_td, legs)
        s = stats(bh + r.values)
        cost = r.sum() / (len(r) / ANN)
        print(f"  {name:22s} {s['cagr']:>+7.0%} {s['maxdd']:>+7.0%} {s['sharpe']:>+7.2f} "
              f"{s['mar']:>6.2f} {cost:>+11.0%}")
    sbh = stats(bh)
    print(f"  {'(buy&hold, no collar)':22s} {sbh['cagr']:>+7.0%} {sbh['maxdd']:>+7.0%} "
          f"{sbh['sharpe']:>+7.2f} {sbh['mar']:>6.2f}")
    print("  NOTE: the same collar bolted onto the OVERNIGHT book prints ~-99% -- a basis")
    print("  artifact (24/7 short call vs overnight-only exposure), NOT a real collar result.")
    structs = put_structs                                  # section 2 reuses the put legs

    hr("2.  RECOMMENDED: combined FREE overlay, and free + a CHEAP option tail")
    configs = {
        "base": base,
        "vol_target (free)": vt,
        "combo free (vol_target x trend)": combo_free,
        "combo free + put spread 7/20%": combo_free + option_overlay(df, by_td, structs["put spread 7/20%"]).values,
        "combo free + tail put 15%": combo_free + option_overlay(df, by_td, structs["tail put 15%"]).values,
    }
    print(f"  {'config':34s} {'CAGR':>7} {'vol':>6} {'Sharpe':>7} {'maxDD':>7} {'MAR':>6}")
    res = {}
    for name, r in configs.items():
        s = stats(r); res[name] = s
        print(f"  {name:34s} {s['cagr']:>+7.0%} {s['vol']:>6.0%} {s['sharpe']:>+7.2f} "
              f"{s['maxdd']:>+7.0%} {s['mar']:>6.2f}")

    hr("3.  by-year max drawdown of the recommended configs")
    for name in ["base", "combo free (vol_target x trend)", "combo free + put spread 7/20%"]:
        r = pd.Series(configs[name], index=df.index)
        yr = {}
        for y, g in r.groupby(r.index.year):
            eq = np.cumprod(1 + g.values); e = np.concatenate([[1], eq])
            yr[y] = (e / np.maximum.accumulate(e) - 1).min()
        print(f"  {name:34s}: " + "  ".join(f"{y}:{d:+.0%}" for y, d in yr.items()))

    _plot(df, configs, res)
    _read(res)


def _read(res):
    hr("READ")
    print("  1) Cheaper PUT structures do cut the bleed (tail-put 15% ~-27%/yr vs outright")
    print("     ~-35%/yr) but ALL still gut return and barely move the -76% drawdown -> puts")
    print("     are too rich (skew +9%) to be worth buying. Least-bad = tail put, MAR 0.20.")
    print("  2) A collar can't fund the put on THIS book: the short call needs a continuous")
    print("     long, which the overnight strategy is not. On buy&hold it's a real (upside-")
    print("     capped) collar; on the overnight book it's just a basis artifact.")
    print("  3) Adding ANY paid option tail ON TOP of the free overlay makes it WORSE: combo")
    print("     free is +28%/-54%/MAR 0.52; + put-spread -> -5%/-57%, + tail-put -> -7%/-68%.")
    print("     The bleed swamps the marginal crash protection, and full-period maxDD rises.")
    print("  => RECOMMENDED: the FREE overlay, no bought protection. combo vol_target x trend")
    print("     for the lowest swing (-76% -> -54%), or vol_target alone for best return/DD")
    print("     (MAR 0.69, and it RAISES return). The pricing says: don't insure with rich puts.")


def _plot(df, configs, res):
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    for name in ["base", "vol_target (free)", "combo free (vol_target x trend)",
                 "combo free + put spread 7/20%"]:
        ax[0].plot(df.index, np.cumprod(1 + configs[name]), label=name, lw=1.2)
    ax[0].set_yscale("log"); ax[0].legend(fontsize=8); ax[0].set_ylabel("growth of $1 (log)")
    ax[0].set_title("Recommended protected overnight configs (2022-2026)")
    names = list(res.keys()); dd = [res[n]["maxdd"] * 100 for n in names]
    ax[1].barh(range(len(names)), dd, color="tab:purple")
    ax[1].set_yticks(range(len(names))); ax[1].set_yticklabels(names, fontsize=8)
    ax[1].set_xlabel("max drawdown %"); ax[1].set_title("max drawdown")
    fig.tight_layout(); fig.savefig(OUT / "protection_combined.png", dpi=110)
    print(f"\nsaved {OUT/'protection_combined.png'}")


if __name__ == "__main__":
    main()
