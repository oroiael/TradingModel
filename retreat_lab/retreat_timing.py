"""How long SOXL holds an upswing before giving back a fraction of it.

Runs any (upswing, retreat) threshold pair; CONFIGS below holds the ones asked
for -- 2%/0.5% and 1%/0.25%.

Measured from SOXL_1min.csv (1-min OHLCV, 2019-12-31 -> 2026-07-30, 1,653
sessions, complete grid, split-adjusted). Cross-checked on SOXL_5min_6Years.csv.

Event definition (the question as asked):
  1. ANCHOR   running trough of the series while we are not in an episode.
  2. TRIGGER  first bar >= anchor * (1 + up)   -> the "upswing".
  3. PEAK     running maximum from the trigger bar onward.
  4. RETREAT  first bar <= peak * (1 - down)   -> the "retreat".
     Leg A = trigger -> peak, Leg B = peak -> retreat. If the trigger bar is
     itself the peak, Leg A = 0 and the whole wait is Leg B.
  5. RESET    anchor restarts from the retreat bar; hunt for the next upswing.

Time is reported two ways because the file is regular-trading-hours only:
  market minutes = tradeable 1-min bars elapsed (index distance on the grid)
  wall minutes   = calendar elapsed, which includes overnights and weekends.

Usage:  python3 retreat_lab/retreat_timing.py [up_bps dn_bps]
"""
import os, sys, csv, datetime as dt
from decimal import Decimal
from collections import Counter, OrderedDict

ROOT = "/home/user/TradingModel"
OUT = os.path.join(ROOT, "retreat_lab/out")

# Thresholds are carried in BASIS POINTS as integers, and every price in both
# files is exactly 2 decimals, so prices are carried as integer cents and both
# tests are exact integer comparisons: px*10000 >= trough*(10000+up_bps) and
# px*10000 <= peak*(10000-dn_bps). Testing them in floating point silently drops
# exact touches -- 14.00 * 1.02 evaluates to 14.280000000000001, so a genuine
# +2.000% move to 14.28 fails a `>=` test. That cost 9 real triggers.
BPS = 10000

# (upswing bps, retreat bps) -- 2%/0.5% and 1%/0.25%
CONFIGS = [(200, 50), (100, 25)]


def bl(bps):
    """200 -> '2%', 25 -> '0.25%'."""
    return f"{bps / 100:.2f}".rstrip("0").rstrip(".") + "%"


def tag(up_bps, dn_bps):
    return f"up{up_bps}_dn{dn_bps}"


# ---------------------------------------------------------------- data

def cents(s):
    """'14.28' -> 1428, exactly. Guards against any file drifting off 2dp."""
    d = Decimal(s)
    q = (d * 100).to_integral_exact()
    return int(q)


def load(name):
    """-> list of (ts, open, high, low, close); prices are integer cents."""
    bars = []
    with open(os.path.join(ROOT, name)) as f:
        r = csv.reader(f)
        next(r)
        for a in r:
            ts = dt.datetime.strptime(
                a[0].replace(" America/New_York", ""), "%Y%m%d %H:%M:%S")
            bars.append((ts, cents(a[1]), cents(a[2]), cents(a[3]), cents(a[4])))
    return bars


def boundary_kind(d1, d2):
    """Classify the non-trading gap between two consecutive session dates."""
    gap = (d2 - d1).days
    if gap == 1:
        return "overnight"
    if any((d1 + dt.timedelta(k)).weekday() >= 5 for k in range(1, gap)):
        return "weekend"
    return "holiday"          # a weekday market holiday, no Sat/Sun in the span


def span_kinds(dates, i, j):
    """Every session boundary crossed between bar i and bar j."""
    out = []
    for k in range(i, j):
        if dates[k] != dates[k + 1]:
            out.append(boundary_kind(dates[k], dates[k + 1]))
    return out


def worst(kinds):
    for k in ("weekend", "holiday", "overnight"):
        if k in kinds:
            return k
    return "intraday"


# ---------------------------------------------------------------- engine

