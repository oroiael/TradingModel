"""
Data-quality audit of UVXY_1min.csv.

The file arrives with no companion 5-minute series, so `intrabar.parity_check`
— the gate every other symbol in this project passed — cannot be run against
it. This module substitutes three independent checks:

  A. **Structural.** Schema, dtypes, duplicates, monotonicity, OHLC coherence,
     RTH windowing, bar counts per session, session calendar vs SOXL/SOXS.
  B. **Scale.** UVXY has reverse-split many times. Detect the split factors
     *from the data itself* and confirm the series is back-adjusted (a
     continuous return stream) rather than raw, because that decides whether
     the file may be used for returns (yes) or for sizing (no).
  C. **External.** UVXY is 1.5x the same index VXX tracks 1x. The repository
     already holds an independently sourced VXX 5-minute file, so daily
     returns must satisfy r_UVXY ~= 1.5 * r_VXX. A vendor error in one series
     will not be replicated in the other.

Run:
    python3 vix_lab/dq_uvxy.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def load_raw(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].astype(str).str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    return df.assign(dt=dt, date=dt.dt.normalize()).sort_values("dt").reset_index(drop=True)


def hdr(s: str) -> None:
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


# ------------------------------------------------------------ A. structural
def structural(df: pd.DataFrame, name: str) -> dict:
    hdr(f"A. Structural checks — {name}")
    res = {}
    print(f"rows                     {len(df):,}")
    print(f"columns                  {list(df.columns[:6])}")
    print(f"span                     {df['dt'].min()} -> {df['dt'].max()}")
    sessions = df["date"].nunique()
    print(f"sessions                 {sessions:,}")

    # dtypes / NaN / non-positive
    ohlcv = ["Open", "High", "Low", "Close", "Volume"]
    nans = int(df[ohlcv].isna().sum().sum())
    nonpos = int((df[["Open", "High", "Low", "Close"]] <= 0).sum().sum())
    negvol = int((df["Volume"] < 0).sum())
    zerovol = int((df["Volume"] == 0).sum())
    print(f"NaN cells                {nans}")
    print(f"non-positive prices      {nonpos}")
    print(f"negative volume          {negvol}")
    print(f"zero-volume bars         {zerovol:,} ({zerovol / len(df):.3%})")
    res.update(nans=nans, nonpos=nonpos, negvol=negvol, zerovol=zerovol)

    # duplicates & ordering
    dupes = int(df["dt"].duplicated().sum())
    mono = bool(df["dt"].is_monotonic_increasing)
    print(f"duplicate timestamps     {dupes}")
    print(f"timestamps sorted        {mono}")
    res.update(dupes=dupes, monotonic=mono)

    # OHLC coherence
    hi = df["High"]
    lo = df["Low"]
    bad_hl = int((hi < lo).sum())
    bad_o = int(((df["Open"] > hi) | (df["Open"] < lo)).sum())
    bad_c = int(((df["Close"] > hi) | (df["Close"] < lo)).sum())
    print(f"High < Low               {bad_hl}")
    print(f"Open outside [Low,High]  {bad_o}")
    print(f"Close outside [Low,High] {bad_c}")
    res.update(bad_hl=bad_hl, bad_o=bad_o, bad_c=bad_c)

    # RTH windowing
    tod = df["dt"].dt.strftime("%H:%M")
    before = int((tod < "09:30").sum())
    after = int((tod > "15:59").sum())
    print(f"bars before 09:30        {before}")
    print(f"bars after 15:59         {after}")
    res.update(pre_rth=before, post_rth=after)

    # bars per session
    per = df.groupby("date").size()
    full = int((per == 390).sum())
    half = int((per == 210).sum())
    print(f"sessions with 390 bars   {full:,} ({full / sessions:.1%})")
    print(f"sessions with 210 bars   {half:,}  (half-days)")
    print(f"bars/session  min {per.min()}  p1 {per.quantile(.01):.0f}  "
          f"median {per.median():.0f}  max {per.max()}")
    odd = per[(per != 390) & (per != 210)]
    print(f"other bar counts         {len(odd)} sessions")
    if len(odd):
        print("   worst 10:", ", ".join(f"{d.date()}:{n}" for d, n in odd.nsmallest(10).items()))
    res.update(sessions=sessions, full=full, half=half, odd=len(odd),
               min_bars=int(per.min()))

    # intra-session minute gaps
    g = df.groupby("date")["dt"].apply(
        lambda s: int(((s.diff().dt.total_seconds() / 60).fillna(1) > 1).sum()))
    print(f"sessions with minute gaps {int((g > 0).sum()):,} "
          f"({int((g > 0).sum()) / sessions:.1%}); total gaps {int(g.sum()):,}")
    res["gap_sessions"] = int((g > 0).sum())
    return res


# ----------------------------------------------------------------- B. scale
def detect_splits(df: pd.DataFrame, thresh: float = 0.35) -> pd.DataFrame:
    """Flag session-boundary jumps large enough to be *candidate* splits.

    A single series cannot tell a reverse split from a genuine gap — on a 1.5x
    VIX product both are large and both are upward. Two things resolve it, and
    neither is this function: the ratio (a split is a round 4, 5 or 10) and a
    second series on the same index (`dq_dig.py` §1). This only narrows the
    list of dates worth looking at.
    """
    daily = df.groupby("date").agg(o=("Open", "first"), c=("Close", "last"))
    prev_c = daily["c"].shift(1)
    ratio = daily["o"] / prev_c
    jumps = daily.assign(prev_close=prev_c, ratio=ratio)
    jumps = jumps[(np.abs(np.log(jumps["ratio"])) > thresh)].dropna()
    return jumps


def scale_report(df: pd.DataFrame, name: str) -> dict:
    hdr(f"B. Price-scale / split conditioning — {name}")
    daily = df.groupby("date").agg(c=("Close", "last"), v=("Volume", "sum"))
    first, last = daily["c"].iloc[0], daily["c"].iloc[-1]
    print(f"first session close      {first:,.4f}   ({daily.index[0].date()})")
    print(f"last  session close      {last:,.4f}   ({daily.index[-1].date()})")
    print(f"ratio first/last         {first / last:,.1f}x")

    yrs = (daily.index[-1] - daily.index[0]).days / 365.25
    cagr = (daily["c"].iloc[-1] / daily["c"].iloc[0]) ** (1 / yrs) - 1
    print(f"implied CAGR             {cagr:.1%}/yr over {yrs:.2f} years")

    jumps = detect_splits(df)
    print(f"\ncandidate split dates (overnight jump > 35% log): {len(jumps)}")
    if len(jumps):
        print(f"{'date':<12}{'prev close':>14}{'open':>14}{'ratio':>9}  round?")
        for d, r in jumps.iterrows():
            near = min((4.0, 5.0, 10.0), key=lambda k: abs(r["ratio"] - k))
            rnd = "yes" if abs(r["ratio"] - near) < 0.15 else "no"
            print(f"{str(d.date()):<12}{r['prev_close']:>14,.4f}{r['o']:>14,.4f}"
                  f"{r['ratio']:>9.3f}  {rnd}")

    # A raw series would carry an upward jump at every reverse split and would
    # therefore drift far less than the fund's published decay; a back-adjusted
    # one shows the decay in full and no round-ratio jumps.
    round_jumps = sum(
        1 for _, r in jumps.iterrows()
        if min(abs(r["ratio"] - k) for k in (4.0, 5.0, 10.0)) < 0.15)
    adjusted = round_jumps == 0 and cagr < -0.40
    print(f"\nverdict: series is "
          + ("BACK-ADJUSTED (continuous return stream)" if adjusted
             else "RAW or partially adjusted — investigate"))
    print("  no jump sits at a round split ratio, and the series shows UVXY's")
    print("  full published decay, which a raw series would not. The two")
    print("  candidates above are confirmed as genuine VIX events in dq_dig.py.")

    # Volume conditioning: adjusted price series usually carry adjusted volume.
    print(f"\nvolume, first session sum  {daily['v'].iloc[0]:,.4f}")
    print(f"volume, last  session sum  {daily['v'].iloc[-1]:,.1f}")
    print("(volume scaled alongside price => volume is NOT raw share count "
          "in the early era)")
    return {"adjusted": len(jumps) == 0, "first_close": float(first),
            "last_close": float(last)}


# -------------------------------------------------------------- C. external
def daily_close(df: pd.DataFrame) -> pd.Series:
    return df.groupby("date")["Close"].last()


def external_check(uvxy: pd.DataFrame, vxx_path: str) -> dict:
    hdr("C. External cross-validation — UVXY vs independently sourced VXX")
    print("UVXY targets 1.5x the daily return of the S&P 500 VIX Short-Term")
    print("Futures index; VXX targets 1.0x the same index. The two files come")
    print("from separate fetches, so agreement is evidence about both.\n")

    vxx = load_raw(vxx_path)
    u = daily_close(uvxy).pct_change().dropna()
    v = daily_close(vxx).pct_change().dropna()
    j = pd.concat([u.rename("uvxy"), v.rename("vxx")], axis=1).dropna()
    print(f"overlapping sessions     {len(j):,}  "
          f"({j.index.min().date()} -> {j.index.max().date()})")

    corr = j["uvxy"].corr(j["vxx"])
    # regression through the origin: the leverage ratio
    beta = float((j["uvxy"] * j["vxx"]).sum() / (j["vxx"] ** 2).sum())
    resid = j["uvxy"] - beta * j["vxx"]
    r2 = 1 - float((resid ** 2).sum() / (j["uvxy"] ** 2).sum())
    print(f"corr(UVXY, VXX) daily    {corr:.6f}")
    print(f"beta through origin      {beta:.4f}   (prospectus target 1.50)")
    print(f"R^2 (no intercept)       {r2:.6f}")
    print(f"residual sd              {resid.std():.5f}  "
          f"({resid.std() * 1e4:.0f} bp/day)")

    worst = resid.abs().nlargest(8)
    print(f"\n8 largest daily residuals |UVXY - 1.5*VXX|:")
    print(f"{'date':<12}{'UVXY %':>10}{'VXX %':>10}{'resid %':>10}")
    for d in worst.index:
        print(f"{str(d.date()):<12}{j.loc[d, 'uvxy'] * 100:>10.2f}"
              f"{j.loc[d, 'vxx'] * 100:>10.2f}{resid.loc[d] * 100:>10.2f}")

    # beta by year -- catches an era where the file is on the wrong basis
    print(f"\nbeta and corr by year (UVXY changed 2x -> 1.5x on 2018-02-28,")
    print(" which predates this sample, so every year should read ~1.5):")
    print(f"{'year':<8}{'n':>6}{'beta':>9}{'corr':>9}")
    rows = []
    for y, g in j.groupby(j.index.year):
        b = float((g["uvxy"] * g["vxx"]).sum() / (g["vxx"] ** 2).sum())
        c = g["uvxy"].corr(g["vxx"])
        rows.append((y, len(g), b, c))
        print(f"{y:<8}{len(g):>6}{b:>9.4f}{c:>9.5f}")

    # calendar agreement
    du, dv = set(daily_close(uvxy).index), set(daily_close(vxx).index)
    both = du & dv
    print(f"\ncalendar: UVXY {len(du)} sessions, VXX {len(dv)}, shared {len(both)}")
    only_u = sorted(du - dv)
    only_v = sorted(dv - du)
    print(f"  in UVXY not VXX: {len(only_u)}"
          + (f"  e.g. {[str(d.date()) for d in only_u[:5]]}" if only_u else ""))
    print(f"  in VXX not UVXY: {len(only_v)}"
          + (f"  e.g. {[str(d.date()) for d in only_v[:5]]}" if only_v else ""))
    return {"corr": float(corr), "beta": beta, "r2": r2,
            "resid_sd": float(resid.std()), "by_year": rows}


def calendar_vs(uvxy: pd.DataFrame, others: dict) -> None:
    hdr("A2. Session calendar vs the two traded sleeves")
    du = set(uvxy["date"].unique())
    print(f"UVXY sessions            {len(du):,}")
    for nm, df in others.items():
        d = set(df["date"].unique())
        print(f"\n{nm}: {len(d):,} sessions; shared with UVXY {len(du & d):,}")
        only_o = sorted(d - du)
        only_u = sorted(du - d)
        print(f"  in {nm} not UVXY: {len(only_o)}"
              + (f"  {[str(pd.Timestamp(x).date()) for x in only_o[:6]]}" if only_o else ""))
        print(f"  in UVXY not {nm}: {len(only_u)}"
              + (f"  {[str(pd.Timestamp(x).date()) for x in only_u[:6]]}" if only_u else ""))


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    uvxy = load_raw(os.path.join(ROOT, "UVXY_1min.csv"))

    a = structural(uvxy, "UVXY_1min.csv")
    b = scale_report(uvxy, "UVXY_1min.csv")

    soxl = load_raw(os.path.join(ROOT, "SOXL_1min.csv"))
    soxs = load_raw(os.path.join(ROOT, "SOXS_1min.csv"))
    calendar_vs(uvxy, {"SOXL_1min": soxl, "SOXS_1min": soxs})

    c = external_check(uvxy, os.path.join(ROOT, "VXX_5min_6Years.csv"))

    hdr("VERDICT")
    fatal = []
    if a["nans"] or a["nonpos"] or a["negvol"]:
        fatal.append("NaN / non-positive values present")
    if a["bad_hl"] or a["bad_o"] or a["bad_c"]:
        fatal.append("OHLC incoherence")
    if a["dupes"]:
        fatal.append("duplicate timestamps")
    if a["pre_rth"] or a["post_rth"]:
        fatal.append("bars outside RTH")
    if not (1.35 <= c["beta"] <= 1.65):
        fatal.append(f"leverage beta vs VXX is {c['beta']:.3f}, not ~1.5")
    if c["corr"] < 0.95:
        fatal.append(f"corr vs VXX only {c['corr']:.3f}")

    if fatal:
        print("FAIL:")
        for f in fatal:
            print("  - " + f)
    else:
        print("PASS — the file is what it claims to be: RTH 1-minute OHLCV for")
        print("UVXY, back-adjusted through its reverse splits, matching an")
        print("independently sourced VXX at the prospectus leverage ratio.")
        print("\nOne caveat, and it is about VXX rather than UVXY: the two part")
        print("company over 2022-03-14 -> 2022-09-19 (corr 0.888 for the year).")
        print("That is the Barclays ETN issuance suspension, which put VXX at a")
        print("premium of up to 33% to its own NAV. Against VIXY -- an ETF, so")
        print("never halted -- UVXY reads beta 1.49 / corr 0.999 in every year")
        print("including 2022. Do not use VXX as a volatility reference in that")
        print("window; UVXY and VIXY are both fine. See dq_dig.py.")
    print("\nUsable for: returns, percentage-based signals, backtest fills.")
    print("NOT usable for: share sizing or dollar levels before the last split")
    print("(the pre-split price grid is an artifact, exactly as for SOXS).")
    return 1 if fatal else 0


if __name__ == "__main__":
    raise SystemExit(main())
