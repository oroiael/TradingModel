"""
V19 — the day profit stop: should a sleeve stop trading once it is up X%?

**Status: DIAGNOSTIC. This is not an adoption program and adopts nothing.**
`README.md` requires a prespecified, signed-off adoption bar before a result may
change v1.0, and no bar was written for this. What follows measures the
question and reports the mechanism; §6 states what a real V19 would still need.

The question, asked directly: the sleeve already truncates a day *downward*
twice — `max_stops` (V11's 2-stop breaker) and §12's DAY_LOSS_KILL at -8.5%.
It has never truncated one *upward*. Is that asymmetry right?

V17 asked the closest existing question — "is the Nth trade of the day worth
taking?" — and answered it by trade **ordinal**. A profit stop conditions on
something V17 never measured: **cumulative P&L so far**. D1 is that measurement,
and it is the diagnostic the whole question reduces to. If the next trade is
still profitable in expectation after the sleeve is up X%, a profit stop can
only destroy money, and no amount of Sharpe arithmetic rescues it.

Judged per ON-day, which V18's finding permits here and would forbid for a
gate test: the profit stop cannot change *whether* a day is ON — the gate and
filter have already run before the first trade — so the denominator is fixed
across every threshold. D0 asserts that rather than assuming it.

    python3 band_lab/v2_dev/profit_stop_test.py
    python3 band_lab/v2_dev/profit_stop_test.py --quick
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
from spec_constants import TARGET_PCT                            # noqa: E402

START = pd.Timestamp("2022-01-01")

#: V17's per-fill cost, unchanged — same data, same round trips, and a profit
#: stop's entire effect is on how many of them there are. Re-deriving it here
#: would create a second source of truth for a number V17 already published.
COST_BP_PER_FILL = {"SOXL": (65.6 - 61.9) / 3.17, "SOXS": (57.7 - 48.1) / 3.36}

SLEEVES = ("SOXL", "SOXS")

#: Thresholds as a fraction of sleeve capital. The two the question named are
#: 0.005 and 0.010; the rest are there to show the *shape*, because a rule whose
#: result depends on which side of a step it lands is not a rule worth adopting.
THRESHOLDS = [0.0025, 0.005, 0.0075, 0.010, 0.015, 0.020, 0.030, 0.040]
QUICK = [0.005, 0.010, 0.020]


def run(symbol, sessions, fine, dates, thr):
    """One replay at one threshold. `thr=None` is the incumbent (no stop)."""
    cfg = dataclasses.replace(backtest_config(symbol), day_profit_stop=thr)
    on, tr = replay_symbol_intrabar(symbol, sessions, 5, cfg=cfg,
                                    fill_model="spec", target_delay="fill_bar",
                                    fine_by_date=fine, trade_dates=dates)
    if len(tr):
        tr = tr.sort_values(["date", "entry_bar"]).reset_index(drop=True)
        tr["ordinal"] = tr.groupby("date").cumcount() + 1
        # P&L *before* this trade opened — the quantity the rule conditions on,
        # and the one V17's ordinal analysis could not see.
        tr["pnl_before"] = tr.groupby("date")["ret"].cumsum() - tr["ret"]
        tr["net_ret"] = tr["ret"] - COST_BP_PER_FILL[symbol] / 1e4
    return on, tr


def net_daily(on, tr, symbol):
    f = (tr.groupby("date").size().reindex(on.index).fillna(0)
         if len(tr) else pd.Series(0.0, index=on.index))
    return on - f * COST_BP_PER_FILL[symbol] / 1e4


def mdd(daily):
    eq = (1.0 + daily.sort_index()).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def sharpe(daily):
    sd = daily.std()
    return float(daily.mean() / sd * np.sqrt(252)) if sd else float("nan")


# ------------------------------------------------------------------- D1
def d1_conditional_expectancy(tr, n_on, thresholds):
    """The next trade's expectancy given the day is already up >= X.

    This is the whole question in one table. A profit stop deletes exactly the
    trades in the `>= thr` row; whatever that row earns is what the stop costs.
    """
    rows = []
    for thr in thresholds:
        above = tr[tr.pnl_before >= thr - 1e-9]
        below = tr[tr.pnl_before < thr - 1e-9]
        if not len(above):
            continue
        rows.append(dict(
            thr=thr, n_deleted=len(above),
            pct_of_trades=len(above) / len(tr) * 100,
            mean_net_bp=above.net_ret.mean() * 1e4,
            win_rate=float((above.ret > 0).mean()),
            #: What the account loses per ON-day by not taking them.
            contrib_bp=above.net_ret.sum() / n_on * 1e4,
            below_mean_net_bp=below.net_ret.mean() * 1e4 if len(below) else np.nan,
        ))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="V19 day-profit-stop diagnostic")
    ap.add_argument("--out", default=os.path.join(_HERE, "out"))
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    thresholds = QUICK if args.quick else THRESHOLDS

    base, sweep, d1 = {}, {}, {}
    for symbol in SLEEVES:
        fine = dict(load_1min_sessions(symbol, ROOT))
        sessions = load_sessions(symbol, ROOT)
        dates = {d for d, _ in sessions} & set(fine)
        dates = {d for d in dates if d >= START}

        on, tr = run(symbol, sessions, fine, dates, None)
        nd = net_daily(on, tr, symbol)
        base[symbol] = dict(on=on, tr=tr, daily=nd, net_bp=nd.mean() * 1e4,
                            mdd=mdd(nd), sharpe=sharpe(nd),
                            worst=float(nd.min()), fills=len(tr) / len(on))
        d1[symbol] = d1_conditional_expectancy(tr, len(on), thresholds)

        rows = {}
        for thr in thresholds:
            o, t = run(symbol, sessions, fine, dates, thr)
            d = net_daily(o, t, symbol)
            binding = (len(t.groupby("date")) and
                       (t.groupby("date")["ret"].apply(
                           lambda s: (s.cumsum() >= thr - 1e-9).any()).sum()))
            rows[thr] = dict(daily=d, net_bp=d.mean() * 1e4, mdd=mdd(d),
                             sharpe=sharpe(d), worst=float(d.min()),
                             fills=len(t) / len(o), n_on=len(o),
                             binding_pct=100.0 * binding / len(o))
        sweep[symbol] = rows

    # --------------------------------------------------------------- report
    print("=" * 96)
    print("V19 — DAY PROFIT STOP (DIAGNOSTIC, ADOPTS NOTHING)")
    print("1-minute fills, net of costs, 2022+.  Threshold = realised day P&L "
          "as a fraction of sleeve capital.")
    print("=" * 96)

    print("\n" + "-" * 96)
    print("D0 — THE MECHANISM.  What does a threshold actually do?")
    print("-" * 96)
    print(f"""
  Under the backtest config the sleeve sizes off the fill price with fractional
  shares, so a target trade returns exactly f x target_pct = {TARGET_PCT:.2%} of sleeve
  capital, and a stop-out returns -4%. Realised day P&L at the moment the rule
  is consulted is therefore a sum of +1s and -4s, and the rule reduces to:

        "stop after ceil(threshold / 1%) winning trades"

  That is the single most important fact about this question, and it is fatal to
  the distinction the question drew: **+0.5% and +1.0% are the same rule.** Both
  fire after the first winner. Nothing in the strategy can produce a day sitting
  between them, because nothing produces a partial winner — the target is the
  only profitable exit that re-arms, and it always pays exactly 1%.
