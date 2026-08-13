"""Verify a captured FX file and profile it against band_lab's SOXL reference.

Two jobs, deliberately separate from the fetcher (same split as
`fas_1min_fetch.py` / `fas_1min_verify.py`):

    python3 fx_lab/fx_profile.py --check     # is the capture sound?
    python3 fx_lab/fx_profile.py             # is the strategy transferable?

--check answers "did the fetch produce a usable file": duplicate timestamps,
NaN, non-monotonic rows, bars per session against what a 24-hour or RTH session
should hold, weekend rows, price discontinuities, and whether Volume carries
anything at all (for spot FX it will not).

The default profile answers the question this lab was opened for.  It computes,
per candidate session definition, the same three numbers `etf_scaling_test.py`
used to decide SOXL -> FAS/SPXL transfer:

    median daily range %        -> k = range / 6.67%, which scales dip/target/stop
    completed >=k% swings/day   -> is there churn to harvest at the scaled depth?
    ATR5 percentile at gate     -> where the V10 vol gate would have to sit

...plus the two things FX adds that a 3x ETF did not:

    spread cost as % of target  -> from the BID/ASK files, if captured
    intrabar range as % target  -> the fill-resolution problem, quantified

WHY SESSION DEFINITION IS A VARIABLE
------------------------------------
band_lab's V2 (rolling *session* high), V5 (start at 11:00) and V9 (opening
30-minute range filter) all reference a session open.  Spot FX has none: it
trades continuously from Sunday 17:00 ET to Friday 17:00 ET.  So this script
scores four candidate anchors rather than assuming one:

    ny       09:30-16:00 ET   identical to band_lab; lets the SOXL numbers be
                              compared like-for-like
    fx       17:00-17:00 ET   IBKR's own FX day. Confirmed from the daily bars
                              the broker serves: they are stamped 21:15 UTC,
                              i.e. 17:15 ET, so the boundary sits at ~17:00 ET
    london   03:00-11:30 ET   the London session
    overlap  08:00-12:00 ET   the London/New York overlap, the deepest liquidity

A session with more churn per unit of spread is the one to build on.  Nothing
here adopts anything -- it is the input to a V-numbered program, not a result.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "out")

SOXL_MEDIAN_RANGE = 6.67      # band_lab/out/etf_churn_density.csv
SOXL_SWINGS_1PCT = 15.0       # mean completed >=1% swings/day
SOXL_ON_RATE = 0.521          # band_lab's ATR5>=6% ON-rate, for gate matching

# (start, end) in ET minutes-from-midnight; end exclusive. `fx` wraps midnight
# and is handled by shifting the calendar day, not by these bounds.
SESSIONS = {
    "ny":      (9 * 60 + 30, 16 * 60),
    "fx":      (0, 24 * 60),
    "london":  (3 * 60, 11 * 60 + 30),
    "overlap": (8 * 60, 12 * 60),
}


# --------------------------------------------------------------------- load
def load(path: str) -> pd.DataFrame:
    """Read a repo-convention CSV into a frame with a parsed NY timestamp."""
    df = pd.read_csv(path)
    missing = {"Date", "Open", "High", "Low", "Close"} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    dt = pd.to_datetime(df["Date"].str.slice(0, 17), format="%Y%m%d %H:%M:%S")
    return (df.assign(dt=dt, minute=dt.dt.hour * 60 + dt.dt.minute)
              .sort_values("dt").reset_index(drop=True))


def load_frame_for_test(stamps) -> pd.DataFrame:
    """Build a minimal frame from bare 'YYYYMMDD HH:MM:SS' strings.

    Exists so the session-slicing rules can be tested against hand-written
    timestamps without a CSV on disk.
    """
    df = pd.DataFrame({"Date": [f"{s} America/New_York" for s in stamps],
                       "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
                       "Volume": -1.0})
    dt = pd.to_datetime(df["Date"].str.slice(0, 17), format="%Y%m%d %H:%M:%S")
    return df.assign(dt=dt, minute=dt.dt.hour * 60 + dt.dt.minute)


def sessionize(df: pd.DataFrame, session: str) -> pd.DataFrame:
    """Attach a `sday` column: which trading day each bar belongs to."""
    lo, hi = SESSIONS[session]
    if session == "fx":
        # IBKR's FX day rolls at 17:00 ET, so 17:00-23:59 belongs to the NEXT
        # calendar day's session -- the same convention CME uses for Globex.
        roll = 17 * 60
        sday = df["dt"].dt.normalize() + pd.to_timedelta(
            (df["minute"] >= roll).astype(int), unit="D")
        return df.assign(sday=sday)
    keep = (df["minute"] >= lo) & (df["minute"] < hi)
    return df[keep].assign(sday=df.loc[keep, "dt"].dt.normalize())


def zigzag_legs(h, l, thresh) -> int:
    """Completed swings >= thresh (fraction). Verbatim from band_lab/band_analysis.py
    so churn counts are directly comparable to the published SOXL numbers."""
    legs = 0
    hi, lo = h[0], l[0]
    direction = 0
    for i in range(1, len(h)):
        hi = max(hi, h[i]); lo = min(lo, l[i])
        if direction >= 0 and h[i] < hi and (hi - l[i]) / hi >= thresh:
            legs += 1; direction = -1; lo = l[i]; hi = h[i]
        elif direction <= 0 and l[i] > lo and (h[i] - lo) / lo >= thresh:
            legs += 1; direction = 1; hi = h[i]; lo = l[i]
    return legs


# -------------------------------------------------------------------- check
def check_file(path: str, session: str) -> dict:
    df = load(path)
    n = len(df)
    dup = int(df["Date"].duplicated().sum())
    nan = int(df[["Open", "High", "Low", "Close"]].isna().sum().sum())
    monotonic = bool(df["dt"].is_monotonic_increasing)
    bad_ohlc = int(((df["High"] < df["Low"]) |
                    (df["High"] < df[["Open", "Close"]].max(axis=1) - 1e-12) |
                    (df["Low"] > df[["Open", "Close"]].min(axis=1) + 1e-12)).sum())
    # Saturday is never a trading day anywhere; Sunday before 17:00 ET is not
    # either. Either one appearing means the timezone handling is wrong.
    dow = df["dt"].dt.dayofweek
    weekend = int(((dow == 5) | ((dow == 6) & (df["minute"] < 17 * 60))).sum())
    vol = df["Volume"] if "Volume" in df else pd.Series(dtype=float)
    vol_live = bool(len(vol) and (vol > 0).any())

    sd = sessionize(df, session)
    per_day = sd.groupby("sday").size()
    span = f"{df['dt'].min():%Y-%m-%d} -> {df['dt'].max():%Y-%m-%d}"
    years = (df["dt"].max() - df["dt"].min()).days / 365.25

    # A price gap between consecutive bars larger than this is either a real
    # event (an intervention, a Sunday reopen) or a stitched-source error.
    step = df["Close"].pct_change().abs()
    jumps = int((step > 0.01).sum())

    print(f"\n{os.path.basename(path)}")
    print(f"  rows {n:,}   span {span}   ({years:.2f} years)")
    print(f"  sessions ({session}) {per_day.size:,}   bars/session "
          f"median {int(per_day.median()) if per_day.size else 0}, "
          f"min {int(per_day.min()) if per_day.size else 0}, "
          f"max {int(per_day.max()) if per_day.size else 0}")
    for label, value, want_zero in (("duplicate timestamps", dup, True),
                                    ("NaN prices", nan, True),
                                    ("OHLC inconsistencies", bad_ohlc, True),
                                    ("weekend bars", weekend, True),
                                    (">1% bar-to-bar jumps", jumps, False)):
        flag = "ok  " if (value == 0 or not want_zero) else "FAIL"
        print(f"  [{flag}] {label}: {value:,}")
    print(f"  [{'ok  ' if monotonic else 'FAIL'}] chronological order")
    print(f"  [{'ok  ' if vol_live else 'note'}] volume: "
          + ("present" if vol_live else "absent/-1 — expected for spot FX, "
             "IBKR has no consolidated trade tape for CASH"))
    if years < 4.9:
        print(f"  [note] {years:.2f} years captured; --probe reports the head "
              f"timestamp IBKR will actually serve")
    return {"file": os.path.basename(path), "rows": n, "years": round(years, 2),
            "sessions": int(per_day.size), "dup": dup, "nan": nan,
            "bad_ohlc": bad_ohlc, "weekend": weekend, "jumps_gt_1pct": jumps,
            "monotonic": monotonic, "volume_present": vol_live}


# ------------------------------------------------------------------ profile
def profile_session(df: pd.DataFrame, session: str, symbol: str) -> dict:
    sd = sessionize(df, session)
    if sd.empty:
        return {}
    g = sd.groupby("sday")
    d = g.agg(o=("Open", "first"), h=("High", "max"), l=("Low", "min"),
              c=("Close", "last"), bars=("Open", "size"))
    d = d[d["bars"] >= 10]
    if len(d) < 20:
        return {}
    d["range_pct"] = (d["h"] - d["l"]) / d["o"] * 100
    med = float(d["range_pct"].median())
    k = med / SOXL_MEDIAN_RANGE
    d["atr5"] = d["range_pct"].rolling(5).mean().shift()

    # Churn at the k-scaled depth: the swing size band_lab's 1% dip becomes.
    thresh = k * 0.01
    legs = []
    for _, gb in g:
        if len(gb) < 10:
            continue
        legs.append(zigzag_legs(gb["High"].to_numpy(), gb["Low"].to_numpy(),
                                thresh))
    legs = np.array(legs, float)

    # The gate: where ATR5 would sit to keep band_lab's 52% ON-rate.
    atr5 = d["atr5"].dropna()
    gate = float(np.nanquantile(atr5, 1 - SOXL_ON_RATE)) if len(atr5) else np.nan

    # Fill resolution: a single bar's own range, against the scaled target.
    # If a bar's range rivals the target, the sim cannot tell a real fill from
    # a same-bar artifact -- the exact defect that halved band_lab's estimate.
    bar_rng = ((sd["High"] - sd["Low"]) / sd["Open"] * 100).replace(0, np.nan)
    bar_med = float(bar_rng.median())

    # Round the stop off the ROUNDED dip, so a reader multiplying the printed
    # dip by 4 gets the printed stop. Rounding each off k independently makes
    # the table disagree with itself in the last digit.
    dip = round(k * 1, 4)
    return {"symbol": symbol, "session": session, "days": int(len(d)),
            "median_range_%": round(med, 3), "scale_k": round(k, 4),
            "scaled_dip_tgt_%": dip,
            "scaled_stop_%": round(dip * 4, 4),
            "swings_mean": round(float(np.nanmean(legs)), 1) if len(legs) else np.nan,
            "swings_median": int(np.nanmedian(legs)) if len(legs) else 0,
            "zero_swing_days_%": round(float((legs == 0).mean() * 100), 1) if len(legs) else np.nan,
            "gate_matched_%": round(gate, 3) if gate == gate else np.nan,
            "median_bar_range_%": round(bar_med, 4),
            "bar_range_vs_target_%": round(bar_med / (k * 1) * 100, 1) if k else np.nan}


def spread_cost(symbol: str, bar_slug: str, data_dir: str, k: float) -> dict:
    """Measured IDEALPRO spread from the BID/ASK captures, vs the scaled target.

    Without this the strategy cannot be costed: at a 5-14 bp target, a spread
    that looks trivial in pips can be a double-digit percentage of gross edge.
    """
    bid_p = os.path.join(data_dir, f"{symbol}_{bar_slug}_BID.csv")
    ask_p = os.path.join(data_dir, f"{symbol}_{bar_slug}_ASK.csv")
    if not (os.path.exists(bid_p) and os.path.exists(ask_p)):
        return {}
    bid, ask = load(bid_p), load(ask_p)
    m = bid[["Date", "Close"]].merge(ask[["Date", "Close"]], on="Date",
                                     suffixes=("_bid", "_ask"))
    if m.empty:
        return {}
    mid = (m["Close_bid"] + m["Close_ask"]) / 2
    spread_bp = (m["Close_ask"] - m["Close_bid"]) / mid * 1e4
    spread_bp = spread_bp[spread_bp >= 0]
    target_bp = k * 1 * 100          # k-scaled 1% target, in basis points
    med = float(spread_bp.median())
    return {"symbol": symbol, "bars": int(len(spread_bp)),
            "median_spread_bp": round(med, 3),
            "p90_spread_bp": round(float(spread_bp.quantile(0.9)), 3),
            "target_bp": round(target_bp, 2),
            "round_trip_spread_%_of_target": round(med / target_bp * 100, 1),
            # IBKR spot FX commission: 0.20 bp of trade value per side, $2 min.
            # ASSUMPTION (tiering and minimums are account-specific) — quoted
            # here only so the total is not silently understated.
            "plus_commission_%_of_target": round(0.40 / target_bp * 100, 1),
            "total_cost_%_of_target": round((med + 0.40) / target_bp * 100, 1)}


# --------------------------------------------------------------------- main
def discover(data_dir: str, bar_slug: str) -> list[str]:
    if not os.path.isdir(data_dir):
        return []
    return sorted(
        os.path.join(data_dir, f) for f in os.listdir(data_dir)
        if f.endswith(f"_{bar_slug}.csv"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Verify and profile captured FX intraday files")
    ap.add_argument("--data-dir", default=DATA)
    ap.add_argument("--bar-slug", default="1min",
                    help="filename bar tag to profile (default 1min)")
    ap.add_argument("--files", nargs="*", default=None,
                    help="explicit CSVs; default every <SYM>_<slug>.csv found")
    ap.add_argument("--session", default=None, choices=sorted(SESSIONS),
                    help="profile one session only (default: all four)")
    ap.add_argument("--check", action="store_true",
                    help="integrity check only")
    args = ap.parse_args(argv)

    files = args.files or discover(args.data_dir, args.bar_slug)
    if not files:
        print(f"no {args.bar_slug} files in {args.data_dir}.\n"
              f"Fetch some first:\n"
              f"  python3 fx_lab/fetch_fx_intraday.py --probe\n"
              f"  python3 fx_lab/fetch_fx_intraday.py --symbols EURUSD "
              f"--what MIDPOINT")
        return 1
    os.makedirs(OUT, exist_ok=True)
    sessions = [args.session] if args.session else list(SESSIONS)

    if args.check:
        print("=" * 78)
        print("INTEGRITY CHECK")
        print("=" * 78)
        # Default to the FX-native day: for a 24-hour capture, "did I get 1440
        # bars?" is the integrity question. Pass --session ny to see the
        # 390-bar equity window instead, which is what band_lab compares to.
        rows = [check_file(f, args.session or "fx") for f in files]
        df = pd.DataFrame(rows)
        dest = os.path.join(OUT, "fx_integrity.csv")
        df.to_csv(dest, index=False)
        print(f"\n-> {dest}")
        failed = df[(df["dup"] > 0) | (df["nan"] > 0) | (df["bad_ohlc"] > 0)
                    | (df["weekend"] > 0) | (~df["monotonic"])]
        if len(failed):
            print(f"\n[!] {len(failed)} file(s) failed a hard check")
            return 1
        return 0

    rows, spreads = [], []
    for path in files:
        symbol = os.path.basename(path).split("_")[0]
        df = load(path)
        for session in sessions:
            r = profile_session(df, session, symbol)
            if r:
                rows.append(r)
        base = [r for r in rows if r["symbol"] == symbol and r["session"] == "fx"]
        k = base[0]["scale_k"] if base else (rows[-1]["scale_k"] if rows else 0)
        s = spread_cost(symbol, args.bar_slug, args.data_dir, k)
        if s:
            spreads.append(s)

    if not rows:
        print("[!] nothing profitable to profile — files too short?")
        return 1

    prof = pd.DataFrame(rows)
    print("=" * 110)
    print("FX PROFILE vs band_lab's SOXL reference — EXPLORATORY, nothing adopted")
    print("=" * 110)
    print(prof.to_string(index=False))
    print(f"\nSOXL reference: median_range 6.67%, k 1.000, dip/target 1.00%, "
          f"stop 4.00%, swings/day mean {SOXL_SWINGS_1PCT}, gate 6.71%")
    prof.to_csv(os.path.join(OUT, "fx_churn_density.csv"), index=False)

    if spreads:
        sp = pd.DataFrame(spreads)
        print("\n" + "=" * 110)
        print("COST — measured spread against the k-scaled target")
        print("=" * 110)
        print(sp.to_string(index=False))
        sp.to_csv(os.path.join(OUT, "fx_spread_cost.csv"), index=False)
    else:
        print("\n[note] no BID/ASK files found, so cost is unmeasured. At a "
              "5-14 bp target that is the difference between an edge and a "
              "rounding error — capture them:\n"
              "  python3 fx_lab/fetch_fx_intraday.py --what BID,ASK")

    print("\nHow to read this:")
    print("  scale_k               parameters etf_scaling_test.py would use: "
          "dip/target k%, stop 4k%")
    print("  swings_mean           churn available at the scaled depth. SOXL's "
          f"is {SOXL_SWINGS_1PCT}; well below that means")
    print("                        there is less to harvest per day no matter "
          "how the entry is tuned")
    print("  bar_range_vs_target_% the fill-resolution warning. Above ~30% and "
          "a bar can straddle entry and")
    print("                        target, which is exactly what inflated "
          "band_lab's 5-minute numbers 2x")
    print("                        (STRATEGY_SPEC §0.2) — go to 30-second bars "
          "or tick data before believing a backtest")
    print(f"\n-> {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
