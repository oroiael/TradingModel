"""Covered call + long-dated protective put on SOXL — shared engine.

Rules implemented (see ccp_lab/README.md for the full statement):
  * Every Monday 10:00 ET (first trading day of the ISO week if Monday is a
    holiday) mark the underlying at the HIGH of the 10:00 1-minute bar.
  * Write a call expiring that same week. Strike chosen from the tradeable
    universe (whole or .5 strikes only), at or above spot, so that the premium
    collected is as close as possible to TARGET_PCT of the underlying value.
  * Hold a protective put at the listed expiry nearest 90 DTE, struck just out
    of the money (highest valid strike strictly below spot). The put is never
    traded: it is held to expiry and exercised if in the money, then reloaded.
  * $100,000 start, whole shares, reinvested.
"""
import os, sys, math
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ccp_lab", "cache")

try:
    from ccp_lab.compat import load_df, cache_path
except ImportError:                                   # run as a loose script
    sys.path.insert(0, ROOT)
    from ccp_lab.compat import load_df, cache_path

TARGET_PCT   = 0.05     # premium target, as a fraction of underlying value
PUT_DTE      = 90       # protective put tenor
START_CASH   = 100_000.0
CARRY        = 0.04     # r - q, validated against the vendor's own EOD mids
COMMISSION   = 0.65     # $/contract
SHARE_FEE    = 0.005    # $/share
MIN_TICK     = 0.01     # an option cannot trade below a penny

# ------------------------------------------------------------ Black-Scholes
def _ncdf(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))

def bs(S, K, T, vol, right, r=CARRY):
    """Black-Scholes with a single carry term r-q; vectorised over K/vol."""
    S = float(S)
    K = np.asarray(K, dtype=float)
    vol = np.asarray(vol, dtype=float)
    T = max(float(T), 1.0 / (365.0 * 24.0))
    vol = np.clip(vol, 1e-4, 5.0)
    sq = vol * math.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * vol ** 2) * T) / sq
    d2 = d1 - sq
    if right == "CALL":
        return S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)

