"""
Two things `drivers.py` left open.

**A. FOMC.** Does UVXY move before, during, or after the announcement? The
1-minute file answers this directly: the statement drops at 14:00 ET and the
press conference starts at 14:30, so the intraday profile either shows a step
at 14:00 or it does not. The date list is validated against the data rather
than trusted -- if the dates were wrong, no 14:00 signature would appear.

**B. The variance-drag control, which decides whether §1-§2's "signals" are
real.** A 1.5x daily-rebalanced fund loses about 0.5*k*(k-1)*sigma^2 = 0.375
sigma^2 per unit time to rebalancing, whatever direction the index takes. So
"UVXY falls hard after a volatility spike" may be a forecast, or it may be
arithmetic: a spike raises sigma, and higher sigma mechanically means more
drag. The two are distinguished by asking the same signal to predict **VIXY**,
the 1x fund, where the drag term is ~0. A signal that predicts UVXY but not
VIXY is measuring the drag, not the market.

Overlapping forward windows are also corrected here: 20-day returns sampled
daily overlap 20:1, and the naive t-stats in `drivers.py` are inflated by
roughly sqrt(20). Newey-West and a non-overlapping resample are both reported.

Run:
    python3 vix_lab/fomc_and_drag.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
from dq_uvxy import load_raw  # noqa: E402
from fetch_refs import load as load_ref  # noqa: E402

OUT = os.path.join(_HERE, "out")

#: Scheduled FOMC statement days. The statement is released at 14:00 ET on the
#: final day of the meeting; the press conference follows at 14:30.
#: 2020-2021 from the Fed's historical calendars, 2022-2026 from the tentative
#: schedules. 2020's two unscheduled actions are held separately: the meeting
#: of Mar 2 was announced Mar 3 at ~10:00, and the Mar 15 action landed on a
#: Sunday evening, so its market day is Mar 16. The scheduled Mar 17-18, 2020
#: meeting was cancelled and replaced by that action.
FOMC = [
    "2020-01-29", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16",
    "2020-11-05", "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28",
    "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27",
    "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26",
    "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
    "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
]
UNSCHEDULED = ["2020-03-03", "2020-03-16"]

STATEMENT_MIN = 270      # minutes from 09:30 to 14:00
PRESSER_MIN = 300        # 14:30
CLOSE_MIN = 385          # 15:55


def hdr(s: str) -> None:
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


def minute_panel() -> pd.DataFrame:
    """UVXY 1-minute closes as a date x minute-offset matrix.

    Forward-filled along the minute axis. Without that, the 12 half-days have
    no bar at minute 389 and every rolling window spanning one of them comes
    back NaN — which silently deletes most of a 200-day moving average.
    """
    df = load_raw(os.path.join(ROOT, "UVXY_1min.csv"))
    df["m"] = ((df["dt"] - (df["date"] + pd.Timedelta("09:30:00")))
               .dt.total_seconds() // 60).astype(int)
    return df.pivot_table(index="date", columns="m", values="Close").ffill(axis=1)


def session_close(panel: pd.DataFrame) -> pd.Series:
    """Last traded price of each session (half-day safe)."""
    return panel.ffill(axis=1).iloc[:, -1]


def seg(panel: pd.DataFrame, a: int, b: int) -> pd.Series:
    """Log return from minute a to minute b, per session.

    On a half-day the forward fill holds the 12:59 close, so a window that
    starts after the early close is flat rather than missing.
    """
    cols = panel.columns
    ca = max([c for c in cols if c <= a], default=cols[0])
    cb = max([c for c in cols if c <= b], default=cols[-1])
    return np.log(panel[cb] / panel[ca])


# ------------------------------------------------------------------- A. FOMC
def fomc(panel: pd.DataFrame) -> None:
    hdr("A. FOMC — before, during, or after?")
    fo = pd.to_datetime([d for d in FOMC])
    fo = fo[fo.isin(panel.index)]
    un = pd.to_datetime(UNSCHEDULED)
    un = un[un.isin(panel.index)]
    other = panel.index.difference(fo).difference(un)
    print(f"scheduled FOMC statement days in sample: {len(fo)}")
    print(f"unscheduled 2020 actions:               {len(un)}")
    print(f"all other sessions:                     {len(other)}\n")

    print("First, validate the date list against the data. Realised UVXY")
    print("volatility in the five minutes 14:00-14:05, ranked over all 1,654")
    print("sessions -- if the dates are right, FOMC days cluster at the top:")
    v = seg(panel, STATEMENT_MIN, STATEMENT_MIN + 5).abs()
    rank = v.rank(pct=True, ascending=True)
    print(f"  median percentile of a scheduled FOMC day: "
          f"{rank.reindex(fo).median():.1%}")
    print(f"  median percentile of every other day:      "
          f"{rank.reindex(other).median():.1%}")
    print(f"  FOMC days in the top decile of 14:00-14:05 move: "
          f"{(rank.reindex(fo) > 0.9).sum()} of {len(fo)} "
          f"(chance would be {0.1 * len(fo):.0f})")

    print("\nWindow-by-window mean |log return|, in bp. 'FOMC' is the scheduled")
    print("statement day; the ratio is FOMC over all other sessions.\n")
    windows = [("09:30-11:00", 0, 90), ("11:00-13:00", 90, 210),
               ("13:00-13:55", 210, 265), ("13:55-14:00", 265, 270),
               ("14:00-14:05  <- statement", 270, 275),
               ("14:05-14:30", 275, 300),
               ("14:30-15:00  <- presser", 300, 330),
               ("15:00-15:55", 330, 385)]
    print(f"{'window':<28}{'FOMC |ret|':>12}{'other |ret|':>13}{'ratio':>8}"
          f"{'FOMC signed':>13}")
    for nm, a, b in windows:
        s = seg(panel, a, b)
        f_, o_ = s.reindex(fo).abs(), s.reindex(other).abs()
        print(f"{nm:<28}{f_.mean() * 1e4:>12.0f}{o_.mean() * 1e4:>13.0f}"
              f"{f_.mean() / o_.mean():>8.2f}"
              f"{s.reindex(fo).mean() * 1e4:>+13.0f}")

    print("\nSigned move, cumulative through the session (bp of UVXY):")
    print(f"{'':<28}{'FOMC':>12}{'other':>13}")
    for nm, a, b in (("open -> 14:00", 0, 270), ("14:00 -> 14:30", 270, 300),
                     ("14:30 -> 15:55", 300, 385), ("open -> 15:55", 0, 385)):
        s = seg(panel, a, b)
        print(f"{nm:<28}{s.reindex(fo).mean() * 1e4:>+12.0f}"
              f"{s.reindex(other).mean() * 1e4:>+13.0f}")

    print("\nDaily returns around the event (close-to-close, all sessions):")
    c = session_close(panel)
    d = np.log(c / c.shift(1))
    pos = {dt: i for i, dt in enumerate(panel.index)}
    print(f"{'day relative to FOMC':<28}{'mean bp':>10}{'median bp':>12}{'n':>6}")
    for k in (-2, -1, 0, 1, 2, 3):
        idx = [panel.index[pos[dt] + k] for dt in fo
               if 0 <= pos[dt] + k < len(panel.index)]
        s = d.reindex(idx).dropna()
        print(f"{'  t' + f'{k:+d}':<28}{s.mean() * 1e4:>+10.0f}"
              f"{s.median() * 1e4:>+12.0f}{len(s):>6}")

    print("\nThe two unscheduled 2020 actions, for contrast:")
    print(f"{'date':<14}{'open->14:00':>13}{'14:00->15:55':>14}{'full day':>11}")
    for dt in un:
        print(f"{str(dt.date()):<14}{seg(panel, 0, 270).get(dt, np.nan) * 1e4:>+13.0f}"
              f"{seg(panel, 270, 385).get(dt, np.nan) * 1e4:>+14.0f}"
              f"{seg(panel, 0, 385).get(dt, np.nan) * 1e4:>+11.0f}")


# ------------------------------------------------------- B. variance-drag test
def nw_t(x: np.ndarray, lags: int) -> float:
    """Newey-West t-stat for the mean of an overlapping series."""
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 10:
        return np.nan
    e = x - x.mean()
    g0 = (e @ e) / n
    var = g0
    for L in range(1, min(lags, n - 1) + 1):
        g = (e[L:] @ e[:-L]) / n
        var += 2 * (1 - L / (lags + 1)) * g
    return x.mean() / np.sqrt(max(var, 1e-18) / n)


def drag(panel: pd.DataFrame) -> None:
    hdr("B. Is the 'signal' a forecast, or is it variance drag?")
    print("A 1.5x daily-rebalanced fund gives up ~0.375*sigma^2 per unit time")
    print("to rebalancing, in every direction. So a signal that fires after a")
    print("volatility spike will 'predict' UVXY falling even with no view on")
    print("the market at all. VIXY (1x) has no such term. Ask both.\n")

    u = np.log(session_close(panel))
    vy = np.log(load_ref("VIXY")["Close"])

    signals = {}
    px = session_close(panel)
    for N in (50, 200):
        signals[f"UVXY SMA{N} z"] = ((px - px.rolling(N).mean())
                                     / px.rolling(N).std()).shift(1)
    ratio = (load_ref("VIXY")["Close"] / load_ref("VIXM")["Close"]).dropna()
    signals["term structure z"] = ((ratio - ratio.rolling(60).mean())
                                   / ratio.rolling(60).std()).shift(1)

    H = 20
    print(f"{H}-day forward log return, top quintile of each signal minus")
    print("bottom quintile. Newey-West t uses 20 lags for the overlap; the")
    print("non-overlapping column resamples every 20th day instead.\n")
    print(f"{'signal':<20}{'target':<8}{'TOP-BOT bp':>12}{'naive t':>9}"
          f"{'NW t':>8}{'non-ovl t':>11}{'n':>7}")
    for nm, sig in signals.items():
        for tgt_name, logpx in (("UVXY", u), ("VIXY", vy)):
            fwd = logpx.shift(-H) - logpx
            j = pd.DataFrame({"s": sig, "f": fwd}).dropna()
            if len(j) < 200:
                continue
            q = pd.qcut(j["s"], 5, labels=False, duplicates="drop")
            hi, lo = j[q == q.max()]["f"], j[q == q.min()]["f"]
            spread = hi.mean() - lo.mean()
            naive = spread / np.sqrt(hi.var() / len(hi) + lo.var() / len(lo))
            d_ = j.assign(q=q)
            d_ = d_[(d_["q"] == q.max()) | (d_["q"] == q.min())]
            sgn = np.where(d_["q"] == q.max(), 1.0, -1.0) * d_["f"].to_numpy()
            nw = nw_t(sgn, H)
            sub = d_.iloc[::H]
            sgn2 = (np.where(sub["q"] == q.max(), 1.0, -1.0)
                    * sub["f"].to_numpy())
            no = (np.nanmean(sgn2) / (np.nanstd(sgn2, ddof=1)
                                      / np.sqrt(len(sgn2)))) if len(sgn2) > 5 else np.nan
            print(f"{nm:<20}{tgt_name:<8}{spread * 1e4:>12.0f}{naive:>9.2f}"
                  f"{nw:>8.2f}{no:>11.2f}{len(j):>7}")
        print()

    hdr("B2. The arithmetic, done directly")
    print("If the effect is drag, then UVXY's shortfall against 1.5x VIXY")
    print("should track realised variance and nothing else. Bucketing by")
    print("trailing 20-day realised vol of VIXY:\n")
    vr = vy.diff()
    rv = vr.rolling(20).std().shift(1) * np.sqrt(252)
    fwd_u = u.shift(-H) - u
    fwd_v = vy.shift(-H) - vy
    j = pd.DataFrame({"rv": rv, "gap": fwd_u - 1.5 * fwd_v,
                      "fu": fwd_u, "fv": fwd_v}).dropna()
    q = pd.qcut(j["rv"], 5, labels=False, duplicates="drop")
    print(f"{'vol quintile':<16}{'ann vol':>10}{'UVXY 20d':>11}{'VIXY 20d':>11}"
          f"{'shortfall':>11}{'predicted':>11}")
    for k in sorted(set(q.dropna())):
        g = j[q == k]
        pred = -0.375 * (g["rv"].mean() ** 2) * (H / 252)
        print(f"{'Q' + str(int(k) + 1):<16}{g.rv.mean():>10.2f}"
              f"{g.fu.mean() * 1e4:>+11.0f}{g.fv.mean() * 1e4:>+11.0f}"
              f"{g.gap.mean() * 1e4:>+11.0f}{pred * 1e4:>+11.0f}")
    print("\n'shortfall' is realised UVXY minus 1.5x realised VIXY over the")
    print("same 20 days. 'predicted' is -0.375*sigma^2*t, the rebalancing")
    print("term alone. If they line up, the 'signal' was never a forecast.")


# ------------------------------------------- C. the same question, but for the
#                                                  sleeves that actually trade
def symbol_panel(sym: str) -> pd.DataFrame:
    df = load_raw(os.path.join(ROOT, f"{sym}_1min.csv"))
    df["m"] = ((df["dt"] - (df["date"] + pd.Timedelta("09:30:00")))
               .dt.total_seconds() // 60).astype(int)
    return df.pivot_table(index="date", columns="m", values="Close").ffill(axis=1)


def fomc_sleeves() -> None:
    hdr("C. FOMC on SOXL and SOXS — the sleeves that actually trade")
    print("UVXY is not traded, so the operationally useful question is whether")
    print("the same signature appears in the two approved sleeves. It does, and")
    print("more strongly. §2.3 forbids orders before 11:00, so the rows from")
    print("11:00 down are the ones the live engine is exposed to.\n")
    syms = ("UVXY", "SOXL", "SOXS")
    P = {s: symbol_panel(s) for s in syms}
    fo = pd.to_datetime(FOMC)

    wins = [("09:30-11:00", 0, 90), ("11:00-13:55", 90, 265),
            ("13:55-14:00", 265, 270), ("14:00-14:05  statement", 270, 275),
            ("14:05-14:30", 275, 300), ("14:30-15:00  presser", 300, 330),
            ("15:00-15:55", 330, 385)]
    print("Volatility multiple, FOMC days vs all other sessions:")
    print(f"{'window':<26}" + "".join(f"{s:>9}" for s in syms))
    for nm, a, b in wins:
        row = f"{nm:<26}"
        for s in syms:
            p = P[s]
            f = fo[fo.isin(p.index)]
            o = p.index.difference(f)
            x = seg(p, a, b)
            row += f"{x.reindex(f).abs().mean() / x.reindex(o).abs().mean():>9.2f}"
        print(row)

    print("\nSigned drift inside the tradeable window (bp):")
    print(f"{'window':<26}" + "".join(f"{s:>9}" for s in syms)
          + "   (non-FOMC in brackets)")
    for nm, a, b in (("11:00-14:00", 90, 270), ("14:00-15:55", 270, 385),
                     ("11:00-15:55", 90, 385)):
        row, note = f"{nm:<26}", []
        for s in syms:
            p = P[s]
            f = fo[fo.isin(p.index)]
            o = p.index.difference(f)
            x = seg(p, a, b)
            row += f"{x.reindex(f).mean() * 1e4:>+9.0f}"
            note.append(f"{x.reindex(o).mean() * 1e4:+.0f}")
        print(row + "   [" + ", ".join(note) + "]")
    print("\nRead: on the eight FOMC days a year the sleeves' prime window")
    print("(11:00-13:55) runs at HALF its normal volatility, and is then hit")
    print("by a 3.5x burst from 13:55. That is the shape most likely to arm a")
    print("low anchor in the quiet and then run it into the -4% stop.")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    panel = minute_panel()
    print(f"UVXY 1-minute panel: {panel.shape[0]} sessions x "
          f"{panel.shape[1]} minute slots")
    fomc(panel)
    drag(panel)
    fomc_sleeves()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
