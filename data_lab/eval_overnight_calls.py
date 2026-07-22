#!/usr/bin/env python3
"""
eval_overnight_calls.py  --  capture the OVERNIGHT drift (finding B') with the CHEAP
CALLS (finding E) instead of the ETF, so down months are capped to premium.

Real intraday OPTION prices (raw_data 5-min files, 2022-2026): BUY a call at the
15:55 close, SELL it at the 09:30 next-day open. No pricing model -- actual close
and open prints, so theta, IV change and the delta move are all real. Strikes are
chosen from the daily EOD underlying.

THE decisive variable is the option bid/ask: a nightly round-trip pays ~half-spread
twice. The 5-min data is TRADE prices, so we model the spread as a haircut `h` (buy
at price*(1+h), sell at price*(1-h)) and SWEEP it. Overnight spreads are widest at
the 09:30 open, so realistic h is toward the high end.

Documented proxies: strike picked from daily EOD underlying (~16:00) vs the 15:55
option print; 'open'=09:30 bar open, 'close'=15:55 bar close; spread modelled, not
observed. Coverage: a night is tradeable only if the chosen contract has both a
15:55 print on D and a 09:30 print on D+1 (near-money is dense, ~99%).
"""
from __future__ import annotations
import sys, glob, pickle
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "call_spread_lab"))
from data_loader import load_options, underlying_daily_from_options  # noqa: E402

OUT = Path(__file__).resolve().parent / "outputs"; OUT.mkdir(exist_ok=True)
SCRATCH = Path("/tmp/claude-0/-home-user-TradingModel/3ee6862d-4424-5812-9b50-ba533ce0c5cb/scratchpad")
CACHE = SCRATCH / "opt_open_close.pkl"
RAW = Path(__file__).resolve().parent.parent / "raw_data"
ANN = 252
pd.set_option("display.width", 210)


def hr(t): print("\n" + "=" * 88 + f"\n{t}\n" + "=" * 88)


def build_open_close():
    """{(date,right,exp,strike) -> (open_0930, close_1555)} from the 5-min option files."""
    if CACHE.exists():
        print(f"loading cached open/close from {CACHE}")
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    print("building 09:30 open / 15:55 close per option-contract-day (~3 min)...")
    files = [p for p in glob.glob(str(RAW / "SOXL_intraday_5m_exp_*.csv"))
             if Path(p).stat().st_size > 10_000]
    parts = []
    for i, p in enumerate(files):
        df = pd.read_csv(p, usecols=["expiration", "strike", "right", "timestamp",
                                     "open", "close", "volume"])
        df = df[(df["right"].str.upper() == "CALL")]
        if df.empty:
            continue
        ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
        df["date"] = ts.dt.date; df["hm"] = ts.dt.strftime("%H:%M")
        df["expiration"] = pd.to_datetime(df["expiration"]).dt.date
        op = df[df["hm"] == "09:30"].groupby(["date", "expiration", "strike"])["open"].first()
        cl = df[df["hm"] == "15:55"].groupby(["date", "expiration", "strike"])["close"].first()
        g = pd.DataFrame({"o": op, "c": cl}).dropna(how="all").reset_index()
        parts.append(g)
        if (i + 1) % 150 == 0:
            print(f"  {i+1}/{len(files)}")
    allg = pd.concat(parts, ignore_index=True)
    d = {}
    for r in allg.itertuples(index=False):
        d[(r.date, "CALL", r.expiration, float(r.strike))] = (float(r.o) if r.o == r.o else np.nan,
                                                              float(r.c) if r.c == r.c else np.nan)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(d, f)
    print(f"built {len(d):,} contract-days -> cached")
    return d


def curve_stats(r):
    r = np.asarray(r); eq = np.cumprod(1 + r)
    cagr = eq[-1] ** (ANN / len(r)) - 1 if eq[-1] > 0 else -1
    sharpe = r.mean() / r.std(ddof=1) * np.sqrt(ANN) if r.std() > 0 else np.nan
    return dict(cagr=cagr, sharpe=sharpe, end=eq[-1]), eq


