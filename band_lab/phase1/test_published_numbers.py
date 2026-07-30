"""
Every load-bearing number published in the specification documents, checked
against the engine that produced it.

`IMPLEMENTATION_SPEC.md`, `STRATEGY_SPEC.md` and `MASTER_STRATEGY_DOCUMENT.md`
quote concrete figures — the residual as-built gap, the tick-grid value, the
cost per round trip, the account size at which IBKR's $1 order minimum stops
binding. Phase 1 found that documents drift: §8's monitoring baselines had
been wrong long enough to be quoted in three places. These tests exist so
that cannot happen again silently.

If one fails, either the engine changed or the document is stale. Fix
whichever is wrong — do not relax the tolerance.

The §8 monitoring table itself is guarded separately, by `parity.py`
section D, which fails the whole run when it drifts.

Run:  python3 -m pytest band_lab/phase1/test_published_numbers.py -v
"""

from __future__ import annotations

import dataclasses as dc
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BAND_LAB = os.path.dirname(HERE)
ROOT = os.path.dirname(BAND_LAB)
for p in (HERE, BAND_LAB, os.path.join(ROOT, "cycle_lab")):
    if p not in sys.path:
        sys.path.insert(0, p)

from cost_model import (CURRENT_PX, CostConfig, daily_cost_series,
                        v14_flat_cost_bp)
from spec_engine import RESEARCH_COMPAT, SPEC_LITERAL, load_bars, run_sleeve

pytestmark = pytest.mark.slow


def _have_data() -> bool:
    return all(os.path.exists(os.path.join(ROOT, f"{s}_5min_6Years.csv"))
               and os.path.getsize(os.path.join(ROOT, f"{s}_5min_6Years.csv")) > 10_000
               for s in ("SOXL", "SOXS"))


@pytest.fixture(scope="module", autouse=True)
def _require_data():
    if not _have_data():
        pytest.skip("5-minute history unavailable (git lfs pull)")


@pytest.fixture(scope="module")
def sleeves():
    out = {}
    for sym in ("SOXL", "SOXS"):
        log, on, tr = run_sleeve(sym, RESEARCH_COMPAT)
        out[sym] = {"log": log, "on": on, "trades": tr}
    return out


# ------------------------------------- IMPLEMENTATION_SPEC.md §9, Phase 1
@pytest.mark.parametrize("symbol,published_days", [("SOXL", 787), ("SOXS", 801)])
def test_published_on_day_counts(sleeves, symbol, published_days):
    """§9: 'parity holds exactly -- 787 SOXL and 801 SOXS ON-days'."""
    assert len(sleeves[symbol]["on"]) == published_days


@pytest.mark.parametrize("symbol,published_gap", [("SOXL", 0.3), ("SOXS", 3.5)])
def test_published_as_built_gap(sleeves, symbol, published_gap):
    """§9: 'worth +0.3 bp/ON-day on SOXL and +3.5 on SOXS'.

    Measured as one combined run, which is the honest way to state it --
    the singles do not add.
    """
    _, spec, _ = run_sleeve(symbol, SPEC_LITERAL)
    gap = (spec.mean() - sleeves[symbol]["on"].mean()) * 1e4
    assert round(gap, 1) == pytest.approx(published_gap, abs=0.05)


def test_published_tick_grid_value(sleeves):
    """§2.5 and §9: 'modelling the cent grid is worth +4.3 bp/ON-day on
    SOXL ... ~6.5% of the sleeve's edge'."""
    base = sleeves["SOXL"]["on"]
    _, rounded, _ = run_sleeve("SOXL", dc.replace(RESEARCH_COMPAT, tick_rounding=True))
    delta_bp = (rounded.mean() - base.mean()) * 1e4
    assert round(delta_bp, 1) == pytest.approx(4.3, abs=0.05)
    assert round(delta_bp / (base.mean() * 1e4) * 100, 1) == pytest.approx(6.5, abs=0.05)


# --------------------------------------------- IMPLEMENTATION_SPEC.md §4
def test_published_soxs_back_adjusted_hazard():
    """§4: the back-adjusted series runs '$1,118,404 per share at the start
    ... to $51.61 at the end (peak $1,171,205)', and whole-share sizing
    deletes '248 of 1,508 sessions'."""
    px = load_bars("SOXS").groupby("date")["Close"].last()
    assert len(px) == 1508
    assert round(px.iloc[0]) == 1_118_404
    assert round(px.max()) == 1_171_205
    assert round(px.iloc[-1], 2) == pytest.approx(51.61, abs=0.005)
    assert int((np.floor(150_000 / px) == 0).sum()) == 248


