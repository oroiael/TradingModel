#!/usr/bin/env python3
"""
backtest.py  --  bear call (call-credit) spread engine for SOXL.

STRATEGY (exactly as specified by the user):
    * SELL 1 call just out-of-the-money  (the "short" leg -- collect premium)
    * BUY  1 call one or more strikes higher (the "long" leg -- defines risk)
    * net CREDIT received; NO underlying is held.
    * hold to expiration, settle at intrinsic value.

This is a bearish/neutral, defined-risk structure:
    max profit  = net credit                     (if S_exp <= K_short)
    max loss    = width - net credit             (if S_exp >= K_long)
    breakeven   = K_short + net credit

DATA REALITY baked in here (measured in profile_data.py):
    * options are DAILY EOD snapshots -> every leg is priced at the daily close.
      There are no intraday option quotes, so "enter Monday 10am" is not
      possible; we enter at the EOD of the entry day and note it.
    * whole-number strikes only (spec rule; ~19% decimal strikes dropped).
    * 20% spread execution rule for fills:
          sell_fill = bid + 0.20*(ask-bid)
          buy_fill  = ask - 0.20*(ask-bid)
      a leg with bid<=0 or ask<bid is illiquid and rejected.
    * settlement uses the underlying_price stamped on the expiration trade_date
      (verified equal to the independent 5-min EOD close, ratio ~1.000).

The engine emits a per-trade LEDGER. Capital models (100%-at-risk sizing,
fractional sizing, drawdown) live in capital_models.py so trade generation and
money management stay decoupled and independently auditable.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


# ----------------------------------------------------------------- fills
def sell_fill(bid, ask):
    return bid + 0.20 * (ask - bid)


def buy_fill(bid, ask):
    return ask - 0.20 * (ask - bid)


def valid_quote(bid, ask):
    return (bid > 0) & (ask >= bid)


# ----------------------------------------------------------------- config
@dataclass
class SpreadConfig:
    target_dte: int = 7            # 7 weekly, 14 two-week, 30 monthly
    dte_tol: int = 4               # accept expirations within +/- tol of target
    short_rule: str = "otm_step"   # "otm_step" | "delta"
    short_otm_step: int = 1        # k-th whole strike strictly above spot
    short_delta: float = 0.30      # used when short_rule == "delta"
    width_steps: int = 1           # long = short + this many whole-strike steps
    fill: str = "spread20"         # "spread20" (the 20% rule) | "mid"


# ----------------------------------------------------------------- indexing
def build_day_index(opt: pd.DataFrame):
    """Pre-slice the (already whole-strike) call chain per trade_date for speed.

    Returns:
      calls_by_td : {trade_date -> DataFrame(strike,bid,ask,delta,expiration,dte)}
      spot_by_td  : {trade_date -> underlying_price}
      trade_dates : sorted list of trade_date
    """
    c = opt[(opt["right"] == "CALL")].copy()
    c = c[valid_quote(c["bid"], c["ask"])]
    calls_by_td, spot_by_td = {}, {}
    for td, g in c.groupby("trade_date"):
        calls_by_td[td] = g[["strike", "bid", "ask", "delta",
                             "expiration", "dte"]].reset_index(drop=True)
        spot_by_td[td] = float(g["underlying_price"].iloc[0])
    trade_dates = sorted(calls_by_td.keys())
    return calls_by_td, spot_by_td, trade_dates


def spot_on(opt_spot_by_td, td):
    return opt_spot_by_td.get(td, np.nan)


# ----------------------------------------------------------------- selection
def pick_expiration(day_chain: pd.DataFrame, target_dte: int, tol: int):
    """Choose the expiration whose DTE is closest to target within tolerance."""
    exps = (day_chain[["expiration", "dte"]].drop_duplicates())
    exps = exps[(exps["dte"] >= target_dte - tol) & (exps["dte"] <= target_dte + tol)]
    if exps.empty:
        return None
    exps = exps.assign(err=(exps["dte"] - target_dte).abs())
    return exps.sort_values(["err", "dte"]).iloc[0]["expiration"]


def select_spread(chain_exp: pd.DataFrame, spot: float, cfg: SpreadConfig):
    """Given the (single-expiration) call chain, choose short & long strikes and
    compute the net credit under the fill model. Returns dict or None."""
    ch = chain_exp.sort_values("strike").reset_index(drop=True)
    strikes = ch["strike"].values
    if len(strikes) < 2:
        return None

    # -- short strike ------------------------------------------------------
    if cfg.short_rule == "otm_step":
        above = np.where(strikes > spot)[0]
        if len(above) < cfg.short_otm_step:
            return None
        si = above[cfg.short_otm_step - 1]
    elif cfg.short_rule == "delta":
        si = int(np.argmin(np.abs(ch["delta"].values - cfg.short_delta)))
    else:
        raise ValueError(cfg.short_rule)

    # -- long strike = short + width_steps grid steps ----------------------
    li = si + cfg.width_steps
    if li >= len(strikes):
        return None

    short = ch.iloc[si]
    long_ = ch.iloc[li]
    if not (valid_quote(short["bid"], short["ask"]) and
            valid_quote(long_["bid"], long_["ask"])):
        return None

    if cfg.fill == "mid":
        s_px = (short["bid"] + short["ask"]) / 2
        l_px = (long_["bid"] + long_["ask"]) / 2
    else:  # spread20
        s_px = sell_fill(short["bid"], short["ask"])
        l_px = buy_fill(long_["bid"], long_["ask"])

    credit = s_px - l_px
    width = float(long_["strike"] - short["strike"])
    if credit <= 0 or width <= 0:
        return None
    return dict(k_short=float(short["strike"]), k_long=float(long_["strike"]),
                width=width, credit=credit, short_delta=float(short["delta"]),
                s_px=float(s_px), l_px=float(l_px))


# ----------------------------------------------------------------- settlement
def settle_pnl_per_share(S_exp, k_short, k_long, credit):
    """Terminal P&L per share of a call credit spread held to expiration."""
    owe = max(0.0, S_exp - k_short) - max(0.0, S_exp - k_long)   # in [0, width]
    return credit - owe


# ----------------------------------------------------------------- engine
def run_backtest(opt: pd.DataFrame, cfg: SpreadConfig,
                 start=None, end=None, prebuilt=None) -> pd.DataFrame:
    """Serial, non-overlapping backtest: enter a spread, hold to expiration,
    then re-enter on the next trading day. Returns a per-trade ledger.

    `prebuilt` may be the (calls_by_td, spot_by_td, trade_dates) tuple from
    build_day_index() so a parameter sweep pays the 1.5M-row grouping cost once.
    """
    if prebuilt is None:
        calls_by_td, spot_by_td, tds = build_day_index(opt)
    else:
        calls_by_td, spot_by_td, tds = prebuilt
    tds = [t for t in tds if (start is None or t >= start) and (end is None or t <= end)]
    td_set = set(tds)
    exp_underlying = spot_by_td  # settlement uses same EOD underlying stamp

    rows = []
    i = 0
    n = len(tds)
    while i < n:
        td = tds[i]
        day = calls_by_td[td]
        spot = spot_by_td[td]
        exp = pick_expiration(day, cfg.target_dte, cfg.dte_tol)
        if exp is None:
            i += 1
            continue
        chain_exp = day[day["expiration"] == exp]
        sel = select_spread(chain_exp, spot, cfg)
        if sel is None:
            i += 1
            continue

        # settlement underlying on the expiration date (fallback: last known <= exp)
        if exp in exp_underlying:
            S_exp = exp_underlying[exp]
        else:
            prior = [t for t in tds if t <= exp]
            S_exp = exp_underlying[prior[-1]] if prior else np.nan
        if not np.isfinite(S_exp):
            i += 1
            continue

        pnl_share = settle_pnl_per_share(S_exp, sel["k_short"], sel["k_long"], sel["credit"])
        max_loss_share = sel["width"] - sel["credit"]
        rows.append(dict(
            entry_date=td, expiration=exp,
            dte=(pd.Timestamp(exp) - pd.Timestamp(td)).days,
            spot_entry=spot, S_exp=S_exp,
            k_short=sel["k_short"], k_long=sel["k_long"],
            width=sel["width"], width_pct=sel["width"] / spot,
            short_delta=sel["short_delta"], credit=sel["credit"],
            credit_pct_width=sel["credit"] / sel["width"],
            max_loss_share=max_loss_share,
            pnl_share=pnl_share,
            ror=pnl_share / max_loss_share if max_loss_share > 0 else np.nan,
            breach=S_exp > sel["k_short"],
            max_loss_hit=S_exp >= sel["k_long"],
            win=pnl_share > 0,
            move_pct=S_exp / spot - 1.0,
            year=pd.Timestamp(td).year,
        ))

        # advance to the next trading day strictly after expiration
        j = i + 1
        while j < n and tds[j] <= exp:
            j += 1
        i = j if j > i else i + 1

    led = pd.DataFrame(rows)
    return led


if __name__ == "__main__":
    from data_loader import load_options
    opt = load_options(whole_strikes_only=True)
    for dte, name in [(7, "WEEKLY"), (14, "TWO-WEEK"), (30, "MONTHLY")]:
        cfg = SpreadConfig(target_dte=dte, short_rule="otm_step",
                           short_otm_step=1, width_steps=1)
        led = run_backtest(opt, cfg)
        print(f"\n{name}  (short=1st OTM strike, width=1 strike, 20% fills)")
        print(f"  trades={len(led)}  win%={led['win'].mean():.1%}  "
              f"breach%={led['breach'].mean():.1%}  maxloss%={led['max_loss_hit'].mean():.1%}")
        print(f"  avg credit/width={led['credit_pct_width'].mean():.1%}  "
              f"avg RoR/trade={led['ror'].mean():+.1%}  "
              f"sum pnl_share={led['pnl_share'].sum():+.2f}")
