#!/usr/bin/env python3
"""
ACTIVE LAB -- signal-driven, in-and-out option trading on SOXL
==============================================================

Question (user): leaving weekly income generation behind, is there an
ACTIVE, automatable (IBKR) options strategy that combines risk management
with high earnings and handles a wild swing in EITHER direction?

Design principle from everything measured so far in this repo:
    * long-dated SOXL options are systematically UNDERPRICED vs delivered
      volatility (pricing lab S2: -22 to -29 vol pts at 90-180d);
    * every net-short-movement structure tested lost (R1, R3, S6);
    * trend information is real (the R2 call-skip lever).
==> the active strategies tested here are LONG-OPTIONS-ONLY: wild swings
    are the payoff, the maximum loss is the premium held, and a whipsaw
    can never produce a margin call or account blow-up.

Strategy families (all EOD-decided at weekly cadence -- the honest limit
of the daily option data; intraday automation would use the same logic on
live IBKR greeks):

  TREND    hold deep-ITM (75d) 150-DTE CALLS while spot >= its N-day SMA,
           switch to deep-ITM PUTS (at half size -- drift headwind) or to
           cash while below.  Convex trend-following.
  BREAKOUT same vehicle, signal = N-day high/low (Donchian).  Position
           flips only on the opposite breakout.
  STRADDLE buy the cheap back-tenor (60-120d) ATM straddle and RE-STRIKE
           to the new ATM whenever spot moves X% from the strike --
           mechanically realizing the winning leg on every big swing, in
           either direction, with no forecast at all.
  COMBO    trend core + straddle sleeve (directional participation plus
           direction-free swing harvesting).

Execution: 20%-of-spread rule from real quotes, whole strikes preferred,
rolls at <=45 DTE.  No commissions (user instruction).  No sweep -- this
is total-return active mode.  QA: every run reconciles cash flows.

Outputs:
    active_lab_results.csv    all runs, ranked
    active_lab_ledger.csv     weekly ledger of the best run
    qa/active_lab_report.txt
"""

from pathlib import Path

import numpy as np
import pandas as pd

from soxl_options_loader import ROOT
from call_diagonal_backtest import CallMarket

QA_DIR = Path(__file__).resolve().parent / "qa"

EPISODES = {          # the four wild swings in the window
    "crash25": ("2025-02-01", "2025-05-31"),
    "recover25": ("2025-04-07", "2025-08-31"),
    "meltup26": ("2026-01-01", "2026-06-15"),
    "crash26": ("2026-06-15", "2026-12-31"),
}


class ActiveMarket(CallMarket):
    def __init__(self):
        super().__init__()
        self.roll_max = {}
        self.roll_min = {}

    def donchian(self, td, n):
        if n not in self.roll_max:
            self.roll_max[n] = self.daily_close.rolling(n).max().shift(1)
            self.roll_min[n] = self.daily_close.rolling(n).min().shift(1)
        hi, lo = self.roll_max[n], self.roll_min[n]
        idx = hi.index[hi.index <= td]
        if not len(idx):
            return np.nan, np.nan
        return float(hi.loc[idx[-1]]), float(lo.loc[idx[-1]])

    def pick(self, td, right, dte_tgt, delta_tgt=None, strike_tgt=None,
             dte_lo=None, dte_hi=None):
        ch = self.chains[td]
        lo = dte_lo if dte_lo is not None else max(30, dte_tgt - 30)
        hi = dte_hi if dte_hi is not None else dte_tgt + 45
        g = ch[(ch["right"] == right) & ch["liquid"] &
               (ch["dte"] >= lo) & (ch["dte"] <= hi)]
        if g.empty:
            return None
        exp = g.loc[(g["dte"] - dte_tgt).abs().idxmin(), "expiration"]
        g = g[g["expiration"] == exp]
        whole = g[g["strike"] % 1 == 0]
        if len(whole):
            g = whole
        if strike_tgt is not None:
            return g.loc[(g["strike"] - strike_tgt).abs().idxmin()]
        return g.loc[(g["delta"].abs() - delta_tgt).abs().idxmin()]


