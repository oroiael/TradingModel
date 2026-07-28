"""
Band Lab -- SOXL intraday range/band deep dive.

Questions (user):
  1. What band does SOXL churn in daily? How much oscillation is harvestable?
  2. What signals, known early, tell you how wide that day's band will be?
  3. Steep drops/climbs ("excursions") -- do they cluster in week-long bursts,
     and are there tells for when/how they start?
  4. Prototype: harvest the churn at the band edges while staying neutral to
     (or riding) a major breakout.

Data: SOXL_5min_6Years.csv via cycle_lab loader (split-adjusted).
Outputs: band_lab/out/*.csv + printed report.
"""

import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "cycle_lab"))
from one_pct_cycle_lab import load_bars

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

def zigzag_legs(h, l, thresh):
    """Count completed swings >= thresh (fraction) using bar highs/lows."""
    legs = 0
    hi, lo = h[0], l[0]
    direction = 0            # +1 riding up-swing, -1 down-swing
    for i in range(1, len(h)):
        hi = max(hi, h[i]); lo = min(lo, l[i])
        if direction >= 0 and h[i] < hi and (hi - l[i]) / hi >= thresh:
            legs += 1; direction = -1; lo = l[i]; hi = h[i]
        elif direction <= 0 and l[i] > lo and (h[i] - lo) / lo >= thresh:
            legs += 1; direction = 1; hi = h[i]; lo = l[i]
    return legs

