"""Does expressing the trade in SOXX make the put overlay affordable?

drawdown.py established that the SOXL put overlay fails on SPREAD, not premium,
and argued SOXX might clear because it is a $500, mega-liquid, ~38%-IV ETF where
spread-as-a-fraction-of-premium should be far tighter. This tests that.

Two things have to be got right or the comparison is meaningless:

  1. MONEYNESS must be matched in UNDERLYING-MOVE terms, not strike terms.
     SOXL moves 3x SOXX, so a k% OTM SOXL put corresponds to a (k/3)% OTM SOXX
     put. Comparing "5% OTM" on both compares a 5% SOXL move against a 15% one.
  2. NOTIONAL must be matched. 3x SOXX = 1x SOXL, so hedging the same exposure
     takes 3x the SOXX notional. All figures below are in bp of SOXL-EQUIVALENT
     notional. Note this multiplier does NOT by itself penalise SOXX: SOXX's
     premium per unit notional is ~1/3 of SOXL's because its vol is ~1/3, so
     3x notional costs about the same premium. Only the spread PERCENTAGE
     differs, and that is what the test isolates.

Quotes in out/option_quotes_20260911.csv were pulled from IBKR on 2026-09-11
after the close, so they are FROZEN and wider than intraday for BOTH names.
The result does not hinge on that: see the margin against breakeven.

Usage:  python3 retreat_lab/soxx_hedge.py
"""
import csv, os, sys
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retreat_timing import ROOT

QUOTES = os.path.join(ROOT, "retreat_lab/out/option_quotes_20260911.csv")
MULT = {"SOXL": 1.0, "SOXX": 3.0}      # notional needed for equal exposure


def main():
    q = list(csv.DictReader(open(QUOTES)))
    for r in q:
        r["spot"] = float(r["spot"]); r["mid"] = float(r["mid"])
        r["bid"] = float(r["bid"]); r["ask"] = float(r["ask"])
        r["eq"] = float(r["moneyness_soxl_equiv"])
        m = MULT[r["symbol"]]
        r["prem_bp"] = r["mid"] / r["spot"] * 1e4 * m
        r["spr_bp"] = (r["ask"] - r["bid"]) / r["spot"] * 1e4 * m
        r["spr_pct"] = (r["ask"] - r["bid"]) / r["mid"]

    print(f"{'='*100}\nMEASURED 7-DTE PUT QUOTES — bp of SOXL-EQUIVALENT notional\n{'='*100}")
    print(f"  {'sym':<6}{'strike':>8}{'SOXL-equiv moneyness':>22}{'premium':>10}"
          f"{'spread':>9}{'spread % of prem':>19}{'OI':>8}")
    for r in q:
        print(f"  {r['symbol']:<6}{r['strike']:>8}{r['eq']*100:>21.2f}%"
              f"{r['prem_bp']:>9.0f}bp{r['spr_bp']:>7.0f}bp{r['spr_pct']*100:>18.1f}%"
              f"{r['open_interest']:>8}")

    print(f"\n{'='*100}\nHEAD TO HEAD at matched SOXL-equivalent moneyness\n{'='*100}")
    print(f"  {'SOXL-equiv strike':<20}{'SOXL prem':>11}{'SOXX prem':>11}"
          f"{'SOXL spr%':>12}{'SOXX spr%':>12}{'SOXX / SOXL':>13}")
    for lo, hi, lbl in ((-0.035, -0.025, "~ -3%"), (-0.050, -0.040, "~ -4.5%"),
                        (-0.080, -0.065, "~ -7%"), (-0.005, 0.005, "ATM")):
        a = [r for r in q if r["symbol"] == "SOXL" and lo <= r["eq"] <= hi]
        b = [r for r in q if r["symbol"] == "SOXX" and lo <= r["eq"] <= hi]
        if not a or not b:
            continue
        a, b = a[0], b[0]
        print(f"  {lbl:<20}{a['prem_bp']:>10.0f}bp{b['prem_bp']:>10.0f}bp"
              f"{a['spr_pct']*100:>11.1f}%{b['spr_pct']*100:>11.1f}%"
              f"{b['spr_pct']/a['spr_pct']:>12.1f}x")

    ml = median([r["spr_pct"] for r in q if r["symbol"] == "SOXL"])
    mx = median([r["spr_pct"] for r in q if r["symbol"] == "SOXX"])
    print(f"\n  median spread as % of premium:  SOXL {ml*100:.1f}%   SOXX {mx*100:.1f}%"
          f"   ({mx/ml:.1f}x worse)")
    print(f"\n  The historical overlay (drawdown.py, real 15:55 -> 09:30 prints) stops")
    print(f"  improving Sharpe at about a 1% round-trip spread. Both names are an")
    print(f"  order of magnitude above that:")
    print(f"    SOXL {ml*100:>5.1f}%  = {ml/0.01:>4.0f}x breakeven")
    print(f"    SOXX {mx*100:>5.1f}%  = {mx/0.01:>4.0f}x breakeven")
    print(f"  Halving both to allow for the frozen-quote bias leaves {ml*50:.0f}x and "
          f"{mx*50:.0f}x. The conclusion does not depend on the quote timing.")


if __name__ == "__main__":
    main()