class Book:
    """Long-options-only weekly book with pluggable policy."""

    def __init__(self, mkt, policy, start=150_000.0):
        self.m, self.policy = mkt, policy
        self.cash = start
        self.start = start
        self.pos = {}          # key -> lot dict
        self.realized = 0.0
        self.rows = []
        self.n_trades = 0

    # --- primitives ---------------------------------------------------
    def mark(self, td, lot):
        q = self.m.quote(td, lot["exp"], lot["strike"], lot["right"])
        if q is not None:
            lot["last_mark"] = float(q["mid"])
        return lot["last_mark"]

    def equity(self, td):
        return self.cash + sum(self.mark(td, p) * 100 * p["n"]
                               for p in self.pos.values())

    def close(self, td, key, force=False):
        lot = self.pos.pop(key, None)
        if lot is None:
            return 0.0
        q = self.m.quote(td, lot["exp"], lot["strike"], lot["right"])
        if q is not None and bool(q["liquid"]):
            px = float(q["sell_px"])
        else:
            px = lot["last_mark"]      # stale-quote fallback, flagged
            self.note(f"{key}:CLOSE_AT_MARK")
        self.cash += px * 100 * lot["n"]
        pnl = (px - lot["entry_px"]) * 100 * lot["n"]
        self.realized += pnl
        self.n_trades += 1
        self.note(f"{key}:SELL {lot['n']}x{lot['right'][0]}"
                  f"K{lot['strike']:g}@{px:.2f} pnl={pnl:,.0f}")
        return pnl

    def open(self, td, key, right, budget, dte_tgt, delta_tgt=None,
             strike_tgt=None):
        row = self.m.pick(td, right, dte_tgt, delta_tgt, strike_tgt)
        if row is None:
            self.note(f"{key}:NO_QUOTE")
            return
        px = float(row["buy_px"])
        n = int(min(budget, self.cash) // (px * 100))
        if n <= 0:
            self.note(f"{key}:NO_BUDGET")
            return
        self.cash -= px * 100 * n
        self.n_trades += 1
        self.pos[key] = {"right": right, "strike": float(row["strike"]),
                         "exp": row["expiration"], "n": n, "entry_px": px,
                         "last_mark": float(row["mid"])}
        self.note(f"{key}:BUY {n}x{right[0]}K{row['strike']:g}@{px:.2f} "
                  f"d={row['delta']:.2f} dte={row['dte']}")

    def note(self, s):
        self.wk["actions"] = (self.wk.get("actions", "") + " | " + s
                              if self.wk.get("actions") else s)

    # --- loop ---------------------------------------------------------
    def run(self):
        weeks = {}
        for d in self.m.dates:
            weeks.setdefault(d.to_period("W-SUN"), []).append(d)
        wl = sorted(weeks)
        for wi, wp in enumerate(wl):
            d0 = weeks[wp][0]
            dl = weeks[wp][-1]
            self.wk = {"week_start": str(d0.date()),
                       "spot": round(self.m.spot(d0), 2)}
            # emergency: any lot inside 10 DTE gets rolled by policy or
            # force-closed here so nothing ever expires in the book
            for key in [k for k, p in self.pos.items()
                        if (p["exp"] - d0).days <= 10]:
                self.close(d0, key)
            self.policy.decide(self, d0)
            if wi == len(wl) - 1:
                for key in list(self.pos):
                    self.close(dl, key, force=True)
            self.wk.update(end_cash=round(self.cash, 2),
                           end_wealth=round(self.equity(dl), 2))
            self.rows.append(self.wk)
        led = pd.DataFrame(self.rows)
        recon_ok = abs(self.start + self.realized - self.cash) < 0.01
        return led, self.stats(led, recon_ok)

    def stats(self, led, recon_ok):
        w = led.set_index(pd.to_datetime(led["week_start"]))["end_wealth"]
        yrs = len(w) / 52
        dd = (w / w.cummax() - 1).min()
        wk = w.pct_change().dropna()
        cagr = ((w.iloc[-1] / self.start) ** (1 / yrs) - 1) * 100 \
            if w.iloc[-1] > 0 else -100
        s = {"policy": self.policy.label, "end_wealth": round(w.iloc[-1], 0),
             "cagr_pct": round(cagr, 1), "max_dd_pct": round(dd * 100, 1),
             "MAR": round(cagr / abs(dd * 100), 2) if dd else np.nan,
             "worst_wk_pct": round(wk.min() * 100, 1),
             "best_wk_pct": round(wk.max() * 100, 1),
             "trades": self.n_trades,
             "qa_recon": "PASS" if recon_ok else "FAIL"}
        for name, (a, b) in EPISODES.items():
            win = w[(w.index >= a) & (w.index <= b)]
            s[name] = round((win.iloc[-1] / win.iloc[0] - 1) * 100, 1) \
                if len(win) > 1 else np.nan
        return s


# ------------------------------------------------------------------------
class Trend:
    def __init__(self, sma=50, down="put", frac=0.75, down_frac=0.375,
                 dte=150, delta=0.75, roll_dte=45):
        self.__dict__.update(sma=sma, down=down, frac=frac,
                             down_frac=down_frac, dte=dte, delta=delta,
                             roll_dte=roll_dte)
        self.label = f"TREND_sma{sma}_{down}_d{delta:.0%}"

    def want(self, book, td):
        s = book.m.sma(td, self.sma)
        if not np.isfinite(s):
            return None
        return "CALL" if book.m.spot(td) >= s else \
            ("PUT" if self.down == "put" else None)

    def decide(self, book, td):
        want = self.want(book, td)
        cur = book.pos.get("dir")
        if cur is not None and (cur["right"] != want or
                                (cur["exp"] - td).days <= self.roll_dte):
            book.close(td, "dir")
            cur = None
        if want and cur is None:
            frac = self.frac if want == "CALL" else self.down_frac
            book.open(td, "dir", want, frac * book.equity(td), self.dte,
                      delta_tgt=self.delta)


class Breakout(Trend):
    def __init__(self, lookback=20, **kw):
        super().__init__(**kw)
        self.lookback = lookback
        self.label = f"BREAKOUT_{lookback}d_{self.down}"

    def want(self, book, td):
        hi, lo = book.m.donchian(td, self.lookback)
        if not np.isfinite(hi):
            return None
        spot = book.m.spot(td)
        cur = book.pos.get("dir")
        if spot >= hi:
            return "CALL"
        if spot <= lo:
            return "PUT" if self.down == "put" else None
        return cur["right"] if cur else None   # hold until opposite signal


class Straddle:
    def __init__(self, tenor=90, restrike=0.15, frac=0.50, roll_dte=45):
        self.__dict__.update(tenor=tenor, restrike=restrike, frac=frac,
                             roll_dte=roll_dte)
        self.label = f"STRADDLE_t{tenor}_rs{restrike:.0%}"

    def decide(self, book, td):
        spot = book.m.spot(td)
        c, p = book.pos.get("stc"), book.pos.get("stp")
        if c is not None:
            moved = abs(spot / c["strike"] - 1) >= self.restrike
            stale = (c["exp"] - td).days <= self.roll_dte
            if moved or stale:
                book.close(td, "stc")
                book.close(td, "stp")
                c = p = None
        if c is None:
            eq = book.equity(td)
            crow = book.m.pick(td, "CALL", self.tenor, strike_tgt=spot)
            if crow is None:
                return
            k = float(crow["strike"])
            budget = self.frac * eq / 2
            book.open(td, "stc", "CALL", budget, self.tenor, strike_tgt=k)
            book.open(td, "stp", "PUT", budget, self.tenor, strike_tgt=k)


class Combo:
    def __init__(self, trend, straddle):
        self.t, self.s = trend, straddle
        self.label = f"COMBO[{trend.label}+{self.s.label}]"

    def decide(self, book, td):
        self.t.decide(book, td)
        self.s.decide(book, td)


# ------------------------------------------------------------------------
def main():
    QA_DIR.mkdir(exist_ok=True)
    print("loading data ...")
    mkt = ActiveMarket()
    runs = []
    # benchmark: always-long calls (no signal)
    runs.append(Trend(sma=1, down="cash"))
    runs[-1].label = "ALWAYS_CALLS(benchmark)"
    for sma in (20, 50, 100):
        for down in ("cash", "put"):
            runs.append(Trend(sma=sma, down=down))
    for lb in (10, 20, 40):
        runs.append(Breakout(lookback=lb))
    for tenor in (60, 90, 120):
        for rs in (0.10, 0.15, 0.25):
            runs.append(Straddle(tenor=tenor, restrike=rs))
    runs += [
        Combo(Trend(sma=50, frac=0.50, down_frac=0.25),
              Straddle(tenor=90, restrike=0.15, frac=0.25)),
        Combo(Trend(sma=100, frac=0.50, down_frac=0.25),
              Straddle(tenor=90, restrike=0.15, frac=0.25)),
        Combo(Trend(sma=100, frac=0.50, down_frac=0.25, delta=0.75),
              Straddle(tenor=120, restrike=0.25, frac=0.25)),
        Combo(Breakout(lookback=20, frac=0.50, down_frac=0.25),
              Straddle(tenor=90, restrike=0.15, frac=0.25)),
    ]
    rows, ledgers = [], {}
    for pol in runs:
        led, s = Book(mkt, pol).run()
        ledgers[s["policy"]] = led
        rows.append(s)
        print(f"  {s['policy']:<42} end={s['end_wealth']:>10,.0f} "
              f"DD={s['max_dd_pct']:>6.1f}% MAR={s['MAR']:>5} "
              f"c25={s['crash25']:>6}% m26={s['meltup26']:>6}% "
              f"c26={s['crash26']:>6}% QA={s['qa_recon']}")
    df = pd.DataFrame(rows).sort_values("MAR", ascending=False)
    df.to_csv(ROOT / "active_lab_results.csv", index=False)
    best = df.iloc[0]["policy"]
    ledgers[best].to_csv(ROOT / "active_lab_ledger.csv", index=False)
    lines = ["ACTIVE LAB -- SIGNAL-DRIVEN LONG-OPTIONS STRATEGIES",
             f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}",
             "weekly EOD decisions; no commissions (user instruction); "
             "long options only -> max loss = premium held, no margin",
             "episode columns = return over each wild swing", ""]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        lines.append(df.to_string(index=False))
    qa_fail = df["qa_recon"].ne("PASS").sum()
    lines += ["", f"best (by MAR): {best}   ledger -> active_lab_ledger.csv",
              f"QA reconciliation failures: {qa_fail} of {len(df)}"]
    (QA_DIR / "active_lab_report.txt").write_text("\n".join(lines) + "\n")
    print(f"\nresults -> active_lab_results.csv; best={best}; "
          f"QA failures: {qa_fail}")


if __name__ == "__main__":
    main()
