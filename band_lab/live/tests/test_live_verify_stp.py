"""
§6.1 — tests for the probe that settles it.

The failure this must not have is a false CONFIRMED. §6.1 gates unattended
operation, so a probe that reports "the stop survived" when nothing was held,
or when it simply failed to ask TWS for other clients' orders, would retire the
last safety-critical unknown on no evidence at all. `PROJECT_STATUS.md` §4.7
names that mistake twice — defects 6 and 7 were both checks that concluded from
an absence of evidence, and each cost a session.
"""

from __future__ import annotations

import json

import pytest

from broker import FakeIB
from verify_stp import (
    CLIENT_ID_OFFSET,
    probe,
    render,
    snapshot,
    verdict,
)

SYMS = ("SOXL", "SOXS")


def held(qty=500.0, stop=500.0, symbol="SOXL") -> FakeIB:
    """A sleeve holding `qty` with a SELL STP covering `stop` of it."""
    ib = FakeIB(symbols=SYMS)
    ib.positions[symbol] = qty
    if stop:
        ib.place_stop(symbol, "SELL", stop, 96.0, f"20260813-{symbol}-S-1",
                      oca_group="g1")
    return ib


# --------------------------------------------------------------- the probe
def test_the_probe_asks_tws_before_reading_its_own_copy():
    """`reqAllOpenOrders` is the *cross-client* request (TWS docs p84); this
    probe is by design a different client from the one that placed the bracket,
    so without the refresh it would read its own empty book and call that
    'no stop'."""
    ib = held()
    assert ib.refreshes == 0
    probe(ib, SYMS)
    assert ib.refreshes == 1


def test_a_ghost_order_is_seen_only_because_of_the_refresh():
    """The state a non-warning error leaves behind: TWS still holds the order,
    the client has buried it. If that is the stop, the difference between
    'gone' and 'invisible to this client' is the whole question."""
    ib = held()
    (order_id,) = list(ib.orders)
    ib.hide(order_id)
    assert ib.working_orders("SOXL") == []          # invisible before refresh
    p = probe(ib, SYMS)
    assert p["SOXL"].stop_qty == 500.0
    assert p["SOXL"].covered


def test_a_covered_position_reads_covered():
    p = probe(held(500.0, 500.0), SYMS)
    assert p["SOXL"].exposed and p["SOXL"].covered
    assert p["SOXS"].exposed is False


def test_a_partially_covered_position_is_not_covered():
    """Defect 8's signature: 241 of 541 shares with no protective stop."""
    p = probe(held(541.0, 300.0), SYMS)
    assert p["SOXL"].exposed and not p["SOXL"].covered


def test_coverage_is_sized_on_remaining_not_nominal():
    """A partially filled stop protects only what is left of it."""
    ib = held(500.0, 500.0)
    (oid,) = list(ib.orders)
    ib.orders[oid].filled = 200.0
    p = probe(ib, SYMS)
    assert p["SOXL"].stop_qty == 300.0
    assert not p["SOXL"].covered


def test_a_resting_buy_limit_is_not_protection():
    """Only a SELL STP protects a long. Counting the entry would report every
    armed sleeve as safe."""
    ib = FakeIB(symbols=SYMS)
    ib.positions["SOXL"] = 500.0
    ib.place_limit("SOXL", "BUY", 500.0, 99.0, "20260813-SOXL-E-1")
    p = probe(ib, SYMS)
    assert p["SOXL"].stop_qty == 0.0 and not p["SOXL"].covered


def test_a_sell_limit_target_is_not_protection():
    """The target is the OTHER bracket leg. It is not a stop and does not cap
    the loss — counting it would call a naked long protected."""
    ib = FakeIB(symbols=SYMS)
    ib.positions["SOXL"] = 500.0
    ib.place_limit("SOXL", "SELL", 500.0, 101.0, "20260813-SOXL-T-1")
    p = probe(ib, SYMS)
    assert p["SOXL"].stop_qty == 0.0 and not p["SOXL"].covered


def test_the_probe_places_nothing():
    ib = held()
    before = dict(ib.orders)
    probe(ib, SYMS)
    probe(ib, SYMS)
    assert ib.orders == before
    assert ib.global_cancels == 0


