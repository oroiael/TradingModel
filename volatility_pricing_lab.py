#!/usr/bin/env python3
"""
SOXL Volatility & Option-Pricing Lab
====================================

Analytical test suite over BOTH datasets used by the other projects in this
repo:

    * SOXL_5min_3Years.csv                    (5-minute underlying bars)
    * SOXL_Options_2024/2025/2026.csv         (detailed daily EOD option
                                               chains via soxl_options_loader)

Purpose: measure how SOXL options are priced RELATIVE TO the underlying and
surface every disparity / irregularity / opportunity that a weekly
income-generation strategy could harvest.  Sections:

    S1  Underlying volatility anatomy (realized vol, weekly move
        distribution, overnight vs intraday, tails, decay drag)
    S2  Implied vs subsequently-realized vol  (variance risk premium)
        at 7 / 14 / 30 / 60 / 90 / 180-day horizons
    S3  Skew: 25-delta put vs 25-delta call, and ATM term structure
    S4  Put-call parity: implied forward / implied carry per expiry,
        strike-level parity residuals, executable conversion-reversal scan
    S5  Liquidity & spread-cost surface (delta x DTE x right)
    S6  Weekly short-premium P&L grid: every permutation of
        {put, call, strangle, straddle} x delta target x entry day,
        priced with the project's 20%-of-spread execution rule
    S7  Defined-risk overlays: wing cost (condor vs naked), jade lizard
        feasibility scan
    S8  Diagonal economics: weekly decay bleed of a 90-180 DTE long put
        vs weekly short-premium collected (harvest ratio)
    S9  Irregularity scans: zero-IV rows with live quotes, stale quote
        detection, largest weekly IV under-predictions (blow-up ledger)

Execution-price convention (project standard, applied everywhere):
    sell  = bid + 0.20 * (ask - bid)
    buy   = ask - 0.20 * (ask - bid)
    quotes with bid <= 0 or ask < bid are rejected as illiquid.

All numbers come from the data files; nothing is simulated with
Black-Scholes.  Where a section needs a risk-free rate it is EXTRACTED from
put-call parity itself (cross-strike regression), not assumed.

Outputs:
    qa/pricing_lab_report.txt      full text report (also printed)
    pricing_lab/*.csv              machine-readable tables per section
"""

from pathlib import Path

import numpy as np
import pandas as pd

from soxl_options_loader import ROOT, RAW_FILES

OUT_DIR = Path(__file__).resolve().parent / "pricing_lab"
QA_DIR = Path(__file__).resolve().parent / "qa"
REPORT = []

ANN = 252  # trading days per year


# --------------------------------------------------------------------------
# report helpers
# --------------------------------------------------------------------------
def emit(txt=""):
    print(txt)
    REPORT.append(txt)


def section(title):
    emit()
    emit("=" * 78)
    emit(title)
    emit("=" * 78)


def table(df, max_rows=40, floatfmt="{:,.4f}"):
    with pd.option_context("display.width", 120, "display.max_columns", 30,
                           "display.float_format", floatfmt.format):
        emit(df.head(max_rows).to_string())


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def load_options():
    """Raw ThetaData exports with quotes, greeks and IV (919k rows)."""
    usecols = ["expiration", "strike", "right", "bid", "ask", "implied_vol",
               "trade_date", "underlying_price", "delta", "volume"]
    frames = []
    for name in RAW_FILES:
        p = ROOT / name
        if not p.exists() or p.stat().st_size < 1000:
            raise FileNotFoundError(f"{name} missing -- run 'git lfs pull'")
        df = pd.read_csv(p, low_memory=False, usecols=usecols)
        for c in ("trade_date", "expiration"):
            fmt = "%m/%d/%y" if "/" in str(df[c].iloc[0]) else "%Y-%m-%d"
            df[c] = pd.to_datetime(df[c], format=fmt)
        frames.append(df)
    f = pd.concat(frames, ignore_index=True)
    f = f.drop_duplicates(["trade_date", "expiration", "strike", "right"],
                          keep="first")
    f["dte"] = (f["expiration"] - f["trade_date"]).dt.days
    f["mid"] = (f["bid"] + f["ask"]) / 2
    f["spread"] = f["ask"] - f["bid"]
    f["liquid"] = (f["bid"] > 0) & (f["ask"] >= f["bid"])
    f["sell_px"] = f["bid"] + 0.20 * f["spread"]
    f["buy_px"] = f["ask"] - 0.20 * f["spread"]
    f["mness"] = f["strike"] / f["underlying_price"]
    return f