def main():
    hr("LOAD daily underlying + intraday option open/close")
    opt = load_options()
    u = underlying_daily_from_options(opt).sort_values("trade_date").reset_index(drop=True)
    spot = dict(zip(u["trade_date"].dt.date, u["close"]))
    tds = list(u["trade_date"].dt.date)
    nextday = {tds[i]: tds[i + 1] for i in range(len(tds) - 1)}
    # available whole-strike calls per (date, dte-target) from daily chain
    oc = build_open_close()
    # index available strikes/exps per date from the cache keys
    by_date = {}
    for (d, r, e, k) in oc:
        by_date.setdefault(d, []).append((e, k))
    print(f"nights with intraday call data: {len(by_date)}  "
          f"{min(by_date)} -> {max(by_date)}")

    def pick_call(D, dte_t, mny):
        """nearest call to spot*(1+mny) at ~dte_t DTE that has a 15:55 print on D."""
        s = spot.get(D)
        if s is None or D not in by_date:
            return None
        cand = [(e, k) for (e, k) in by_date[D]
                if 3 <= (pd.Timestamp(e) - pd.Timestamp(D)).days <= 200]
        if not cand:
            return None
        target_k = s * (1 + mny)
        # nearest DTE first, then nearest strike
        cand.sort(key=lambda ek: (abs((pd.Timestamp(ek[0]) - pd.Timestamp(D)).days - dte_t),
                                  abs(ek[1] - target_k)))
        for e, k in cand[:8]:
            c_close = oc.get((D, "CALL", e, k), (np.nan, np.nan))[1]
            if c_close and c_close > 0.05:
                return (e, k, c_close)
        return None

    hr("1.  OVERNIGHT CALL round-trip: mean nightly return by strike x DTE (no spread)")
    print(f"  {'config':22s} {'nights':>7} {'mean/night':>11} {'median':>8} {'win%':>6} "
          f"{'Sharpe(ann)':>11} {'worst':>7}")
    configs = [("ATM 14D", 0.00, 14), ("ATM 30D", 0.00, 30), ("+3% 30D", 0.03, 30),
               ("+5% 30D", 0.05, 30), ("+5% 14D", 0.05, 14), ("+8% 30D", 0.08, 30)]
    series = {}
    for name, mny, dte_t in configs:
        rets, dates = [], []
        for D in tds:
            D1 = nextday.get(D)
            if D1 is None:
                continue
            pick = pick_call(D, dte_t, mny)
            if pick is None:
                continue
            e, k, buy = pick
            sell = oc.get((D1, "CALL", e, k), (np.nan, np.nan))[0]     # 09:30 open on D+1
            if not (sell and sell > 0):
                continue
            rets.append(sell / buy - 1); dates.append(D1)
        rets = np.array(rets)
        if len(rets) < 30:
            print(f"  {name:22s} {len(rets):>7} (too few)"); continue
        series[name] = (np.array(dates), rets)
        sh = rets.mean() / rets.std() * np.sqrt(ANN)
        print(f"  {name:22s} {len(rets):>7} {rets.mean():>+11.2%} {np.median(rets):>+8.2%} "
              f"{np.mean(rets>0):>6.0%} {sh:>+11.2f} {rets.min():>+7.0%}")

    # ---------------------------------------------------------------- 2 spread sweep
    hr("2.  DOES IT SURVIVE THE OPTION BID/ASK?  (round-trip pays ~2*h of premium)")
    base = "+5% 30D"
    if base in series:
        dts_b, r_b = series[base]
        print(f"  config {base}: nightly round-trip return net of half-spread h")
        print(f"  {'h (half-spread)':>16} {'mean/night':>11} {'win%':>6} {'ann Sharpe':>11} {'compounded (risk 20%/nt)':>26}")
        for h in (0.0, 0.025, 0.05, 0.075, 0.10):
            net = (1 - h) / (1 + h) * (1 + r_b) - 1        # buy*(1+h), sell*(1-h)
            cs, _ = curve_stats(0.20 * net)                # risk 20% of capital per night
            sh = net.mean() / net.std() * np.sqrt(ANN)
            print(f"  {h:>15.1%} {net.mean():>+11.2%} {np.mean(net>0):>6.0%} {sh:>+11.2f} "
                  f"{cs['end']:>24.1f}x")
        print("  (near-ATM option spread/mid ~10% => h~5%; the 09:30 OPEN is the widest-spread"
              " bar,\n   so realistic h is 5-10%. This is the make-or-break number.)")

    # ---------------------------------------------------------------- 3 downside / by year
    hr("3.  DOWNSIDE CAP & BY-YEAR  (does the call cap the down-month bleed the ETF suffers?)")
    if base in series:
        dts_b, r_b = series[base]
        dfb = pd.DataFrame({"date": pd.to_datetime(dts_b), "r": r_b})
        dfb["year"] = dfb["date"].dt.year
        print(f"  {base}, no spread:  worst night {r_b.min():+.0%}  best {r_b.max():+.0%}  "
              f"(the ETF-overnight worst night was about -3x the index gap)")
        print("  by year (mean/night, win%, n):")
        for y, g in dfb.groupby("year"):
            print(f"    {y}: {g['r'].mean():+.2%}/night  win {np.mean(g['r']>0):.0%}  n={len(g)}")

    _plot(series)
    _caveats()
    print(f"\nsaved {OUT/'eval_overnight_calls.png'}")


def _plot(series):
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    for name in ["ATM 30D", "+5% 30D", "+8% 30D"]:
        if name in series:
            d, r = series[name]
            ax[0].plot(pd.to_datetime(d), np.cumprod(1 + 0.20 * r),
                       label=f"{name} (risk20%/nt, 0 spread)", lw=1.2)
    ax[0].set_yscale("log"); ax[0].legend(); ax[0].set_title("overnight-call equity (NO spread — optimistic)")
    ax[0].set_ylabel("growth of $1 (log)")
    if "+5% 30D" in series:
        d, r = series["+5% 30D"]
        for h, c in [(0.0, "tab:green"), (0.05, "tab:orange"), (0.10, "tab:red")]:
            net = (1 - h) / (1 + h) * (1 + r) - 1
            ax[1].plot(pd.to_datetime(d), np.cumprod(1 + 0.20 * net), label=f"h={h:.0%}", color=c, lw=1.2)
        ax[1].set_yscale("log"); ax[1].legend()
        ax[1].set_title("+5% 30D overnight call vs half-spread h (risk 20%/night)")
    fig.tight_layout(); fig.savefig(OUT / "eval_overnight_calls.png", dpi=110)


def _caveats():
    hr("PROXIES / ASSUMPTIONS  &  ADDITIONAL DATA")
    print("""  - Option prices are TRADE prints (5-min open/close), not bid/ask; the spread is
    MODELLED via h and swept -- this is the decisive assumption, not an observation.
  - Strike chosen from the daily EOD (~16:00) underlying vs the 15:55 option print.
  - 'open' = 09:30 bar open (widest spread of the day), 'close' = 15:55 bar close.
  - Coverage 2022-2026 (better than the ETF test) but only contracts with both a
    15:55 print on D and a 09:30 print on D+1; near-money is ~99% covered.
  ADDITIONAL DATA: intraday option BID/ASK (not just trades) at 15:55 and 09:30
    would replace the modelled spread with the real one -- HIGHEST value here, since
    the spread is exactly what decides whether this works.""")


if __name__ == "__main__":
    main()
