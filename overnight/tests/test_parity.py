"""P0's gate, and proof that the gate can fail.

A parity harness that passes on the first run is worth exactly nothing until it
has been shown to detect a wrong answer. Each mutation below changes one part of
the specification and asserts the gate goes red. If any of them ever passes, the
gate has stopped testing and these tests are the alarm.
"""
import pytest

import core
import features
import parity


@pytest.mark.slow
def test_the_gate_passes_on_the_real_history():
    assert parity.main() == 0


@pytest.mark.slow
def test_replay_shape_matches_the_research_ledger():
    mine, theirs = parity.replay(), parity.load_ledger()
    assert len(mine) == len(theirs) == 895
    legs = {}
    for r in mine:
        legs[r["leg"]] = legs.get(r["leg"], 0) + 1
    assert legs == {"SOXL": 580, "XLU": 204, "FLAT": 111}


@pytest.mark.slow
def test_every_decision_holds_at_most_one_leg():
    for r in parity.replay():
        assert r["decision"].multiple in (0.0, 1.0, 3.0)


# ------------------------------------------------------------------ mutations

@pytest.mark.slow
def test_gate_FAILS_if_the_percentile_arithmetic_shifts(monkeypatch):
    """Move the cut by 1% and different nights trade."""
    orig = features.percentile
    monkeypatch.setattr(features, "percentile",
                        lambda xs, p: orig(xs, p) * 1.01)
    assert parity.main() == 1


@pytest.mark.slow
def test_gate_FAILS_if_the_cost_assumption_changes(monkeypatch):
    """Same legs, different returns — the gate must catch the P&L too."""
    monkeypatch.setattr(parity, "PRIMARY_COST_BPS", 1.29)
    assert parity.main() == 1


@pytest.mark.slow
def test_gate_FAILS_if_the_rv_window_stops_lagging(monkeypatch):
    """The look-ahead the whole design turns on. Dropping the lag must go red."""
    monkeypatch.setattr(features, "window_end_index",
                        lambda i, lag=0: i)
    assert parity.main() == 1


@pytest.mark.slow
def test_gate_FAILS_if_leg_precedence_is_reversed(monkeypatch):
    """Cover-before-primary is a different strategy and must not pass."""
    def flipped(primary, cover):
        if cover.eligible:
            return core.Decision(cover.symbol, 3.0, primary, cover)
        if primary.eligible:
            return core.Decision(primary.symbol, 1.0, primary, cover)
        return core.Decision("FLAT", 0.0, primary, cover)
    monkeypatch.setattr(core, "decide", flipped)
    assert parity.main() == 1