def main():
    bars = load_bars()
    bars["t"] = bars["dt"].dt.time
    g = bars.groupby("date")
    daily = g.agg(o=("Open", "first"), h=("High", "max"),
                  l=("Low", "min"), c=("Close", "last"))
    daily["range_pct"] = (daily["h"] - daily["l"]) / daily["o"] * 100
    daily["co_pct"] = (daily["c"] / daily["o"] - 1) * 100
    daily["gap_pct"] = (daily["o"] / daily["c"].shift() - 1) * 100
    daily["atr5"] = daily["range_pct"].rolling(5).mean().shift()
    daily["year"] = daily.index.year

    # opening range (first 30 min = 6 bars) and per-day micro stats
    or30, zz1, zz2, steep, steep_t, closepos = {}, {}, {}, {}, {}, {}
    for d, gb in g:
        h = gb["High"].to_numpy(); l = gb["Low"].to_numpy()
        c = gb["Close"].to_numpy(); o = gb["Open"].to_numpy()
        or30[d] = (h[:6].max() - l[:6].min()) / o[0] * 100
        zz1[d] = zigzag_legs(h, l, 0.01)
        zz2[d] = zigzag_legs(h, l, 0.02)
        # steepest 30-min (6-bar) excursion and when it starts
        if len(c) > 6:
            m = pd.Series(c).pct_change(6).abs()
            steep[d] = m.max() * 100
            steep_t[d] = gb["t"].iloc[int(m.idxmax())]
        rng = h.max() - l.min()
        closepos[d] = (c[-1] - l.min()) / rng if rng > 0 else 0.5
    for name, dd in [("or30_pct", or30), ("zz1", zz1), ("zz2", zz2),
                     ("steep30_pct", steep), ("close_pos", closepos)]:
        daily[name] = pd.Series(dd)
    daily["steep30_time"] = pd.Series(steep_t)

    print("=" * 72)
    print("1. THE DAILY BAND")
    print("=" * 72)
    q = daily["range_pct"].describe(percentiles=[.25, .5, .75, .9])
    print(f"daily high-low range: median {q['50%']:.1f}%  IQR {q['25%']:.1f}-"
          f"{q['75%']:.1f}%  90th pct {q['90%']:.1f}%")
    print("\nby year:")
    print(daily.groupby("year")["range_pct"].median().round(1).to_string())
    px = daily["c"].iloc[-1]
    print(f"\nat the last close (${px:.0f}) the median band is "
          f"${px*q['50%']/100:.0f} wide, 90th pct ${px*q['90%']/100:.0f}")
    print(f"\nharvestable churn (completed swings/day, 6-yr avg):")
    print(f"  >=1% swings: mean {daily['zz1'].mean():.1f}/day  "
          f"median {daily['zz1'].median():.0f}  "
          f"(days with 0: {(daily['zz1']==0).mean()*100:.0f}%)")
    print(f"  >=2% swings: mean {daily['zz2'].mean():.1f}/day  "
          f"median {daily['zz2'].median():.0f}")
    print("\n>=1% swings per day by year:")
    print(daily.groupby("year")["zz1"].mean().round(1).to_string())

    # when is the band built? intraday vol profile + range completion
    bars["absr"] = bars.groupby("date")["Close"].pct_change().abs()
    prof = bars.groupby("t")["absr"].mean() * 100
    prof.to_csv(os.path.join(OUT, "intraday_vol_profile.csv"))
    b = bars.copy()
    b["cmax"] = b.groupby("date")["High"].cummax()
    b["cmin"] = b.groupby("date")["Low"].cummin()
    b["day_h"] = b.groupby("date")["High"].transform("max")
    b["day_l"] = b.groupby("date")["Low"].transform("min")
    b["frac"] = (b["cmax"] - b["cmin"]) / (b["day_h"] - b["day_l"])
    comp = b.groupby("t")["frac"].median()
    comp.to_csv(os.path.join(OUT, "range_completion_by_time.csv"))
    marks = {t: comp.loc[t] for t in comp.index
             if str(t) in ("10:00:00", "10:30:00", "11:30:00", "13:00:00", "15:00:00")}
    print("\nmedian fraction of the day's final range already set by:")
    for t, v in marks.items():
        print(f"  {t}: {v*100:.0f}%")
    v5 = prof.sort_values(ascending=False)
    print(f"\nmost volatile 5-min buckets: " +
          ", ".join(f"{t} ({x:.2f}%)" for t, x in v5.head(4).items()))

    print()
    print("=" * 72)
    print("2. SIGNALS FOR TODAY'S BAND WIDTH")
    print("=" * 72)
    d2 = daily.dropna(subset=["atr5", "gap_pct", "or30_pct"]).copy()
    for sig in ["atr5", "gap_pct", "or30_pct"]:
        d2[f"abs_{sig}"] = d2[sig].abs()
    cors = {s: d2["range_pct"].corr(d2[f"abs_{s}"])
            for s in ["atr5", "gap_pct", "or30_pct"]}
    print("corr with today's range:  " +
          "  ".join(f"|{k}| {v:.2f}" for k, v in cors.items()))
    d2["or_q"] = pd.qcut(d2["or30_pct"], 5, labels=False) + 1
    tab = d2.groupby("or_q").agg(
        or30_med=("or30_pct", "median"), day_range_med=("range_pct", "median"),
        mult=("range_pct", "median"), zz1=("zz1", "mean"),
        trend_share=("close_pos", lambda x: ((x > .9) | (x < .1)).mean()))
    tab["mult"] = tab["day_range_med"] / tab["or30_med"]
    print("\nopening-30-min range quintile -> the day (medians):")
    print(tab.round(2).to_string())
    tab.to_csv(os.path.join(OUT, "or30_quintiles.csv"))
    print(f"\nrule of thumb: day range ~= {(d2['range_pct']/d2['or30_pct']).median():.1f}"
          f" x opening-30-min range (median multiplier)")
    d2["gap_q"] = pd.qcut(d2["gap_pct"].abs(), 4, labels=False) + 1
    gt = d2.groupby("gap_q").agg(gap_med=("abs_gap_pct", "median"),
                                 range_med=("range_pct", "median"),
                                 zz1=("zz1", "mean"))
    print("\n|overnight gap| quartile -> day range / churn:")
    print(gt.round(2).to_string())

    print()
    print("=" * 72)
    print("3. EXCURSIONS: STEEP DROPS/CLIMBS AND THEIR CLUSTERING")
    print("=" * 72)
    thr = daily["steep30_pct"].quantile(.9)
    daily["excursion"] = daily["steep30_pct"] >= thr
    print(f"'excursion day' = steepest 30-min move >= {thr:.1f}% (top decile)")
    tt = pd.to_datetime(daily.loc[daily["excursion"], "steep30_time"].astype(str))
    print("\nwhen the steep move happens (excursion days):")
    print((tt.dt.hour.value_counts(normalize=True).sort_index() * 100)
          .round(0).astype(int).astype(str).add("%").to_string())
    p_uncond = daily["excursion"].mean()
    p_cond = daily["excursion"][daily["excursion"].shift(fill_value=False)].mean()
    p_cond5 = daily["excursion"][daily["excursion"].rolling(5).max().shift()
                                 .fillna(0) > 0].mean()
    print(f"\nP(excursion day) unconditional: {p_uncond*100:.0f}%")
    print(f"P(excursion | excursion yesterday): {p_cond*100:.0f}%")
    print(f"P(excursion | excursion in last 5 days): {p_cond5*100:.0f}%")
    # vol regimes: high-vol day vs 63d rolling median, episode runs
    med63 = daily["range_pct"].rolling(63).median().shift()
    daily["hivol"] = daily["range_pct"] > 1.5 * med63
    runs, run = [], 0
    for x in daily["hivol"].fillna(False):
        if x: run += 1
        elif run: runs.append(run); run = 0
    runs = pd.Series(runs)
    print(f"\nhigh-vol day = range > 1.5x trailing 63d median ({daily['hivol'].mean()*100:.0f}% of days)")
    print(f"P(high-vol | high-vol yesterday): "
          f"{daily['hivol'][daily['hivol'].shift(fill_value=False)].mean()*100:.0f}%  "
          f"(clustering vs {daily['hivol'].mean()*100:.0f}% base)")
    print(f"burst lengths: median {runs.median():.0f}d, 75th {runs.quantile(.75):.0f}d, "
          f"max {runs.max():.0f}d")
    # biggest episodes
    daily["hv30"] = daily["hivol"].rolling(10).sum()
    top = daily["hv30"].nlargest(40)
    eps, used = [], set()
    for d, v in top.items():
        if all(abs((d - u).days) > 30 for u in used):
            eps.append((d, v)); used.add(d)
        if len(eps) >= 8:
            break
    print("\ndensest high-vol bursts (>= high-vol days in trailing 10 sessions):")
    for d, v in sorted(eps):
        print(f"  around {d.date()}: {int(v)}/10 days high-vol")
    gap_led = daily["gap_pct"].abs()[daily["excursion"]].median()
    gap_norm = daily["gap_pct"].abs()[~daily["excursion"]].median()
    print(f"\n|gap| on excursion days: median {gap_led:.1f}% vs {gap_norm:.1f}% normal")
    or_led = daily["or30_pct"][daily["excursion"]].median()
    or_norm = daily["or30_pct"][~daily["excursion"]].median()
    print(f"OR30 on excursion days: median {or_led:.1f}% vs {or_norm:.1f}% normal")

    print()
    print("=" * 72)
    print("4. PROTOTYPE: HARVEST THE CHURN, STAY SAFE ON BREAKOUTS")
    print("=" * 72)
    # Long-only OR-band day plan, evaluated per day in % terms:
    #  after 10:00, buy a touch of OR low; target OR mid; stop OR_low - 0.5*OR
    #  (the stop IS the breakout protection). On an upside breakout
    #  (trade above OR high + 0.25*OR) buy and hold to close (ride it).
    res = []
    for d, gb in g:
        h = gb["High"].to_numpy(); l = gb["Low"].to_numpy()
        c = gb["Close"].to_numpy(); o = gb["Open"].to_numpy()
        if len(c) < 12:
            continue
        orh, orl = h[:6].max(), l[:6].min()
        orr = orh - orl
        if orr <= 0:
            continue
        mid = (orh + orl) / 2
        stop = orl - 0.5 * orr
        bo = orh + 0.25 * orr
        fade_pnl = 0.0; fades = 0; state = 0; entry = 0.0
        bo_pnl = 0.0; bo_hit = 0
        for i in range(6, len(c)):
            if state == 0 and l[i] <= orl and fades < 3:
                state = 1; entry = orl; fades += 1
            if state == 1:
                if l[i] <= stop:
                    fade_pnl += stop / entry - 1; state = 0
                elif h[i] >= mid:
                    fade_pnl += mid / entry - 1; state = 0
            if bo_hit == 0 and h[i] >= bo:
                bo_hit = 1
                bo_pnl = c[-1] / bo - 1
        if state == 1:
            fade_pnl += c[-1] / entry - 1
        res.append({"date": d, "fades": fades, "fade_pnl": fade_pnl,
                    "bo": bo_hit, "bo_pnl": bo_pnl,
                    "both_pnl": fade_pnl + bo_pnl})
    r = pd.DataFrame(res).set_index("date")
    r.to_csv(os.path.join(OUT, "or_band_plan_daily.csv"))
    yr = r.index.year
    print("day plan, all in % of capital-per-trade (no compounding, no costs):")
    print(f"  fade trades: {r['fades'].sum():.0f} "
          f"({r['fades'].mean():.2f}/day), day-level win rate "
          f"{(r.loc[r['fades']>0,'fade_pnl']>0).mean()*100:.0f}%")
    print(f"  fade edge:  mean {r['fade_pnl'].mean()*100:+.2f}%/day  "
          f"annual sum ~{r['fade_pnl'].mean()*252*100:+.0f}%")
    print(f"  breakout rides: {r['bo'].sum():.0f} days "
          f"({r['bo'].mean()*100:.0f}%), mean ride {r.loc[r['bo']==1,'bo_pnl'].mean()*100:+.2f}%")
    print(f"  combined:  mean {r['both_pnl'].mean()*100:+.2f}%/day")
    print("\nby year (mean %/day):")
    print((r.groupby(yr)[["fade_pnl", "bo_pnl", "both_pnl"]].mean() * 100)
          .round(2).to_string())

    daily.to_csv(os.path.join(OUT, "daily_band_stats.csv"))

if __name__ == "__main__":
    main()