def episodes(bars, up_bps, dn_bps, mode="close"):
    """Run the state machine. mode 'close' uses bar closes only; mode
    'intrabar' triggers/peaks on High and retreats on Low (earliest possible
    detection, but the within-bar sequence is unknowable at 1-min)."""
    up_n, dn_n = BPS + up_bps, BPS - dn_bps
    ts = [b[0] for b in bars]
    dates = [b[0].date() for b in bars]
    if mode == "close":
        up_px = dn_px = [b[4] for b in bars]
    else:
        up_px, dn_px = [b[2] for b in bars], [b[3] for b in bars]

    eps = []
    seeking = True
    trough = dn_px[0]; trough_i = 0
    peak = peak_i = trig_i = None
    anchor = anchor_i = None

    for i in range(len(bars)):
        if seeking:
            if dn_px[i] < trough:
                trough, trough_i = dn_px[i], i
            if up_px[i] * BPS >= trough * up_n:
                seeking = False
                anchor, anchor_i = trough, trough_i
                trig_i = i
                peak, peak_i = up_px[i], i
        else:
            if up_px[i] > peak:
                peak, peak_i = up_px[i], i
            if dn_px[i] * BPS <= peak * dn_n:
                eps.append(dict(
                    anchor_i=anchor_i, trig_i=trig_i, peak_i=peak_i, ret_i=i,
                    anchor=anchor / 100, trig=up_px[trig_i] / 100,
                    peak=peak / 100, ret=dn_px[i] / 100,
                    a_mkt=peak_i - trig_i, b_mkt=i - peak_i, t_mkt=i - trig_i,
                    a_wall=(ts[peak_i] - ts[trig_i]).total_seconds() / 60,
                    b_wall=(ts[i] - ts[peak_i]).total_seconds() / 60,
                    t_wall=(ts[i] - ts[trig_i]).total_seconds() / 60,
                    a_kinds=span_kinds(dates, trig_i, peak_i),
                    b_kinds=span_kinds(dates, peak_i, i),
                    t_kinds=span_kinds(dates, trig_i, i),
                    ret_at_open=(dates[i] != dates[i - 1]) if i else False,
                ))
                seeking = True
                trough, trough_i = dn_px[i], i
    censored = None if seeking else dict(trig_i=trig_i, peak_i=peak_i)
    return eps, censored


# ---------------------------------------------------------------- stats

def pct(xs, p):
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def describe(out, xs, label, unit="min"):
    out(f"  {label:<27} n={len(xs):<6}"
        f"min={min(xs):>6.0f} p25={pct(xs,25):>7.0f} med={pct(xs,50):>7.0f} "
        f"p75={pct(xs,75):>7.0f} p90={pct(xs,90):>7.0f} p99={pct(xs,99):>8.0f} "
        f"max={max(xs):>8.0f} mean={sum(xs)/len(xs):>8.1f} {unit}")


def fmt_minutes(m):
    """Market minutes -> human scale. 390 market minutes = one full session."""
    if m < 390:
        return f"{m:.0f} min"
    return f"{m:.0f} min ({m/390:.1f} sessions)"


