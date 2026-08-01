"""
V16 — joint re-test of the churn-rate parameters (V1 dip x V3 target x V7 cap).

See V16_CHURN_JOINT_TEST.md. The adoption bar in §5 of that document was
written and committed before this script was run.

The three parameters all control the same quantity — round trips per day — so
they are swept jointly. Sweeping them one at a time would hold the other two
at values chosen under the S10 fill-model bias.

    python3 band_lab/v2_dev/churn_joint_test.py
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

START = pd.Timestamp("2022-01-01")

#: §4 — per-fill cost implied by IMPLEMENTATION_SPEC §8 (gross-vs-net / fills).
#: Applied because V3 and V7 both change trade count directly, so a gross
#: comparison would systematically favour high-churn cells.
COST_BP_PER_FILL = {"SOXL": (65.6 - 61.9) / 3.17, "SOXS": (57.7 - 48.1) / 3.36}

INCUMBENT = (0.0100, 0.0100, 5)          # V1, V3, V7 as locked in §12

DIPS = [0.0050, 0.0075, 0.0100, 0.0125, 0.0150, 0.0200, 0.0250, 0.0300]
TARGETS = [0.0050, 0.0075, 0.0100, 0.0125, 0.0150, 0.0200]
CAPS = [2, 3, 4, 5, 6, 8, 10]

QUICK_DIPS = [0.0075, 0.0100, 0.0150, 0.0200]
QUICK_TARGETS = [0.0075, 0.0100, 0.0150]
QUICK_CAPS = [3, 5, 8]


# ------------------------------------------------------------------ metrics
def max_drawdown(daily: pd.Series) -> float:
    eq = (1.0 + daily.sort_index()).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def same_bar_share(trades: pd.DataFrame, total_pnl: float) -> float:
    """B6 — share of P&L booked in entries opened in the bar that just exited."""
    if not len(trades) or not total_pnl:
        return float("nan")
    s = trades.sort_values(["date", "entry_bar"])
    prev = s.groupby("date")["exit_bar"].shift(1)
    return float(s.loc[s["entry_bar"] == prev, "ret"].sum() / total_pnl)


def evaluate(symbol, sessions, fine, dates, dip, target, cap):
    """One grid cell. Returns per-day net returns, and the summary row."""
    cfg = dataclasses.replace(backtest_config(symbol),
                              dip_pct=dip, target_pct=target, max_fills=cap)
    on, tr = replay_symbol_intrabar(symbol, sessions, 5, cfg=cfg,
                                    fill_model="spec", target_delay="fill_bar",
                                    fine_by_date=fine, trade_dates=dates)
    fills = (tr.groupby("date").size().reindex(on.index).fillna(0)
             if len(tr) else pd.Series(0.0, index=on.index))
    net = on - fills * COST_BP_PER_FILL[symbol] / 1e4
    return net, dict(dip=dip, target=target, cap=cap,
                     on_days=len(net), trades=len(tr),
                     fills_per_day=len(tr) / max(len(net), 1),
                     gross_bp=on.mean() * 1e4, net_bp=net.mean() * 1e4,
                     mdd=max_drawdown(net),
                     same_bar=same_bar_share(tr, on.sum()))


# --------------------------------------------------------------- the sweep
def run_sleeve(symbol, dips, targets, caps, verbose=True):
    fine = dict(load_1min_sessions(symbol, ROOT))
    sessions = load_sessions(symbol, ROOT)
    dates = {d for d, _ in sessions} & set(fine)
    dates = {d for d in dates if d >= START}
    rows, daily = [], {}
    total = len(dips) * len(targets) * len(caps)
    n = 0
    for dip in dips:
        for target in targets:
            for cap in caps:
                net, row = evaluate(symbol, sessions, fine, dates, dip, target, cap)
                rows.append(row)
                daily[(dip, target, cap)] = net
                n += 1
                if verbose and n % 25 == 0:
                    print(f"  {symbol}: {n}/{total} cells", flush=True)
    return pd.DataFrame(rows), daily


def walk_forward(daily, dips, targets, caps):
    """B1 — hold each year out, select on the rest, score on the held-out year.

    Returns (per-year selection table, OOS wins vs incumbent out of n years).
    """
    years = sorted({d.year for d in next(iter(daily.values())).index})
    inc = daily[INCUMBENT]
    out = []
    for y in years:
        best, best_key = None, None
        for key in daily:
            s = daily[key]
            ins = s[s.index.year != y]
            if not len(ins):
                continue
            v = ins.mean()
            if best is None or v > best:
                best, best_key = v, key
        oos = daily[best_key]
        oos = oos[oos.index.year == y]
        inc_y = inc[inc.index.year == y]
        out.append(dict(year=y, selected=best_key,
                        oos_bp=oos.mean() * 1e4,
                        incumbent_bp=inc_y.mean() * 1e4,
                        beat=bool(oos.mean() > inc_y.mean())))
    return pd.DataFrame(out)


def plateau_score(df, dips, targets, caps, cell):
    """B2 — mean net edge of the immediate neighbours, as a share of the cell's."""
    di, ti, ci = dips.index(cell[0]), targets.index(cell[1]), caps.index(cell[2])
    vals = []
    for dd in (-1, 0, 1):
        for tt in (-1, 0, 1):
            for cc in (-1, 0, 1):
                if dd == tt == cc == 0:
                    continue
                i, j, k = di + dd, ti + tt, ci + cc
                if not (0 <= i < len(dips) and 0 <= j < len(targets)
                        and 0 <= k < len(caps)):
                    continue
                r = df[(df.dip == dips[i]) & (df.target == targets[j])
                       & (df.cap == caps[k])]
                if len(r):
                    vals.append(float(r.net_bp.iloc[0]))
    own = float(df[(df.dip == cell[0]) & (df.target == cell[1])
                   & (df.cap == cell[2])].net_bp.iloc[0])
    return (np.mean(vals) / own if vals and own else float("nan")), len(vals)


