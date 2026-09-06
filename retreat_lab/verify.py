"""Independent re-check of retreat_timing.py's episodes against the raw bars.

Re-derives every claim in the ledger straight from SOXL_1min.csv without reusing
the state machine, so a bug in the engine cannot hide behind its own output.
"""
import csv, datetime as dt, sys, os
from decimal import Decimal

ROOT = "/home/user/TradingModel"
UP_N, UP_D = 102, 100      # exact integer thresholds, prices in cents
DN_N, DN_D = 995, 1000

bars, idx = [], {}
with open(os.path.join(ROOT, "SOXL_1min.csv")) as f:
    r = csv.reader(f); next(r)
    for a in r:
        t = dt.datetime.strptime(a[0].replace(" America/New_York", ""),
                                 "%Y%m%d %H:%M:%S")
        idx[t] = len(bars)
        bars.append((t, int((Decimal(a[4]) * 100).to_integral_exact())))
close = [b[1] for b in bars]
ts = [b[0] for b in bars]

rows = list(csv.DictReader(open(os.path.join(ROOT,
            "retreat_lab/out/retreat_episodes_1min.csv"))))
print(f"episodes in ledger: {len(rows)}")

fail = []
def chk(cond, ep, msg):
    if not cond:
        fail.append((ep, msg))

prev_ret = -1
for n, row in enumerate(rows):
    T = lambda k: idx[dt.datetime.strptime(row[k], "%Y-%m-%d %H:%M")]
    a, g, p, r = T("anchor_ts"), T("trigger_ts"), T("peak_ts"), T("retreat_ts")

    # 1. ordering
    chk(a <= g <= p < r, n, f"order broken a={a} g={g} p={p} r={r}")
    # 2. prices in the ledger match the file
    for k, i in (("anchor_px", a), ("trigger_px", g), ("peak_px", p), ("retreat_px", r)):
        chk(int((Decimal(row[k]) * 100).to_integral_exact()) == close[i], n,
            f"{k} != file close")
    # 3. the trigger really is a >=2% upswing off the anchor
    chk(close[g] * UP_D >= close[a] * UP_N, n,
        f"trigger only {close[g]/close[a]-1:.4%} above anchor")
    # 4. and it is the FIRST such bar -- no earlier bar cleared 2% off the
    #    running trough of the seeking window
    lo = close[prev_ret] if prev_ret >= 0 else close[0]
    start = prev_ret if prev_ret >= 0 else 0
    for i in range(start, g):
        lo = min(lo, close[i])
        chk(close[i] * UP_D < lo * UP_N, n, f"earlier 2% trigger at {ts[i]}")
    chk(lo == close[a], n, "anchor is not the running trough")
    # 5. the peak is the true running max over [trigger, retreat)
    chk(max(close[g:r]) == close[p], n, "peak is not the max")
    chk(close[p] == max(close[g:p + 1]), n, "peak not first-max")
    # 6. the retreat bar really is >=0.5% below the peak
    chk(close[r] * DN_D <= close[p] * DN_N, n,
        f"retreat only {1-close[r]/close[p]:.4%} below peak")
    # 7. and it is the FIRST bar to break 0.5% below the running peak
    run = close[g]
    for i in range(g, r):
        run = max(run, close[i])
        chk(close[i] * DN_D > run * DN_N, n, f"earlier 0.5% breach at {ts[i]}")
    # 8. reported durations equal the true grid distances / wall clock
    chk(int(row["legA_mkt_min"]) == p - g, n, "legA market minutes")
    chk(int(row["legB_mkt_min"]) == r - p, n, "legB market minutes")
    chk(int(row["total_mkt_min"]) == r - g, n, "total market minutes")
    chk(int(row["legA_mkt_min"]) + int(row["legB_mkt_min"])
        == int(row["total_mkt_min"]), n, "legs do not sum to total")
    chk(int(row["total_wall_min"]) == round((ts[r] - ts[g]).total_seconds() / 60),
        n, "total wall minutes")
    # 9. session-span label agrees with the actual dates crossed
    spans = ts[g].date() != ts[r].date()
    chk((row["span"] != "intraday") == spans, n, "span label")
    chk((int(row["retreat_on_first_bar_back"]) == 1)
        == (ts[r].date() != ts[r - 1].date()), n, "first-bar-back flag")
    # 10. episodes must not overlap
    chk(g > prev_ret or prev_ret < 0, n, "overlaps previous episode")
    prev_ret = r

print(f"checks failed: {len(fail)}")
for ep, m in fail[:20]:
    print("  episode", ep, m)

# 11. no 2% upswing left unclaimed after the final episode
lo = close[prev_ret]; leftover = None
for i in range(prev_ret, len(close)):
    lo = min(lo, close[i])
    if close[i] * UP_D >= lo * UP_N:
        leftover = ts[i]; break
print("un-retreated episode open at end of file:",
      leftover if leftover else "none")
sys.exit(1 if fail else 0)
