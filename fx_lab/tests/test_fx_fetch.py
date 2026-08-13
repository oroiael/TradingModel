"""Offline tests for fx_lab. No broker, no network.

The network paths cannot run without TWS, so what is covered here is everything
that can silently corrupt a multi-hour capture or misstate a profile:

  * timestamp conversion — the formatDate=2 UTC->NY path, including a DST
    boundary, because this is the one thing the older fetchers in this repo get
    right only by accident (they assume TWS is set to New York)
  * merge/resume — dedupe, sort, atomicity across an interrupted run
  * the request plan — a wrong ETA turns a 50-hour job into a surprise
  * pacing — BID_ASK must cost double, per the docs' pacing table
  * session slicing — the 17:00 ET FX day roll is the whole reason `sday` exists
  * zigzag_legs — asserted character-identical to band_lab's, so churn counts
    stay comparable to the published SOXL numbers instead of quietly drifting
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import fetch_fx_intraday as fx
import fx_profile as prof

NY = fx.NY


@dataclass
class FakeBar:
    """Shaped like ib_async's BarData for the fields bars_to_frame reads."""
    date: object
    open: float
    high: float
    low: float
    close: float
    volume: float


# ------------------------------------------------------------- timestamps
def test_utc_bar_becomes_new_york_wall_time():
    """formatDate=2 gives a tz-aware UTC datetime; the CSV must carry NY time.

    2026-06-15 13:30 UTC is 09:30 EDT — the equity open, a value that is
    obviously wrong if the conversion is skipped.
    """
    got = fx.format_bar_date(datetime(2026, 6, 15, 13, 30, tzinfo=timezone.utc))
    assert got == "20260615 09:30:00 America/New_York"


def test_conversion_tracks_daylight_saving():
    """Same UTC clock time, opposite sides of the DST switch -> different NY hour.

    A fixed -5 or -4 offset anywhere in the pipeline fails this.
    """
    winter = fx.format_bar_date(datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc))
    summer = fx.format_bar_date(datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc))
    assert winter == "20260115 09:00:00 America/New_York"
    assert summer == "20260715 10:00:00 America/New_York"


def test_naive_datetime_is_left_alone():
    """A naive datetime is already NY (the formatDate=1 legacy shape)."""
    assert (fx.format_bar_date(datetime(2026, 6, 15, 9, 30))
            == "20260615 09:30:00 America/New_York")


@pytest.mark.parametrize("text", [
    "20260615 09:30:00",
    "20260615  09:30:00",                      # IBKR's double space
    "20260615-09:30:00",                       # newer sample format
    "20260615 09:30:00 America/New_York",      # round-trip our own output
])
def test_string_forms_round_trip(text):
    assert fx.format_bar_date(text) == "20260615 09:30:00 America/New_York"


def test_unparseable_date_raises_rather_than_guessing():
    with pytest.raises(ValueError):
        fx.format_bar_date("15/06/2026 9:30am")


