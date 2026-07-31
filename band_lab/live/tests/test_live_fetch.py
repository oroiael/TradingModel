"""
Tests for the fetcher's pure parts.

The IBKR request loop cannot be tested without a broker; what *can* be tested
is the part that decides what lands on disk — timestamp formatting, merge and
de-duplication, and resumption — because a malformed CSV would silently
corrupt the fill-resolution study rather than fail loudly.
"""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from fetch_1min import (
    bars_to_frame,
    earliest_session,
    format_bar_date,
    merge_and_write,
)

NY = ZoneInfo("America/New_York")


def bar(date, o=1.0, h=2.0, l=0.5, c=1.5, v=10):
    return SimpleNamespace(date=date, open=o, high=h, low=l, close=c, volume=v)


# ------------------------------------------------------------- date formats
def test_naive_datetime_is_rendered_in_the_repo_convention():
    assert format_bar_date(datetime(2026, 6, 2, 9, 30)) == \
        "20260602 09:30:00 America/New_York"


def test_aware_datetime_is_converted_to_new_york():
    utc = datetime(2026, 6, 2, 13, 30, tzinfo=ZoneInfo("UTC"))
    assert format_bar_date(utc) == "20260602 09:30:00 America/New_York"


@pytest.mark.parametrize("raw", [
    "20260602 09:30:00",
    "20260602 09:30:00 America/New_York",
    "20260602-09:30:00",
])
def test_string_forms_are_accepted(raw):
    assert format_bar_date(raw) == "20260602 09:30:00 America/New_York"


def test_unparseable_dates_raise():
    with pytest.raises(ValueError):
        format_bar_date("2 June 2026")


def test_frame_matches_the_five_minute_csv_schema():
    df = bars_to_frame([bar(datetime(2026, 6, 2, 9, 30))])
    assert list(df.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert df.loc[0, "Date"].endswith(" America/New_York")


# ------------------------------------------------------------ merge / resume
def test_merge_deduplicates_and_sorts(tmp_path):
    path = str(tmp_path / "X_1min.csv")
    merge_and_write(path, bars_to_frame([
        bar(datetime(2026, 6, 2, 9, 31)), bar(datetime(2026, 6, 2, 9, 30))]))
    out = merge_and_write(path, bars_to_frame([
        bar(datetime(2026, 6, 1, 9, 30)), bar(datetime(2026, 6, 2, 9, 31), o=9.0)]))

    assert len(out) == 3                              # one duplicate collapsed
    assert out["Date"].tolist() == sorted(out["Date"].tolist())
    dup = out[out["Date"].str.startswith("20260602 09:31")]
    assert float(dup["Open"].iloc[0]) == 9.0          # the newer row wins


def test_merge_is_idempotent(tmp_path):
    path = str(tmp_path / "X_1min.csv")
    frame = bars_to_frame([bar(datetime(2026, 6, 2, 9, 30))])
    merge_and_write(path, frame)
    assert len(merge_and_write(path, frame)) == 1


def test_earliest_session_drives_resumption(tmp_path):
    path = str(tmp_path / "X_1min.csv")
    assert earliest_session(path) is None
    merge_and_write(path, bars_to_frame([
        bar(datetime(2026, 6, 2, 9, 30)), bar(datetime(2026, 5, 29, 15, 59))]))
    assert earliest_session(path) == datetime(2026, 5, 29)


def test_written_file_is_readable_by_the_study_harness(tmp_path):
    """The output must round-trip through intrabar.load_1min_sessions."""
    from intrabar import load_1min_sessions

    path = str(tmp_path / "ZZZ_1min.csv")
    bars = [bar(datetime(2026, 6, 2, 9, 30 + m), o=10.0 + m, h=11.0 + m,
                l=9.0 + m, c=10.5 + m) for m in range(10)]
    merge_and_write(path, bars_to_frame(bars))

    sessions = load_1min_sessions("ZZZ", root=str(tmp_path), path=path)
    assert len(sessions) == 1
    date, loaded = sessions[0]
    assert date == pd.Timestamp("2026-06-02")
    assert [b.idx for b in loaded] == list(range(10))   # minutes since 09:30
    assert loaded[0].open == 10.0
