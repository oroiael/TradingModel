#!/usr/bin/env python3
"""
R5 -- Delta-hedged long gamma (gamma scalping) backtest
=======================================================

The one options structure this project has never tested, and the only one
its own measurements actually argue for.

The thesis (harvest_blueprint/README.md S1, vol_anatomy/harvestability.py):

    SOXL's variance risk premium is NEGATIVE beyond a week -- realized vol
    EXCEEDS implied by 14 points at 30d, 22 at 90d, 29 at 180d, and the
    regression of forward realized on implied has a slope ABOVE 1.0 at every
    tenor. Every short-premium structure inherits that sign and loses.

    Turned around, that same measurement says the profitable side of SOXL
    vol was BUYING it. But a long option is also short delta or long delta,
    and direction swamped the vol edge in every long-premium test here.
    Stripping the direction out is exactly what delta hedging does:

        delta-hedged long option P&L ~ (1/2) * SUM Gamma * S^2 * (rv^2 - iv^2)

    If realized beats implied, this is positive GROSS. The whole question is
    whether it survives paying a spread on every rehedge -- which is why
    vol_anatomy flagged it as open rather than answering it.

Structure: buy an ATM straddle (or a single option) from the real EOD chain,
hedge to delta-neutral with SOXL shares, rehedge on a schedule, hold to
expiry, settle at intrinsic, unwind the shares. One cycle at a time, no
overlap.

WHERE THE DELTAS COME FROM -- this is the modelling boundary, stated plainly:

    daily schedule      uses the REAL `delta` column from the EOD chain at
                        every rehedge. No model at all.
    intraday schedules  need a delta between EOD snapshots, and the intraday
                        option files carry trade prices only, no greeks. So
                        delta is Black-Scholes (r=q=0) at the current 5-min
                        close, struck on the contract's own most recent EOD
                        implied vol. call_spread_lab/verify.py established
                        that BS priced with this data's own IV lands inside
                        the quoted bid/ask ~94% of the time. QA below
                        re-validates it directly: BS delta vs the real EOD
                        delta, on every EOD in every cycle.

Execution discipline: every hedge is priced at the BAR CLOSE, never at the
bar's high or low. call_spread_lab/FINDINGS_6 is the cautionary tale -- an
intraday result there reversed sign entirely once fills stopped assuming
foresight. Hedges are market orders, so each pays half the spread.

Costs: IBKR Pro Fixed, taken from band_lab/phase1/cost_model.py so the share
leg is charged exactly what the live engine charges -- $0.005/share with a
$1.00 order minimum and a 1%-of-value cap, 1.0c spread (0.5c crossing),
SEC 0.28bp and FINRA TAF on sells. Options use the project 20% fill rule and
$0.65/contract.

Outputs:
    gamma_scalp_cycles.csv    per-cycle ledger (base config)
    gamma_scalp_grid.csv      hedge-schedule / tenor / structure grid
    qa/gamma_scalp_report.txt
"""

from dataclasses import dataclass, asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from volatility_pricing_lab import load_options, load_bars

ROOT = Path(__file__).resolve().parent
QA_DIR = ROOT / "qa"

OPT_COMMISSION = 0.65           # $/contract
SH_COMM_PER_SHARE = 0.005       # IBKR Pro Fixed
SH_COMM_MIN = 1.00
SH_COMM_MAX_FRAC = 0.01
SH_SPREAD_CENTS = 1.0           # crossing pays half
SEC_FEE_BP_SELLS = 0.28
FINRA_TAF_PER_SHARE = 0.000166
FINRA_TAF_MAX = 8.30
EPS = 1e-9


# --------------------------------------------------------------------------
# Black-Scholes delta (r=q=0), matching call_spread_lab/bs.py's conventions
# --------------------------------------------------------------------------
from scipy.special import ndtr as _norm_cdf     # vectorised N(x)


def bs_delta(S, K, T, sigma, right):
    """Vectorised. Returns +N(d1) for calls, N(d1)-1 for puts."""
    S = np.asarray(S, dtype=float)
    T = np.maximum(np.asarray(T, dtype=float), 0.0)
    sig = float(sigma)
    out = np.where(S > K, 1.0, 0.0) if right == "CALL" \
        else np.where(S < K, -1.0, 0.0)
    live = (T > 0) & (sig > 0) & (S > 0)
    if not np.any(live):
        return out
    d1 = ((np.log(np.where(live, S, 1.0) / K) + 0.5 * sig * sig * T)
          / (sig * np.sqrt(np.where(live, T, 1.0))))
    nd1 = _norm_cdf(d1)
    return np.where(live, nd1 if right == "CALL" else nd1 - 1.0, out)


# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Config:
    structure: str = "straddle"     # straddle | call | put
    dte: int = 60                   # target tenor at entry
    dte_lo: int = 45
    dte_hi: int = 90
    hedge: str = "daily"            # daily | bars_K (K x 5min) | band_X
    contracts: int = 0              # 0 = size on premium_budget instead
    premium_budget: float = 15_000.0
    costs: bool = True              # False = gross, isolates the friction
    exit_dte: int = 0               # 0 = hold to expiry
    start_capital: float = 150_000.0

    def label(self):
        p = [self.structure[:4], f"t{self.dte}", self.hedge]
        if self.contracts:
            p.append(f"n{self.contracts}")
        if not self.costs:
            p.append("GROSS")
        if self.exit_dte:
            p.append(f"x{self.exit_dte}")
        return "_".join(p)


def share_cost(qty, price, side):
    """One share order's cost in $ (qty>0). Market order: crosses the spread."""
    if qty <= 0:
        return 0.0
    value = qty * price
    comm = min(max(SH_COMM_PER_SHARE * qty, SH_COMM_MIN),
               SH_COMM_MAX_FRAC * value)
    exec_ = qty * (SH_SPREAD_CENTS / 2.0) / 100.0
    reg = 0.0
    if side == "SELL":
        reg = (value * SEC_FEE_BP_SELLS / 1e4
               + min(FINRA_TAF_PER_SHARE * qty, FINRA_TAF_MAX))
    return comm + exec_ + reg


