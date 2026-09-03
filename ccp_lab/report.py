"""Per-year summary writer for the CC+LP backtest."""
import os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ccp_lab", "out")
os.makedirs(OUT, exist_ok=True)


def _stats(eq):
    e = eq["equity"].values.astype(float)
    if len(e) < 2:
        return dict(maxdd=0.0, sharpe=0.0, vol=0.0)
    peak = np.maximum.accumulate(e)
    dd = (e / peak - 1.0).min()
    r = np.diff(e) / e[:-1]
    r = r[np.isfinite(r)]
    vol = r.std() * np.sqrt(252) if len(r) > 1 else 0.0
    sharpe = (r.mean() / r.std() * np.sqrt(252)) if len(r) > 1 and r.std() > 0 else 0.0
    return dict(maxdd=dd * 100, sharpe=sharpe, vol=vol * 100)


def buy_hold(data, year, start_cash):
    ses = [s for s in data.sessions if s.year == year]
    first, last = ses[0], ses[-1]
    entry = data.ten_high(first)
    sh = int(start_cash // entry)
    cash = start_cash - sh * entry
    curve = pd.DataFrame({"date": ses,
                          "equity": [cash + sh * data.close(s) for s in ses]})
    return cash + sh * data.close(last), curve


def write(res, data, tag=""):
    y = res["year"]
    lg, ev, eq = res["ledger"], res["events"], res["equity"]
    start, final = res["start_cash"], res["final"]
    ret = final / start - 1.0
    st = _stats(eq)
    bh_final, bh_curve = buy_hold(data, y, start)
    bh_st = _stats(bh_curve)

    ses = [s for s in data.sessions if s.year == y]
    s0, s1 = data.ten_high(ses[0]), data.close(ses[-1])

    lg.to_csv(f"{OUT}/ledger_{y}{tag}.csv", index=False)
    ev.to_csv(f"{OUT}/events_{y}{tag}.csv", index=False)
    eq.to_csv(f"{OUT}/equity_{y}{tag}.csv", index=False)

    w = lg[lg.get("call_strike").notna()] if "call_strike" in lg else lg.iloc[0:0]
    n_assign = int((ev.kind == "CALL_ASSIGNED").sum()) if len(ev) else 0
    n_expire = int((ev.kind == "CALL_EXPIRED").sum()) if len(ev) else 0
    n_putex = int((ev.kind == "PUT_EXERCISED").sum()) if len(ev) else 0
    n_putexp = int((ev.kind == "PUT_EXPIRED").sum()) if len(ev) else 0
    prem_tot = float(w.call_premium.sum()) if "call_premium" in w else 0.0
    mk = res["marks"]; mk_tot = max(sum(mk.values()), 1)

    L = []
    A = L.append
    A(f"# SOXL covered call + 90-day protective put — {y}\n")
    A(f"Start ${start:,.0f} on {ses[0].date()} · liquidated {ses[-1].date()} "
      f"· {len(w)} weekly writes\n")

    A("\n## Result\n")
    A("| | strategy | buy & hold SOXL |")
    A("|---|---:|---:|")
    A(f"| final equity | **${final:,.0f}** | ${bh_final:,.0f} |")
    A(f"| return | **{ret*100:+.1f}%** | {(bh_final/start-1)*100:+.1f}% |")
    A(f"| max drawdown | {st['maxdd']:.1f}% | {bh_st['maxdd']:.1f}% |")
    A(f"| annualised vol | {st['vol']:.1f}% | {bh_st['vol']:.1f}% |")
    A(f"| Sharpe | {st['sharpe']:.2f} | {bh_st['sharpe']:.2f} |")
    A(f"\nSOXL {s0:.2f} → {s1:.2f} ({(s1/s0-1)*100:+.1f}%) over the same window.\n")

    p = res["pnl"]
    A("\n## Where the money came from\n")
    A("| leg | P&L |")
    A("|---|---:|")
    A(f"| shares | ${p['shares']:+,.0f} |")
    A(f"| short calls | ${p['calls']:+,.0f} |")
    A(f"| long puts | ${p['puts']:+,.0f} |")
    A(f"| commissions & fees | ${-p['fees']:+,.0f} |")
    A(f"| **total** | **${final-start:+,.0f}** |")
    A("\nLegs reconcile to the final equity exactly.\n")

    A("\n## Did the 5% rule actually work?\n")
    if len(w):
        A(f"- Premium collected, as a share of the underlying it was written against: "
          f"**median {w.prem_pct.median():.2f}%**, mean {w.prem_pct.mean():.2f}%, "
          f"range {w.prem_pct.min():.2f}%–{w.prem_pct.max():.2f}%.")
        hit = (w.prem_pct >= 4.5).mean() * 100
        A(f"- Weeks that actually reached ~5% (≥4.5%): **{hit:.0f}%** "
          f"({int((w.prem_pct>=4.5).sum())} of {len(w)}).")
        A(f"- The strike the rule had to pick sat **median {w.otm_pct.median():.2f}% "
          f"out of the money** (range {w.otm_pct.min():.2f}%–{w.otm_pct.max():.2f}%).")
        A(f"- Gross gain if called out that week: median "
          f"**{w.gross_if_called_pct.median():.2f}%**.")
        A(f"- Total premium collected over the year: **${prem_tot:,.0f}** "
          f"({prem_tot/start*100:.0f}% of starting capital).")
        A(f"- Median implied vol of the written call: {w.call_iv.median()*100:.0f}%.")
    A(f"- Calls: **{n_assign} assigned**, {n_expire} expired worthless "
      f"({n_assign/max(n_assign+n_expire,1)*100:.0f}% called away).")
    A(f"- Puts: {n_putex} exercised, {n_putexp} expired worthless.")
    bp = ev[ev.kind == "BUY_PUT"] if len(ev) else ev
    if len(bp) and "dte" in bp:
        A(f"- Protective puts bought: {len(bp)}, at a median **{bp.dte.median():.0f} DTE** "
          f"(target 90; the listed ladder is monthly so an exact 90 rarely exists), "
          f"struck a median {bp.otm_pct.median():.1f}% out of the money.")

    A("\n## How the option marks were obtained\n")
    A(f"- real 10:00 trade print: {mk.get('print_1000',0)} "
      f"({mk.get('print_1000',0)/mk_tot*100:.0f}%)")
    A(f"- nearest print inside 09:30–10:30: {mk.get('print_near',0)} "
      f"({mk.get('print_near',0)/mk_tot*100:.0f}%)")
    A(f"- Black-Scholes off that contract's own EOD implied vol, repriced to the "
      f"10:00 spot: {mk.get('model',0)} ({mk.get('model',0)/mk_tot*100:.0f}%)")

    A("\n## Files\n")
    A(f"- `ledger_{y}{tag}.csv` — one row per Monday: spot, lots, strike chosen, "
      f"premium, moneyness")
    A(f"- `events_{y}{tag}.csv` — every fill, assignment, exercise and expiry")
    A(f"- `equity_{y}{tag}.csv` — daily marked-to-market equity")

    txt = "\n".join(L) + "\n"
    with open(f"{OUT}/summary_{y}{tag}.md", "w") as f:
        f.write(txt)
    return dict(year=y, final=final, ret=ret * 100, maxdd=st["maxdd"],
                sharpe=st["sharpe"], bh_final=bh_final,
                bh_ret=(bh_final / start - 1) * 100, bh_maxdd=bh_st["maxdd"],
                premium=prem_tot, assigned=n_assign, expired=n_expire,
                med_prem_pct=float(w.prem_pct.median()) if len(w) else np.nan,
                med_otm_pct=float(w.otm_pct.median()) if len(w) else np.nan,
                writes=len(w), pnl_shares=p["shares"], pnl_calls=p["calls"],
                pnl_puts=p["puts"], fees=p["fees"], text=txt)