def report(bars, eps, censored, title, fh, up_bps, dn_bps):
    U, D = bl(up_bps), bl(dn_bps)
    def out(s=""):
        print(s); fh.write(s + "\n")

    ts = [b[0] for b in bars]
    n = len(eps)
    out("=" * 100)
    out(title)
    out("=" * 100)
    out(f"Window {ts[0]:%Y-%m-%d} -> {ts[-1]:%Y-%m-%d}   "
        f"{len(bars):,} bars   episodes={n}"
        + (f"   (1 episode still open at the end of the file)" if censored else ""))
    out()

    a = [e["a_mkt"] for e in eps]; b = [e["b_mkt"] for e in eps]
    t = [e["t_mkt"] for e in eps]
    aw = [e["a_wall"] for e in eps]; bw = [e["b_wall"] for e in eps]
    tw = [e["t_wall"] for e in eps]

    out("MARKET MINUTES (tradeable bars elapsed)")
    describe(out, a, f"Leg A  {U} trigger -> peak")
    describe(out, b, f"Leg B  peak -> {D} retreat")
    describe(out, t, "Total  trigger -> retreat")
    out()
    out("WALL-CLOCK MINUTES (calendar time, includes closed hours)")
    describe(out, aw, f"Leg A  {U} trigger -> peak")
    describe(out, bw, f"Leg B  peak -> {D} retreat")
    describe(out, tw, "Total  trigger -> retreat")
    out()

    # --- headline answer
    out("HEADLINE")
    out(f"  Median time from the {U} trigger to the {D} retreat".ljust(54)
        + f": {fmt_minutes(pct(t,50))} of market time")
    out(f"  Median time from the {U} trigger to the peak".ljust(54)
        + f": {fmt_minutes(pct(a,50))}")
    out(f"  Median time from the peak to the {D} retreat".ljust(54)
        + f": {fmt_minutes(pct(b,50))}")
    imm = sum(1 for e in eps if e["a_mkt"] == 0)
    out("  Peak IS the trigger bar (no further run-up)".ljust(54)
        + f": {imm}/{n} = {imm/n:.1%}")
    ru = [e["peak"] / e["trig"] - 1 for e in eps]
    out(f"  Run-up past the {U} line before the peak".ljust(54)
        + f": med {pct(ru,50)*100:.2f}%   p90 {pct(ru,90)*100:.2f}%"
          f"   max {max(ru)*100:.1f}%")
    tot = [e["peak"] / e["anchor"] - 1 for e in eps]
    out("  Full upswing anchor -> peak".ljust(54)
        + f": med {pct(tot,50)*100:.2f}%   p90 {pct(tot,90)*100:.2f}%"
          f"   max {max(tot)*100:.1f}%")
    out()

    out("SURVIVAL — share of episodes still un-retreated after N market minutes")
    for k in (1, 2, 5, 10, 15, 30, 60, 120, 195, 390, 780, 1950):
        alive = sum(1 for x in t if x > k)
        lbl = {195: " (half session)", 390: " (1 session)",
               780: " (2 sessions)", 1950: " (1 week)"}.get(k, "")
        out(f"  > {k:>5} min{lbl:<15} {alive:>5} / {n}  = {alive/n:>6.1%}")
    out()

    # --- the session-boundary question
    out("OVERNIGHT / WEEKEND — episodes whose trigger->retreat window spans a close")
    c = Counter(worst(e["t_kinds"]) for e in eps)
    for k in ("intraday", "overnight", "holiday", "weekend"):
        out(f"  {k:<12} {c[k]:>5} / {n}  = {c[k]/n:>6.1%}")
    spanning = [e for e in eps if e["t_kinds"]]
    out(f"  {'ANY close':<12} {len(spanning):>5} / {n}  = {len(spanning)/n:>6.1%}"
        f"   (crossed {sum(len(e['t_kinds']) for e in eps)} session boundaries in total)")
    out()

    out("  ...of which the RETREAT ITSELF happened across the gap (peak one session,")
    out(f"     {D} breach in a later one — un-actionable while the market was shut):")
    bspan = [e for e in eps if e["b_kinds"]]
    cb = Counter(worst(e["b_kinds"]) for e in bspan)
    out(f"     peak -> retreat crossed a close : {len(bspan)} / {n} = {len(bspan)/n:.1%}"
        f"   (overnight {cb['overnight']}, weekend {cb['weekend']}, holiday {cb['holiday']})")
    gap_done = [e for e in bspan if e["ret_at_open"]]
    cg = Counter(worst(e["b_kinds"]) for e in gap_done)
    out(f"     breached on the very first bar back (gap-down did it) : {len(gap_done)}"
        f"   (overnight {cg['overnight']}, weekend {cg['weekend']}, holiday {cg['holiday']})")
    out()
    out(f"  ...and the run-up leg spanning a close ({U} hit, kept climbing past the bell):")
    aspan = [e for e in eps if e["a_kinds"]]
    ca = Counter(worst(e["a_kinds"]) for e in aspan)
    out(f"     trigger -> peak crossed a close : {len(aspan)} / {n} = {len(aspan)/n:.1%}"
        f"   (overnight {ca['overnight']}, weekend {ca['weekend']}, holiday {ca['holiday']})")
    out()

    # --- time of day: this is what drives the overnight/weekend count
    out("BY TRIGGER TIME OF DAY — a late trigger is what pushes an episode past the bell")
    out(f"  {'trigger window':<16} {'n':>6} {'med min':>8} {'p90':>6} "
        f"{'spans close':>17} {'gap did the retreat':>21}")
    buckets = [("09:30-10:00", 9 * 60 + 30, 10 * 60), ("10:00-11:00", 600, 660),
               ("11:00-12:00", 660, 720), ("12:00-13:00", 720, 780),
               ("13:00-14:00", 780, 840), ("14:00-15:00", 840, 900),
               ("15:00-15:30", 900, 930), ("15:30-16:00", 930, 960)]
    for lbl, lo_m, hi_m in buckets:
        es = [e for e in eps
              if lo_m <= ts[e["trig_i"]].hour * 60 + ts[e["trig_i"]].minute < hi_m]
        if not es:
            continue
        xs = [e["t_mkt"] for e in es]
        sp = sum(1 for e in es if e["t_kinds"])
        gp = sum(1 for e in es if e["ret_at_open"] and e["b_kinds"])
        out(f"  {lbl:<16} {len(es):>6} {pct(xs,50):>8.0f} {pct(xs,90):>6.0f} "
            f"{sp:>9} ({sp/len(es):>5.1%}) {gp:>13} ({gp/len(es):>5.1%})")
    out()

    # --- by year
    out("BY YEAR (market minutes, trigger -> retreat)")
    out(f"  {'year':<6} {'n':>5} {'med':>8} {'mean':>9} {'p90':>9} {'max':>10}"
        f" {'spans close':>13} {'wknd':>6}")
    yrs = OrderedDict()
    for e in eps:
        yrs.setdefault(ts[e["trig_i"]].year, []).append(e)
    for y, es in sorted(yrs.items()):
        xs = [e["t_mkt"] for e in es]
        sp = sum(1 for e in es if e["t_kinds"])
        wk = sum(1 for e in es if worst(e["t_kinds"]) == "weekend")
        out(f"  {y:<6} {len(es):>5} {pct(xs,50):>8.0f} {sum(xs)/len(xs):>9.1f}"
            f" {pct(xs,90):>9.0f} {max(xs):>10.0f} {sp:>8} ({sp/len(es):>4.0%}) {wk:>6}")
    out()

    # --- longest holds
    out(f"TEN LONGEST HOLDS ({U} trigger -> {D} retreat, by market minutes)")
    out(f"  {'trigger':<17} {'peak':<17} {'retreat':<17} {'A':>6} {'B':>6}"
        f" {'total':>7} {'runup':>7} {'span':>9}")
    for e in sorted(eps, key=lambda e: -e["t_mkt"])[:10]:
        out(f"  {ts[e['trig_i']]:%Y-%m-%d %H:%M}  {ts[e['peak_i']]:%Y-%m-%d %H:%M}"
            f"  {ts[e['ret_i']]:%Y-%m-%d %H:%M} {e['a_mkt']:>6} {e['b_mkt']:>6}"
            f" {e['t_mkt']:>7} {e['peak']/e['trig']-1:>6.1%} {worst(e['t_kinds']):>9}")
    out()
    return eps


