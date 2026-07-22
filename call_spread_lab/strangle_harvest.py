#!/usr/bin/env python3
"""
strangle_harvest.py  --  active long-strangle "volatility harvesting" on SOXL.

The idea (user's): SOXL's realized moves are huge and its options are chronically
cheap (negative VRP, measured in signals.py), so hold BOTH a long OTM call and a
long OTM put, and actively HARVEST whichever leg the move inflates -- rather than
letting the spike decay to expiration (probe_strangle.py showed the best leg
peaks >=+100% intra-life 75% of the time, yet buy-&-hold-to-expiry has a -43%
median).

Rules implemented (documented interpretation; all parameters are configurable):
  * ENTRY: buy a call `dist` above spot and a put `dist` below (nearest whole
    strikes), at `dte_target` days.
  * HARVEST: any open leg whose mark (sell-side, 20% fill) is up >= `take` on the
    premium paid is sold and the gain realized.
  * ONE UNIFIED RE-ENTRY RULE reproduces every behavior described: each side must
    always have a leg within `rearm_far` (30%) of spot; if it doesn't, buy a fresh
    leg on that side at `dist`. This (a) re-arms the winning side right after a
    harvest, (b) rolls a side whose leg expired, and (c) adds a NEW floor/ceiling
    when price runs >30% past the existing leg -- while the old far leg is LEFT
    ALONE as a deep tail hedge until it expires (or spikes and is harvested).
  * SIZING: "invest ~100%, reinvest". Each leg is bought with `leg_frac` of current
    equity, capped by available cash (a real cash account -- ladders/re-arms are
    funded by harvested cash).

Everything is priced on DAILY EOD marks with the 20% fill rule (buy=ask-0.2*spr,
sell=bid+0.2*spr); there are no intraday option quotes in the data.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from verticals import build_index, buy_fill, sell_fill, valid_quote
from bs import bs_call, bs_put

CONTRACT = 100.0


@dataclass
class HConfig:
    dte_target: int = 90
    dte_tol: int = 20
    dist: float = 0.10          # strike distance from spot for fresh legs
    take: float = 0.50          # harvest when a leg is up >= this on its premium
    rearm_far: float = 0.30     # a side needs a leg within this % of spot
    leg_frac: float = 0.50      # premium budget per leg as fraction of equity
    cap0: float = 100_000.0
    max_legs: int = 30
    real_exit: str = "limit"    # real-hi harvest fill: "limit" (fill at the +take%
                                # threshold, realistic for a limit order) or "high"
                                # (sell at the intraday high -- optimistic upper bound)
    harvest_mode: str = "threshold"  # "threshold" (sell at +take%) or "trailing"
    arm_pct: float = 0.50       # trailing: arm the stop once the leg is up this much
    trail_pct: float = 0.30     # trailing: exit when the leg falls this far off its peak


def build_hilo(fm):
    """{trade_date -> (day_high, day_low)} of the underlying from 5-min bars."""
    g = fm.groupby("date").agg(high=("High", "max"), low=("Low", "min"))
    return {d: (float(r.high), float(r.low)) for d, r in g.iterrows()}


def build_iv_key(opt):
    """{(trade_date,right,expiration,strike) -> implied_vol} for intraday BS marks."""
    return {(td, r, e, k): iv for td, r, e, k, iv in
            zip(opt["trade_date"], opt["right"], opt["expiration"],
                opt["strike"], opt["implied_vol"]) if iv == iv and iv > 0}


def compact_index(idx):
    """Precompute pandas-free lookup tables once so the daily loop is pure dicts:
       exps_by[(td,right)]   -> (exp_array, dte_array)
       strikes_by[(td,right,exp)] -> sorted strike array
    """
    chain_by_td, spot_by_td, quote_by_key, tds = idx
    exps_by, strikes_by = {}, {}
    for td, day in chain_by_td.items():
        for right in ("CALL", "PUT"):
            sub = day[day["right"] == right]
            if len(sub) == 0:
                continue
            ex = sub[["expiration", "dte"]].drop_duplicates()
            exps_by[(td, right)] = (ex["expiration"].to_numpy(), ex["dte"].to_numpy())
            for exp, g in sub.groupby("expiration"):
                strikes_by[(td, right, exp)] = np.sort(g["strike"].to_numpy())
    return exps_by, strikes_by


def _pick_exp(exps_by, td, right, dte_target, tol):
    got = exps_by.get((td, right))
    if got is None:
        return None
    exp_arr, dte_arr = got
    m = (dte_arr >= dte_target - tol) & (dte_arr <= dte_target + tol)
    if not m.any():
        return None
    idx = np.where(m)[0]
    return exp_arr[idx[np.argmin(np.abs(dte_arr[idx] - dte_target))]]


def _open_leg(exps_by, strikes_by, quote_by_key, td, spot, right, cfg, cash, equity):
    exp = _pick_exp(exps_by, td, right, cfg.dte_target, cfg.dte_tol)
    if exp is None:
        return None
    strikes = strikes_by.get((td, right, exp))
    if strikes is None or len(strikes) == 0:
        return None
    target = spot * (1 + cfg.dist) if right == "CALL" else spot * (1 - cfg.dist)
    k = float(strikes[int(np.argmin(np.abs(strikes - target)))])
    q = quote_by_key.get((td, right, exp, k))
    if not q or not valid_quote(*q):
        return None
    cost = buy_fill(*q)
    if cost <= 0:
        return None
    budget = cfg.leg_frac * equity
    n = int(min(budget // (cost * CONTRACT), cash // (cost * CONTRACT)))
    if n < 1:
        return None
    return dict(right=right, strike=k, exp=exp, entry_date=td,
                entry_cost=cost, n=n, last_mark=cost, spend=n * cost * CONTRACT)


def _equity(cash, legs):
    return cash + sum(l["n"] * l["last_mark"] * CONTRACT for l in legs)


def simulate(idx, cfg: HConfig, compact=None, intraday=None, regime_sides=None,
             real_hi=None, real_hilo=None):
    """real_hi = {(td,right,exp,strike) -> option's REAL 5-min intraday high that
    day}; when present for a leg it is the PREFERRED harvest signal (exit at
    high*(1-slip)), ahead of the BS model, ahead of the EOD quote.

    real_hilo = {(td,right,exp,strike) -> (day_high, day_low)} enables the TRAILING
    stop (cfg.harvest_mode='trailing'): once a leg is up >= arm_pct, ratchet a peak
    on the daily highs and exit when the daily low falls trail_pct below that peak,
    filling at the stop level (peak*(1-trail_pct))*(1-slip). The stop is checked
    against the peak established through PRIOR days (today's high updates the peak
    only after the check), so there is no same-day high/low ordering assumption."""
    """intraday = (hilo_by_td, iv_by_key, slip) enables modeled intraday harvests:
    a leg is harvested if its Black-Scholes value at the day's 5-min high (calls)
    or low (puts), using the contract's own prior-EOD IV, clears the take
    threshold -- exiting at that modeled price minus `slip`. Falls back to the EOD
    real-quote harvest on days without 5-min data.

    regime_sides = {td -> frozenset of rights to MAINTAIN that day}. A side dropped
    from the set is liquidated at the EOD mark and not re-armed (the vol-regime
    rotation). Default None = always maintain both sides (plain strangle)."""
    chain_by_td, spot_by_td, quote_by_key, tds = idx
    exps_by, strikes_by = compact if compact is not None else compact_index(idx)
    hilo_by_td, iv_by_key, slip = intraday if intraday is not None else (None, None, 0.0)
    cash = cfg.cap0
    legs, log, eq, dates = [], [], [], []
    peak_deploy = 0.0

    for td in tds:
        spot = spot_by_td[td]

        # 1. refresh marks from today's quotes (carry last mark if unquoted)
        for l in legs:
            q = quote_by_key.get((td, l["right"], l["exp"], l["strike"]))
            if q and valid_quote(*q):
                l["last_mark"] = sell_fill(*q)

        # 2. settle expirations at intrinsic
        keep = []
        for l in legs:
            if l["exp"] <= td:
                intr = (max(0.0, spot - l["strike"]) if l["right"] == "CALL"
                        else max(0.0, l["strike"] - spot))
                cash += l["n"] * intr * CONTRACT
                log.append(dict(date=td, action="expire", right=l["right"],
                                strike=l["strike"], exp=l["exp"], n=l["n"], px=intr,
                                leg_ret=intr / l["entry_cost"] - 1,
                                held_days=(pd.Timestamp(td) - pd.Timestamp(l["entry_date"])).days))
            else:
                keep.append(l)
        legs = keep

        # 3. harvest
        keep = []
        if cfg.harvest_mode == "trailing" and real_hilo is not None:
            # --- TRAILING STOP: let winners run, exit on a pullback off the peak ---
            for l in legs:
                hd = (pd.Timestamp(td) - pd.Timestamp(l["entry_date"])).days
                harvested = False
                hl = real_hilo.get((td, l["right"], l["exp"], l["strike"]))
                if hl is not None:
                    ohi, olo = hl
                    peak = l.get("peak", l["entry_cost"])
                    # check the stop against the peak from PRIOR days first
                    if l.get("armed") and olo <= peak * (1 - cfg.trail_pct):
                        px = peak * (1 - cfg.trail_pct) * (1 - slip)
                        cash += l["n"] * px * CONTRACT
                        log.append(dict(date=td, action="harvest_trail", right=l["right"],
                                        strike=l["strike"], exp=l["exp"], n=l["n"], px=px,
                                        leg_ret=px / l["entry_cost"] - 1, held_days=hd))
                        harvested = True
                    else:                       # then ratchet the peak / arm with today's high
                        if ohi > peak:
                            l["peak"] = ohi
                        if not l.get("armed") and ohi / l["entry_cost"] - 1 >= cfg.arm_pct:
                            l["armed"] = True
                if not harvested:
                    keep.append(l)
            legs = keep
        else:
          for l in legs:
            hd = (pd.Timestamp(td) - pd.Timestamp(l["entry_date"])).days
            harvested = False
            if real_hi is not None:
                rh = real_hi.get((td, l["right"], l["exp"], l["strike"]))
                if rh is not None and rh / l["entry_cost"] - 1 >= cfg.take:
                    # "sell when up +take%" is a LIMIT order -> it fills at the
                    # threshold when the intraday high reaches it, NOT at the high.
                    # "high" mode is the optimistic upper bound (perfect timing).
                    px = (rh if cfg.real_exit == "high"
                          else l["entry_cost"] * (1 + cfg.take)) * (1 - slip)
                    cash += l["n"] * px * CONTRACT
                    log.append(dict(date=td, action="harvest_real", right=l["right"],
                                    strike=l["strike"], exp=l["exp"], n=l["n"], px=px,
                                    leg_ret=px / l["entry_cost"] - 1, held_days=hd))
                    harvested = True
            if not harvested and hilo_by_td is not None and td in hilo_by_td and l.get("iv_ref", 0) > 0:
                hi, lo = hilo_by_td[td]
                T = max((pd.Timestamp(l["exp"]) - pd.Timestamp(td)).days, 0) / 365.0
                S_ext = hi if l["right"] == "CALL" else lo
                peak = (bs_call(S_ext, l["strike"], T, l["iv_ref"]) if l["right"] == "CALL"
                        else bs_put(S_ext, l["strike"], T, l["iv_ref"]))
                if peak / l["entry_cost"] - 1 >= cfg.take:
                    px = peak * (1 - slip)
                    cash += l["n"] * px * CONTRACT
                    log.append(dict(date=td, action="harvest_intraday", right=l["right"],
                                    strike=l["strike"], exp=l["exp"], n=l["n"], px=px,
                                    leg_ret=px / l["entry_cost"] - 1, held_days=hd))
                    harvested = True
            if not harvested:
                q = quote_by_key.get((td, l["right"], l["exp"], l["strike"]))
                if q and valid_quote(*q) and (l["last_mark"] / l["entry_cost"] - 1) >= cfg.take:
                    px = sell_fill(*q)
                    cash += l["n"] * px * CONTRACT
                    log.append(dict(date=td, action="harvest", right=l["right"],
                                    strike=l["strike"], exp=l["exp"], n=l["n"], px=px,
                                    leg_ret=px / l["entry_cost"] - 1, held_days=hd))
                    harvested = True
            if not harvested:
                keep.append(l)
        legs = keep

        # 3b. rotation: liquidate legs on a side the regime no longer maintains
        maintain = regime_sides.get(td, frozenset({"CALL", "PUT"})) if regime_sides else None
        if maintain is not None:
            keep = []
            for l in legs:
                q = quote_by_key.get((td, l["right"], l["exp"], l["strike"]))
                if l["right"] not in maintain and q and valid_quote(*q):
                    cash += l["n"] * sell_fill(*q) * CONTRACT
                    log.append(dict(date=td, action="rotate_out", right=l["right"],
                                    strike=l["strike"], exp=l["exp"], n=l["n"],
                                    px=sell_fill(*q),
                                    leg_ret=sell_fill(*q) / l["entry_cost"] - 1, held_days=hd))
                else:
                    keep.append(l)
            legs = keep

        # 4. unified re-entry: each MAINTAINED side needs a leg within rearm_far of spot
        sides = maintain if maintain is not None else ("CALL", "PUT")
        if len(legs) < cfg.max_legs:
            for right in sides:
                has_near = any(l["right"] == right and abs(l["strike"] / spot - 1) <= cfg.rearm_far
                               for l in legs)
                if not has_near:
                    nl = _open_leg(exps_by, strikes_by, quote_by_key, td, spot, right,
                                   cfg, cash, _equity(cash, legs))
                    if nl and nl["spend"] <= cash:
                        cash -= nl["spend"]
                        log.append(dict(date=td, action="open", right=right,
                                        strike=nl["strike"], exp=nl["exp"], n=nl["n"], px=nl["entry_cost"],
                                        leg_ret=0.0, held_days=0))
                        legs.append(nl)

        # 5. track each leg's IV (today's EOD) so tomorrow's intraday BS uses prior-day IV
        if iv_by_key is not None:
            for l in legs:
                iv = iv_by_key.get((td, l["right"], l["exp"], l["strike"]))
                if iv is not None and iv > 0:
                    l["iv_ref"] = iv

        e = _equity(cash, legs)
        peak_deploy = max(peak_deploy, 1 - cash / e if e > 0 else 0)
        eq.append(e); dates.append(td)

    return dict(dates=dates, equity=np.array(eq), log=pd.DataFrame(log),
                end_legs=legs, end_cash=cash, peak_deploy=peak_deploy)


def stats(res, cfg: HConfig):
    eq = res["equity"]; cap0 = cfg.cap0
    if len(eq) == 0:
        return {}
    peak = np.maximum.accumulate(np.concatenate([[cap0], eq]))
    dd = (np.concatenate([[cap0], eq]) / peak - 1).min()
    yrs = (pd.Timestamp(res["dates"][-1]) - pd.Timestamp(res["dates"][0])).days / 365.25
    cagr = (eq[-1] / cap0) ** (1 / yrs) - 1 if eq[-1] > 0 and yrs > 0 else np.nan
    log = res["log"]
    harv = log[log["action"] == "harvest"] if len(log) else log
    return dict(end_equity=float(eq[-1]), total_return=float(eq[-1] / cap0 - 1),
                cagr=float(cagr), max_dd=float(dd),
                n_harvests=int(len(harv)),
                harvest_mean_ret=float(harv["leg_ret"].mean()) if len(harv) else np.nan,
                peak_deploy=float(res["peak_deploy"]))


if __name__ == "__main__":
    import time
    from data_loader import load_options
    opt = load_options(whole_strikes_only=True)
    idx = build_index(opt)
    compact = compact_index(idx)
    for take in (0.05, 0.5, 1.0, 999):
        cfg = HConfig(dte_target=90, dist=0.10, take=take)
        t0 = time.time()
        r = simulate(idx, cfg, compact)
        s = stats(r, cfg)
        print(f"  ({time.time()-t0:.1f}s)", end=" ")
        lbl = "no-harvest" if take == 999 else f"take+{take:.0%}"
        print(f"90DTE 10% dist {lbl:12s}: end ${s['end_equity']:>12,.0f}  "
              f"CAGR {s['cagr']:+.0%}  maxDD {s['max_dd']:+.0%}  "
              f"harvests {s['n_harvests']:>4d}  peakDeploy {s['peak_deploy']:.0%}")
