#!/usr/bin/env python3
"""
bracket_deep.py  --  (1) sweep EVERY put-strike x call-strike combination to find the
right bracket, (2) run a detailed WEEKLY backtest of the 100%-bracket book with a
printed trade log + CSV, (3) document how exercise-at-intrinsic works notionally and
what the price data actually supports.

Honesty note: earlier work (bracket_weekly.py) tested only the ATM straddle and one ~5%
strangle. This is the full grid the request asks for. Built on the VALIDATED per-cycle
engine (matches the audit's +38% intrinsic for the ATM straddle).

--------------------------------------------------------------------------------------
HOW THE EXERCISE WORKS  (notional vs. reality with THIS data)
--------------------------------------------------------------------------------------
Notional (theory): a long bracket = long 1 PUT @ Kp + long 1 CALL @ Kc, weekly expiry.
  At expiry with underlying S_E:
    * if S_E > Kc : the CALL is in-the-money -> EXERCISE it: buy 100 sh @ Kc worth S_E,
      capturing (S_E - Kc)*100; the PUT expires worthless.
    * if S_E < Kp : the PUT is in-the-money -> EXERCISE it: sell 100 sh @ Kp, capturing
      (Kp - S_E)*100; the CALL expires worthless.
    * if Kp <= S_E <= Kc (strangle only): both expire worthless -> lose the premium.
  Because the book is DELTA-HEDGED, at expiry it already holds ~ -1 (or +1) share per
  ITM contract, so the exercised shares mostly CANCEL the hedge -> you end ~flat stock,
  and the realized value of the leg = its intrinsic |S_E - K|. There is NO assignment
  risk (both legs are LONG -- you choose whether to exercise).

Reality with the price data I have (daily EOD chain + validated EOD underlying):
  * The backtest settles each expiring leg at INTRINSIC = max(S_E - Kc,0)+max(Kp - S_E,0),
    using S_E = the underlying_price stamped on the chain at ~expiry (dte~0). That equals
    what exercise realizes. It does NOT sell the option into the market -- on expiry day
    the ITM BID sits ~1-2% of spot BELOW intrinsic (spreads 10-19%, volume ~5), so selling
    would give up that gap; exercising captures it. (This is exactly the optimistic side
    of the earlier audit.)
  * What the data does NOT capture / the idealizations: (a) real settlement uses the
    official close; my S_E is the 15:55/EOD mark (validated to ~0.15% vs daily EOD, so
    small but nonzero); (b) final-day gamma between the last EOD hedge and settlement is
    unhedged; (c) pin risk when S_E ~ K (which leg is ITM is uncertain into the close);
    (d) the operational cost/slippage of exercising and unwinding the delivered stock
    (small for a delta-hedged book, not zero). Net: intrinsic is achievable but is the
    OPTIMISTIC bound; selling at the bid is the pessimistic bound (see bracket_reality.py).
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
from data_loader import load_options, daily_oc_6y  # noqa: E402

OUT = HERE / "outputs"; OUT.mkdir(exist_ok=True)
ANN = 252; WKS = 52; CAP0 = 100_000
pd.set_option("display.width", 220)


def hr(t): print("\n" + "=" * 96 + f"\n{t}\n" + "=" * 96)


def cyc_options():
    o = load_options()
    o = o[(o["bid"] > 0) & (o["ask"] >= o["bid"]) & o["delta"].notna()].copy()
    o["trade_date"] = pd.to_datetime(o["trade_date"]); o["expiration"] = pd.to_datetime(o["expiration"])
    return o


def run_bracket(o, put_mny, call_mny):
    """Per weekly cycle: long PUT @ ~spot*(1+put_mny) + CALL @ ~spot*(1+call_mny), enter
    at ask ~8 DTE, delta-hedge daily on stamped deltas, settle at INTRINSIC (exercise)."""
    recs = []
    for exp, g in o.groupby("expiration"):
        g = g.sort_values("trade_date")
        dte = (exp - g["trade_date"]).dt.days
        em = (dte >= 4) & (dte <= 8)
        if not em.any():
            continue
        t0 = g.loc[em, "trade_date"].min()
        ge = g[g["trade_date"] == t0]
        spot0 = float(ge["underlying_price"].iloc[0])
        calls, puts = ge[ge["right"] == "CALL"], ge[ge["right"] == "PUT"]
        if calls.empty or puts.empty or spot0 <= 0:
            continue
        Kc = float(calls.iloc[(calls["strike"] - spot0 * (1 + call_mny)).abs().argmin()]["strike"])
        Kp = float(puts.iloc[(puts["strike"] - spot0 * (1 + put_mny)).abs().argmin()]["strike"])
        c0 = ge[(ge["right"] == "CALL") & (ge["strike"] == Kc)]
        p0 = ge[(ge["right"] == "PUT") & (ge["strike"] == Kp)]
        if c0.empty or p0.empty:
            continue
        cost = float(c0["ask"].iloc[0] + p0["ask"].iloc[0])
        iv0 = float(np.nanmean([c0["implied_vol"].iloc[0], p0["implied_vol"].iloc[0]]))
        gc = g[(g["right"] == "CALL") & (g["strike"] == Kc)].set_index("trade_date")
        gp = g[(g["right"] == "PUT") & (g["strike"] == Kp)].set_index("trade_date")
        dates = [d for d in sorted(set(gc.index) | set(gp.index)) if d >= t0]
        if len(dates) < 2:
            continue
        spot, nd = {}, {}
        for d in dates:
            src = gc if d in gc.index else gp
            spot[d] = float(src.loc[d, "underlying_price"])
            dcv = float(gc.loc[d, "delta"]) if d in gc.index else np.nan
            dpv = float(gp.loc[d, "delta"]) if d in gp.index else np.nan
            nd[d] = (dcv if dcv == dcv else 0.0) + (dpv if dpv == dpv else 0.0)
        hedge = 0.0; last = nd[dates[0]]
        for i in range(len(dates) - 1):
            hedge += -last * (spot[dates[i + 1]] - spot[dates[i]]); last = nd[dates[i + 1]]
        S_E = spot[dates[-1]]
        intrinsic = max(S_E - Kc, 0.0) + max(Kp - S_E, 0.0)
        recs.append(dict(date=t0, exp=exp, Kp=Kp, Kc=Kc, spot0=spot0, cost=cost, S_E=S_E,
                         intrinsic=intrinsic, hedge=hedge / spot0, iv=iv0,
                         premium_pct=cost / spot0, pnl=(intrinsic - cost + hedge) / spot0))
    return pd.DataFrame(recs).sort_values("date").reset_index(drop=True)


def add_gate(df):
    d = daily_oc_6y()
    cc = np.log(d["close"] / d["close"].shift(1)); trail = cc.rolling(20).std() * np.sqrt(ANN)
    df["trv"] = [float(trail.asof(pd.Timestamp(t))) for t in df["date"]]
    df["gate"] = (df["trv"] >= 0.9 * df["iv"]).values
    df["pnl_g"] = np.where(df["gate"], df["pnl"], 0.0)
    return df


def wk(r):
    r = np.asarray(r, float); eq = np.cumprod(1 + r)
    cagr = eq[-1] ** (WKS / len(r)) - 1 if eq[-1] > 0 else -1.0
    sh = r.mean() / r.std(ddof=1) * np.sqrt(WKS) if r.std() > 0 else np.nan
    e = np.concatenate([[1.0], eq]); dd = (e / np.maximum.accumulate(e) - 1).min()
    return dict(cagr=cagr, sharpe=sh, maxdd=dd, mar=cagr / abs(dd) if dd else np.nan)


def main():
    o = cyc_options()

    hr("1.  STRIKE SWEEP -- every put x call combination (gated, exercise@intrinsic)")
    put_m = [0.0, -0.02, -0.05, -0.08, -0.10]
    call_m = [0.0, 0.02, 0.05, 0.08, 0.10]
    print("  Sharpe grid (rows = put OTM %, cols = call OTM %); (0,0) = ATM straddle:")
    print("           " + "".join(f"call{int(c*100):+3d}%".rjust(9) for c in call_m))
    best = None; store = {}
    for pm in put_m:
        cells = []
        for cm in call_m:
            df = add_gate(run_bracket(o, pm, cm)); store[(pm, cm)] = df
            s = wk(df["pnl_g"]); cells.append(s["sharpe"])
            if best is None or s["sharpe"] > best[1]["sharpe"]:
                best = ((pm, cm), s)
        print(f"  put{int(pm*100):+4d}% " + "".join(f"{c:>9.2f}" for c in cells))
    print("\n  CAGR grid:")
    print("           " + "".join(f"call{int(c*100):+3d}%".rjust(9) for c in call_m))
    for pm in put_m:
        print(f"  put{int(pm*100):+4d}% " + "".join(f"{wk(store[(pm,cm)]['pnl_g'])['cagr']:>+8.0%} " for cm in call_m))
    (bpm, bcm), bs = best
    print(f"\n  BEST by Sharpe: put {bpm:+.0%} / call {bcm:+.0%}  "
          f"(Sharpe {bs['sharpe']:.2f}, CAGR {bs['cagr']:+.0%}, maxDD {bs['maxdd']:+.0%})")
    sa = wk(store[(0.0, 0.0)]['pnl_g'])
    print(f"  ATM straddle (0,0) for reference: Sharpe {sa['sharpe']:.2f}, CAGR {sa['cagr']:+.0%}, "
          f"maxDD {sa['maxdd']:+.0%}")
    print("  NOTE: this is IN-SAMPLE optimization over 25 combos -- read the grid for the")
    print("  PATTERN (is ATM robustly good?), don't over-trust the single best cell.")

    hr("2.  DETAILED WEEKLY BACKTEST of the 100% ATM-straddle bracket book ($100k)")
    df = store[(0.0, 0.0)].copy()
    eq = CAP0; rows = []
    for _, r in df.iterrows():
        pnl = r["pnl_g"]; pnl_dollar = eq * pnl if r["gate"] else 0.0
        rows.append(dict(week=len(rows) + 1, entry=r["date"].date(), expiry=r["exp"].date(),
                         K=r["Kc"], spot0=r["spot0"], prem_pct=r["premium_pct"], S_E=r["S_E"],
                         move_pct=r["S_E"] / r["spot0"] - 1, intr_pct=r["intrinsic"] / r["spot0"],
                         hedge_pct=r["hedge"], net_pct=pnl if r["gate"] else 0.0,
                         gate="ON" if r["gate"] else "off", equity=eq + pnl_dollar))
        eq += pnl_dollar
    log = pd.DataFrame(rows)
    log.to_csv(OUT / "bracket_100_weekly_log.csv", index=False)
    s = wk(df["pnl_g"])
    print(f"  $100,000 -> ${eq:,.0f} over {len(log)} weekly cycles ({log['entry'].iloc[0]} .. "
          f"{log['expiry'].iloc[-1]})")
    print(f"  CAGR {s['cagr']:+.0%}  Sharpe {s['sharpe']:.2f}  maxDD {s['maxdd']:+.0%}  "
          f"win {np.mean(df['pnl_g']>0):.0%}  weeks gated OFF {np.mean(~df['gate']):.0%}")
    print(f"  mean premium paid/wk {df['premium_pct'].mean():.1%} of notional; saved full log -> "
          f"outputs/bracket_100_weekly_log.csv\n")
    show = pd.concat([log.head(8), log[log['net_pct'].abs() > 0.10].head(6), log.tail(8)]).drop_duplicates('week')
    with pd.option_context('display.float_format', lambda v: f"{v:,.2f}"):
        print(show.to_string(index=False,
              columns=["week", "entry", "expiry", "K", "spot0", "prem_pct", "S_E", "move_pct",
                       "intr_pct", "hedge_pct", "net_pct", "gate", "equity"]))
    print("\n  columns: prem_pct=straddle premium paid (% of notional); move_pct=underlying move")
    print("  entry->expiry; intr_pct=intrinsic captured at exercise; hedge_pct=delta-hedge P&L;")
    print("  net_pct = intrinsic - premium + hedge (the week's return on notional).")

    hr("3.  by-year of the 100% ATM-straddle bracket")
    df["yr"] = df["date"].dt.year
    for y, g in df.groupby("yr"):
        print(f"  {y}: sum {g['pnl_g'].sum():+.0%}  compounded {np.prod(1+g['pnl_g'].values)-1:+.0%}  "
              f"weeks {len(g)}  gated-off {np.mean(~g['gate']):.0%}  best wk {g['pnl_g'].max():+.0%}  "
              f"worst {g['pnl_g'].min():+.0%}")

    _plot(log, store, put_m, call_m)


def _plot(log, store, put_m, call_m):
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    ax[0].plot(pd.to_datetime(log["entry"]), log["equity"], lw=1.4, color="tab:red")
    ax[0].axhline(CAP0, color="k", lw=0.6, ls=":"); ax[0].set_yscale("log")
    ax[0].set_ylabel("account $ (log)"); ax[0].set_title("100% ATM-straddle bracket, $100k, weekly (exercise)")
    grid = np.array([[wk(store[(pm, cm)]['pnl_g'])['sharpe'] for cm in call_m] for pm in put_m])
    im = ax[1].imshow(grid, cmap="RdYlGn", aspect="auto", origin="upper")
    ax[1].set_xticks(range(len(call_m))); ax[1].set_xticklabels([f"{int(c*100):+d}%" for c in call_m])
    ax[1].set_yticks(range(len(put_m))); ax[1].set_yticklabels([f"{int(p*100):+d}%" for p in put_m])
    ax[1].set_xlabel("call OTM"); ax[1].set_ylabel("put OTM"); ax[1].set_title("Sharpe by strike combo")
    for i in range(len(put_m)):
        for j in range(len(call_m)):
            ax[1].text(j, i, f"{grid[i,j]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax[1]); fig.tight_layout(); fig.savefig(OUT / "bracket_deep.png", dpi=110)
    print(f"\nsaved {OUT/'bracket_deep.png'}")


if __name__ == "__main__":
    main()