# ------------------------------------------------------------------ loaders
class Data:
    def __init__(self):
        self.ten = load_df("underlying_1min_1000")
        self.ten["date"] = pd.to_datetime(self.ten["date"])
        self.ten = self.ten.set_index("date").sort_index()

        self.daily = load_df("underlying_daily")
        self.daily["date"] = pd.to_datetime(self.daily["date"])
        self.daily = self.daily.set_index("date").sort_index()

        ch = load_df("chains")
        ch = ch[ch.std_strike & ch.implied_vol.notna() & (ch.implied_vol > 0)]
        self.ch = ch.sort_values(["trade_date", "expiration", "strike"])
        self._by_date = {d: g for d, g in self.ch.groupby("trade_date")}

        # The intraday print cache is an enhancement, not a requirement: without
        # it every option is priced by model instead of by a real 10:00 trade.
        p = cache_path("prints_1000")
        self.p_exact, self.p_near = {}, {}
        try:
            pr = load_df("prints_1000") if p is not None else None
        except Exception as e:
            print(f"warning: intraday print cache unusable ({e.__class__.__name__});"
                  f" pricing every option from the model instead.", file=sys.stderr)
            pr = None
        if pr is not None:
            pr["date"] = pd.to_datetime(pr["date"])
            pr["expiration"] = pd.to_datetime(pr["expiration"])
            pr = pr[pr["close"] > 0]
            mins = (pr.hm.str.slice(0, 2).astype(int) * 60 +
                    pr.hm.str.slice(3, 5).astype(int))
            pr = pr.assign(_d=(mins - 600).abs())
            keys = list(zip(pr.date.values, pr.expiration.values,
                            pr.strike.values, pr.right.values))
            pr = pr.assign(_k=keys)
            ex = pr[pr.hm == "10:00"].drop_duplicates("_k")
            self.p_exact = dict(zip(ex._k, ex["close"].astype(float)))
            nr = pr.sort_values("_d").drop_duplicates("_k")
            self.p_near = dict(zip(nr._k, nr["close"].astype(float)))

        self.sessions = list(self.daily.index)

    # -- underlying -------------------------------------------------------
    def ten_high(self, d):
        r = self.ten.loc[d] if d in self.ten.index else None
        return None if r is None else float(r["h"])

    def close(self, d):
        return float(self.daily.loc[d, "c"]) if d in self.daily.index else None

    def chain(self, d):
        return self._by_date.get(d)

    # -- option marks -----------------------------------------------------
    def print_1000(self, d, exp, strike, right):
        """Real 5-min trade print: exactly 10:00 if it exists, else the nearest
        print inside 09:30-10:30. Returns (price, quality) or (None, None)."""
        k = (np.datetime64(d), np.datetime64(exp), float(strike), right)
        v = self.p_exact.get(k)
        if v is not None:
            return v, "print_1000"
        v = self.p_near.get(k)
        if v is not None:
            return v, "print_near"
        return None, None

    def eod_value(self, chain, exp, strike, right, spot, d):
        """Mark an open leg at the EOD chain mid; fall back to model, then intrinsic."""
        intrinsic = max(spot - strike, 0.0) if right == "CALL" else max(strike - spot, 0.0)
        if chain is None or not len(chain):
            return intrinsic
        g = chain[(chain.expiration == exp) & (chain.right == right)
                  & np.isclose(chain.strike, strike)]
        if len(g):
            m = g.iloc[0]["mid"]
            if pd.notna(m) and m > 0:
                return float(m)
            iv = g.iloc[0]["implied_vol"]
            if pd.notna(iv) and iv > 0:
                T = max((exp - d).days, 0) / 365.0
                return max(float(bs(spot, strike, T, iv, right)), intrinsic)
        return intrinsic

    def mark(self, d, exp, strike, right, spot, iv):
        """10:00 mark: real print first, model repriced to the 10:00 spot second."""
        px, q = self.print_1000(d, exp, strike, right)
        if px is not None and px > 0:
            return px, q
        T = max((exp - d).days, 0) / 365.0
        return float(bs(spot, strike, T, iv, right)), "model"


# ------------------------------------------------------------ contract pick
def week_expiry(chain, d):
    """The listed expiry that settles this week (Mon..Fri of d's week)."""
    friday = d + pd.Timedelta(days=(4 - d.weekday()))
    ok = chain[(chain.expiration > d) & (chain.expiration <= friday)]
    return None if not len(ok) else ok.expiration.max()

def put_expiry(chain, d, dte=PUT_DTE):
    ok = chain[chain.dte >= 20]
    if not len(ok):
        return None
    e = ok.assign(_g=(ok.dte - dte).abs()).sort_values(["_g", "expiration"])
    return e.iloc[0]["expiration"]

def next_week_expiry(chain, d):
    """The listed expiry that settles in the week AFTER d's week."""
    nxt_mon = d + pd.Timedelta(days=(7 - d.weekday()))
    nxt_fri = nxt_mon + pd.Timedelta(days=4)
    ok = chain[(chain.expiration > d) & (chain.expiration <= nxt_fri)]
    return None if not len(ok) else ok.expiration.max()