class GammaScalp:
    def __init__(self, opt, bars, cfg: Config):
        self.cfg = cfg
        self.opt = opt
        self.chains = dict(tuple(opt.groupby("trade_date")))
        self.dates = sorted(self.chains)
        # intraday bars keyed by date
        bars = bars.copy()
        bars["date"] = bars["dt"].dt.normalize()
        self.bars_by_date = dict(tuple(bars.groupby("date")))
        self.daily_close = bars.groupby("date")["Close"].last()
        self.cycles = []
        self.delta_check = []       # (bs_delta, real_delta) pairs for QA

    # --- leg selection -------------------------------------------------
    def pick_legs(self, td):
        cfg = self.cfg
        ch = self.chains[td]
        g = ch[ch["liquid"] & (ch["dte"] >= cfg.dte_lo)
               & (ch["dte"] <= cfg.dte_hi) & (ch["implied_vol"] > 0.01)]
        if g.empty:
            return None
        # Only expiries the data actually covers. Without this the final
        # cycle settles at intrinsic while still holding weeks of time value,
        # which is a fabricated loss, not a result.
        g = g[g["expiration"] <= self.dates[-1]]
        if g.empty:
            return None
        exp = g.loc[(g["dte"] - cfg.dte).abs().idxmin(), "expiration"]
        g = g[g["expiration"] == exp]
        spot = float(ch["underlying_price"].iloc[0])
        whole = g[g["strike"] % 1 == 0]
        if len(whole):
            g = whole
        if g.empty:
            return None
        K = float(g.loc[(g["strike"] - spot).abs().idxmin(), "strike"])
        rights = ["CALL", "PUT"] if cfg.structure == "straddle" \
            else [cfg.structure.upper()]
        legs = []
        for r in rights:
            row = g[(g["strike"] == K) & (g["right"] == r)]
            if row.empty:
                return None
            row = row.iloc[0]
            if not bool(row["liquid"]) or float(row["buy_px"]) <= 0.05 \
                    or float(row["implied_vol"]) <= 0.01:
                return None
            legs.append({"right": r, "strike": K, "exp": row["expiration"],
                         "cost": float(row["buy_px"]),
                         "iv": float(row["implied_vol"]),
                         "delta": float(row["delta"])})
        return legs

    def eod_delta(self, td, leg):
        """Real EOD delta for a leg, from the chain. None if unquoted."""
        ch = self.chains.get(td)
        if ch is None:
            return None
        r = ch[(ch["expiration"] == leg["exp"]) & (ch["strike"] == leg["strike"])
               & (ch["right"] == leg["right"])]
        if r.empty or pd.isna(r.iloc[0]["delta"]):
            return None
        return float(r.iloc[0]["delta"])

    def eod_iv(self, td, leg):
        ch = self.chains.get(td)
        if ch is None:
            return None
        r = ch[(ch["expiration"] == leg["exp"]) & (ch["strike"] == leg["strike"])
               & (ch["right"] == leg["right"])]
        if r.empty:
            return None
        iv = float(r.iloc[0]["implied_vol"])
        return iv if iv > 0.01 else None

    # --- one cycle ------------------------------------------------------
    def run_cycle(self, td):
        cfg = self.cfg
        legs = self.pick_legs(td)
        if legs is None:
            return None
        exp = legs[0]["exp"]
        K = legs[0]["strike"]
        unit = sum(l["cost"] for l in legs) * 100
        n = cfg.contracts or int(cfg.premium_budget // unit)
        if n <= 0:
            return None
        spot0 = float(self.chains[td]["underlying_price"].iloc[0])

        opt_cost = sum(l["cost"] for l in legs) * 100 * n
        costs = OPT_COMMISSION * n * len(legs) if cfg.costs else 0.0

        # hedge state
        shares = 0
        share_cash = 0.0
        n_hedges = 0
        # dates in the cycle: entry -> expiry (exclusive of entry-day open)
        cyc_dates = [d for d in self.dates if td <= d <= pd.Timestamp(exp)]
        if cfg.exit_dte:
            cyc_dates = [d for d in cyc_dates
                         if (pd.Timestamp(exp) - d).days >= cfg.exit_dte]
        if len(cyc_dates) < 2:
            return None

        def target_shares(delta_sum):
            return int(round(-delta_sum * 100 * n))

        def trade_to(target, price):
            """share_cash is kept GROSS of costs; every cost lands in `costs`,
            so total = opt_pnl + hedge_pnl - costs is an exact identity."""
            nonlocal shares, share_cash, costs, n_hedges
            dq = target - shares
            if dq == 0:
                return
            share_cash -= dq * price
            if cfg.costs:
                costs += share_cost(abs(dq), price,
                                    "BUY" if dq > 0 else "SELL")
            shares = target
            n_hedges += 1

        # --- entry hedge at the entry close, on REAL EOD deltas
        d0 = sum(l["delta"] for l in legs)
        trade_to(target_shares(d0), spot0)

        rv_rets = []        # returns at the hedge sampling frequency
        last_px = spot0
        # IV known when an intraday hedge is placed = the PRIOR EOD's IV.
        # Using the same day's closing IV would be look-ahead.
        prev_iv = {l["right"]: l["iv"] for l in legs}

        for d in cyc_dates[1:]:
            if cfg.hedge == "daily":
                px = float(self.daily_close.get(d, np.nan))
                if not np.isfinite(px):
                    continue
                ds = []
                for l in legs:
                    rd = self.eod_delta(d, l)
                    if rd is None:      # fall back to BS on a missing quote
                        iv = self.eod_iv(d, l) or l["iv"]
                        T = max((pd.Timestamp(l["exp"]) - d).days, 0) / 365.0
                        rd = float(bs_delta(px, l["strike"], T, iv, l["right"]))
                    ds.append(rd)
                rv_rets.append(np.log(px / last_px))
                last_px = px
                trade_to(target_shares(sum(ds)), px)
            else:
                day = self.bars_by_date.get(d)
                if day is None or day.empty:
                    continue
                closes = day["Close"].to_numpy(dtype=float)
                times = day["dt"].to_numpy()
                # per-leg BS delta across the whole day, vectorised
                dmat = np.zeros(len(closes))
                for l in legs:
                    iv = prev_iv[l["right"]]
                    T = np.maximum(
                        (pd.Timestamp(l["exp"]) - pd.Series(times)).dt.days
                        .to_numpy(dtype=float), 0.0) / 365.0
                    dmat += bs_delta(closes, l["strike"], T, iv, l["right"])
                if cfg.hedge.startswith("bars_"):
                    step = int(cfg.hedge.split("_")[1])
                    idx = list(range(step - 1, len(closes), step))
                    if idx and idx[-1] != len(closes) - 1:
                        idx.append(len(closes) - 1)   # always close the day
                    for i in idx:
                        rv_rets.append(np.log(closes[i] / last_px))
                        last_px = closes[i]
                        trade_to(target_shares(dmat[i]), closes[i])
                elif cfg.hedge.startswith("band_"):
                    thr = float(cfg.hedge.split("_")[1]) / 100.0
                    held = -shares / (100.0 * n)
                    for i in range(len(closes)):
                        if abs(dmat[i] - held) >= thr or i == len(closes) - 1:
                            rv_rets.append(np.log(closes[i] / last_px))
                            last_px = closes[i]
                            trade_to(target_shares(dmat[i]), closes[i])
                            held = dmat[i]
                # QA: BS (on the IV actually available) vs the real EOD delta
                for l in legs:
                    rd = self.eod_delta(d, l)
                    if rd is not None:
                        T = max((pd.Timestamp(l["exp"]) - d).days, 0) / 365.0
                        self.delta_check.append(
                            (float(bs_delta(closes[-1], l["strike"], T,
                                            prev_iv[l["right"]], l["right"])),
                             rd))
                    nv = self.eod_iv(d, l)      # roll the IV forward for d+1
                    if nv:
                        prev_iv[l["right"]] = nv

        # --- settle
        last_d = cyc_dates[-1]
        settle_px = float(self.daily_close.get(last_d, last_px))
        if cfg.exit_dte:                       # close the options at market
            opt_val = 0.0
            ch = self.chains.get(last_d)
            for l in legs:
                r = ch[(ch["expiration"] == l["exp"])
                       & (ch["strike"] == l["strike"])
                       & (ch["right"] == l["right"])] if ch is not None else None
                if r is not None and len(r) and bool(r.iloc[0]["liquid"]):
                    opt_val += float(r.iloc[0]["sell_px"])
                else:
                    opt_val += max(settle_px - l["strike"], 0.0) \
                        if l["right"] == "CALL" else max(l["strike"] - settle_px, 0.0)
            if cfg.costs:
                costs += OPT_COMMISSION * n * len(legs)
        else:
            opt_val = sum(max(settle_px - l["strike"], 0.0) if l["right"] == "CALL"
                          else max(l["strike"] - settle_px, 0.0) for l in legs)
        trade_to(0, settle_px)                 # unwind the share hedge

        opt_pnl = (opt_val - sum(l["cost"] for l in legs)) * 100 * n
        total = opt_pnl + share_cash - costs
        rv = float(np.std(rv_rets, ddof=1)) if len(rv_rets) > 2 else np.nan
        # annualise at the sampling frequency actually used
        per_yr = 252.0 if cfg.hedge == "daily" else 252.0 * len(rv_rets) / \
            max(len(cyc_dates) - 1, 1)
        return {
            "entry": str(td.date()), "expiry": str(pd.Timestamp(exp).date()),
            "strike": K, "spot0": round(spot0, 2), "settle": round(settle_px, 2),
            "dte": (pd.Timestamp(exp) - td).days, "contracts": n,
            "entry_iv": round(float(np.mean([l["iv"] for l in legs])), 4),
            "realized_vol": round(rv * np.sqrt(per_yr), 4)
            if np.isfinite(rv) else None,
            "opt_cost": round(sum(l["cost"] for l in legs) * 100 * n, 2),
            "opt_pnl": round(opt_pnl, 2),
            "hedge_pnl": round(share_cash, 2),
            "costs": round(costs, 2), "n_hedges": n_hedges,
            "total_pnl": round(total, 2),
            "pnl_pct_prem": round(100 * total / (opt_cost or 1), 2),
        }

    def run(self):
        cfg = self.cfg
        i = 0
        while i < len(self.dates):
            td = self.dates[i]
            c = self.run_cycle(td)
            if c is None:
                i += 1
                continue
            self.cycles.append(c)
            # next cycle starts on the first trade date after this expiry
            nxt = [j for j, d in enumerate(self.dates)
                   if str(d.date()) > c["expiry"]]
            if not nxt:
                break
            i = nxt[0]
        return pd.DataFrame(self.cycles)


def summarize(bt, cyc):
    cfg = bt.cfg
    if cyc.empty:
        return {"config": cfg.label(), "cycles": 0}
    tot = cyc["total_pnl"].sum()
    prem = cyc["opt_cost"].sum()
    start = cfg.start_capital
    dc = pd.DataFrame(bt.delta_check, columns=["bs", "real"])
    return {
        "config": cfg.label(), "cycles": len(cyc),
        "total_pnl": round(tot, 0),
        "pnl_pct_of_premium": round(100 * tot / prem, 1) if prem else None,
        "mean_cycle_pnl": round(cyc["total_pnl"].mean(), 0),
        "win_rate_pct": round(100 * (cyc["total_pnl"] > 0).mean(), 1),
        "mean_pct_prem": round(cyc["pnl_pct_prem"].mean(), 2),
        "t_stat": round(float(cyc["total_pnl"].mean()
                              / (cyc["total_pnl"].std()
                                 / np.sqrt(len(cyc)))), 2) if len(cyc) > 2 else None,
        "pnl_ex_best": round(cyc["total_pnl"].sum()
                             - cyc["total_pnl"].max(), 0),
        "opt_pnl": round(cyc["opt_pnl"].sum(), 0),
        "hedge_pnl": round(cyc["hedge_pnl"].sum(), 0),
        "costs": round(cyc["costs"].sum(), 0),
        "premium_paid": round(cyc["opt_cost"].sum(), 0),
        "hedges": int(cyc["n_hedges"].sum()),
        "mean_entry_iv": round(cyc["entry_iv"].mean(), 3),
        "mean_realized_vol": round(cyc["realized_vol"].mean(), 3)
        if cyc["realized_vol"].notna().any() else None,
        "bs_vs_real_delta_mae": round(float((dc.bs - dc.real).abs().mean()), 4)
        if len(dc) else None,
        "qa_recon": "PASS" if abs(
            (cyc.opt_pnl + cyc.hedge_pnl - cyc.costs).sum() - tot) < 1.0
        else "FAIL",
    }


def main():
    print("loading option chains and 5-min bars ...")
    opt = load_options()
    bars = load_bars()
    print(f"  options {len(opt):,} rows, {opt.trade_date.nunique()} dates")
    print(f"  bars    {len(bars):,} rows")

    base = Config()
    grid = [base]
    for h in ("bars_1", "bars_3", "bars_6", "bars_12", "bars_78",
              "band_5", "band_10", "band_20"):
        grid.append(replace(base, hedge=h))
    for t, lo, hi in [(30, 21, 45), (90, 60, 120)]:
        grid.append(replace(base, dte=t, dte_lo=lo, dte_hi=hi))
    for s in ("call", "put"):
        grid.append(replace(base, structure=s))
    for h in ("bars_6",):
        for t, lo, hi in [(30, 21, 45), (90, 60, 120)]:
            grid.append(replace(base, hedge=h, dte=t, dte_lo=lo, dte_hi=hi))
    # gross (no friction at all) -- isolates how much the hedging costs
    for h in ("daily", "bars_6", "bars_1"):
        grid.append(replace(base, hedge=h, costs=False))

    rows, ledger, seen = [], None, set()
    for cfg in grid:
        if cfg.label() in seen:
            continue
        seen.add(cfg.label())
        bt = GammaScalp(opt, bars, cfg)
        cyc = bt.run()
        if cfg == base:
            ledger = cyc
        s = summarize(bt, cyc)
        rows.append(s)
        print(f"  {s['config']:22s} cycles={s.get('cycles',0):3d} "
              f"pnl={s.get('total_pnl',0):>11,.0f}  "
              f"iv={s.get('mean_entry_iv')}  rv={s.get('mean_realized_vol')}  "
              f"hedges={s.get('hedges',0):>6,}  {s.get('qa_recon','')}")

    grid_df = pd.DataFrame(rows)
    ledger.to_csv(ROOT / "gamma_scalp_cycles.csv", index=False)
    grid_df.to_csv(ROOT / "gamma_scalp_grid.csv", index=False)
    QA_DIR.mkdir(exist_ok=True)
    fails = (grid_df["qa_recon"] != "PASS").sum()
    with open(QA_DIR / "gamma_scalp_report.txt", "w") as f:
        f.write("R5 DELTA-HEDGED LONG GAMMA -- BACKTEST REPORT\n")
        f.write(f"run: {pd.Timestamp.now():%Y-%m-%d %H:%M}\n")
        f.write("Options priced at the 20% rule from real EOD quotes.\n")
        f.write("Hedges execute at the BAR CLOSE (never the high/low) and pay\n")
        f.write("half the spread; IBKR Pro Fixed share costs per band_lab.\n")
        f.write("'daily' uses the REAL EOD delta column -- no model. Intraday\n")
        f.write("schedules use BS delta on the contract's own EOD IV; the\n")
        f.write("bs_vs_real_delta_mae column re-validates that every EOD.\n\n")
        f.write(f"BASE CONFIG {asdict(base)}\n\n")
        f.write(grid_df.to_string(index=False))
        led = ledger.copy()
        led["year"] = led["entry"].str.slice(0, 4)
        yr = led.groupby("year").agg(cycles=("total_pnl", "size"),
                                     pnl=("total_pnl", "sum"),
                                     pct_prem=("pnl_pct_prem", "mean"),
                                     mean_iv=("entry_iv", "mean"),
                                     mean_rv=("realized_vol", "mean"))
        f.write("\n\nBASE CONFIG BY YEAR (real EOD deltas, no model)\n")
        f.write(yr.round(3).to_string())
        f.write("\n\nBASE CONFIG CYCLES\n")
        f.write(ledger.to_string(index=False))
        f.write(f"\n\nQA reconciliation failures: {fails} of {len(grid_df)}\n")
    print(f"\nwrote gamma_scalp_grid.csv, gamma_scalp_cycles.csv, "
          f"qa/gamma_scalp_report.txt  (QA fails: {fails}/{len(grid_df)})")


if __name__ == "__main__":
    main()
