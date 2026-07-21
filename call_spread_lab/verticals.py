#!/usr/bin/env python3
"""
verticals.py  --  general defined-risk VERTICAL spread engine for SOXL.

Supersedes backtest.py's call-only logic with a unified legs-based model that
covers the three structures this study needs:

  bear_call  (credit) : SELL call just-OTM, BUY higher call.  profits if SOXL falls/flat.
  bull_put   (credit) : SELL put  just-OTM, BUY lower  put.   profits if SOXL rises/flat.
  bull_call  (debit)  : BUY  call just-OTM, SELL higher call. profits if SOXL rises.

Same data conventions as the rest of the lab (measured in profile_data.py):
  * whole-number strikes only; daily EOD marks (no intraday option quotes);
  * 20% spread fill rule: sell=bid+0.2(ask-bid), buy=ask-0.2(ask-bid);
  * settlement at intrinsic on the expiration-day underlying close.

P&L is computed from explicit legs so every structure uses one code path:
    per-share P&L = net_entry_cash + sum_i qty_i * intrinsic_i(S_exp)
where qty=+1 for a bought leg, -1 for a sold leg, and
    net_entry_cash = -sum_i qty_i * fill_i   (credit>0, debit<0).

An OPTIONAL daily stop can close the spread early at that day's real EOD mark
(used by run_verticals.py to test "the trade is going against us -> exit").

This engine also reproduces bear_call, so its agreement with the committed
backtest.py results is itself a cross-check (see verify_verticals.py).
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


def sell_fill(bid, ask):
    return bid + 0.20 * (ask - bid)


def buy_fill(bid, ask):
    return ask - 0.20 * (ask - bid)


def valid_quote(bid, ask):
    return (bid > 0) & (ask >= bid)


def call_intr(S, K):
    return max(0.0, S - K)


def put_intr(S, K):
    return max(0.0, K - S)


# structure -> (option right, is_credit, primary leg short?, side, single-leg?)
STRUCTURES = {
    "bear_call": dict(right="CALL", credit=True,  primary_short=True,  side="above", single=False),
    "bull_put":  dict(right="PUT",  credit=True,  primary_short=True,  side="below", single=False),
    "bull_call": dict(right="CALL", credit=False, primary_short=False, side="above", single=False),
    "long_call": dict(right="CALL", credit=False, primary_short=False, side="above", single=True),
    "long_put":  dict(right="PUT",  credit=False, primary_short=False, side="below", single=True),
}


@dataclass
class VConfig:
    structure: str = "bear_call"
    target_dte: int = 7
    dte_tol: int = 4
    primary_rule: str = "otm_step"     # "otm_step" | "delta"
    primary_otm_step: int = 1          # k-th strike OTM for the primary leg
    primary_delta: float = 0.30        # |delta| target when primary_rule=="delta"
    width_steps: int = 1               # protective leg is width_steps strikes away
    fill: str = "spread20"             # "spread20" | "mid"
    stop: dict = field(default=None)   # optional daily stop (see run_verticals)


# ----------------------------------------------------------------- indexing
def build_index(opt: pd.DataFrame):
    """Per trade_date chains for BOTH rights + a quote lookup for interim marking."""
    v = opt[valid_quote(opt["bid"], opt["ask"])].copy()
    chain_by_td, spot_by_td, quote_by_key = {}, {}, {}
    for td, g in v.groupby("trade_date"):
        chain_by_td[td] = g[["strike", "right", "bid", "ask", "delta",
                             "expiration", "dte"]].reset_index(drop=True)
        spot_by_td[td] = float(g["underlying_price"].iloc[0])
        for r in g.itertuples(index=False):
            quote_by_key[(td, r.right, r.expiration, r.strike)] = (r.bid, r.ask)
    return chain_by_td, spot_by_td, quote_by_key, sorted(chain_by_td.keys())


def pick_expiration(day_chain, target_dte, tol):
    exps = day_chain[["expiration", "dte"]].drop_duplicates()
    exps = exps[(exps["dte"] >= target_dte - tol) & (exps["dte"] <= target_dte + tol)]
    if exps.empty:
        return None
    exps = exps.assign(err=(exps["dte"] - target_dte).abs())
    return exps.sort_values(["err", "dte"]).iloc[0]["expiration"]


def _leg_fill(bid, ask, buy, fill):
    if fill == "mid":
        return (bid + ask) / 2
    return buy_fill(bid, ask) if buy else sell_fill(bid, ask)


def select_vertical(chain_exp: pd.DataFrame, spot: float, cfg: VConfig):
    """Choose the two strikes for `cfg.structure` and price the spread."""
    meta = STRUCTURES[cfg.structure]
    ch = chain_exp[chain_exp["right"] == meta["right"]].sort_values("strike")
    ch = ch.reset_index(drop=True)
    strikes = ch["strike"].values
    if len(strikes) < 2:
        return None

    # -- primary leg (anchored to spot). otm_step counts from the money:
    #    step 1 = first strike OTM; step 0 = first strike at/through the money
    #    (ATM/ITM); negative = deeper ITM. Lets debit calls anchor ITM.
    if cfg.primary_rule == "otm_step":
        if meta["side"] == "above":
            above = np.where(strikes > spot)[0]
            if len(above) == 0:
                return None
            pi = above[0] + (cfg.primary_otm_step - 1)
        else:  # below (puts)
            below = np.where(strikes < spot)[0]
            if len(below) == 0:
                return None
            pi = below[-1] - (cfg.primary_otm_step - 1)
    else:  # delta
        pi = int(np.argmin(np.abs(np.abs(ch["delta"].values) - cfg.primary_delta)))
    if pi < 0 or pi >= len(strikes):
        return None

    pr = ch.iloc[pi]
    if not valid_quote(pr["bid"], pr["ask"]):
        return None
    primary_qty = -1 if meta["primary_short"] else +1

    # -- single-leg structures (pure long call / put) ---------------------
    if meta["single"]:
        fillp = _leg_fill(pr["bid"], pr["ask"], primary_qty > 0, cfg.fill)
        legs = [(meta["right"], float(pr["strike"]), primary_qty, fillp)]
        net_cash = -primary_qty * fillp                    # debit (<0) for a long
        max_loss = -net_cash                               # premium paid
        if max_loss <= 0:
            return None
        return dict(legs=legs, net_cash=net_cash, k_lo=float(pr["strike"]),
                    k_hi=float(pr["strike"]), width=np.nan, max_loss=max_loss,
                    k_primary=float(pr["strike"]), primary_delta=float(pr["delta"]))

    # -- protective leg = width_steps strikes further OTM -----------------
    oi = pi + cfg.width_steps if meta["side"] == "above" else pi - cfg.width_steps
    if oi < 0 or oi >= len(strikes):
        return None
    ot = ch.iloc[oi]
    if not valid_quote(ot["bid"], ot["ask"]):
        return None

    legs = [(meta["right"], float(pr["strike"]), primary_qty,
             _leg_fill(pr["bid"], pr["ask"], primary_qty > 0, cfg.fill)),
            (meta["right"], float(ot["strike"]), -primary_qty,
             _leg_fill(ot["bid"], ot["ask"], -primary_qty > 0, cfg.fill))]

    net_cash = -sum(q * f for _, _, q, f in legs)          # credit>0 / debit<0
    k_lo, k_hi = sorted([legs[0][1], legs[1][1]])
    width = k_hi - k_lo
    if width <= 0:
        return None
    if meta["credit"] and net_cash <= 0:
        return None
    if (not meta["credit"]) and net_cash >= 0:
        return None
    max_loss = (width - net_cash) if meta["credit"] else (-net_cash)
    if max_loss <= 0:
        return None
    return dict(legs=legs, net_cash=net_cash, k_lo=k_lo, k_hi=k_hi,
                width=width, max_loss=max_loss, k_primary=float(pr["strike"]),
                primary_delta=float(pr["delta"]))


def _position_value(legs, S):
    val = 0.0
    for right, K, qty, _fill in legs:
        intr = call_intr(S, K) if right == "CALL" else put_intr(S, K)
        val += qty * intr
    return val


def _mark_exit(legs, quote_by_key, td, exp, fill):
    """Cost to CLOSE the position at td's EOD marks (buy back shorts, sell longs).
    Returns the closing cash flow (paid<0 / received>0) or None if a leg is unquoted."""
    cash = 0.0
    for right, K, qty, _entry in legs:
        q = quote_by_key.get((td, right, exp, K))
        if q is None:
            return None
        bid, ask = q
        if not valid_quote(bid, ask):
            return None
        if qty < 0:      # short -> buy to close (pay ask-side)
            cash -= buy_fill(bid, ask)
        else:            # long -> sell to close (receive bid-side)
            cash += sell_fill(bid, ask)
    return cash


# ----------------------------------------------------------------- runner
def run(opt: pd.DataFrame, cfg: VConfig, prebuilt=None, start=None, end=None):
    chain_by_td, spot_by_td, quote_by_key, tds = prebuilt or build_index(opt)
    tds = [t for t in tds if (start is None or t >= start) and (end is None or t <= end)]
    n = len(tds)
    rows, i = [], 0
    while i < n:
        td = tds[i]
        day, spot = chain_by_td[td], spot_by_td[td]
        exp = pick_expiration(day, cfg.target_dte, cfg.dte_tol)
        if exp is None:
            i += 1; continue
        sel = select_vertical(day[day["expiration"] == exp], spot, cfg)
        if sel is None:
            i += 1; continue

        # walk the hold day-by-day: optional stop, else settle at expiration
        exit_td, exit_S, exit_kind, pnl_share = None, None, "expiry", None
        j = i + 1
        while j < n and tds[j] <= exp:
            d = tds[j]
            S = spot_by_td[d]
            if cfg.stop and _stop_hit(cfg, sel, spot, S):
                close = _mark_exit(sel["legs"], quote_by_key, d, exp, cfg.fill)
                if close is not None:
                    pnl_share = sel["net_cash"] + close
                    exit_td, exit_S, exit_kind = d, S, "stop"
                    break
            j += 1

        if pnl_share is None:  # held to expiration -> intrinsic settle
            if exp in spot_by_td:
                S_exp = spot_by_td[exp]
            else:
                prior = [t for t in tds if t <= exp]
                S_exp = spot_by_td[prior[-1]] if prior else np.nan
            if not np.isfinite(S_exp):
                i += 1; continue
            pnl_share = sel["net_cash"] + _position_value(sel["legs"], S_exp)
            exit_td, exit_S = exp, S_exp

        rows.append(dict(
            structure=cfg.structure, entry_date=td, expiration=exp,
            dte=(pd.Timestamp(exp) - pd.Timestamp(td)).days,
            spot_entry=spot, exit_date=exit_td, S_exit=exit_S, exit_kind=exit_kind,
            k_lo=sel["k_lo"], k_hi=sel["k_hi"], width=sel["width"],
            width_pct=sel["width"] / spot, primary_delta=sel["primary_delta"],
            net=sel["net_cash"], net_pct_width=sel["net_cash"] / sel["width"],
            max_loss_share=sel["max_loss"], pnl_share=pnl_share,
            ror=pnl_share / sel["max_loss"] if sel["max_loss"] > 0 else np.nan,
            win=pnl_share > 0, move_pct=exit_S / spot - 1.0,
            year=pd.Timestamp(td).year))

        j = i + 1
        while j < n and tds[j] <= (exit_td or exp):
            j += 1
        i = j if j > i else i + 1
    return pd.DataFrame(rows)


def _stop_hit(cfg, sel, spot_entry, S_now):
    """Evaluate a daily stop against the underlying path (EOD)."""
    rule = cfg.stop
    kind = rule.get("type")
    if kind == "breach_primary":
        # credit spreads: primary (short) strike breached
        if cfg.structure == "bear_call":
            return S_now >= sel["k_primary"]
        if cfg.structure == "bull_put":
            return S_now <= sel["k_primary"]
        return False
    if kind == "move_pct":
        thr = rule["thresh"]
        mv = S_now / spot_entry - 1.0
        # exit when moving in the LOSS direction by thr
        if cfg.structure in ("bear_call",):      # loses on up-moves
            return mv >= thr
        if cfg.structure in ("bull_put", "bull_call"):  # lose on down-moves
            return mv <= -thr
    return False


if __name__ == "__main__":
    from data_loader import load_options
    opt = load_options(whole_strikes_only=True)
    idx = build_index(opt)
    for stru in ("bear_call", "bull_put", "bull_call"):
        cfg = VConfig(structure=stru, target_dte=7, primary_rule="otm_step",
                      primary_otm_step=1, width_steps=1)
        led = run(opt, cfg, prebuilt=idx)
        print(f"{stru:10s} weekly 1-OTM w1: trades={len(led)} win={led['win'].mean():.1%} "
              f"mean_ror={led['ror'].mean():+.1%} total_ror={led['ror'].sum():+.1f} "
              f"net/width={led['net_pct_width'].mean():+.0%}")