# -------------------------------------------------------------- reporting
def report(symbol, df, daily, dips, targets, caps):
    inc = df[(df.dip == INCUMBENT[0]) & (df.target == INCUMBENT[1])
             & (df.cap == INCUMBENT[2])].iloc[0]
    print("\n" + "=" * 92)
    print(f"{symbol} — V16 grid, net of costs, 1-minute fills, 2022+")
    print("=" * 92)
    print(f"INCUMBENT  dip {inc.dip:.2%}  target {inc.target:.2%}  cap {int(inc.cap)}"
          f"   ->  net {inc.net_bp:.1f} bp/ON-day, MaxDD {inc.mdd:.1%}, "
          f"{inc.fills_per_day:.2f} fills/day, same-bar {inc.same_bar:.0%}")

    top = df.sort_values("net_bp", ascending=False).head(12)
    print(f"\nTop 12 cells by net bp/ON-day:")
    print(f"  {'dip':>6}{'target':>8}{'cap':>5}{'net bp':>9}{'gross':>8}"
          f"{'MaxDD':>8}{'fills/d':>9}{'same-bar':>10}{'vs inc':>8}")
    for _, r in top.iterrows():
        print(f"  {r.dip:>6.2%}{r.target:>8.2%}{int(r.cap):>5}{r.net_bp:>9.1f}"
              f"{r.gross_bp:>8.1f}{r.mdd:>8.1%}{r.fills_per_day:>9.2f}"
              f"{r.same_bar:>10.0%}{r.net_bp - inc.net_bp:>+8.1f}")

    # marginal views — what each variable does on its own, others at incumbent
    for var, vals, others in (("dip", dips, ("target", "cap")),
                              ("target", targets, ("dip", "cap")),
                              ("cap", caps, ("dip", "target"))):
        fixed = {k: INCUMBENT[["dip", "target", "cap"].index(k)] for k in others}
        sub = df.copy()
        for k, v in fixed.items():
            sub = sub[sub[k] == v]
        sub = sub.sort_values(var)
        lbl = {"dip": "V1 dip depth", "target": "V3 profit target",
               "cap": "V7 trade cap"}[var]
        print(f"\n{lbl}, others held at locked values:")
        print(f"  {'value':>8}{'net bp':>9}{'MaxDD':>8}{'fills/d':>9}{'same-bar':>10}")
        for _, r in sub.iterrows():
            v = f"{r[var]:.2%}" if var != "cap" else f"{int(r[var])}"
            mark = "  <- locked" if r[var] == fixed.get(var, INCUMBENT[
                ["dip", "target", "cap"].index(var)]) else ""
            print(f"  {v:>8}{r.net_bp:>9.1f}{r.mdd:>8.1%}{r.fills_per_day:>9.2f}"
                  f"{r.same_bar:>10.0%}{mark}")
    return inc, top