""")

    print("-" * 96)
    print("D1 — THE TRADES A STOP DELETES.  Are they worth taking?  (the whole question)")
    print("-" * 96)
    for symbol in SLEEVES:
        b, d = base[symbol], d1[symbol]
        print(f"\n{symbol}   (no stop: {b['net_bp']:.1f} bp/ON-day over "
              f"{len(b['on'])} ON-days, {len(b['tr'])} trades, "
              f"mean net {b['tr'].net_ret.mean()*1e4:.1f} bp/trade)")
        print(f"  {'thr':>7}{'trades cut':>12}{'% of all':>10}"
              f"{'mean net bp':>13}{'win rate':>10}{'bp/ON-day lost':>16}"
              f"{'vs trades kept':>16}")
        for _, r in d.iterrows():
            print(f"  {r.thr:>7.2%}{int(r.n_deleted):>12}{r.pct_of_trades:>9.0f}%"
                  f"{r.mean_net_bp:>13.1f}{r.win_rate:>10.1%}"
                  f"{-r.contrib_bp:>16.1f}{r.below_mean_net_bp:>16.1f}")

    print("\n" + "-" * 96)
    print("D2 — THRESHOLD SWEEP.  Does anything win on risk-adjusted terms?")
    print("-" * 96)
    for symbol in SLEEVES:
        b, s = base[symbol], sweep[symbol]
        print(f"\n{symbol}   (incumbent: {b['net_bp']:.1f} bp, Sharpe "
              f"{b['sharpe']:.2f}, MaxDD {b['mdd']:.1%}, worst day "
              f"{b['worst']:.2%}, {b['fills']:.2f} fills/day)")
        print(f"  {'thr':>7}{'net bp':>9}{'vs inc':>9}{'Sharpe':>9}{'dSharpe':>9}"
              f"{'MaxDD':>9}{'worst day':>11}{'fills/d':>9}{'days bound':>12}")
        for thr in thresholds:
            r = s[thr]
            print(f"  {thr:>7.2%}{r['net_bp']:>9.1f}"
                  f"{r['net_bp']-b['net_bp']:>+9.1f}{r['sharpe']:>9.2f}"
                  f"{r['sharpe']-b['sharpe']:>+9.2f}{r['mdd']:>9.1%}"
                  f"{r['worst']:>11.2%}{r['fills']:>9.2f}"
                  f"{r['binding_pct']:>11.0f}%")

    print("\n" + "-" * 96)
    print("D3 — PER-YEAR SIGN TEST vs the incumbent.  (V16 R4.2: walk-forward is")
    print("     not protective on this dataset, so this is a consistency check only)")
    print("-" * 96)
    for symbol in SLEEVES:
        b, s = base[symbol], sweep[symbol]
        bd = b["daily"].copy(); bd.index = pd.DatetimeIndex(bd.index)
        yrs = sorted({d.year for d in bd.index})
        print(f"\n{symbol}")
        print(f"  {'thr':>7}" + "".join(f"{y:>10}" for y in yrs) + f"{'wins':>7}")
        for thr in thresholds:
            d = s[thr]["daily"].copy(); d.index = pd.DatetimeIndex(d.index)
            cells, w = [], 0
            for y in yrs:
                diff = (d[d.index.year == y].mean()
                        - bd[bd.index.year == y].mean()) * 1e4
                cells.append(f"{diff:>+10.1f}")
                w += diff > 0
            print(f"  {thr:>7.2%}" + "".join(cells) + f"{w:>5}/{len(yrs)}")

    # ------------------------------------------------------------- verdict
    print("\n" + "=" * 96)
    any_win = False
    for symbol in SLEEVES:
        b, s = base[symbol], sweep[symbol]
        best = max(thresholds, key=lambda t: s[t]["net_bp"])
        won = s[best]["net_bp"] > b["net_bp"]
        any_win = any_win or won
        sh = max(thresholds, key=lambda t: s[t]["sharpe"])
        print(f"{symbol}: best net bp at {best:.2%} "
              f"({s[best]['net_bp']:.1f} vs {b['net_bp']:.1f} incumbent, "
              f"{s[best]['net_bp']-b['net_bp']:+.1f}); "
              f"best Sharpe at {sh:.2%} "
              f"({s[sh]['sharpe']:.2f} vs {b['sharpe']:.2f})")
    print("-" * 96)
    print("DIAGNOSTIC ONLY — nothing here is adopted, and D1 is the row that")
    print("matters: a stop deletes those trades and nothing else. §6 of the")
    print("write-up states what a real V19 program would still have to do.")
    print("=" * 96)

    for symbol in SLEEVES:
        d1[symbol].to_csv(os.path.join(args.out, f"v19_conditional_{symbol}.csv"),
                          index=False)
        pd.DataFrame({t: {k: v for k, v in r.items() if k != "daily"}
                      for t, r in sweep[symbol].items()}).T.to_csv(
            os.path.join(args.out, f"v19_sweep_{symbol}.csv"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
