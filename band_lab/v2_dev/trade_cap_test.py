"""
V17 — the trade cap (V7), tested at the margin.

See V17_TRADE_CAP_TEST.md. The adoption bar in §6 of that document was written
and committed before this script was run.

The cap moves no price — it only decides whether trade N of the day happens.
So the question is asked directly ("is the Nth trade worth taking?") rather
than as a sweep. T1/T2 are the diagnostics, T3/T4 the confirmation.

    python3 band_lab/v2_dev/trade_cap_test.py
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
ROOT = os.path.dirname(_BAND_LAB)
for _p in (os.path.join(_BAND_LAB, "live"), os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from intrabar import load_1min_sessions, replay_symbol_intrabar  # noqa: E402
from replay import backtest_config, load_sessions                # noqa: E402
from spec_constants import MAX_STOPS                             # noqa: E402

START = pd.Timestamp("2022-01-01")
COST_BP_PER_FILL = {"SOXL": (65.6 - 61.9) / 3.17, "SOXS": (57.7 - 48.1) / 3.36}

INCUMBENT_CAP = 5
CAPS = [4, 5, 6, 7, 8, 9, 10, 12]
UNCAPPED = 20                    # effectively uncapped: max observed is 20
SLEEVES = ("SOXL", "SOXS")

# --- bar thresholds, from V17_TRADE_CAP_TEST.md §6 -------------------------
C2_MAX_EXCESS_PP = 5.0           # same-bar share, marginal vs ordinals 1-5
C3_MIN_RETENTION_RATIO = 0.80    # binding-day retention / non-binding
C4_MAX_MDD_WORSE = 0.02          # absolute, vs cap 5
C5_MAX_BREAKER_RISE_PP = 3.0     # share of ON days ending on the 2-stop breaker
C6_MIN_YEARS = 4
C6_PLATEAU = 0.90


def run(symbol, sessions, fine, dates, cap, resolution="1min"):
    cfg = dataclasses.replace(backtest_config(symbol), max_fills=cap)
    step, fb = (5, fine) if resolution == "1min" else (1, {})
    on, tr = replay_symbol_intrabar(symbol, sessions, step, cfg=cfg,
                                    fill_model="spec", target_delay="fill_bar",
                                    fine_by_date=fb, trade_dates=dates)
    if len(tr):
        tr = tr.sort_values(["date", "entry_bar"]).reset_index(drop=True)
        tr["ordinal"] = tr.groupby("date").cumcount() + 1
        prev = tr.groupby("date")["exit_bar"].shift(1)
        tr["same_bar"] = tr["entry_bar"] == prev
        tr["net_ret"] = tr["ret"] - COST_BP_PER_FILL[symbol] / 1e4
    return on, tr


def net_daily(on, tr, symbol):
    f = (tr.groupby("date").size().reindex(on.index).fillna(0)
         if len(tr) else pd.Series(0.0, index=on.index))
    return on - f * COST_BP_PER_FILL[symbol] / 1e4


def mdd(daily):
    eq = (1.0 + daily.sort_index()).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def breaker_share(on, tr):
    """Share of ON days that terminate on the 2-stop breaker."""
    if not len(tr):
        return 0.0
    stops = tr[tr.outcome == "stop"].groupby("date").size()
    return float((stops >= MAX_STOPS).reindex(on.index).fillna(False).mean())


# ------------------------------------------------------------------- T1
def t1_marginal_profile(symbol, one, five, n_on):
    rows = []
    for n in range(1, 13):
        a = one[one.ordinal == n]
        b = five[five.ordinal == n]
        if not len(a):
            continue
        rows.append(dict(
            ordinal=n, trades=len(a),
            mean_net_bp=a.net_ret.mean() * 1e4,
            win_rate=float((a.ret > 0).mean()),
            contrib_bp=a.net_ret.sum() / n_on * 1e4,
            same_bar_pct=(a.loc[a.same_bar, "ret"].sum() / a.ret.sum() * 100
                          if a.ret.sum() else np.nan),
            five_contrib_bp=(b.net_ret.sum() / n_on * 1e4) if len(b) else np.nan,
        ))
    df = pd.DataFrame(rows)
    df["retention"] = df.contrib_bp / df.five_contrib_bp
    return df


# ------------------------------------------------------------------- T2
def t2_binding_days(symbol, one_on, one_tr, five_on, five_tr, cap=INCUMBENT_CAP):
    """Retention on days where the cap binds vs days where it does not."""
    fills = one_tr.groupby("date").size().reindex(one_on.index).fillna(0)
    binding = fills > cap
    out = {}
    for lbl, mask in (("binding", binding), ("non-binding", ~binding)):
        o = one_on[mask].sum()
        f = five_on[mask.reindex(five_on.index).fillna(False)].sum()
        sub = one_tr[one_tr.date.isin(one_on.index[mask])]
        out[lbl] = dict(
            days=int(mask.sum()),
            one_bp=(one_on[mask].mean() * 1e4) if mask.sum() else np.nan,
            five_bp=(five_on[mask.reindex(five_on.index).fillna(False)].mean() * 1e4)
            if mask.sum() else np.nan,
            retention=(o / f) if f else np.nan,
            same_bar_pct=(sub.loc[sub.same_bar, "ret"].sum() / sub.ret.sum() * 100
                          if len(sub) and sub.ret.sum() else np.nan),
        )
    return out, binding


# ------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="V17 trade-cap test")
    ap.add_argument("--out", default=os.path.join(_HERE, "out"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    data, t1, t2, sweep = {}, {}, {}, {}
    for symbol in SLEEVES:
        fine = dict(load_1min_sessions(symbol, ROOT))
        sessions = load_sessions(symbol, ROOT)
        dates = {d for d, _ in sessions} & set(fine)
        dates = {d for d in dates if d >= START}
        data[symbol] = (sessions, fine, dates)

        one_on, one_tr = run(symbol, sessions, fine, dates, UNCAPPED, "1min")
        five_on, five_tr = run(symbol, sessions, fine, dates, UNCAPPED, "5min")
        t1[symbol] = t1_marginal_profile(symbol, one_tr, five_tr, len(one_on))
        t2[symbol] = t2_binding_days(symbol, one_on, one_tr, five_on, five_tr)

        rows = {}
        for cap in CAPS:
            on, tr = run(symbol, sessions, fine, dates, cap, "1min")
            nd = net_daily(on, tr, symbol)
            rows[cap] = dict(daily=nd, net_bp=nd.mean() * 1e4, mdd=mdd(nd),
                             trades=len(tr), fills_per_day=len(tr) / len(on),
                             breaker=breaker_share(on, tr),
                             same_bar=(tr.loc[tr.same_bar, "ret"].sum()
                                       / on.sum() * 100) if on.sum() else np.nan)
        sweep[symbol] = rows

    # ------------------------------------------------------------- report
    print("=" * 94)
    print("V17 — TRADE CAP (V7), TESTED AT THE MARGIN.  1-minute fills, net of costs, 2022+")
    print("=" * 94)

    print("\n" + "-" * 94)
    print("T1 — MARGINAL TRADE PROFILE (uncapped).  Is the Nth trade worth taking?")
    print("-" * 94)
    for symbol in SLEEVES:
        d = t1[symbol]
        base = d[d.ordinal <= 5]
        base_sb = (base.same_bar_pct * base.contrib_bp).sum() / base.contrib_bp.sum()
        print(f"\n{symbol}   (ordinals 1-5 weighted same-bar share = {base_sb:.0f}%)")
        print(f"  {'ord':>4}{'trades':>8}{'mean net bp':>13}{'win rate':>10}"
              f"{'contrib bp':>12}{'same-bar':>10}{'retention':>11}")
        for _, r in d.iterrows():
            flag = "  <- marginal" if r.ordinal > INCUMBENT_CAP else ""
            print(f"  {int(r.ordinal):>4}{int(r.trades):>8}{r.mean_net_bp:>13.1f}"
                  f"{r.win_rate:>10.1%}{r.contrib_bp:>12.2f}{r.same_bar_pct:>9.0f}%"
                  f"{r.retention:>11.0%}{flag}")

    print("\n" + "-" * 94)
    print("T2 — ARE CAP-BINDING DAYS THE LOW-TRUST DAYS?  (C3, the veto)")
    print("-" * 94)
    for symbol in SLEEVES:
        g, _ = t2[symbol]
        print(f"\n{symbol}")
        print(f"  {'day type':<14}{'days':>7}{'5-min bp':>11}{'1-min bp':>11}"
              f"{'retention':>11}{'same-bar':>10}")
        for lbl in ("binding", "non-binding"):
            r = g[lbl]
            print(f"  {lbl:<14}{r['days']:>7}{r['five_bp']:>11.1f}{r['one_bp']:>11.1f}"
                  f"{r['retention']:>11.0%}{r['same_bar_pct']:>9.0f}%")
        ratio = g["binding"]["retention"] / g["non-binding"]["retention"]
        print(f"  -> retention ratio binding/non-binding = {ratio:.2f}"
              f"   (C3 needs >= {C3_MIN_RETENTION_RATIO:.2f})"
              f"  {'PASS' if ratio >= C3_MIN_RETENTION_RATIO else 'FAIL'}")

    print("\n" + "-" * 94)
    print("T3 — CAP SWEEP, with the 2-stop-breaker interaction")
    print("-" * 94)
    for symbol in SLEEVES:
        s = sweep[symbol]
        inc = s[INCUMBENT_CAP]
        print(f"\n{symbol}   (incumbent cap {INCUMBENT_CAP}: {inc['net_bp']:.1f} bp, "
              f"MaxDD {inc['mdd']:.1%}, breaker {inc['breaker']:.1%})")
        print(f"  {'cap':>5}{'net bp':>9}{'vs inc':>9}{'MaxDD':>9}{'dMaxDD':>9}"
              f"{'fills/d':>9}{'same-bar':>10}{'breaker':>10}{'dbreaker':>10}")
        for cap in CAPS:
            r = s[cap]
            print(f"  {cap:>5}{r['net_bp']:>9.1f}{r['net_bp']-inc['net_bp']:>+9.1f}"
                  f"{r['mdd']:>9.1%}{(r['mdd']-inc['mdd'])*100:>+8.1f}p"
                  f"{r['fills_per_day']:>9.2f}{r['same_bar']:>9.0f}%"
                  f"{r['breaker']:>10.1%}{(r['breaker']-inc['breaker'])*100:>+9.1f}p")

    print("\n" + "-" * 94)
    print("T4 — PER-YEAR SIGN TEST vs cap 5 (selection-based walk-forward is not")
    print("     protective on this dataset — V16 R4.2)")
    print("-" * 94)
    years_won = {}
    for symbol in SLEEVES:
        s = sweep[symbol]
        base = s[INCUMBENT_CAP]["daily"]
        base.index = pd.DatetimeIndex(base.index)
        yrs = sorted({d.year for d in base.index})
        print(f"\n{symbol}")
        print(f"  {'cap':>5}" + "".join(f"{y:>10}" for y in yrs) + f"{'wins':>7}")
        for cap in CAPS:
            if cap == INCUMBENT_CAP:
                continue
            d = s[cap]["daily"]; d.index = pd.DatetimeIndex(d.index)
            cells, w = [], 0
            for y in yrs:
                diff = (d[d.index.year == y].mean() - base[base.index.year == y].mean()) * 1e4
                cells.append(f"{diff:>+10.1f}")
                w += diff > 0
            years_won[(symbol, cap)] = w
            print(f"  {cap:>5}" + "".join(cells) + f"{w:>5}/{len(yrs)}")

    # ------------------------------------------------------ adoption bar
    print("\n" + "=" * 94)
    print("ADOPTION BAR — the six criteria fixed in V17_TRADE_CAP_TEST.md §6")
    print("=" * 94)
    adopted = {}
    for symbol in SLEEVES:
        d, s = t1[symbol], sweep[symbol]
        inc = s[INCUMBENT_CAP]
        g, _ = t2[symbol]
        base = d[d.ordinal <= 5]
        base_sb = (base.same_bar_pct * base.contrib_bp).sum() / base.contrib_bp.sum()
        c3_ratio = g["binding"]["retention"] / g["non-binding"]["retention"]
        c3 = c3_ratio >= C3_MIN_RETENTION_RATIO
        print(f"\n{symbol}")
        best = None
        for cap in CAPS:
            if cap <= INCUMBENT_CAP:
                continue
            marg = d[(d.ordinal > INCUMBENT_CAP) & (d.ordinal <= cap)]
            c1 = bool(len(marg)) and bool((marg.mean_net_bp > 0).all())
            msb = ((marg.same_bar_pct * marg.contrib_bp).sum() / marg.contrib_bp.sum()
                   if marg.contrib_bp.sum() else np.nan)
            c2 = bool(msb <= base_sb + C2_MAX_EXCESS_PP)
            c4 = bool(s[cap]["mdd"] >= inc["mdd"] - C4_MAX_MDD_WORSE)
            c5 = bool((s[cap]["breaker"] - inc["breaker"]) * 100 <= C5_MAX_BREAKER_RISE_PP)
            c6_years = years_won[(symbol, cap)] >= C6_MIN_YEARS
            interior = cap != CAPS[-1]
            nb = [s[c]["net_bp"] for c in (cap - 1, cap + 1) if c in s]
            c6_plat = bool(nb) and (np.mean(nb) / s[cap]["net_bp"] >= C6_PLATEAU
                                    if s[cap]["net_bp"] > 0 else False)
            c6 = c6_years and interior and c6_plat
            ok = c1 and c2 and c3 and c4 and c5 and c6
            print(f"  cap {cap:>2}: C1 {'ok ' if c1 else 'FAIL'} | C2 {'ok ' if c2 else 'FAIL'}"
                  f" (marg {msb:>4.0f}% vs base {base_sb:.0f}%) | C3 {'ok ' if c3 else 'FAIL'}"
                  f" ({c3_ratio:.2f}) | C4 {'ok ' if c4 else 'FAIL'}"
                  f" ({s[cap]['mdd']:.1%}) | C5 {'ok ' if c5 else 'FAIL'}"
                  f" ({(s[cap]['breaker']-inc['breaker'])*100:+.1f}p) |"
                  f" C6 {'ok ' if c6 else 'FAIL'} ({years_won[(symbol,cap)]}/5"
                  f"{', boundary' if not interior else ''})"
                  f"  => {'ADOPT' if ok else 'reject'}")
            if ok and (best is None or s[cap]["net_bp"] > s[best]["net_bp"]):
                best = cap
        adopted[symbol] = best
        print(f"  -> {symbol}: " + (f"cap {best} clears all six "
              f"({s[best]['net_bp']:.1f} bp vs {inc['net_bp']:.1f}, "
              f"{s[best]['net_bp']-inc['net_bp']:+.1f})" if best else
              "NO cap clears the bar — V7 stays at 5"))

    print("\n" + "=" * 94)
    if not any(adopted.values()):
        print("VERDICT: NOT ADOPTED in either sleeve. Per §6 the stopping rule applies —")
        print("V7 closes for this dataset until sub-minute or live fills exist.")
    else:
        print(f"VERDICT: {adopted}")
    print("=" * 94)

    # persist
    for symbol in SLEEVES:
        t1[symbol].to_csv(os.path.join(args.out, f"v17_ordinals_{symbol}.csv"), index=False)
        pd.DataFrame({c: {k: v for k, v in r.items() if k != "daily"}
                      for c, r in sweep[symbol].items()}).T.to_csv(
            os.path.join(args.out, f"v17_capsweep_{symbol}.csv"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
