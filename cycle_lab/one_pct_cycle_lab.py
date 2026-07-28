"""
1% Cycle Lab -- SOXL shares-only cycle strategy with 5-day stall put hedge.

Rules under test (user spec):
  1. Buy 100 SOXL. If price reaches entry * (1 + target) intraday, sell and
     immediately restart a new 100-share lot.
  2. If the lot stalls for `stall_days` trading days without hitting target:
     buy ANOTHER 100 shares (new active lot at current price) and buy 1 put
     ~30 calendar days out, strike just below spot (first OTM strike), to
     hedge the stalled lot.
  3. At put expiry: if OTM, put dies worthless and the stalled shares are sold
     at the close of the last trading day <= expiry. If ITM, take the better
     of (a) exercise: sell shares at strike, (b) sell put at bid + sell shares
     at market.
  4. Repeat forever. Multiple stalled/hedged lots can be outstanding at once.

Data: SOXL_5min_6Years.csv (unadjusted; 15:1 split 2021-03-02 handled here),
      SOXL_Options_2022..2026.csv (EOD chains with bid/ask, trade_date).

Outputs into cycle_lab/out/: crossing counts, strategy ledgers, variant grid.
"""

import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "cycle_lab", "out")
os.makedirs(OUT, exist_ok=True)

SPLIT_DATE = pd.Timestamp("2021-03-02")  # 15:1 split
SPLIT_RATIO = 15.0

