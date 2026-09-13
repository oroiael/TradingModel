"""The decision logic, including the ways it must fail closed."""
import math

import pytest

import core
from constants import COVER_MULTIPLE, COVER_SYMBOL, FLAT, PRIMARY_MULTIPLE, PRIMARY_SYMBOL


def sig(sym="SOXL", rv=50.0, cut=100.0):
    return core.Signal(sym, rv, cut)


# ---------------------------------------------------------------- eligibility

def test_below_the_cut_is_eligible():
    assert sig(rv=99.9, cut=100.0).eligible


def test_at_the_cut_is_NOT_eligible():
    """`<` not `<=`. On a tie the instrument sits out, matching the research."""
    assert not sig(rv=100.0, cut=100.0).eligible


def test_above_the_cut_is_not_eligible():
    assert not sig(rv=100.1, cut=100.0).eligible


@pytest.mark.parametrize("rv,cut", [(None, 100.0), (50.0, None), (None, None)])
def test_missing_inputs_fail_CLOSED(rv, cut):
    """Burn-in and data gaps must both produce 'hold nothing', never 'hold'."""
    assert not core.Signal("X", rv, cut).eligible


def test_margin_is_signed_distance_and_none_when_unknown():
    assert sig(rv=90.0, cut=100.0).margin == pytest.approx(10.0)
    assert sig(rv=110.0, cut=100.0).margin == pytest.approx(-10.0)
    assert core.Signal("X", None, 100.0).margin is None


# ------------------------------------------------------------------- decision

def test_primary_wins_when_both_are_eligible():
    d = core.decide(sig(PRIMARY_SYMBOL, 50, 100), sig(COVER_SYMBOL, 10, 20))
    assert d.leg == PRIMARY_SYMBOL
    assert d.multiple == PRIMARY_MULTIPLE


def test_cover_only_when_primary_is_benched():
    d = core.decide(sig(PRIMARY_SYMBOL, 150, 100), sig(COVER_SYMBOL, 10, 20))
    assert d.leg == COVER_SYMBOL
    assert d.multiple == COVER_MULTIPLE


def test_flat_when_neither_qualifies():
    d = core.decide(sig(PRIMARY_SYMBOL, 150, 100), sig(COVER_SYMBOL, 30, 20))
    assert d.leg == FLAT
    assert d.multiple == 0.0
    assert d.is_flat


def test_legs_are_mutually_exclusive_over_the_whole_truth_table():
    """There is no input pair that holds both. Gross notional is 1x or 3x, never 4x."""
    for prv in (50, 150):
        for crv in (10, 30):
            d = core.decide(sig(PRIMARY_SYMBOL, prv, 100), sig(COVER_SYMBOL, crv, 20))
            assert d.multiple in (0.0, PRIMARY_MULTIPLE, COVER_MULTIPLE)
            assert d.leg in (FLAT, PRIMARY_SYMBOL, COVER_SYMBOL)


def test_burn_in_holds_nothing():
    d = core.decide(core.Signal(PRIMARY_SYMBOL, 50.0, None),
                    core.Signal(COVER_SYMBOL, 10.0, None))
    assert d.is_flat


def test_describe_mentions_both_instruments():
    d = core.decide(sig(PRIMARY_SYMBOL, 50, 100), sig(COVER_SYMBOL, 30, 20))
    text = d.describe()
    assert PRIMARY_SYMBOL in text and COVER_SYMBOL in text


# --------------------------------------------------------------------- sizing

def test_target_shares_rounds_down():
    """Under-fill against target, never unplanned leverage."""
    assert core.target_shares(1000.0, 1.0, 300.0) == 3        # 3.33 -> 3
    assert core.target_shares(1000.0, 3.0, 42.38) == 70       # 70.78 -> 70


@pytest.mark.parametrize("eq,mult,px", [(0, 1, 100), (-5, 1, 100),
                                        (1000, 0, 100), (1000, 1, 0)])
def test_target_shares_degenerate_inputs_are_zero(eq, mult, px):
    assert core.target_shares(eq, mult, px) == 0


# ----------------------------------------------------------------- commission

def test_commission_uses_per_share_rate_above_100_shares():
    assert core.commission(1000, 122.28) == pytest.approx(3.50)


def test_the_035_MINIMUM_binds_below_100_shares():
    """§3.5's whole point: 9 shares pay $0.35, not $0.0315."""
    assert core.commission(9, 122.28) == pytest.approx(0.35)
    assert core.commission(99, 122.28) == pytest.approx(0.35)
    assert core.commission(100, 122.28) == pytest.approx(0.35)  # exactly at the knee


def test_one_percent_cap_binds_on_penny_prices():
    # 1000 shares at $0.10 = $100 notional; per-share would be $3.50, cap is $1.00
    assert core.commission(1000, 0.10) == pytest.approx(1.00)


def test_no_shares_no_commission():
    assert core.commission(0, 122.28) == 0.0


def test_round_trip_cost_is_quoted_against_equity_not_notional():
    """The cover leg runs at 3x notional; quoting against notional understates it."""
    bps = core.round_trip_cost_bps(shares=1000, entry=42.38, exit_=42.50,
                                   equity=1000 * 42.38 / 3.0)
    # two orders of ~$3.50 on ~$14,127 of equity
    assert bps == pytest.approx(4.96, abs=0.05)


# -------------------------------------------------------------------- returns

def test_net_on_equity_scales_gross_and_cost_by_the_multiple():
    net = core.net_on_equity(0.01, 3.0, 0.83)
    assert net == pytest.approx(3.0 * 0.01 - 3.0 * 2 * 0.83 / 1e4)


def test_a_flat_night_costs_exactly_nothing():
    """No order placed, no commission charged. Must be exactly 0.0."""
    assert core.net_on_equity(0.05, 0.0, 0.83) == 0.0


def test_net_return_from_a_fill_pair_matches_the_primitive():
    a = core.net_return(100.0, 101.0, 1.0, 0.29)
    b = core.net_on_equity(0.01, 1.0, 0.29)
    assert a == pytest.approx(b)
