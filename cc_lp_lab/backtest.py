"""Covered call + long-dated protective put on SOXL -- literal rule backtest.

RULES (as specified)
  * Act at the 10:00 ET 5-min bar of the first trading day of each week
    ("Monday", or the nearest session when Monday is a holiday).
  * Hold SOXL. Sell a weekly call TWO LISTED STRIKES out of the money,
    expiring that week's Friday (Thursday in holiday weeks).
  * Buy a proportionate number of puts ~3 months out, TWO LISTED STRIKES OTM
    on the put side. Leave the put alone until its expiry.
  * If the call expires worthless, rewrite NEXT week at the SAME strike.
    If the call is assigned, rebuy the shares the next Monday and write a
    fresh two-strikes-OTM call.
  * If the put is in the money at its expiry, exercise it (shares delivered at
    the put strike); rebuy shares and a new put the next Monday.
  * Start $100,000, reinvest weekly (position size compounds with equity).
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import data, pricing

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
START, END = pd.Timestamp("2022-01-03"), pd.Timestamp("2026-07-02")
CARRY = 0.04
ENTRY_MIN = 600            # 10:00 ET


def standard_strikes(arr):
    """Drop split-adjusted odd strikes (e.g. 37.67 = pre-2021 565/15)."""
    a = np.asarray(arr, dtype=float)
    return np.sort(a[np.abs(a * 2 - np.round(a * 2)) < 1e-6])


class Book:
    def __init__(self, cash):
        self.cash = cash
        self.shares = 0
        self.call = None      # dict(exp,K,n) short
        self.put = None       # dict(exp,K,n) long


def run(n_otm=2, put_dte=91, cost_per_contract=0.0, slip_call=0.0, slip_put=0.0,
        share_cost=0.0, cash_rate=0.0, start_cash=100_000.0, sticky=True,
        freeze_put_qty=False, use_put=True, use_call=True,
        early_assign_pct=0.0, strike_mode="count", call_delta=0.20, call_pct=0.05,
        put_ratio=1.0, n_otm_put=None, start=None, end=None, verbose=False):
    """slip_call / slip_put are RELATIVE half-spreads: we sell at px*(1-s) and
    buy at px*(1+s). Measured EOD medians are 0.055 (weekly 2-OTM call) and
    0.019 (~90d 2-OTM put) -- see validate_pricing.py."""
    e, tr = data.eod_chain(), data.intraday_trades()
    spot10 = data.spot_at(ENTRY_MIN)
    close = data.daily_close()
    P = pricing.Pricer(e, tr, carry=CARRY)

    days = data.trading_days()
    days = days[(days >= (start or START)) & (days <= (end or END))]
    iso = days.isocalendar()
    wkkey = pd.Series(list(zip(iso.year, iso.week)), index=days)
    week_start = set(pd.Series(days, index=days).groupby(wkkey.values).first())
    week_end = {k: v for k, v in pd.Series(days, index=days).groupby(wkkey.values).last().items()}
    day_week = dict(zip(days, wkkey.values))

    # chain index for fast per-day lookups
    ch_by_day = {d: g for d, g in e[e.date.isin(days)].groupby("date")}

    b = Book(start_cash)
    sticky_K = None
    ledger, equity = [], []
    basis = 0.0                      # average cost per share
    pnl = dict(shares=0.0, calls=0.0, puts=0.0)

    def buy_shares(q, px):
        nonlocal basis
        basis = (basis * b.shares + q * px) / (b.shares + q) if (b.shares + q) else 0.0
        b.shares += q
        b.cash -= q * px + q * share_cost
        pnl["shares"] -= q * share_cost

    def sell_shares(q, px):
        pnl["shares"] += q * (px - basis) - q * share_cost
        b.shares -= q
        b.cash += q * px - q * share_cost

    def mark(d, leg, S):
        """Intraday (10:00) mark -- used for sizing and for trading decisions."""
        if leg is None: return 0.0
        px, src = P.mark(d, leg["exp"], leg["right"], leg["K"], S, ENTRY_MIN)
        if px is None:
            px = max(0.0, (S - leg["K"]) if leg["right"] == "C" else (leg["K"] - S))
        return px

    def mark_close(d, leg, S):
        """End-of-day mark -- used only for the equity curve / drawdown."""
        if leg is None: return 0.0
        return P.mark_eod(d, leg["exp"], leg["right"], leg["K"], S)

    def fill(px, side, right="C"):
        """side +1 = we buy (pay up), -1 = we sell (receive less)."""
        s = slip_call if right == "C" else slip_put
        return max(px * (1 + side * s), 0.0)

    for d in days:
        S10 = float(spot10.loc[d, "px"])
        ch = ch_by_day.get(d)

        # ---------------- Monday 10:00 routine ----------------
        if d in week_start and ch is not None:
            wk_last = week_end[day_week[d]]
            # weekly call expiration: latest listed expiry inside this week, after today
            exps = pd.to_datetime(sorted(ch.exp.unique()))
            wk_exps = [x for x in exps if d < x <= wk_last]
            cexp = max(wk_exps) if wk_exps else None

            # -- 1. buy a new ~3M put if we have none --
            need_put = use_put and b.put is None
            put_px = np.nan; pexp = pK = None
            if need_put:
                pc = ch[ch.right == "P"].groupby("exp")["strike"].nunique()
                pc = pc[pc >= 10]
                cand = pd.DataFrame({"exp": pc.index, "dte": (pc.index - d).days})
                cand = cand[cand.dte.between(max(14, put_dte // 2), min(500, put_dte * 2 + 30))]
                if len(cand):
                    pexp = cand.iloc[(cand.dte - put_dte).abs().argsort()].iloc[0]["exp"]
                    ks = standard_strikes(ch[(ch.exp == pexp) & (ch.right == "P")].strike.unique())
                    below = ks[ks < S10][::-1]
                    n_p = n_otm_put if n_otm_put is not None else n_otm
                    if len(below) >= n_p:
                        pK = float(below[n_p - 1])
                        px, src = P.mark(d, pexp, "P", pK, S10, ENTRY_MIN)
                        if px is not None: put_px = fill(px, +1, "P")
            live_put_px = mark(d, b.put, S10) if b.put else np.nan
            unit_put = put_px if need_put else live_put_px
            if not np.isfinite(unit_put): unit_put = 0.0

            # -- 2. target lots: reinvest all liquid equity --
            avail = b.cash + b.shares * S10 + (b.put["n"] * 100 * live_put_px if b.put else 0.0)
            unit = 100 * S10 + put_ratio * 100 * unit_put + 2 * cost_per_contract
            L = int(max(0, np.floor(avail / unit))) if unit > 0 else 0

            # -- 3. trade shares to L lots --
            d_sh = L * 100 - b.shares
            if d_sh > 0:
                buy_shares(d_sh, S10)
                ledger.append(dict(date=d, act="BUY_SHARES", qty=d_sh, px=S10,
                                   spot=S10, cash=b.cash))
            elif d_sh < 0:
                sell_shares(-d_sh, S10)
                ledger.append(dict(date=d, act="SELL_SHARES", qty=d_sh, px=S10,
                                   spot=S10, cash=b.cash))
            # -- 4. trade puts to L --
            n_put_tgt = int(round(L * put_ratio))
            if L > 0 and put_ratio > 0: n_put_tgt = max(1, n_put_tgt)
            if need_put and n_put_tgt > 0 and pK is not None and np.isfinite(put_px):
                b.put = dict(exp=pexp, K=pK, n=n_put_tgt, right="P", cost=put_px)
                b.cash -= n_put_tgt * 100 * put_px + n_put_tgt * cost_per_contract
                pnl["puts"] -= n_put_tgt * 100 * put_px + n_put_tgt * cost_per_contract
                ledger.append(dict(date=d, act="BUY_PUT", qty=n_put_tgt, K=pK, exp=pexp,
                                   px=put_px, dte=(pexp - d).days, spot=S10,
                                   otm_pct=100*(S10 - pK)/S10, cash=b.cash))
            elif (b.put is not None and n_put_tgt != b.put["n"] and np.isfinite(live_put_px)
                  and not freeze_put_qty):
                dn = n_put_tgt - b.put["n"]
                _px = fill(live_put_px, +1 if dn > 0 else -1, "P")
                b.cash -= dn * 100 * _px + abs(dn) * cost_per_contract
                pnl["puts"] -= dn * 100 * _px + abs(dn) * cost_per_contract
                b.put["n"] = n_put_tgt
                ledger.append(dict(date=d, act="ADD_PUT" if dn > 0 else "TRIM_PUT",
                                   qty=dn, K=b.put["K"], exp=b.put["exp"], px=live_put_px, cash=b.cash))
                if n_put_tgt == 0: b.put = None

            # -- 5. write the weekly call --
            if use_call and L > 0 and cexp is not None:
                cc = ch[(ch.exp == cexp) & (ch.right == "C")]
                ks = standard_strikes(cc.strike.unique())
                above = ks[ks > S10]
                fresh = float(above[n_otm - 1]) if len(above) >= n_otm else None
                if strike_mode == "pct" and len(above):
                    tgt = S10 * (1 + call_pct)
                    fresh = float(above[np.argmin(np.abs(above - tgt))])
                elif strike_mode == "delta" and len(above):
                    dl = cc[cc.strike.isin(above) & cc.delta.notna() & (cc.delta > 0)]
                    if len(dl):
                        fresh = float(dl.iloc[(dl.delta - call_delta).abs().argsort()].iloc[0]["strike"])
                    else:                                   # no delta -> % fallback
                        tgt = S10 * (1 + call_pct)
                        fresh = float(above[np.argmin(np.abs(above - tgt))])
                use_sticky = sticky and sticky_K is not None and b.shares > 0
                K = sticky_K if use_sticky else fresh
                if K is None or K not in set(ks):
                    K, use_sticky = fresh, False
                if K is not None:
                    px, src = P.mark(d, cexp, "C", K, S10, ENTRY_MIN)
                    if px is not None:
                        cpx = fill(px, -1, "C")
                        b.call = dict(exp=cexp, K=K, n=L, right="C", cost=cpx)
                        b.cash += L * 100 * cpx - L * cost_per_contract
                        pnl["calls"] += L * 100 * cpx - L * cost_per_contract
                        sticky_K = K
                        ledger.append(dict(date=d, act="SELL_CALL", qty=L, K=K, exp=cexp,
                                           px=cpx, src=src, spot=S10, dte=(cexp - d).days,
                                           itm_at_write=int(K < S10),
                                           sticky_write=int(use_sticky),
                                           otm_pct=100*(K - S10)/S10, cash=b.cash))

        # ---------------- close: settle expiries ----------------
        C = float(close.loc[d])
        # Early assignment: an American short call is exercised early when its
        # remaining time value falls below the dividend about to be captured.
        # Modelled as a threshold on extrinsic value, in % of spot (SOXL's
        # quarterly dividend runs ~0.25-0.5% of price).
        if (early_assign_pct > 0 and b.call is not None and b.call["exp"] != d
                and C > b.call["K"]):
            mk = mark_close(d, b.call, C)
            if (mk - (C - b.call["K"])) < early_assign_pct * C:
                K, n = b.call["K"], b.call["n"]
                sold = min(b.shares, n * 100)
                sell_shares(sold, K)
                pnl["calls"] -= n * 100 * (C - K)
                pnl["shares"] += sold * (C - K)
                if n * 100 > sold:
                    b.cash -= (n * 100 - sold) * (C - K)
                ledger.append(dict(date=d, act="CALL_EARLY_ASSIGNED", qty=n, K=K, px=C,
                                   spot=C, itm=C - K, cash=b.cash))
                b.call = None
                sticky_K = None

        if b.call is not None and b.call["exp"] == d:
            K, n = b.call["K"], b.call["n"]
            if C > K:                                   # assigned -> shares called away
                sold = min(b.shares, n * 100)
                sell_shares(sold, K)
                pnl["calls"] -= n * 100 * (C - K)
                pnl["shares"] += sold * (C - K)         # short-call intrinsic is the cap,
                if n * 100 > sold:                      # not a share loss; keep legs clean
                    b.cash -= (n * 100 - sold) * (C - K)
                ledger.append(dict(date=d, act="CALL_ASSIGNED", qty=n, K=K, px=C,
                                   spot=C, itm=C - K, cash=b.cash))
                sticky_K = None
            else:
                ledger.append(dict(date=d, act="CALL_EXPIRED", qty=n, K=K, px=C,
                                   spot=C, cash=b.cash))
            b.call = None

        if b.put is not None and b.put["exp"] == d:
            K, n = b.put["K"], b.put["n"]
            if C < K:                                   # exercise -> deliver shares at K
                sold = min(b.shares, n * 100)
                sell_shares(sold, K)
                pnl["puts"] += n * 100 * (K - C)
                pnl["shares"] -= sold * (K - C)         # put payoff is the floor, not share gain
                if n * 100 > sold:
                    b.cash += (n * 100 - sold) * (K - C)
                ledger.append(dict(date=d, act="PUT_EXERCISED", qty=n, K=K, px=C,
                                   spot=C, cash=b.cash))
                sticky_K = None
            else:
                ledger.append(dict(date=d, act="PUT_EXPIRED", qty=n, K=K, px=C,
                                   spot=C, cash=b.cash))
            b.put = None

        if cash_rate and b.cash > 0:
            b.cash *= (1 + cash_rate / 252)

        cv = mark_close(d, b.call, C) if b.call else 0.0
        pv = mark_close(d, b.put, C) if b.put else 0.0
        eq = (b.cash + b.shares * C
              - (b.call["n"] * 100 * cv if b.call else 0)
              + (b.put["n"] * 100 * pv if b.put else 0))
        equity.append(dict(date=d, equity=eq, cash=b.cash, shares=b.shares, spot=C,
                           call_K=b.call["K"] if b.call else np.nan,
                           put_K=b.put["K"] if b.put else np.nan,
                           call_val=cv * (b.call["n"] * 100 if b.call else 0),
                           put_val=pv * (b.put["n"] * 100 if b.put else 0)))

    eqdf = pd.DataFrame(equity).set_index("date")
    led = pd.DataFrame(ledger)
    # unrealised at the end, so the legs reconcile to total equity
    Cl = float(close.loc[days[-1]])
    pnl["shares"] += b.shares * (Cl - basis)
    if b.put is not None:
        pnl["puts"] += b.put["n"] * 100 * P.mark_eod(days[-1], b.put["exp"], "P", b.put["K"], Cl)
    if b.call is not None:
        pnl["calls"] -= b.call["n"] * 100 * P.mark_eod(days[-1], b.call["exp"], "C", b.call["K"], Cl)
    return eqdf, led, dict(marks=P.stats, pnl=pnl)


def stats(eq, label=""):
    e = eq["equity"]
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    tot = e.iloc[-1] / e.iloc[0] - 1
    cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1
    dd = e / e.cummax() - 1
    r = e.pct_change().dropna()
    return dict(label=label, final=e.iloc[-1], total_ret=tot, cagr=cagr,
                maxdd=dd.min(), vol=r.std() * np.sqrt(252),
                sharpe=(r.mean() * 252) / (r.std() * np.sqrt(252) + 1e-12),
                years=yrs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="base")
    ap.add_argument("--n_otm", type=int, default=2)
    ap.add_argument("--put_dte", type=int, default=91)
    ap.add_argument("--cost", type=float, default=0.0)
    ap.add_argument("--slip_call", type=float, default=0.0)
    ap.add_argument("--slip_put", type=float, default=0.0)
    ap.add_argument("--cash_rate", type=float, default=0.0)
    ap.add_argument("--no_sticky", action="store_true")
    a = ap.parse_args()
    eq, led, st = run(n_otm=a.n_otm, put_dte=a.put_dte, cost_per_contract=a.cost,
                      slip_call=a.slip_call, slip_put=a.slip_put,
                      cash_rate=a.cash_rate, sticky=not a.no_sticky)
    os.makedirs(OUT, exist_ok=True)
    eq.to_csv(f"{OUT}/equity_{a.tag}.csv")
    led.to_csv(f"{OUT}/ledger_{a.tag}.csv", index=False)
    s = stats(eq, a.tag)
    print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()})
    print("mark sources:", st)
    print(led.act.value_counts().to_dict())
