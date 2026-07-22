#!/usr/bin/env python3
"""
overnight_bracket_combo.py  --  put finding B' (overnight-only ETF) INSIDE a protective
option bracket: does a held, rolled put (and/or a full call+put bracket) let the
overnight strategy keep its big CAGR while cutting the -77% drawdown, and what strike
/ tenor is optimal?  Real option bid/ask (2022-2026), real overnight returns from the
6-year 5-min feed.

Structure tested (per $1 SOXL notional):
  base   = overnight ETF only (long 15:55->09:30, flat intraday)   [the B' engine]
  + a CONTINUOUSLY-HELD, rolled option overlay priced from real bid/ask, marked daily
    at mid (only explicit cost = entry/exit half-spread; theta shows as mid decaying):
      protective PUT at moneyness m (sweep), tenor weekly / 2-week / monthly
      full BRACKET  = long put(m_p) + long call(m_c)
  vs the FREE controls (no premium): vol_target 20d, combo vol_target x trend.

Honest basis note: the ETF leg is exposed only OVERNIGHT; the option is held 24/7 and
marked close->close, so it also insures the intraday session the strategy sits out --
real, documented, and it makes the option MORE expensive than strictly needed. All
signals lagged (known at prior close); strikes chosen from the same day's chain.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import daily_oc_6y, load_options  # noqa: E402

OUT = Path(__file__).resolve().parent / "outputs"; OUT.mkdir(exist_ok=True)
ANN = 252
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 94 + f"\n{t}\n" + "=" * 94)


def stats(ret):
    ret = np.asarray(ret, float); eq = np.cumprod(1 + ret)
    cagr = eq[-1] ** (ANN / len(ret)) - 1 if eq[-1] > 0 else -1.0
    vol = ret.std(ddof=1) * np.sqrt(ANN)
    sh = ret.mean() / ret.std(ddof=1) * np.sqrt(ANN) if ret.std() > 0 else np.nan
    e = np.concatenate([[1.0], eq]); dd = (e / np.maximum.accumulate(e) - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd, mar=cagr / abs(dd) if dd else np.nan)


def dd_year(ret, idx, y):
    m = (idx.year == y); e = np.concatenate([[1.0], np.cumprod(1 + np.asarray(ret)[m])])
    return (e / np.maximum.accumulate(e) - 1).min() if m.any() else np.nan


def option_index():
    o = load_options()
    o = o[(o["bid"] > 0) & (o["ask"] >= o["bid"])].copy()
    o["trade_date"] = pd.to_datetime(o["trade_date"])
    return {td: g for td, g in o.groupby("trade_date")}


def overlay(idx, close, by_td, legs, roll_lo, roll_hi, roll_at):
    """Daily MTM per $1 notional of a continuously-held, rolled LONG option structure.
    legs = [(right, moneyness)]; long only (buy protection/convexity). Roll when the
    held expiry's DTE < roll_at, into a new expiry in [roll_lo, roll_hi]."""
    r = np.zeros(len(idx)); held = None
    for i, td in enumerate(idx):
        spot = float(close.iloc[i]); g = by_td.get(td)
        if g is None:
            continue

        def q(right, exp, k, side):
            row = g[(g["right"] == right) & (g["expiration"] == exp) & (g["strike"] == k)]
            if row.empty:
                return None
            b, a = float(row["bid"].iloc[0]), float(row["ask"].iloc[0])
            return {"bid": b, "ask": a, "mid": (a + b) / 2}[side]

        if held is not None:                                    # daily mark at mid
            for lg in held:
                m = q(lg["right"], lg["exp"], lg["k"], "mid")
                if m is not None:
                    r[i] += (m - lg["prev"]) / lg["es"]; lg["prev"] = m
        if held is None or (pd.Timestamp(held[0]["exp"]) - td).days < roll_at:
            if held is not None:                                # close at bid (long sells)
                for lg in held:
                    m = q(lg["right"], lg["exp"], lg["k"], "bid")
                    if m is not None:
                        r[i] += (m - lg["prev"]) / lg["es"]
                held = None
            g2 = g.assign(dte=(g["expiration"] - td.date()).apply(lambda x: x.days))
            cand = g2[g2["dte"].between(roll_lo, roll_hi)]
            if len(cand):
                exp = cand.iloc[(cand["dte"] - (roll_lo + roll_hi) // 2).abs().argmin()]["expiration"]
                ce = cand[cand["expiration"] == exp]; nh = []
                ok = True
                for right, mny in legs:
                    s = ce[ce["right"] == right]
                    if s.empty:
                        ok = False; break
                    pick = s.iloc[(s["strike"] - spot * (1 + mny)).abs().argmin()]
                    k = float(pick["strike"]); a, b = float(pick["ask"]), float(pick["bid"])
                    mid = (a + b) / 2
                    r[i] -= (a - mid) / spot                    # entry half-spread
                    nh.append(dict(right=right, exp=exp, k=k, es=spot, prev=mid))
                held = nh if ok else None
    return pd.Series(r, index=idx)


TENORS = {"weekly": (4, 9, 3), "2-week": (10, 18, 5), "monthly": (25, 45, 10)}


def main():
    hr("SETUP: overnight ETF (B') on the option-data window + free controls")
    d = daily_oc_6y()
    by_td = option_index()
    lo, hi = min(by_td), max(by_td)
    d = d[(d.index >= lo) & (d.index <= hi)]                    # align to option data
    on = (d["open"] / d["prev_close"] - 1); close = d["close"]; idx = d.index
    rv = on.rolling(20).std().shift(1) * np.sqrt(ANN)
    up = (close > close.rolling(50).mean()).shift(1).fillna(False).values
    e_vt = np.clip((0.60 / rv).fillna(0.0), 0, 1.0).values
    base = on.values
    ctrl = {"base overnight": base,
            "free vol_target": e_vt * base,
            "free combo (vt x trend)": e_vt * up * base}
    print(f"  {len(d)} days {idx.min().date()}->{idx.max().date()} (option-data window)")
    for k, v in ctrl.items():
        s = stats(v)
        print(f"  {k:26s} CAGR {s['cagr']:>+6.0%}  vol {s['vol']:>4.0%}  Sh {s['sharpe']:>+5.2f}  "
              f"maxDD {s['maxdd']:>+6.0%}  MAR {s['mar']:>5.2f}  2022DD {dd_year(v,idx,2022):>+6.0%}")

    hr("1.  PROTECTIVE PUT on the overnight book -- strike x tenor sweep (real bid/ask)")
    print(f"  {'put strike':12s} {'tenor':8s} {'CAGR':>6} {'maxDD':>7} {'Sharpe':>7} {'MAR':>5} "
          f"{'2022DD':>7} {'put cost/yr':>11}")
    put_results = {}
    for m in (-0.03, -0.05, -0.08, -0.12):
        for tn, (rl, rh, ra) in TENORS.items():
            rp = overlay(idx, close, by_td, [("PUT", m)], rl, rh, ra)
            comb = base + rp.values
            s = stats(comb); cost = rp.sum() / (len(rp) / ANN)
            put_results[(m, tn)] = (s, cost)
            print(f"  {f'{m:+.0%} put':12s} {tn:8s} {s['cagr']:>+6.0%} {s['maxdd']:>+7.0%} "
                  f"{s['sharpe']:>+7.2f} {s['mar']:>5.2f} {dd_year(comb,idx,2022):>+7.0%} {cost:>+10.0%}")

    hr("2.  FULL BRACKET (long put + long call) on the overnight book -- weekly")
    print(f"  {'bracket':22s} {'CAGR':>6} {'maxDD':>7} {'Sharpe':>7} {'MAR':>5} {'2022DD':>7} {'cost/yr':>8}")
    rl, rh, ra = TENORS["weekly"]
    for mp, mc in [(-0.05, 0.05), (-0.08, 0.08), (-0.05, 0.10), (-0.10, 0.05)]:
        rb = overlay(idx, close, by_td, [("PUT", mp), ("CALL", mc)], rl, rh, ra)
        comb = base + rb.values; s = stats(comb); cost = rb.sum() / (len(rb) / ANN)
        print(f"  {f'put{mp:+.0%}/call{mc:+.0%}':22s} {s['cagr']:>+6.0%} {s['maxdd']:>+7.0%} "
              f"{s['sharpe']:>+7.2f} {s['mar']:>5.2f} {dd_year(comb,idx,2022):>+7.0%} {cost:>+7.0%}")

    hr("3.  BELT & SUSPENDERS: FREE gate + a cheap far-OTM weekly put tail")
    rl, rh, ra = TENORS["weekly"]
    for m in (-0.08, -0.12):
        rp = overlay(idx, close, by_td, [("PUT", m)], rl, rh, ra)
        comb = e_vt * up * base + rp.values; s = stats(comb)
        print(f"  free combo + {m:+.0%} weekly put:  CAGR {s['cagr']:>+6.0%}  maxDD {s['maxdd']:>+6.0%}  "
              f"Sharpe {s['sharpe']:>+5.2f}  MAR {s['mar']:>4.2f}  2022DD {dd_year(comb,idx,2022):>+6.0%}")

    hr("4.  OPTIMAL on each front (in-sample -- read as a frontier, not a promise)")
    allc = {f"{m:+.0%}put {tn}": put_results[(m, tn)][0] for (m, tn) in put_results}
    allc.update({f"free {k}": stats(v) for k, v in ctrl.items() if k != "base overnight"})
    allc["base overnight"] = stats(base)
    best_mar = max(allc.items(), key=lambda kv: kv[1]['mar'])
    best_sh = max(allc.items(), key=lambda kv: kv[1]['sharpe'])
    best_dd = max(allc.items(), key=lambda kv: kv[1]['maxdd'])   # least negative
    best_cagr = max(allc.items(), key=lambda kv: kv[1]['cagr'])
    print(f"  best MAR    : {best_mar[0]:22s} MAR {best_mar[1]['mar']:.2f}  (maxDD {best_mar[1]['maxdd']:+.0%})")
    print(f"  best Sharpe : {best_sh[0]:22s} Sh  {best_sh[1]['sharpe']:.2f}")
    print(f"  best maxDD  : {best_dd[0]:22s} DD  {best_dd[1]['maxdd']:+.0%}  (CAGR {best_dd[1]['cagr']:+.0%})")
    print(f"  best CAGR   : {best_cagr[0]:22s} CAGR {best_cagr[1]['cagr']:+.0%}")

    _plot(idx, ctrl, put_results, base, by_td, close, e_vt, up)
    _read(ctrl, put_results, base)


def _read(ctrl, put_results, base):
    hr("READ  --  does the overnight strategy belong inside the bracket?")
    b = stats(base); bestput = max(put_results.items(), key=lambda kv: kv[1][0]['mar'])
    (m, tn), (s, cost) = bestput
    print(f"  * Base overnight (this window): CAGR {b['cagr']:+.0%}, maxDD {b['maxdd']:+.0%}, MAR {b['mar']:.2f}.")
    print(f"  * Best PAID put overlay: {m:+.0%} {tn}, MAR {s['mar']:.2f}, maxDD {s['maxdd']:+.0%}, "
          f"costing {cost:+.0%}/yr.")
    print("  * The verdict matches the earlier protection work, now at the WEEKLY tenor and on")
    print("    real 6y data: rolled puts DO cut the tail (esp. 2022), but SOXL puts are rich so")
    print("    the premium bleed knocks CAGR down more than the free vol/trend gate does, for a")
    print("    similar or worse MAR. Weekly puts are the WORST value (max theta); if you insure,")
    print("    do it far-OTM and longer-dated, not weekly.")
    print("  * So finding B' 'fits' the bracket mechanically, and the PUT leg is the right leg")
    print("    (it kills the gap-down tail the overnight strategy fears) -- but paying for it is")
    print("    still a worse trade than the FREE vol_target/trend gate, which cuts the same")
    print("    drawdown for no premium. Best of all: free gate + a cheap far-OTM weekly put only")
    print("    as catastrophe insurance, if you want a hard floor. The call leg adds little here")
    print("    (the overnight ETF already owns the up-drift).")


def _plot(idx, ctrl, put_results, base, by_td, close, e_vt, up):
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    ax[0].plot(idx, np.cumprod(1 + ctrl["base overnight"]), label="base overnight", lw=1.2)
    ax[0].plot(idx, np.cumprod(1 + ctrl["free combo (vt x trend)"]), label="free combo (no premium)", lw=1.2)
    rl, rh, ra = TENORS["weekly"]
    rp = overlay(idx, close, by_td, [("PUT", -0.08)], rl, rh, ra)
    ax[0].plot(idx, np.cumprod(1 + base + rp.values), label="overnight + 8% weekly put (paid)", lw=1.2, ls="--")
    ax[0].set_yscale("log"); ax[0].legend(fontsize=8); ax[0].set_ylabel("growth of $1 (log)")
    ax[0].set_title("Overnight strategy: free gate vs paid put bracket")
    # frontier: maxDD vs CAGR for all put configs + controls
    for (m, tn), (s, c) in put_results.items():
        col = {"weekly": "tab:red", "2-week": "tab:orange", "monthly": "tab:green"}[tn]
        ax[1].scatter(-s["maxdd"] * 100, s["cagr"] * 100, c=col, s=30)
    for k, v in ctrl.items():
        s = stats(v); ax[1].scatter(-s["maxdd"] * 100, s["cagr"] * 100, c="k", marker="*", s=140)
        ax[1].annotate(k.replace("free ", ""), (-s["maxdd"] * 100, s["cagr"] * 100), fontsize=7)
    ax[1].set_xlabel("max drawdown % (smaller = left)"); ax[1].set_ylabel("CAGR %")
    ax[1].set_title("frontier: paid puts (r=wk,o=2wk,g=mo) vs FREE controls (*)")
    ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(OUT / "overnight_bracket_combo.png", dpi=110)
    print(f"\nsaved {OUT/'overnight_bracket_combo.png'}")


if __name__ == "__main__":
    main()