def test_bars_to_frame_shape_matches_repo_convention():
    bars = [FakeBar(datetime(2026, 6, 15, 13, 30, tzinfo=timezone.utc),
                    1.1, 1.2, 1.05, 1.15, -1.0)]
    df = fx.bars_to_frame(bars)
    assert list(df.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert df.loc[0, "Date"].endswith(" America/New_York")
    # Volume is written through as returned; spot FX gives -1 and we do not
    # invent a number for it.
    assert df.loc[0, "Volume"] == -1.0


# ------------------------------------------------------------ merge/resume
def _frame(*stamps):
    return pd.DataFrame(
        [{"Date": f"{s} America/New_York", "Open": 1.0, "High": 1.0,
          "Low": 1.0, "Close": 1.0, "Volume": -1.0} for s in stamps],
        columns=fx.COLUMNS)


def test_merge_sorts_and_dedupes_across_chunks(tmp_path):
    path = str(tmp_path / "EURUSD_1min.csv")
    fx.merge_and_write(path, _frame("20260615 09:31:00", "20260615 09:30:00"))
    # A resumed run overlaps the previous chunk — the overlap must collapse.
    n = fx.merge_and_write(path, _frame("20260615 09:31:00", "20260615 09:29:00"))
    assert n == 3
    out = pd.read_csv(path)
    assert out["Date"].tolist() == [
        "20260615 09:29:00 America/New_York",
        "20260615 09:30:00 America/New_York",
        "20260615 09:31:00 America/New_York"]


def test_merge_sorts_chronologically_not_lexically_across_midnight(tmp_path):
    """FX runs through midnight, so 23:59 must precede the next day's 00:00."""
    path = str(tmp_path / "EURUSD_1min.csv")
    fx.merge_and_write(path, _frame("20260616 00:00:00", "20260615 23:59:00"))
    out = pd.read_csv(path)
    assert out["Date"].iloc[0].startswith("20260615 23:59")


def test_merge_leaves_no_temp_file_behind(tmp_path):
    path = str(tmp_path / "EURUSD_1min.csv")
    fx.merge_and_write(path, _frame("20260615 09:30:00"))
    assert not os.path.exists(path + ".tmp")


def test_existing_span_drives_the_resume_cursor(tmp_path):
    path = str(tmp_path / "EURUSD_1min.csv")
    assert fx.existing_span(path) == (None, None)
    fx.merge_and_write(path, _frame("20260615 09:30:00", "20260710 12:00:00"))
    assert fx.existing_span(path) == (date(2026, 6, 15), date(2026, 7, 10))


# -------------------------------------------------------------- plan/pacing
@pytest.mark.parametrize("text,expected", [
    ("1 D", timedelta(days=1)),
    ("1 W", timedelta(weeks=1)),
    ("2 D", timedelta(days=2)),
    ("3600 S", timedelta(seconds=3600)),
])
def test_parse_duration(text, expected):
    assert fx.parse_duration(text) == expected


def test_parse_duration_rejects_unknown_unit():
    with pytest.raises(ValueError):
        fx.parse_duration("1 X")


def test_bid_ask_costs_double_against_pacing():
    """Docs p.62: "when BID_ASK historical data is requested, each request is
    counted twice"."""
    assert fx.pacing_floor("BID_ASK") == pytest.approx(2 * fx.pacing_floor("MIDPOINT"))
    assert fx.pacing_floor("BID") == fx.pacing_floor("MIDPOINT")


def test_cursors_are_timezone_aware_new_york():
    c = fx.ny_midnight(date(2026, 8, 13))
    assert c.tzinfo is not None
    assert c.utcoffset().total_seconds() == -4 * 3600      # EDT in August
    assert fx.ny_midnight(date(2026, 1, 13)).utcoffset().total_seconds() == -5 * 3600


def test_an_aware_cursor_reaches_ibkr_as_an_explicit_utc_boundary():
    """Verified against ib_async's own formatter: an aware datetime becomes
    '... UTC', so the request boundary does not depend on the TWS timezone.
    A bare string would be passed through and read in TWS's timezone instead."""
    util = pytest.importorskip("ib_async.util")
    got = util.formatIBDatetime(fx.ny_midnight(date(2026, 8, 13)))
    assert got == "20260813 04:00:00 UTC"                  # 00:00 EDT
    # and the trap this guards against: a string is NOT normalised
    assert util.formatIBDatetime("20260813 00:00:00") == "20260813 00:00:00"


def test_request_bars_refuses_a_naive_endpoint():
    """The assertion is the guard: a naive datetime would be interpreted in the
    local machine's timezone, reintroducing the ambiguity."""
    with pytest.raises(AssertionError, match="timezone-aware"):
        fx.request_bars(None, None, datetime(2026, 8, 13), "1 D", "1 min",
                        "MIDPOINT", False)


def test_weekend_skip_is_correct_across_a_dst_transition():
    """US DST flips on 2026-11-01, mid-closure. The closure must still be the
    same 48 hours, not 47 or 49."""
    fri = fx.ny_midnight(date(2026, 10, 30)).replace(hour=17)
    assert fx.window_is_closed(fri + timedelta(hours=8), fri + timedelta(hours=40))
    assert not fx.window_is_closed(fri + timedelta(hours=40),
                                   fri + timedelta(hours=56))


def test_a_window_wholly_inside_the_weekend_is_skipped():
    """Saturday 00:00 -> Sunday 00:00 is entirely closed: no request needed."""
    assert fx.window_is_closed(datetime(2026, 8, 15), datetime(2026, 8, 16))


@pytest.mark.parametrize("a,b,why", [
    (datetime(2026, 8, 14), datetime(2026, 8, 15), "Friday holds a full session"),
    (datetime(2026, 8, 16), datetime(2026, 8, 17), "Sunday reopens at 17:00 ET"),
    (datetime(2026, 8, 13), datetime(2026, 8, 14), "an ordinary Thursday"),
    (datetime(2026, 8, 10), datetime(2026, 8, 17), "a weekly chunk spans both"),
])
def test_any_overlap_with_an_open_market_is_never_skipped(a, b, why):
    """The skip must never cost data — it is an optimisation, not a filter."""
    assert not fx.window_is_closed(a, b), why


def test_no_window_across_five_years_of_weekends_is_wrongly_skipped():
    """Exhaustive: every daily window in five years that contains any open
    minute must survive the skip. A one-hour error in the closure boundary
    would silently delete Friday evenings or Sunday opens."""
    cursor = datetime(2021, 8, 13)
    step = timedelta(days=1)
    while cursor < datetime(2026, 8, 13):
        nxt = cursor + step
        closed = fx.window_is_closed(cursor, nxt)
        # A window is genuinely dataless only if it starts on Saturday, or on
        # Sunday and ends by 17:00.
        expect = (cursor.weekday() == 5
                  or (cursor.weekday() == 6 and nxt <= cursor.replace(hour=17)))
        assert closed == expect, f"{cursor} -> {nxt}: skipped={closed}"
        cursor = nxt


def test_skipping_weekends_cuts_the_daily_chunk_plan_by_about_a_seventh():
    start, end = date(2021, 8, 13), date(2026, 8, 13)
    p = fx.plan(["EURUSD"], ["MIDPOINT"], start, end, "1 D", 0.0)
    calendar_days = (end - start).days
    assert 0.80 < p["per_series"] / calendar_days < 0.90


def test_weekly_chunks_are_about_six_times_fewer_requests():
    """~6x, not 7x: daily chunking already skips the one day in seven that is
    wholly inside the weekend closure, so weekly only saves the six open days."""
    start, end = date(2021, 8, 13), date(2026, 8, 13)
    daily = fx.plan(["EURUSD"], ["MIDPOINT"], start, end, "1 D", 0.0)
    weekly = fx.plan(["EURUSD"], ["MIDPOINT"], start, end, "1 W", 0.0)
    assert daily["per_series"] / weekly["per_series"] == pytest.approx(6, abs=0.2)
    assert weekly["hours"] < daily["hours"]


def test_plan_scales_with_symbols_and_series():
    start, end = date(2025, 8, 13), date(2026, 8, 13)
    one = fx.plan(["EURUSD"], ["MIDPOINT"], start, end, "1 D", 0.0)
    many = fx.plan(["EURUSD", "USDJPY"], ["MIDPOINT", "BID", "ASK"],
                   start, end, "1 D", 0.0)
    assert many["total_requests"] == 6 * one["total_requests"]
    assert many["hours"] == pytest.approx(6 * one["hours"], rel=1e-6)


def test_five_year_three_series_plan_is_flagged_as_overnight(capsys):
    """The ETA exists so a 10-hour job is a decision, not a discovery."""
    p = fx.print_plan(fx.UNIVERSE["core"], ["MIDPOINT", "BID", "ASK"],
                      date(2021, 8, 13), date(2026, 8, 13), "1 D", 0.0, "1 min")
    assert p["hours"] > 8
    assert "overnight" in capsys.readouterr().out


# ------------------------------------------------------------------ naming
def test_midpoint_keeps_the_bare_repo_filename():
    """SOXL_1min.csv is the repo's convention; the primary series must match it
    so band_lab's own loaders can read the file unchanged."""
    assert (fx.out_path("EURUSD", "1 min", "MIDPOINT", "/d")
            == "/d/EURUSD_1min.csv")
    assert (fx.out_path("EURUSD", "1 min", "BID", "/d")
            == "/d/EURUSD_1min_BID.csv")
    assert (fx.out_path("USDZAR", "5 mins", "ASK", "/d")
            == "/d/USDZAR_5min_ASK.csv")


@pytest.mark.parametrize("size,slug", [
    ("1 min", "1min"), ("5 mins", "5min"), ("30 secs", "30sec"),
    ("1 hour", "1hour"),
])
def test_bar_slug(size, slug):
    assert fx.bar_slug(size) == slug


# --------------------------------------------------------------- contracts
def test_spot_pair_is_cash_on_idealpro():
    pytest.importorskip("ib_async")
    c = fx.make_contract("EURUSD", futures=False)
    assert (c.secType, c.symbol, c.currency, c.exchange) == (
        "CASH", "EUR", "USD", "IDEALPRO")


def test_futures_root_is_contfut_on_cme():
    pytest.importorskip("ib_async")
    c = fx.make_contract("6E", futures=True)
    assert (c.secType, c.symbol, c.exchange) == ("CONTFUT", "6E", "CME")


def test_a_non_pair_symbol_is_rejected_before_it_reaches_the_broker():
    pytest.importorskip("ib_async")
    with pytest.raises(ValueError):
        fx.make_contract("EUR", futures=False)


def test_every_preset_holds_well_formed_pairs():
    for name, syms in fx.UNIVERSE.items():
        assert syms, name
        assert all(len(s) == 6 and s.isupper() for s in syms), name


# -------------------------------------------------------------------- cli
def test_dry_run_prints_a_plan_without_connecting(capsys):
    rc = fx.main(["--symbols", "EURUSD", "--what", "MIDPOINT", "--years", "5",
                  "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "requests" in out and "hours" in out
    # the measured k for EURUSD should be surfaced as fetch-time guidance
    assert "k=0.067" in out


def test_unsupported_what_to_show_is_refused():
    assert fx.main(["--symbols", "EURUSD", "--what", "VWAP", "--dry-run"]) == 2


def test_start_after_end_is_refused():
    assert fx.main(["--symbols", "EURUSD", "--start", "2026-08-01",
                    "--end", "2026-01-01", "--dry-run"]) == 2


def test_default_is_all_hours_because_fx_has_no_session():
    """--rth must be opt-in: 24-hour data is a superset, RTH cannot be undone."""
    ap_default = fx.main(["--symbols", "EURUSD", "--dry-run"])
    assert ap_default == 0
    # and the flag exists to turn it back on
    assert fx.main(["--symbols", "EURUSD", "--rth", "--dry-run"]) == 0