# ---------------------------- COST_MODEL.md / STRATEGY_SPEC / MASTER doc
@pytest.mark.parametrize("symbol,cost_bp,rt_bp,cross_pct,net_flat_bp", [
    ("SOXL", 3.2, 0.92, 28.7, 61.9),
    ("SOXS", 8.5, 2.25, 28.2, 48.1),
])
def test_published_cost_figures(sleeves, symbol, cost_bp, rt_bp, cross_pct,
                                net_flat_bp):
    s, px, cfg = sleeves[symbol], CURRENT_PX[symbol], CostConfig()
    per_day = daily_cost_series(s["trades"], px, cfg, s["on"].index)
    assert round(per_day.mean() * 1e4, 1) == pytest.approx(cost_bp, abs=0.05)

    from cost_model import trade_cost_usd, SLEEVE_CAPITAL
    target_rt = trade_cost_usd(px, "target", cfg)["total"] / SLEEVE_CAPITAL * 1e4
    assert round(target_rt, 2) == pytest.approx(rt_bp, abs=0.005)

    crossing = s["trades"]["outcome"].isin(("stop", "flatten")).mean() * 100
    assert round(crossing, 1) == pytest.approx(cross_pct, abs=0.05)

    tpd = s["log"].loc[s["log"]["traded"], "fills"].mean()
    net = s["on"].mean() * 1e4 - v14_flat_cost_bp(px, tpd)
    assert round(net, 1) == pytest.approx(net_flat_bp, abs=0.05)


def test_published_order_minimum_binding_point(sleeves):
    """STRATEGY_SPEC: the $1.00 minimum stops binding at '200 shares
    ~ $31,700 of sleeve capital', and §9/Phase 3: SOXL costs '4.0 bp/ON-day
    at $22.5K and 7.5 bp at $10K, against 3.2 bp at full size'."""
    cfg = CostConfig()
    assert cfg.commission_min_per_order / cfg.commission_per_share == 200
    assert round(200 * CURRENT_PX["SOXL"]) == 31_682

    s, px = sleeves["SOXL"], CURRENT_PX["SOXL"]
    for capital, published in ((10_000, 7.5), (22_500, 4.0), (150_000, 3.2)):
        d = daily_cost_series(s["trades"], px, cfg, s["on"].index, capital=capital)
        assert round(d.mean() * 1e4, 1) == pytest.approx(published, abs=0.05), capital


def test_published_cost_sensitivity_ranges(sleeves):
    """COST_MODEL.md §4: across the sensitivity grid 'SOXL moves 2.3 bp and
    SOXS moves 7.3 bp' -- the claim that all cost risk sits in SOXS."""
    best = CostConfig(spread_cents=1.0)
    worst = CostConfig(spread_cents=5.0, stop_slippage_cents=2.0,
                       flatten_slippage_cents=2.0)
    for symbol, published_range in (("SOXL", 2.3), ("SOXS", 7.3)):
        s, px = sleeves[symbol], CURRENT_PX[symbol]
        lo = (s["on"] - daily_cost_series(s["trades"], px, best, s["on"].index)).mean()
        hi = (s["on"] - daily_cost_series(s["trades"], px, worst, s["on"].index)).mean()
        assert round((lo - hi) * 1e4, 1) == pytest.approx(published_range, abs=0.05)


def test_published_w_plateau_is_cost_model_independent(sleeves):
    """COST_MODEL.md §5 and §2.9: w = 0.50 is the Sharpe argmax under every
    cost scenario tested, including a stressed one."""
    import pandas as pd
    for cfg in (CostConfig(), CostConfig(spread_cents=5.0,
                                         stop_slippage_cents=2.0,
                                         flatten_slippage_cents=2.0)):
        nets = {}
        for sym in ("SOXL", "SOXS"):
            s, px = sleeves[sym], CURRENT_PX[sym]
            nets[sym] = s["on"] - daily_cost_series(s["trades"], px, cfg,
                                                    s["on"].index)
        cal = pd.date_range(min(n.index.min() for n in nets.values()),
                            max(n.index.max() for n in nets.values()), freq="B")
        a = nets["SOXL"].reindex(cal).fillna(0.0)
        b = nets["SOXS"].reindex(cal).fillna(0.0)
        sharpes = {w: (r.mean() / r.std() * np.sqrt(252))
                   for w in np.arange(0, 1.0001, 0.125)
                   for r in [w * a + (1 - w) * b]}
        assert max(sharpes, key=sharpes.get) == pytest.approx(0.5)