def main() -> int:
    ap = argparse.ArgumentParser(description="V16 joint churn-rate re-test")
    ap.add_argument("--quick", action="store_true", help="coarse grid")
    ap.add_argument("--out", default=os.path.join(_HERE, "out"))
    args = ap.parse_args()
    dips = QUICK_DIPS if args.quick else DIPS
    targets = QUICK_TARGETS if args.quick else TARGETS
    caps = QUICK_CAPS if args.quick else CAPS
    for seq, name in ((dips, "dip"), (targets, "target"), (caps, "cap")):
        if INCUMBENT[["dip", "target", "cap"].index(name)] not in seq:
            raise SystemExit(f"incumbent {name} must be in the grid")
    os.makedirs(args.out, exist_ok=True)

    print(f"V16 grid: {len(dips)}x{len(targets)}x{len(caps)} = "
          f"{len(dips)*len(targets)*len(caps)} cells per sleeve")
    store = {}
    for symbol in ("SOXL", "SOXS"):
        df, daily = run_sleeve(symbol, dips, targets, caps)
        df.to_csv(os.path.join(args.out, f"v16_grid_{symbol}.csv"), index=False)
        store[symbol] = (df, daily)
        report(symbol, df, daily, dips, targets, caps)

    print("\n" + "=" * 92)
    print("B1 — WALK-FORWARD (hold each year out, select on the rest)")
    print("=" * 92)
    wfs, picks = {}, {}
    for symbol in ("SOXL", "SOXS"):
        df, daily = store[symbol]
        wf = walk_forward(daily, dips, targets, caps)
        wf.to_csv(os.path.join(args.out, f"v16_walkforward_{symbol}.csv"), index=False)
        wfs[symbol] = wf
        print(f"\n{symbol}:")
        print(f"  {'year':>6}{'selected (dip/target/cap)':>28}{'OOS bp':>9}"
              f"{'incumbent':>11}{'beat?':>7}")
        for _, r in wf.iterrows():
            k = r.selected
            print(f"  {r.year:>6}{f'{k[0]:.2%} / {k[1]:.2%} / {k[2]}':>28}"
                  f"{r.oos_bp:>9.1f}{r.incumbent_bp:>11.1f}"
                  f"{'YES' if r.beat else 'no':>7}")
        print(f"  -> beat incumbent OOS in {int(wf.beat.sum())} of {len(wf)} years"
              f"   (B1 needs >= 4)")
        picks[symbol] = tuple(df.sort_values("net_bp", ascending=False)
                              .iloc[0][["dip", "target", "cap"]])

    # ------------------------------------------------ the six-criterion bar
    print("\n" + "=" * 92)
    print("ADOPTION BAR — the six criteria fixed in V16_CHURN_JOINT_TEST.md §5")
    print("=" * 92)
    verdicts = {}
    for symbol in ("SOXL", "SOXS"):
        df, daily = store[symbol]
        cand = (picks[symbol][0], picks[symbol][1], int(picks[symbol][2]))
        row = df[(df.dip == cand[0]) & (df.target == cand[1])
                 & (df.cap == cand[2])].iloc[0]
        inc = df[(df.dip == INCUMBENT[0]) & (df.target == INCUMBENT[1])
                 & (df.cap == INCUMBENT[2])].iloc[0]
        wins = int(wfs[symbol].beat.sum()); nyr = len(wfs[symbol])
        plat, nb = plateau_score(df, dips, targets, caps, cand)
        b1 = wins >= 4
        b2 = plat >= 0.90
        b5 = row.mdd >= inc.mdd - 0.02
        b6 = row.same_bar <= inc.same_bar + 1e-9
        boundary = (cand[0] in (dips[0], dips[-1]) or cand[1] in (targets[0], targets[-1])
                    or cand[2] in (caps[0], caps[-1]))
        verdicts[symbol] = dict(cand=cand, b1=b1, b2=b2, b5=b5, b6=b6,
                                plat=plat, wins=wins, nyr=nyr, row=row, inc=inc,
                                boundary=boundary)
        print(f"\n{symbol}  candidate = dip {cand[0]:.2%} / target {cand[1]:.2%} / cap {cand[2]}")
        print(f"  net {row.net_bp:.1f} bp vs incumbent {inc.net_bp:.1f}  "
              f"({row.net_bp - inc.net_bp:+.1f})")
        print(f"  B1 out-of-sample  : {wins}/{nyr} years          -> {'PASS' if b1 else 'FAIL'}")
        print(f"  B2 plateau        : neighbours avg {plat:.0%} of cell ({nb} nbrs)"
              f"  -> {'PASS' if b2 else 'FAIL'}")
        print(f"  B4 costs          : net figures used throughout -> PASS (by construction)")
        print(f"  B5 risk           : MaxDD {row.mdd:.1%} vs {inc.mdd:.1%} "
              f"(limit {inc.mdd-0.02:.1%})   -> {'PASS' if b5 else 'FAIL'}")
        print(f"  B6 mechanism      : same-bar share {row.same_bar:.0%} vs "
              f"incumbent {inc.same_bar:.0%}  -> {'PASS' if b6 else 'FAIL'}")
        if boundary:
            print(f"  [!] candidate sits on a GRID BOUNDARY — the optimum may lie "
                  f"outside the tested range; treat as unresolved, not as a result")
    same_dir = verdicts["SOXL"]["cand"] == verdicts["SOXS"]["cand"]
    print(f"\n  B3 both sleeves   : SOXL {verdicts['SOXL']['cand']} vs "
          f"SOXS {verdicts['SOXS']['cand']}  -> {'PASS' if same_dir else 'see report'}")
    allpass = all(v[k] for v in verdicts.values() for k in ("b1", "b2", "b5", "b6"))
    print(f"\n  OVERALL: {'ALL CRITERIA PASS' if allpass and same_dir else 'NOT ADOPTED — at least one criterion fails'}")
    print("  Per §5: if no cell clears the bar, the locked values stand.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
