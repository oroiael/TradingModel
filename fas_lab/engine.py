"""band_lab's locked intraday rules, parameterised so they can be run on any ETF.

Implements band_lab/IMPLEMENTATION_SPEC.md section 2 verbatim, including the
normative anti-lookahead backtest convention (section 2.6):
  * on the entry bar only the STOP may fire; the target is live from the next bar
  * within any bar the stop is checked BEFORE the target
Sizing is in fractions of capital (never whole shares) per the Phase-1 note.
"""
import functools
import numpy as np
import pandas as pd

ROOT = "/home/user/TradingModel"


@functools.lru_cache(maxsize=8)
def load_5min(name):
    df = pd.read_csv(f"{ROOT}/{name}")
    ts = df["Date"].str.replace(" America/New_York", "", regex=False)
    df["ts"] = pd.to_datetime(ts, format="%Y%m%d %H:%M:%S")
    df["date"] = df["ts"].dt.normalize()
    df["minute"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    return df[["ts", "date", "minute", "Open", "High", "Low", "Close", "Volume"]]


def sessions(df):
    """Per-session arrays plus the daily statistics the rules need."""
    out = {}
    for d, g in df.groupby("date"):
        g = g.sort_values("minute")
        out[d] = g
    return out


@functools.lru_cache(maxsize=8)
def _prep(name):
    df = load_5min(name)
    return daily_stats(df), sessions(df)


def daily_stats(df):
    g = df.groupby("date")
    d = pd.DataFrame({"o": g.Open.first(), "h": g.High.max(),
                      "l": g.Low.min(), "c": g.Close.last(),
                      "nbars": g.size()})
    d["range_pct"] = (d.h - d.l) / d.o * 100
    d["atr5"] = d.range_pct.shift(1).rolling(5).mean()      # 5 completed prior sessions
    # opening range 09:30-10:00 and pos10 from the 09:55 bar (closes AT 10:00)
    orw = df[df.minute < 600]
    og = orw.groupby("date")
    d["or_hi"] = og.High.max()
    d["or_lo"] = og.Low.min()
    d["close10"] = orw[orw.minute == 595].set_index("date")["Close"]
    d["or30"] = (d.or_hi - d.or_lo) / d.o * 100
    rng = (d.or_hi - d.or_lo)
    d["pos10"] = np.where(rng > 0, (d.close10 - d.or_lo) / rng.replace(0, np.nan), 0.5)
    # thr80 = 80th pct of OR30 over the prior 504 sessions, >=120 observations
    d["thr80"] = d.or30.shift(1).rolling(504, min_periods=120).quantile(0.80)
    return d


def run(symbol_file, gate=6.0, dip=0.01, target=0.01, stop=0.04, lev=1.0,
        f=1.00, max_fills=5, max_stops=2, entry_bar=18, cost_bp=0.0,
        start=None, end=None, half_day_bars=0):
    """Returns (per-day frame, per-trade frame).

    `cost_bp` is the all-in ROUND-TRIP cost per trade in basis points of notional
    (spread + slippage + commission); it is charged on every fill and scales with
    `lev`. Calibration: SOXL at 3.17 trades/day with cost_bp=2 gives ~6 bp/day,
    matching band_lab's stated 4-7 bp/day arithmetic drag.

    `lev` multiplies POSITION SIZE only; thresholds are taken as given. Running
    SOXL's rules on a k-times levered instrument therefore means passing every
    threshold divided by k together with lev=k.
    """
    ds_all, sess = _prep(symbol_file)
    ds = ds_all
    if start is not None: ds = ds[ds.index >= pd.Timestamp(start)]
    if end is not None:   ds = ds[ds.index <= pd.Timestamp(end)]

    g_eff, d_eff, t_eff, s_eff = gate, dip, target, stop

    days, trades = [], []
    for d, row in ds.iterrows():
        rec = dict(date=d, atr5=row.atr5, or30=row.or30, thr80=row.thr80,
                   pos10=row.pos10, on=False, ret=0.0, n_fills=0, n_stops=0)
        if (not np.isfinite(row.atr5) or not np.isfinite(row.thr80)
                or row.nbars < half_day_bars):                  # gate / (optional half-day)
            days.append(rec); continue
        if row.atr5 < g_eff:
            days.append(rec); continue
        if (row.or30 >= row.thr80) and (row.pos10 < 2.0 / 3.0):  # morning filter
            days.append(rec); continue

        g = sess[d]
        mins = g.minute.values
        O, H, L, C = g.Open.values, g.High.values, g.Low.values, g.Close.values
        n = len(g)
        rec["on"] = True
        fills = stops = 0
        pos = None                      # (entry_px, target_px, stop_px)
        day_ret = 0.0
        entry_i = -1
        for i in range(entry_bar, n):
            if pos is not None:
                E0, tp, sp = pos
                if L[i] <= sp:                                   # stop first (gap-aware)
                    px = sp if O[i] > sp else O[i]
                    r = (px / E0 - 1) * lev * f
                    day_ret += r; stops += 1
                    trades.append(dict(date=d, entry=E0, exit=px, ret=r, how="stop"))
                    pos = None
                elif i > entry_i and H[i] >= tp:                 # target from next bar on
                    px = tp if O[i] < tp else O[i]
                    r = (px / E0 - 1) * lev * f
                    day_ret += r
                    trades.append(dict(date=d, entry=E0, exit=px, ret=r, how="target"))
                    pos = None
            if pos is None and fills < max_fills and stops < max_stops:
                anchor = H[:i].max() if i > 0 else H[0]          # completed bars only
                lim = anchor * (1 - d_eff)
                if L[i] <= lim:
                    E = min(lim, O[i])
                    entry_i = i; fills += 1
                    day_ret -= cost_bp / 1e4 * lev * f
                    tp, sp = E * (1 + t_eff), E * (1 - s_eff)
                    if L[i] <= sp:                               # entry bar: stop only
                        px = sp if O[i] > sp else min(O[i], sp)
                        r = (px / E - 1) * lev * f
                        day_ret += r; stops += 1
                        trades.append(dict(date=d, entry=E, exit=px, ret=r, how="stop_entrybar"))
                    else:
                        pos = (E, tp, sp)
        if pos is not None:                                      # flatten at the close
            r = (C[-1] / pos[0] - 1) * lev * f
            day_ret += r
            trades.append(dict(date=d, entry=pos[0], exit=C[-1], ret=r, how="flatten"))
        rec.update(ret=day_ret, n_fills=fills, n_stops=stops)
        days.append(rec)
    return pd.DataFrame(days).set_index("date"), pd.DataFrame(trades)


def stats(days, trades, label=""):
    on = days[days.on]
    r = days.ret                                   # 0 on idle days
    ann = 252
    sharpe = r.mean() / r.std() * np.sqrt(ann) if r.std() > 0 else np.nan
    eq = (1 + r).cumprod()
    yrs = (days.index[-1] - days.index[0]).days / 365.25
    by_year = r.groupby(days.index.year).sum()
    on_sharpe = on.ret.mean() / on.ret.std() * np.sqrt(ann) if len(on) > 2 and on.ret.std() > 0 else np.nan
    return dict(label=label, on_days=int(on.on.sum()), on_rate=on.on.sum() / len(days),
                on_sharpe=on_sharpe,
                bp_per_on_day=on.ret.mean() * 1e4 if len(on) else np.nan,
                trades_per_on_day=len(trades) / max(len(on), 1),
                sharpe=sharpe, maxdd=(eq / eq.cummax() - 1).min(),
                cagr=eq.iloc[-1] ** (1 / yrs) - 1,
                win_rate=(trades.ret > 0).mean() if len(trades) else np.nan,
                worst_day=on.ret.min() if len(on) else np.nan,
                yrs_pos=f"{int((by_year > 0).sum())}/{len(by_year)}")