def pick_call_close(data, chain, d, exp, spot, target_pct=TARGET_PCT,
                    mode="premium", min_strike=None, min_credit=None,
                    buyback=0.0):
    """Pick a call to sell at the CLOSE of day d, marked on the EOD chain.

    min_strike : never re-strike below this (a roll may not lower the cap).
    min_credit : if set, require premium - buyback >= min_credit, walking the
                 strike DOWN from the target until the credit is met.
    """
    g = chain[(chain.expiration == exp) & (chain.right == "CALL")
              & (chain.strike >= spot)]
    if min_strike is not None:
        g = g[g.strike >= min_strike]
    if not len(g):
        return None
    g = g.sort_values("strike").head(40)
    T = max((exp - d).days, 0) / 365.0
    px = np.array([data.eod_value(chain, exp, float(k), "CALL", spot, d)
                   for k in g.strike.values], dtype=float)
    model = bs(spot, g.strike.values, T, g.implied_vol.values, "CALL")
    px = np.where(px > 0, px, model)
    target = target_pct * spot
    metric = px if mode == "premium" else px + (g.strike.values - spot)
    i = int(np.argmin(np.abs(metric - target)))
    if min_credit is not None:
        ok = np.where(px - buyback >= min_credit)[0]
        if len(ok):
            i = int(ok[np.argmin(np.abs(metric[ok] - target))])
        else:
            i = 0                        # lowest strike = richest premium
    return dict(strike=float(g.iloc[i]["strike"]), expiry=exp, price=float(px[i]),
                quality="eod_mid", iv=float(g.iloc[i]["implied_vol"]))


def iv_at(chain, exp, strike, right, fallback=None):
    g = chain[(chain.expiration == exp) & (chain.right == right)]
    if not len(g):
        return fallback
    exact = g[np.isclose(g.strike, strike)]
    if len(exact):
        return float(exact.iloc[0]["implied_vol"])
    j = (g.strike - strike).abs().idxmin()          # nearest-strike IV
    return float(g.loc[j, "implied_vol"])

def pick_call(data, chain, d, exp, spot, target_pct=TARGET_PCT, mode="premium"):
    """Pick the weekly call strike.

    mode="premium": premium alone is closest to target_pct * spot.
    mode="total":   premium + (K - spot), i.e. the whole gross gain if the stock
                    is called away, is closest to target_pct * spot.
    """
    g = chain[(chain.expiration == exp) & (chain.right == "CALL") & (chain.strike >= spot)]
    if not len(g):
        return None
    g = g.sort_values("strike").head(40)
    T = max((exp - d).days, 0) / 365.0
    px = bs(spot, g.strike.values, T, g.implied_vol.values, "CALL")
    target = target_pct * spot
    metric = px if mode == "premium" else px + (g.strike.values - spot)
    i = int(np.argmin(np.abs(metric - target)))
    K = float(g.iloc[i]["strike"]); iv = float(g.iloc[i]["implied_vol"])
    mk, q = data.mark(d, exp, K, "CALL", spot, iv)
    return dict(strike=K, expiry=exp, price=mk, quality=q, iv=iv,
                model_px=float(px[i]), target=target)

def call_at_strike(data, chain, d, exp, want, spot):
    """Re-write at a strike already chosen in an earlier week (the sticky rule).

    If that exact strike is not listed for this expiry, take the nearest listed
    strike at or above it — a sticky rule may never quietly lower the cap.
    """
    g = chain[(chain.expiration == exp) & (chain.right == "CALL")]
    if not len(g):
        return None
    at = g[np.isclose(g.strike, want)]
    if not len(at):
        up = g[g.strike >= want].sort_values("strike")
        if not len(up):
            return None
        at = up.head(1)
    K = float(at.iloc[0]["strike"]); iv = float(at.iloc[0]["implied_vol"])
    mk, q = data.mark(d, exp, K, "CALL", spot, iv)
    return dict(strike=K, expiry=exp, price=mk, quality=q, iv=iv,
                target=TARGET_PCT * spot)


def pick_put(data, chain, d, exp, spot):
    """Highest valid strike strictly below spot — 'just out of the money'."""
    g = chain[(chain.expiration == exp) & (chain.right == "PUT") & (chain.strike < spot)]
    if not len(g):
        return None
    r = g.sort_values("strike").iloc[-1]
    K = float(r["strike"]); iv = float(r["implied_vol"])
    mk, q = data.mark(d, exp, K, "PUT", spot, iv)
    return dict(strike=K, expiry=exp, price=mk, quality=q, iv=iv)


