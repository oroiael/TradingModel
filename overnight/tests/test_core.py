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

def test_commission_uses_per_share_rate_above_the_minimum():
    # $0.005/share + $0.000003/share clearing, FIXED schedule.
    assert core.commission(1000, 122.28) == pytest.approx(5.003)


def test_the_100_MINIMUM_binds_below_200_shares():
    """§3.5's whole point: 9 shares pay $1.00, not $0.045."""
    assert core.commission(9, 122.28) == pytest.approx(1.000027)
    assert core.commission(199, 122.28) == pytest.approx(1.000597)
    assert core.commission(200, 122.28) == pytest.approx(1.0006)  # at the knee


def test_one_percent_cap_binds_on_penny_prices():
    # 10,000 shares at $0.10 = $1,000 notional; per-share would be $50, cap is $10.
    assert core.commission(10_000, 0.10) == pytest.approx(10.03)


def test_a_sell_costs_more_than_the_buy_that_opened_it():
    """TAF and Section 31 ride on the exit only. Never treat a side as symmetric."""
    buy = core.commission(1000, 122.28, "BUY")
    sell = core.commission(1000, 122.28, "SELL")
    assert sell > buy
    assert sell - buy == pytest.approx(1000 * 0.000195 + 122_280 * 20.60e-6)


def test_no_shares_no_commission():
    assert core.commission(0, 122.28) == 0.0
    assert core.commission(0, 122.28, "SELL") == 0.0


@pytest.mark.parametrize("shares,price,expect", [
    (629, 101.264880763, 3.146887),    # SOXL 2026-09-14 MOC buy
    (218, 114.818348624, 1.090654),    # SOXL 2026-09-17 MOC buy
    (8734, 41.32, 43.696202),          # XLU  2026-09-15 MOC buy
    (8930, 41.33, 44.676790),          # XLU  2026-09-16 MOC buy
])
def test_buy_commission_reproduces_the_activity_statement(shares, price, expect):
    """Every buy in DU1790300 2026-09-14..17, to the sixth decimal.

    These are the numbers IBKR actually charged. If this test fails the cost
    model has drifted off the account's real fee schedule, which is exactly
    what went wrong for the first four live nights.
    """
    assert core.commission(shares, price, "BUY") == pytest.approx(expect, abs=1e-6)


@pytest.mark.parametrize("shares,price,expect", [
    (8734, 41.59022899, 52.882263),   # XLU  2026-09-16 MOO sell
    (8930, 41.550269877, 54.061645),  # XLU  2026-09-17 MOO sell
    (629, 104.824562798, 4.627796),   # SOXL 2026-09-15 watchdog sell
])
def test_sell_commission_reproduces_the_activity_statement(shares, price, expect):
    """Same, for the sells, and to the same tolerance as the buys.

    The two sell-side rates were fitted on exactly these three rows, so this
    is not independent confirmation of the FIT -- it is a pin on the rates.
    It earns its place because the fit had a spare degree of freedom (three
    rows, two unknowns) and still came out at zero residual: if an edit moves
    either rate, all three go red together, not one.
    """
    assert core.commission(shares, price, "SELL") == pytest.approx(expect, abs=1e-6)


def test_round_trip_cost_is_quoted_against_equity_not_notional():
    """The cover leg runs at 3x notional; quoting against notional understates it."""
    bps = core.round_trip_cost_bps(shares=1000, entry=42.38, exit_=42.50,
                                   equity=1000 * 42.38 / 3.0)
    # $5.00 in, $6.07 out, on ~$14,127 of equity
    assert bps == pytest.approx(7.84, abs=0.05)


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


# ------------------------------------------- deployed vs researched sizing

def test_decide_honours_a_deployed_cover_multiple():
    """The account trades 2.5x; the ledger is priced at 3.0x. Both must work."""
    from constants import COVER_MULTIPLE_LIVE
    d = core.decide(sig(PRIMARY_SYMBOL, 150, 100), sig(COVER_SYMBOL, 10, 20),
                    cover_multiple=COVER_MULTIPLE_LIVE)
    assert d.leg == COVER_SYMBOL
    assert d.multiple == pytest.approx(2.5)


def test_the_deployed_cover_multiple_leaves_headroom_under_a_3to1_cap():
    """At exactly 3:1 any adverse move breaches. The deployed size must be under."""
    from constants import COVER_MULTIPLE_LIVE
    assert COVER_MULTIPLE_LIVE < 3.0
    assert (3.0 / COVER_MULTIPLE_LIVE - 1) >= 0.15      # at least 15% of room


def test_defaults_still_reproduce_the_research_multiples():
    """parity.py depends on this: a deployment change must not move the gate."""
    from constants import COVER_MULTIPLE
    d = core.decide(sig(PRIMARY_SYMBOL, 150, 100), sig(COVER_SYMBOL, 10, 20))
    assert d.multiple == COVER_MULTIPLE == 3.0
