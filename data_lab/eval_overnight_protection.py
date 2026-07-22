#!/usr/bin/env python3
"""
eval_overnight_protection.py  --  a SYSTEM for testing ways to cut the overnight
strategy's drawdown, on the FULL 2022-2026 series (real 5-min where available,
put-call-parity reconstruction for 2022-2023H1; validated to ~0.15%).

Overlays, each measured on one axis (CAGR / vol / Sharpe / maxDD / MAR=CAGR/|maxDD|):

  FREE (exploit the measured volatility CLUSTERING -- no premium paid):
    - vol_target : size overnight exposure = min(cap, target_vol / trailing_realized_vol)
    - trend      : flat overnight when close < SMA50 (down-gaps cluster in downtrends)
    - dd_stop    : cut exposure while the strategy is in a deep drawdown
    - combo      : vol_target x trend
  PAID (priced from real daily option bid/ask -- puts are RICH per the skew finding):
    - prot_put   : a continuously-held, monthly-rolled ~7% OTM put overlay

All signals use only info known at the prior close (no look-ahead).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import load_5min, load_options  # noqa: E402

OUT = Path(__file__).resolve().parent / "outputs"; OUT.mkdir(exist_ok=True)
ANN = 252
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 88 + f"\n{t}\n" + "=" * 88)


def spliced_daily():
    """Full 2022-2026 daily open/close: real 5-min (2023-07+) + reconstruction before."""
    rec = pd.read_csv(OUT / "underlying_reconstructed.csv", parse_dates=[0], index_col=0)
    fm = load_5min(); fm["ts"] = pd.to_datetime(fm["ts"]); fm["date"] = fm["ts"].dt.date
    fm["hm"] = fm["ts"].dt.strftime("%H:%M")
    o = fm[fm["hm"] == "09:30"].groupby("date")["Open"].first()
    c = fm[fm["hm"] == "15:55"].groupby("date")["Close"].first()
    real = pd.DataFrame({"open": o, "close": c}); real.index = pd.to_datetime(real.index)
    # real (ground truth) takes priority; reconstruction fills the pre-2023-07 gap
    df = real.combine_first(rec)[["open", "close"]].dropna().sort_index()
    df["prev_close"] = df["close"].shift(1)
    return df.dropna()


def stats(ret, cap0=1.0):
    ret = np.asarray(ret); eq = cap0 * np.cumprod(1 + ret)
    cagr = eq[-1] ** (ANN / len(ret)) - 1 if eq[-1] > 0 else -1.0
    vol = ret.std(ddof=1) * np.sqrt(ANN)
    sh = ret.mean() / ret.std(ddof=1) * np.sqrt(ANN) if ret.std() > 0 else np.nan
    e = np.concatenate([[cap0], eq]); dd = (e / np.maximum.accumulate(e) - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd, mar=cagr / abs(dd) if dd else np.nan, eq=eq)


def dd_stop_exposure(overnight, thresh=-0.25):
    """path-dependent: exposure 1 normally, 0 once equity DD < thresh, back to 1 at new high."""
    e = np.ones(len(overnight)); eq = 1.0; peak = 1.0; on = True
    for i, r in enumerate(overnight):
        e[i] = 1.0 if on else 0.0
        eq *= 1 + e[i] * r
        peak = max(peak, eq)
        if eq / peak - 1 < thresh:
            on = False
        if eq >= peak:
            on = True
    return e


def rolled_put_overlay(df):
    """Daily P&L per $1 SOXL notional of a monthly-rolled ~7% OTM put, priced from
    real daily option bid/ask (buy at ask, mark at mid, sell at bid on roll).
    Per $1 notional a put's P&L = (mark_change)/entry_spot. Negative = premium
    bleed; positive on crashes. Basis note: the put marks close->close while the
    strategy is exposed only overnight -- a real, documented imperfection."""
    opt = load_options()
    puts = opt[(opt["right"] == "PUT") & (opt["bid"] > 0) & (opt["ask"] >= opt["bid"])].copy()
    puts["trade_date"] = pd.to_datetime(puts["trade_date"])
    by_td = {td: g for td, g in puts.groupby("trade_date")}
    dates = df.index
    r_put = np.zeros(len(dates))
    held = None                                     # dict(exp,k,entry_spot,mark_prev)
    for i, td in enumerate(dates):
        spot = float(df["close"].iloc[i])
        g = by_td.get(td)
        if g is None:
            continue

        def mark(exp, k, side):
            row = g[(g["expiration"] == exp) & (g["strike"] == k)]
            if row.empty:
                return None
            b, a = float(row["bid"].iloc[0]), float(row["ask"].iloc[0])
            return {"bid": b, "ask": a, "mid": (a + b) / 2}[side]

        if held is not None:                        # daily mark at mid
            m = mark(held["exp"], held["k"], "mid")
            if m is not None:
                r_put[i] += (m - held["mark_prev"]) / held["entry_spot"]
                held["mark_prev"] = m

        if held is None or (pd.Timestamp(held["exp"]) - td).days < 15:
            if held is not None:                    # realize the roll-out at the bid
                mb = mark(held["exp"], held["k"], "bid")
                if mb is not None:
                    r_put[i] += (mb - held["mark_prev"]) / held["entry_spot"]
                held = None
            g2 = g.assign(dte=(g["expiration"] - td.date()).apply(lambda x: x.days))
            cand = g2[g2["dte"].between(30, 55)]
            if len(cand):
                pick = cand.iloc[(cand["strike"] - spot * 0.93).abs().argmin()]
                exp, k = pick["expiration"], float(pick["strike"])
                a, mid0 = mark(exp, k, "ask"), mark(exp, k, "mid")
                if a and mid0 and a > 0:
                    # pure MTM: hold the put at its MID; the only explicit cost is the
                    # entry half-spread (ask-mid). Theta decay shows up as mid falling.
                    r_put[i] -= (a - mid0) / spot
                    held = dict(exp=exp, k=k, entry_spot=spot, mark_prev=mid0)
    return pd.Series(r_put, index=dates)


def main():
    hr("BASE: overnight strategy on the FULL 2022-2026 series (spliced real+reconstructed)")
    df = spliced_daily()
    on = df["open"] / df["prev_close"] - 1                        # overnight return
    close = df["close"]
    print(f"{len(df)} days | {df.index.min().date()} -> {df.index.max().date()}  "
          f"(2022-2023H1 = reconstructed, validated ~0.15%)")
    b = stats(on.values)
    print(f"  BASE overnight: CAGR {b['cagr']:+.0%}  vol {b['vol']:.0%}  Sharpe {b['sharpe']:+.2f}  "
          f"maxDD {b['maxdd']:+.0%}  MAR {b['mar']:.2f}")
    print(f"  (adding 2022 deepened the drawdown: the overnight drift REVERSED in the bear.)")

    # signals (all shifted -> known at prior close)
    rv = on.rolling(20).std().shift(1) * np.sqrt(ANN)
    sma = close.rolling(50).mean()
    uptrend = (close > sma).shift(1).fillna(False)

    overlays = {}
    overlays["base"] = on.values
    for tgt, cap in [(0.60, 1.0), (0.60, 2.0)]:
        e = np.clip((tgt / rv).fillna(0.0), 0, cap).values
        overlays[f"vol_target {tgt:.0%} cap{cap:.0f}x"] = e * on.values
    overlays["trend (flat if <SMA50)"] = uptrend.values * on.values
    overlays["dd_stop -25%"] = dd_stop_exposure(on.values, -0.25) * on.values
    e_vt = np.clip((0.60 / rv).fillna(0.0), 0, 1.0).values
    overlays["combo vol_target x trend"] = e_vt * uptrend.values * on.values

    hr("PROTECTION FRONTIER (free overlays)  --  CAGR / vol / Sharpe / maxDD / MAR")
    print(f"  {'overlay':28s} {'CAGR':>7} {'vol':>6} {'Sharpe':>7} {'maxDD':>7} {'MAR':>6}")
    results = {}
    for name, r in overlays.items():
        s = stats(r); results[name] = s
        print(f"  {name:28s} {s['cagr']:>+7.0%} {s['vol']:>6.0%} {s['sharpe']:>+7.2f} "
              f"{s['maxdd']:>+7.0%} {s['mar']:>6.2f}")

    hr("PAID overlay: continuously-held monthly-rolled ~7% OTM protective PUT (real bid/ask)")
    r_put = rolled_put_overlay(df)
    hedged = on.values + r_put.values                            # overnight strat + put MTM
    sp = stats(hedged); results["prot_put (rich, real cost)"] = sp
    print(f"  overnight + rolled put: CAGR {sp['cagr']:+.0%}  vol {sp['vol']:.0%}  "
          f"Sharpe {sp['sharpe']:+.2f}  maxDD {sp['maxdd']:+.0%}  MAR {sp['mar']:.2f}")
    print(f"  put premium bleed ~ {r_put[r_put<0].sum():.0%} total; crash offset ~ {r_put[r_put>0].sum():+.0%} total")

    _plot(df, results, overlays, hedged)
    print(f"\nsaved {OUT/'overnight_protection.png'}")
    _read(b, results)


def _read(base, results):
    hr("READ")
    best_mar = max(results.items(), key=lambda kv: (kv[1]['mar'] if kv[1]['mar'] == kv[1]['mar'] else -9))
    print(f"  base MAR {base['mar']:.2f} (maxDD {base['maxdd']:+.0%}).  "
          f"best risk-adjusted overlay: {best_mar[0]} (MAR {best_mar[1]['mar']:.2f}, "
          f"maxDD {best_mar[1]['maxdd']:+.0%}).")
    print("  Compare the FREE vol/trend overlays (drawdown cut for ~no cost, exploiting vol")
    print("  clustering) against the PAID rich put (protection minus premium bleed). The MAR")
    print("  and maxDD columns show which actually mitigates the swing best per unit return.")


def _plot(df, results, overlays, hedged):
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    x = df.index
    for name in ["base", "vol_target 60% cap1x", "trend (flat if <SMA50)", "combo vol_target x trend"]:
        if name in overlays:
            ax[0].plot(x, np.cumprod(1 + overlays[name]), label=name, lw=1.2)
    ax[0].plot(x, np.cumprod(1 + hedged), label="prot_put", lw=1.2, ls="--")
    ax[0].set_yscale("log"); ax[0].legend(fontsize=8); ax[0].set_ylabel("growth of $1 (log)")
    ax[0].set_title("overnight strategy: drawdown-protection overlays (2022-2026)")
    names = list(results.keys()); dds = [results[n]["maxdd"] * 100 for n in names]
    ax[1].barh(range(len(names)), dds, color="tab:red")
    ax[1].set_yticks(range(len(names))); ax[1].set_yticklabels(names, fontsize=8)
    ax[1].set_xlabel("max drawdown %"); ax[1].set_title("max drawdown by overlay")
    fig.tight_layout(); fig.savefig(OUT / "overnight_protection.png", dpi=110)


if __name__ == "__main__":
    main()