# ----------------------------------------------------------------- load bars
def load_bars():
    df = pd.read_csv(os.path.join(ROOT, "SOXL_5min_6Years.csv"))
    dt = pd.to_datetime(df["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    df = df.assign(dt=dt, date=dt.dt.normalize())
    pre = df["date"] < SPLIT_DATE
    for c in ["Open", "High", "Low", "Close"]:
        df.loc[pre, c] = df.loc[pre, c] / SPLIT_RATIO
    return df.sort_values("dt").reset_index(drop=True)

def daily_from_bars(bars):
    return bars.groupby("date").agg(
        o=("Open", "first"), h=("High", "max"),
        l=("Low", "min"), c=("Close", "last"))

# ------------------------------------------------------- part A: crossings
def count_cycles_intraday(bars, target):
    """Buy at first bar close; limit-sell at entry*(1+target); re-enter at the
    exit bar's close. Returns cycle list with trading-day durations."""
    o = bars["Open"].to_numpy(); h = bars["High"].to_numpy()
    c = bars["Close"].to_numpy()
    day = bars["date"].to_numpy()
    day_codes = pd.factorize(bars["date"])[0]
    cycles = []
    entry = c[0]; entry_bar = 0; entry_day = day_codes[0]
    for i in range(1, len(c)):
        tgt = entry * (1 + target)
        if h[i] >= tgt:
            fill = o[i] if o[i] > tgt else tgt
            cycles.append({"entry_date": day[entry_bar], "exit_date": day[i],
                           "entry": entry, "exit": fill,
                           "tdays": int(day_codes[i] - entry_day),
                           "ret": fill / entry - 1})
            entry = c[i]; entry_bar = i; entry_day = day_codes[i]
    open_cycle = {"entry": entry, "last": c[-1],
                  "tdays_open": int(day_codes[-1] - entry_day)}
    return pd.DataFrame(cycles), open_cycle

def count_cycles_eod(daily, target):
    c = daily["c"].to_numpy(); idx = daily.index.to_numpy()
    cycles = []
    entry = c[0]; entry_i = 0
    for i in range(1, len(c)):
        if c[i] >= entry * (1 + target):
            cycles.append({"entry_date": idx[entry_i], "exit_date": idx[i],
                           "entry": entry, "exit": c[i],
                           "tdays": i - entry_i, "ret": c[i] / entry - 1})
            entry = c[i]; entry_i = i
    return pd.DataFrame(cycles)

# ------------------------------------------------------------ load options
def load_opts():
    frames = []
    for y in [2022, 2023, 2024, 2025, 2026]:
        f = os.path.join(ROOT, f"SOXL_Options_{y}.csv")
        d = pd.read_csv(f, usecols=["expiration", "strike", "right",
                                    "bid", "ask", "trade_date"])
        d["expiration"] = pd.to_datetime(d["expiration"], format="mixed")
        d["trade_date"] = pd.to_datetime(d["trade_date"], format="mixed")
        frames.append(d)
    opts = pd.concat(frames, ignore_index=True)
    opts["strike"] = opts["strike"].astype(float)
    # one row per (trade_date, right, expiration, strike): keep the last
    opts = opts.drop_duplicates(["trade_date", "right", "expiration", "strike"],
                                keep="last")
    return opts

class OptBook:
    def __init__(self, opts):
        self.by_day = {(d, r): g for (d, r), g in opts.groupby(["trade_date", "right"])}

    def chain(self, day, right="PUT"):
        return self.by_day.get((day, right))

    def _pick(self, day, spot, right, dte_target, otm_pct, nearest=False):
        """otm_pct < 0 selects in-the-money strikes (e.g. a call struck below
        spot). nearest=True picks the strike closest to spot*(1+otm_pct)
        instead of the first strike beyond it."""
        g = self.chain(day, right)
        if g is None:
            return None
        px_col = "ask" if right == "PUT" else "bid"
        g = g[(g["expiration"] > day) & (g[px_col] > 0)]
        if g.empty:
            return None
        dte = (g["expiration"] - day).dt.days
        g = g.assign(dte=dte)
        g = g[(g["dte"] >= 5) & (g["dte"] <= 60)]
        if g.empty:
            return None
        best_exp = g.loc[(g["dte"] - dte_target).abs().idxmin(), "expiration"]
        ref = spot * (1 + otm_pct) if right == "CALL" else spot * (1 - otm_pct)
        ge = g[g["expiration"] == best_exp]
        if nearest:
            gg = ge
            if gg.empty:
                return None
            row = gg.loc[(gg["strike"] - ref).abs().idxmin()]
        elif right == "PUT":   # first strike below ref
            gg = ge[ge["strike"] < ref]
            if gg.empty:
                return None
            row = gg.loc[gg["strike"].idxmax()]
        else:                  # first strike above ref
            gg = ge[ge["strike"] > ref]
            if gg.empty:
                return None
            row = gg.loc[gg["strike"].idxmin()]
        return {"expiration": row["expiration"], "strike": float(row["strike"]),
                "ask": float(row["ask"]), "bid": float(row["bid"]),
                "dte": int(row["dte"])}

    def pick_hedge(self, day, spot, dte_target=30, otm_pct=0.0):
        return self._pick(day, spot, "PUT", dte_target, otm_pct)

    def pick_call(self, day, spot, dte_target=30, otm_pct=0.0, nearest=False):
        return self._pick(day, spot, "CALL", dte_target, otm_pct, nearest)

    def quote(self, day, expiration, strike, right="PUT"):
        g = self.chain(day, right)
        if g is None:
            return None
        m = g[(g["expiration"] == expiration) & (g["strike"] == strike)]
        if m.empty:
            return None
        r = m.iloc[0]
        return {"bid": float(r["bid"]), "ask": float(r["ask"])}

# ----------------------------------------------------------- strategy engine
def run_strategy(bars, daily, putbook, start, end,
                 target=0.01, stall_days=5, mode="put",
                 otm_pct=0.0, dte_target=30, early_unwind=False,
                 strike_ref="spot", shares=100):
    """mode: 'put'  = user spec (hedge stalled lot with a put)
             'none' = same timeline, no put bought (control)
             'stop' = sell the stalled lot at the stall close (hard reset)
             'cc'   = sell a ~30d covered call on the stalled lot instead"""
    days = [d for d in daily.index if start <= d <= end]
    bars_by_day = {d: g for d, g in
                   bars[(bars["date"] >= start) & (bars["date"] <= end)].groupby("date")}
    day_pos = {d: i for i, d in enumerate(days)}

    ledger = []      # closed-lot records
    hedged = []      # open hedged/parked lots
    cash = 0.0
    equity_rows = []

    d0 = days[0]
    active = {"entry": float(daily.loc[d0, "c"]), "entry_day": d0}

    def close_hedged_lot(lot, day, spot, reason):
        nonlocal cash
        put_pnl = 0.0
        proceeds = spot * shares
        detail = reason
        if mode == "cc" and lot.get("strike"):
            put_pnl = lot["prem"] * shares          # premium collected up front
            if spot > lot["strike"]:
                proceeds = lot["strike"] * shares   # assigned
                detail += "|assigned"
            else:
                detail += "|call_expired"
        elif mode == "put":
            intrinsic = max(lot["strike"] - spot, 0.0)
            q = putbook.quote(day, lot["expiration"], lot["strike"])
            bid = q["bid"] if q else 0.0
            put_val = max(intrinsic, bid)
            if intrinsic > 0 and intrinsic >= bid:
                proceeds = lot["strike"] * shares          # exercise
                detail += "|exercised"
                put_pnl = -lot["put_cost"] * shares
            else:
                put_pnl = (put_val - lot["put_cost"]) * shares
                detail += "|put_sold" if put_val > 0 else "|put_worthless"
        share_pnl = proceeds - lot["entry"] * shares
        cash += share_pnl + put_pnl
        ledger.append({"kind": "hedged_lot", "entry_date": lot["entry_day"],
                       "hedge_date": lot.get("hedge_day"), "exit_date": day,
                       "entry": lot["entry"], "exit_spot": spot,
                       "strike": lot.get("strike"), "put_cost": lot.get("put_cost", 0.0),
                       "share_pnl": share_pnl, "put_pnl": put_pnl,
                       "pnl": share_pnl + put_pnl, "detail": detail})

    for d in days:
        g = bars_by_day.get(d)
        if g is None:
            continue
        o = g["Open"].to_numpy(); h = g["High"].to_numpy(); c = g["Close"].to_numpy()

        # 1) resolve hedged lots whose exit day is today
        still = []
        for lot in hedged:
            if lot["exit_day"] == d:
                close_hedged_lot(lot, d, c[-1], "expiry")
            elif early_unwind and daily.loc[d, "h"] >= lot["entry"]:
                # recovered to breakeven: sell shares at entry, dump the put
                spot = lot["entry"]
                q = (putbook.quote(d, lot["expiration"], lot["strike"])
                     if mode == "put" else None)
                bid = q["bid"] if q else 0.0
                share_pnl = 0.0
                put_pnl = (bid - lot["put_cost"]) * shares if mode == "put" else 0.0
                nonlocal_cash = share_pnl + put_pnl
                cashadd = nonlocal_cash
                ledger.append({"kind": "hedged_lot", "entry_date": lot["entry_day"],
                               "hedge_date": lot.get("hedge_day"), "exit_date": d,
                               "entry": lot["entry"], "exit_spot": spot,
                               "strike": lot.get("strike"),
                               "put_cost": lot.get("put_cost", 0.0),
                               "share_pnl": share_pnl, "put_pnl": put_pnl,
                               "pnl": cashadd, "detail": "early_unwind"})
                cash += cashadd
            else:
                still.append(lot)
        hedged = still

        # 2) intraday: active lot limit-sell at target, restart on fill
        i = 0
        while i < len(c):
            tgt = active["entry"] * (1 + target)
            if h[i] >= tgt:
                fill = o[i] if o[i] > tgt else tgt
                pnl = (fill - active["entry"]) * shares
                cash += pnl
                ledger.append({"kind": "cycle_win", "entry_date": active["entry_day"],
                               "exit_date": d, "entry": active["entry"], "exit_spot": fill,
                               "strike": None, "put_cost": 0.0,
                               "share_pnl": pnl, "put_pnl": 0.0, "pnl": pnl,
                               "detail": f"target_hit"})
                active = {"entry": c[i], "entry_day": d}
            i += 1

        # 3) end of day: stall check on the active lot
        age = day_pos[d] - day_pos[active["entry_day"]]
        if age >= stall_days:
            spot = c[-1]
            if mode == "stop":
                pnl = (spot - active["entry"]) * shares
                cash += pnl
                ledger.append({"kind": "stalled_stop", "entry_date": active["entry_day"],
                               "exit_date": d, "entry": active["entry"], "exit_spot": spot,
                               "strike": None, "put_cost": 0.0,
                               "share_pnl": pnl, "put_pnl": 0.0, "pnl": pnl,
                               "detail": "stall_stop"})
                active = {"entry": spot, "entry_day": d}
            else:
                if mode == "put":
                    hedge = putbook.pick_hedge(d, spot, dte_target, otm_pct)
                elif mode == "cc":
                    if strike_ref == "entry":   # repair: strike nearest entry
                        rel = active["entry"] / spot - 1
                        hedge = putbook.pick_call(d, spot, dte_target, rel,
                                                  nearest=True)
                    else:
                        hedge = putbook.pick_call(d, spot, dte_target, otm_pct)
                else:
                    hedge = None
                if mode in ("put", "cc") and hedge is None:
                    pass  # no usable chain today; try again tomorrow
                else:
                    exp = (hedge["expiration"] if hedge is not None
                           else d + pd.Timedelta(days=dte_target))
                    # exit on last trading day <= expiry
                    exit_day = max([x for x in days if x <= exp], default=None)
                    if exit_day is None or exit_day <= d:
                        exit_day = days[min(day_pos[d] + 21, len(days) - 1)]
                    lot = {"entry": active["entry"], "entry_day": active["entry_day"],
                           "hedge_day": d, "exit_day": exit_day}
                    if mode == "put":
                        lot.update({"strike": hedge["strike"],
                                    "expiration": hedge["expiration"],
                                    "put_cost": hedge["ask"]})
                    elif mode == "cc":
                        lot.update({"strike": hedge["strike"],
                                    "expiration": hedge["expiration"],
                                    "put_cost": 0.0, "prem": hedge["bid"]})
                    else:
                        lot.update({"strike": None, "expiration": exp, "put_cost": 0.0})
                    hedged.append(lot)
                    active = {"entry": spot, "entry_day": d}

        # 4) daily mark-to-market
        spot = c[-1]
        mtm = cash + (spot - active["entry"]) * shares
        for lot in hedged:
            mtm += (spot - lot["entry"]) * shares
            if mode == "put" and lot.get("strike"):
                q = putbook.quote(d, lot["expiration"], lot["strike"])
                v = q["bid"] if q and q["bid"] > 0 else max(lot["strike"] - spot, 0.0)
                mtm += (v - lot["put_cost"]) * shares
            elif mode == "cc" and lot.get("strike"):
                q = putbook.quote(d, lot["expiration"], lot["strike"], right="CALL")
                v = (q["ask"] if q and q["ask"] > 0
                     else max(spot - lot["strike"], 0.0))
                mtm += (lot["prem"] - v) * shares
        equity_rows.append({"date": d, "cash_pnl": cash, "mtm_pnl": mtm,
                            "open_hedged": len(hedged),
                            "capital": (1 + len(hedged)) * spot * shares})

    # liquidate at the end
    last = days[-1]; spot = float(daily.loc[last, "c"])
    pnl = (spot - active["entry"]) * shares
    cash += pnl
    ledger.append({"kind": "final_liq", "entry_date": active["entry_day"],
                   "exit_date": last, "entry": active["entry"], "exit_spot": spot,
                   "strike": None, "put_cost": 0.0, "share_pnl": pnl,
                   "put_pnl": 0.0, "pnl": pnl, "detail": "end_of_data"})
    for lot in hedged:
        close_hedged_lot(lot, last, spot, "end_of_data")

    led = pd.DataFrame(ledger)
    eq = pd.DataFrame(equity_rows).set_index("date")
    return led, eq, cash

def summarize(name, led, eq, cash):
    wins = led[led["kind"] == "cycle_win"]
    hlots = led[led["kind"] == "hedged_lot"]
    peak = eq["mtm_pnl"].cummax()
    dd = (eq["mtm_pnl"] - peak).min()
    return {
        "variant": name,
        "total_pnl": round(cash, 0),
        "cycle_wins": len(wins),
        "cycle_win_pnl": round(wins["pnl"].sum(), 0),
        "stalls": len(hlots) + len(led[led["kind"] == "stalled_stop"]),
        "hedged_lot_pnl": round(hlots["pnl"].sum()
                                + led[led["kind"] == "stalled_stop"]["pnl"].sum(), 0),
        "put_spend": round((hlots["put_cost"] * 100).sum(), 0),
        "put_pnl": round(hlots["put_pnl"].sum(), 0),
        "max_open_hedged": int(eq["open_hedged"].max()),
        "avg_open_hedged": round(eq["open_hedged"].mean(), 2),
        "max_capital": round(eq["capital"].max(), 0),
        "max_dd_$": round(dd, 0),
        "ret_on_max_cap": round(cash / eq["capital"].max() * 100, 1),
        "final_liq_pnl": round(led[led["kind"] == "final_liq"]["pnl"].sum(), 0),
    }

# -------------------------------------------------------------------- main
def main():
    bars = load_bars()
    daily = daily_from_bars(bars)
    print(f"bars {len(bars)}  days {len(daily)}  "
          f"{daily.index[0].date()} .. {daily.index[-1].date()}")

    # ---------------- Part A: +1% crossings, intraday vs EOD, full 6 years
    rows = []
    for tgt in [0.005, 0.01, 0.02, 0.03]:
        cyc, open_c = count_cycles_intraday(bars, tgt)
        cyc_eod = count_cycles_eod(daily, tgt)
        rows.append({
            "target_pct": tgt * 100,
            "intraday_hits": len(cyc),
            "intraday_hits_per_year": round(len(cyc) / (len(daily) / 252), 1),
            "intraday_median_tdays": float(cyc["tdays"].median()),
            "intraday_pct_within_5d": round((cyc["tdays"] <= 5).mean() * 100, 1),
            "eod_hits": len(cyc_eod),
            "eod_median_tdays": float(cyc_eod["tdays"].median()),
            "eod_pct_within_5d": round((cyc_eod["tdays"] <= 5).mean() * 100, 1),
        })
        if tgt == 0.01:
            cyc.to_csv(os.path.join(OUT, "crossings_intraday_1pct.csv"), index=False)
            cyc_eod.to_csv(os.path.join(OUT, "crossings_eod_1pct.csv"), index=False)
            # stall odds: distribution of trading days to target
            dist = (cyc["tdays"].value_counts(normalize=True).sort_index().cumsum()
                    .rename("cum_frac").to_frame())
            dist.to_csv(os.path.join(OUT, "days_to_target_1pct_intraday.csv"))
    cross = pd.DataFrame(rows)
    cross.to_csv(os.path.join(OUT, "crossing_summary.csv"), index=False)
    print("\n=== Part A: target crossings (full history) ===")
    print(cross.to_string(index=False))

    # ---------------- Part B/C: strategy variants on the options window
    opts = load_opts()
    putbook = OptBook(opts)
    start = pd.Timestamp("2022-01-03")
    end = min(pd.Timestamp("2026-07-02"), daily.index[-1])

    variants = [
        ("USER_SPEC 1%/5d/putOTM0", dict(target=0.01, stall_days=5, mode="put", otm_pct=0.0)),
        ("no_hedge control",        dict(target=0.01, stall_days=5, mode="none")),
        ("stop_reset control",      dict(target=0.01, stall_days=5, mode="stop")),
        ("early_unwind",            dict(target=0.01, stall_days=5, mode="put", early_unwind=True)),
        ("put 5% OTM",              dict(target=0.01, stall_days=5, mode="put", otm_pct=0.05)),
        ("put 10% OTM",             dict(target=0.01, stall_days=5, mode="put", otm_pct=0.10)),
        ("target 2%",               dict(target=0.02, stall_days=5, mode="put")),
        ("target 3%",               dict(target=0.03, stall_days=5, mode="put")),
        ("stall 3d",                dict(target=0.01, stall_days=3, mode="put")),
        ("stall 10d",               dict(target=0.01, stall_days=10, mode="put")),
        ("2%/10d",                  dict(target=0.02, stall_days=10, mode="put")),
        ("stop_reset 2%/10d",       dict(target=0.02, stall_days=10, mode="stop")),
        ("covered_call justOTM",    dict(target=0.01, stall_days=5, mode="cc", otm_pct=0.0)),
        ("covered_call 5% OTM",     dict(target=0.01, stall_days=5, mode="cc", otm_pct=0.05)),
        ("covered_call 2%/10d",     dict(target=0.02, stall_days=10, mode="cc")),
    ]
    summary = []
    for name, kw in variants:
        led, eq, cash = run_strategy(bars, daily, putbook, start, end, **kw)
        summary.append(summarize(name, led, eq, cash))
        tag = name.replace(" ", "_").replace("%", "pct").replace("/", "-")
        led.to_csv(os.path.join(OUT, f"ledger_{tag}.csv"), index=False)
        if name.startswith("USER_SPEC"):
            eq.to_csv(os.path.join(OUT, "equity_user_spec.csv"))
    summ = pd.DataFrame(summary)

    # buy & hold 100 shares benchmark on the same window
    win = daily[(daily.index >= start) & (daily.index <= end)]
    bh = (win["c"].iloc[-1] - win["c"].iloc[0]) * 100
    bh_dd = ((win["c"] - win["c"].cummax()) * 100).min()
    summ = pd.concat([summ, pd.DataFrame([{
        "variant": "buy_hold_100sh", "total_pnl": round(bh, 0),
        "max_capital": round(win["c"].max() * 100, 0),
        "max_dd_$": round(bh_dd, 0)}])], ignore_index=True)

    summ.to_csv(os.path.join(OUT, "variant_summary.csv"), index=False)
    print(f"\n=== Part B/C: strategy variants {start.date()}..{end.date()} "
          f"(100 sh/lot, real put quotes, no commissions) ===")
    print(summ.to_string(index=False))

if __name__ == "__main__":
    main()
