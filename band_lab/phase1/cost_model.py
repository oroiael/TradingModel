"""
Phase 1 addendum — a per-trade cost model.

The cost model in `v14_pair_protocol.py` is a single flat number per ON day
(SOXL 3.7 bp, SOXS 9.6 bp) built from an assumed 3.17 / 3.36 trades per day.
That was the right shape for a research answer, and its mean is sound. It
has three structural gaps, and Phase 1 produced the trade-level data needed
to close two of them:

  G1  It charges every ON day the same. Real fill counts are bimodal — 31%
      of SOXL ON-days hit the 5-fill cap and 17% take a single fill — and
      fill count correlates +0.44 with the day's P&L. A flat charge
      therefore overcharges the losing days and undercharges the winning
      ones, which distorts the tails and the worst-day guarantee.

  G2  It charges `0.30 x full spread` per round trip. Crossing a spread
      costs a HALF spread, and the legs that actually cross are the stop and
      the 15:55 flatten — measured at 28.7% (SOXL) / 28.2% (SOXS) of exits,
      which is a striking confirmation of the 0.30 guess. But the charge is
      then ~2x a half-spread, so the model carries an unnamed slippage
      buffer inside its spread term. Naming it separately is what lets Phase
      2 falsify it.

  G3  Spread is assumed 1 cent, always. This strategy trades ONLY when
      ATR5 >= 6%, i.e. it self-selects into the exact regime where spreads
      widen. Nothing in this repository can measure a spread — the data is
      5-minute OHLCV with no quotes — so this stays a parameter, and the
      honest deliverable is a sensitivity table rather than a point estimate.

Nothing here changes `band_lab/out/v14_*.csv`. Those are the validated
artifacts and Phase 1 parity depends on reproducing them; this module
reports what a better cost model would do to them.

Usage:  python3 band_lab/phase1/cost_model.py
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BAND_LAB = os.path.dirname(HERE)
ROOT = os.path.dirname(BAND_LAB)
for p in (HERE, BAND_LAB, os.path.join(ROOT, "cycle_lab")):
    if p not in sys.path:
        sys.path.insert(0, p)

from spec_engine import RESEARCH_COMPAT, load_bars, run_sleeve

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
SLEEVES = ["SOXL", "SOXS"]
SLEEVE_CAPITAL = 150_000.0

# §4: historical prices in these files are ADJUSTED and are not tradeable
# levels (SOXS's back-adjusted history reaches $1.17M/share). A forward-
# looking cost estimate must use what you would trade at today, so costs are
# computed at the current price, exactly as v14 does.
CURRENT_PX = {"SOXL": 158.41, "SOXS": 51.61}


@dataclass(frozen=True)
class CostConfig:
    """IBKR Pro **Fixed** pricing, US equities, per §2.5 of STRATEGY_SPEC."""
    # --- commission: $0.005/share, $1.00 order minimum, 1% of value cap
    commission_per_share: float = 0.005
    commission_min_per_order: float = 1.00
    commission_max_frac_of_value: float = 0.01

    # --- regulatory, SELL side only
    # SEC Section 31 fee. The rate is reset by the SEC at least annually and
    # has moved by more than 3x between recent fiscal years -- reconfirm it
    # before Phase 3 rather than trusting this constant.
    sec_fee_bp_on_sells: float = 0.28
    finra_taf_per_share: float = 0.000166
    finra_taf_max_per_order: float = 8.30

    # --- execution. Which legs cross is not a parameter, it is the strategy:
    #   entry   resting BUY LIMIT   -> never crosses
    #   target  resting SELL LIMIT  -> never crosses
    #   stop    SELL STOP -> market -> crosses, plus stop-specific slippage
    #   flatten MARKET at 15:55     -> crosses, plus late-day slippage
    spread_cents: float = 1.0
    stop_slippage_cents: float = 0.0       # BEYOND the half-spread
    flatten_slippage_cents: float = 0.0    # BEYOND the half-spread

    # --- fixed overhead, amortised over trading days
    market_data_usd_per_month: float = 0.0
    trading_days_per_month: float = 21.0


CROSSING_EXITS = ("stop", "flatten")


def _commission(qty: float, price: float, cfg: CostConfig) -> float:
    value = qty * price
    c = max(cfg.commission_per_share * qty, cfg.commission_min_per_order)
    return min(c, cfg.commission_max_frac_of_value * value)


def _reg_fees(qty: float, price: float, cfg: CostConfig) -> float:
    """SEC Section 31 + FINRA TAF. Sells only."""
    sec = qty * price * cfg.sec_fee_bp_on_sells / 1e4
    taf = min(cfg.finra_taf_per_share * qty, cfg.finra_taf_max_per_order)
    return sec + taf


def trade_cost_usd(price: float, outcome: str, cfg: CostConfig,
                   capital: float = SLEEVE_CAPITAL) -> dict:
    """Cost of one round trip, in dollars, at `price`, sized f=1.0."""
    qty = np.floor(capital / price)
    comm = _commission(qty, price, cfg) * 2          # buy + sell
    reg = _reg_fees(qty, price, cfg)                 # sell only
    if outcome in CROSSING_EXITS:
        slip_c = (cfg.stop_slippage_cents if outcome == "stop"
                  else cfg.flatten_slippage_cents)
        exec_ = qty * (cfg.spread_cents / 2.0 + slip_c) / 100.0
    else:
        exec_ = 0.0
    return {"commission": comm, "regulatory": reg, "execution": exec_,
            "total": comm + reg + exec_, "qty": qty}


def per_trade_costs(trades: pd.DataFrame, price: float, cfg: CostConfig,
                    capital: float = SLEEVE_CAPITAL) -> pd.DataFrame:
    """Cost of every trade in the log, in fractions of sleeve capital."""
    rows = [trade_cost_usd(price, o, cfg, capital) for o in trades["outcome"]]
    c = pd.DataFrame(rows, index=trades.index)
    for col in ("commission", "regulatory", "execution", "total"):
        c[col + "_frac"] = c[col] / capital
    return pd.concat([trades[["date", "outcome"]], c], axis=1)


def daily_cost_series(trades: pd.DataFrame, price: float, cfg: CostConfig,
                      on_index: pd.Index,
                      capital: float = SLEEVE_CAPITAL) -> pd.Series:
    """Per-ON-day cost as a fraction of sleeve capital, charged per trade."""
    c = per_trade_costs(trades, price, cfg, capital)
    daily = c.groupby("date")["total_frac"].sum().reindex(on_index).fillna(0.0)
    if cfg.market_data_usd_per_month:
        daily = daily + (cfg.market_data_usd_per_month
                         / cfg.trading_days_per_month / capital)
    return daily


# ---------------------------------------------------------------- v14 model
def v14_flat_cost_bp(price: float, trades_per_day: float,
                     capital: float = SLEEVE_CAPITAL) -> float:
    """The incumbent: flat bp per ON day. Reproduced here for comparison."""
    shares = capital / price
    comm_bp_side = max(0.005 * shares, 1.00) / capital * 1e4
    return (2 * comm_bp_side + 0.35 + 0.30 * (0.01 / price) * 1e4) * trades_per_day


# ------------------------------------------------------------------- report
def metrics(net: pd.Series) -> dict:
    return {"bp_per_ON_day": round(net.mean() * 1e4, 1),
            "sharpe": round(net.mean() / net.std() * np.sqrt(252), 2),
            "worst_day_%": round(net.min() * 100, 3),
            "total_%": round(net.sum() * 100, 1)}


def volatility_proxy() -> pd.DataFrame:
    """G3: spreads widen with volatility and this strategy only trades
    volatile days. No quote data exists here, so measure the regime
    difference with intrabar range as a proxy and let the reader scale."""
    rows = []
    for sym in SLEEVES:
        log, _, _ = run_sleeve(sym, RESEARCH_COMPAT)
        bars = load_bars(sym)
        rng = ((bars["High"] - bars["Low"]) / bars["Close"] * 1e4)
        on_days = set(log.index[log["traded"]])
        is_on = bars["date"].isin(on_days)
        rows.append({
            "sleeve": sym,
            "median_5min_bar_range_bp_ON": round(rng[is_on].median(), 1),
            "median_5min_bar_range_bp_OFF": round(rng[~is_on].median(), 1),
            "ON/OFF_ratio": round(rng[is_on].median() / rng[~is_on].median(), 2),
        })
    return pd.DataFrame(rows)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    base = CostConfig()
    gross, logs, trades = {}, {}, {}
    for sym in SLEEVES:
        logs[sym], gross[sym], trades[sym] = run_sleeve(sym, RESEARCH_COMPAT)

    # ---------------------------------------------------------------- 1
    print("=" * 92)
    print("1. COST PER ROUND TRIP, BY EXIT TYPE  (IBKR Pro Fixed, $150K, f=1.0)")
    print("=" * 92)
    rows = []
    for sym in SLEEVES:
        px = CURRENT_PX[sym]
        for outcome in ("target", "stop", "flatten"):
            c = trade_cost_usd(px, outcome, base)
            share = (trades[sym]["outcome"] == outcome).mean() * 100
            rows.append({
                "sleeve": sym, "price": px, "shares": int(c["qty"]),
                "exit": outcome, "share_of_exits_%": round(share, 1),
                "crosses": "yes" if outcome in CROSSING_EXITS else "no",
                "commission_bp": round(c["commission"] / SLEEVE_CAPITAL * 1e4, 2),
                "regulatory_bp": round(c["regulatory"] / SLEEVE_CAPITAL * 1e4, 2),
                "execution_bp": round(c["execution"] / SLEEVE_CAPITAL * 1e4, 2),
                "total_bp": round(c["total"] / SLEEVE_CAPITAL * 1e4, 2)})
    rt = pd.DataFrame(rows)
    print(rt.to_string(index=False))
    rt.to_csv(os.path.join(OUT, "cost_per_round_trip.csv"), index=False)

    # ---------------------------------------------------------------- 2
    print()
    print("=" * 92)
    print("2. PER-TRADE COSTING vs THE FLAT v14 CHARGE")
    print("=" * 92)
    rows = []
    for sym in SLEEVES:
        px, g = CURRENT_PX[sym], gross[sym]
        tpd = logs[sym].loc[logs[sym]["traded"], "fills"].mean()
        flat_bp = v14_flat_cost_bp(px, tpd)
        per_day = daily_cost_series(trades[sym], px, base, g.index)
        rows.append({"sleeve": sym, "model": "v14 flat", **metrics(g - flat_bp / 1e4),
                     "mean_cost_bp": round(flat_bp, 2),
                     "cost_bp_p5": round(flat_bp, 2), "cost_bp_p95": round(flat_bp, 2)})
        rows.append({"sleeve": sym, "model": "per-trade", **metrics(g - per_day),
                     "mean_cost_bp": round(per_day.mean() * 1e4, 2),
                     "cost_bp_p5": round(per_day.quantile(.05) * 1e4, 2),
                     "cost_bp_p95": round(per_day.quantile(.95) * 1e4, 2)})
    cmp_ = pd.DataFrame(rows)
    print(cmp_.to_string(index=False))
    cmp_.to_csv(os.path.join(OUT, "cost_model_comparison.csv"), index=False)
    print("\n  The flat charge is right on the mean by construction. What it gets")
    print("  wrong is WHERE the cost lands: it overcharges 1-2 fill days (which")
    print("  are the losing days) and undercharges 5-fill days (the winners).")

    # ---------------------------------------------------------------- 3
    print()
    print("=" * 92)
    print("3. SENSITIVITY — the two assumptions nobody has measured yet")
    print("=" * 92)
    rows = []
    for sym in SLEEVES:
        px, g = CURRENT_PX[sym], gross[sym]
        for spread in (1.0, 2.0, 3.0, 5.0):
            for slip in (0.0, 1.0, 2.0):
                cfg = replace(base, spread_cents=spread,
                              stop_slippage_cents=slip, flatten_slippage_cents=slip)
                d = daily_cost_series(trades[sym], px, cfg, g.index)
                net = g - d
                rows.append({"sleeve": sym, "spread_cents": spread,
                             "slippage_cents": slip,
                             "cost_bp_per_ON_day": round(d.mean() * 1e4, 1),
                             "net_bp_per_ON_day": round(net.mean() * 1e4, 1),
                             "sharpe": round(net.mean() / net.std() * np.sqrt(252), 2)})
    sens = pd.DataFrame(rows)
    for sym in SLEEVES:
        s = sens[sens.sleeve == sym]
        print(f"\n  {sym} — net bp/ON-day (gross {gross[sym].mean()*1e4:.1f})")
        print(s.pivot(index="spread_cents", columns="slippage_cents",
                      values="net_bp_per_ON_day").to_string())
    sens.to_csv(os.path.join(OUT, "cost_sensitivity.csv"), index=False)

    # ---------------------------------------------------------------- 4
    print()
    print("=" * 92)
    print("4. G3 — DOES THE STRATEGY SELF-SELECT INTO WIDE-SPREAD DAYS?")
    print("=" * 92)
    vp = volatility_proxy()
    print(vp.to_string(index=False))
    vp.to_csv(os.path.join(OUT, "cost_regime_proxy.csv"), index=False)
    print("\n  No quote data exists in this repository, so the spread cannot be")
    print("  measured -- only the regime it is sampled in. ON-day 5-minute bars")
    print("  are materially wider than OFF-day bars, so a 1-cent assumption")
    print("  calibrated on an average day is optimistic for the days actually")
    print("  traded. Row 'spread 2c' in section 3 is the more prudent planning")
    print("  case until Phase 2 measures real fills.")

    # ---------------------------------------------------------------- 5
    print()
    print("=" * 92)
    print("5. COST vs ACCOUNT SIZE — the $1.00 order minimum and Phase 3")
    print("=" * 92)
    rows = []
    for sym in SLEEVES:
        px, g = CURRENT_PX[sym], gross[sym]
        for cap in (10_000, 22_500, 30_000, 50_000, 150_000, 500_000):
            d = daily_cost_series(trades[sym], px, base, g.index, capital=cap)
            qty = int(np.floor(cap / px))
            binds = base.commission_per_share * qty < base.commission_min_per_order
            rows.append({"sleeve": sym, "sleeve_capital": cap, "shares_per_order": qty,
                         "$1_min_binds": "YES" if binds else "no",
                         "cost_bp_per_ON_day": round(d.mean() * 1e4, 1),
                         "net_bp_per_ON_day": round((g - d).mean() * 1e4, 1)})
    scale = pd.DataFrame(rows)
    print(scale.to_string(index=False))
    scale.to_csv(os.path.join(OUT, "cost_by_account_size.csv"), index=False)
    print("\n  §9 Phase 3 runs live at 10-20% of intended capital and then asks")
    print("  whether realised cost matches 'the modelled 3.7 bp/day (SOXL) and")
    print("  9.6 bp/day (SOXS)'. Those figures are $150K figures. At Phase 3")
    print("  sizing the $1.00 order minimum binds and cost per bp is structurally")
    print("  higher -- comparing against the $150K number would fail a system")
    print("  that is working correctly. Phase 3 must compare against its OWN row.")

    # ---------------------------------------------------------------- 6
    print()
    print("=" * 92)
    print("6. DOES A BETTER COST MODEL MOVE THE w PLATEAU? (§2.9, v14 T3)")
    print("=" * 92)
    scenarios = {
        "v14 flat (incumbent)": None,
        "per-trade, 1c spread": replace(base, spread_cents=1.0),
        "per-trade, 2c + 1c slip": replace(base, spread_cents=2.0,
                                           stop_slippage_cents=1.0,
                                           flatten_slippage_cents=1.0),
        "per-trade, SOXS stressed 5c + 2c slip": replace(base, spread_cents=5.0,
                                                        stop_slippage_cents=2.0,
                                                        flatten_slippage_cents=2.0),
    }
    rows = []
    for label, cfg in scenarios.items():
        nets = {}
        for sym in SLEEVES:
            px, g = CURRENT_PX[sym], gross[sym]
            if cfg is None:
                tpd = logs[sym].loc[logs[sym]["traded"], "fills"].mean()
                nets[sym] = g - v14_flat_cost_bp(px, tpd) / 1e4
            else:
                nets[sym] = g - daily_cost_series(trades[sym], px, cfg, g.index)
        cal = pd.date_range(min(n.index.min() for n in nets.values()),
                            max(n.index.max() for n in nets.values()), freq="B")
        a = nets["SOXL"].reindex(cal).fillna(0.0)
        b = nets["SOXS"].reindex(cal).fillna(0.0)
        best_w, best_s = None, -99
        for w in np.arange(0, 1.0001, 0.125):
            r = w * a + (1 - w) * b
            s = r.mean() / r.std() * np.sqrt(252)
            if s > best_s:
                best_s, best_w = s, w
        half = 0.5 * a + 0.5 * b
        rows.append({"cost scenario": label,
                     "SOXL_net_bp": round(nets["SOXL"].mean() * 1e4, 1),
                     "SOXS_net_bp": round(nets["SOXS"].mean() * 1e4, 1),
                     "argmax_w": best_w, "sharpe_at_argmax": round(best_s, 2),
                     "sharpe_at_w=0.5": round(half.mean() / half.std() * np.sqrt(252), 2)})
    wtab = pd.DataFrame(rows)
    print(wtab.to_string(index=False))
    wtab.to_csv(os.path.join(OUT, "cost_w_plateau.csv"), index=False)

    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