def load_bars():
    b = pd.read_csv(ROOT / "SOXL_5min_3Years.csv")
    b["dt"] = pd.to_datetime(b["Date"].str.slice(0, 17),
                             format="%Y%m%d %H:%M:%S")
    b["date"] = b["dt"].dt.normalize()
    b["time"] = b["dt"].dt.time
    return b


def daily_frame(bars):
    g = bars.groupby("date")
    d = pd.DataFrame({
        "open": g["Open"].first(),
        "high": g["High"].max(),
        "low": g["Low"].min(),
        "close": g["Close"].last(),
        "volume": g["Volume"].sum(),
        # realized variance from 5-min log returns (intraday only)
        "rv5_var": bars.groupby("date")["Close"].apply(
            lambda s: (np.diff(np.log(s)) ** 2).sum()),
    })
    d["ret_cc"] = np.log(d["close"] / d["close"].shift(1))
    d["ret_on"] = np.log(d["open"] / d["close"].shift(1))   # overnight gap
    d["ret_id"] = np.log(d["close"] / d["open"])            # intraday
    return d


# --------------------------------------------------------------------------
# S1  underlying volatility anatomy
# --------------------------------------------------------------------------
def s1_underlying(daily, bars):
    section("S1  UNDERLYING VOLATILITY ANATOMY  (5-min file, "
            f"{daily.index.min().date()} -> {daily.index.max().date()})")
    r = daily["ret_cc"].dropna()
    emit(f"daily close-close log returns: n={len(r)}  mean={r.mean():+.4%}  "
         f"sd={r.std():.4%}  skew={r.skew():+.2f}  kurt={r.kurt():.1f}")
    emit(f"annualized realized vol (close-close): {r.std() * np.sqrt(ANN):.1%}")
    rv5 = np.sqrt(daily["rv5_var"].mean() * ANN)
    emit(f"annualized realized vol (5-min intraday RV): {rv5:.1%}")
    on, iday = daily["ret_on"].dropna(), daily["ret_id"].dropna()
    emit(f"overnight-gap vol: {on.std() * np.sqrt(ANN):.1%}   "
         f"intraday vol: {iday.std() * np.sqrt(ANN):.1%}   "
         f"(overnight share of total variance: "
         f"{on.var() / (on.var() + iday.var()):.0%})")
    emit(f"days with |move| > 5%: {(r.abs() > .05).mean():.1%}   "
         f"> 10%: {(r.abs() > .10).mean():.1%}   "
         f"worst day {r.min():+.1%}  best day {r.max():+.1%}")

    # Monday-10:00 -> Friday-15:30 weekly move (the strategy window)
    bars = bars.copy()
    bars["week"] = bars["dt"].dt.to_period("W-SUN")
    entries, exits = {}, {}
    for wk, g in bars.groupby("week"):
        g = g.sort_values("dt")
        first_day = g["date"].iloc[0]
        mon = g[(g["date"] == first_day) & (g["dt"].dt.time >=
                                            pd.Timestamp("10:00").time())]
        last_day = g["date"].iloc[-1]
        fri = g[(g["date"] == last_day) & (g["dt"].dt.time >=
                                           pd.Timestamp("15:30").time())]
        if len(mon) and len(fri):
            entries[wk] = mon["Open"].iloc[0]
            exits[wk] = fri["Close"].iloc[0]
    wk = pd.DataFrame({"entry": entries, "exit": exits})
    wk["ret"] = wk["exit"] / wk["entry"] - 1
    emit(f"\nweekly Mon-10:00 -> Fri-15:30 window: n={len(wk)} weeks")
    emit(f"  mean={wk['ret'].mean():+.2%}  median={wk['ret'].median():+.2%}  "
         f"sd={wk['ret'].std():.2%}  skew={wk['ret'].skew():+.2f}")
    qs = wk["ret"].quantile([.01, .05, .10, .25, .50, .75, .90, .95, .99])
    emit("  quantiles: " + "  ".join(f"p{int(q * 100):02d}={v:+.1%}"
                                     for q, v in qs.items()))
    for thr in (.05, .08, .10, .15, .20):
        emit(f"  weeks beyond +/-{thr:.0%}:  up {(wk['ret'] > thr).mean():.1%}"
             f"   down {(wk['ret'] < -thr).mean():.1%}")
    # decay drag: mean daily arithmetic vs terminal
    tot = daily["close"].iloc[-1] / daily["close"].iloc[0] - 1
    emit(f"\nleveraged-decay check: sum of daily log returns = "
         f"{r.sum():+.1%} over {len(r)} days (terminal {tot:+.1%}) while "
         f"mean daily |move| = {r.abs().mean():.2%} -- classic 3x drag: "
         f"huge daily vol, weak drift.")
    wk.index = wk.index.astype(str)
    wk.to_csv(OUT_DIR / "s1_weekly_window_returns.csv")
    return wk


