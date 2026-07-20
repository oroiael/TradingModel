#!/usr/bin/env python3
"""
R:50% BLEND -- integrated backtest of the regime-switched portfolio
===================================================================

The strategy selected from blend_lab.py ("R_above50_below0"), built here
as ONE account managing every leg directly (not a NAV simulation), so the
weekly ledger shows each leg, each trade, and each trigger firing.

THE REGIME SWITCH (computed once a week, first trading day, EOD):
    RISK-ON  : SOXL close >= its 100-day simple moving average
    RISK-OFF : SOXL close <  its 100-day simple moving average

Target sleeve weights of total account equity:
    RISK-ON  : 50% ACTIVE sleeve + 50% DEFENSE sleeve
    RISK-OFF : 0% ACTIVE (all active legs closed) + 100% DEFENSE

DEFENSE sleeve (the R2 "Defense package"), applied to its sleeve equity:
    D1 LONG CALL   75-delta, 120-180 DTE target 150, sized so share-
                   equivalent notional = 50% of sleeve equity; rolled out
                   at <=45 DTE; resized weekly (10% dead-band).
    D2 SHORT CALL  weekly expiry, 15-20 delta (target 0.175), 1:1 with
                   D1 contracts; cash-settled at expiry close.  SKIPPED
                   while spot < 50d SMA or after a >10% down week.
    D3 PUT WING    25-delta, ~90 DTE, 0.5 contract per D1 contract;
                   rolled at <=21 DTE; MONETIZED (sold and re-bought
                   fresh) when its price reaches 3x cost.
    D4 CASH        idle cash accrues 4% APY (T-bill assumption).

ACTIVE sleeve (only exists in RISK-ON; its own trend mode is by
construction always "calls" because the allocation uses the same signal):
    A1 TREND CALL  75-delta, ~150 DTE, share-equivalent notional = 50% of
                   sleeve equity; rolled at <=45 DTE; resized weekly
                   (10% dead-band).
    A2/A3 STRADDLE 120-DTE ATM call + put, same whole strike, 25% of
                   sleeve equity split evenly; RE-STRUCK to the new ATM
                   when spot moves 25% from the strike; rolled <=45 DTE.

Execution everywhere: project 20%-of-spread rule on real EOD quotes
(sell = bid+0.2*spread, buy = ask-0.2*spread; bid=0 rejected), whole
strikes preferred, $0.65/contract commissions.  Weekly income sweep:
25% of positive DEFENSE-leg realized P&L moves to the sweep account.

Outputs:
    r_blend_ledger.csv     full weekly per-leg backtest table
    qa/r_blend_report.txt  stats + yearly/episode/margin summary
"""

from pathlib import Path

import numpy as np
import pandas as pd

from soxl_options_loader import ROOT
from put_diagonal_backtest import COMMISSION, EPS
from active_lab import ActiveMarket, EPISODES

QA_DIR = Path(__file__).resolve().parent / "qa"
START = 150_000.0
ACTIVE_W = 0.50          # active sleeve weight in RISK-ON
TREND_SMA = 100          # allocation + active direction signal
DEF_SMA = 50             # defense call-skip signal
CASH_APY = 0.04
SCAN = (-0.45, -0.30, -0.15, 0.0, 0.15, 0.30, 0.45)


