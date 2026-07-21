#!/usr/bin/env python3
"""
run_all.py  --  runs the neutral data-analysis suite and prints a SYNTHESIS that
separates MEASURED FACTS from what they SUGGEST (to evaluate later). Data first.

    python3 run_all.py            # full run (underlying + intraday + options + synthesis)
"""
import underlying_signature
import intraday_microstructure
import options_surface


def synthesis():
    print("\n" + "#" * 84)
    print("# SYNTHESIS  --  what the DATA says (measured), and what it SUGGESTS (to test)")
    print("#" * 84)
    print("""
MEASURED FACTS (SOXL, 2022-2026):

  A. Volatility DRAG ~= 64%/yr. Arithmetic daily edge annualizes to ~+87%/yr but
     SOXL only NETS ~+23%/yr. Choppiness is the dominant tax on the instrument.
  B. DIRECTION is ~a random walk daily->monthly (variance ratios ~0.9, z~0,
     Hurst 0.49). No linear trend/reversion edge at those horizons. BUT:
       - OVERNIGHT drift is strong: close->open Sharpe ~1.60 (+346% cumulative)
         vs the intraday session Sharpe ~0.23 (+60%). The return lives overnight.
       - EXTREMES mean-revert: the day after a <-10% day averages +1.4% (60% up).
  C. VOLATILITY is the exploitable axis: strong clustering (|r| autocorrelation
     persistent to 20 days), fat LEFT tails (skew -0.37, excess kurtosis +2.8),
     and IV jumps when price falls (corr IV-change vs return = -0.57).
  D. OPTIONS ARE CHEAP: 30d implied < subsequent realized by ~6-12% in every year
     EXCEPT 2023 (+2%). Selling premium fights this; buying convexity is paid.
  E. SKEW: puts RICH (25d put +9 vol pts over ATM), calls CHEAP (25d call -4 pts).
     The RIGHT tail is underpriced; the LEFT tail is overpriced.
  F. TERM STRUCTURE mildly INVERTED (short-tenor IV > long on 65% of days).
  G. INTRADAY: U-shaped vol (open ~2.9x midday), 5-min returns ~random, no
     end-of-day rebalancing momentum (mild fade into 15:55).

WHAT THIS SUGGESTS (candidate structures to EVALUATE, ranked by fit -- not yet
proven; this is the hand-off from 'what the data is' to 'what trade matches it'):

  1. LONG RIGHT-TAIL CONVEXITY (buy the cheap calls). Cheap calls (E) + overnight
     up-drift (B) + fat tails (C) + cheap options (D) all point the same way. Long
     calls / call debit spreads / call ratio backspreads. [Matches earlier wins.]
  2. OVERNIGHT-DRIFT CAPTURE. Hold long delta close->open, flat/hedged intraday --
     Sharpe 1.60 vs 0.23. Untested here and the single most striking neutral fact.
  3. LONG-VOL, VOL-TIMED. Own convexity (strangles/straddles) because vol clusters
     (C) and options are cheap (D); stand down when VRP turns positive (2023, D) or
     realized vol is low. [Matches the strangle + vol-regime rotation.]
  4. TACTICAL MEAN-REVERSION on extremes (buy after big down days, B).
  5. AVOID selling premium, especially PUTS (negative VRP + fat left tail + rich-
     but-justified put skew). [Matches every credit-spread failure.]
  6. Harvest convexity with a TRAILING exit, not a fixed profit target (keeps the
     fat-tail winners the drag/skew create). [Matches the walk-forward result.]

The unifying story: SOXL is a volatility-DRAG machine with cheap, right-skewed
options and an overnight up-drift. You get paid to be LONG convexity (especially
calls) and to capture the overnight move; you get punished for being SHORT vol or
for holding through the intraday/choppy grind. Direction itself is not the edge --
volatility, convexity, and the overnight session are.
""")


if __name__ == "__main__":
    underlying_signature.main()
    intraday_microstructure.main()
    options_surface.main()
    synthesis()