# --------------------------------------------------------------------------
# S2  implied vs forward realized vol  (variance risk premium)
# --------------------------------------------------------------------------
def atm_iv_by_dte(opt, dte_lo, dte_hi):
    """Per trade_date: liquid-quote IV of the contracts nearest ATM within a
    DTE window (both rights averaged)."""
    o = opt[(opt["dte"] >= dte_lo) & (opt["dte"] <= dte_hi) & opt["liquid"] &
            (opt["implied_vol"] > 0)]
    if o.empty:
        return pd.Series(dtype=float)

    def pick(g):
        g = g.assign(dist=(g["mness"] - 1).abs())
        exp = g.loc[g["dist"].idxmin(), "expiration"]
        g = g[g["expiration"] == exp]
        return g.nsmallest(4, "dist")["implied_vol"].mean()

    return o.groupby("trade_date").apply(pick, include_groups=False)


def forward_rv(daily, horizon_days):
    """Annualized realized vol over the NEXT `horizon_days` calendar days,
    from daily close-close returns."""
    r = daily["ret_cc"]
    out = {}
    dates = daily.index
    for i, d in enumerate(dates):
        end = d + pd.Timedelta(days=horizon_days)
        w = r[(dates > d) & (dates <= end)]
        if len(w) >= max(3, horizon_days // 4):
            out[d] = w.std() * np.sqrt(ANN)
    return pd.Series(out)


def s2_vrp(opt, daily):
    section("S2  IMPLIED vs SUBSEQUENT REALIZED VOL  (variance risk premium)")
    emit("For each trade date: ATM IV in a DTE bucket vs realized vol over")
    emit("the matching forward window.  VRP = IV - forward RV.  Positive =")
    emit("options overpriced relative to what then happened (edge to seller).")
    rows = []
    hor = {"7d (weekly)": (4, 9, 7), "14d": (10, 17, 14), "30d": (25, 38, 30),
           "60d": (50, 70, 60), "90d": (80, 100, 90), "180d": (150, 210, 180)}
    detail = {}
    for name, (lo, hi, days) in hor.items():
        iv = atm_iv_by_dte(opt, lo, hi)
        rv = forward_rv(daily, days)
        j = pd.DataFrame({"iv": iv, "rv": rv}).dropna()
        vrp = j["iv"] - j["rv"]
        rows.append({"bucket": name, "n_dates": len(j),
                     "mean_IV": j["iv"].mean(), "mean_fwd_RV": j["rv"].mean(),
                     "mean_VRP": vrp.mean(), "median_VRP": vrp.median(),
                     "VRP>0 freq": (vrp > 0).mean(),
                     "p05_VRP": vrp.quantile(.05),
                     "p95_VRP": vrp.quantile(.95)})
        detail[name] = j.assign(vrp=vrp)
    t = pd.DataFrame(rows).set_index("bucket")
    table(t)
    pd.concat(detail, names=["bucket"]).to_csv(OUT_DIR / "s2_vrp_daily.csv")
    emit("\nInterpretation: 'VRP>0 freq' is how often the seller of ATM vol")
    emit("was paid more than delivered movement over the option's life.")
    return t


# --------------------------------------------------------------------------
# S3  skew and term structure
# --------------------------------------------------------------------------
def s3_skew(opt):
    section("S3  SKEW (25-delta put vs call) AND ATM TERM STRUCTURE")
    o = opt[opt["liquid"] & (opt["implied_vol"] > 0)]
    rows = []
    for name, (lo, hi) in {"weekly(4-9d)": (4, 9), "30d": (25, 38),
                           "90d": (80, 100), "180d": (150, 210)}.items():
        w = o[(o["dte"] >= lo) & (o["dte"] <= hi)]
        skews = {}
        for right, tgt in (("PUT", -0.25), ("CALL", 0.25)):
            s = w[w["right"] == right].copy()
            s["dist"] = (s["delta"] - tgt).abs()
            iv = s.loc[s.groupby("trade_date")["dist"].idxmin()]
            iv = iv[iv["dist"] < 0.08].set_index("trade_date")["implied_vol"]
            skews[right] = iv
        j = pd.DataFrame(skews).dropna()
        d = j["PUT"] - j["CALL"]
        rows.append({"bucket": name, "n": len(j),
                     "IV_25d_put": j["PUT"].mean(),
                     "IV_25d_call": j["CALL"].mean(),
                     "put-call skew": d.mean(), "skew>0 freq": (d > 0).mean(),
                     "p10": d.quantile(.1), "p90": d.quantile(.9)})
    table(pd.DataFrame(rows).set_index("bucket"))
    emit("\nskew > 0  => downside puts carry richer IV than symmetric calls")
    emit("skew < 0  => CALLS are the rich side (unusual; sell-call edge)")

    # ATM term structure slope: weekly IV minus 30d IV per date
    iv7 = atm_iv_by_dte(opt, 4, 9)
    iv30 = atm_iv_by_dte(opt, 25, 38)
    iv180 = atm_iv_by_dte(opt, 150, 210)
    ts = pd.DataFrame({"iv7": iv7, "iv30": iv30, "iv180": iv180}).dropna()
    ts["slope_7_30"] = ts["iv7"] - ts["iv30"]
    ts["slope_7_180"] = ts["iv7"] - ts["iv180"]
    emit(f"\nATM term structure across {len(ts)} dates:")
    emit(f"  mean IV: 7d={ts['iv7'].mean():.1%}  30d={ts['iv30'].mean():.1%} "
         f" 180d={ts['iv180'].mean():.1%}")
    emit(f"  7d - 30d slope: mean={ts['slope_7_30'].mean():+.1%}  "
         f"inverted (7d>30d) on {(ts['slope_7_30'] > 0).mean():.0%} of days")
    emit(f"  7d - 180d slope: mean={ts['slope_7_180'].mean():+.1%}  "
         f"inverted on {(ts['slope_7_180'] > 0).mean():.0%} of days")
    emit("  persistent inversion = front-week vol systematically rich vs")
    emit("  the back months -> calendarized structures collect the spread.")
    ts.to_csv(OUT_DIR / "s3_term_structure.csv")
    return ts


# --------------------------------------------------------------------------
# S4  put-call parity: implied forward, carry, executable arb
# --------------------------------------------------------------------------
def s4_parity(opt):
    section("S4  PUT-CALL PARITY: IMPLIED FORWARD / CARRY & EXECUTABLE ARB")
    emit("Cross-strike regression per (date, expiry):  C_mid - P_mid = "
         "a + b*K")
    emit("  => implied forward F = -a/b, discount = -b, implied carry =")
    emit("     ln(F/S) * 365/dte  (r minus borrow/decay premium).")
    o = opt[opt["liquid"]]
    recs = []
    for (td, exp), g in o.groupby(["trade_date", "expiration"]):
        c = g[g["right"] == "CALL"].set_index("strike")["mid"]
        p = g[g["right"] == "PUT"].set_index("strike")["mid"]
        ks = c.index.intersection(p.index)
        if len(ks) < 6:
            continue
        y = (c.loc[ks] - p.loc[ks]).values
        b, a = np.polyfit(ks.values, y, 1)
        if not -1.05 < b < -0.5:
            continue
        S = g["underlying_price"].iloc[0]
        dte = g["dte"].iloc[0]
        F = -a / b
        recs.append({"trade_date": td, "expiration": exp, "dte": dte,
                     "spot": S, "fwd": F, "fwd_over_spot": F / S,
                     "carry_ann": np.log(F / S) * 365 / max(dte, 1),
                     "n_strikes": len(ks)})
    par = pd.DataFrame(recs)
    par.to_csv(OUT_DIR / "s4_implied_forward.csv", index=False)
    buck = pd.cut(par["dte"], [0, 9, 21, 45, 100, 250, 900])
    t = par.groupby(buck, observed=True).agg(
        n=("fwd", "size"), mean_fwd_over_spot=("fwd_over_spot", "mean"),
        mean_carry_ann=("carry_ann", "mean"),
        med_carry_ann=("carry_ann", "median"),
        carry_neg_freq=("carry_ann", lambda s: (s < 0).mean()))
    table(t)
    emit("\ncarry_ann below the T-bill rate (~4-5%) means the market prices")
    emit("SOXL forwards BELOW fair carry: puts are structurally expensive /")
    emit("calls structurally cheap vs spot (borrow fee + decay expectation).")
    emit("This is a persistent relative-pricing disparity, not free money --")
    emit("it is the compensation embedded for shorting a 3x ETF.")

    # executable conversion / reversal scan (crossing the 20%-rule prices)
    emit("\nExecutable arb scan (20%-rule prices, per contract pair):")
    emit("  reversal: short stock + sell put(exec) + buy call(exec) -> "
         "locks -K")
    emit("  conversion: long stock + buy put(exec) + sell call(exec) -> "
         "locks +K")
    m = o.pivot_table(index=["trade_date", "expiration", "strike",
                             "underlying_price", "dte"],
                      columns="right", values=["sell_px", "buy_px"])
    m.columns = [f"{a}_{b}" for a, b in m.columns]
    m = m.dropna().reset_index()
    # ignore financing (conservative for conversion when r>0)
    m["conv_pnl"] = (m["strike"] - m["underlying_price"]
                     - m["buy_px_PUT"] + m["sell_px_CALL"])
    m["rev_pnl"] = (m["underlying_price"] - m["strike"]
                    + m["sell_px_PUT"] - m["buy_px_CALL"])
    for nm in ("conv_pnl", "rev_pnl"):
        pos = m[m[nm] > 0.02]
        emit(f"  {nm}>$0.02: {len(pos):,} of {len(m):,} pairs "
             f"({len(pos) / len(m):.2%});  p99 profit "
             f"${m[nm].quantile(.99):.2f};  note: ex-financing and "
             f"ex-borrow-fee, so apparent reversal 'profits' are mostly the "
             f"hard-to-borrow fee you would pay to short SOXL.")
    return par


# --------------------------------------------------------------------------
# S5  liquidity & spread-cost surface
# --------------------------------------------------------------------------
def s5_liquidity(opt):
    section("S5  LIQUIDITY & SPREAD-COST SURFACE")
    o = opt.copy()
    o["dl"] = pd.cut(o["delta"].abs(), [0, .1, .2, .3, .4, .6, 1.01],
                     labels=["0-10d", "10-20d", "20-30d", "30-40d", "40-60d",
                             "60d+"])
    o["db"] = pd.cut(o["dte"], [0, 9, 21, 45, 100, 250, 900],
                     labels=["<=9", "10-21", "22-45", "46-100", "101-250",
                             ">250"])
    liq = o[o["liquid"] & (o["mid"] > 0)]
    liq = liq.assign(spread_pct=liq["spread"] / liq["mid"])
    t = liq.pivot_table(index="db", columns="dl", values="spread_pct",
                        aggfunc="median", observed=True)
    emit("median spread as % of mid  (rows: DTE, cols: |delta| bucket):")
    table(t, floatfmt="{:.1%}")
    z = o.pivot_table(index="db", columns="dl", values="liquid",
                      aggfunc=lambda s: 1 - s.mean(), observed=True)
    emit("\nshare of quotes REJECTED by the 20% rule (bid=0 / inverted):")
    table(z, floatfmt="{:.1%}")
    emit("\nround-trip friction at the 20% rule is 0.6 x spread%; e.g. a "
         "14% spread costs ~8.4% of premium round trip.")
    t.to_csv(OUT_DIR / "s5_spread_surface.csv")
    return t


# --------------------------------------------------------------------------
# S6  weekly short-premium permutation grid
# --------------------------------------------------------------------------
def week_expiry_map(opt):
    """For each Monday(or first-of-week) trade date, the nearest expiration
    3-7 calendar days out (that week's Friday, Thursday on holidays)."""
    dates = pd.Series(sorted(opt["trade_date"].unique()))
    dow = dates.dt.dayofweek
    return dates[dow == 0], dates


def settle_prices(daily):
    return daily["close"]


def pick_by_delta(chain, right, target, max_dist=0.10):
    g = chain[(chain["right"] == right) & chain["liquid"] &
              (chain["sell_px"] >= 0.03)]
    if right == "PUT":
        g = g[g["delta"] < 0]
    else:
        g = g[g["delta"] > 0]
    if g.empty:
        return None
    g = g.assign(dist=(g["delta"].abs() - target).abs())
    row = g.loc[g["dist"].idxmin()]
    if row["dist"] > max_dist:
        return None
    return row


def s6_weekly_grid(opt, daily):
    section("S6  WEEKLY SHORT-PREMIUM GRID  (Mon EOD entry -> expiry "
            "settlement, 20%-rule fills)")
    emit("NOTE: option quotes are EOD snapshots; Monday-10:00 execution per")
    emit("the strategy docs cannot be priced from this file -- Monday EOD is")
    emit("the closest verifiable proxy.  (Intraday option data = request.)")
    settle = settle_prices(daily)
    mondays, all_dates = week_expiry_map(opt)
    grid_specs = []
    for tgt in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50):
        grid_specs.append(("short_put", {"put": tgt}))
        grid_specs.append(("short_call", {"call": tgt}))
    for pt in (0.15, 0.20, 0.25, 0.30):
        for ct in (0.10, 0.15, 0.20, 0.30):
            grid_specs.append(("strangle", {"put": pt, "call": ct}))
    grid_specs.append(("straddle", {"put": 0.50, "call": 0.50}))

    results = []
    trades_out = []
    for td in mondays:
        chain = opt[opt["trade_date"] == td]
        wk = chain[(chain["dte"] >= 3) & (chain["dte"] <= 7)]
        if wk.empty:
            continue
        exp = wk.loc[wk["dte"].idxmin(), "expiration"]
        wk = wk[wk["expiration"] == exp]
        if exp not in settle.index:
            after = settle.index[settle.index <= exp]
            if len(after) == 0:
                continue
            exp_px = settle.loc[after[-1]]
        else:
            exp_px = settle.loc[exp]
        S0 = wk["underlying_price"].iloc[0]
        for name, legs in grid_specs:
            prem, ok, strikes = 0.0, True, {}
            for side, tgt in legs.items():
                row = pick_by_delta(wk, "PUT" if side == "put" else "CALL",
                                    tgt)
                if row is None:
                    ok = False
                    break
                prem += row["sell_px"]
                strikes[side] = row["strike"]
            if not ok:
                continue
            payoff = 0.0
            if "put" in strikes:
                payoff -= max(strikes["put"] - exp_px, 0)
            if "call" in strikes:
                payoff -= max(exp_px - strikes["call"], 0)
            pnl = prem + payoff
            results.append({"strategy": name,
                            "legs": "/".join(f"{k}{v:.0%}"
                                             for k, v in legs.items()),
                            "trade_date": td, "pnl": pnl, "prem": prem,
                            "spot": S0, "settle": exp_px})
            trades_out.append(results[-1] | strikes)
    res = pd.DataFrame(results)
    pd.DataFrame(trades_out).to_csv(OUT_DIR / "s6_weekly_grid_trades.csv",
                                    index=False)

    def agg(g):
        pnl, prem = g["pnl"], g["prem"]
        notional = g["spot"]  # per-share capital proxy
        return pd.Series({
            "n": len(g), "win%": (pnl > 0).mean(),
            "avg_prem": prem.mean(), "avg_pnl": pnl.mean(),
            "med_pnl": pnl.median(), "worst": pnl.min(),
            "p05": pnl.quantile(.05),
            "capture": pnl.sum() / prem.sum() if prem.sum() else np.nan,
            "wk_yield_on_spot": (pnl / notional).mean(),
            "ann_yield": (pnl / notional).mean() * 52,
            "sum_pnl_per_share": pnl.sum()})

    t = (res.groupby(["strategy", "legs"])
            .apply(agg, include_groups=False)
            .sort_values("ann_yield", ascending=False))
    table(t, max_rows=60)
    t.to_csv(OUT_DIR / "s6_weekly_grid_summary.csv")
    emit("\ncapture = total kept / total collected.  wk_yield_on_spot is per")
    emit("share of underlying (naked-cash basis, before margin relief).")
    return res, t


