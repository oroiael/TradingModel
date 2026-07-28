"""
Phase 1 — the parity harness (IMPLEMENTATION_SPEC.md §9 Phase 1, §10 test 1).

Three jobs:

  A. PARITY   Run the clean-room engine in RESEARCH_COMPAT mode and compare
              its daily P&L series, day by day, against the research engine
              (transfer_test/etf_scaling_test/v5_corrected_rerun). This is
              the acceptance test: exact agreement to floating-point
              tolerance on both sleeves.

  B. ARTIFACT Rebuild band_lab/out/v14_*.csv from the clean-room series and
              diff against the committed files.

  C. DELTA    Run the spec-literal engine and attribute the difference from
              the research engine to each individual interpretation switch,
              so the reader can see the price of every ambiguity in §2.

Outputs: band_lab/phase1/out/
Usage:   python3 band_lab/phase1/parity.py [--tol 1e-12]
"""

from __future__ import annotations

import argparse
import dataclasses as dc
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BAND_LAB = os.path.dirname(HERE)
ROOT = os.path.dirname(BAND_LAB)
for p in (HERE, BAND_LAB, os.path.join(ROOT, "cycle_lab")):
    if p not in sys.path:
        sys.path.insert(0, p)

from spec_engine import RESEARCH_COMPAT, SPEC_LITERAL, EngineConfig, run_sleeve

OUT = os.path.join(HERE, "out")
REF_OUT = os.path.join(BAND_LAB, "out")
SLEEVES = ["SOXL", "SOXS"]

# v14_pair_protocol.py constants, needed only to rebuild its tables (§B).
CURRENT_PX = {"SOXL": 158.41, "SOXS": 51.61}
TRADES_PER_DAY = {"SOXL": 3.17, "SOXS": 3.36}
WGRID = [0.0, 0.25, 0.50, 0.75, 1.0]


def sharpe(x: pd.Series) -> float:
    return (x.mean() / x.std() * np.sqrt(252)
            if len(x) > 2 and x.std() > 0 else np.nan)


# =============================================================== A. parity
def research_series() -> dict[str, pd.Series]:
    """The research engine's ON-day P&L series, exactly as v14 consumes it."""
    from transfer_test import load_symbol, build_daily
    from etf_scaling_test import run_cell
    out = {}
    for sym in SLEEVES:
        d, g = build_daily(load_symbol(sym))
        _, on = run_cell(d, g, 6.0, .01, .01, .04, sym)
        out[sym] = on
    return out


def cleanroom_series(cfg: EngineConfig) -> tuple[dict, dict, dict]:
    series, logs, trades = {}, {}, {}
    for sym in SLEEVES:
        log, on, tr = run_sleeve(sym, cfg)
        series[sym], logs[sym], trades[sym] = on, log, tr
    return series, logs, trades


def compare(ref: pd.Series, got: pd.Series, tol: float) -> dict:
    only_ref = ref.index.difference(got.index)
    only_got = got.index.difference(ref.index)
    both = ref.index.intersection(got.index)
    diff = (got.reindex(both) - ref.reindex(both)).abs()
    worst = float(diff.max()) if len(diff) else 0.0
    n_bad = int((diff > tol).sum()) if len(diff) else 0
    return {
        "ref_days": len(ref), "cleanroom_days": len(got),
        "common_days": len(both),
        "days_only_in_research": len(only_ref),
        "days_only_in_cleanroom": len(only_got),
        "max_abs_diff": worst,
        "days_over_tol": n_bad,
        "PASS": bool(len(only_ref) == 0 and len(only_got) == 0 and n_bad == 0),
        "_only_ref": only_ref, "_only_got": only_got, "_diff": diff,
    }


# ============================================================ B. artifacts
def cost_bp(price: float, trades_per_day: float, capital: float = 150000.0):
    """IBKR Pro Fixed round-trip cost in bp of position (v14 §T1 model)."""
    shares = capital / price
    comm_side = max(0.005 * shares, 1.00)
    comm_bp_side = comm_side / capital * 1e4
    reg_bp_sell = 0.35
    spread_bp = (0.01 / price) * 1e4
    cross_frac = 0.30
    per_rt = 2 * comm_bp_side + reg_bp_sell + cross_frac * spread_bp
    return per_rt, per_rt * trades_per_day, comm_bp_side, spread_bp