class RBlend:
    def __init__(self, mkt: ActiveMarket):
        self.m = mkt
        self.cash = START
        self.sweep = 0.0
        self.commissions = 0.0
        self.interest = 0.0
        self.realized = []            # (date, leg, amount)
        self.legs = {}                # leg_name -> lot dict
        self.prev_week_spot = None
        self.rows = []
        self.wk = None

    # ------------------------------------------------------ primitives --
    def commission(self, n):
        c = COMMISSION * n
        self.commissions += c
        self.cash -= c

    def realize(self, td, leg, amt):
        self.realized.append((td, leg, amt))
        self.wk[f"{leg}_realized"] = round(
            self.wk.get(f"{leg}_realized", 0.0) + amt, 2)

    def mark(self, td, lot):
        q = self.m.quote(td, lot["exp"], lot["strike"], lot["right"])
        if q is not None:
            lot["last_mark"] = float(q["mid"])
        return lot["last_mark"]

    def equity(self, td):
        eq = self.cash
        for name, lot in self.legs.items():
            v = self.mark(td, lot) * 100 * lot["n"]
            eq += -v if lot["short"] else v
        return eq

    def close(self, td, name, why):
        lot = self.legs.pop(name, None)
        if lot is None:
            return
        q = self.m.quote(td, lot["exp"], lot["strike"], lot["right"])
        if lot["short"]:
            px = float(q["buy_px"]) if q is not None and bool(q["liquid"]) \
                else lot["last_mark"]
            self.cash -= px * 100 * lot["n"]
            pnl = (lot["entry_px"] - px) * 100 * lot["n"]
        else:
            px = float(q["sell_px"]) if q is not None and bool(q["liquid"]) \
                else lot["last_mark"]
            self.cash += px * 100 * lot["n"]
            pnl = (px - lot["entry_px"]) * 100 * lot["n"]
        self.commission(lot["n"])
        self.realize(td, name, pnl)
        self.wk[f"{name}_action"] = (self.wk.get(f"{name}_action", "")
                                     + f"|CLOSE({why})@{px:.2f}").strip("|")

    def open(self, td, name, right, short, n, row, why):
        if n <= 0 or row is None:
            self.wk[f"{name}_action"] = f"SKIP({why})"
            return
        px = float(row["sell_px"] if short else row["buy_px"])
        if short:
            self.cash += px * 100 * n
        else:
            cap = int((self.cash - 1) // (px * 100 + COMMISSION))
            n = min(n, cap)
            if n <= 0:
                self.wk[f"{name}_action"] = "SKIP(NO_CASH)"
                return
            self.cash -= px * 100 * n
        self.commission(n)
        self.legs[name] = {"right": right, "short": short,
                           "strike": float(row["strike"]),
                           "exp": row["expiration"], "n": n, "entry_px": px,
                           "last_mark": float(row["mid"])}
        self.wk.update({
            f"{name}_action": (self.wk.get(f"{name}_action", "")
                               + f"|{why}").strip("|"),
            f"{name}_strike": float(row["strike"]),
            f"{name}_exp": str(row["expiration"].date()),
            f"{name}_n": n, f"{name}_px": round(px, 3),
            f"{name}_note": (f"bid={row['bid']:.2f} ask={row['ask']:.2f} "
                             f"delta={row['delta']:.2f} dte={row['dte']}")})

    def resize(self, td, name, target_n, band=0.10):
        lot = self.legs.get(name)
        if lot is None:
            return
        q = self.m.quote(td, lot["exp"], lot["strike"], lot["right"])
        if q is None or not bool(q["liquid"]):
            return
        diff = target_n - lot["n"]
        if abs(diff) < max(1, band * max(lot["n"], target_n)):
            return
        if diff < 0:
            k = -diff
            px = float(q["sell_px"])
            self.cash += px * 100 * k
            self.commission(k)
            self.realize(td, name, (px - lot["entry_px"]) * 100 * k)
            lot["n"] = target_n
            self.wk[f"{name}_action"] = f"RESIZE_DOWN(-{k})"
        else:
            px = float(q["buy_px"])
            k = min(diff, int((self.cash - 1) // (px * 100 + COMMISSION)))
            if k <= 0:
                return
            self.cash -= px * 100 * k
            self.commission(k)
            lot["entry_px"] = (lot["entry_px"] * lot["n"] + px * k) \
                / (lot["n"] + k)
            lot["n"] += k
            self.wk[f"{name}_action"] = f"RESIZE_UP(+{k})"
        self.wk[f"{name}_n"] = lot["n"]

    # ------------------------------------------------------ leg logic ---
    def manage_long_call(self, td, name, sleeve_eq, frac, dte_tgt):
        """Shared logic for D1 and A1: 75d call, roll <=45 DTE, resize."""
        spot = self.m.spot(td)
        target_n = int(frac * sleeve_eq // (spot * 100))
        lot = self.legs.get(name)
        if lot is not None and (lot["exp"] - td).days <= 45:
            self.close(td, name, f"ROLL_DTE({(lot['exp'] - td).days}d)")
            lot = None
        if lot is None:
            row = self.m.pick(td, "CALL", dte_tgt, delta_tgt=0.75)
            self.open(td, name, "CALL", False, target_n, row, "BUY")
        else:
            self.resize(td, name, target_n)
            self.wk.setdefault(f"{name}_action", "HOLD")
            self.wk.update({f"{name}_strike": lot["strike"],
                            f"{name}_n": lot["n"],
                            f"{name}_exp": str(lot["exp"].date())})

    def manage_put_wing(self, td, sleeve_eq):
        d1 = self.legs.get("D1_longcall")
        target = int(round(0.5 * (d1["n"] if d1 else 0)))
        lot = self.legs.get("D3_putwing")
        if lot is not None:
            q = self.m.quote(td, lot["exp"], lot["strike"], "PUT")
            if q is not None and bool(q["liquid"]) and \
                    float(q["sell_px"]) >= 3.0 * lot["entry_px"]:
                self.close(td, "D3_putwing", "TP_MONETIZED_3x")
                lot = None
            elif (lot["exp"] - td).days <= 21:
                self.close(td, "D3_putwing", "ROLL_DTE")
                lot = None
        if lot is None and target > 0:
            row = self.m.pick(td, "PUT", 90, delta_tgt=0.25)
            self.open(td, "D3_putwing", "PUT", False, target, row, "BUY")
        elif lot is not None:
            self.wk.setdefault("D3_putwing_action", "HOLD")
            self.wk.update(D3_putwing_strike=lot["strike"],
                           D3_putwing_n=lot["n"])

    def manage_short_call(self, td):
        if "D2_shortcall" in self.legs:
            self.wk.setdefault("D2_shortcall_action", "HELD")
            return
        spot = self.m.spot(td)
        sma = self.m.sma(td, DEF_SMA)
        if np.isfinite(sma) and spot < sma:
            self.wk["D2_shortcall_action"] = "SKIP(BELOW_50D_SMA)"
            return
        if self.prev_week_spot and spot / self.prev_week_spot - 1 < -0.10:
            self.wk["D2_shortcall_action"] = "SKIP(AFTER_>10%_DOWN_WEEK)"
            return
        d1 = self.legs.get("D1_longcall")
        if d1 is None:
            self.wk["D2_shortcall_action"] = "SKIP(NO_D1)"
            return
        chain = self.m.week_expiry_chain(td)
        if chain is None:
            self.wk["D2_shortcall_action"] = "SKIP(NO_EXPIRY)"
            return
        row = self.m.pick_short_call(chain, 0.175)
        self.open(td, "D2_shortcall", "CALL", True, d1["n"], row, "SELL")

    def manage_straddle(self, td, sleeve_eq):
        spot = self.m.spot(td)
        c, p = self.legs.get("A2_stcall"), self.legs.get("A3_stput")
        if c is not None:
            moved = abs(spot / c["strike"] - 1) >= 0.25
            stale = (c["exp"] - td).days <= 45
            if moved or stale:
                why = "RESTRIKE_25%MOVE" if moved else "ROLL_DTE"
                self.close(td, "A2_stcall", why)
                self.close(td, "A3_stput", why)
                c = p = None
        if c is None:
            crow = self.m.pick(td, "CALL", 120, strike_tgt=spot)
            if crow is None:
                return
            k, exp = float(crow["strike"]), crow["expiration"]
            ch = self.m.chains[td]
            pg = ch[(ch["right"] == "PUT") & (ch["expiration"] == exp) &
                    (ch["strike"] == k) & ch["liquid"]]
            if pg.empty:
                return
            prow = pg.iloc[0]
            budget = 0.25 * sleeve_eq / 2
            n_c = int(budget // (float(crow["buy_px"]) * 100))
            n_p = int(budget // (float(prow["buy_px"]) * 100))
            self.open(td, "A2_stcall", "CALL", False, n_c, crow, "BUY_ATM")
            self.open(td, "A3_stput", "PUT", False, n_p, prow, "BUY_ATM")
        else:
            for nm, lot in (("A2_stcall", c), ("A3_stput", p)):
                self.wk.setdefault(f"{nm}_action", "HOLD")
                self.wk.update({f"{nm}_strike": lot["strike"],
                                f"{nm}_n": lot["n"]})

    def settle_short_call(self, td):
        lot = self.legs.pop("D2_shortcall", None)
        if lot is None:
            return
        px = self.m.settle_close(lot["exp"])
        intrinsic = max(px - lot["strike"], 0.0)
        if intrinsic > 0:
            self.cash -= intrinsic * 100 * lot["n"]
        self.realize(td, "D2_shortcall",
                     (lot["entry_px"] - intrinsic) * 100 * lot["n"])
        self.wk["D2_shortcall_outcome"] = (
            f"{'SETTLED_ITM' if intrinsic else 'EXPIRED_WORTHLESS'}"
            f"(close {px:.2f})")

    # ------------------------------------------------------ margin scan -
    def pm_scan(self, td):
        S = self.m.spot(td)
        worst = 0.0
        for mv in SCAN:
            Sx = S * (1 + mv)
            pnl = 0.0
            for lot in self.legs.values():
                iv = max(Sx - lot["strike"], 0.0) if lot["right"] == "CALL" \
                    else max(lot["strike"] - Sx, 0.0)
                sgn = -1 if lot["short"] else 1
                pnl += sgn * (iv - lot["last_mark"]) * 100 * lot["n"]
            worst = min(worst, pnl)
        sn = self.legs.get("D2_shortcall")
        return max(-worst, 37.5 * (sn["n"] if sn else 0))

    # ------------------------------------------------------ main loop ---
    def run(self):
        weeks = {}
        for d in self.m.dates:
            weeks.setdefault(d.to_period("W-SUN"), []).append(d)
        wl = sorted(weeks)
        for wi, wp in enumerate(wl):
            d0, dl = weeks[wp][0], weeks[wp][-1]
            spot = self.m.spot(d0)
            sma100 = self.m.sma(d0, TREND_SMA)
            regime = bool(np.isfinite(sma100) and spot >= sma100)
            self.wk = {"week_start": str(d0.date()),
                       "week_end": str(dl.date()),
                       "spot_monday": round(spot, 2),
                       "sma100": round(sma100, 2) if np.isfinite(sma100)
                       else np.nan,
                       "regime": "RISK-ON" if regime else "RISK-OFF",
                       "begin_cash": round(self.cash, 2),
                       "begin_equity": round(self.equity(d0), 2),
                       "begin_sweep": round(self.sweep, 2)}
            n_before = len(self.realized)
            if self.cash > 0:
                i = self.cash * CASH_APY / 52
                self.cash += i
                self.interest += i

            total_eq = self.equity(d0)
            active_eq = ACTIVE_W * total_eq if regime else 0.0
            defense_eq = total_eq - active_eq
            self.wk.update(active_target=round(active_eq, 0),
                           defense_target=round(defense_eq, 0))

            # ACTIVE sleeve
            if not regime:
                for name in ("A1_trendcall", "A2_stcall", "A3_stput"):
                    if name in self.legs:
                        self.close(d0, name, "RISK_OFF")
            else:
                self.manage_long_call(d0, "A1_trendcall", active_eq,
                                      0.50, 150)
                self.manage_straddle(d0, active_eq)

            # DEFENSE sleeve
            self.manage_long_call(d0, "D1_longcall", defense_eq, 0.50, 150)
            self.manage_put_wing(d0, defense_eq)
            self.manage_short_call(d0)

            self.wk["pm_requirement"] = round(self.pm_scan(d0), 0)
            self.wk["pm_util_pct"] = round(
                self.wk["pm_requirement"] / max(total_eq, 1) * 100, 1)

            # walk to expiry / settle the weekly short call
            sc = self.legs.get("D2_shortcall")
            if sc is not None and sc["exp"] <= dl:
                self.settle_short_call(dl)

            if wi == len(wl) - 1:
                for name in list(self.legs):
                    self.close(dl, name, "FINAL_LIQUIDATION")

            wk_real = self.realized[n_before:]
            def_real = sum(a for (_, leg, a) in wk_real
                           if leg.startswith("D"))
            swept = 0.0
            if def_real > 0 and wi < len(wl) - 1:
                swept = min(0.25 * def_real, max(self.cash, 0.0))
                self.cash -= swept
                self.sweep += swept
            self.prev_week_spot = self.m.spot(dl)
            self.wk.update(
                spot_friday=round(self.prev_week_spot, 2),
                week_realized=round(sum(a for (_, _, a) in wk_real), 2),
                defense_realized_wk=round(def_real, 2),
                sweep_amount=round(swept, 2),
                end_cash=round(self.cash, 2),
                end_sweep=round(self.sweep, 2),
                end_equity=round(self.equity(dl), 2),
                end_total_wealth=round(self.equity(dl) + self.sweep, 2))
            self.rows.append(self.wk)
        return self.finish()

    def finish(self):
        led = pd.DataFrame(self.rows)
        w = led.set_index(pd.to_datetime(led["week_start"]))[
            "end_total_wealth"]
        yrs = len(w) / 52
        wk = w.pct_change().dropna()
        dd = (w / w.cummax() - 1).min()
        real = pd.DataFrame(self.realized, columns=["d", "leg", "amt"])
        by_leg = real.groupby("leg")["amt"].sum().round(0)
        recon = START + real["amt"].sum() + self.interest - self.commissions
        qa_ok = abs(recon - (self.cash + self.sweep)) < 0.01
        stats = {
            "end_wealth": round(w.iloc[-1], 0),
            "total_ret_pct": round((w.iloc[-1] / START - 1) * 100, 1),
            "cagr_pct": round(((w.iloc[-1] / START) ** (1 / yrs) - 1) * 100,
                              1),
            "max_dd_pct": round(dd * 100, 1),
            "MAR": round((((w.iloc[-1] / START) ** (1 / yrs) - 1) * 100)
                         / abs(dd * 100), 2),
            "worst_wk_pct": round(wk.min() * 100, 1),
            "best_wk_pct": round(wk.max() * 100, 1),
            "riskon_weeks": int((led["regime"] == "RISK-ON").sum()),
            "riskoff_weeks": int((led["regime"] == "RISK-OFF").sum()),
            "income_weeks": int((led["defense_realized_wk"] > 0).sum()),
            "sweep_final": round(self.sweep, 2),
            "interest": round(self.interest, 0),
            "commissions": round(self.commissions, 0),
            "avg_pm_util_pct": round(led["pm_util_pct"].mean(), 1),
            "max_pm_util_pct": round(led["pm_util_pct"].max(), 1),
            "qa_recon": "PASS" if qa_ok else
                        f"FAIL({recon:.2f} vs {self.cash + self.sweep:.2f})",
        }
        for name, (a, b) in EPISODES.items():
            win = w[(w.index >= a) & (w.index <= b)]
            stats[name + "_pct"] = round(
                (win.iloc[-1] / win.iloc[0] - 1) * 100, 1) \
                if len(win) > 1 else np.nan
        yearly = {}
        for y, g in w.groupby(w.index.year):
            prev = w[w.index < g.index[0]]
            base = prev.iloc[-1] if len(prev) else START
            yearly[f"ret_{y}_pct"] = round((g.iloc[-1] / base - 1) * 100, 1)
        stats |= yearly
        return led, stats, by_leg


def main():
    QA_DIR.mkdir(exist_ok=True)
    print("loading data ...")
    mkt = ActiveMarket()
    bt = RBlend(mkt)
    led, stats, by_leg = bt.run()
    led.to_csv(ROOT / "r_blend_ledger.csv", index=False)
    lines = ["R:50% BLEND -- INTEGRATED BACKTEST",
             f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}", ""]
    lines += [f"  {k}: {v}" for k, v in stats.items()]
    lines += ["", "realized P&L by leg:", by_leg.to_string()]
    txt = "\n".join(lines)
    (QA_DIR / "r_blend_report.txt").write_text(txt + "\n")
    print(txt)
    print(f"\nledger -> r_blend_ledger.csv ({len(led)} weeks, "
          f"{len(led.columns)} columns)")


if __name__ == "__main__":
    main()
