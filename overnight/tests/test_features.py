"""Feature arithmetic, and the two places a silent error would trade wrong nights."""
import datetime as dt
import math

import pytest

import features
from constants import ANNUALISATION, MIN_HISTORY, RV_LAG, RV_WINDOW


def series(closes, start=dt.date(2024, 1, 2)):
    """Sessions on consecutive weekdays with open == close (opens unused here)."""
    out, day = [], start
    for c in closes:
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        out.append(features.Session(day, c, c))
        day += dt.timedelta(days=1)
    return out


# --------------------------------------------------------------- percentile

def test_percentile_interpolates_linearly():
    xs = [1.0, 2.0, 3.0, 4.0]
    assert features.percentile(xs, 0) == 1.0
    assert features.percentile(xs, 100) == 4.0
    assert features.percentile(xs, 50) == pytest.approx(2.5)
    assert features.percentile(xs, 60) == pytest.approx(2.8)


def test_percentile_is_order_independent():
    a = features.percentile([5, 1, 4, 2, 3], 60)
    b = features.percentile([1, 2, 3, 4, 5], 60)
    assert a == pytest.approx(b)


@pytest.mark.parametrize("np_p,expected", [(25, 1.75), (75, 3.25)])
def test_percentile_matches_numpy_linear_convention(np_p, expected):
    """numpy.percentile default agrees; numpy is not a live dependency, so pin it."""
    assert features.percentile([1.0, 2.0, 3.0, 4.0], np_p) == pytest.approx(expected)


# ---------------------------------------------------------------- threshold

def test_threshold_is_none_until_min_history():
    assert features.threshold_at([1.0] * (MIN_HISTORY - 1)) is None
    assert features.threshold_at([1.0] * MIN_HISTORY) is not None


def test_threshold_uses_only_what_it_is_given():
    """It has no access to 'now' — leakage can only come from the caller."""
    hist = list(range(MIN_HISTORY))
    assert features.threshold_at(hist) == pytest.approx(
        features.percentile(hist, 60.0))


# ------------------------------------------------------- THE LAG. read this.

def test_window_end_index_excludes_the_decision_day():
    assert features.window_end_index(100, lag=1) == 99
    assert features.window_end_index(100, lag=0) == 100


def test_realised_vol_does_NOT_see_the_decision_day_move():
    """The load-bearing test of this module.

    An MOC must be in by 15:50, so day D's close cannot reach the decision that
    submits it. Here every prior return is identical (zero dispersion) and day
    D's is enormous. With the specified lag the RV is 0; if the lag were ever
    dropped to 0 the huge move would leak in and the RV would be large.
    """
    closes = [100.0 * (1.01 ** k) for k in range(RV_WINDOW + 2)]
    closes.append(closes[-1] * 2.0)               # +100% on the decision day
    rets = features.close_to_close(series(closes))
    d = len(closes) - 1                            # the decision day's index

    assert features.realised_vol(rets, d, lag=RV_LAG) == pytest.approx(0.0, abs=1e-9)
    leaked = features.realised_vol(rets, d, lag=0)
    assert leaked > 100.0, "a lag of 0 must visibly leak; if not, the test is blind"


def test_realised_vol_annualises_as_specified():
    closes = [100.0]
    for k in range(RV_WINDOW + 2):
        closes.append(closes[-1] * (1.02 if k % 2 == 0 else 1 / 1.02))
    rets = features.close_to_close(series(closes))
    d = len(closes) - 1
    got = features.realised_vol(rets, d)
    from statistics import stdev
    end = d - RV_LAG
    want = stdev(rets[end - RV_WINDOW:end]) * math.sqrt(ANNUALISATION) * 100
    assert got == pytest.approx(want)


def test_realised_vol_is_none_when_history_is_short():
    rets = features.close_to_close(series([100.0, 101.0, 102.0]))
    assert features.realised_vol(rets, 2) is None


# --------------------------------------------------------------------- build

def test_build_emits_no_row_before_the_window_fits():
    closes = [100.0 + k for k in range(RV_WINDOW + 5)]
    rows = features.build(series(closes))
    assert min(r_i for r_i, _ in enumerate(closes)
               if closes[r_i] is not None) == 0        # sanity
    assert len(rows) <= len(closes) - RV_WINDOW - RV_LAG - 1


def test_build_thresholds_are_none_during_burn_in_then_appear():
    closes = [100.0 * (1 + 0.001 * ((k * 7) % 13 - 6)) ** 1 for k in range(200)]
    running = [100.0]
    for k in range(1, 200):
        running.append(running[-1] * (1 + 0.002 * ((k * 7) % 13 - 6)))
    rows = features.build(series(running))
    ordered = [rows[d] for d in sorted(rows)]
    assert ordered[0].threshold is None
    assert ordered[-1].threshold is not None
    first_cut = next(i for i, r in enumerate(ordered) if r.threshold is not None)
    assert first_cut == MIN_HISTORY


def test_build_never_lets_a_day_set_its_own_threshold():
    """Regression guard for the subtlest possible leak in this strategy."""
    running = [100.0]
    for k in range(1, 250):
        running.append(running[-1] * (1 + 0.003 * ((k * 11) % 17 - 8)))
    sess = series(running)
    rows = features.build(sess)
    ordered = [rows[d] for d in sorted(rows)]
    seen: list[float] = []
    for r in ordered:
        expected = features.threshold_at(seen)
        assert r.threshold == expected or (r.threshold is None and expected is None)
        seen.append(r.rv)


def test_build_records_the_overnight_return_from_the_next_open():
    sess = [features.Session(dt.date(2024, 1, 2) + dt.timedelta(days=k),
                             open=100.0 + k, close=200.0 + k)
            for k in range(RV_WINDOW + 5)]
    rows = features.build(sess)
    r = rows[sorted(rows)[0]]
    i = next(k for k, s in enumerate(sess) if s.date == r.date)
    assert r.overnight_return == pytest.approx(sess[i + 1].open / sess[i].close - 1)
    assert r.next_date == sess[i + 1].date
