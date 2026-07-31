"""
Stage 1 — the equivalence proof.

`PHASE2_PLAN.md` §3: the live state machine must reproduce
`phase1/spec_engine.py` decision for decision on the historical bars, so that
a live shortfall can be attributed to fills rather than to a coding error.
This file is that proof, and it is a regression gate: if a later stage
changes what the sleeve decides, this goes red before anything reaches IBKR.

The comparison is against `SPEC_LITERAL` — the specification as it stands,
which is what the live engine implements — not `RESEARCH_COMPAT`. The two
differ by the four residual rules in PHASE1_PARITY.md §4.

Run:  python3 -m pytest band_lab/live -v
      python3 -m pytest band_lab/live -v -m "not slow"    (skip these)
"""

from __future__ import annotations

import numpy as np
import pytest

from replay import FILL_MODELS, backtest_config, load_sessions, replay_symbol
from spec_engine import SPEC_LITERAL, run_sleeve

pytestmark = pytest.mark.slow

# PHASE1_PARITY.md §4 — the as-built (SPEC_LITERAL) series the live engine
# inherits. Quoted in PHASE2_PLAN.md §7 and asserted here so the documents
# cannot drift away from the code.
PUBLISHED = {
    "SOXL": dict(on_days=779, bp=65.9, sharpe=3.14),
    "SOXS": dict(on_days=793, bp=61.2, sharpe=2.83),
}

_cache: dict = {}


def both(symbol):
    if symbol not in _cache:
        ref = run_sleeve(symbol, SPEC_LITERAL)
        live = replay_symbol(symbol, backtest_config(symbol))
        _cache[symbol] = (ref, live)
    return _cache[symbol]


@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_on_day_sets_are_identical(symbol):
    (_, ref_on, _), (_, live_on, _) = both(symbol)
    assert list(ref_on.index) == list(live_on.index)


@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_daily_pnl_series_is_identical(symbol):
    (_, ref_on, _), (_, live_on, _) = both(symbol)
    assert float((ref_on - live_on).abs().max()) < 1e-12


@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_gate_and_filter_reasons_are_identical(symbol):
    (ref_log, _, _), (live_log, _, _) = both(symbol)
    assert (ref_log["gate_reason"] == live_log["gate_reason"]).all()
    assert (ref_log["filter_reason"] == live_log["filter_reason"]).all()
    assert (ref_log["fills"] == live_log["fills"]).all()
    assert (ref_log["stop_outs"] == live_log["stop_outs"]).all()


@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_features_match_the_pandas_implementation(symbol):
    """FeatureHistory is incremental; spec_engine's is a pandas rolling window."""
    (ref_log, _, _), (live_log, _, _) = both(symbol)
    for col, tol in (("atr5", 1e-12), ("thr80", 1e-12),
                     ("or30", 1e-12), ("pos10", 1e-12)):
        assert float((ref_log[col] - live_log[col]).abs().max()) < tol, col


@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_every_trade_matches(symbol):
    (_, _, ref_tr), (_, _, live_tr) = both(symbol)
    assert len(ref_tr) == len(live_tr)
    for col in ("entry_bar", "exit_bar", "outcome"):
        assert (ref_tr[col].to_numpy() == live_tr[col].to_numpy()).all(), col
    for col in ("entry_px", "exit_px", "qty", "ret"):
        assert float((ref_tr[col] - live_tr[col]).abs().max()) < 1e-9, col


@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_published_as_built_numbers(symbol):
    (_, _, _), (_, live_on, _) = both(symbol)
    want = PUBLISHED[symbol]
    assert len(live_on) == want["on_days"]
    assert live_on.mean() * 1e4 == pytest.approx(want["bp"], abs=0.05)
    sharpe = live_on.mean() / live_on.std() * np.sqrt(252)
    assert sharpe == pytest.approx(want["sharpe"], abs=0.01)


@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_worst_day_is_the_structural_minus_eight_percent(symbol):
    """§2.7's breaker converts the worst possible day to two 4% stops."""
    (_, _, _), (_, live_on, _) = both(symbol)
    assert live_on.min() == pytest.approx(-0.08, abs=0.001)


@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_no_entry_is_ever_priced_above_its_anchor_dip(symbol):
    """§2.5 invariant, asserted over every historical trade."""
    (_, _, _), (_, _, live_tr) = both(symbol)
    assert (live_tr["entry_px"] <= live_tr["limit_px"] + 1e-9).all()


@pytest.mark.parametrize("symbol", ["SOXL", "SOXS"])
def test_conservative_fill_models_run_and_are_not_better(symbol):
    """S10 — the same-bar re-entry sensitivity is a standing diagnostic.

    No claim about which model is right; only that the spec model is the most
    optimistic of the three, which is what makes it the wrong planning case.
    """
    sessions = load_sessions(symbol)
    edges = {}
    for model in FILL_MODELS:
        _, on, _ = replay_symbol(symbol, backtest_config(symbol),
                                 sessions=sessions, fill_model=model)
        edges[model] = on.mean() * 1e4
    assert edges["spec"] > edges["no_better"]
    assert edges["spec"] > edges["next_bar"]
