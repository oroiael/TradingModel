"""Offline tests for fx_profile.py — session slicing, churn, integrity, cost."""

from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd
import pytest

import fetch_fx_intraday as fx
import fx_profile as prof

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)


# ----------------------------------------------------------------- fixtures
def synth(days=40, bars_per_day=1440, amp=0.0025, seed=0, start="2026-06-01"):
    """A synthetic 24-hour FX series that oscillates by a known amount.

    A clean sine plus noise: the daily range is close to 2*amp, so a test can
    assert the profiler recovers a range it was told to produce.
    """
    rng = np.random.default_rng(seed)
    stamps, o, h, l, c = [], [], [], [], []
    day = pd.Timestamp(start)
    made = 0
    while made < days:
        if day.dayofweek >= 5:                 # FX does not trade weekends
            day += pd.Timedelta(days=1)
            continue
        base = 1.10
        for i in range(bars_per_day):
            t = day + pd.Timedelta(minutes=i)
            mid = base * (1 + amp * np.sin(2 * np.pi * i / 120))
            jitter = rng.normal(0, base * 2e-5)
            op = mid + jitter
            hi = op + abs(rng.normal(0, base * 2e-5))
            lo = op - abs(rng.normal(0, base * 2e-5))
            stamps.append(t.strftime("%Y%m%d %H:%M:%S") + " America/New_York")
            o.append(op); h.append(hi); l.append(lo); c.append(op)
        made += 1
        day += pd.Timedelta(days=1)
    return pd.DataFrame({"Date": stamps, "Open": o, "High": h, "Low": l,
                         "Close": c, "Volume": -1.0})


@pytest.fixture
def synth_file(tmp_path):
    path = tmp_path / "EURUSD_1min.csv"
    synth().to_csv(path, index=False)
    return str(path)


