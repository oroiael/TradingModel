"""
§6.1 — does a broker-side `STP` survive the engine dying?

**The last safety-critical unknown, and the cheapest one to settle.** It has
been open since Stage 2. `PHASE2_PLAN.md` §6 lists it, `PROJECT_STATUS.md` §3
gates unattended operation on it, and `RUNBOOK.md` §8.1 says an unattended
crash mid-position "has no proven protection" until it is answered. Nobody has
answered it because the instruction was "kill the engine and look at TWS with
your own eyes", and an eye is not evidence you can put in a commit.

This makes it a recorded observation instead:

    python band_lab/live/verify_stp.py --label before   # bracket on, engine up
    ...kill the engine...
    python band_lab/live/verify_stp.py --label after    # engine down
    python band_lab/live/verify_stp.py --compare

## Why this can be run against a live session at all

It connects as a **separate API client** — `client_id + 60`, the convention
`diagnose.py` already uses at `+50` — which is an API client slot, *not* a
login. That is the whole difference from opening TWS or the IBKR mobile app to
check on the day: those are competing logins and they disconnect the engine
(error 1100, "a competing session"). A second API client does not.

It requests no market data, so it cannot consume a subscription line, and it is
constructed with `dry_run=True` so `IBBroker` refuses to transmit anything even
if a future edit adds a call that tries.

## What it asks TWS, and why that specific call

`refresh_orders()` → `reqAllOpenOrders`, which IBKR's own documentation defines
as "Requests **all current open orders in associated accounts** at the current
moment" (`TWS API/TWS Documentation - Copy Paste from Online.pdf`, p84). That is
the cross-client request. `reqOpenOrders` is the wrong one and would silently
answer "no stop": p86 defines it as "all open orders **placed by this specific
API client** (identified by the API client id)" — and this probe is, by design,
a different client from the one that placed the bracket.

**What the documentation does not say is whether the order survives at all.**
Pages 21, 22, 46, 80 and 93 mention disconnection and none of them addresses
order persistence across a client dying. That is why §6.1 needs an experiment
rather than a citation, and why this file exists.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import EngineConfig                                  # noqa: E402
from spec_constants import TIMEZONE                              # noqa: E402

NY = ZoneInfo(TIMEZONE)

#: Offset from the engine's client id. `diagnose.py` uses +50; this uses +60 so
#: the two can be run at the same moment without colliding with each other.
#: Reusing the engine's own id would be refused by TWS (error 326), which is a
#: safe failure — but a probe that cannot run while the engine is up is a probe
#: that cannot answer this question.
CLIENT_ID_OFFSET = 60

#: Quantity tolerance. Shares are whole, and a fractional residue should not
#: decide whether a position is called protected.
QTY_EPS = 1e-6


# ------------------------------------------------------------------ snapshot
@dataclass
class SleeveProbe:
    """What the broker says about one sleeve, right now."""
    symbol: str
    position: float
    stop_qty: float                     # working SELL STP quantity, remaining
    orders: list = field(default_factory=list)

    @property
    def exposed(self) -> bool:
        return abs(self.position) > QTY_EPS

    @property
    def covered(self) -> bool:
        """Is every share held protected by a resting stop?

        §6.1's guarantee, stated as arithmetic. Sized on `remaining` rather than
        `qty` because a partially filled stop protects only what is left of it,
        and defect 8 was exactly the mistake of trusting an order's nominal size
        over what it actually covers.
        """
        return not self.exposed or self.stop_qty + QTY_EPS >= abs(self.position)


def probe(broker, symbols: Sequence[str]) -> dict[str, SleeveProbe]:
    """Read positions and working orders. **Reads only — places nothing.**

    `refresh_orders()` first, always. Without it this reads whatever this
    client happened to be told at connect, which for a client that placed
    nothing is nothing at all — and "no stop" would be indistinguishable from
    "the stop is gone", which is the entire question.
    """
    broker.refresh_orders()
    out: dict[str, SleeveProbe] = {}
    for sym in symbols:
        working = broker.working_orders(sym)
        stop = sum(w.remaining for w in working
                   if w.order_type == "STP" and w.action == "SELL")
        out[sym] = SleeveProbe(
            symbol=sym, position=float(broker.position(sym)), stop_qty=stop,
            orders=[{"ref": w.order_ref, "id": w.order_id, "type": w.order_type,
                     "action": w.action, "qty": w.qty, "remaining": w.remaining,
                     "aux_px": w.aux_px, "limit_px": w.limit_px,
                     "oca": w.oca_group, "status": w.status} for w in working])
    return out


def snapshot(probes: dict[str, SleeveProbe], label: str,
             now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(NY)
    return {"label": label, "ts": now.isoformat(),
            "sleeves": {s: asdict(p) for s, p in probes.items()}}


# ------------------------------------------------------------------- verdict
def verdict(before: dict, after: dict) -> tuple[str, list[str]]:
    """§6.1, decided. Returns (verdict, lines).

    Three outcomes, and the inconclusive one is not a failure of the test — it
    is the ordinary result of running it on a sleeve that was flat. Reporting
    it as CONFIRMED would be `PROJECT_STATUS.md` §4.7's defect 6 and 7 all over
    again: concluding from an absence of evidence.
    """
    lines: list[str] = []
    exposed_any = False
    lost_any = False
    held_any = False

    for sym, b in before.get("sleeves", {}).items():
        a = after.get("sleeves", {}).get(sym)
        if a is None:
            lines.append(f"  {sym}: not present in the 'after' snapshot")
            continue
        pos_b, pos_a = b["position"], a["position"]
        stp_b, stp_a = b["stop_qty"], a["stop_qty"]

        if abs(pos_b) <= QTY_EPS:
            lines.append(f"  {sym}: flat before the kill — this sleeve says "
                         f"nothing about §6.1")
            continue
        if stp_b + QTY_EPS < abs(pos_b):
            lines.append(f"  {sym}: ⚠️ held {pos_b:,.0f} with only {stp_b:,.0f} "
                         f"stopped BEFORE the kill — that is a §6.1-independent "
                         f"defect (defect 8's signature), fix it before reading "
                         f"anything else here")
            continue

        exposed_any = True
        if abs(pos_a) <= QTY_EPS:
            lines.append(f"  {sym}: position closed between the snapshots "
                         f"({pos_b:,.0f} → {pos_a:,.0f}) — inconclusive, the "
                         f"bracket may simply have filled")
            continue
        if stp_a + QTY_EPS >= abs(pos_a):
            held_any = True
            lines.append(f"  {sym}: ✅ held {pos_a:,.0f}, stop still resting for "
                         f"{stp_a:,.0f} with the engine down")
        else:
            lost_any = True
            lines.append(f"  {sym}: 🔴 held {pos_a:,.0f} and only {stp_a:,.0f} "
                         f"is stopped — {abs(pos_a) - stp_a:,.0f} shares are "
                         f"UNPROTECTED right now")

    if lost_any:
        return "REFUTED", lines
    if held_any and not lost_any:
        return "CONFIRMED", lines
    if not exposed_any:
        return "INCONCLUSIVE", lines
    return "INCONCLUSIVE", lines


def render(before: dict, after: dict) -> str:
    v, lines = verdict(before, after)
    out = ["=" * 78,
           "§6.1 — does a broker-side STP survive the engine dying?",
           "=" * 78,
           f"  before: {before.get('ts', '?')}",
           f"  after:  {after.get('ts', '?')}",
           ""]
    out += lines
    out.append("")
    if v == "CONFIRMED":
        out += [
            "VERDICT: CONFIRMED — the stop is broker-side and outlived the client.",
            "",
            "  One observation, not a proof. Record the date in PHASE2_PLAN.md §6",
            "  and move it out of the open-questions table, exactly as the",
            "  ocaType finding was moved when ibapi/order.py settled it.",
            "  It does NOT license unattended operation on its own: alerting and",
            "  service supervision are still open (PROJECT_STATUS.md §5F).",
        ]
    elif v == "REFUTED":
        out += [
            "VERDICT: 🔴 REFUTED — shares are held with no resting stop.",
            "",
            "  ACT NOW, in this order:",
            "    1. Flatten by hand in TWS. §1's first design priority is never",
            "       holding overnight, and this position has no protection at all.",
            "    2. Do not restart the engine into an unreconciled position until",
            "       you have.",
            "    3. Nothing runs unattended, ever, until this is designed around —",
            "       a crash mid-position is now a known-unprotected state.",
        ]
    else:
        out += [
            "VERDICT: INCONCLUSIVE — nothing was held across the kill.",
            "",
            "  Not a failure. Run it again on a session where a bracket is on:",
            "  the 'before' snapshot must show a position AND a stop covering it,",
            "  or there is nothing for the kill to test.",
        ]
    out.append("=" * 78)
    return "\n".join(out)


# ---------------------------------------------------------------------- CLI
def path_for(label: str, outdir: str) -> str:
    return os.path.join(outdir, f"stp_probe_{label}.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--config", default=None)
    p.add_argument("--label", help="take a snapshot and store it under this name")
    p.add_argument("--compare", action="store_true",
                   help="render the §6.1 verdict from the two snapshots")
    p.add_argument("--before", default="before")
    p.add_argument("--after", default="after")
    p.add_argument("--out", default=os.path.join(_HERE, "out"))
    a = p.parse_args(argv)

    if not a.label and not a.compare:
        p.error("give --label before/after to snapshot, or --compare to judge")

    if a.compare:
        try:
            before = json.load(open(path_for(a.before, a.out), encoding="utf-8"))
            after = json.load(open(path_for(a.after, a.out), encoding="utf-8"))
        except OSError as exc:
            print(f"missing snapshot: {exc}\nTake both first: --label "
                  f"{a.before}, then kill the engine, then --label {a.after}",
                  file=sys.stderr)
            return 2
        print(render(before, after))
        return 0 if verdict(before, after)[0] != "REFUTED" else 1

    from broker import IBBroker           # lazy: tests never need ib_async
    cfg = EngineConfig.load(a.config)
    broker = IBBroker(host=cfg.host, port=cfg.port,
                      client_id=cfg.client_id + CLIENT_ID_OFFSET,
                      dry_run=True,       # structurally cannot transmit
                      account=getattr(cfg, "account", ""),
                      on_event=lambda lvl, msg: print(f"  [{lvl}] {msg}"))
    try:
        broker.connect()
        probes = probe(broker, cfg.symbols)
    finally:
        try:
            broker.disconnect()
        except Exception:                                     # noqa: BLE001
            pass

    snap = snapshot(probes, a.label)
    os.makedirs(a.out, exist_ok=True)
    with open(path_for(a.label, a.out), "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=2)

    print(f"\n  snapshot '{a.label}' — {snap['ts']}")
    for sym, pr in probes.items():
        mark = "✅" if pr.covered else "🔴"
        print(f"  {mark} {sym}: position {pr.position:,.0f}, "
              f"SELL STP covering {pr.stop_qty:,.0f}, "
              f"{len(pr.orders)} working order(s)")
        for o in pr.orders:
            print(f"       {o['action']:<4} {o['type']:<4} {o['remaining']:>7,.0f} "
                  f"@ {o['aux_px'] or o['limit_px']:<9,.2f} {o['status']:<14} "
                  f"{o['ref']}")
    print(f"\n  wrote {path_for(a.label, a.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
