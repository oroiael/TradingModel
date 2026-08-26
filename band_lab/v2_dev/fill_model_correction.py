"""
V20 — §8's baselines under a fill model that cannot buy back below its own exit.

See V20_FILL_MODEL_CORRECTION.md. The bar in §6 of that document was written and
committed before this script was run.

`spec` prices a same-bar re-entry at `min(limit, bar.open)` — a price that traded
before the exit did. Live says that trade is not available: over 13 sleeve-
sessions the backtest booked ten same-bar re-entries the live engine never got,
and 9 of live's 14 actual re-entries came in at or worse than the price just
sold. This recomputes every published number under `no_better` (a re-entry may
not be priced better than the exit it followed) and `next_bar` (no same-bar
re-entry at all), which bracket the truth.

    python3 band_lab/v2_dev/fill_model_correction.py
"""

from __future__ import annotations

import argparse
import dataclasses
import math
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

from intrabar import load_1min_sessions, replay_symbol_intrabar   # noqa: E402
from replay import backtest_config, load_sessions                 # noqa: E402

START = pd.Timestamp("2022-01-01")

#: Per-fill cost, from the published gross-to-net difference. Held fixed across
#: models: the correction is to fill *price*, not to what a fill costs.
COST_BP_PER_FILL = {"SOXL": (65.6 - 61.9) / 3.17, "SOXS": (57.7 - 48.1) / 3.36}

SLEEVES = ("SOXL", "SOXS")
MODELS = ("spec", "no_better", "next_bar")

#: §8 incumbents, from phase1/out/monitoring_expectations.csv.
PUBLISHED = {
    "SOXL": dict(fills=3.17, on_rate=52.1, target=71.3, stop=9.9, flatten=18.8,
                 gross=65.6, net=61.9),
    "SOXS": dict(fills=3.36, on_rate=53.1, target=71.8, stop=9.3, flatten=18.9,
                 gross=57.7, net=48.1),
}

#: B6 — below this, same-bar re-entries are too rare to explain the live gap and
#: the §2 diagnosis is refuted rather than merely unsupported.
B6_MIN_TRADE_COUNT_CHANGE = 0.05

W = 0.50                    # §12 sleeve weight, for the account-level roll-up


def run(symbol, sessions, fine, dates, model):
    cfg = dataclasses.replace(backtest_config(symbol))
    on, tr = replay_symbol_intrabar(symbol, sessions, 5, cfg=cfg,
                                    fill_model=model, target_delay="fill_bar",
                                    fine_by_date=fine, trade_dates=dates)
    fills = (tr.groupby("date").size().reindex(on.index).fillna(0)
             if len(tr) else pd.Series(0.0, index=on.index))
    net = on - fills * COST_BP_PER_FILL[symbol] / 1e4
    return on, tr, net