# ---------------------------------------------------------------- backtest
def mondays(sessions, year):
    """First trading day of each ISO week in `year`."""
    s = pd.Series(sessions)
    s = s[(s >= pd.Timestamp(f"{year}-01-01")) & (s <= pd.Timestamp(f"{year}-12-31"))]
    iso = s.dt.isocalendar()
    return list(s.groupby([iso.year.values, iso.week.values]).min())


class Book:
    """Open option legs. Puts are never sold — only expired or exercised."""
    def __init__(self):
        self.call = None      # dict(strike, expiry, qty, open_px)
        self.puts = []        # list of the same shape

    @property
    def put_qty(self):
        return sum(p["qty"] for p in self.puts)


def run_year(year, data=None, target_pct=TARGET_PCT, start_cash=START_CASH,
             costs=True, verbose=False, use_call=True, use_put=True,
             target_mode="premium", roll=None, roll_credit=False,
             roll_up_only=True, reserve_pct=0.0, sticky=False,
             put_policy="hold"):
    """One calendar year, standalone: $100k in on the first Monday of the year,
    everything liquidated at the close of the last session of the year."""
    d = data or Data()
    weeks = mondays(d.sessions, year)
    if not weeks:
        raise SystemExit(f"no sessions in {year}")
    last = [s for s in d.sessions if s.year == year][-1]

    cash, shares = float(start_cash), 0
    bk = Book()
    sticky_strike = None      # survives while the share position survives
    pnl = {"shares": 0.0, "calls": 0.0, "puts": 0.0, "fees": 0.0}
    marks = {"print_1000": 0, "print_near": 0, "model": 0, "eod_mid": 0}
    ledger, events, curve = [], [], []

    fee_opt = (lambda n: COMMISSION * n) if costs else (lambda n: 0.0)
    fee_shr = (lambda n: SHARE_FEE * n) if costs else (lambda n: 0.0)

    def settle(s, px):
        """Expire/assign/exercise everything dated on or before session `s`."""
        nonlocal cash, shares, sticky_strike
        if bk.call is not None and s >= bk.call["expiry"]:
            c = bk.call; K, n = c["strike"], c["qty"]
            pnl["calls"] += c["open_px"] * n * 100
            if px > K:
                ch = d.chain(s)
                intrinsic = px - K
                # you never buy a call back for less than its intrinsic value
                bb = max(d.eod_value(ch, c["expiry"], K, "CALL", px, s), intrinsic) \
                    if roll else intrinsic

                # A classic roll is one combo order, so only the NET debit has to
                # be funded. Closing to re-write on Monday is two separate trades,
                # so the whole buyback has to be funded on the day.
                new_leg = None
                if roll == "friday" and ch is not None and shares >= 100:
                    nexp = next_week_expiry(ch, s)
                    if nexp is not None:
                        new_leg = pick_call_close(
                            d, ch, s, nexp, px, target_pct, target_mode,
                            min_strike=K if roll_up_only else None,
                            min_credit=0.0 if roll_credit else None,
                            buyback=bb)

                if not roll:
                    closable = 0
                else:
                    per = bb - (new_leg["price"] if new_leg else 0.0)
                    unit = 100 * per + (2 * COMMISSION if costs and new_leg
                                        else (COMMISSION if costs else 0.0))
                    closable = n if unit <= 0 else min(n, int(cash // unit))

                if closable > 0:
                    cost = closable * 100 * bb + fee_opt(closable)
                    cash -= cost
                    pnl["calls"] -= closable * 100 * bb
                    pnl["fees"] += fee_opt(closable)
                    events.append(dict(date=s, kind="CALL_ROLLED_CLOSE",
                                       qty=closable, strike=K, spot=px, px=bb))
                left = n - closable
                if left > 0:                      # could not fund the buyback
                    sold = min(shares, left * 100)
                    cash += sold * K - fee_shr(sold)
                    pnl["shares"] += sold * px
                    pnl["calls"] -= sold * (px - K)
                    pnl["fees"] += fee_shr(sold)
                    shares -= sold
                    events.append(dict(date=s, kind="CALL_ASSIGNED", qty=sold,
                                       strike=K, spot=px))
                bk.call = None

                # classic roll: the far leg of the same combo order
                if new_leg is not None and closable > 0:
                    qty = min(closable, shares // 100)
                    if qty > 0:
                        cash += qty * 100 * new_leg["price"] - fee_opt(qty)
                        pnl["fees"] += fee_opt(qty)
                        marks["eod_mid"] += 1
                        bk.call = dict(strike=new_leg["strike"],
                                       expiry=new_leg["expiry"], qty=qty,
                                       open_px=new_leg["price"])
                        events.append(dict(date=s, kind="CALL_ROLLED_OPEN",
                                           qty=qty, strike=new_leg["strike"],
                                           spot=px, px=new_leg["price"]))
            else:
                events.append(dict(date=s, kind="CALL_EXPIRED", qty=n,
                                   strike=K, spot=px))
                bk.call = None

        for p in list(bk.puts):
            if s < p["expiry"]:
                continue
            K, n = p["strike"], p["qty"]
            pnl["puts"] -= p["open_px"] * n * 100
            if px < K:
                sold = min(shares, n * 100)
                if sold > 0:                       # exercise: deliver shares at K
                    cash += sold * K - fee_shr(sold)
                    pnl["shares"] += sold * px
                    pnl["puts"] += sold * (K - px)
                    pnl["fees"] += fee_shr(sold)
                    shares -= sold
                    events.append(dict(date=s, kind="PUT_EXERCISED", qty=sold,
                                       strike=K, spot=px))
                rem = n * 100 - sold               # uncovered puts settle for cash
                if rem > 0:
                    cash += rem * (K - px)
                    pnl["puts"] += rem * (K - px)
                    events.append(dict(date=s, kind="PUT_CASH_SETTLED",
                                       qty=rem // 100, strike=K, spot=px))
            else:
                events.append(dict(date=s, kind="PUT_EXPIRED", qty=n,
                                   strike=K, spot=px))
            bk.puts.remove(p)

        # The sticky strike belongs to the share position. Once the shares are
        # gone -- called away, or put to the counterparty -- the next position
        # picks a fresh strike.
        if shares == 0:
            sticky_strike = None

        # A protective put exists to protect shares. Once the shares have been
        # called away it is an unhedged long option nobody asked for, so this
        # policy sells it at market instead of riding it to expiry through
        # whatever the stock does next.
        if put_policy == "sell_when_flat" and shares == 0 and bk.puts:
            ch = d.chain(s)
            for p in list(bk.puts):
                v = d.eod_value(ch, p["expiry"], p["strike"], "PUT", px, s)
                v = max(v, max(p["strike"] - px, 0.0))     # never below intrinsic
                proceeds = p["qty"] * 100 * v - fee_opt(p["qty"])
                cash += proceeds
                pnl["puts"] += p["qty"] * 100 * v - p["open_px"] * p["qty"] * 100
                pnl["fees"] += fee_opt(p["qty"])
                events.append(dict(date=s, kind="PUT_SOLD_FLAT", qty=p["qty"],
                                   strike=p["strike"], spot=px, px=v))
                bk.puts.remove(p)

    def mtm(s, px):
        """Equity marked at the EOD chain mid where quoted, intrinsic otherwise."""
        eq = cash + shares * px
        ch = d.chain(s)
        for p in bk.puts:
            eq += p["qty"] * 100 * d.eod_value(ch, p["expiry"], p["strike"],
                                               "PUT", px, s)
        if bk.call is not None:
            c = bk.call
            eq -= c["qty"] * 100 * d.eod_value(ch, c["expiry"], c["strike"],
                                               "CALL", px, s)
        return eq

    for wi, mon in enumerate(weeks):
        spot = d.ten_high(mon)
        chain = d.chain(mon)
        if spot is None or chain is None or not len(chain):
            continue

        # ---- size the position -------------------------------------------
        # Buy shares with everything available; each 100 shares must carry a put,
        # so the unit cost of a lot includes the put we would have to buy for it.
        pexp = put_expiry(chain, mon)
        put_probe = (pick_put(d, chain, mon, pexp, spot)
                     if (use_put and pexp is not None) else None)
        put_px = put_probe["price"] if put_probe else 0.0
        can_size = put_probe is not None or not use_put

        covered = bk.put_qty                            # lots already carrying a put
        held = shares // 100
        put_lot   = 100 * put_px + (COMMISSION if costs else 0.0)
        share_lot = 100 * spot + (SHARE_FEE * 100 if costs else 0.0)

        # A rolling rule needs dry powder: a buyback that cannot be funded is an
        # assignment. reserve_pct holds back that share of equity as cash.
        equity_now = cash + shares * spot
        investable = cash - reserve_pct * equity_now

        def net_cost(L):
            """Cash needed to end the morning holding L fully-hedged lots.
            Negative means the trade releases cash (we are selling shares)."""
            c = (L - held) * share_lot if L >= held else (L - held) * 100 * spot
            return c + max(0, L - covered) * put_lot

        # Largest position we can hold with every lot hedged and cash never short.
        L = held
        if can_size and spot > 0:
            if net_cost(L) <= investable:
                while net_cost(L + 1) <= investable and L < 100000:
                    L += 1
            else:
                while L > 0 and net_cost(L) > investable:
                    L -= 1
        else:
            L = held                                     # no put quoted: stand pat

        # ---- trade the share leg to L lots --------------------------------
        if L > held:
            qty = (L - held) * 100
            cash -= qty * spot + fee_shr(qty)
            pnl["shares"] -= qty * spot
            pnl["fees"] += fee_shr(qty)
            shares += qty
            events.append(dict(date=mon, kind="BUY_SHARES", qty=qty,
                               strike=np.nan, spot=spot))
        elif L < held:
            qty = (held - L) * 100
            cash += qty * spot - fee_shr(qty)
            pnl["shares"] += qty * spot
            pnl["fees"] += fee_shr(qty)
            shares -= qty
            events.append(dict(date=mon, kind="SELL_SHARES", qty=qty,
                               strike=np.nan, spot=spot))

        lots = shares // 100
        if lots == 0:
            curve.append((mon, mtm(mon, d.close(mon))))
            continue

        # ---- top the put hedge up to the share position -------------------
        short = lots - bk.put_qty
        if short > 0 and put_probe is not None:
            cost = short * 100 * put_probe["price"] + fee_opt(short)
            cash -= cost
            pnl["fees"] += fee_opt(short)
            marks[put_probe["quality"]] += 1
            bk.puts.append(dict(strike=put_probe["strike"], expiry=put_probe["expiry"],
                                qty=short, open_px=put_probe["price"]))
            events.append(dict(date=mon, kind="BUY_PUT", qty=short,
                               strike=put_probe["strike"], spot=spot,
                               dte=(put_probe["expiry"] - mon).days,
                               px=put_probe["price"],
                               otm_pct=(put_probe["strike"]/spot-1)*100))

        # ---- write the weekly call ----------------------------------------
        row = dict(week=wi + 1, monday=mon, spot_1000_high=spot, lots=lots,
                   shares=shares)
        cexp = week_expiry(chain, mon)
        if use_call and cexp is not None and bk.call is None:
            if sticky and sticky_strike is not None and sticky_strike >= spot:
                # Hold the old cap while the stock is still below it: that is the
                # whole point, the rebound up to the strike belongs to us.
                leg = call_at_strike(d, chain, mon, cexp, sticky_strike, spot)
                if leg is None:          # strike not listed at all this week
                    leg = pick_call(d, chain, mon, cexp, spot, target_pct, target_mode)
            else:
                # Either a fresh position, or the stock has climbed back through
                # the old strike -- the rebound has been collected in full, so
                # re-strike upward rather than write in the money.
                leg = pick_call(d, chain, mon, cexp, spot, target_pct, target_mode)
            # A stranded strike can model out at a fraction of a cent. No such
            # trade exists: the bid is 0.00 and there is nothing to sell. Writing
            # it anyway would also pay commission to collect nothing, which is the
            # one thing a real trader would certainly not do.
            if leg and (leg["price"] < MIN_TICK
                        or lots * 100 * leg["price"] <= fee_opt(lots)):
                row["no_write_reason"] = ("below a tick" if leg["price"] < MIN_TICK
                                          else "premium under commission")
                leg = None
            if leg:
                sticky_strike = leg["strike"]
                n = lots
                prem = n * 100 * leg["price"]
                cash += prem - fee_opt(n)
                pnl["fees"] += fee_opt(n)
                marks[leg["quality"]] += 1
                bk.call = dict(strike=leg["strike"], expiry=leg["expiry"], qty=n,
                               open_px=leg["price"])
                row.update(call_strike=leg["strike"], call_expiry=leg["expiry"],
                           call_px=leg["price"], call_qty=n, call_premium=prem,
                           call_mark=leg["quality"], call_iv=leg["iv"],
                           prem_pct=leg["price"] / spot * 100,
                           otm_pct=(leg["strike"] / spot - 1) * 100,
                           gross_if_called_pct=(leg["strike"] - spot + leg["price"]) / spot * 100,
                           target_hit=abs(leg["price"] - leg["target"]) < 0.005 * spot)
        if bk.puts:
            p0 = bk.puts[0]
            row.update(put_strike=p0["strike"], put_expiry=p0["expiry"],
                       put_qty=bk.put_qty,
                       put_dte=(p0["expiry"] - mon).days)

        # ---- walk the week forward ----------------------------------------
        nxt = weeks[wi + 1] if wi + 1 < len(weeks) else None
        horizon = [s for s in d.sessions if s > mon and s <= last
                   and (nxt is None or s < nxt)]
        for s in horizon:
            px = d.close(s)
            settle(s, px)
            curve.append((s, mtm(s, px)))

        row["cash_after"] = cash
        row["equity"] = mtm(horizon[-1] if horizon else mon,
                            d.close(horizon[-1] if horizon else mon))
        ledger.append(row)

    # ---- liquidate at the last close ------------------------------------
    px = d.close(last)
    settle(last, px)
    if bk.call is not None:
        c = bk.call
        v = c["qty"] * 100 * max(px - c["strike"], 0)
        cash -= v
        pnl["calls"] += c["open_px"] * c["qty"] * 100 - v
        events.append(dict(date=last, kind="EOY_CLOSE_CALL", qty=c["qty"],
                           strike=c["strike"], spot=px, px=v / (c["qty"] * 100)))
        bk.call = None
    for p in list(bk.puts):
        v = p["qty"] * 100 * max(p["strike"] - px, 0)
        cash += v
        pnl["puts"] += v - p["open_px"] * p["qty"] * 100
        events.append(dict(date=last, kind="EOY_SELL_PUT", qty=p["qty"],
                           strike=p["strike"], spot=px, px=v / (p["qty"] * 100)))
        bk.puts.remove(p)
    if shares:
        cash += shares * px - fee_shr(shares)
        pnl["shares"] += shares * px
        pnl["fees"] += fee_shr(shares)
        events.append(dict(date=last, kind="EOY_SELL_SHARES", qty=shares,
                           strike=np.nan, spot=px))
        shares = 0
    curve.append((last, cash))

    return dict(year=year, final=cash, ledger=pd.DataFrame(ledger),
                events=pd.DataFrame(events),
                equity=pd.DataFrame(curve, columns=["date", "equity"]),
                pnl=pnl, marks=marks, weeks=len(weeks),
                start_cash=start_cash)
