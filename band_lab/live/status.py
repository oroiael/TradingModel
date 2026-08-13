"""
Stage 7 (part) — the phone-sized status snapshot.

`PROJECT_STATUS.md` §3 has carried "**No alerting** — `run.py` prints to the
console and writes SQLite. There is no push, email or desktop notification of
any kind, despite three documents describing them" since the paper run started.
This is the first piece of that gap: not alerting on a condition, but *being
able to see the session at all* from somewhere other than the console.

The operational problem it solves is specific. IBKR permits one login per user,
so opening TWS or the IBKR mobile app to check on the day **disconnects the
engine's session**. Checking on the run breaks the run. Everything here reads
the engine's own database instead, so looking costs the session nothing.

**Read-only, no broker, cannot steer anything.** Same discipline as
`report.py`, for the same reason: `store.py` makes the broker the only source
of truth, and a monitoring tool that could feed back into a decision would
break that. This module imports no `ib_async`, opens the store without writing
to it, and reconstructs trades by importing `report.py` rather than by
re-deriving them — defect 8 (one order is not one fill) is a mistake worth
making in exactly one place.

    python3 band_lab/live/status.py                    # print it
    python3 band_lab/live/status.py --watch 300        # reprint every 5 min
    python3 band_lab/live/status.py --publish          # to a private gist
    python3 band_lab/live/status.py --publish --watch 300

## Publishing, and the privacy decision it forces

`RUNBOOK.md` and `PROJECT_STATUS.md` §5F both say alerting must not go through
public `ntfy.sh`, "it would carry positions and P&L in clear text through a
third party". That constraint is respected but not dissolved: a **secret gist**
is authenticated and unlisted rather than public, and the repository's own
`.gitignore` still keeps `live/out/` out of git entirely. It is a third party
either way. `--no-dollars` publishes states, counts and basis points without
absolute account size, which is the version worth defaulting to on a phone.

Needs `BANDLAB_GITHUB_TOKEN` with the `gist` scope. The gist id is created once
and remembered in `live/out/status_gist.json` so the URL is stable — bookmark it
once. Nothing here reads the repository or can write to it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
_BAND_LAB = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_BAND_LAB, "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from report import live_trades, session_label, sessions_in, symbols_in  # noqa: E402
from store import Store                                                # noqa: E402
from spec_constants import HARD_FLAT_BY, TIMEZONE                       # noqa: E402

NY = ZoneInfo(TIMEZONE)

#: §6.2's rule, restated for a human rather than for the watchdog: the engine
#: writes a heartbeat every poll (30s default), so two minutes without one
#: during RTH means something is wrong. `watchdog.py` acts on it; this only
#: says so, because two processes acting on one condition is how you get two
#: flattens.
STALE_SECONDS = 120.0

GIST_API = "https://api.github.com/gists"
GIST_FILENAME = "band_lab_status.md"


# ------------------------------------------------------------------ helpers
def _fmt(x: Optional[float], nd: int = 2) -> str:
    return "—" if x is None or x != x else f"{x:,.{nd}f}"


def _age(ts: str, now: datetime) -> Optional[float]:
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return None
    return (now - dt).total_seconds()


def _et(ts: str) -> str:
    """`HH:MM:SS` in ET for a stored timestamp.

    `store.py` stamps every row in UTC, and slicing the ISO string renders 22:49
    for a warning raised at 18:49 ET. On a page whose whole purpose is telling
    you *when* something happened during the session, that is not cosmetic —
    §4.6 cost a session to a naive local time, and this is the same mistake in
    the read direction.
    """
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return "??:??:??"
    return f"{dt.astimezone(NY):%H:%M:%S}" if dt.tzinfo else f"{dt:%H:%M:%S}"


def _mins(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 90:
        return f"{seconds:.0f}s ago"
    return f"{seconds / 60:.0f}m ago"


def read_heartbeat(path: str) -> Optional[dict]:
    """The engine's proof of life, or None if it has never written one.

    Deliberately not fatal. A snapshot that says "no heartbeat" is useful; one
    that raises because the engine has not started yet is not.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ snapshot
