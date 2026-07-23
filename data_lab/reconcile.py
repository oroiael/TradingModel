#!/usr/bin/env python3
"""
reconcile.py  --  put EVERY strategy on ONE consistent basis and expose the
inconsistencies that made earlier headline numbers non-comparable.

The three basis problems being fixed:
  (1) ANNUALIZATION: bracket_weekly reported arithmetic (mean/wk x 52); everything
      else geometric CAGR. Arithmetic >> geometric for a high-vol weekly series.
  (2) CAPITAL BASIS: the overnight ETF return is on FULL notional (= capital you post).
      The bracket return is "per $1 notional" but the capital truly at risk is only the
      premium (~12.6%/wk) + hedge margin -- so "per notional" understates its return on
      capital AND blending 40/60 "by notional" silently mixes two different leverages.
  (3) DRAWDOWN SAMPLING: blend/bracket drawdowns were computed on WEEKLY points; the
      overnight -77% was DAILY. Weekly sampling hides intra-week troughs -> shallower DD.

Here everything is a DAILY return series on the SAME 2022-2026 window, geometric CAGR,
DAILY maxDD, under the stated convention: each sleeve CASH-COLLATERALIZED at 1x notional
(the conservative, apples-to-apples choice). Leverage is then a separate, explicit dial.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import daily_oc_6y, load_options  # noqa: E402

ANN = 252
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 94 + f"\n{t}\n" + "=" * 94)


def stats(ret, freq=ANN):
    ret = np.asarray(ret, float); eq = np.cumprod(1 + ret)
    cagr = eq[-1] ** (freq / len(ret)) - 1 if eq[-1] > 0 else -1.0
    vol = ret.std(ddof=1) * np.sqrt(freq)
    sh = ret.mean() / ret.std(ddof=1) * np.sqrt(freq) if ret.std() > 0 else np.nan
    e = np.concatenate([[1.0], eq]); dd = (e / np.maximum.accumulate(e) - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd, mar=cagr / abs(dd) if dd else np.nan,
                arith=ret.mean() * freq)


def opt_index():
    o = load_options()
    o = o[(o["bid"] > 0) & (o["ask"] >= o["bid"]) & o["delta"].notna()].copy()
    o["trade_date"] = pd.to_datetime(o["trade_date"]); o["expiration"] = pd.to_datetime(o["expiration"])
    return {td: g for td, g in o.groupby("trade_date")}


def q(g, right, exp, k, field):
    row = g[(g["right"] == right) & (g["expiration"] == exp) & (g["strike"] == k)]
    if row.empty:
        return None
    if field == "delta":
        return float(row["delta"].iloc[0])
    b, a = float(row["bid"].iloc[0]), float(row["ask"].iloc[0])
    return {"bid": b, "ask": a, "mid": (a + b) / 2}[field]


def daily_bracket(idx, close, by_td, gate_map=None, rl=4, rh=9, ra=3):
    """DAILY P&L per $1 notional of a continuously-rolled ATM weekly straddle, delta-
    hedged daily at mid. One straddle live at a time (clean daily series). gate_map:
    optional {date: bool}; when False at a roll, stand down (flat) that week."""
    r = np.zeros(len(idx)); held = None
    for i, td in enumerate(idx):
        spot = float(close.iloc[i]); g = by_td.get(td)
        if g is None:
            continue
        if held is not None:
            for leg in held["legs"]:                      # mark options at mid
                m = q(g, leg["right"], held["exp"], leg["k"], "mid")
                if m is not None:
                    r[i] += (m - leg["prev"]) / held["es"]; leg["prev"] = m
            r[i] += held["hpos"] * (spot - held["pspot"]) / held["es"]   # hedge P&L
            held["pspot"] = spot
            nd = 0.0
            for leg in held["legs"]:
                dlt = q(g, leg["right"], held["exp"], leg["k"], "delta")
                nd += dlt if dlt is not None else 0.0
            held["hpos"] = -nd                            # re-hedge to current delta
        if held is None or (pd.Timestamp(held["exp"]) - td).days < ra:
            if held is not None:                          # close legs at bid
                for leg in held["legs"]:
                    m = q(g, leg["right"], held["exp"], leg["k"], "bid")
                    if m is not None:
                        r[i] += (m - leg["prev"]) / held["es"]
                held = None
            if gate_map is not None and not gate_map.get(td, True):
                continue
            g2 = g.assign(dte=(g["expiration"] - td).dt.days)
            cand = g2[g2["dte"].between(rl, rh)]
            if len(cand):
                exp = cand.iloc[(cand["dte"] - (rl + rh) // 2).abs().argmin()]["expiration"]
                ce = cand[cand["expiration"] == exp]
                calls, puts = ce[ce["right"] == "CALL"], ce[ce["right"] == "PUT"]
                if len(calls) and len(puts):
                    k = float(calls.iloc[(calls["strike"] - spot).abs().argmin()]["strike"])
                    legs, ok, nd0 = [], True, 0.0
                    for right in ("CALL", "PUT"):
                        a, mid = q(g, right, exp, k, "ask"), q(g, right, exp, k, "mid")
                        dlt = q(g, right, exp, k, "delta")
                        if a is None or mid is None:
                            ok = False; break
                        r[i] -= (a - mid) / spot           # entry half-spread
                        legs.append(dict(right=right, k=k, prev=mid)); nd0 += dlt if dlt else 0.0
                    if ok:
                        held = dict(exp=exp, es=spot, legs=legs, hpos=-nd0, pspot=spot)
    return pd.Series(r, index=idx)


def atm_iv_and_rv(d, by_td):
    """per-date ATM weekly implied vol and trailing 20d realized vol (for the VRP gate)."""
    cc = np.log(d["close"] / d["close"].shift(1))
    rv = cc.rolling(20).std() * np.sqrt(ANN)
    iv = {}
    for td, g in by_td.items():
        g2 = g.assign(dte=(g["expiration"] - td).dt.days)
        c = g2[g2["dte"].between(4, 9) & (g2["right"] == "CALL")]
        if len(c) and td in d.index:
            spot = float(d.loc[td, "close"])
            iv[td] = float(c.iloc[(c["strike"] - spot).abs().argmin()]["implied_vol"])
    return iv, rv


def main():
    by_td = opt_index()
    d = daily_oc_6y()
    lo, hi = min(by_td), max(by_td)
    d = d[(d.index >= lo) & (d.index <= hi)]
    idx, close = d.index, d["close"]
    on = (d["open"] / d["prev_close"] - 1)
    rv20 = on.rolling(20).std().shift(1) * np.sqrt(ANN)
    up = (close > close.rolling(50).mean()).shift(1).fillna(False).values
    e_vt = np.clip((0.60 / rv20).fillna(0.0), 0, 1.0).values

    raw_on = on.values
    gated_on = e_vt * up * raw_on
    hr("BUILD daily bracket sleeve (continuous weekly straddle, delta-hedged) -- ~1 min")
    iv, rv = atm_iv_and_rv(d, by_td)
    gate_map = {td: (rv.get(td, np.nan) >= 0.9 * iv.get(td, np.inf)) for td in idx}
    brk = daily_bracket(idx, close, by_td).values
    brk_g = daily_bracket(idx, close, by_td, gate_map=gate_map).values
    print(f"  {len(idx)} daily obs {idx.min().date()}->{idx.max().date()}")

    hr("1.  THE INCONSISTENCY, shown: arithmetic vs geometric annualization")
    sb = stats(brk)
    print(f"  bracket sleeve, SAME daily series:")
    print(f"    arithmetic (mean*252, the bracket_weekly convention) : {sb['arith']:+.0%}")
    print(f"    geometric  CAGR (compounded, the honest number)      : {sb['cagr']:+.0%}")
    print(f"    -> the +41% I quoted was arithmetic; comparable CAGR is ~{sb['cagr']:+.0%}.")

    hr("2.  ALL sleeves on ONE basis: daily returns, geometric CAGR, DAILY maxDD, 1x notional")
    rows = {
        "raw overnight (Finding B')": raw_on,
        "gated overnight (vt x trend)": gated_on,
        "bracket (weekly straddle)": brk,
        "bracket, VRP-gated": brk_g,
        "blend 40/60 (gated on + brkt)": 0.40 * gated_on + 0.60 * brk,
        "blend 40/60 (both gated)": 0.40 * gated_on + 0.60 * brk_g,
    }
    print(f"  {'strategy':32s} {'CAGR':>6} {'vol':>5} {'Sharpe':>7} {'maxDD(daily)':>13} {'MAR':>5}")
    S = {}
    for k, r in rows.items():
        s = stats(r); S[k] = s
        print(f"  {k:32s} {s['cagr']:>+6.0%} {s['vol']:>5.0%} {s['sharpe']:>+7.2f} "
              f"{s['maxdd']:>+13.0%} {s['mar']:>5.2f}")

    hr("3.  WEEKLY-sampled vs DAILY maxDD (why -36% looked better than it is)")
    for k in ["blend 40/60 (both gated)", "bracket (weekly straddle)"]:
        r = pd.Series(rows[k], index=idx)
        wk = (1 + r).resample("W").prod() - 1
        dd_d = stats(r)["maxdd"]; dd_w = stats(wk.values, freq=52)["maxdd"]
        print(f"  {k:32s} daily maxDD {dd_d:+.0%}   weekly-sampled maxDD {dd_w:+.0%}")

    hr("4.  WHY the blend CAGR < raw overnight, and only ~ bracket (the direct answers)")
    ro, go = stats(raw_on), stats(gated_on)
    bl = S["blend 40/60 (both gated)"]
    print(f"  * raw overnight = {ro['cagr']:+.0%} CAGR but maxDD {ro['maxdd']:+.0%} (the scary one).")
    print(f"  * gating it for safety ALREADY drops it to {go['cagr']:+.0%} (maxDD {go['maxdd']:+.0%}).")
    print(f"  * the blend then MIXES that {go['cagr']:+.0%} sleeve 40% with the bracket 60%, so its")
    print(f"    CAGR {bl['cagr']:+.0%} sits BETWEEN the two -- a blend averages returns; it buys")
    print(f"    a better SHARPE ({bl['sharpe']:.2f}) and shallower DD ({bl['maxdd']:+.0%}), not a higher CAGR.")
    print(f"  * so 'only marginally better than the bracket' is EXPECTED: diversification pays in")
    print(f"    risk-adjusted terms. If you want the raw {ro['cagr']:+.0%}, you must accept the {ro['maxdd']:+.0%} DD.")
    print(f"  * and all of it is at 1x notional; leverage scales CAGR and DD together (Sharpe fixed).")


if __name__ == "__main__":
    main()
