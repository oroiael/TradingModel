"""
V18 — the volatility gate (V10): cutoff x lookback.

See V18_VOL_GATE_TEST.md. The adoption bar in §7 of that document was written
and committed before this script was run.

The load-bearing decision is the metric (§2): the gate changes the denominator,
so bp/ON-day rises mechanically whenever a tightening drops below-average days.
Everything below is decided on **net bp per CALENDAR day**.

    python3 band_lab/v2_dev/vol_gate_test.py
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
from strategy_core import FeatureHistory, session_stats          # noqa: E402
from spec_constants import ATR_LOOKBACK, GATE_ATR5_MIN, MAX_FILLS  # noqa: E402

START = pd.Timestamp("2022-01-01")
COST_BP_PER_FILL = {"SOXL": (65.6 - 61.9) / 3.17, "SOXS": (57.7 - 48.1) / 3.36}
SLEEVES = ("SOXL", "SOXS")

CUTOFFS = [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]
LOOKBACKS = [3, 5, 10, 20]
INCUMBENT = (GATE_ATR5_MIN, ATR_LOOKBACK)          # (6.0, 5)

# --- §7 thresholds --------------------------------------------------------
D4_MAX_MDD_WORSE = 0.02
D5_MIN_ON_DAYS = 300
D7_MIN_REL = 0.10          # >= 10% improvement ...
D7_MIN_ABS_BP = 2.0        # ... and >= 2 bp per calendar day
D1_MIN_YEARS = 4


def calendar_days(symbol, sessions, dates) -> int:
    """Denominator for the primary metric: every session in the window, not
    only the ones the gate turned on."""
    return len([d for d, _ in sessions if d in dates])


def run_cell(symbol, sessions, fine, dates, cutoff, lookback):
    cfg = dataclasses.replace(backtest_config(symbol), gate_atr5_min=cutoff)
    on, tr = replay_symbol_intrabar(symbol, sessions, 5, cfg=cfg,
                                    fill_model="spec", target_delay="fill_bar",
                                    fine_by_date=fine, trade_dates=dates,
                                    atr_lookback=lookback)
    fills = (tr.groupby("date").size().reindex(on.index).fillna(0)
             if len(tr) else pd.Series(0.0, index=on.index))
    net = on - fills * COST_BP_PER_FILL[symbol] / 1e4
    return net, tr


def metrics(net_on_days, n_calendar, tr):
    """`net_on_days` is indexed by ON day only; OFF days contribute exactly 0."""
    total = float(net_on_days.sum())
    per_cal = total / n_calendar * 1e4 if n_calendar else np.nan
    per_on = float(net_on_days.mean() * 1e4) if len(net_on_days) else np.nan
    eq = (1.0 + net_on_days.sort_index()).cumprod()
    mdd = float((eq / eq.cummax() - 1.0).min()) if len(eq) else np.nan
    yrs = n_calendar / 252.0
    cagr = ((1.0 + total_return(net_on_days)) ** (1 / yrs) - 1) if yrs > 0 else np.nan
    calmar = cagr / abs(mdd) if mdd and mdd < 0 else np.nan
    cohort = float((tr.groupby("date").size() >= MAX_FILLS).mean()) if len(tr) else np.nan
    return dict(on_days=len(net_on_days), calendar=n_calendar,
                per_cal_bp=per_cal, per_on_bp=per_on, mdd=mdd, cagr=cagr,
                calmar=calmar, cap_share=cohort, total=total)


def total_return(net_on_days):
    return float((1.0 + net_on_days.sort_index()).cumprod().iloc[-1] - 1.0) \
        if len(net_on_days) else 0.0


# ------------------------------------------------------------------- T1/T2
def decile_profile(symbol, sessions, fine, dates):
    """T1 + T2: ON-day deciles by ATR5 — net contribution and cohort share."""
    net, tr = run_cell(symbol, sessions, fine, dates, *INCUMBENT)
    hist, atr = FeatureHistory(), {}
    for d, bars in sessions:
        atr[d] = hist.atr5()
        hist.append(session_stats(bars))
    n_cal = calendar_days(symbol, sessions, dates)
    fills = tr.groupby("date").size().reindex(net.index).fillna(0)
    df = pd.DataFrame({"net": net, "atr5": [atr[d] for d in net.index],
                       "fills": fills})
    df["decile"] = pd.qcut(df.atr5, 10, labels=False, duplicates="drop")
    rows = []
    for k, g in df.groupby("decile", observed=True):
        rows.append(dict(decile=int(k) + 1, days=len(g),
                         atr5_lo=g.atr5.min(), atr5_hi=g.atr5.max(),
                         net_bp_per_on=g.net.mean() * 1e4,
                         contrib_bp_per_cal=g.net.sum() / n_cal * 1e4,
                         cap_share=float((g.fills >= MAX_FILLS).mean())))
    return pd.DataFrame(rows), n_cal


def main() -> int:
    ap = argparse.ArgumentParser(description="V18 volatility-gate test")
    ap.add_argument("--out", default=os.path.join(_HERE, "out"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    data, sweep, deciles = {}, {}, {}
    for symbol in SLEEVES:
        fine = dict(load_1min_sessions(symbol, ROOT))
        sessions = load_sessions(symbol, ROOT)
        dates = {d for d, _ in sessions} & set(fine)
        dates = {d for d in dates if d >= START}
        n_cal = calendar_days(symbol, sessions, dates)
        data[symbol] = (sessions, fine, dates, n_cal)
        deciles[symbol] = decile_profile(symbol, sessions, fine, dates)
        rows = {}
        for cutoff in CUTOFFS:
            for lb in LOOKBACKS:
                net, tr = run_cell(symbol, sessions, fine, dates, cutoff, lb)
                m = metrics(net, n_cal, tr)
                m.update(cutoff=cutoff, lookback=lb, daily=net)
                rows[(cutoff, lb)] = m
        sweep[symbol] = rows

    # --------------------------------------------------------------- T1/T2
    print("=" * 96)
    print("V18 — VOLATILITY GATE (V10).  1-minute fills, net of costs, 2022+")
    print("PRIMARY METRIC: net bp per CALENDAR day (§2 — the gate moves the denominator)")
    print("=" * 96)
    print("\n" + "-" * 96)
    print("T1/T2 — ON-day deciles by ATR5 at the incumbent gate (6.0%, 5d)")
    print("        cap_share = fraction reaching the 5-trade cap (the V17 R5 cohort)")
    print("-" * 96)
    for symbol in SLEEVES:
        d, n_cal = deciles[symbol]
        print(f"\n{symbol}   ({n_cal} calendar days in window)")
        print(f"  {'dec':>4}{'days':>6}{'ATR5 range':>18}{'net bp/ON-day':>15}"
              f"{'contrib bp/cal':>16}{'cap share':>11}")
        for _, r in d.iterrows():
            print(f"  {int(r.decile):>4}{int(r.days):>6}"
                  f"{f'{r.atr5_lo:.1f}-{r.atr5_hi:.1f}':>18}"
                  f"{r.net_bp_per_on:>15.1f}{r.contrib_bp_per_cal:>16.2f}"
                  f"{r.cap_share:>11.0%}")

    # ----------------------------------------------------------------- T3
    print("\n" + "-" * 96)
    print("T3 — CUTOFF x LOOKBACK.  Ranked by the PRIMARY metric.")
    print("-" * 96)
    for symbol in SLEEVES:
        s = sweep[symbol]
        inc = s[INCUMBENT]
        print(f"\n{symbol}   incumbent (6.0%, 5d): {inc['per_cal_bp']:.1f} bp/cal-day, "
              f"{inc['per_on_bp']:.1f} bp/ON-day, {inc['on_days']} ON days, "
              f"MaxDD {inc['mdd']:.1%}, Calmar {inc['calmar']:.2f}, "
              f"cap share {inc['cap_share']:.0%}")
        print(f"  {'cutoff':>7}{'lb':>4}{'bp/cal':>9}{'vs inc':>9}{'bp/ON':>8}"
              f"{'ON days':>9}{'MaxDD':>8}{'Calmar':>8}{'cap sh':>8}")
        top = sorted(s.values(), key=lambda r: -r["per_cal_bp"])[:10]
        for r in top:
            mark = "  <- incumbent" if (r["cutoff"], r["lookback"]) == INCUMBENT else ""
            print(f"  {r['cutoff']:>6.1f}%{r['lookback']:>4}{r['per_cal_bp']:>9.1f}"
                  f"{r['per_cal_bp']-inc['per_cal_bp']:>+9.1f}{r['per_on_bp']:>8.1f}"
                  f"{r['on_days']:>9}{r['mdd']:>8.1%}{r['calmar']:>8.2f}"
                  f"{r['cap_share']:>8.0%}{mark}")
        print(f"  {'-- cutoff at the locked 5-day lookback --':<50}")
        for c in CUTOFFS:
            r = s[(c, 5)]
            mark = "  <- locked" if c == GATE_ATR5_MIN else ""
            print(f"  {c:>6.1f}%{5:>4}{r['per_cal_bp']:>9.1f}"
                  f"{r['per_cal_bp']-inc['per_cal_bp']:>+9.1f}{r['per_on_bp']:>8.1f}"
                  f"{r['on_days']:>9}{r['mdd']:>8.1%}{r['calmar']:>8.2f}"
                  f"{r['cap_share']:>8.0%}{mark}")

    # ----------------------------------------------------------------- T4
    print("\n" + "-" * 96)
    print("T4 — PER-YEAR SIGN TEST on bp/calendar day (selection WF is not")
    print("     protective on this dataset — V16 R4.2)")
    print("-" * 96)
    years_won = {}
    for symbol in SLEEVES:
        s, (_, _, _, n_cal) = sweep[symbol], data[symbol]
        base = s[INCUMBENT]["daily"]
        base.index = pd.DatetimeIndex(base.index)
        yrs = sorted({d.year for d in base.index})
        cal_by_year = {y: len([d for d, _ in data[symbol][0]
                               if d in data[symbol][2] and d.year == y]) for y in yrs}
        print(f"\n{symbol}")
        print(f"  {'cutoff/lb':>11}" + "".join(f"{y:>10}" for y in yrs) + f"{'wins':>7}")
        for key in sorted(s, key=lambda k: -s[k]["per_cal_bp"])[:6]:
            d = s[key]["daily"]; d.index = pd.DatetimeIndex(d.index)
            cells, w = [], 0
            for y in yrs:
                a = d[d.index.year == y].sum() / cal_by_year[y] * 1e4
                b = base[base.index.year == y].sum() / cal_by_year[y] * 1e4
                cells.append(f"{a-b:>+10.1f}")
                w += (a - b) > 0
            years_won[(symbol, key)] = w
            print(f"  {f'{key[0]:.1f}%/{key[1]}d':>11}" + "".join(cells) + f"{w:>5}/{len(yrs)}")

    # ----------------------------------------------------------------- T5
    print("\n" + "-" * 96)
    print("T5 — GATE INPUT (diagnostic only, no adoption proposed)")
    print("-" * 96)
    atr_by_symbol = {}
    for symbol in SLEEVES:
        sessions, _, dates, _ = data[symbol]
        hist, atr = FeatureHistory(), {}
        for d, bars in sessions:
            atr[d] = hist.atr5()
            hist.append(session_stats(bars))
        atr_by_symbol[symbol] = atr
    shared = sorted(set(atr_by_symbol["SOXL"]) & set(atr_by_symbol["SOXS"])
                    & data["SOXS"][2])
    own = [atr_by_symbol["SOXS"][d] for d in shared]
    soxl = [atr_by_symbol["SOXL"][d] for d in shared]
    own_on = sum(1 for v in own if np.isfinite(v) and v >= GATE_ATR5_MIN)
    soxl_on = sum(1 for v in soxl if np.isfinite(v) and v >= GATE_ATR5_MIN)
    agree = sum(1 for a, b in zip(own, soxl)
                if (np.isfinite(a) and a >= GATE_ATR5_MIN) ==
                   (np.isfinite(b) and b >= GATE_ATR5_MIN))
    print(f"  SOXS sessions compared: {len(shared)}")
    print(f"  gate ON using SOXS's own ATR5 (as built) : {own_on}")
    print(f"  gate ON using SOXL's ATR5   (as documented): {soxl_on}")
    print(f"  the two agree on {agree} of {len(shared)} sessions "
          f"({agree/len(shared):.0%}); they differ on {len(shared)-agree}")
    print(f"  correlation of the two ATR5 series: "
          f"{np.corrcoef([v for v in own], [v for v in soxl])[0,1]:.3f}"
          if all(np.isfinite(own)) and all(np.isfinite(soxl)) else
          "  correlation: (NaNs present in early sessions)")

    # ----------------------------------------------------- the adoption bar
    print("\n" + "=" * 96)
    print("ADOPTION BAR — the seven criteria fixed in V18_VOL_GATE_TEST.md §7")
    print("=" * 96)
    adopted = {}
    for symbol in SLEEVES:
        s = sweep[symbol]
        inc = s[INCUMBENT]
        dec, n_cal = deciles[symbol]
        print(f"\n{symbol}   incumbent {inc['per_cal_bp']:.1f} bp/cal-day, "
              f"Calmar {inc['calmar']:.2f}, cap share {inc['cap_share']:.0%}")
        best = None
        for key in sorted(s, key=lambda k: -s[k]["per_cal_bp"]):
            if key == INCUMBENT:
                continue
            r = s[key]
            gain = r["per_cal_bp"] - inc["per_cal_bp"]
            d1_win = gain > 0
            d1_years = years_won.get((symbol, key))
            d1 = d1_win and (d1_years is None or d1_years >= D1_MIN_YEARS)
            # D2: bands excluded relative to the incumbent must not be profitable
            removed = dec[(dec.atr5_hi < key[0])] if key[0] > INCUMBENT[0] else None
            d2 = True if removed is None or removed.empty else \
                bool(removed.contrib_bp_per_cal.sum() <= 0)
            d3 = bool(r["cap_share"] > inc["cap_share"])
            d4 = bool(r["calmar"] > inc["calmar"]
                      and r["mdd"] >= inc["mdd"] - D4_MAX_MDD_WORSE)
            d5 = bool(r["on_days"] >= D5_MIN_ON_DAYS)
            nb = [s[k]["per_cal_bp"] for k in _neighbours(key)
                  if k in s]
            interior = (key[0] not in (CUTOFFS[0], CUTOFFS[-1])
                        and key[1] not in (LOOKBACKS[0], LOOKBACKS[-1]))
            d6 = bool(nb) and interior and (np.mean(nb) / r["per_cal_bp"] >= 0.90
                                            if r["per_cal_bp"] > 0 else False)
            d7 = bool(gain >= D7_MIN_ABS_BP
                      and gain / abs(inc["per_cal_bp"]) >= D7_MIN_REL)
            ok = all((d1, d2, d3, d4, d5, d6, d7))
            if key in [k for k in sorted(s, key=lambda k: -s[k]["per_cal_bp"])[:5]]:
                print(f"  {key[0]:.1f}%/{key[1]}d {gain:>+6.1f} bp/cal | "
                      f"D1 {'ok ' if d1 else 'FAIL'}({d1_years}/5) | "
                      f"D2 {'ok ' if d2 else 'FAIL'} | D3 {'ok ' if d3 else 'FAIL'}"
                      f"({r['cap_share']:.0%}) | D4 {'ok ' if d4 else 'FAIL'}"
                      f"(Calmar {r['calmar']:.2f}) | D5 {'ok ' if d5 else 'FAIL'}"
                      f"({r['on_days']}d) | D6 {'ok ' if d6 else 'FAIL'} | "
                      f"D7 {'ok ' if d7 else 'FAIL'} => {'ADOPT' if ok else 'reject'}")
            if ok and (best is None or r["per_cal_bp"] > s[best]["per_cal_bp"]):
                best = key
        adopted[symbol] = best
        print(f"  -> {symbol}: " + (f"ADOPT {best}" if best else
                                    "NO cell clears the bar — V10 stands at 6.0%/5d"))

    print("\n" + "=" * 96)
    if not any(adopted.values()):
        print("VERDICT: NOT ADOPTED in either sleeve. V10's cutoff and lookback")
        print("close for this dataset, per §7.")
    else:
        print(f"VERDICT: {adopted}")
    print("=" * 96)

    for symbol in SLEEVES:
        deciles[symbol][0].to_csv(
            os.path.join(args.out, f"v18_deciles_{symbol}.csv"), index=False)
        pd.DataFrame([{k: v for k, v in r.items() if k != "daily"}
                      for r in sweep[symbol].values()]).to_csv(
            os.path.join(args.out, f"v18_grid_{symbol}.csv"), index=False)
    return 0


def _neighbours(key):
    c, lb = key
    ci, li = CUTOFFS.index(c), LOOKBACKS.index(lb)
    out = []
    for dc in (-1, 0, 1):
        for dl in (-1, 0, 1):
            if dc == dl == 0:
                continue
            i, j = ci + dc, li + dl
            if 0 <= i < len(CUTOFFS) and 0 <= j < len(LOOKBACKS):
                out.append((CUTOFFS[i], LOOKBACKS[j]))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