def render(store: Store, session: Optional[str] = None,
           heartbeat_file: Optional[str] = None,
           now: Optional[datetime] = None,
           dollars: bool = True) -> str:
    """The whole snapshot, as Markdown. Pure — no I/O beyond the store."""
    now = now or datetime.now(NY)
    all_sessions = sessions_in(store)
    session = session or (all_sessions[-1] if all_sessions else None)
    hb = read_heartbeat(heartbeat_file) if heartbeat_file else None

    out: list[str] = []
    out.append(f"# {session_label(session) if session else 'no session yet'}")
    out.append(f"`{now:%H:%M:%S}` ET · updated {now:%Y-%m-%d %H:%M} ET")
    out.append("")

    # --- is the engine alive? The first question, so it goes first.
    if hb is None:
        out.append("## ⚠️ ENGINE — no heartbeat file")
        out.append("The engine has not started, or is writing elsewhere. "
                   "`watchdog.py` is what acts on this; this only reports it.")
    else:
        age = _age(hb.get("ts", ""), now)
        stale = age is None or age > STALE_SECONDS
        mark = "⚠️ STALE" if stale else "✅ alive"
        out.append(f"## ENGINE — {mark}")
        out.append(f"- heartbeat {_mins(age)} · pid {hb.get('pid', '?')}")
        if not hb.get("transmit", False):
            out.append("- **transmit OFF** — this is a rehearsal, no orders "
                       "reach the market")
        if stale:
            out.append(f"- nothing for over {STALE_SECONDS / 60:.0f} minutes. "
                       f"If it is a trading day and the account is not flat, "
                       f"check the console.")
    out.append("")

    if not session:
        out.append("_No session in the database yet._")
        return "\n".join(out)

    # --- per sleeve
    day_bp = 0.0
    day_dollars = 0.0
    open_positions = []
    for sym in symbols_in(store, session):
        rows = store.rows("SELECT * FROM daily WHERE session=? AND symbol=?",
                          (session, sym))
        row = rows[0] if rows else None
        trades = live_trades(store, sym, session)
        closed = [t for t in trades if t.outcome != "open"]
        held = [t for t in trades if t.outcome == "open"]
        cap = None
        if row is not None and row["sleeve_capital"] is not None:
            cap = float(row["sleeve_capital"])

        out.append(f"## {sym}")
        if row is None:
            out.append("- no decision recorded yet today")
            out.append("")
            continue

        gate = "ON" if row["gate_ok"] else "OFF"
        filt = "ON" if row["filter_ok"] else "OFF"
        if not row["gate_ok"]:
            out.append(f"- **not trading today** — gate {gate} "
                       f"({row['gate_reason'] or '?'})")
        elif not row["filter_ok"]:
            out.append(f"- **stood down** — filter {filt} "
                       f"({row['filter_reason'] or '?'})")
        else:
            out.append(f"- gate {gate} · filter {filt} · trading")

        cnt = store.rows("SELECT * FROM counters WHERE session=? AND symbol=?",
                         (session, sym))
        if cnt:
            out.append(f"- state **{cnt[0]['state']}** · "
                       f"{cnt[0]['fills']} fill(s) · "
                       f"{cnt[0]['stop_outs']} stop-out(s)")

        # Realised, and separately what is still open. Marking an open position
        # would need a live quote, and this module has no broker — so it says
        # what it holds and does not pretend to price it.
        bp = 1e4 * sum(t.ret for t in closed)
        day_bp += bp
        cash = sum(t.pnl for t in closed)
        day_dollars += cash
        money = f" · ${cash:+,.0f}" if (dollars and closed) else ""
        out.append(f"- realised **{bp:+,.1f} bp**{money} over "
                   f"{len(closed)} round trip(s)")

        for i, t in enumerate(closed, 1):
            out.append(f"  {i}. {t.entry_px:,.2f} → {t.exit_px:,.2f} "
                       f"**{t.outcome}** {t.ret * 1e4:+,.1f} bp")
        for t in held:
            open_positions.append(sym)
            qty = f"{t.qty:,.0f} sh " if dollars else ""
            out.append(f"  ⚠️ **HOLDING** {qty}from {t.entry_px:,.2f} "
                       f"(bar {t.entry_bar}) — not yet closed")
        if cap is not None and dollars:
            out.append(f"- sleeve capital {cap:,.0f}")
        out.append("")

    money = f" · **${day_dollars:+,.0f}**" if dollars else ""
    out.append(f"## DAY — {day_bp:+,.1f} bp{money} realised")
    out.append("")

    # --- anything that needs a human
    bad = store.rows(
        "SELECT * FROM events WHERE session=? AND level IN ('warn','error',"
        "'critical') ORDER BY ts DESC LIMIT 12", (session,))
    crit = [e for e in bad if e["level"] == "critical"]
    if crit:
        out.append(f"## 🔴 {len(crit)} CRITICAL")
        for e in crit[:6]:
            out.append(f"- `{_et(e['ts'])}` {e['message']}")
        out.append("")
    rest = [e for e in bad if e["level"] != "critical"]
    if rest:
        out.append(f"## warnings and errors ({len(rest)})")
        for e in rest[:8]:
            out.append(f"- `{_et(e['ts'])}` [{e['level']}] {e['message']}")
        out.append("")

    # --- the one thing that matters after the close
    hh, mm = (int(v) for v in HARD_FLAT_BY.split(":"))
    if (now.hour, now.minute) >= (hh, mm):
        if open_positions:
            out.append(f"## 🔴 NOT FLAT past {HARD_FLAT_BY} — "
                       f"{', '.join(open_positions)}")
            out.append("§1's first design priority is never holding overnight. "
                       "Close by hand.")
        else:
            out.append(f"## ✅ flat past {HARD_FLAT_BY}")
    return "\n".join(out)