# --------------------------------------------------------------------------
# S7  defined-risk overlays: wings and jade lizards
# --------------------------------------------------------------------------
def s7_wings(opt, daily):
    section("S7  DEFINED-RISK OVERLAYS: WING COST & JADE LIZARD SCAN")
    settle = settle_prices(daily)
    mondays, _ = week_expiry_map(opt)
    rows = []
    jl_rows = []
    for td in mondays:
        chain = opt[opt["trade_date"] == td]
        wk = chain[(chain["dte"] >= 3) & (chain["dte"] <= 7)]
        if wk.empty:
            continue
        exp = wk.loc[wk["dte"].idxmin(), "expiration"]
        wk = wk[wk["expiration"] == exp]
        if exp in settle.index:
            exp_px = settle.loc[exp]
        else:
            idx = settle.index[settle.index <= exp]
            if len(idx) == 0:
                continue
            exp_px = settle.loc[idx[-1]]
        sp = pick_by_delta(wk, "PUT", 0.25)
        sc = pick_by_delta(wk, "CALL", 0.15)
        if sp is None or sc is None:
            continue
        # put wing: nearest liquid put >= $2 below the short strike
        wings = wk[(wk["right"] == "PUT") & wk["liquid"] &
                   (wk["strike"] <= sp["strike"] - 2)]
        lp = wings.loc[wings["strike"].idxmax()] if len(wings) else None
        credit_naked = sp["sell_px"] + sc["sell_px"]
        rec = {"trade_date": td, "spot": wk["underlying_price"].iloc[0],
               "settle": exp_px, "sp_k": sp["strike"], "sc_k": sc["strike"],
               "credit_naked": credit_naked}
        if lp is not None:
            width = sp["strike"] - lp["strike"]
            credit_prot = credit_naked - lp["buy_px"]
            pnl_naked = (credit_naked - max(sp["strike"] - exp_px, 0)
                         - max(exp_px - sc["strike"], 0))
            pnl_prot = (credit_prot
                        - max(sp["strike"] - exp_px, 0)
                        + max(lp["strike"] - exp_px, 0)
                        - max(exp_px - sc["strike"], 0))
            rec |= {"lp_k": lp["strike"], "width": width,
                    "wing_cost": lp["buy_px"],
                    "wing_cost_pct_of_credit": lp["buy_px"] / credit_naked,
                    "credit_prot": credit_prot, "pnl_naked": pnl_naked,
                    "pnl_prot": pnl_prot,
                    "jade_lizard": credit_prot >= width * 0 + 0}
            # jade lizard on the CALL side: short put + short call spread,
            # credit > call-spread width -> zero upside risk
            cw = wk[(wk["right"] == "CALL") & wk["liquid"] &
                    (wk["strike"] >= sc["strike"] + 1)]
            if len(cw):
                lc = cw.loc[cw["strike"].idxmin()]
                cred = sp["sell_px"] + sc["sell_px"] - lc["buy_px"]
                w = lc["strike"] - sc["strike"]
                jl_rows.append({"trade_date": td, "credit": cred,
                                "call_width": w, "no_upside_risk": cred >= w})
        rows.append(rec)
    wr = pd.DataFrame(rows).dropna(subset=["width"])
    wr.to_csv(OUT_DIR / "s7_wing_scan.csv", index=False)
    emit(f"weekly 25d-put/15d-call strangle, put wing ~$2+ lower: n={len(wr)}")
    emit(f"  avg naked credit ${wr['credit_naked'].mean():.2f}   avg wing "
         f"cost ${wr['wing_cost'].mean():.2f} "
         f"({wr['wing_cost_pct_of_credit'].mean():.0%} of credit)")
    emit(f"  total P&L naked ${wr['pnl_naked'].sum():+.2f}/share-week vs "
         f"protected ${wr['pnl_prot'].sum():+.2f}  "
         f"(wing drag ${wr['pnl_naked'].sum() - wr['pnl_prot'].sum():.2f})")
    emit(f"  worst week naked ${wr['pnl_naked'].min():+.2f} vs protected "
         f"${wr['pnl_prot'].min():+.2f}  <-- what you buy with the wing")
    if jl_rows:
        jl = pd.DataFrame(jl_rows)
        emit(f"\njade lizard scan (short put + short call vertical): "
             f"{len(jl)} weeks; structures where credit >= call width "
             f"(NO upside risk): {jl['no_upside_risk'].mean():.0%}")
        jl.to_csv(OUT_DIR / "s7_jade_lizard.csv", index=False)
    return wr


