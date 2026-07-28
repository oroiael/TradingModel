"""
Sizing-dial verification (2026-07-28) — closes the two gaps the spec's
engine-correction header left open for V11/V8 sizing, and corrects two
errors found in the process.

Gap 1: the per-unit pyramid was only ever validated on the PRE-BUGFIX
engine and the OLD config (10:30 start, plain filter).
Gap 2: the V11 bootstrap (P(-30% DD/yr) = 46%) was computed on the
pre-refinement P&L series.

Corrections made here:
 (a) EXPOSURE MATCHING. The pyramid is not a "half-capital" strategy:
     measured average exposure is 0.483 of equity vs 0.362 for flat
     f=0.5 and 0.724 for flat f=1.0, and it reaches full 1.0 exposure on
     81% of ON days. The honest comparison is against flat sizing at the
     SAME average exposure (f = 0.667), not against flat f=0.5.
 (b) CONSERVATIVE-SCENARIO MODELLING. Multiplying the return series by
     0.83 (the earlier approach) shrinks volatility as well as edge,
     which flatters drawdown statistics. Edge decay and costs reduce the
     MEAN while leaving volatility intact, so the conservative series is
     built as `on - drag`, drag = 0.17*mean + 5bp.

Universe note: "ON day" = gate + filter pass, INCLUDING days where no
entry ever triggered (genuine zero-P&L ON days). Excluding them
overstates bp/ON-day by ~1 bp.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
sys.path.insert(0, HERE)
from one_pct_cycle_lab import load_bars
from put_overlay_test import core_series

OUT = os.path.join(HERE, "out")
D, T, S, START_I, MAXTR, MAXSTOP = .01, .01, .04, 18, 5, 2

def sim_pyramid(o, h, l, c):
    """Per-unit pyramid: up to 2 concurrent units of f/2, second unit 1%
    below the first entry, each with its own +1%/-4% bracket; breaker
    counts unit-stops. Returns (pnl, mean_exposure, peak_exposure)."""
    roll_hi = h[:START_I].max()
    units = []; trades = 0; stops = 0; pnl = 0.0; expo = []
    for i in range(START_I, len(c)):
        keep = []
        for e, ei in units:
            tgt = e * (1 + T); stp = e * (1 - S)
            if l[i] <= stp:
                px = o[i] if o[i] < stp else stp
                pnl += 0.5 * (px / e - 1); stops += 1
            elif i > ei and h[i] >= tgt:
                px = o[i] if o[i] > tgt else tgt
                pnl += 0.5 * (px / e - 1)
            else:
                keep.append((e, ei))
        units = keep
        if trades < MAXTR and stops < MAXSTOP:
            if not units:
                trig = roll_hi * (1 - D)
                if l[i] <= trig:
                    e = min(trig, o[i]); units = [(e, i)]; trades += 1
                    if l[i] <= e * (1 - S):
                        pnl += 0.5 * (-S); stops += 1; units = []
            elif len(units) == 1:
                t2 = units[0][0] * (1 - D)
                if l[i] <= t2:
                    e = min(t2, o[i]); units.append((e, i)); trades += 1
                    if l[i] <= e * (1 - S):
                        pnl += 0.5 * (-S); stops += 1; units = units[:1]
        expo.append(0.5 * len(units))
        roll_hi = max(roll_hi, h[i])
    for e, ei in units:
        pnl += 0.5 * (c[-1] / e - 1)
    return pnl, float(np.mean(expo)), float(max(expo) if expo else 0)

def flat_exposure(o, h, l, c):
    roll_hi = h[:START_I].max()
    state = 0; entry = 0.0; ei = -1; trades = 0; stops = 0; expo = []
    for i in range(START_I, len(c)):
        if state == 1:
            if l[i] <= entry * (1 - S):
                stops += 1; state = 0
            elif i > ei and h[i] >= entry * (1 + T):
                state = 0
        if state == 0 and trades < MAXTR and stops < MAXSTOP:
            trig = roll_hi * (1 - D)
            if l[i] <= trig:
                entry = min(trig, o[i]); ei = i; state = 1; trades += 1
                if l[i] <= entry * (1 - S):
                    stops += 1; state = 0
        expo.append(float(state))
        roll_hi = max(roll_hi, h[i])
    return float(np.mean(expo))

def stats(ser, calendar_index, label, avg_expo=None):
    fullc = ser.reindex(calendar_index).fillna(0.0)
    eq = (1 + fullc).cumprod(); pk = eq.cummax(); dd = (eq - pk) / pk
    yrs = (calendar_index[-1] - calendar_index[0]).days / 365.25
    sh = ser.mean() / ser.std() * np.sqrt(252) if ser.std() > 0 else 0
    row = {"variant": label, "bp_ON_day": round(ser.mean() * 1e4, 1),
           "sharpe": round(sh, 2), "worst_day_pct": round(ser.min() * 100, 1),
           "cal_cagr_pct": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1),
           "max_dd_pct": round(dd.min() * 100, 1)}
    if avg_expo:
        row["avg_exposure"] = round(avg_expo, 3)
        row["bp_per_unit_expo"] = round(ser.mean() * 1e4 / avg_expo, 1)
    return row

def bootstrap(pool, rng, n=10000, days=252, block=10):
    arr = pool.to_numpy(); out = np.empty((n, days))
    for p in range(n):
        i = 0
        while i < days:
            st = rng.integers(0, len(arr))
            ln = min(rng.geometric(1 / block), days - i)
            out[p, i:i + ln] = np.take(arr, np.arange(st, st + ln), mode="wrap")
            i += ln
    eq = np.cumprod(1 + out, axis=1)
    pk = np.maximum.accumulate(eq, axis=1)
    mdd = ((eq - pk) / pk).min(axis=1); r = eq[:, -1] - 1
    return {"P_dd_lt_30_pct": round((mdd < -.30).mean() * 100, 1),
            "P_dd_lt_20_pct": round((mdd < -.20).mean() * 100, 1),
            "median_dd_pct": round(np.median(mdd) * 100, 1),
            "median_yr_ret_pct": round(np.median(r) * 100, 0),
            "p5_yr_ret_pct": round(np.percentile(r, 5) * 100, 0)}

def main():
    daily, full = core_series()
    d = daily
    onm = ((d["or30"] < d["thr80"]) |
           ((d["or30"] >= d["thr80"]) & (d["pos10"] >= 2/3))) & (d["atr5"] >= 6)
    bars = load_bars(); g = bars.groupby("date")
    pyr, pexpo, ppeak, fexpo = {}, [], [], []
    for dd, gb in g:
        if not onm.get(dd, False) or len(gb) < 20:
            continue
        o, h, l, c = (gb[x].to_numpy() for x in ["Open", "High", "Low", "Close"])
        p, e, m = sim_pyramid(o, h, l, c)
        pyr[dd] = p; pexpo.append(e); ppeak.append(m)
        fexpo.append(flat_exposure(o, h, l, c))
    pyr = pd.Series(pyr).sort_index()
    on = full.reindex(pyr.index).fillna(0.0)      # same ON-day universe
    pe, fe = float(np.mean(pexpo)), float(np.mean(fexpo))

    print("=" * 78)
    print("EXPOSURE PROFILE")
    print("=" * 78)
    print(f"  flat f=1.0 : average exposure {fe:.3f} of equity across trading bars")
    print(f"  flat f=0.5 : average exposure {fe*0.5:.3f}")
    print(f"  pyramid    : average exposure {pe:.3f}, reaches full 1.0 on "
          f"{np.mean(np.array(ppeak) >= 1.0)*100:.0f}% of ON days")
    f_match = pe / fe
    print(f"  => exposure-matched flat equivalent of the pyramid: f = {f_match:.3f}")

    print()
    print("=" * 78)
    print("SIZING TABLE (corrected engine, current locked config, full sample)")
    print("=" * 78)
    rows = [stats(on * 0.5, daily.index, "flat f=0.50", fe * 0.5),
            stats(on * f_match, daily.index,
                  f"flat f={f_match:.2f} (exposure-matched)", pe),
            stats(pyr, daily.index, "pyramid (2 x f/2)", pe),
            stats(on, daily.index, "flat f=1.00", fe)]
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    df.to_csv(os.path.join(OUT, "sizing_verification.csv"), index=False)
    print("\n  VERDICT: flat sizing returns the same bp per unit of average")
    print("  exposure at any f (linear); the pyramid returns materially less,")
    print("  i.e. it is DOMINATED by flat sizing at matched exposure.")

    print()
    print("=" * 78)
    print("BOOTSTRAP (10k simulated 252-ON-day years, 10-day blocks)")
    print("=" * 78)
    drag = 0.17 * on.mean() + 0.0005
    cons = on - drag
    print(f"  conservative model: mean {on.mean()*1e4:.1f} -> {cons.mean()*1e4:.1f} bp "
          f"(drag {drag*1e4:.1f} bp), volatility UNCHANGED "
          f"({cons.std()*100:.2f}% vs {on.std()*100:.2f}%)")
    rng = np.random.default_rng(11)
    brows = []
    for label, pool in [("gross f=1.00", on), ("gross f=0.67", on * f_match),
                        ("gross f=0.50", on * 0.5), ("gross pyramid", pyr),
                        ("conserv f=1.00", cons), ("conserv f=0.67", cons * f_match),
                        ("conserv f=0.50", cons * 0.5)]:
        brows.append({"scenario": label, **bootstrap(pool, rng)})
    bdf = pd.DataFrame(brows)
    print(bdf.to_string(index=False))
    bdf.to_csv(os.path.join(OUT, "sizing_bootstrap.csv"), index=False)
    print("\n  NOTE: the conservative f=1.0 drawdown risk EXCEEDS the gross case")
    print("  (less edge, same volatility). This is the honest planning number.")

if __name__ == "__main__":
    main()