# ----------------------------------------------------------------- publish
def _api(url: str, token: str, payload: Optional[dict] = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "band_lab-status",
                 "Content-Type": "application/json"},
        method="PATCH" if payload is not None and "/gists/" in url else
               ("POST" if payload is not None else "GET"))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def publish(text: str, token: str, state_path: str,
            description: str = "band_lab live status") -> str:
    """Create or update the secret gist, and return its URL.

    The id is remembered so the URL stays the same across restarts — a monitor
    you have to re-find is a monitor you stop checking.
    """
    gist_id = None
    try:
        with open(state_path, encoding="utf-8") as fh:
            gist_id = json.load(fh).get("gist_id")
    except (OSError, ValueError):
        pass

    body = {"description": description,
            "files": {GIST_FILENAME: {"content": text}}}
    if gist_id:
        try:
            return _api(f"{GIST_API}/{gist_id}", token, body)["html_url"]
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            gist_id = None          # deleted upstream; fall through and remake

    body["public"] = False
    res = _api(GIST_API, token, body)
    os.makedirs(os.path.dirname(os.path.abspath(state_path)), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump({"gist_id": res["id"], "html_url": res["html_url"]}, fh)
    return res["html_url"]


# ---------------------------------------------------------------------- CLI
def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--db", default=os.path.join(_HERE, "out", "live.db"))
    p.add_argument("--heartbeat", default=os.path.join(_HERE, "out",
                                                       "heartbeat.json"))
    p.add_argument("--session", help="YYYYMMDD (default: latest in the db)")
    p.add_argument("--publish", action="store_true",
                   help="create/update a secret gist (BANDLAB_GITHUB_TOKEN)")
    p.add_argument("--no-dollars", action="store_true",
                   help="omit absolute sizes and cash — bp and states only")
    p.add_argument("--watch", type=float, metavar="SECONDS",
                   help="re-render on an interval instead of once")
    p.add_argument("--state", default=os.path.join(_HERE, "out",
                                                   "status_gist.json"))
    a = p.parse_args(argv)

    if not os.path.exists(a.db):
        print(f"no database at {a.db} — the engine writes it at "
              f"live/out/live.db; pass --db if yours is elsewhere",
              file=sys.stderr)
        return 2
    token = os.environ.get("BANDLAB_GITHUB_TOKEN", "").strip()
    if a.publish and not token:
        print("--publish needs BANDLAB_GITHUB_TOKEN (scope: gist)",
              file=sys.stderr)
        return 2

    while True:
        store = Store(a.db)
        try:
            text = render(store, a.session, a.heartbeat,
                          dollars=not a.no_dollars)
        finally:
            store.close()
        print(text)
        if a.publish:
            try:
                url = publish(text, token, a.state)
                print(f"\n-> {url}", file=sys.stderr)
            except Exception as exc:                        # noqa: BLE001
                # Never fatal, and never retried into a tight loop: a monitor
                # that dies when GitHub has a bad minute is worse than one that
                # skips an update, and this process must never be a reason to
                # go look at the trading machine.
                print(f"\npublish failed ({exc!r}) — snapshot above is still "
                      f"current", file=sys.stderr)
        if not a.watch:
            return 0
        time.sleep(max(30.0, a.watch))


if __name__ == "__main__":
    raise SystemExit(main())
