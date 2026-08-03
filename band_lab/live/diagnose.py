"""
What is IBKR actually giving us? — a read-only pre-flight.

    python band_lab/live/diagnose.py

`run.py` is deliberately quiet: it prints decisions, not plumbing. That is right
for a trading session and wrong for the first connection to a new broker, where
a silent feed and a working feed look identical from the outside.

This connects read-only, performs each call the engine performs, and prints what
came back — including the **raw** bar timestamps, because `Bar.idx` is minutes
since 09:30 ET and a timezone mismatch there produces indices that match neither
the 10:00 filter (bar 5) nor the 11:00 activation (bar 18). The engine would then
run a whole session, consume every bar, and decide nothing — with no error.

It places no orders and cancels every subscription it opens.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "phase1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from broker import (                                          # noqa: E402
    IBBroker, MarketClosedError, NotLiveDataError, bar_time_et,
)
from config import EngineConfig                               # noqa: E402

NY = ZoneInfo("America/New_York")
OK, BAD, WARN = "  ok  ", " FAIL ", " warn "


class Diagnosis:
    def __init__(self, cfg: EngineConfig) -> None:
        self.cfg = cfg
        self.errors: list[tuple] = []
        self.step = "connect"
        self.verdicts: list[tuple] = []
        self.broker = IBBroker(host=cfg.host, port=cfg.port,
                               client_id=cfg.client_id + 50,   # never clash with a running engine
                               exchange=cfg.exchange, primary=cfg.primary,
                               readonly=True, on_event=lambda lvl, m: None)

    def say(self, tag: str, what: str, detail: str = "") -> None:
        print(f"[{tag}] {what}" + (f"\n         {detail}" if detail else ""))
        self.verdicts.append((tag, what))

    def _err(self, reqId, code, msg, contract=None) -> None:
        if code in (2104, 2106, 2107, 2158, 2119):     # "farm is OK" chatter
            return
        sym = getattr(contract, "symbol", "") or ""
        self.errors.append((self.step, code, sym, msg))
        # `step` is best-effort: IBKR errors arrive asynchronously, so one
        # raised by the previous step can surface while the next is running.
        where = self.step if sym and sym in self.step else f"{self.step} {sym}".strip()
        print(f"         · IBKR {code} during {where}: {msg[:110]}")

    # ------------------------------------------------------------------ run
    def run(self) -> int:
        print("=" * 74)
        print(f"IBKR PRE-FLIGHT  {datetime.now(NY):%Y-%m-%d %H:%M:%S %Z}  "
              f"{self.cfg.host}:{self.cfg.port}")
        print("=" * 74)

        try:
            self.broker.connect()
            self.broker._ib.errorEvent += self._err
        except Exception as exc:                              # noqa: BLE001
            self.say(BAD, f"cannot connect to {self.cfg.host}:{self.cfg.port}", repr(exc))
            print("\n  TWS running? API enabled? port 7497 for paper? "
                  "trusted IP 127.0.0.1?")
            return 1
        self.say(OK, f"connected on port {self.cfg.port}"
                     f" — {'PAPER' if self.cfg.port == 7497 else 'CHECK THIS PORT'}")

        self.account()
        for symbol in self.cfg.symbols:
            print(f"\n--- {symbol} " + "-" * (68 - len(symbol)))
            self.contract(symbol)
            self.hours(symbol)
            self.bars(symbol)
            self.market_data(symbol)

        return self.summary()

    # --------------------------------------------------------------- steps
    def account(self) -> None:
        self.step = "account"
        try:
            equity = self.broker.net_liquidation()
        except Exception as exc:                              # noqa: BLE001
            return self.say(BAD, "NetLiquidation unavailable", repr(exc))
        basis = min(equity, self.cfg.capital_cap)
        sleeve = self.cfg.w * basis
        self.say(OK if sleeve > 1000 else WARN,
                 f"NetLiquidation ${equity:,.0f} -> sleeve_capital ${sleeve:,.0f}",
                 "" if sleeve > 1000 else "too small to buy meaningful size")

    def contract(self, symbol: str) -> None:
        self.step = f"qualify {symbol}"
        try:
            c = self.broker.contract(symbol)
            self.say(OK, f"{symbol} qualified: conId={c.conId} "
                         f"{c.exchange}/{c.primaryExchange}")
        except Exception as exc:                              # noqa: BLE001
            self.say(BAD, f"{symbol} will not qualify", repr(exc))

    def hours(self, symbol: str) -> None:
        self.step = f"hours {symbol}"
        try:
            sh = self.broker.session_hours(symbol, datetime.now(NY))
        except MarketClosedError as exc:
            return self.say(WARN, f"{symbol} market closed today", str(exc))
        except Exception as exc:                              # noqa: BLE001
            return self.say(BAD, f"{symbol} session hours failed", repr(exc))
        self.say(OK, f"{symbol} session {sh.open:%H:%M}-{sh.close:%H:%M} "
                     f"({sh.minutes:.0f} min)"
                     + (" HALF DAY -> gate OFF" if sh.is_half_day else ""))

    def bars(self, symbol: str) -> None:
        """The important one. Raw timestamps first, then what the engine sees."""
        self.step = f"historical {symbol}"
        try:
            raw = self.broker._ib.reqHistoricalData(
                self.broker.contract(symbol), endDateTime="", durationStr="1 D",
                barSizeSetting="5 mins", whatToShow="TRADES", useRTH=True,
                formatDate=1, keepUpToDate=False)
        except Exception as exc:                              # noqa: BLE001
            return self.say(BAD, f"{symbol} historical request raised", repr(exc))

        if not raw:
            return self.say(BAD, f"{symbol} historical returned NO BARS",
                            "the engine sees an empty session and decides nothing")

        b0 = raw[0].date
        kind = ("tz-aware " + str(getattr(b0, "tzinfo", None))) if isinstance(
            b0, datetime) and b0.tzinfo else (
            "naive datetime" if isinstance(b0, datetime) else f"{type(b0).__name__}")
        print(f"         raw first={b0!r}  ({kind})")
        print(f"         raw last ={raw[-1].date!r}")

        et = [bar_time_et(b.date) for b in raw]
        idx = [(d.hour * 60 + d.minute - 570) // 5 for d in et]
        print(f"         as ET    first={et[0]:%Y-%m-%d %H:%M}  last={et[-1]:%H:%M}")
        print(f"         indices  first={idx[0]}  last={idx[-1]}  count={len(idx)}")

        if et[0].hour == 9 and et[0].minute == 30 and idx[0] == 0:
            self.say(OK, f"{symbol} bar 0 is the 09:30 bar — indices are aligned")
        else:
            self.say(BAD, f"{symbol} bar 0 is idx {idx[0]} at {et[0]:%H:%M} ET",
                     "index 0 must be 09:30. The 10:00 filter (bar 5) and the "
                     "11:00 arming (bar 18) cannot fire on a shifted grid.")

        dates = sorted({d.date() for d in et})
        if len(dates) > 1:
            self.say(WARN, f"{symbol} window spans {len(dates)} sessions: "
                           f"{dates[0]}..{dates[-1]}",
                     "historical_bars filters to one date; this is why it must")

        seen = self.broker.historical_bars(symbol, datetime.now(NY), "1 D", "5 mins")
        if seen:
            self.say(OK, f"{symbol} engine would consume {len(seen)} bars "
                         f"(idx {seen[0].idx}..{seen[-1].idx})")
        else:
            self.say(BAD, f"{symbol} engine would consume ZERO bars",
                     f"{len(raw)} arrived but none matched today "
                     f"({datetime.now(NY).date()}) after the date filter")

    def market_data(self, symbol: str) -> None:
        self.step = f"market data {symbol}"
        try:
            self.broker.assert_live_data(symbol)
        except NotLiveDataError as exc:
            return self.say(BAD, f"{symbol} NOT on live data", str(exc))
        except Exception as exc:                              # noqa: BLE001
            return self.say(BAD, f"{symbol} live-data probe raised", repr(exc))
        self.say(OK, f"{symbol} live market data confirmed")

    # ------------------------------------------------------------- verdict
    def summary(self) -> int:
        print("\n" + "=" * 74)
        bad = [w for t, w in self.verdicts if t == BAD]
        warn = [w for t, w in self.verdicts if t == WARN]
        for w in bad:
            print(f"[{BAD}] {w}")
        for w in warn:
            print(f"[{WARN}] {w}")
        if self.errors:
            codes = sorted({c for _, c, _, _ in self.errors})
            print(f"\nIBKR error codes seen: {codes}")
            for code, hint in (
                (10089, "no live L1 entitlement for API — subscribe in Client "
                        "Portal and share to the paper account"),
                (354, "market data not subscribed"),
                (162, "another IBKR session holds the market-data connection — "
                      "log out of Client Portal / mobile / any second TWS"),
                (200, "contract not qualified — check symbol/exchange"),
            ):
                if code in codes:
                    print(f"  {code}: {hint}")
        print("=" * 74)
        if bad:
            print("VERDICT: NOT READY — fix the FAIL lines above.")
            return 1
        print("VERDICT: READY" + (" (with warnings)" if warn else ""))
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="IBKR pre-flight for the live engine")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = EngineConfig.load(args.config)
    d = Diagnosis(cfg)
    try:
        return d.run()
    finally:
        try:
            d.broker.disconnect()
        except Exception:                                     # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
