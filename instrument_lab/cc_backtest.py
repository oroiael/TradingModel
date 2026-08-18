"""Weekly covered call on instruments with NO option chain in the repo.

There is no FAS or XLU option data anywhere here -- only SOXL and TQQQ. So the
option leg has to be MODEL-PRICED. That is only worth anything if the model
reproduces a backtest we can check, so the same engine is run on SOXL, where a
real-quote answer already exists in cc_lp_lab, and the two are compared.

Pricing: IV = trailing realised vol (13w, no lookahead) + a stated VRP in vol
points. The VRP is the one unmeasured input for FAS/XLU, so it is swept.
Strikes are rounded to a plausible listed grid; costs are commission plus a
relative half-spread on the premium.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from scipy.optimize import brentq
import screen as sc

ROOT = "/home/user/TradingModel"
OUT = os.path.join(ROOT, "instrument_lab/out")


def weekly_series_from_5min(name, entry_minute=600):
    """Weekly (entry price at Monday `entry_minute`, exit at Friday close)."""
    df = pd.read_csv(f"{ROOT}/{name}")
    ts = df["Date"].str.replace(" America/New_York", "", regex=False)
    df["ts"] = pd.to_datetime(ts, format="%Y%m%d %H:%M:%S")
    df["date"] = df["ts"].dt.normalize()
    df["minute"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    iso = df["date"].dt.isocalendar()
    df["wk"] = list(zip(iso.year, iso.week))
    rows = []
    for wk, g in df.groupby("wk", sort=False):
        d0 = g["date"].min()
        first = g[g["date"] == d0]
        e = first[first["minute"] >= entry_minute]
        entry = float(e["Open"].iloc[0]) if len(e) else float(first["Open"].iloc[0])
        rows.append(dict(wk_start=d0, entry=entry, close=float(g["Close"].iloc[-1]),
                         high=float(g["High"].max())))
    return pd.DataFrame(rows).sort_values("wk_start").reset_index(drop=True)


def weekly_series_from_closes(closes, start="2021-08-20"):
    """Weekly closes only: entry at the prior week's close."""
    s = pd.Series(closes)
    idx = pd.date_range(start, periods=len(s), freq="W-FRI")
    return pd.DataFrame(dict(wk_start=idx[:-1], entry=s.values[:-1],
                             close=s.values[1:], high=np.maximum(s.values[:-1], s.values[1:])))


def run(wk, delta=0.30, vrp_pts=0.02, vol_lb=13, grid=1.0, cost_ct=0.65, const_vol=False,
        slip=0.05, div_yield=0.0, start_cash=100_000.0, write_calls=True):
    r = wk["close"] / wk["entry"] - 1
    rv_tr = r.rolling(vol_lb).std().shift(1) * np.sqrt(52)      # no lookahead
    if const_vol:
        # Trailing vol systematically OVERprices options after a vol spike, because
        # vol mean-reverts -- that manufactures a premium the market never paid.
        # A single constant vol has no timing bias in either direction.
        rv_tr = pd.Series(r.std() * np.sqrt(52), index=r.index)
        rv_tr.iloc[:vol_lb] = np.nan
    T = 1 / 52
    cash, shares, K_live = start_cash, 0, None
    eq, led = [], []
    for i, row in wk.iterrows():
        S = row.entry
        rv = rv_tr.iloc[i]
        # The share position is held from week ONE. Only the CALL waits for a
        # volatility estimate -- otherwise the engine sits in cash through the
        # warm-up and gets a free pass on whatever the market did meanwhile.
        can_write = np.isfinite(rv) and rv > 0
        iv = max(rv + vrp_pts, 0.02) if can_write else np.nan
        lots = int((cash + shares * S) // (100 * S))
        d_sh = lots * 100 - shares
        if d_sh != 0:
            cash -= d_sh * S; shares += d_sh
        prem_recv = 0.0
        K_live = None
        if write_calls and can_write and lots > 0:
            Kraw = sc.strike_for_delta(S, T, iv, delta)
            K = np.round(Kraw / grid) * grid
            if K <= S: K = S + grid
            px = sc.bs_call(S, K, T, iv)
            px_fill = max(px * (1 - slip), 0.0)
            prem_recv = lots * 100 * px_fill - lots * cost_ct
            cash += prem_recv
            K_live = K
        C = row.close
        assigned = K_live is not None and C > K_live
        if assigned:
            cash += shares * K_live; shares = 0
        cash += shares * S * (div_yield / 52) if div_yield else 0.0
        eqv = cash + shares * C
        eq.append(dict(wk=row.wk_start, equity=eqv, lots=lots, spot=C,
                       K=K_live if write_calls else np.nan, assigned=assigned,
                       prem=prem_recv, iv=iv))
        led.append(dict(wk=row.wk_start, S=S, K=K_live, C=C, iv=iv, lots=lots,
                        prem=prem_recv, assigned=assigned))
    e = pd.DataFrame(eq).set_index("wk")
    return e, pd.DataFrame(led)


def stats(e, label, start_cash=100_000.0):
    """CAGR must be measured from the CAPITAL COMMITTED, not from the first
    week's closing equity -- week 1 can move a long way before it is observed."""
    q = e["equity"].dropna()
    q = q[q > 0]
    yrs = (q.index[-1] - q.index[0]).days / 365.25
    rr = pd.concat([pd.Series([start_cash], index=[q.index[0]]), q]).pct_change().dropna()
    return dict(label=label, final=q.iloc[-1], cagr=(q.iloc[-1] / start_cash) ** (1 / yrs) - 1,
                maxdd=(q / q.cummax() - 1).min(),
                sharpe=rr.mean() / rr.std() * np.sqrt(52) if rr.std() > 0 else np.nan,
                vol=rr.std() * np.sqrt(52), years=yrs)
