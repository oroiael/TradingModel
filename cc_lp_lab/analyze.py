"""Headline results, controls and mechanism diagnostics for CC + long-dated put."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import data, backtest as bt

OUT = bt.OUT
COST = dict(cost_per_contract=0.65, share_cost=0.005, slip_call=0.055, slip_put=0.019)
pd.set_option("display.width", 220)


def buy_hold(start=100_000.0, d0=None, d1=None):
    c = data.daily_close()
    c = c[(c.index >= (d0 or bt.START)) & (c.index <= (d1 or bt.END))]
    s10 = data.spot_at(600)
    n = int(start // float(s10.loc[c.index[0], "px"]))
    return pd.DataFrame({"equity": n * c + (start - n * float(s10.loc[c.index[0], "px"]))})


def yearly(eq):
    e = eq["equity"]
    out = {}
    for y, g in e.groupby(e.index.year):
        prev = e[e.index < g.index[0]]
        out[y] = g.iloc[-1] / (prev.iloc[-1] if len(prev) else g.iloc[0]) - 1
    return pd.Series(out)


def fmt(df, pct=(), money=(), num=()):
    f = {}
    for c in pct:   f[c] = "{:+.2%}".format
    for c in money: f[c] = "{:,.0f}".format
    for c in num:   f[c] = "{:.2f}".format
    return df.to_string(formatters=f)


def main():
    runs = {
        "Strategy: CC + long put (frictionless)": bt.run(),
        "Strategy: CC + long put (with costs)": bt.run(**COST),
        "Control: covered call only (with costs)": bt.run(use_put=False, **COST),
        "Control: shares + long put only (with costs)": bt.run(use_call=False, **COST),
    }
    rows, ycols = [], {}
    for k, (eq, led, meta) in runs.items():
        s = bt.stats(eq, k); s["pnl"] = meta["pnl"]; rows.append(s); ycols[k] = yearly(eq)
    bh = buy_hold()
    rows.append(bt.stats(bh, "Benchmark: buy & hold SOXL")); ycols["Benchmark: buy & hold SOXL"] = yearly(bh)

    print("=" * 118)
    print("HEADLINE   $100,000 start | 2022-01-03 -> 2026-07-02 (4.49 yrs, 235 weekly cycles)")
    print("           costs = $0.65/contract + $0.005/share + measured half-spread (5.5% call, 1.9% put)")
    print("=" * 118)
    hd = pd.DataFrame([{"": r["label"], "final $": r["final"], "total": r["total_ret"],
                        "CAGR": r["cagr"], "max DD": r["maxdd"], "ann vol": r["vol"],
                        "Sharpe": r["sharpe"]} for r in rows]).set_index("")
    print(hd.to_string(formatters={"final $": "{:,.0f}".format, "total": "{:+.1%}".format,
                                   "CAGR": "{:+.2%}".format, "max DD": "{:.1%}".format,
                                   "ann vol": "{:.1%}".format, "Sharpe": "{:.2f}".format}))

    print("\n" + "=" * 118); print("CALENDAR-YEAR RETURNS  (2022 from 01-03; 2026 through 07-02)"); print("=" * 118)
    print(pd.DataFrame(ycols).T.to_string(float_format=lambda v: f"{v:+.1%}"))

    print("\n" + "=" * 118); print("P&L ATTRIBUTION BY LEG ($)   -- legs sum exactly to (final - 100,000)"); print("=" * 118)
    att = pd.DataFrame({r["label"]: r["pnl"] for r in rows if "pnl" in r}).T
    att["TOTAL"] = att.sum(axis=1)
    print(att.to_string(float_format=lambda v: f"{v:>12,.0f}"))

    eq, led, meta = runs["Strategy: CC + long put (with costs)"]
    eq.to_csv(f"{OUT}/equity_base.csv"); led.to_csv(f"{OUT}/ledger_base.csv", index=False)
    buy_hold().to_csv(f"{OUT}/equity_buyhold.csv")
    for tag, key in [("cc_only", "Control: covered call only (with costs)"),
                     ("put_only", "Control: shares + long put only (with costs)")]:
        runs[key][0].to_csv(f"{OUT}/equity_{tag}.csv")

    w = led[led.act == "SELL_CALL"].copy()
    asg, exp = led[led.act == "CALL_ASSIGNED"], led[led.act == "CALL_EXPIRED"]
    print("\n" + "=" * 118); print("CALL LEG -- what the rule actually did"); print("=" * 118)
    print(f"weeks traded {len(w)}   assigned {len(asg)} ({len(asg)/len(w):.1%})   "
          f"expired worthless {len(exp)} ({len(exp)/len(w):.1%})")
    fresh, stick = w[w.sticky_write == 0], w[w.sticky_write == 1]
    print(f"\n  FRESH writes (new share position)  n={len(fresh):>3}  "
          f"median {fresh.otm_pct.median():+.2f}% OTM   median premium {100*(fresh.px/fresh.spot).median():.2f}% of spot")
    print(f"  STICKY re-writes (same strike)     n={len(stick):>3}  "
          f"median {stick.otm_pct.median():+.2f}% OTM   median premium {100*(stick.px/stick.spot).median():.2f}% of spot")
    print(f"  written IN the money               n={int(w.itm_at_write.sum())}")
    print("\n  -> 'two strikes' is a FIXED-DOLLAR rule on a moving stock. What it means by year:")
    g = w.groupby(w.date.dt.year).apply(lambda x: pd.Series({
        "median spot": x.spot.median(),
        "fresh-write % OTM": x[x.sticky_write == 0].otm_pct.median(),
        "all-write % OTM": x.otm_pct.median(),
        "premium % of spot": 100 * (x.px / x.spot).median(),
        "weeks": len(x)}), include_groups=False)
    print(g.to_string(float_format=lambda v: f"{v:8.2f}"))
    rl, cur = [], 0
    for _, r in led[led.act.isin(["SELL_CALL", "CALL_ASSIGNED"])].iterrows():
        if r.act == "SELL_CALL": cur += 1
        else: rl.append(cur); cur = 0
    rl = pd.Series(rl + ([cur] if cur else []))
    print(f"\n  consecutive weeks stuck on one sticky strike: median {rl.median():.0f}, mean {rl.mean():.1f}, max {rl.max():.0f}")
    print(f"  total premium collected  ${(w.px*w.qty*100).sum():>12,.0f}")
    print(f"  intrinsic paid on assignment ${(asg.itm*asg.qty*100).sum():>9,.0f}")
    print(f"  NET call leg             ${meta['pnl']['calls']:>12,.0f}")

    print("\n" + "=" * 118); print("WHIPSAW -- the structural cost of being called out and rebuying"); print("=" * 118)
    rb = []
    for _, a in asg.iterrows():
        nxt = led[(led.date > a.date) & (led.act == "BUY_SHARES")]
        if len(nxt):
            n0 = nxt.iloc[0]
            rb.append(dict(K=a.K, fri=a.px, rebuy=n0.px, days=(n0.date - a.date).days,
                           cap_pct=100*(a.px - a.K)/a.K, gap_pct=100*(n0.px - a.px)/a.px,
                           tot_pct=100*(n0.px - a.K)/a.K))
    r = pd.DataFrame(rb)
    print(f"n={len(r)} called-out-then-rebought events (median {r.days.median():.0f} days flat)")
    print(f"  upside surrendered at expiry (Fri close vs strike) : median {r.cap_pct.median():+.2f}%  mean {r.cap_pct.mean():+.2f}%")
    print(f"  weekend gap paid on rebuy (Mon 10:00 vs Fri close) : median {r.gap_pct.median():+.2f}%  mean {r.gap_pct.mean():+.2f}%")
    print(f"  combined round-trip (rebuy vs strike sold at)      : median {r.tot_pct.median():+.2f}%  mean {r.tot_pct.mean():+.2f}%")
    print(f"  rebought ABOVE the strike sold at: {(r.tot_pct>0).sum()} of {len(r)} ({(r.tot_pct>0).mean():.1%})")

    print("\n" + "=" * 118); print("PUT LEG"); print("=" * 118)
    pb, pex, pxp = led[led.act == "BUY_PUT"], led[led.act == "PUT_EXERCISED"], led[led.act == "PUT_EXPIRED"]
    payoff = float((pex.qty * (pex.K - pex.px) * 100).sum())
    print(f"put cycles {len(pb)}   median DTE at purchase {pb.dte.median():.0f}d   "
          f"median strike {pb.otm_pct.median():.2f}% OTM ({bt.__doc__.count('x') and 2} listed strikes)")
    print(f"  expired worthless {len(pxp)}   exercised ITM {len(pex)}")
    print(f"  premium paid   ${payoff - meta['pnl']['puts']:>12,.0f}")
    print(f"  payoff received ${payoff:>11,.0f}")
    print(f"  NET put leg    ${meta['pnl']['puts']:>12,.0f}   "
          f"(= {meta['pnl']['puts']/100000:.1%} of starting capital)")
    print("\n  put purchases (each cycle):")
    print(pb[["date", "K", "spot", "otm_pct", "dte", "px", "qty"]].to_string(
        index=False, float_format=lambda v: f"{v:.2f}"))

    print("\n" + "=" * 118); print("MARK SOURCES for executed option trades"); print("=" * 118)
    m = meta["marks"]; tot = sum(m.values())
    print(f"  real 5-min trade print at 10:00 : {m['print']:>4}  ({m['print']/tot:.1%})")
    print(f"  real print within +/-30 min     : {m['print_near']:>4}  ({m['print_near']/tot:.1%})")
    print(f"  model (EOD IV repriced to 10:00): {m['model']:>4}  ({m['model']/tot:.1%})")
    print(f"  unpriceable                     : {m['miss']:>4}")


if __name__ == "__main__":
    main()