def rebuild_v14(series: dict[str, pd.Series]) -> dict[str, pd.DataFrame]:
    rows = []
    for sym in SLEEVES:
        on, px, tpd = series[sym], CURRENT_PX[sym], TRADES_PER_DAY[sym]
        rt, per_day, comm_side, spr = cost_bp(px, tpd)
        rows.append({"sleeve": sym, "mean_price": round(px, 2),
                     "comm_bp_per_side": round(comm_side, 2),
                     "spread_bp_1cent": round(spr, 2),
                     "cost_bp_per_round_trip": round(rt, 2),
                     "trades_per_day": tpd,
                     "cost_bp_per_day": round(per_day, 1),
                     "gross_bp_day": round(on.mean() * 1e4, 1),
                     "NET_bp_day": round(on.mean() * 1e4 - per_day, 1)})
    costs = pd.DataFrame(rows)

    cL = costs.loc[costs.sleeve == "SOXL", "cost_bp_per_day"].iloc[0] / 1e4
    cX = costs.loc[costs.sleeve == "SOXS", "cost_bp_per_day"].iloc[0] / 1e4
    nL, nX = series["SOXL"] - cL, series["SOXS"] - cX
    cal = pd.date_range(min(nL.index.min(), nX.index.min()),
                        max(nL.index.max(), nX.index.max()), freq="B")
    a, b = nL.reindex(cal).fillna(0.0), nX.reindex(cal).fillna(0.0)
    onLc = pd.Series(False, index=cal); onLc[nL.index] = True
    onXc = pd.Series(False, index=cal); onXc[nX.index] = True

    def blend(w, mode="static"):
        if mode == "static":
            return w * a + (1 - w) * b
        act = onLc.astype(float) * w + onXc.astype(float) * (1 - w)
        sc = pd.Series(np.where(act > 0, 1.0 / act.replace(0, np.nan), 0.0),
                       index=cal).fillna(0.0)
        return (w * a + (1 - w) * b) * sc

    def stats(r, label):
        eq = (1 + r).cumprod(); pk = eq.cummax()
        yrs = (cal[-1] - cal[0]).days / 365.25
        return {"variant": label, "bp_cal_day": round(r.mean() * 1e4, 1),
                "sharpe": round(sharpe(r), 2),
                "maxDD_%": round(((eq - pk) / pk).min() * 100, 1),
                "CAGR_%": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1)}

    plateau = pd.DataFrame([stats(blend(w), f"w={w:.3f}")
                            for w in np.arange(0, 1.0001, 0.125)])

    picks = []
    for yr in [2022, 2023, 2024, 2025, 2026]:
        t0 = pd.Timestamp(f"{yr}-01-01")
        best, bs = None, -99
        for w in WGRID:
            s_ = sharpe(blend(w)[blend(w).index < t0])
            if not np.isnan(s_) and s_ > bs:
                bs, best = s_, w
        picks.append({"year": yr, "w_picked": best})
    walkforward = pd.DataFrame(picks)

    capital_rule = pd.DataFrame([
        stats(a, "SOXL alone"),
        stats(blend(.5), "pair 50/50 static"),
        stats(blend(.5, "dynamic"), "pair 50/50 dynamic")])

    return {"v14_costs": costs, "v14_plateau": plateau,
            "v14_walkforward": walkforward, "v14_capital_rule": capital_rule}