# ---------------------------------------------------------------- verdicts
def _snap(ib, label):
    return snapshot(probe(ib, SYMS), label)


def test_the_stop_surviving_is_confirmed():
    before = _snap(held(500.0, 500.0), "before")
    after = _snap(held(500.0, 500.0), "after")
    v, _ = verdict(before, after)
    assert v == "CONFIRMED"
    assert "CONFIRMED" in render(before, after)


def test_the_stop_vanishing_is_refuted_and_says_what_to_do():
    before = _snap(held(500.0, 500.0), "before")
    after = _snap(held(500.0, 0.0), "after")          # position kept, stop gone
    v, _ = verdict(before, after)
    assert v == "REFUTED"
    text = render(before, after)
    assert "UNPROTECTED" in text
    assert "Flatten by hand" in text


def test_a_flat_sleeve_is_inconclusive_not_confirmed():
    """The false-CONFIRMED this file exists to prevent. Nothing was held, so
    nothing was tested — reporting success here retires §6.1 on no evidence."""
    before = _snap(FakeIB(symbols=SYMS), "before")
    after = _snap(FakeIB(symbols=SYMS), "after")
    v, _ = verdict(before, after)
    assert v == "INCONCLUSIVE"
    assert "CONFIRMED" not in render(before, after)


def test_a_position_that_closed_between_snapshots_is_inconclusive():
    """The bracket may simply have filled. That is not evidence either way."""
    before = _snap(held(500.0, 500.0), "before")
    after = _snap(FakeIB(symbols=SYMS), "after")
    v, lines = verdict(before, after)
    assert v == "INCONCLUSIVE"
    assert any("may simply have filled" in ln for ln in lines)


def test_an_uncovered_position_before_the_kill_is_called_out_separately():
    """If the bracket did not cover the position while the engine was still up,
    the kill tests nothing — and the real finding is defect 8, not §6.1."""
    before = _snap(held(541.0, 300.0), "before")
    after = _snap(held(541.0, 300.0), "after")
    v, lines = verdict(before, after)
    assert v == "INCONCLUSIVE"
    assert any("before the kill" in ln for ln in lines)


def test_one_sleeve_losing_its_stop_refutes_even_if_the_other_holds():
    ib_b = held(500.0, 500.0)
    ib_b.positions["SOXS"] = 800.0
    ib_b.place_stop("SOXS", "SELL", 800.0, 38.0, "20260813-SOXS-S-1")
    before = _snap(ib_b, "before")

    ib_a = held(500.0, 500.0)              # SOXL keeps its stop
    ib_a.positions["SOXS"] = 800.0         # SOXS keeps the shares, loses the stop
    after = _snap(ib_a, "after")

    assert verdict(before, after)[0] == "REFUTED"


def test_a_missing_sleeve_in_the_after_snapshot_is_reported():
    before = _snap(held(500.0, 500.0), "before")
    after = {"label": "after", "ts": "x", "sleeves": {}}
    v, lines = verdict(before, after)
    assert v == "INCONCLUSIVE"
    assert any("not present" in ln for ln in lines)


# ------------------------------------------------------------- mechanics
def test_the_snapshot_round_trips_through_json():
    """The two halves are taken by different processes minutes apart, so the
    file is the only channel between them."""
    snap = _snap(held(500.0, 500.0), "before")
    reloaded = json.loads(json.dumps(snap))
    assert verdict(reloaded, reloaded)[0] == "CONFIRMED"


def test_the_probe_client_id_cannot_collide_with_diagnose():
    """`diagnose.py` uses +50 and states it must never clash with a running
    engine. These two must also not clash with each other, or running both
    during the one session that can answer §6.1 fails on error 326."""
    assert CLIENT_ID_OFFSET != 50 and CLIENT_ID_OFFSET > 0


def test_importing_the_probe_never_needs_ib_async():
    """`ib_async` is imported inside `main`, so the whole verdict path is
    testable — which is what makes a false CONFIRMED catchable at all."""
    import subprocess
    import sys as _sys
    import os as _os
    import verify_stp
    code = ("import sys; sys.path.insert(0, %r); import verify_stp; "
            "print('ib_async' in sys.modules)"
            % _os.path.dirname(_os.path.abspath(verify_stp.__file__)))
    res = subprocess.run([_sys.executable, "-c", code],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "False"
