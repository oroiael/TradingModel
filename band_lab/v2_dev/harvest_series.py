"""
RUN 1 (PARK the losers) across every complete session in the file.

The single-session tool answers "what happened that day". This answers "what
happens if you do it every day for six and a half years", which is a different
question: it needs compounding, a drawdown, and a CAGR, and it needs the
commission bill that 95,000 round trips actually generates.

The rule is unchanged from harvest_one_day.py and is imported from it rather
than restated, so the two cannot drift apart:

    buy at a minute's open, wait for the first touch of +0.5% or -0.5%,
    re-enter at the next minute's open, no new entries from 14:00, and at
    15:55 close whatever is still held at that minute's close. A loser is NOT
    sold when it is marked -- it is parked and closed with everything else at
    15:55, so unsold losers accumulate through the day.

Settled assumptions, all of them switchable from the command line
------------------------------------------------------------------
  A1  Slot size is set at each day's OPEN to (equity - reserve) / slots and
      held fixed for that session. It scales with the account.
  A2  The reserve is a flat $25,000 that never scales -- the PDT minimum.
  A3  No overnight carry. Every day ends flat, so compounding is day-to-day.
  A4  Commission is IBKR Pro tiered: $0.0035 a share, $1.00 order minimum,
      capped at 1% of trade value, charged on the buy and again on the sell.
  A5  SLIPPAGE IS NOT MODELLED. Limit orders are assumed to fill at exactly
      the target price. This flatters every number below.
  A6  Gross and net are two separate compounded paths, because commissions
      change equity, which changes position size, which changes share counts.
      Net is not derivable from gross by subtraction.
  A7  If (equity - reserve) will not buy one share the day trades nothing.
  A8  Intraday equity marks open positions at each bar's CLOSE. A low-marked
      figure is reported beside it as the worst price actually touched.

    python3 band_lab/v2_dev/harvest_series.py
    python3 band_lab/v2_dev/harvest_series.py --since 2022-01-01
    python3 band_lab/v2_dev/harvest_series.py --slippage 0.005 --outdir out/
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest_one_day import (  # noqa: E402  -- one implementation of the rule
    FLAT_MIN, NO_NEW_MIN, OPEN_MIN, ROOT, ibkr_tiered, simulate)

TRADING_DAYS = 252.0


def load_sessions(symbol, since=None, until=None):
    """Every complete session in the file, as {date: [bars]}.

    A session must open at 09:30 and still be trading at 15:55; half-days are
    excluded because the 15:55 exit the rule depends on does not exist on them.
    """
    df = pd.read_csv(os.path.join(ROOT, f"{symbol}_1min.csv"))
    dt = pd.to_datetime(df["Date"].str.replace(" America/New_York", "", regex=False),
                        format="%Y%m%d %H:%M:%S")
    df = df.assign(day=dt.dt.normalize(), minute=dt.dt.hour * 60 + dt.dt.minute)

    bm = df.groupby("day")["minute"]
    full = set(bm.min()[bm.min() == OPEN_MIN].index) & set(
        df[df.minute == FLAT_MIN]["day"].unique())
    if since:
        full = {d for d in full if d >= pd.Timestamp(since)}
    if until:
        full = {d for d in full if d <= pd.Timestamp(until)}

    sub = df[df.day.isin(full) & df.minute.between(OPEN_MIN, FLAT_MIN)]
    out = {}
    for day, g in sub.sort_values(["day", "minute"]).groupby("day", sort=True):
        out[day] = list(zip(g.minute.astype(int), g.Open.astype(float),
                            g.High.astype(float), g.Low.astype(float),
                            g.Close.astype(float), g.Volume.astype(float)))
    return out


def intraday_marks(bars, ledger, start_equity):
    """Equity at the end of every bar, marking open positions to market.

    Positions are all the same instrument, so the mark only needs the total
    open share count -- not a per-position loop. Cash moves out at an entry's
    minute and back in at its exit's minute; a trade that opens and closes
    inside one minute nets to zero shares held at the end of that bar, which
    is correct.
    """
    n = len(bars)
    base = bars[0][0]
    d_cash = np.zeros(n + 1)
    d_shares = np.zeros(n + 1)

    for t in ledger:
        i, j = t["entry_min"] - base, t["exit_min"] - base
        d_cash[i] -= t["cost"] + t["buy_fee"]
        d_cash[j] += t["proceeds"] - t["sell_fee"]
        d_shares[i] += t["shares"]
        d_shares[j] -= t["shares"]

    cash = start_equity + np.cumsum(d_cash[:n])
    shares = np.cumsum(d_shares[:n])
    close = np.array([b[4] for b in bars])
    low = np.array([b[3] for b in bars])
    return cash + shares * close, cash + shares * low


def run_series(sessions, pct, park, equity0, reserve, slots, commission,
               slippage=0.0, cutoff=NO_NEW_MIN, marks=True):
    """Compound the rule day after day. One row per session."""
    equity = equity0
    rows, trade_pnl, trade_won, curve_min_c, curve_min_l = [], [], [], [], []

    for day, bars in sessions.items():
        start = equity
        sim = simulate(bars, pct, park, start, reserve, slots,
                       commission=commission, slippage=slippage, cutoff=cutoff)
        led = sim["ledger"]
        equity = sim["ending"]

        if led and marks:
            mc, ml = intraday_marks(bars, led, start)
            trough_c, trough_l = float(mc.min()), float(ml.min())
        else:
            trough_c = trough_l = start

        wins = sum(t["outcome"] == "up" for t in led)
        losses = sum(t["outcome"] == "down" for t in led)
        for t in led:
            trade_pnl.append(t["pnl"])
            trade_won.append(t["outcome"] == "up")
        curve_min_c.append(trough_c)
        curve_min_l.append(trough_l)

        rows.append(dict(
            date=day.date(), start_equity=start, end_equity=equity,
            pnl=equity - start, ret=equity / start - 1 if start else 0.0,
            trades=len(led), wins=wins, losses=losses,
            unresolved=sum(t["outcome"] == "open" for t in led),
            ambiguous=sum(t["ambiguous"] for t in led),
            win_rate=wins / (wins + losses) if wins + losses else np.nan,
            fees=sim["fees"], peak_open=sim["peak_open"],
            peak_cost=sim["peak_cost"], blocked=len(sim["blocked"]),
            slot_size=(start - reserve) / slots if park else start - reserve,
            intraday_trough_close=trough_c, intraday_trough_low=trough_l,
            day_open=bars[0][1], day_close=bars[-1][4],
            underlying_ret=bars[-1][4] / bars[0][1] - 1))

    df = pd.DataFrame(rows)
    return df, np.array(trade_pnl), np.array(trade_won)


def longest_run(flags):
    """(longest True run, longest False run) over a boolean sequence."""
    best = {True: 0, False: 0}
    cur, prev = 0, None
    for f in flags:
        f = bool(f)
        cur = cur + 1 if f == prev else 1
        best[f] = max(best[f], cur)
        prev = f
    return best[True], best[False]


def run_spans(dates, flags):
    """Every maximal run of True, as (start, end, length), longest first."""
    spans, i = [], 0
    flags = list(map(bool, flags))
    while i < len(flags):
        if not flags[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(flags) and flags[j + 1]:
            j += 1
        spans.append((dates[i], dates[j], j - i + 1))
        i = j + 1
    return sorted(spans, key=lambda s: -s[2])


def drawdown(curve):
    """(max drawdown fraction, peak index, trough index) on an equity curve."""
    curve = np.asarray(curve, dtype=float)
    peaks = np.maximum.accumulate(curve)
    dd = curve / peaks - 1.0
    t = int(dd.argmin())
    p = int(np.argmax(curve[:t + 1])) if t else 0
    return float(dd.min()), p, t


def metrics(df, equity0, trade_pnl, trade_won, label, slots):
    eq = df.end_equity.to_numpy(float)
    dates = list(df.date)
    years = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25
    final = eq[-1]
    total = final / equity0 - 1
    cagr = (final / equity0) ** (1 / years) - 1 if years > 0 and final > 0 else np.nan

    r = df.ret.to_numpy(float)
    sharpe = r.mean() / r.std(ddof=1) * np.sqrt(TRADING_DAYS) if r.std(ddof=1) else np.nan
    dn = r[r < 0]
    sortino = (r.mean() / dn.std(ddof=1) * np.sqrt(TRADING_DAYS)
               if len(dn) > 1 and dn.std(ddof=1) else np.nan)

    dd_eod, p_i, t_i = drawdown(eq)
    # Intraday: the trough inside a day can be below both its neighbours' closes,
    # so the running peak has to come from the end-of-day curve it sits between.
    prev_eq = np.concatenate(([equity0], eq[:-1]))
    run_peak = np.maximum.accumulate(np.maximum(prev_eq, eq))
    dd_intra_c = float((df.intraday_trough_close.to_numpy(float) / run_peak - 1).min())
    dd_intra_l = float((df.intraday_trough_low.to_numpy(float) / run_peak - 1).min())

    # A day the account did not trade has pnl == 0. It is not a losing day, and
    # counting it as one manufactured a 614-day "losing streak" worth -$71.61
    # out of a frozen account. Wins and losses are each counted on their own.
    day_w, _ = longest_run(df.pnl > 0)
    day_l, _ = longest_run(df.pnl < 0)
    tr_w, _ = longest_run(trade_pnl > 0)
    tr_l, _ = longest_run(trade_pnl < 0)
    sig_w, _ = longest_run(trade_won)
    sig_l, _ = longest_run(~trade_won)

    # Once equity decays to the reserve, (equity - reserve) / slots will not buy
    # one share and the strategy stops dead. That is a distinct outcome from
    # losing money and has to be named, not averaged into the return.
    traded = df.trades > 0
    frozen_from = None
    if traded.any() and not traded.iloc[-1]:
        last = int(np.flatnonzero(traded.to_numpy())[-1])
        frozen_from = df.date.iloc[last + 1]
    elif not traded.any():
        frozen_from = df.date.iloc[0]

    return dict(
        label=label, days=len(df), years=years, equity0=equity0, final=final,
        total=total, cagr=cagr, sharpe=sharpe, sortino=sortino,
        dd_eod=dd_eod, dd_peak=dates[p_i], dd_trough=dates[t_i],
        dd_intra_c=dd_intra_c, dd_intra_l=dd_intra_l,
        win_days=int((df.pnl > 0).sum()), lose_days=int((df.pnl < 0).sum()),
        flat_days=int((df.pnl == 0).sum()),
        day_streak_w=day_w, day_streak_l=day_l,
        trade_streak_w=tr_w, trade_streak_l=tr_l,
        sig_streak_w=sig_w, sig_streak_l=sig_l,
        trades=int(df.trades.sum()), fees=float(df.fees.sum()),
        trade_pnl_mean=float(trade_pnl.mean()) if len(trade_pnl) else np.nan,
        trade_win_rate=float((trade_pnl > 0).mean()) if len(trade_pnl) else np.nan,
        signal_win_rate=float(trade_won.mean()) if len(trade_won) else np.nan,
        blocked=int(df.blocked.sum()), max_peak_open=int(df.peak_open.max()),
        slots=slots, days_capped=int((df.peak_open >= slots).sum()),
        zero_trade_days=int((df.trades == 0).sum()), frozen_from=frozen_from)


def pct(x):
    return "n/a" if x != x else f"{x * 100:+.2f}%"


def report(m, df, trade_pnl, dates):
    print(f"\n{'=' * 86}")
    print(f"  {m['label']}")
    print(f"{'=' * 86}")
    print(f"  {m['days']:,} sessions   {dates[0]} -> {dates[-1]}   "
          f"{m['years']:.2f} years   {m['trades']:,} trades")

    print(f"\n  RETURN")
    print(f"    start ${m['equity0']:>14,.2f}      final ${m['final']:>16,.2f}")
    print(f"    total {pct(m['total']):>15}      CAGR  {pct(m['cagr']):>16}")
    print(f"    commissions paid ${m['fees']:>,.2f}")

    print(f"\n  RISK")
    print(f"    max drawdown, end-of-day      {pct(m['dd_eod']):>9}   "
          f"{m['dd_peak']} -> {m['dd_trough']}")
    print(f"    max drawdown, intraday close  {pct(m['dd_intra_c']):>9}")
    print(f"    max drawdown, intraday low    {pct(m['dd_intra_l']):>9}   "
          f"(worst price actually touched)")
    print(f"    Sharpe {m['sharpe']:.2f}      Sortino {m['sortino']:.2f}"
          f"      (daily returns, {TRADING_DAYS:.0f}d annualised, rf=0)")

    if m["frozen_from"] is not None:
        print(f"\n  *** ACCOUNT FROZE {m['frozen_from']} -- equity fell to the "
              f"reserve and (equity - reserve) / {m['slots']} would not buy one "
              f"share.")
        print(f"      {m['zero_trade_days']:,} of {m['days']:,} sessions traded "
              f"nothing. Every figure after that date is a flat line, not a "
              f"result.")

    print(f"\n  DAYS")
    traded = m["days"] - m["zero_trade_days"]
    print(f"    sessions {m['days']:,}   traded {traded:,}   "
          f"no trades {m['zero_trade_days']:,}")
    print(f"    winning {m['win_days']:,}   losing {m['lose_days']:,}   "
          f"flat {m['flat_days']:,}   "
          f"hit rate {m['win_days'] / traded * 100:.1f}% of days traded"
          if traded else "    no sessions traded")
    # By dollars and by percent these are different days, because the account
    # size moves. Printing one row's dollars beside another row's percent would
    # invent a day that never happened.
    for lbl, idx in (("best  by $", df.pnl.idxmax()), ("worst by $", df.pnl.idxmin()),
                     ("best  by %", df.ret.idxmax()), ("worst by %", df.ret.idxmin())):
        r = df.loc[idx]
        print(f"    {lbl} {r['date']}   ${r['pnl']:>13,.2f}   "
              f"{pct(r['ret']):>9}   on ${r['start_equity']:>12,.2f}")
    print(f"    mean {pct(df.ret.mean()):>9}   median {pct(df.ret.median()):>9}   "
          f"stdev {df.ret.std(ddof=1) * 100:.3f}%")

    print(f"\n  TRADES")
    print(f"    {m['trades']:,} total   mean P&L ${m['trade_pnl_mean']:+,.2f}   "
          f"profitable {m['trade_win_rate'] * 100:.1f}%   "
          f"hit +0.5% first {m['signal_win_rate'] * 100:.1f}%")
    print(f"    max positions open on any day {m['max_peak_open']}")
    print(f"    days that filled all {m['slots']} slots  {m['days_capped']:,}"
          f"   ({m['days_capped'] / m['days'] * 100:.1f}% of sessions)")
    print(f"    minutes wanting an entry with no slot or cash free "
          f"{m['blocked']:,}")

    print(f"\n  STREAKS")
    print(f"    consecutive winning days   {m['day_streak_w']:>4}")
    print(f"    consecutive losing days    {m['day_streak_l']:>4}")
    print(f"    consecutive winning trades {m['trade_streak_w']:>4}   (by P&L)")
    print(f"    consecutive losing trades  {m['trade_streak_l']:>4}   (by P&L)")
    print(f"    consecutive +0.5%-first    {m['sig_streak_w']:>4}   (by signal)")
    print(f"    consecutive -0.5%-first    {m['sig_streak_l']:>4}   (by signal)")


def table(title, rows, cols, headers):
    print(f"\n  {title}")
    print("    " + "  ".join(h.rjust(w) for h, w in headers))
    for _, r in rows.iterrows():
        print("    " + "  ".join(f(r).rjust(w) for f, w in cols))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SOXL")
    p.add_argument("--pct", type=float, default=0.005)
    p.add_argument("--equity", type=float, default=100_000)
    p.add_argument("--reserve", type=float, default=25_000)
    p.add_argument("--slots", type=int, default=50)
    p.add_argument("--since", default=None)
    p.add_argument("--until", default=None)
    p.add_argument("--close-losers", action="store_true",
                   help="RUN 2 instead: sell the loser on the touch")
    p.add_argument("--top", type=int, default=10, help="rows in the best/worst tables")
    p.add_argument("--outdir", default="band_lab/v2_dev/out")
    a = p.parse_args()

    park = not a.close_losers
    name = "RUN 2  CLOSE the losers" if a.close_losers else "RUN 1  PARK the losers"
    slots = 1 if a.close_losers else a.slots

    sessions = load_sessions(a.symbol, a.since, a.until)
    if not sessions:
        raise SystemExit("no complete sessions in range")
    print(f"loaded {len(sessions):,} complete sessions")

    os.makedirs(a.outdir, exist_ok=True)
    results = {}
    for tag, comm in (("GROSS  no commission", None),
                      ("NET    IBKR tiered", ibkr_tiered)):
        df, tp, tw = run_series(sessions, a.pct, park, a.equity, a.reserve,
                                slots, comm)
        m = metrics(df, a.equity, tp, tw, f"{name}   |   {tag}", slots)
        report(m, df, tp, list(df.date))

        top = df.nlargest(a.top, "pnl")[["date", "pnl", "ret", "trades", "win_rate"]]
        bot = df.nsmallest(a.top, "pnl")[["date", "pnl", "ret", "trades", "win_rate"]]
        cols = [(lambda r: str(r["date"]), 10), (lambda r: f"{r['pnl']:+,.2f}", 14),
                (lambda r: f"{r['ret'] * 100:+.2f}%", 8),
                (lambda r: f"{r['trades']:.0f}", 6),
                (lambda r: f"{r['win_rate'] * 100:.0f}%", 5)]
        heads = [("date", 10), ("P&L $", 14), ("ret", 8), ("trd", 6), ("win", 5)]
        table(f"BEST {a.top} DAYS", top, cols, heads)
        table(f"WORST {a.top} DAYS", bot, cols, heads)

        dates = list(df.date)
        for lbl, fl in (("winning", (df.pnl > 0).to_numpy()),
                        ("losing", (df.pnl < 0).to_numpy())):
            spans = run_spans(dates, fl)[:5]
            print(f"\n  LONGEST {lbl.upper()} DAY STREAKS")
            for s, e, n in spans:
                seg = df[(df.date >= s) & (df.date <= e)]
                print(f"    {n:>3} days   {s} -> {e}   "
                      f"${seg.pnl.sum():>+14,.2f}")

        # The window has to be in the filename. Without it a --since run
        # silently overwrites the full-history artifact with a different
        # study, and the file on disk stops matching the numbers it is cited
        # for.
        slug = ("run2" if a.close_losers else "run1") + "_" + tag.split()[0].lower()
        span = f"{df.date.iloc[0]}_{df.date.iloc[-1]}"
        path = os.path.join(a.outdir,
                            f"harvest_series_{a.symbol}_{span}_{slug}.csv")
        df.to_csv(path, index=False)
        results[tag] = (m, df, path)
        print(f"\n  per-day results -> {path}")

    print(f"\n{'=' * 86}")
    print(f"  GROSS vs NET")
    print(f"{'=' * 86}")
    g, n = results["GROSS  no commission"][0], results["NET    IBKR tiered"][0]
    print(f"    {'':22}{'gross':>18}{'net':>18}")
    for lbl, key, f in (("final equity", "final", lambda v: f"${v:,.2f}"),
                        ("total return", "total", pct),
                        ("CAGR", "cagr", pct),
                        ("max DD (EOD)", "dd_eod", pct),
                        ("max DD (intraday)", "dd_intra_c", pct),
                        ("Sharpe", "sharpe", lambda v: f"{v:.2f}"),
                        ("commissions", "fees", lambda v: f"${v:,.2f}")):
        print(f"    {lbl:22}{f(g[key]):>18}{f(n[key]):>18}")
    print(f"\n    commission drag on CAGR: "
          f"{(g['cagr'] - n['cagr']) * 100:.2f} percentage points\n")


if __name__ == "__main__":
    main()
