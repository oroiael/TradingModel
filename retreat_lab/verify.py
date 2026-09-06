"""Independent re-check of retreat_timing.py's episodes against the raw bars.

Re-derives every claim in the ledger straight from SOXL_1min.csv without reusing
the state machine, so a bug in the engine cannot hide behind its own output.
Checks every threshold pair in CONFIGS.

Usage:  python3 retreat_lab/verify.py [up_bps dn_bps]
"""
import csv, datetime as dt, sys, os
from decimal import Decimal

ROOT = "/home/user/TradingModel"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import BPS, CONFIGS, bl, tag   # thresholds only, not the engine

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

def check(up_bps, dn_bps):
  U, D = bl(up_bps), bl(dn_bps)
  up_n, dn_n = BPS + up_bps, BPS - dn_bps
  rows = list(csv.DictReader(open(os.path.join(
      ROOT, f"retreat_lab/out/retreat_episodes_1min_{tag(up_bps, dn_bps)}.csv"))))
  print(f"\n{U} upswing / {D} retreat — episodes in ledger: {len(rows)}")

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
      # 3. the trigger really is a >= up_bps upswing off the anchor
      chk(close[g] * BPS >= close[a] * up_n, n,
          f"trigger only {close[g]/close[a]-1:.4%} above anchor")
      # 4. and it is the FIRST such bar -- no earlier bar cleared up_bps off the
      #    running trough of the seeking window
      lo = close[prev_ret] if prev_ret >= 0 else close[0]
      start = prev_ret if prev_ret >= 0 else 0
      for i in range(start, g):
          lo = min(lo, close[i])
          chk(close[i] * BPS < lo * up_n, n, f"earlier {U} trigger at {ts[i]}")
      chk(lo == close[a], n, "anchor is not the running trough")
      # 5. the peak is the true running max over [trigger, retreat)
      chk(max(close[g:r]) == close[p], n, "peak is not the max")
      chk(close[p] == max(close[g:p + 1]), n, "peak not first-max")
      # 6. the retreat bar really is >= dn_bps below the peak
      chk(close[r] * BPS <= close[p] * dn_n, n,
          f"retreat only {1-close[r]/close[p]:.4%} below peak")
      # 7. and it is the FIRST bar to break dn_bps below the running peak
      run = close[g]
      for i in range(g, r):
          run = max(run, close[i])
          chk(close[i] * BPS > run * dn_n, n, f"earlier {D} breach at {ts[i]}")
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

  print(f"  checks failed: {len(fail)}")
  for ep, m in fail[:20]:
      print("    episode", ep, m)

  # 11. no upswing left unclaimed after the final episode
  lo = close[prev_ret]; leftover = None
  for i in range(prev_ret, len(close)):
      lo = min(lo, close[i])
      if close[i] * BPS >= lo * up_n:
          leftover = ts[i]; break
  print("  un-retreated episode open at end of file:",
        leftover if leftover else "none")
  return len(fail)


cfgs = [(int(sys.argv[1]), int(sys.argv[2]))] if len(sys.argv) > 2 else CONFIGS
bad = sum(check(u, d) for u, d in cfgs)
print(f"\nTOTAL FAILURES: {bad}")
sys.exit(1 if bad else 0)
