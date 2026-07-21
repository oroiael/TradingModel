#!/usr/bin/env python3
"""
run_analysis.py  --  the full study for the SOXL bear-call-spread question.

Produces, from the data only:
  1. a parameter SWEEP over tenor x short-strike rule x width -> scoreboard,
     ranked by sizing-independent expectancy (mean return per $ risked). This is
     the honest search for "any strike that works", not a single cherry pick.
  2. the three headline tenors (weekly / two-week / monthly) at the user's
     literal structure (short = 1st OTM strike, long = 1 strike up), with:
        - by-year / by-regime breakdown
        - the "invest 100% of capital" equity path -> when it is ruined
        - a survivable fractional-sizing path -> drawdown structure
  3. drawdown attribution: losses vs the SOXL move that caused them.
  4. a fill-model sensitivity (20% spread rule vs midpoint).

Outputs: outputs/scoreboard.csv, outputs/ledger_*.csv, outputs/*.png, and a
printed report.
"""

from __future__ import annotations
import itertools
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

from data_loader import load_options
from backtest import SpreadConfig, build_day_index, run_backtest
from capital_models import (full_risk_curve, fractional_curve, curve_stats,
                            expectancy_stats)

OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(exist_ok=True)
CAP0 = 100_000.0
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)


def hr(t):
    print("\n" + "=" * 82 + f"\n{t}\n" + "=" * 82)


def by_year(led):
    g = led.groupby("year").agg(
        trades=("win", "size"),
        win=("win", "mean"),
        breach=("breach", "mean"),
        maxloss=("max_loss_hit", "mean"),
        mean_ror=("ror", "mean"),
        total_ror=("ror", "sum"),
        soxl_move=("move_pct", "mean"),
    )
    return g.round(3)


def main():
    hr("LOADING (whole-number strikes enforced)")
    opt = load_options(whole_strikes_only=True, verbose=True)
    idx = build_day_index(opt)   # pay the grouping cost once
    print(f"day index built: {len(idx[2])} trade dates")

    # ------------------------------------------------------------------ SWEEP
    hr("1.  PARAMETER SWEEP  (find any config with positive expectancy)")
    tenors = [("weekly", 7, 4), ("two_week", 14, 4), ("monthly", 30, 6)]
    short_rules = (
        [("otm_step", dict(short_rule="otm_step", short_otm_step=k)) for k in (1, 2, 3)] +
        [("delta", dict(short_rule="delta", short_delta=d))
         for d in (0.10, 0.15, 0.20, 0.30, 0.40)]
    )
    widths = [1, 2, 3, 5]

    recs = []
    ledgers = {}
    for (tname, dte, tol), (sname, skw), w in itertools.product(tenors, short_rules, widths):
        cfg = SpreadConfig(target_dte=dte, dte_tol=tol, width_steps=w,
                           fill="spread20", **skw)
        led = run_backtest(opt, cfg, prebuilt=idx)
        if len(led) < 10:
            continue
        e = expectancy_stats(led)
        frac_eq = fractional_curve(led, CAP0, risk_frac=0.10)
        fr_eq, ruined, ruin_idx = full_risk_curve(led, CAP0)
        cs = curve_stats(led, frac_eq, CAP0)
        key = (tname, sname, str(skw.get("short_otm_step", skw.get("short_delta"))), w)
        ledgers[key] = led
        recs.append(dict(
            tenor=tname, short_rule=sname,
            short_param=skw.get("short_otm_step", skw.get("short_delta")),
            width=w, **e,
            frac10_end=cs["end_equity"], frac10_cagr=cs["cagr"],
            frac10_maxdd=cs["max_drawdown"],
            full_risk_ruined=ruined,
            full_risk_ruin_trade=(ruin_idx + 1) if ruined else None,
        ))
    sb = pd.DataFrame(recs).sort_values("mean_ror", ascending=False).reset_index(drop=True)
    sb.to_csv(OUT / "scoreboard.csv", index=False)
    show = ["tenor", "short_rule", "short_param", "width", "trades", "win_rate",
            "maxloss_rate", "avg_credit_pct_width", "mean_ror", "total_ror",
            "frac10_end", "frac10_maxdd", "full_risk_ruined", "full_risk_ruin_trade"]
    print(f"\nconfigs tested: {len(sb)}   (ranked by mean return per $ risked)")
    print("\nTOP 12 by expectancy:")
    print(sb[show].head(12).to_string(index=False))
    print("\nBOTTOM 6 by expectancy:")
    print(sb[show].tail(6).to_string(index=False))
    pos = sb[sb["mean_ror"] > 0]
    print(f"\nconfigs with POSITIVE expectancy (mean_ror>0): {len(pos)} of {len(sb)}")
    print(f"configs NOT ruined under 100% sizing: "
          f"{(~sb['full_risk_ruined']).sum()} of {len(sb)}")

    # -------------------------------------------------- HEADLINE STRUCTURE
    hr("2.  HEADLINE: user's literal structure (short=1st OTM, long=+1 strike)")
    headline = {}
    for tname, dte, tol in tenors:
        cfg = SpreadConfig(target_dte=dte, dte_tol=tol, short_rule="otm_step",
                           short_otm_step=1, width_steps=1, fill="spread20")
        led = run_backtest(opt, cfg, prebuilt=idx)
        headline[tname] = led
        led.to_csv(OUT / f"ledger_{tname}_1otm_w1.csv", index=False)
        e = expectancy_stats(led)
        fr_eq, ruined, ruin_idx = full_risk_curve(led, CAP0)
        print(f"\n--- {tname.upper()} ---  trades={e['trades']} "
              f"win={e['win_rate']:.1%} breach={e['breach_rate']:.1%} "
              f"maxloss={e['maxloss_rate']:.1%} credit/width={e['avg_credit_pct_width']:.1%}")
        print(f"    mean RoR/trade={e['mean_ror']:+.1%}  worst trade RoR={e['worst_ror']:+.0%}")
        if ruined:
            r = led.iloc[ruin_idx]
            print(f"    INVEST-100%: FUNCTIONALLY RUINED on trade #{ruin_idx+1} "
                  f"({r['entry_date']}: SOXL {r['spot_entry']:.1f}->{r['S_exp']:.1f} "
                  f"= {r['move_pct']:+.0%}, spread maxed out). "
                  f"End equity ${fr_eq[-1]:,.0f} (−{1-fr_eq[-1]/CAP0:.2%}).")
        else:
            print(f"    INVEST-100%: survived, end equity ${fr_eq[-1]:,.0f}")
        print("    by year/regime:")
        print(by_year(led).to_string().replace("\n", "\n      "))

    # -------------------------------------------------- DRAWDOWN ATTRIBUTION
    hr("3.  DRAWDOWN ATTRIBUTION  (how & why losses happen) -- weekly ledger")
    w = headline["weekly"]
    print("per-trade RoR grouped by the SOXL move over the hold:")
    bins = [-1, -0.10, -0.03, 0.03, 0.10, 1e9]
    labels = ["SOXL<-10%", "-10..-3%", "flat +/-3%", "+3..+10%", "SOXL>+10%"]
    w = w.assign(move_bucket=pd.cut(w["move_pct"], bins=bins, labels=labels))
    tab = w.groupby("move_bucket", observed=True).agg(
        trades=("ror", "size"), share=("ror", lambda s: len(s) / len(w)),
        mean_ror=("ror", "mean"), total_ror=("ror", "sum"),
        maxloss_rate=("max_loss_hit", "mean")).round(3)
    print(tab.to_string())
    up = w[w["move_pct"] > 0.03]
    print(f"\nOf all lost risk (sum of negative RoR), the share coming from SOXL "
          f"up-moves >+3%: "
          f"{w.loc[w['move_pct']>0.03,'ror'].clip(upper=0).sum() / w['ror'].clip(upper=0).sum():.0%}")

    # -------------------------------------------------- FILL SENSITIVITY
    hr("4.  FILL-MODEL SENSITIVITY  (20% spread rule vs midpoint) -- weekly")
    for fill in ("spread20", "mid"):
        cfg = SpreadConfig(target_dte=7, dte_tol=4, short_rule="otm_step",
                           short_otm_step=1, width_steps=1, fill=fill)
        led = run_backtest(opt, cfg, prebuilt=idx)
        e = expectancy_stats(led)
        print(f"  fill={fill:9s}: credit/width={e['avg_credit_pct_width']:.1%} "
              f"win={e['win_rate']:.1%} mean_ror={e['mean_ror']:+.1%} "
              f"total_ror={e['total_ror']:+.1f}")

    # -------------------------------------------------- PLOTS
    _plots(headline, sb, ledgers)
    print(f"\nsaved plots + scoreboard.csv + ledgers to {OUT}")


