#!/usr/bin/env python3
"""
capital_models.py  --  turn a per-trade ledger into equity curves & risk stats.

Two sizing models, both "reinvest winnings" (compound on realized capital):

  full_risk  : the literal "invest 100% of capital" reading. For a call credit
               spread the broker collateral / true max loss per contract is
               (width - credit)*100, so n = floor(capital / max_loss_per_ctr).
               A single maximum-loss expiration therefore takes capital to ~0
               (ruin). This is the honest consequence of 100% deployment.

  fractional : risk a fixed fraction f of current capital per trade
               (n = floor(f*capital / max_loss_per_ctr)). Used only to expose
               the drawdown STRUCTURE that full-risk ruin hides.

Nothing here invents returns: P&L per trade = n * pnl_share * 100, taken
straight from the ledger the engine produced.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

CONTRACT = 100.0  # shares per option contract


def _drawdown(equity: np.ndarray):
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return dd, float(dd.min())


def full_risk_curve(ledger: pd.DataFrame, capital0=100_000.0, ruin_frac=0.01):
    """100%-at-risk sizing. Returns (equity_series, ruined_bool, ruin_index).

    "Functional ruin" = equity first falls below ruin_frac of the start (default
    1%). Because n is floored, one maximum-loss expiration cannot literally reach
    $0 (a few dollars of residual remain that can no longer fund a contract), so
    reporting exact-zero ruin would understate the blow-up. We report the first
    trade that takes the account below 1% of starting capital instead.
    """
    cap = capital0
    eq = []
    ruined, ruin_idx = False, None
    for k, r in enumerate(ledger.itertuples(index=False)):
        max_loss_ctr = r.max_loss_share * CONTRACT
        n = int(cap // max_loss_ctr) if max_loss_ctr > 0 else 0
        pnl = n * r.pnl_share * CONTRACT
        cap = max(cap + pnl, 0.0)
        eq.append(cap)
        if cap < ruin_frac * capital0 and not ruined:
            ruined, ruin_idx = True, k
    return np.array(eq), ruined, ruin_idx


def fractional_curve(ledger: pd.DataFrame, capital0=100_000.0, risk_frac=0.10):
    """Risk a fixed fraction of capital per trade; compound."""
    cap = capital0
    eq = []
    for r in ledger.itertuples(index=False):
        max_loss_ctr = r.max_loss_share * CONTRACT
        budget = risk_frac * cap
        n = int(budget // max_loss_ctr) if max_loss_ctr > 0 else 0
        pnl = n * r.pnl_share * CONTRACT
        cap = max(cap + pnl, 0.0)
        eq.append(cap)
    return np.array(eq)


def curve_stats(ledger: pd.DataFrame, equity: np.ndarray, capital0=100_000.0):
    """Summary risk/return stats for an equity path aligned to the ledger."""
    if len(equity) == 0:
        return {}
    dd, maxdd = _drawdown(np.concatenate([[capital0], equity]))
    total_ret = equity[-1] / capital0 - 1.0
    dates = pd.to_datetime(ledger["entry_date"])
    yrs = (dates.iloc[-1] - dates.iloc[0]).days / 365.25 if len(dates) > 1 else np.nan
    cagr = (equity[-1] / capital0) ** (1 / yrs) - 1 if (yrs and equity[-1] > 0) else np.nan
    # per-trade return series (guard divide-by-zero at ruin)
    eqp = np.concatenate([[capital0], equity])
    with np.errstate(divide="ignore", invalid="ignore"):
        tr = np.where(eqp[:-1] > 0, eqp[1:] / eqp[:-1] - 1.0, 0.0)
    sharpe_tr = np.mean(tr) / np.std(tr) if np.std(tr) > 0 else np.nan
    return dict(end_equity=float(equity[-1]), total_return=float(total_ret),
                cagr=float(cagr) if cagr == cagr else np.nan,
                max_drawdown=float(maxdd),
                per_trade_sharpe=float(sharpe_tr) if sharpe_tr == sharpe_tr else np.nan)


def expectancy_stats(ledger: pd.DataFrame):
    """Sizing-independent edge of the trade stream."""
    if len(ledger) == 0:
        return dict(trades=0)
    L = ledger
    return dict(
        trades=len(L),
        win_rate=float(L["win"].mean()),
        breach_rate=float(L["breach"].mean()),
        maxloss_rate=float(L["max_loss_hit"].mean()),
        avg_credit_pct_width=float(L["credit_pct_width"].mean()),
        mean_ror=float(L["ror"].mean()),           # mean return per $ risked
        median_ror=float(L["ror"].median()),
        total_ror=float(L["ror"].sum()),           # sum of per-unit-risk returns
        mean_pnl_share=float(L["pnl_share"].mean()),
        worst_ror=float(L["ror"].min()),
        best_ror=float(L["ror"].max()),
    )
