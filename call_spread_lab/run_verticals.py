#!/usr/bin/env python3
"""
run_verticals.py  --  test the mirror-image structures the bear-call study pointed to:
  * bull_put   (credit, "put side")
  * bull_call  (debit,  "debit call structure")
  * long_call / long_put (pure long references)
and reconfirm bear_call so the new engine agrees with backtest.py.

Outputs outputs/verticals_scoreboard.csv, per-structure headline ledgers, and a
by-year regime breakdown. The signal / regime-filter work is in run_signals.py.
"""
from __future__ import annotations
import itertools
import numpy as np
import pandas as pd
from pathlib import Path

from data_loader import load_options
from verticals import VConfig, build_index, run
from capital_models import full_risk_curve, fractional_curve, curve_stats

OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(exist_ok=True)
CAP0 = 100_000.0
pd.set_option("display.width", 210); pd.set_option("display.max_columns", 40)


def hr(t): print("\n" + "=" * 84 + f"\n{t}\n" + "=" * 84)


def stats(led):
    L = led
    return dict(trades=len(L), win_rate=float(L["win"].mean()),
                mean_ror=float(L["ror"].mean()), median_ror=float(L["ror"].median()),
                total_ror=float(L["ror"].sum()), worst_ror=float(L["ror"].min()),
                net_pct_width=float(L["net_pct_width"].mean()))


def by_year(led):
    return led.groupby("year").agg(trades=("win", "size"), win=("win", "mean"),
                                   mean_ror=("ror", "mean"), total_ror=("ror", "sum"),
                                   soxl_move=("move_pct", "mean")).round(3)


def main():
    hr("LOAD + cross-check bear_call agreement with backtest.py")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_index(opt)
    led_bc = run(opt, VConfig(structure="bear_call", target_dte=7,
                              primary_otm_step=1, width_steps=1), prebuilt=idx)
    s = stats(led_bc)
    print(f"bear_call weekly 1-OTM w1 (new engine): trades={s['trades']} "
          f"win={s['win_rate']:.1%} mean_ror={s['mean_ror']:+.1%}  "
          f"[backtest.py committed: 207 / 59.4% / -8.1%]")

    hr("1.  SWEEP  bull_put / bull_call / long_call / long_put")
    tenors = [("weekly", 7, 4), ("two_week", 14, 4), ("monthly", 30, 6)]
    grids = {
        "bull_put":  ([("otm_step", dict(primary_rule="otm_step", primary_otm_step=k)) for k in (1, 2, 3)] +
                      [("delta", dict(primary_rule="delta", primary_delta=d)) for d in (0.10, 0.15, 0.20, 0.30)],
                      [1, 2, 3, 5]),
        "bull_call": ([("otm_step", dict(primary_rule="otm_step", primary_otm_step=k)) for k in (0, 1)] +
                      [("delta", dict(primary_rule="delta", primary_delta=d)) for d in (0.40, 0.50, 0.60, 0.70)],
                      [1, 2, 3, 5]),
        "long_call": ([("delta", dict(primary_rule="delta", primary_delta=d)) for d in (0.30, 0.40, 0.50, 0.60)],
                      [1]),  # width ignored for single-leg
        "long_put":  ([("delta", dict(primary_rule="delta", primary_delta=d)) for d in (0.30, 0.40)],
                      [1]),
    }
    recs, ledgers = [], {}
    for stru, (rules, widths) in grids.items():
        for (tname, dte, tol), (rname, rkw), w in itertools.product(tenors, rules, widths):
            cfg = VConfig(structure=stru, target_dte=dte, dte_tol=tol,
                          width_steps=w, fill="spread20", **rkw)
            led = run(opt, cfg, prebuilt=idx)
            if len(led) < 8:
                continue
            st = stats(led)
            fr, ruined, ridx = full_risk_curve(led, CAP0)
            fe = fractional_curve(led, CAP0, 0.10); cs = curve_stats(led, fe, CAP0)
            key = (stru, tname, rname, str(rkw.get("primary_otm_step", rkw.get("primary_delta"))), w)
            ledgers[key] = led
            recs.append(dict(structure=stru, tenor=tname, rule=rname,
                             param=rkw.get("primary_otm_step", rkw.get("primary_delta")),
                             width=w, **st, frac10_end=cs["end_equity"],
                             frac10_maxdd=cs["max_drawdown"],
                             full_ruin_trade=(ridx + 1) if ruined else None))
    sb = pd.DataFrame(recs).sort_values("mean_ror", ascending=False).reset_index(drop=True)
    sb.to_csv(OUT / "verticals_scoreboard.csv", index=False)
    cols = ["structure", "tenor", "rule", "param", "width", "trades", "win_rate",
            "net_pct_width", "mean_ror", "total_ror", "frac10_end", "frac10_maxdd", "full_ruin_trade"]
    print(f"\nconfigs tested: {len(sb)}")
    print("\nTOP 15 by expectancy (mean return per $ risked):")
    print(sb[cols].head(15).to_string(index=False))
    print(f"\nPOSITIVE-expectancy configs: {(sb['mean_ror'] > 0).sum()} of {len(sb)}")
    for stru in grids:
        sub = sb[sb["structure"] == stru]
        pos = (sub["mean_ror"] > 0).sum()
        best = sub.iloc[0] if len(sub) else None
        print(f"   {stru:10s}: {pos:2d}/{len(sub):2d} positive | best mean_ror "
              f"{sub['mean_ror'].max():+.1%} | best frac10_end ${sub['frac10_end'].max():,.0f}")

    hr("2.  HEADLINE by-year regime breakdown (best config per structure)")
    headline = {}
    for stru in grids:
        row = sb[sb["structure"] == stru].iloc[0]
        rkw = ({"primary_rule": "delta", "primary_delta": float(row["param"])}
               if row["rule"] == "delta"
               else {"primary_rule": "otm_step", "primary_otm_step": int(row["param"])})
        dte = {"weekly": 7, "two_week": 14, "monthly": 30}[row["tenor"]]
        tol = 6 if row["tenor"] == "monthly" else 4
        cfg = VConfig(structure=stru, target_dte=dte, dte_tol=tol,
                      width_steps=int(row["width"]), **rkw)
        led = run(opt, cfg, prebuilt=idx)
        headline[stru] = (cfg, led)
        led.to_csv(OUT / f"vled_{stru}_best.csv", index=False)
        fr, ruined, ridx = full_risk_curve(led, CAP0)
        print(f"\n--- {stru.upper()} best: {row['tenor']} {row['rule']}={row['param']} "
              f"width={int(row['width'])} | mean_ror={row['mean_ror']:+.1%} "
              f"win={row['win_rate']:.1%} ---")
        rl = (f"invest-100pct: functional ruin trade #{ridx + 1}, end ${fr[-1]:,.0f}"
              if ruined else f"invest-100pct: end ${fr[-1]:,.0f}")
        print("    " + rl)
        print(by_year(led).to_string().replace("\n", "\n     "))
    return sb, headline


if __name__ == "__main__":
    main()