def summarise(symbol, on, tr, net, n_calendar):
    oc = tr.outcome.value_counts(normalize=True) if len(tr) else {}
    return dict(
        trades=len(tr),
        fills=len(tr) / len(on) if len(on) else float("nan"),
        on_rate=100.0 * len(on) / n_calendar,
        target=100.0 * oc.get("target", 0.0),
        stop=100.0 * oc.get("stop", 0.0),
        flatten=100.0 * oc.get("flatten", 0.0),
        gross=on.mean() * 1e4,
        net=net.mean() * 1e4,
        sd=net.std(ddof=1) * 1e4,
        worst=net.min() * 100.0,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="V20 fill-model correction")
    ap.add_argument("--out", default=os.path.join(_HERE, "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    data, res, nets = {}, {}, {}
    calendar = set()
    for s in SLEEVES:
        fine = dict(load_1min_sessions(s, ROOT))
        sessions = load_sessions(s, ROOT)
        dates = {d for d, _ in sessions} & set(fine)
        dates = {d for d in dates if d >= START}
        data[s] = (sessions, fine, dates)
        calendar |= dates
    n_cal = len(calendar)

    for s in SLEEVES:
        sessions, fine, dates = data[s]
        for m in MODELS:
            on, tr, net = run(s, sessions, fine, dates, m)
            res[(s, m)] = summarise(s, on, tr, net, n_cal)
            nets[(s, m)] = net

    w = 96
    print("=" * w)
    print("V20 — §8 BASELINES UNDER AN HONEST SAME-BAR RE-ENTRY.  "
          "1-min fills, net of costs, 2022+")
    print("=" * w)

    print("\n  Four columns, and mixing them up conflates two separate corrections.")
    print("  §8 was published at 5-MINUTE fill resolution. The S10 haircut already")
    print("  moved it to 1-minute. `spec@1min` is that post-haircut incumbent, and it")
    print("  is what `no_better` must be measured against — NOT the 5-minute headline.")
    for s in SLEEVES:
        p = PUBLISHED[s]
        print(f"\n{s} " + "-" * (w - len(s) - 1))
        print(f"  {'metric':<22}{'§8 pub(5m)':>12}{'spec@1min':>12}"
              f"{'no_better':>12}{'next_bar':>12}{'  nb vs spec@1m':>18}")
        for key, label, pub in (("fills", "fills_per_ON_day", p["fills"]),
                                ("on_rate", "ON_day_rate_%", p["on_rate"]),
                                ("target", "target_%", p["target"]),
                                ("stop", "stop_%", p["stop"]),
                                ("flatten", "flatten_%", p["flatten"]),
                                ("gross", "gross_bp_per_ON_day", p["gross"]),
                                ("net", "net_bp_per_ON_day", p["net"])):
            sp = res[(s, "spec")][key]
            nb, nx = res[(s, "no_better")][key], res[(s, "next_bar")][key]
            dev = (nb - sp) / abs(sp) * 100.0 if sp else float("nan")
            note = ""
            if key == "on_rate":
                note = "  <- denominator differs from §8; not comparable"
            print(f"  {label:<22}{pub:>12.2f}{sp:>12.2f}{nb:>12.2f}{nx:>12.2f}"
                  f"{dev:>17.1f}%{note}")
        print(f"  {'trades':<22}{'--':>12}{res[(s,'spec')]['trades']:>12d}"
              f"{res[(s,'no_better')]['trades']:>12d}"
              f"{res[(s,'next_bar')]['trades']:>12d}")

    # ------------------------------------------------------------- B6 first
    print("\n" + "=" * w)
    print("B6 — IS THE DIAGNOSIS REFUTED?  (checked before anything is concluded)")
    print("=" * w)
    refuted = True
    for s in SLEEVES:
        a_, b_ = res[(s, "spec")]["trades"], res[(s, "no_better")]["trades"]
        chg = abs(b_ - a_) / a_
        ok = chg >= B6_MIN_TRADE_COUNT_CHANGE
        refuted &= not ok
        print(f"  {s}: spec {a_} trades -> no_better {b_}  "
              f"({chg:+.1%})  threshold {B6_MIN_TRADE_COUNT_CHANGE:.0%}  "
              f"{'material' if ok else 'BELOW THRESHOLD'}")
    print(f"\n  -> V20 {'IS REFUTED — see B6' if refuted else 'is not refuted'}")

    # ----------------------------------------------- account roll-up and B2-B4
    print("\n" + "=" * w)
    print("ACCOUNT LEVEL (w=0.5 each), and the standard error on each estimate")
    print("=" * w)
    cal = pd.DatetimeIndex(sorted(calendar))
    for m in MODELS:
        acct = sum(W * nets[(s, m)].reindex(cal).fillna(0.0) for s in SLEEVES)
        act = acct[(nets[("SOXL", m)].reindex(cal).notna()
                    | nets[("SOXS", m)].reindex(cal).notna())]
        mean, sd = act.mean() * 1e4, act.std(ddof=1) * 1e4
        sem = sd / math.sqrt(len(act))
        horizon = (1.96 * sd / mean) ** 2 if mean > 0 else float("inf")
        print(f"\n  {m}:")
        print(f"    per active day  mean {mean:+7.2f} bp   sd {sd:6.2f}   "
              f"sem {sem:5.2f}   n {len(act)}")
        print(f"    95% CI on the mean  [{mean-1.96*sem:+.2f}, {mean+1.96*sem:+.2f}] bp")
        for s in SLEEVES:
            x = nets[(s, m)].dropna()
            xm, xs = x.mean() * 1e4, x.std(ddof=1) * 1e4
            xsem = xs / math.sqrt(len(x))
            print(f"    {s} net {xm:+7.2f} bp/ON-day  sem {xsem:5.2f}  "
                  f"95% CI [{xm-1.96*xsem:+.2f}, {xm+1.96*xsem:+.2f}]  "
                  f"{'ZERO INSIDE CI' if xm-1.96*xsem <= 0 <= xm+1.96*xsem else ''}")
        print(f"    B5 detection horizon (95%, two-sided): "
              f"{horizon:,.0f} active days" if mean > 0
              else "    B5 detection horizon: undefined, mean is not positive")

    rows = []
    for s in SLEEVES:
        for m in MODELS:
            rows.append(dict(sleeve=s, fill_model=m, **res[(s, m)]))
    path = os.path.join(a.out, "v20_fill_model_correction.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"\n  wrote {path}")

    # ------------------------------------------------------- B1: publish them
    #
    # NOT written to phase1/out/monitoring_expectations.csv, even though that is
    # the file §8 reads. `parity.py` regenerates that file under `spec` on every
    # run, so a corrected value written there is reverted by the next person who
    # runs the Phase 1 harness — silently, and into the one number the daily
    # report compares live against. `report.py` prefers this file instead and
    # says which one it used.
    #
    # ON_day_rate_% is deliberately absent: the gate is computed from prior
    # sessions and no fill model can move it. Leaving it out keeps §8 reading
    # the incumbent rather than a number this run has no business restating.
    base = []
    for s in SLEEVES:
        r = res[(s, "no_better")]
        for metric, key in (("fills_per_ON_day", "fills"), ("target_%", "target"),
                            ("stop_%", "stop"), ("flatten_%", "flatten"),
                            ("gross_bp_per_ON_day", "gross"),
                            ("net_bp_per_ON_day", "net"), ("worst_day_%", "worst")):
            base.append(dict(sleeve=s, metric=metric, measured=round(r[key], 2),
                             fill_model="no_better",
                             superseded=PUBLISHED[s].get(
                                 {"fills_per_ON_day": "fills", "target_%": "target",
                                  "stop_%": "stop", "flatten_%": "flatten",
                                  "gross_bp_per_ON_day": "gross",
                                  "net_bp_per_ON_day": "net"}.get(metric, ""), "")))
    bpath = os.path.join(a.out, "v20_corrected_baselines.csv")
    pd.DataFrame(base).to_csv(bpath, index=False)
    print(f"  wrote {bpath}   <- §8 reads this in preference to the spec file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