# --------------------------------------------------------------------------
# S8  diagonal economics: long-put bleed vs weekly credit
# --------------------------------------------------------------------------
def s8_diagonal(opt):
    section("S8  DIAGONAL ECONOMICS: 90-180 DTE LONG-PUT BLEED vs WEEKLY "
            "SHORT CREDIT")
    emit("Buy ~ATM put 120-180 DTE at 20%-rule ask; re-mark it one week")
    emit("later (same contract, mid).  Compare the average weekly bleed to")
    emit("the weekly short-premium collected in S6.")
    mondays, _ = week_expiry_map(opt)
    mon = set(mondays)
    idx = opt.set_index(["trade_date", "expiration", "strike", "right"])
    rows = []
    mond = sorted(mon)
    for i, td in enumerate(mond[:-1]):
        nxt = mond[i + 1]
        chain = opt[(opt["trade_date"] == td) & (opt["right"] == "PUT") &
                    (opt["dte"] >= 120) & (opt["dte"] <= 200) & opt["liquid"]]
        if chain.empty:
            continue
        chain = chain.assign(dist=(chain["mness"] - 1).abs())
        exp = chain.loc[chain["dist"].idxmin(), "expiration"]
        chain = chain[chain["expiration"] == exp]
        row = chain.loc[chain["dist"].idxmin()]
        try:
            nxt_row = idx.loc[(nxt, exp, row["strike"], "PUT")]
        except KeyError:
            continue
        if isinstance(nxt_row, pd.DataFrame):
            nxt_row = nxt_row.iloc[0]
        rows.append({"trade_date": td, "expiration": exp,
                     "strike": row["strike"], "dte": row["dte"],
                     "buy_px": row["buy_px"], "mark_t0": row["mid"],
                     "mark_t1": nxt_row["mid"],
                     "wk_bleed": nxt_row["mid"] - row["mid"],
                     "spot0": row["underlying_price"],
                     "spot1": nxt_row["underlying_price"]})
    d = pd.DataFrame(rows)
    d["spot_ret"] = d["spot1"] / d["spot0"] - 1
    d.to_csv(OUT_DIR / "s8_longput_bleed.csv", index=False)
    flat = d[d["spot_ret"].abs() < 0.03]
    emit(f"n={len(d)} weekly re-marks of a ~150-DTE ATM put")
    emit(f"  entry cost: avg ${d['buy_px'].mean():.2f} on spot "
         f"${d['spot0'].mean():.2f} ({(d['buy_px'] / d['spot0']).mean():.1%} "
         f"of spot!)")
    emit(f"  avg weekly mark change: ${d['wk_bleed'].mean():+.3f} "
         f"(all weeks)   ${flat['wk_bleed'].mean():+.3f} (flat weeks "
         f"|move|<3%, n={len(flat)})")
    emit(f"  in crash weeks (spot -10% or worse): "
         f"${d.loc[d['spot_ret'] < -.10, 'wk_bleed'].mean():+.2f} avg gain "
         f"(n={(d['spot_ret'] < -.10).sum()})")
    emit("  -> compare bleed to the ~weekly credits in S6 to see whether")
    emit("     short premium actually funds the anchor put.")
    return d


