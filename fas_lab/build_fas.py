"""An active daily FAS strategy, built from the SOXL rules and the vol research.

Step 1 reproduces band_lab's published FAS cells to prove the harness agrees.
Step 2 adds the contribution from vol_anatomy: band_lab scaled the THRESHOLDS
down to FAS's smaller moves, which shrinks the P&L per trade. The alternative is
to leave the percentage rules scaled but LEVER THE POSITION so each move is worth
what a SOXL move is worth. Because the strategy is flat overnight, that leverage
is day-trading buying power and carries no financing cost.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import engine

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
SOXL, FAS = "SOXL_5min_6Years.csv", "FAS_5min_6Years.csv"
pd.set_option("display.width", 220)
COLS = ["on_days", "trades_per_on_day", "bp_per_on_day", "on_sharpe", "sharpe",
        "maxdd", "cagr", "win_rate", "worst_day", "yrs_pos"]
F = {"trades_per_on_day": "{:.2f}".format, "bp_per_on_day": "{:+.1f}".format,
     "on_sharpe": "{:.2f}".format, "sharpe": "{:.2f}".format, "maxdd": "{:.1%}".format,
     "cagr": "{:+.1%}".format, "win_rate": "{:.1%}".format, "worst_day": "{:.1%}".format}


def matched_gate(src=SOXL, dst=FAS, src_gate=6.0):
    """The dst ATR5 level admitting the same fraction of days as src_gate on src."""
    a = engine.daily_stats(engine.load_5min(src)).atr5.dropna()
    b = engine.daily_stats(engine.load_5min(dst)).atr5.dropna()
    return float(b.quantile((a < src_gate).mean()))


def row(label, sym, **kw):
    d, t = engine.run(sym, **kw)
    s = engine.stats(d, t, label)
    return s, d


def show(rows, title):
    print("\n" + "=" * 150); print(title); print("=" * 150)
    print(pd.DataFrame(rows).set_index("label")[COLS].to_string(formatters=F))


if __name__ == "__main__":
    K = 3.69 / 6.67                       # FAS moves are 0.553x SOXL's
    G = matched_gate()
    print(f"FAS/SOXL day-range ratio k = {K:.3f}   matched FAS ATR5 gate = {G:.2f}%")

    ref, _ = row("SOXL locked (reference)", SOXL)
    cells = [ref,
             row("FAS A  locked settings verbatim", FAS)[0],
             row("FAS B  gate matched, dip 1%", FAS, gate=G)[0],
             row("FAS C  gate + dip scaled", FAS, gate=G, dip=.01 * K)[0],
             row("FAS D  fully scaled", FAS, gate=G, dip=.01 * K, target=.01 * K, stop=.04 * K)[0]]
    show(cells, "STEP 1 -- reproduce band_lab's published FAS cells "
                "(A -2.8 / B -8.9 / C +7.1 / D +2.4 bp per ON-day)")

    print("\n" + "=" * 150)
    print("STEP 2 -- LEVERAGE INSTEAD OF SHRINKING THE TRADE.  lev multiplies position size only.")
    print("Note lev=1/k=1.81 restores SOXL-sized moves; the -8% structural worst day is preserved")
    print("only in cell D form, where the stop is also scaled.")
    print("=" * 150)
    lev_rows = [ref]
    for L in (1.0, 1.5, 1.81, 2.5, 3.0):
        lev_rows.append(row(f"FAS C-style, lev {L:.2f}x", FAS, gate=G, dip=.01 * K, lev=L)[0])
    show(lev_rows, "C-style (dip scaled; target 1% and stop 4% left at SOXL's absolute levels)")

    lev_rows2 = [ref]
    for L in (1.0, 1.81, 2.5, 3.0):
        lev_rows2.append(row(f"FAS D-style, lev {L:.2f}x", FAS, gate=G, dip=.01 * K,
                             target=.01 * K, stop=.04 * K, lev=L)[0])
    show(lev_rows2, "D-style (every percentage scaled by k, so lev=1.81 == SOXL's rules on levered FAS)")

    # by-year for the two best candidates
    print("\n" + "=" * 150); print("BY CALENDAR YEAR (sum of daily returns, %)"); print("=" * 150)
    cand = {"SOXL locked": dict(sym=SOXL, kw={}),
            "FAS C lev 1.81x": dict(sym=FAS, kw=dict(gate=G, dip=.01 * K, lev=1.81)),
            "FAS D lev 1.81x": dict(sym=FAS, kw=dict(gate=G, dip=.01 * K, target=.01 * K,
                                                     stop=.04 * K, lev=1.81))}
    yr = {}
    for n, c in cand.items():
        d, t = engine.run(c["sym"], **c["kw"])
        yr[n] = d.ret.groupby(d.index.year).sum() * 100
        d.to_csv(f"{OUT}/days_{n.replace(' ','_').replace('.','')}.csv")
    print(pd.DataFrame(yr).to_string(float_format=lambda v: f"{v:+.1f}%"))