def write_ledger(bars, eps, path):
    ts = [b[0] for b in bars]
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["anchor_ts", "anchor_px", "trigger_ts", "trigger_px",
                    "peak_ts", "peak_px", "retreat_ts", "retreat_px",
                    "legA_mkt_min", "legB_mkt_min", "total_mkt_min",
                    "legA_wall_min", "legB_wall_min", "total_wall_min",
                    "runup_past_trigger", "upswing_anchor_to_peak",
                    "span", "legB_span", "retreat_on_first_bar_back",
                    "boundaries_crossed"])
        for e in eps:
            w.writerow([
                f"{ts[e['anchor_i']]:%Y-%m-%d %H:%M}", f"{e['anchor']:.4f}",
                f"{ts[e['trig_i']]:%Y-%m-%d %H:%M}", f"{e['trig']:.4f}",
                f"{ts[e['peak_i']]:%Y-%m-%d %H:%M}", f"{e['peak']:.4f}",
                f"{ts[e['ret_i']]:%Y-%m-%d %H:%M}", f"{e['ret']:.4f}",
                e["a_mkt"], e["b_mkt"], e["t_mkt"],
                f"{e['a_wall']:.0f}", f"{e['b_wall']:.0f}", f"{e['t_wall']:.0f}",
                f"{e['peak']/e['trig']-1:.6f}", f"{e['peak']/e['anchor']-1:.6f}",
                worst(e["t_kinds"]), worst(e["b_kinds"]),
                int(e["ret_at_open"]), len(e["t_kinds"])])


def run(m1, m5, up_bps, dn_bps):
    U, D, tg = bl(up_bps), bl(dn_bps), tag(up_bps, dn_bps)
    with open(os.path.join(OUT, f"retreat_report_{tg}.txt"), "w") as fh:
        eps, cens = episodes(m1, up_bps, dn_bps, "close")
        report(m1, eps, cens, f"PRIMARY — SOXL 1-min bar CLOSES  (+{U} upswing, "
               f"then {D} off the peak)", fh, up_bps, dn_bps)
        write_ledger(m1, eps, os.path.join(OUT, f"retreat_episodes_1min_{tg}.csv"))

        eps_ib, cens_ib = episodes(m1, up_bps, dn_bps, "intrabar")
        report(m1, eps_ib, cens_ib, f"SENSITIVITY A — SOXL 1-min INTRABAR "
               f"(trigger/peak on High, retreat on Low)  [{U} / {D}]",
               fh, up_bps, dn_bps)
        write_ledger(m1, eps_ib,
                     os.path.join(OUT, f"retreat_episodes_1min_intrabar_{tg}.csv"))

        eps5, cens5 = episodes(m5, up_bps, dn_bps, "close")
        for e in eps5:               # 5-min bars -> convert bar counts to minutes
            e["a_mkt"] *= 5; e["b_mkt"] *= 5; e["t_mkt"] *= 5
        report(m5, eps5, cens5, f"SENSITIVITY B — SOXL 5-min bar CLOSES "
               f"(independent file, 2020-07 -> 2026-07)  [{U} / {D}]",
               fh, up_bps, dn_bps)
    print(f"\nwrote {OUT}/retreat_report_{tg}.txt and 2 episode ledgers")


def main():
    os.makedirs(OUT, exist_ok=True)
    cfgs = [(int(sys.argv[1]), int(sys.argv[2]))] if len(sys.argv) > 2 else CONFIGS
    m1 = load("SOXL_1min.csv")
    m5 = load("SOXL_5min_6Years.csv")
    for up_bps, dn_bps in cfgs:
        run(m1, m5, up_bps, dn_bps)


if __name__ == "__main__":
    main()
