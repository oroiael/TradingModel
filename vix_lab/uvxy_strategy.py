"""
Run the LOCKED band_lab strategy on UVXY, unchanged, and compare it to the
two sleeves that are already approved.

Nothing here re-optimises anything. §12's constants are used exactly as they
stand; the only thing that varies between rows is the symbol.

Method note. SOXL and SOXS take their 5-minute decision bars from
`{SYM}_5min_6Years.csv`. UVXY has no such file, so its decision bars are the
1-minute file aggregated 5:1. That substitution is validated, not assumed:
`intrabar.parity_check` shows the aggregation reproduces the 5-minute files to
within 2 disputed prints in ~88,600 bars on 2022+, and this module re-runs
SOXL and SOXS *both ways* so the reader can see the substitution costs nothing.

Run:
    python3 vix_lab/uvxy_strategy.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for _p in (os.path.join(ROOT, "band_lab", "live"),
           os.path.join(ROOT, "band_lab", "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from intrabar import (aggregate, load_1min_sessions,  # noqa: E402
                      replay_symbol_intrabar)
from replay import backtest_config, load_sessions  # noqa: E402
from strategy_core import session_stats  # noqa: E402

OUT = os.path.join(_HERE, "out")
WINDOW = pd.Timestamp("2022-01-01")     # the window S11/S12 validated
FLATTEN_IDX = 77                        # the 15:55 five-minute bar


def hdr(s: str) -> None:
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


# ------------------------------------------------------------------ loading
_CACHE: dict[str, list] = {}


def fine_sessions(symbol: str) -> list:
    if symbol not in _CACHE:
        _CACHE[symbol] = load_1min_sessions(symbol, ROOT)
    return _CACHE[symbol]


def decision_from_1min(symbol: str) -> list:
    """5-minute decision bars built by aggregating the 1-minute file."""
    return [(d, aggregate(bars, 5)) for d, bars in fine_sessions(symbol)]


def run(symbol: str, decision: list, start: pd.Timestamp | None = WINDOW,
        fill_model: str = "spec") -> tuple[pd.Series, pd.DataFrame, set]:
    fine = dict(fine_sessions(symbol))
    dates = {d for d, _ in decision} & set(fine)
    if start is not None:
        dates = {d for d in dates if d >= start}
    on, tr = replay_symbol_intrabar(symbol, decision, 5, fill_model=fill_model,
                                    fine_by_date=fine, trade_dates=dates)
    return on, tr, dates


def stats(on: pd.Series, tr: pd.DataFrame, eligible: int) -> dict:
    sharpe = (on.mean() / on.std() * np.sqrt(252)
              if len(on) > 1 and on.std() else float("nan"))
    return {
        "ON": len(on), "eligible": eligible,
        "on_rate": len(on) / eligible if eligible else float("nan"),
        "bp": on.mean() * 1e4, "sharpe": sharpe,
        "trades": len(tr),
        "win": (tr["outcome"] == "target").mean() if len(tr) else float("nan"),
        "worst": on.min() if len(on) else float("nan"),
        "best": on.max() if len(on) else float("nan"),
        "pos_yrs": None,
    }


def row(name: str, s: dict) -> str:
    return (f"{name:<26}{s['ON']:>8}{s['on_rate']:>8.1%}{s['bp']:>11.1f}"
            f"{s['sharpe']:>9.2f}{s['trades']:>8}{s['win']:>8.1%}"
            f"{s['worst'] * 100:>9.2f}")


HEAD = (f"{'run':<26}{'ON days':>8}{'ON rate':>8}{'bp/ON-day':>11}"
        f"{'Sharpe':>9}{'trades':>8}{'win%':>8}{'worst%':>9}")


# ------------------------------------------------------- 1. method is sound
def validate_method() -> None:
    hdr("1. Does aggregating the 1-minute file to 5 minutes change the answer?")
    print("UVXY has no 5-minute file, so its decision bars must be aggregated.")
    print("Before trusting that for UVXY, do it to SOXL and SOXS, where the")
    print("published result is known. Window 2022-01-03+, fill model `spec`.\n")
    print(HEAD)
    for sym, published in (("SOXL", 42.5), ("SOXS", 34.2)):
        native = load_sessions(sym, ROOT)
        on, tr, dates = run(sym, native)
        print(row(f"{sym} 5-min file (pub {published})", stats(on, tr, len(dates))))
        agg = decision_from_1min(sym)
        on2, tr2, d2 = run(sym, agg)
        print(row(f"{sym} 1-min aggregated", stats(on2, tr2, len(d2))))
        delta = on2.mean() * 1e4 - on.mean() * 1e4
        print(f"{'':<26}-> substitution costs {delta:+.2f} bp/ON-day\n")


# ------------------------------------------------- 2. the raw material check
def churn_profile() -> None:
    hdr("2. Raw material — does UVXY have the churn the strategy eats?")
    print("README §1 measures SOXL's band. The same numbers for all three.\n")
    print(f"{'symbol':<8}{'sessions':>9}{'med range%':>12}{'p90 range%':>12}"
          f"{'>=1% swings/d':>15}{'med ATR5':>10}{'ATR5>=6':>9}")
    rows = []
    for sym in ("SOXL", "SOXS", "UVXY"):
        sess = decision_from_1min(sym)
        rng, swings = [], []
        for d, bars in sess:
            if d < WINDOW:
                continue
            st = session_stats(bars)
            rng.append(st.range_pct)
            # completed >=1% swings, high-water/low-water alternation
            px = [b.close for b in bars]
            n, ref, direction = 0, px[0], 0
            for p in px:
                if direction >= 0 and p <= ref * 0.99:
                    n += 1; ref = p; direction = -1
                elif direction <= 0 and p >= ref * 1.01:
                    n += 1; ref = p; direction = 1
                elif direction >= 0 and p > ref:
                    ref = p
                elif direction <= 0 and p < ref:
                    ref = p
            swings.append(n)
        rng = pd.Series(rng)
        atr5 = rng.rolling(5).mean().shift(1).dropna()
        print(f"{sym:<8}{len(rng):>9}{rng.median():>12.2f}{rng.quantile(.9):>12.2f}"
              f"{np.mean(swings):>15.1f}{atr5.median():>10.2f}"
              f"{(atr5 >= 6).mean():>9.1%}")
        rows.append((sym, rng.median(), np.mean(swings), (atr5 >= 6).mean()))
    print("\nThe expectation going in was that a VIX product would be the")
    print("wildest of the three and that the ATR5 gate would be a no-op on it.")
    print("The data says the opposite on both counts: UVXY has the *narrowest*")
    print("median band and the *fewest* 1% swings, and the gate is ON barely")
    print("half the time against ~75% for the two semiconductor sleeves.")
    print("UVXY is 1.5x VIX *futures*, not 1.5x spot VIX, and the front future")
    print("moves far less than the index it settles to.")


# ------------------------------------------ 3. the drift the strategy fights
def drift_decomposition() -> None:
    hdr("3. Intraday vs overnight drift — the structural question for UVXY")
    print("UVXY loses ~67%/yr. The strategy is long-only and flat overnight,")
    print("so what matters is not the total decay but the part of it that is")
    print("realised between 09:30 and 15:55, which is the only window a long")
    print("position is exposed to.\n")
    print(f"{'symbol':<8}{'sessions':>9}{'overnight bp/d':>16}{'intraday bp/d':>15}"
          f"{'total bp/d':>12}{'intraday share':>16}")
    for sym in ("SOXL", "SOXS", "UVXY"):
        sess = [(d, b) for d, b in decision_from_1min(sym) if d >= WINDOW]
        o = np.array([b[0].open for _, b in sess])
        c = np.array([next((x.close for x in reversed(b) if x.idx <= FLATTEN_IDX),
                           b[-1].close) for _, b in sess])
        intr = np.log(c / o)
        overn = np.log(o[1:] / c[:-1])
        tot = intr[1:] + overn
        share = intr[1:].mean() / tot.mean() if tot.mean() else float("nan")
        print(f"{sym:<8}{len(sess):>9}{overn.mean() * 1e4:>16.1f}"
              f"{intr.mean() * 1e4:>15.1f}{tot.mean() * 1e4:>12.1f}"
              f"{share:>16.1%}")
    print("\nA long-only intraday sleeve pays the intraday column and escapes")
    print("the overnight one.")


# ------------------------------------------------------- 4. the actual test
def headline() -> pd.DataFrame:
    hdr("4. The locked strategy, unchanged, on all three symbols")
    print("Identical engine, identical §12 constants, 1-minute fills,")
    print("decision bars aggregated from 1-minute for every symbol so the")
    print("three rows differ only in which security they are pointed at.\n")
    print(HEAD)
    daily = {}
    recs = []
    for sym in ("SOXL", "SOXS", "UVXY"):
        on, tr, dates = run(sym, decision_from_1min(sym))
        s = stats(on, tr, len(dates))
        print(row(sym, s))
        daily[sym] = on
        s["symbol"] = sym
        recs.append(s)
        tr.to_csv(os.path.join(OUT, f"trades_{sym}.csv"), index=False)
        on.to_csv(os.path.join(OUT, f"daily_{sym}.csv"))

    hdr("4b. Year by year (bp/ON-day)")
    print(f"{'symbol':<8}", end="")
    yrs = sorted({d.year for s in daily.values() for d in s.index})
    for y in yrs:
        print(f"{y:>9}", end="")
    print(f"{'  yrs +ve':>10}")
    for sym, on in daily.items():
        print(f"{sym:<8}", end="")
        pos = 0
        for y in yrs:
            g = on[on.index.year == y]
            if len(g):
                print(f"{g.mean() * 1e4:>9.1f}", end="")
                pos += g.mean() > 0
            else:
                print(f"{'-':>9}", end="")
        print(f"{pos:>7}/{len(yrs)}")

    hdr("4c. Diversification — daily P&L correlation on shared ON-days")
    df = pd.DataFrame(daily)
    print("pairwise correlation (only days both sleeves were ON):")
    print(f"{'':<8}", end="")
    for s in df.columns:
        print(f"{s:>9}", end="")
    print(f"{'  n shared':>11}")
    for a in df.columns:
        print(f"{a:<8}", end="")
        for b in df.columns:
            j = df[[a, b]].dropna() if a != b else None
            c = 1.0 if a == b else (j[a].corr(j[b]) if len(j) > 2 else float("nan"))
            print(f"{c:>9.3f}", end="")
        print()
    for a, b in (("SOXL", "SOXS"), ("SOXL", "UVXY"), ("SOXS", "UVXY")):
        n = len(df[[a, b]].dropna())
        print(f"  {a}/{b}: {n} shared ON-days")
    df.to_csv(os.path.join(OUT, "daily_pnl_all.csv"))
    return pd.DataFrame(recs)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    validate_method()
    churn_profile()
    drift_decomposition()
    res = headline()
    res.to_csv(os.path.join(OUT, "headline.csv"), index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