# --------------------------------------------------------------------------
# S9  irregularity scans
# --------------------------------------------------------------------------
def s9_irregularities(opt, daily):
    section("S9  IRREGULARITY SCANS")
    o = opt
    z_iv = o[(o["implied_vol"] == 0) & o["liquid"] & (o["mid"] > 0.05)]
    emit(f"zero-IV rows with live two-sided quotes: {len(z_iv):,} "
         f"({len(z_iv) / len(o):.2%}) -- IV column unusable there; quotes "
         f"still fine.")
    # deep-ITM quote sanity: mid below intrinsic (buyable below parity?)
    itm_c = o[(o["right"] == "CALL") & o["liquid"] &
              (o["strike"] < o["underlying_price"])]
    viol = itm_c[itm_c["buy_px"] <
                 (itm_c["underlying_price"] - itm_c["strike"]) * 0.995 - 0.05]
    emit(f"ITM calls buyable (20% rule) below intrinsic-5c: {len(viol):,} of "
         f"{len(itm_c):,} ({len(viol) / max(len(itm_c), 1):.2%}) -- "
         f"early-exercise/stale-quote artifacts, not a real edge at retail.")
    itm_p = o[(o["right"] == "PUT") & o["liquid"] &
              (o["strike"] > o["underlying_price"])]
    violp = itm_p[itm_p["buy_px"] <
                  (itm_p["strike"] - itm_p["underlying_price"]) * 0.995 - .05]
    emit(f"ITM puts buyable below intrinsic-5c: {len(violp):,} of "
         f"{len(itm_p):,} ({len(violp) / max(len(itm_p), 1):.2%})")

    # blow-up ledger: weeks where weekly ATM IV most underpriced the move
    iv7 = atm_iv_by_dte(opt, 4, 9)
    r = daily["ret_cc"]
    led = []
    for td, iv in iv7.items():
        end = td + pd.Timedelta(days=7)
        w = r[(r.index > td) & (r.index <= end)]
        if len(w) < 3:
            continue
        realized = w.std() * np.sqrt(ANN)
        led.append({"trade_date": td, "iv7": iv, "rv_next_wk": realized,
                    "gap": realized - iv,
                    "wk_move": np.exp(w.sum()) - 1})
    led = pd.DataFrame(led).sort_values("gap", ascending=False)
    emit("\nworst 10 'IV underpriced the week' events (seller blow-ups):")
    table(led.head(10).set_index("trade_date"), floatfmt="{:+.2f}")
    led.to_csv(OUT_DIR / "s9_blowup_ledger.csv", index=False)
    emit(f"\nweeks where realized > implied: {(led['gap'] > 0).mean():.0%} "
         f"of {len(led)} weeks -- the loss tail the income engine must "
         f"survive; sizing/wings exist because of these rows.")
    return led


# --------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(exist_ok=True)
    QA_DIR.mkdir(exist_ok=True)
    emit("SOXL VOLATILITY & OPTION-PRICING LAB")
    emit(f"run date: {pd.Timestamp.now():%Y-%m-%d %H:%M}")
    opt = load_options()
    bars = load_bars()
    daily = daily_frame(bars)
    ol, oh = opt["trade_date"].min().date(), opt["trade_date"].max().date()
    emit(f"options: {len(opt):,} rows, {opt['trade_date'].nunique()} trade "
         f"dates ({ol} -> {oh});  bars: {len(bars):,} "
         f"({daily.index.min().date()} -> {daily.index.max().date()})")

    s1_underlying(daily, bars)
    s2_vrp(opt, daily)
    s3_skew(opt)
    s4_parity(opt)
    s5_liquidity(opt)
    s6_weekly_grid(opt, daily)
    s7_wings(opt, daily)
    s8_diagonal(opt)
    s9_irregularities(opt, daily)

    (QA_DIR / "pricing_lab_report.txt").write_text("\n".join(REPORT) + "\n")
    emit(f"\nreport written to qa/pricing_lab_report.txt; tables in "
         f"{OUT_DIR.name}/")


if __name__ == "__main__":
    main()
