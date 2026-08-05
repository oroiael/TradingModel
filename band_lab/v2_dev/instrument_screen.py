"""
Instrument screen — which candidates are worth a transfer test?

`band_lab/transfer_test.py` already runs the LOCKED core on a candidate. It is
not cheap: it needs six years of 5-minute bars per symbol. This script is the
step *before* — a fast filter that says which symbols deserve that run, using
metrics derived from why the previous candidates failed rather than from
generic "good stock" intuition.

WHAT THE STRATEGY ACTUALLY NEEDS, and how we know
-------------------------------------------------
`MASTER_STRATEGY_DOCUMENT.md` §9.1 diagnosed the SPXL failure precisely:
SPXL's median daily range is 2.92% against SOXL's 6.67%. Rescaling only the
*gate* produced 4.5 bp/ON-day because the 1% dip starved the cadence to 1.73
trades/day; rescaling the *dip* too restored 3.07 trades/day and tripled the
edge to 14.1 bp — still a fifth of SOXL's 65.6.

So the binding constraint is **churn density**: how often price falls `dip%`
below the running session high, often enough to fill the daily trade cap,
with each swing large enough to clear costs. Everything below measures that
directly rather than by proxy.

The screen is a filter, not an adoption. Clearing it earns a
`transfer_test.py` run; adoption needs a full prespecified protocol, as
`V14_PAIR_PROTOCOL.md` did for SOXS.

USAGE
-----
    # offline — screens every <SYM>_5min_6Years.csv already in the repo
    python3 band_lab/v2_dev/instrument_screen.py

    # with IBKR (TWS running) — fetches candidates, then screens them
    python3 band_lab/v2_dev/instrument_screen.py --ib --symbols TQQQ,TNA,LABU
    python3 band_lab/v2_dev/instrument_screen.py --ib --universe   # the default list
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
ROOT = os.path.dirname(_BAND_LAB)
for _p in (os.path.join(_BAND_LAB, "live"), os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from strategy_core import Bar, session_stats          # noqa: E402
from spec_constants import (                          # noqa: E402
    DIP_PCT, GATE_ATR5_MIN, MAX_FILLS, bar_index,
)

START_IDX = bar_index("11:00")
FLATTEN_IDX = bar_index("15:55")

#: IBKR Fixed is per share, so a cheap instrument costs more in basis points
#: for identical share-count logic. `V14_PAIR_PROTOCOL.md` T1 ran exactly this
#: derivation for SOXS and it is why SOXS costs 2.86 bp/fill against SOXL's 1.17.
COMMISSION_PER_SHARE = 0.005
REG_FEE_BP_PER_SELL = 0.35

#: A default candidate universe of US-listed leveraged ETFs. This is a starting
#: list to edit, not a claim about what exists — `--symbols` overrides it.
DEFAULT_UNIVERSE = [
    "TQQQ", "SQQQ", "SPXL", "SPXS", "TNA", "TZA", "FAS", "FAZ",
    "LABU", "LABD", "TECL", "TECS", "NUGT", "DUST", "ERX", "ERY",
    "YINN", "YANG", "UDOW", "SDOW", "DFEN", "DRN", "DRV", "WEBL",
    "BOIL", "KOLD", "UVXY", "SVXY", "GDXU", "JNUG", "SOXL", "SOXS",
]


@dataclass
class Screen:
    symbol: str
    sessions: int
    median_range_pct: float      # the §9.1 headline: SOXL 6.67, SPXL 2.92
    range_ratio: float           # vs SOXL — the §9.1 scaling factor
    gate_rate: float             # % of sessions with ATR5 >= 6 (absolute gate)
    triggers_per_day: float      # dips below the running high — the actual trigger
    cap_fill_rate: float         # % of days that could reach MAX_FILLS triggers
    median_price: float
    commission_bp: float         # per round trip, from price
    median_dollar_vol: float
    corr_soxl: float           # INSTRUMENT daily-return corr, not sleeve corr

    def verdict(self, ref: "Screen") -> tuple[bool, list[str]]:
        """Pass/fail against the SOXL reference. Thresholds are stated, not tuned.

        Each is anchored to a measured fact about why previous candidates
        failed, not to a round number chosen for looking reasonable.
        """
        fails = []
        # §9.1: SPXL at 0.44x SOXL's range needed every level rescaled and still
        # reached only 14.1 bp. Below half of SOXL's range, the locked 1% levels
        # cannot work and a rescaled variant is a different strategy.
        if self.range_ratio < 0.50:
            fails.append(f"range {self.range_ratio:.2f}x SOXL (<0.50 — §9.1 SPXL case)")
        # §9.1 cell B: 1.73 triggers/day produced 4.5 bp. The cap is 5/day and
        # SOXL runs 3.17 fills/day; a candidate must be able to feed that.
        if self.triggers_per_day < 2.5:
            fails.append(f"{self.triggers_per_day:.1f} triggers/day (<2.5 — cadence starved)")
        # The gate is ABSOLUTE (transfer_test.py header). A candidate that never
        # passes ATR5>=6 never trades at all under the locked rules.
        if self.gate_rate < 0.25:
            fails.append(f"gate fires {self.gate_rate:.0%} of days (<25%)")
        # Costs must not eat the target. SOXS at 2.86 bp/fill is the worst
        # already accepted; twice that against a 100 bp target is not viable.
        if self.commission_bp > 6.0:
            fails.append(f"{self.commission_bp:.1f} bp/round-trip commission (>6)")
        # $75k per sleeve; 0.5% of median dollar volume is a conservative cap.
        if self.median_dollar_vol < 15_000_000:
            fails.append(f"${self.median_dollar_vol/1e6:.1f}M/day volume (<$15M)")
        return (not fails), fails


def screen_sessions(symbol: str, sessions: list, dip: float = DIP_PCT) -> Screen:
    """All metrics from one list of (date, [Bar]) — the same shape the engine uses."""
    ranges, triggers, closes, dvols, prices, dates = [], [], [], [], [], []
    for date, bars in sessions:
        if len(bars) < 20:
            continue
        st = session_stats(bars)
        ranges.append(st.range_pct)
        closes.append(st.close)
        dates.append(date)
        prices.append(bars[-1].close)
        dvols.append(sum(b.close * b.volume for b in bars))

        # The actual V1 trigger: price dipping `dip` below the running session
        # high built from COMPLETED bars only (§2.5), counted after 11:00.
        high = float("-inf")
        n = 0
        for b in bars:
            if b.idx > FLATTEN_IDX:
                break
            if b.idx >= START_IDX and np.isfinite(high) and b.low <= high * (1 - dip):
                n += 1
                high = float("-inf")        # one trigger per swing, then re-arm
            high = max(high, b.high)
        triggers.append(n)

    ranges = np.asarray(ranges, dtype=float)
    atr5 = pd.Series(ranges).rolling(5).mean().shift(1)
    ret = pd.Series(closes, index=pd.DatetimeIndex(dates)).pct_change()
    return Screen(
        symbol=symbol, sessions=len(ranges),
        median_range_pct=float(np.median(ranges)),
        range_ratio=float("nan"),
        gate_rate=float((atr5 >= GATE_ATR5_MIN).mean()),
        triggers_per_day=float(np.mean(triggers)),
        cap_fill_rate=float(np.mean([t >= MAX_FILLS for t in triggers])),
        # The MOST RECENT close, never a long-run median: SOXS's file is
        # back-adjusted and opens at $1.07M/share (the Phase 1 S7 series), so a
        # median price would understate its commission by ~6x. Reproduces the
        # documented 1.17 bp (SOXL) / 2.86 bp (SOXS) from IMPLEMENTATION_SPEC §8.
        median_price=float(prices[-1]),
        commission_bp=float(2 * COMMISSION_PER_SHARE / prices[-1] * 1e4
                            + REG_FEE_BP_PER_SELL),
        median_dollar_vol=float(np.median(dvols)),
        corr_soxl=float("nan"),
    ), ret


# ------------------------------------------------------------------ sources
def from_csv(symbol: str, root: str = ROOT):
    from replay import load_sessions
    return load_sessions(symbol, root)


def from_ib(broker, symbol: str, days: int = 250):
    """5-minute RTH bars from IBKR, chunked to stay inside pacing limits.

    §6.4 (duration limits for 5-minute bars) is still an unverified assumption,
    so this asks in conservative 30-day slices rather than one large request.
    """
    out, end = {}, datetime.now()
    remaining = days
    while remaining > 0:
        chunk = min(remaining, 30)
        try:
            got = broker.historical_sessions(symbol, end, f"{chunk} D", "5 mins")
        except Exception as exc:                          # noqa: BLE001
            print(f"    {symbol}: fetch failed ({exc}); using what we have")
            break
        if not got:
            break
        for d, bars in got:
            out.setdefault(d, bars)
        oldest = min(out)
        end = datetime.combine(oldest, datetime.min.time())
        remaining -= chunk
    return [(pd.Timestamp(d), b) for d, b in sorted(out.items())]


# ------------------------------------------------------------------ report
def run(candidates: dict, dip: float = DIP_PCT) -> pd.DataFrame:
    rows, rets = [], {}
    for sym, sessions in candidates.items():
        if len(sessions) < 30:
            print(f"  {sym}: only {len(sessions)} sessions — skipped")
            continue
        s, r = screen_sessions(sym, sessions, dip)
        rows.append(s)
        rets[sym] = r
    if not rows:
        return pd.DataFrame()

    ref = next((s for s in rows if s.symbol == "SOXL"), rows[0])
    for s in rows:
        s.range_ratio = s.median_range_pct / ref.median_range_pct
        # NOTE: this is the correlation of the *instruments*, which is what a
        # screen can see. V14's "-0.70 correlated SOXS sleeve" is the
        # correlation of the two strategies' daily P&L — a different and
        # smaller number, only obtainable after a transfer test runs.
        if s.symbol in rets and "SOXL" in rets:
            a, b = rets[s.symbol].align(rets["SOXL"], join="inner")
            s.corr_soxl = float(a.corr(b)) if len(a) > 30 else float("nan")

    df = pd.DataFrame([asdict(s) for s in rows]).sort_values(
        "triggers_per_day", ascending=False)

    print("=" * 104)
    print("INSTRUMENT SCREEN — does the candidate produce enough churn to feed the locked rules?")
    print(f"reference = {ref.symbol} (median range {ref.median_range_pct:.2f}%)")
    print("=" * 104)
    print(f"{'symbol':<8}{'sess':>6}{'range%':>8}{'xSOXL':>7}{'gate%':>7}"
          f"{'trig/day':>10}{'cap%':>7}{'price':>8}{'cost bp':>9}{'$vol M':>9}"
          f"{'inst corr':>10}  verdict")
    for s in rows:
        ok, fails = s.verdict(ref)
        mark = "PASS" if ok else "; ".join(fails)
        print(f"{s.symbol:<8}{s.sessions:>6}{s.median_range_pct:>8.2f}"
              f"{s.range_ratio:>7.2f}{s.gate_rate:>7.0%}{s.triggers_per_day:>10.2f}"
              f"{s.cap_fill_rate:>7.0%}{s.median_price:>8.0f}{s.commission_bp:>9.2f}"
              f"{s.median_dollar_vol/1e6:>9.0f}{s.corr_soxl:>10.2f}  {mark}")
    print("\nA PASS earns a transfer_test.py run — not an adoption. Adoption needs a")
    print("prespecified protocol (see V14_PAIR_PROTOCOL.md) and, per §11, a")
    print("deliberate documented decision.")
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description="screen instruments for the churn harvester")
    ap.add_argument("--ib", action="store_true", help="fetch from IBKR (needs TWS)")
    ap.add_argument("--symbols", default=None, help="comma-separated candidates")
    ap.add_argument("--universe", action="store_true",
                    help="use the built-in leveraged-ETF list")
    ap.add_argument("--days", type=int, default=250, help="sessions to fetch per symbol")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497)
    ap.add_argument("--client-id", type=int, default=31)
    ap.add_argument("--out", default=os.path.join(_HERE, "out", "instrument_screen.csv"))
    args = ap.parse_args()

    if args.ib:
        from broker import IBBroker
        syms = (args.symbols.split(",") if args.symbols
                else DEFAULT_UNIVERSE if args.universe else ["SOXL", "SOXS"])
        # SOXL is the reference every ratio is taken against; always include it.
        if "SOXL" not in syms:
            syms.append("SOXL")
        broker = IBBroker(host=args.host, port=args.port, client_id=args.client_id,
                          readonly=True, on_event=lambda l, m: print(f"  [{l}] {m}"))
        broker.connect()
        try:
            cands = {}
            for s in syms:
                print(f"  fetching {s} ...", flush=True)
                cands[s] = from_ib(broker, s, args.days)
        finally:
            broker.disconnect()
    else:
        found = sorted(os.path.basename(p).split("_")[0]
                       for p in glob.glob(os.path.join(ROOT, "*_5min_6Years.csv")))
        syms = args.symbols.split(",") if args.symbols else found
        cands = {}
        for s in syms:
            try:
                cands[s] = from_csv(s)
            except Exception as exc:                       # noqa: BLE001
                print(f"  {s}: {exc}")
        print(f"offline mode — screening {', '.join(cands)}\n")

    df = run(cands)
    if len(df):
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        df.to_csv(args.out, index=False)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