def _plots(headline, sb, ledgers):
    # equity curves (fractional 10%) for the three tenors + full-risk overlay
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for tname, led in headline.items():
        eq = fractional_curve(led, CAP0, 0.10)
        x = pd.to_datetime(led["entry_date"])
        axes[0].plot(x, eq, label=f"{tname} (risk 10%/trade)")
    axes[0].axhline(CAP0, color="k", lw=0.6, ls="--")
    axes[0].set_title("Fractional sizing (risk 10%/trade) — survivable view")
    axes[0].set_ylabel("equity ($)"); axes[0].legend(); axes[0].set_yscale("log")

    # full-risk on weekly
    fr, ruined, ridx = full_risk_curve(headline["weekly"], CAP0)
    x = pd.to_datetime(headline["weekly"]["entry_date"])
    axes[1].plot(x, fr, color="crimson")
    axes[1].axhline(CAP0, color="k", lw=0.6, ls="--")
    if ruined:
        axes[1].scatter([x.iloc[ridx]], [fr[ridx]], color="black", zorder=5)
        axes[1].annotate(f"functional ruin\ntrade #{ridx+1}  {x.iloc[ridx].date()}",
                         (x.iloc[ridx], fr[ridx]), textcoords="offset points",
                         xytext=(10, 40), fontsize=9)
    axes[1].set_title("Invest 100% of capital (weekly) — max-loss sizing")
    axes[1].set_ylabel("equity ($)"); axes[1].set_yscale("log")
    fig.tight_layout(); fig.savefig(OUT / "equity_curves.png", dpi=110)

    # scoreboard heat: mean_ror by tenor x short_param for width=1
    fig2, ax2 = plt.subplots(figsize=(9, 4))
    piv = (sb[sb["width"] == 1]
           .pivot_table(index="tenor", columns=["short_rule", "short_param"],
                        values="mean_ror"))
    im = ax2.imshow(piv.values, cmap="RdYlGn", vmin=-0.4, vmax=0.4, aspect="auto")
    ax2.set_xticks(range(len(piv.columns)))
    ax2.set_xticklabels([f"{a}\n{b}" for a, b in piv.columns], fontsize=7)
    ax2.set_yticks(range(len(piv.index))); ax2.set_yticklabels(piv.index)
    ax2.set_title("mean return per $ risked (width=1 strike) — green=edge, red=bleed")
    fig2.colorbar(im, ax=ax2)
    fig2.tight_layout(); fig2.savefig(OUT / "expectancy_heatmap.png", dpi=110)


if __name__ == "__main__":
    main()