def diff_tables(built: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, got in built.items():
        ref_path = os.path.join(REF_OUT, f"{name}.csv")
        got.to_csv(os.path.join(OUT, f"rebuilt_{name}.csv"), index=False)
        if not os.path.exists(ref_path):
            rows.append({"table": name, "status": "REFERENCE MISSING"})
            continue
        ref = pd.read_csv(ref_path)
        same_shape = ref.shape == got.shape and list(ref.columns) == list(got.columns)
        identical = False
        if same_shape:
            g = got.copy()
            for c in ref.columns:
                if pd.api.types.is_numeric_dtype(ref[c]):
                    g[c] = pd.to_numeric(g[c], errors="coerce")
            identical = bool(ref.reset_index(drop=True)
                             .equals(g.reset_index(drop=True)))
        rows.append({"table": name,
                     "shape_ref": str(ref.shape), "shape_built": str(got.shape),
                     "status": "IDENTICAL" if identical else
                               ("SHAPE MISMATCH" if not same_shape else "VALUES DIFFER")})
    return pd.DataFrame(rows)


# ================================================================ C. delta
SWITCHES = [
    ("S1 thr80 recomputed monthly (§2.1)", dict(thr80_refresh="monthly")),
    ("S2 half-days OFF (§2.2)", dict(half_day_policy="off")),
    ("S3 flatten at 15:55 (§2.8)", dict(eod_mode="flatten_1555")),
    ("S4 target live on entry bar (§2.6)", dict(target_on_entry_bar=True)),
    ("S5 round_to_tick (§2.5/§2.6)", dict(tick_rounding=True)),
    ("S6 clock bar indexing (§2.1)", dict(bar_indexing="clock")),
    ("S7 whole-share sizing (§2.4)", dict(share_rounding=True)),
    ("S8 refuse incomplete sessions (§4)", dict(require_full_session_open=True)),
]


def summarise(on: pd.Series, label: str) -> dict:
    return {"variant": label, "ON_days": len(on),
            "bp_per_ON_day": round(on.mean() * 1e4, 1) if len(on) else np.nan,
            "sharpe": round(sharpe(on), 2),
            "worst_day_%": round(on.min() * 100, 2) if len(on) else np.nan,
            "total_%": round(on.sum() * 100, 1)}


def _in_spec_literal(kw: dict) -> bool:
    return all(getattr(SPEC_LITERAL, k) == v for k, v in kw.items())


def delta_attribution() -> pd.DataFrame:
    rows = []
    base = RESEARCH_COMPAT
    adopted = [s for s, kw in SWITCHES if _in_spec_literal(kw)]
    for sym in SLEEVES:
        _, on0, _ = run_sleeve(sym, base)
        r = summarise(on0, "research-compat baseline")
        r.update(sleeve=sym, in_spec_literal="-", d_bp_vs_baseline=0.0)
        rows.append(r)
        for label, kw in SWITCHES:
            _, on, _ = run_sleeve(sym, dc.replace(base, **kw))
            r = summarise(on, f"+ {label}")
            r.update(sleeve=sym,
                     in_spec_literal="yes" if _in_spec_literal(kw) else "no",
                     d_bp_vs_baseline=round((on.mean() - on0.mean()) * 1e4, 1))
            rows.append(r)
        _, onS, _ = run_sleeve(sym, SPEC_LITERAL)
        r = summarise(onS, "= SPEC_LITERAL ("
                           + ",".join(s.split()[0] for s in adopted) + ")")
        r.update(sleeve=sym, in_spec_literal="-",
                 d_bp_vs_baseline=round((onS.mean() - on0.mean()) * 1e4, 1))
        rows.append(r)
    cols = ["sleeve", "variant", "in_spec_literal", "ON_days", "bp_per_ON_day",
            "d_bp_vs_baseline", "sharpe", "worst_day_%", "total_%"]
    return pd.DataFrame(rows)[cols]


# ============================================ §8 live-vs-backtest expectations
def monitoring_check(series: dict[str, pd.Series]) -> pd.DataFrame:
    """§8 lists the numbers the live system will be judged against. Measure
    them on the research engine so a live deviation means something."""
    rows = []
    for sym in SLEEVES:
        log, on, tr = run_sleeve(sym, RESEARCH_COMPAT)
        traded = log[log["traded"]]
        mix = tr["outcome"].value_counts(normalize=True) * 100
        rows.append({
            "sleeve": sym,
            "fills_per_ON_day": round(traded["fills"].mean(), 2),
            "spec_§8_expects": "~3.2",
            "target_share_of_exits_%": round(mix.get("target", 0.0), 1),
            "target_share_ex_flatten_%": round(
                mix.get("target", 0.0) / (mix.get("target", 0.0)
                                          + mix.get("stop", 0.0)) * 100, 1),
            "spec_§8_expects_target": "75-80%",
            "ON_day_rate_%": round(len(on) / len(log) * 100, 1),
            "spec_§8_expects_ON": "~50%",
            "gross_bp_per_ON_day": round(on.mean() * 1e4, 1),
            "worst_day_%": round(on.min() * 100, 2),
            "spec_§8_expects_worst": "never below -8%",
        })
    return pd.DataFrame(rows)


# ================================================================== main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=1e-12)
    ap.add_argument("--skip-delta", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    rc = 0

    print("=" * 92)
    print("A. CLEAN-ROOM PARITY vs RESEARCH ENGINE  (spec §9 Phase 1, §10 test 1)")
    print("=" * 92)
    ref = research_series()
    got, logs, trades = cleanroom_series(RESEARCH_COMPAT)
    prows = []
    for sym in SLEEVES:
        c = compare(ref[sym], got[sym], args.tol)
        prows.append({"sleeve": sym, **{k: v for k, v in c.items()
                                        if not k.startswith("_")}})
        if not c["PASS"]:
            rc = 1
            for label, idx in (("research-only", c["_only_ref"]),
                               ("cleanroom-only", c["_only_got"])):
                if len(idx):
                    print(f"  [{sym}] days {label}: "
                          f"{[str(x.date()) for x in idx[:10]]}"
                          f"{' ...' if len(idx) > 10 else ''}")
            bad = c["_diff"][c["_diff"] > args.tol]
            if len(bad):
                print(f"  [{sym}] {len(bad)} days over tolerance, worst 10:")
                print(bad.sort_values(ascending=False).head(10).to_string())
        pd.DataFrame({"research": ref[sym], "cleanroom": got[sym]}).to_csv(
            os.path.join(OUT, f"parity_daily_{sym}.csv"))
        logs[sym].to_csv(os.path.join(OUT, f"decision_log_{sym}.csv"))
        trades[sym].to_csv(os.path.join(OUT, f"trade_log_{sym}.csv"), index=False)
    ptab = pd.DataFrame(prows)
    print(ptab.to_string(index=False))
    ptab.to_csv(os.path.join(OUT, "parity_summary.csv"), index=False)
    print(f"\n  tolerance {args.tol:g} -> "
          f"{'PARITY PASS' if ptab['PASS'].all() else 'PARITY FAIL'}")

    print()
    print("=" * 92)
    print("B. REBUILD band_lab/out/v14_*.csv FROM THE CLEAN-ROOM SERIES")
    print("=" * 92)
    dtab = diff_tables(rebuild_v14(got))
    print(dtab.to_string(index=False))
    dtab.to_csv(os.path.join(OUT, "v14_table_diff.csv"), index=False)
    if not (dtab["status"] == "IDENTICAL").all():
        rc = 1

    if not args.skip_delta:
        print()
        print("=" * 92)
        print("C. SPEC-LITERAL vs RESEARCH-COMPAT — cost of each ambiguity in §2")
        print("=" * 92)
        dl = delta_attribution()
        print(dl.to_string(index=False))
        dl.to_csv(os.path.join(OUT, "spec_vs_research_attribution.csv"), index=False)

        for sym in SLEEVES:
            log, on, tr = run_sleeve(sym, SPEC_LITERAL)
            log.to_csv(os.path.join(OUT, f"spec_literal_decision_log_{sym}.csv"))
            tr.to_csv(os.path.join(OUT, f"spec_literal_trade_log_{sym}.csv"),
                      index=False)
            on.to_csv(os.path.join(OUT, f"spec_literal_daily_{sym}.csv"))

    print()
    print("=" * 92)
    print("D. §8 LIVE-VS-BACKTEST MONITORING EXPECTATIONS, MEASURED")
    print("=" * 92)
    mon = monitoring_check(got)
    print(mon.T.to_string())
    mon.to_csv(os.path.join(OUT, "monitoring_expectations.csv"), index=False)

    print(f"\nwrote {OUT}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
