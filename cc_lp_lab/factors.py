"""Test the three proposed fixes independently, then every combination.

F1  early assignment   -- American short calls exercised early when the remaining
                          time value drops below the dividend about to be captured
F2  scale-invariant strike -- delta target instead of "two listed strikes"
F3  ratio put          -- hedge fewer than 1 put per lot
"""
import os, sys, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import backtest as bt, data

COST = dict(cost_per_contract=0.65, share_cost=0.005, slip_call=0.055, slip_put=0.019)
pd.set_option("display.width", 240)


def row(label, **kw):
    eq, led, meta = bt.run(**{**COST, **kw})
    s = bt.stats(eq, label); s.update(meta["pnl"])
    s["assigned"] = int((led.act == "CALL_ASSIGNED").sum())
    s["early"] = int((led.act == "CALL_EARLY_ASSIGNED").sum())
    w = led[led.act == "SELL_CALL"]
    s["fresh_otm%"] = w[w.sticky_write == 0].otm_pct.median()
    s["prem%"] = 100 * (w.px / w.spot).median()
    return s


COLS = ["final", "cagr", "maxdd", "sharpe", "shares", "calls", "puts",
        "assigned", "early", "fresh_otm%", "prem%"]
FMT = {"final": "{:,.0f}".format, "cagr": "{:+.2%}".format, "maxdd": "{:.1%}".format,
       "sharpe": "{:.2f}".format, "shares": "{:+,.0f}".format, "calls": "{:+,.0f}".format,
       "puts": "{:+,.0f}".format, "fresh_otm%": "{:.1f}".format, "prem%": "{:.2f}".format}


def show(rows, title):
    print("\n" + "=" * 132); print(title); print("=" * 132)
    print(pd.DataFrame(rows).set_index("label")[COLS].to_string(formatters=FMT))


if __name__ == "__main__":
    base = row("BASELINE  as specified")

    show([base] + [row(f"F1 early-assign thresh {p:.2%} of spot", early_assign_pct=p)
                   for p in (0.001, 0.003, 0.005, 0.010)],
         "F1 -- EARLY ASSIGNMENT ALONE  (short call taken away once time value collapses)")

    f2 = [base]
    f2 += [row(f"F2 fresh strike = {p:.0%} OTM", strike_mode="pct", call_pct=p)
           for p in (0.03, 0.05, 0.08, 0.12)]
    f2 += [row(f"F2 fresh strike = {d:.2f} delta", strike_mode="delta", call_delta=d)
           for d in (0.30, 0.20, 0.15, 0.10)]
    show(f2, "F2 -- SCALE-INVARIANT STRIKE ALONE  (sticky rewrite kept)")

    f3 = [base]
    f3 += [row(f"F3 put ratio {r:.2f}", put_ratio=r) for r in (0.75, 0.50, 0.25)]
    f3 += [row(f"F3 put {n} strikes OTM", n_otm_put=n) for n in (4, 6, 10)]
    f3 += [row("F3 put ratio 0.50 + 6 strikes OTM", put_ratio=0.5, n_otm_put=6)]
    f3 += [row("F3 no put at all", use_put=False)]
    show(f3, "F3 -- RATIO / CHEAPER PUT ALONE")

    # ---- every combination of the three canonical settings ----
    CANON = {"F1": dict(early_assign_pct=0.003),
             "F2": dict(strike_mode="delta", call_delta=0.20),
             "F3": dict(put_ratio=0.5)}
    combo = []
    for k in range(4):
        for pick in itertools.combinations(["F1", "F2", "F3"], k):
            kw = {}
            for p in pick: kw.update(CANON[p])
            combo.append(row("+".join(pick) if pick else "none (baseline)", **kw))
    show(combo, "ALL 8 COMBINATIONS   F1=early assignment 0.3% · F2=0.20-delta strike · F3=0.5 put ratio")
    pd.DataFrame(combo).set_index("label").to_csv(f"{bt.OUT}/factor_combinations.csv")