# ------------------------------------------------------------------ loading
def test_load_rejects_a_file_missing_price_columns(tmp_path):
    p = tmp_path / "BAD_1min.csv"
    pd.DataFrame({"Date": ["20260615 09:30:00 America/New_York"],
                  "Open": [1.0]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="missing columns"):
        prof.load(str(p))


# ------------------------------------------------------------------ session
def test_fx_day_rolls_at_1700_new_york():
    """IBKR's FX day ends ~17:00 ET — its daily bars are stamped 21:15 UTC.

    So a bar at 17:30 on the 15th belongs to the 16th's session, and one at
    16:30 belongs to the 15th's.
    """
    df = prof.load_frame_for_test([
        "20260615 16:30:00", "20260615 17:00:00", "20260615 23:59:00",
        "20260616 02:00:00", "20260616 16:59:00"])
    sd = prof.sessionize(df, "fx")
    days = [str(d.date()) for d in sd["sday"]]
    assert days == ["2026-06-15", "2026-06-16", "2026-06-16",
                    "2026-06-16", "2026-06-16"]


def test_ny_session_keeps_only_the_equity_hours():
    df = prof.load_frame_for_test([
        "20260615 03:00:00", "20260615 09:29:00", "20260615 09:30:00",
        "20260615 15:59:00", "20260615 16:00:00", "20260615 20:00:00"])
    sd = prof.sessionize(df, "ny")
    assert len(sd) == 2
    assert sd["dt"].dt.strftime("%H:%M").tolist() == ["09:30", "15:59"]


def test_london_and_overlap_windows_differ():
    df = prof.load_frame_for_test([
        "20260615 03:30:00", "20260615 09:00:00", "20260615 13:00:00"])
    assert len(prof.sessionize(df, "london")) == 2      # 03:30, 09:00
    assert len(prof.sessionize(df, "overlap")) == 1     # 09:00 only


def test_every_session_is_a_real_window():
    for name, (lo, hi) in prof.SESSIONS.items():
        assert 0 <= lo < hi <= 24 * 60, name


# ------------------------------------------------------------------ zigzag
def test_zigzag_matches_band_labs_implementation_character_for_character():
    """Churn counts are compared to band_lab's published SOXL figures, so this
    copy must not drift from the original. Compare the source text itself —
    band_analysis.py cannot be imported here because it loads SOXL data at
    import time."""
    src = open(os.path.join(ROOT, "band_lab", "band_analysis.py")).read()
    theirs = re.search(r"def zigzag_legs\(h, l, thresh\):\n(.*?)\n(?=\S)",
                       src, re.S).group(1)
    ours = re.search(r"def zigzag_legs\(h, l, thresh\).*?\n(    legs = 0.*?)\n(?=\S)",
                     open(os.path.join(HERE, "fx_profile.py")).read(), re.S).group(1)

    def body(text):
        """Executable lines only — comments and docstrings may legitimately
        differ, the arithmetic may not."""
        out = []
        for ln in text.splitlines():
            code = ln.split("#")[0].strip()
            if code and not code.startswith('"""'):
                out.append(code)
        return out

    assert body(ours) == body(theirs)


def test_zigzag_counts_a_known_oscillation():
    """Four completed 1% legs: up, down, up, down.

    The algorithm needs a LOWER high to close a down-leg (h[i] < running high),
    so a genuine zigzag is required — a monotone ramp counts zero, however far
    it travels.
    """
    h = np.array([100.0, 102.0, 101.0, 103.0, 102.0])
    l = np.array([100.0, 101.0, 99.0, 102.0, 100.0])
    assert prof.zigzag_legs(h, l, 0.01) == 4


def test_a_monotone_ramp_completes_one_leg_however_far_it_travels():
    """This is what makes the metric a churn measure rather than a range one.

    A one-way trend books the single leg off its starting low and then nothing:
    closing a down-leg requires a LOWER high, which never comes. So a 9% ramp
    and a 90% ramp both score 1, while an oscillation of the same total travel
    scores many. Verified against band_lab's implementation, not assumed.
    """
    short = np.arange(100.0, 110.0)
    long = np.arange(100.0, 190.0)
    assert prof.zigzag_legs(short, short - 0.5, 0.01) == 1
    assert prof.zigzag_legs(long, long - 0.5, 0.01) == 1


def test_zigzag_finds_nothing_below_the_threshold():
    h = np.array([100.0, 100.1, 100.0, 100.1, 100.0])
    l = np.array([99.9, 100.0, 99.9, 100.0, 99.9])
    assert prof.zigzag_legs(h, l, 0.01) == 0


# ----------------------------------------------------------------- profile
def test_profile_recovers_the_range_it_was_given(synth_file):
    """The synthetic series swings +/-0.25% around its base, so the daily range
    is ~0.5% and k should land near 0.5/6.67 = 0.075."""
    df = prof.load(synth_file)
    r = prof.profile_session(df, "fx", "EURUSD")
    assert r["days"] > 20
    assert 0.4 < r["median_range_%"] < 0.6
    assert r["scale_k"] == round(r["median_range_%"] / prof.SOXL_MEDIAN_RANGE, 4)


def test_scaled_parameters_keep_band_labs_four_to_one_ratio(synth_file):
    """dip/target = k*1%, stop = k*4% — the 4:1 asymmetry is deliberate (V4)."""
    r = prof.profile_session(prof.load(synth_file), "fx", "EURUSD")
    assert r["scaled_stop_%"] == pytest.approx(4 * r["scaled_dip_tgt_%"], rel=1e-6)


def test_fill_resolution_ratio_is_reported(synth_file):
    """bar_range_vs_target_% is the warning that a single bar can straddle
    entry and target — the defect that halved band_lab's estimate."""
    r = prof.profile_session(prof.load(synth_file), "fx", "EURUSD")
    assert r["median_bar_range_%"] > 0
    assert r["bar_range_vs_target_%"] == pytest.approx(
        r["median_bar_range_%"] / r["scaled_dip_tgt_%"] * 100, abs=0.05)


def test_a_too_short_file_profiles_to_nothing_rather_than_noise(tmp_path):
    p = tmp_path / "EURUSD_1min.csv"
    synth(days=2).to_csv(p, index=False)
    assert prof.profile_session(prof.load(str(p)), "fx", "EURUSD") == {}


# ------------------------------------------------------------------- check
def test_check_passes_a_clean_file(synth_file, capsys):
    r = prof.check_file(synth_file, "fx")
    assert (r["dup"], r["nan"], r["bad_ohlc"], r["weekend"]) == (0, 0, 0, 0)
    assert r["monotonic"]
    assert r["volume_present"] is False     # spot FX carries no volume


def test_check_catches_duplicate_timestamps(tmp_path):
    df = synth(days=5)
    df = pd.concat([df, df.iloc[[10]]], ignore_index=True)
    p = tmp_path / "EURUSD_1min.csv"
    df.to_csv(p, index=False)
    assert prof.check_file(str(p), "fx")["dup"] == 1


def test_check_catches_a_saturday_bar(tmp_path):
    """A weekend bar means the timezone handling is wrong — FX is shut."""
    df = synth(days=5)
    df.loc[0, "Date"] = "20260613 12:00:00 America/New_York"   # a Saturday
    p = tmp_path / "EURUSD_1min.csv"
    df.to_csv(p, index=False)
    assert prof.check_file(str(p), "fx")["weekend"] == 1


def test_check_catches_impossible_ohlc(tmp_path):
    df = synth(days=5)
    df.loc[5, "High"] = df.loc[5, "Low"] - 0.01
    p = tmp_path / "EURUSD_1min.csv"
    df.to_csv(p, index=False)
    assert prof.check_file(str(p), "fx")["bad_ohlc"] >= 1


# -------------------------------------------------------------------- cost
def test_spread_cost_is_measured_against_the_scaled_target(tmp_path):
    """A 0.2 bp spread against a 6.7 bp target is ~3% of gross edge; the point
    of capturing BID/ASK is that this number stops being a guess."""
    mid = synth(days=5)
    half = 1.10 * 0.00001                       # 0.2 bp total spread
    bid = mid.assign(Close=mid["Close"] - half)
    ask = mid.assign(Close=mid["Close"] + half)
    bid.to_csv(tmp_path / "EURUSD_1min_BID.csv", index=False)
    ask.to_csv(tmp_path / "EURUSD_1min_ASK.csv", index=False)
    s = prof.spread_cost("EURUSD", "1min", str(tmp_path), k=0.067)
    assert s["median_spread_bp"] == pytest.approx(0.2, abs=0.02)
    assert s["target_bp"] == pytest.approx(6.7, abs=0.01)
    assert s["round_trip_spread_%_of_target"] == pytest.approx(3.0, abs=0.5)
    # commission must be included in the headline, not left implicit
    assert s["total_cost_%_of_target"] > s["round_trip_spread_%_of_target"]


def test_spread_cost_is_absent_when_bid_ask_were_not_captured(tmp_path):
    assert prof.spread_cost("EURUSD", "1min", str(tmp_path), k=0.067) == {}


# --------------------------------------------------------------------- cli
def test_profile_cli_reports_missing_data_instead_of_crashing(tmp_path, capsys):
    rc = prof.main(["--data-dir", str(tmp_path)])
    assert rc == 1
    assert "fetch_fx_intraday" in capsys.readouterr().out


def test_profile_cli_runs_end_to_end(tmp_path, capsys, monkeypatch):
    synth(days=40).to_csv(tmp_path / "EURUSD_1min.csv", index=False)
    monkeypatch.setattr(prof, "OUT", str(tmp_path / "out"))
    assert prof.main(["--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "scale_k" in out and "EURUSD" in out
    assert os.path.exists(os.path.join(str(tmp_path / "out"),
                                       "fx_churn_density.csv"))


def test_check_cli_runs_end_to_end(tmp_path, monkeypatch):
    synth(days=10).to_csv(tmp_path / "EURUSD_1min.csv", index=False)
    monkeypatch.setattr(prof, "OUT", str(tmp_path / "out"))
    assert prof.main(["--data-dir", str(tmp_path), "--check"]) == 0
