"""
The two guards every future test has to pass through.

**T23 — the benchmark column.** Every backtest in this repository's history
reported its own return without printing what the underlying did over the
identical window. That single omission made a -65% option strategy the top
recommendation in one study, hid the band strategy's failure for three weeks,
and made a PMCC that loses on 89% of start dates look like +257%.

A convention would not have prevented it — the convention already existed in
spirit. So `Result` *refuses to be constructed* without a benchmark. There is no
polite path around it: no default, no `None`, no "benchmark not applicable".

**T20 — the friction screen.** Before testing an idea, know whether its target
move can pay for the trading. Friction here is measured, not assumed:

    commission   1.16 bp/side   IBKR statement 2026-08-03..08-25, $599.36
    spread       2.82 bp entry, 2.89 bp exit, from live fills on 30 trades
    round trip   8.03 bp

Those numbers are SOXL/SOXS specific. For any other instrument the screen
refuses to guess — supply a measured figure or get an exception.

    python3 band_lab/v2_dev/research_kit.py          # self-test + worked examples
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------- T20 friction
@dataclass(frozen=True)
class Friction:
    """Round-trip cost, in basis points. Every field traceable to a measurement."""
    symbol: str
    commission_bp_per_side: float
    spread_bp_entry: float
    spread_bp_exit: float
    source: str

    @property
    def round_trip_bp(self) -> float:
        return (2 * self.commission_bp_per_side
                + self.spread_bp_entry + self.spread_bp_exit)


#: Only instruments whose costs have actually been measured on live fills.
#: Adding a row here without a live measurement behind it defeats the point.
MEASURED = {
    "SOXL": Friction("SOXL", 1.16, 2.82, 2.89,
                     "IBKR statement 2026-08-03..08-25 ($599.36) + 30 live fills"),
    "SOXS": Friction("SOXS", 1.16, 2.82, 2.89,
                     "IBKR statement 2026-08-03..08-25 ($599.36) + 30 live fills"),
}


class UnmeasuredInstrument(RuntimeError):
    """Raised rather than substituting a plausible-looking cost estimate."""


def friction_for(symbol: str) -> Friction:
    f = MEASURED.get(symbol.upper())
    if f is None:
        raise UnmeasuredInstrument(
            f"no measured friction for {symbol}. Supply one from real fills — "
            f"guessing a spread is how a strategy gets approved on costs it "
            f"never had to pay. Known: {sorted(MEASURED)}")
    return f


def friction_screen(target_move_pct: float, symbol: str = "SOXL",
                    stop_move_pct: Optional[float] = None) -> dict:
    """Can a move this size pay for the trading?

    `target_move_pct` and `stop_move_pct` are fractions (0.01 = 1%). If a stop is
    given, the break-even win rate accounts for the asymmetry: a +1%/-4% bet
    needs to win 80% of the time before costs, and more after.
    """
    f = friction_for(symbol)
    rt = f.round_trip_bp
    target_bp = target_move_pct * 1e4
    share = rt / target_bp if target_bp else float("inf")

    out = dict(symbol=symbol, target_bp=target_bp, friction_bp=rt,
               friction_share=share, source=f.source)

    # The win rate a SYMMETRIC bet (win `target`, lose `target`) must clear just
    # to break even:  p(target - f) = (1-p)(target + f)  ->  p = 0.5 + f/(2*target).
    # This replaces a "verdict" column whose thresholds (>25% hostile, >10%
    # expensive) were invented. They looked authoritative and rested on nothing,
    # which is the failure mode this module exists to prevent. Arithmetic with a
    # measured comparison beats an adjective.
    out["breakeven_symmetric"] = 0.5 + rt / (2 * target_bp) if target_bp else float("nan")

    if stop_move_pct:
        stop_bp = stop_move_pct * 1e4
        # Asymmetric bet: p*target = (1-p)*stop  ->  p = stop/(target+stop)
        # before costs. Costs are paid on every trade, so they raise the bar.
        out["breakeven_gross"] = stop_bp / (target_bp + stop_bp)
        out["breakeven_net"] = (stop_bp + rt) / (target_bp + stop_bp)
    return out


#: Measured, `move_census.py`, 2022+, ~445k starting minutes per symbol: from any
#: minute, the share of the time price reaches +X before -X. Never above 50%.
OBSERVED_HIT_RATE = {0.0025: 0.492, 0.005: 0.497, 0.01: 0.500, 0.02: 0.495}


# --------------------------------------------------------------- T23 benchmark
def daily_closes(symbol: str) -> pd.Series:
    """Session closes from the 5-minute file. Raises if the file is an LFS stub."""
    path = os.path.join(ROOT, f"{symbol}_5min_6Years.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"no price file for {symbol} at {path}")
    with open(path, "rb") as fh:
        if fh.read(40).startswith(b"version https://git-lfs"):
            raise FileNotFoundError(
                f"{symbol}: price file is an LFS pointer — run `git lfs pull`. "
                f"A benchmark cannot be silently skipped.")
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    return df.assign(date=dt.dt.normalize()).groupby("date")["Close"].last()


def benchmark_return(symbol: str, start, end,
                     closes: Optional[pd.Series] = None) -> float:
    """Buy-and-hold return over the identical window. The number nothing printed."""
    c = closes if closes is not None else daily_closes(symbol)
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    w = c[(c.index >= s) & (c.index <= e)]
    if len(w) < 2:
        raise ValueError(f"{symbol}: fewer than 2 sessions between {s.date()} "
                         f"and {e.date()} — cannot benchmark")
    return float(w.iloc[-1] / w.iloc[0] - 1.0)


class MissingBenchmark(RuntimeError):
    """Raised when a result is assembled without the column that matters."""


@dataclass
class Result:
    """A backtest result that cannot exist without its benchmark.

    Construct it with `Result.of(...)`, which computes the benchmark from the
    price file rather than accepting one on trust. The plain constructor still
    validates, so neither route can produce a result missing the comparison.
    """
    name: str
    start: pd.Timestamp
    end: pd.Timestamp
    strategy_return: float
    benchmark_symbol: str
    benchmark_return: float
    n_trades: int = 0
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.benchmark_symbol is None or self.benchmark_return is None:
            raise MissingBenchmark(
                f"{self.name}: a result without a benchmark is not a result. "
                f"This is T23 and it is not optional.")
        if not np.isfinite(self.benchmark_return):
            raise MissingBenchmark(
                f"{self.name}: benchmark_return is not finite "
                f"({self.benchmark_return!r}).")

    @classmethod
    def of(cls, name, start, end, strategy_return, benchmark_symbol,
           closes=None, **kw):
        return cls(name=name, start=pd.Timestamp(start), end=pd.Timestamp(end),
                   strategy_return=float(strategy_return),
                   benchmark_symbol=benchmark_symbol,
                   benchmark_return=benchmark_return(benchmark_symbol, start,
                                                     end, closes),
                   **kw)

    @property
    def excess(self) -> float:
        return self.strategy_return - self.benchmark_return

    @property
    def beat_benchmark(self) -> bool:
        return self.excess > 0

    def line(self) -> str:
        return (f"{self.name:<28}{self.strategy_return*100:>+9.1f}%"
                f"{self.benchmark_return*100:>+11.1f}%"
                f"{self.excess*100:>+10.1f}%   "
                f"{'BEAT' if self.beat_benchmark else 'LOST'}")


def table(results: Sequence[Result]) -> str:
    if not results:
        return "  (no results)"
    head = (f"  {'result':<28}{'strategy':>9}{'benchmark':>12}{'excess':>10}\n"
            f"  " + "-" * 62)
    body = "\n".join("  " + r.line() for r in results)
    won = sum(r.beat_benchmark for r in results)
    tail = (f"  " + "-" * 62 +
            f"\n  beat the benchmark: {won} of {len(results)} "
            f"({won/len(results)*100:.0f}%)")
    return f"{head}\n{body}\n{tail}"


# --------------------------------------------------------------------- selftest
def _selftest() -> int:
    print("=" * 74)
    print("SELF-TEST — the guards must refuse the things they exist to refuse")
    print("=" * 74)
    fails = 0

    def ok(name, cond):
        nonlocal fails
        if not cond:
            fails += 1
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    try:
        Result(name="x", start=pd.Timestamp("2022-01-03"),
               end=pd.Timestamp("2022-06-01"), strategy_return=0.5,
               benchmark_symbol=None, benchmark_return=None)
        ok("a result without a benchmark is refused", False)
    except MissingBenchmark:
        ok("a result without a benchmark is refused", True)

    try:
        Result(name="x", start=pd.Timestamp("2022-01-03"),
               end=pd.Timestamp("2022-06-01"), strategy_return=0.5,
               benchmark_symbol="SOXL", benchmark_return=float("nan"))
        ok("a NaN benchmark is refused", False)
    except MissingBenchmark:
        ok("a NaN benchmark is refused", True)

    try:
        friction_for("FAS")
        ok("friction for an unmeasured instrument is refused", False)
    except UnmeasuredInstrument:
        ok("friction for an unmeasured instrument is refused", True)

    try:
        benchmark_return("SOXL", "2022-01-03", "2022-01-03")
        ok("a one-session window is refused", False)
    except ValueError:
        ok("a one-session window is refused", True)

    closes = daily_closes("SOXL")
    r = Result.of("smoke", "2022-01-03", "2026-07-02", 0.10, "SOXL",
                  closes=closes)
    ok("benchmark computes from the price file", abs(r.benchmark_return - 1.513) < 0.01)
    ok("excess is strategy minus benchmark",
       abs(r.excess - (0.10 - r.benchmark_return)) < 1e-12)

    print("\n" + "=" * 74)
    print("T20 — FRICTION SCREEN (measured costs, SOXL)")
    print("=" * 74)
    f = friction_for("SOXL")
    print(f"  round trip {f.round_trip_bp:.2f} bp "
          f"= {2*f.commission_bp_per_side:.2f} commission "
          f"+ {f.spread_bp_entry + f.spread_bp_exit:.2f} spread")
    print(f"  source: {f.source}")
    print("\n  Friction is the cost of ONE COMPLETE TRADE — buy and sell.")
    print("  8.03 bp = 0.0803% = about $56 on a $70,000 position, in and out.")
    print("\n  'share of move' = friction / the move you are trying to capture.")
    print("  'break-even' = the win rate a symmetric win-X/lose-X bet needs just")
    print("  to cover friction:  0.5 + friction/(2 x move).  Pure arithmetic.")
    print("  'observed' = what actually happens, measured over ~445,000 minutes.")
    print(f"\n  {'target':>8}{'friction':>10}{'share':>9}"
          f"{'break-even':>12}{'observed':>10}   can it clear?")
    for m in (0.0025, 0.005, 0.01, 0.02):
        s = friction_screen(m)
        be = s["breakeven_symmetric"]
        obs = OBSERVED_HIT_RATE[m]
        gap = (be - obs) * 100
        can = "YES" if obs > be else f"no — short by {gap:.1f} points"
        print(f"  {m*100:>7.2f}%{s['friction_bp']:>9.2f}bp"
              f"{s['friction_share']*100:>8.1f}%{be*100:>11.1f}%{obs*100:>9.1f}%"
              f"   {can}")

    print(f"\n  the band strategy's own bet (+1% target, -4% stop):")
    s = friction_screen(0.01, "SOXL", stop_move_pct=0.04)
    print(f"    break-even win rate before costs  {s['breakeven_gross']*100:.1f}%")
    print(f"    break-even win rate after costs   {s['breakeven_net']*100:.1f}%")
    print(f"    measured P(target | resolved)      87.1%   -> the resolved bet "
          f"clears it")
    print(f"    but 33% of bets never resolve, and those average -0.79%")

    print("\n" + "=" * 74)
    print("T23 — WORKED EXAMPLE: what every past study should have printed")
    print("=" * 74)
    rows = [
        Result.of("R1 put diagonal", "2024-01-02", "2026-07-17", -0.650,
                  "SOXL", closes=closes, notes="prior study"),
        Result.of("R2 PMCC", "2024-01-02", "2026-07-17", 2.573,
                  "SOXL", closes=closes, notes="prior study"),
        Result.of("band, SOXL sleeve w=0.5", "2022-01-06", "2026-07-24", 0.779,
                  "SOXL", closes=closes, notes="corrected simulator"),
    ]
    print(table(rows))
    print("\n  Every one of these was reported without the middle column.")
    print("\n" + "=" * 74)
    print("FAILURES: 0 — the guards work" if not fails
          else f"FAILURES: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
