"""
Stage 6 — the shadow-parity report. `PHASE2_PLAN.md` Stage 6, `DEPLOYMENT.md` §12.3.

    python3 band_lab/live/report.py                     # today
    python3 band_lab/live/report.py --session 20260807
    python3 band_lab/live/report.py --weekly            # vs the §8 baselines
    python3 band_lab/live/report.py --list              # what sessions exist

This is the instrument the paper run exists to feed. Without it the engine
produces fills that nobody diffs against the backtest, and four weeks of running
answers nothing.

It asks four questions of each session, in descending order of how much they
matter:

**0. Is this session usable evidence at all?** Asked first, and loudly, because
the answer is often no. A mid-session restart, a hand-placed order, a late start,
a bar gap — each of these makes the numbers below describe something other than
the strategy. Sessions on 2026-08-06 and -07 were contaminated by all four, and a
report that quietly averaged them in would be worse than no report.

**1. Did the live engine do what the backtest would have done?** The same bars
the engine actually saw are replayed through the same state machine, and the
trades are diffed. A gap here is a fill-quality question. No gap and a gap in
P&L is an arithmetic question. They need separating, and only this can do it.

**2. Did any fill occur without the quote reaching the limit?** `PHASE2_PLAN.md`
§1's question. If IBKR's simulator fills a resting limit the market never traded
through, paper cannot validate assumption A1 at all and the §8 baselines stay
unfalsified — which would be worth knowing in week one rather than week four.

**3. On a same-bar re-entry, was the achieved price worse than the price just
sold?** `PHASE2_PARITY.md` S10/S11 predicts a systematic gap here, and says it is
"a sharper and faster test than watching aggregate bp". It is the single most
consequential open question in the project.

Read-only. It never writes to the store and never talks to a broker.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import EngineConfig                                  # noqa: E402
from replay import replay_session                                # noqa: E402
from sleeve import SleeveConfig, SleeveStateMachine              # noqa: E402
from strategy_core import Bar                                    # noqa: E402

#: `IMPLEMENTATION_SPEC.md` §8, and the S11 planning figures beside them.
BASELINES = {
    "SOXL": {"fills_per_on_day": 3.17, "on_day_rate": 52.1, "target_pct": 71.3,
             "stop_pct": 9.9, "flatten_pct": 18.8, "net_bp": 61.9, "plan_bp": 40.0},
    "SOXS": {"fills_per_on_day": 3.36, "on_day_rate": 53.1, "target_pct": 71.8,
             "stop_pct": 9.3, "flatten_pct": 18.9, "net_bp": 48.1, "plan_bp": 30.0},
}
ROLE_NAME = {"E": "entry", "T": "target", "S": "stop", "F": "flatten"}


@dataclass
class Trade:
    """A round trip reconstructed from executions, not from engine memory."""
    symbol: str
    qty: float
    entry_px: float
    exit_px: float
    outcome: str
    entry_ts: str
    exit_ts: str
    entry_execs: int = 1
    exit_execs: int = 1

    @property
    def ret_frac(self) -> float:
        return (self.exit_px - self.entry_px) / self.entry_px if self.entry_px else 0.0

    def bp_on(self, capital: float) -> float:
        return (self.qty * (self.exit_px - self.entry_px) / capital * 1e4
                if capital else 0.0)


@dataclass
class SessionReport:
    db: str
    session: str
    conn: sqlite3.Connection = field(init=False)

    def __post_init__(self) -> None:
        self.conn = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def rows(self, sql: str, args=()) -> list:
        return self.conn.execute(sql, args).fetchall()

    # ------------------------------------------------------------- sources
    def symbols(self) -> list[str]:
        return [r["symbol"] for r in self.rows(
            "SELECT DISTINCT symbol FROM daily WHERE session=? ORDER BY symbol",
            (self.session,))]

    def daily(self, symbol: str) -> Optional[sqlite3.Row]:
        got = self.rows("SELECT * FROM daily WHERE session=? AND symbol=?",
                        (self.session, symbol))
        return got[0] if got else None

    def fills(self, symbol: str) -> list[sqlite3.Row]:
        return self.rows("SELECT * FROM fills WHERE session=? AND symbol=? "
                         "ORDER BY ts, rowid", (self.session, symbol))

    def bars(self, symbol: str) -> list[Bar]:
        return [Bar(r["bar_idx"], r["open"], r["high"], r["low"], r["close"],
                    r["volume"] or 0.0)
                for r in self.rows(
                    "SELECT * FROM bars WHERE session=? AND symbol=? "
                    "AND source='feed' ORDER BY bar_idx", (self.session, symbol))]

    # ------------------------------------------- 0. is this usable evidence?
    def integrity(self, symbol: str) -> list[str]:
        """Everything that makes this session describe something else."""
        flags = []

        starts = self.rows("SELECT COUNT(*) n FROM events WHERE session=? "
                           "AND message LIKE 'pre-open%'", (self.session,))[0]["n"]
        if starts > 1:
            flags.append(f"engine started {starts} times — a mid-session restart "
                         f"re-anchors on the session high and re-enters a market "
                         f"that has already moved")

        manual = [f for f in self.fills(symbol) if not (f["order_ref"] or "")]
        if manual:
            qty = sum(f["qty"] for f in manual)
            flags.append(f"{len(manual)} hand-placed execution(s) totalling "
                         f"{qty:.0f} shares — not the engine's trades")

        bars = self.bars(symbol)
        if not bars:
            flags.append("no bars recorded — nothing to compare against")
        else:
            if bars[0].idx > 0:
                flags.append(f"first bar seen was idx {bars[0].idx} "
                             f"({_bar_time(bars[0].idx)}), not 09:30 — the anchor "
                             f"is built from a partial session")
            missing = [i for i in range(bars[0].idx, bars[-1].idx)
                       if i not in {b.idx for b in bars}]
            if missing:
                flags.append(f"{len(missing)} missing bar(s) between "
                             f"{bars[0].idx} and {bars[-1].idx} — session_high "
                             f"may be understated")

        for r in self.rows("SELECT message FROM events WHERE session=? AND "
                           "level='critical' ORDER BY ts", (self.session,)):
            if symbol in r["message"] or "flat" in r["message"].lower():
                flags.append(f"critical: {r['message'][:120]}")
        return flags

    # --------------------------------------------- 1. live vs the backtest
    def live_trades(self, symbol: str) -> tuple[list[Trade], float]:
        """Round trips walked out of the executions themselves.

        Deliberately not read from the engine's own trade list: the whole point
        is to check the engine, and a report that trusts its bookkeeping cannot
        do that. Position is tracked across executions, so a fill split into
        fourteen pieces is one trade — which is what IBKR actually does.
        """
        trades, pos = [], 0.0
        in_qty = in_notional = out_qty = out_notional = 0.0
        entry_ts = ""
        outcome = "?"
        n_in = n_out = 0
        unattributed = 0.0

        for f in self.fills(symbol):
            ref, qty, px = f["order_ref"] or "", f["qty"], f["price"]
            role = (f["role"] or "").upper()[:1]
            if not ref:
                unattributed += qty
                continue                       # hand-placed; counted, not traded
            signed = qty if f["side"] == "BOT" else -qty
            if pos == 0 and signed > 0:        # a new round trip opens
                in_qty = in_notional = out_qty = out_notional = 0.0
                n_in = n_out = 0
                entry_ts = f["ts"]
            if signed > 0:
                in_qty += qty
                in_notional += qty * px
                n_in += 1
            else:
                out_qty += qty
                out_notional += qty * px
                n_out += 1
                outcome = ROLE_NAME.get(role, role or "?")
            pos += signed
            if abs(pos) < 1e-9 and in_qty > 0 and out_qty > 0:
                trades.append(Trade(
                    symbol=symbol, qty=in_qty,
                    entry_px=in_notional / in_qty, exit_px=out_notional / out_qty,
                    outcome=outcome, entry_ts=entry_ts, exit_ts=f["ts"],
                    entry_execs=n_in, exit_execs=n_out))
                in_qty = out_qty = 0.0
        return trades, unattributed

    def shadow_trades(self, symbol: str, capital: float) -> list[Trade]:
        """What the backtest books on the *same bars the engine actually saw*."""
        bars = self.bars(symbol)
        if not bars or capital <= 0:
            return []
        # The *live* shape deliberately, not `backtest_config`'s. Comparing
        # against a config that ignores the cent grid and buys fractional shares
        # would fold Phase 1's already-measured S5/S7 differences into the diff
        # and hide the thing this report exists to isolate: fill quality.
        cfg = SleeveConfig(symbol=symbol, sleeve_capital=capital)
        sm = SleeveStateMachine(cfg)
        sm.begin_session(self.session, atr5=99.0, is_half_day=False,
                         late_open=False)          # the gate already said yes
        sm.apply_morning_filter(or30=0.0, thr80=99.0, pos10=1.0)
        sm.drain_intents()
        replay_session(bars, sm)
        return [Trade(symbol=symbol, qty=t.qty, entry_px=t.entry_px,
                      exit_px=t.exit_px, outcome=t.outcome,
                      entry_ts=f"bar {t.entry_bar}", exit_ts=f"bar {t.exit_bar}")
                for t in sm.trades]

    # ------------------------------------------------- 2 & 3. the two tests
    def fills_without_the_quote(self, symbol: str) -> list[sqlite3.Row]:
        """§1/§12.3 Q1 — a buy that filled while the ask was still above it.

        If the simulator does this, paper cannot test assumption A1 and the §8
        baselines stay unfalsified however long the run goes on.
        """
        out = []
        for f in self.fills(symbol):
            if (f["role"] or "").upper()[:1] != "E":
                continue
            ask, price = f["ask"] or 0.0, f["price"]
            if ask > 0 and price < ask - 1e-9:
                out.append(f)                 # bought below the prevailing ask
        return out

    def same_bar_reentries(self, symbol: str) -> list[tuple]:
        """§12.3 Q2 — re-entry price against the price just sold (S10/S11).

        S11 predicts the achieved re-entry is systematically *worse* than the
        backtest's, which prices it at the exit bar's open — a level that traded
        before the exit did.
        """
        out = []
        last_exit_px = last_exit_ts = None
        pending_ref = None
        for f in self.fills(symbol):
            ref = f["order_ref"] or ""
            role = (f["role"] or "").upper()[:1]
            if not ref:
                continue                       # hand-placed; not a re-entry
            if role in ("T", "S", "F"):
                last_exit_px, last_exit_ts = f["price"], f["ts"]
                pending_ref = None
            elif role == "E" and last_exit_px and ref != pending_ref:
                # The *first* execution of the entry that follows an exit. Later
                # slices of the same order are the same re-entry, not new ones.
                pending_ref = ref
                gap_bp = (f["price"] - last_exit_px) / last_exit_px * 1e4
                out.append((last_exit_px, f["price"], gap_bp,
                            _seconds_between(last_exit_ts, f["ts"])))
        return out

    # ------------------------------------------------------------- render
    def render(self) -> str:
        L = [f"{'=' * 74}", f"SESSION REPORT  {self.session}", "=" * 74]
        syms = self.symbols()
        if not syms:
            return "\n".join(L + [f"  no session {self.session} in {self.db}"])

        for symbol in syms:
            d = self.daily(symbol)
            cap = (d["sleeve_capital"] or 0.0) if d else 0.0
            L.append(f"\n--- {symbol} " + "-" * (68 - len(symbol)))

            if d:
                gate = "ON" if d["gate_ok"] else f"OFF ({d['gate_reason']})"
                filt = ("ON" if d["filter_ok"] else f"STAND DOWN ({d['filter_reason']})"
                        ) if d["filter_ok"] is not None else "not evaluated"
                L.append(f"  gate {gate}   atr5={_n(d['atr5'])}")
                L.append(f"  filter {filt}   or30={_n(d['or30'])} "
                         f"thr80={_n(d['thr80'])} pos10={_n(d['pos10'])}")
                L.append(f"  sleeve capital ${cap:,.0f}")

            flags = self.integrity(symbol)
            if flags:
                L.append("\n  [!] EVIDENCE QUALITY")
                for f in flags:
                    L.append(f"      ! {f}")
                L.append("      -> treat the numbers below as descriptive of this "
                         "session, not of the strategy")

            live, manual = self.live_trades(symbol)
            L.append(f"\n  LIVE  {len(live)} round trip(s)"
                     + (f", plus {manual:.0f} shares hand-placed" if manual else ""))
            live_bp = 0.0
            for t in live:
                live_bp += t.bp_on(cap)
                L.append(f"    {t.outcome:<8} {t.qty:>6.0f} @ {t.entry_px:.4f} "
                         f"-> {t.exit_px:.4f}  {t.bp_on(cap):+8.1f} bp"
                         f"   ({t.entry_execs}+{t.exit_execs} execs)")
            L.append(f"    {'total':<8} {'':>6} {'':>21}  {live_bp:+8.1f} bp")

            shadow = self.shadow_trades(symbol, cap)
            shadow_bp = sum(t.bp_on(cap) for t in shadow)
            L.append(f"\n  SHADOW  {len(shadow)} round trip(s) on the same bars")
            for t in shadow:
                L.append(f"    {t.outcome:<8} {t.qty:>6.0f} @ {t.entry_px:.4f} "
                         f"-> {t.exit_px:.4f}  {t.bp_on(cap):+8.1f} bp")
            L.append(f"    {'total':<8} {'':>6} {'':>21}  {shadow_bp:+8.1f} bp")
            L.append(f"\n  DIFFERENCE (live - shadow): {live_bp - shadow_bp:+.1f} bp")
            if len(live) != len(shadow):
                L.append(f"    trade counts differ ({len(live)} vs {len(shadow)}) — "
                         f"compare the trades, not the totals")

            unq = self.fills_without_the_quote(symbol)
            L.append(f"\n  §12.3 Q1  entry fills below the prevailing ask: "
                     f"{len(unq)}")
            if unq:
                L.append("      IBKR's simulator filled where the market had not "
                         "traded — paper cannot test A1")
                for f in unq[:3]:
                    L.append(f"      {f['price']:.4f} vs ask {f['ask']:.4f}")

            re = self.same_bar_reentries(symbol)
            L.append(f"  §12.3 Q2  re-entries after an exit: {len(re)}")
            for sold, bought, gap, secs in re[:5]:
                verdict = "worse" if gap > 0 else "better"
                L.append(f"      sold {sold:.4f} -> bought {bought:.4f} "
                         f"({gap:+.1f} bp, {verdict}, {secs:.0f}s later)")
            if re:
                avg = sum(g for _, _, g, _ in re) / len(re)
                L.append(f"      mean {avg:+.1f} bp — S11 predicts positive "
                         f"(the backtest's re-entry is unachievable)")

        L.append("\n" + "=" * 74)
        return "\n".join(L)


def _n(x, nd=2):
    return "—" if x is None else f"{x:.{nd}f}"


def _bar_time(idx: int) -> str:
    m = 9 * 60 + 30 + 5 * idx
    return f"{m // 60:02d}:{m % 60:02d}"


def _seconds_between(a: str, b: str) -> float:
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except Exception:                                          # noqa: BLE001
        return float("nan")


# ------------------------------------------------------------------- weekly
def weekly(db: str, sessions: list[str]) -> str:
    """§8's monitoring table against what actually happened."""
    L = ["=" * 74, f"WEEKLY REPORT  {sessions[0]}..{sessions[-1]}"
         f"  ({len(sessions)} session(s))", "=" * 74]
    for symbol, base in BASELINES.items():
        on_days = trades = targets = stops = flattens = 0
        bp = 0.0
        dirty = 0
        for s in sessions:
            r = SessionReport(db, s)
            d = r.daily(symbol)
            if not d:
                continue
            if d["filter_ok"]:
                on_days += 1
            if r.integrity(symbol):
                dirty += 1
            cap = d["sleeve_capital"] or 0.0
            live, _ = r.live_trades(symbol)
            trades += len(live)
            for t in live:
                bp += t.bp_on(cap)
                targets += t.outcome == "target"
                stops += t.outcome == "stop"
                flattens += t.outcome == "flatten"
        L.append(f"\n--- {symbol} " + "-" * (68 - len(symbol)))
        if not on_days:
            L.append("  no ON days")
            continue
        exits = max(targets + stops + flattens, 1)
        L.append(f"  {'metric':<24}{'measured':>12}{'§8 baseline':>14}"
                 f"{'S11 plan':>11}")
        L.append(f"  {'ON days':<24}{on_days:>12}{'—':>14}{'—':>11}")
        L.append(f"  {'fills / ON day':<24}{trades/on_days:>12.2f}"
                 f"{base['fills_per_on_day']:>14.2f}{'—':>11}")
        L.append(f"  {'target %':<24}{targets/exits*100:>12.1f}"
                 f"{base['target_pct']:>14.1f}{'—':>11}")
        L.append(f"  {'stop %':<24}{stops/exits*100:>12.1f}"
                 f"{base['stop_pct']:>14.1f}{'—':>11}")
        L.append(f"  {'15:55 flatten %':<24}{flattens/exits*100:>12.1f}"
                 f"{base['flatten_pct']:>14.1f}{'—':>11}")
        L.append(f"  {'bp / ON day':<24}{bp/on_days:>12.1f}"
                 f"{base['net_bp']:>14.1f}{base['plan_bp']:>11.1f}")
        if dirty:
            L.append(f"\n  [!] {dirty} of {on_days} ON day(s) carry evidence-quality "
                     f"flags.")
            L.append(f"      §8 says investigate STRUCTURAL breaks, not noise, and "
                     f"a single week proves nothing.")
            L.append(f"      With {on_days} ON day(s) against the ~10-11 four weeks "
                     f"yields, this is not yet a measurement.")
    L.append("\n" + "=" * 74)
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="shadow-parity report (Stage 6)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--session", default=None, help="YYYYMMDD; default today")
    ap.add_argument("--weekly", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    db = args.db or EngineConfig.load(args.config).db_path
    if not os.path.exists(db):
        print(f"no store at {db}")
        return 1

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    sessions = [r[0] for r in conn.execute(
        "SELECT DISTINCT session FROM daily ORDER BY session")]
    conn.close()
    if not sessions:
        print(f"no sessions recorded in {db}")
        return 1

    if args.list:
        print(f"{len(sessions)} session(s) in {db}:")
        for s in sessions:
            print(f"  {s}")
        return 0
    if args.weekly:
        print(weekly(db, sessions))
        return 0

    session = args.session or datetime.now().strftime("%Y%m%d")
    if session not in sessions:
        print(f"no session {session}; have {', '.join(sessions)}")
        return 1
    print(SessionReport(db, session).render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
