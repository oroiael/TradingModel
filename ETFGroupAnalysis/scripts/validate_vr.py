"""Validation harness for the variance-ratio and DFA implementations.

Runs them on series with KNOWN properties.  If these fail, no VR/Hurst number
in the analysis can be trusted.  This exists because the first implementation
of the z-statistic was wrong (missing sqrt(n) scaling) and produced |z| < 0.01
on 115,000 observations, which is not a plausible test statistic.
"""

from __future__ import annotations

import numpy as np

from common import dfa_hurst, variance_ratio

rng = np.random.default_rng(42)
N = 100_000

print("=" * 78)
print("VALIDATION -- variance ratio and DFA on series with known properties")
print("=" * 78)

# 1. i.i.d. Gaussian white noise: VR(q) == 1, z ~ N(0,1), H == 0.5
wn = rng.standard_normal(N)
print("\n[1] i.i.d. Gaussian white noise   (expect VR=1.00, |z|<2, H=0.50)")
for q in (2, 6, 12):
    vr, z, p = variance_ratio(wn, q)
    print(f"    q={q:3d}  VR={vr:.4f}  z={z:+7.3f}  p={p:.3f}")
print(f"    DFA H = {dfa_hurst(wn):.4f}")

# 2. Size of the test: fraction of white-noise samples rejected at 5% should be ~5%
rej = 0
trials = 200
for _ in range(trials):
    _, z, _ = variance_ratio(rng.standard_normal(5000), 6)
    rej += abs(z) > 1.96
print(f"\n[2] Test size: {rej}/{trials} = {rej/trials:.1%} rejected at 5% "
      f"(expect ~5%)")

# 3. Trending / persistent series (AR(1) on the cumulative sum -> VR > 1, H > 0.5)
phi = 0.15
ar = np.zeros(N)
e = rng.standard_normal(N)
for t in range(1, N):
    ar[t] = phi * ar[t - 1] + e[t]
print(f"\n[3] AR(1) returns, phi=+{phi}   (expect VR>1, H>0.5)")
for q in (2, 6, 12):
    vr, z, p = variance_ratio(ar, q)
    print(f"    q={q:3d}  VR={vr:.4f}  z={z:+8.2f}  p={p:.3e}")
print(f"    DFA H = {dfa_hurst(ar):.4f}")

# 4. Mean-reverting series (negative AR(1) -> VR < 1, H < 0.5)
phi = -0.15
mr = np.zeros(N)
e = rng.standard_normal(N)
for t in range(1, N):
    mr[t] = phi * mr[t - 1] + e[t]
print(f"\n[4] AR(1) returns, phi={phi}   (expect VR<1, H<0.5)")
for q in (2, 6, 12):
    vr, z, p = variance_ratio(mr, q)
    print(f"    q={q:3d}  VR={vr:.4f}  z={z:+8.2f}  p={p:.3e}")
print(f"    DFA H = {dfa_hurst(mr):.4f}")

# 5. Heteroskedastic but uncorrelated (GARCH-like): VR should stay ~1 and the
#    ROBUST z should NOT over-reject -- this is the whole point of using the
#    heteroskedasticity-consistent statistic on financial data.
vol = np.exp(np.cumsum(rng.standard_normal(N) * 0.01))
vol = vol / vol.mean()
het = rng.standard_normal(N) * vol
print("\n[5] Uncorrelated but heteroskedastic   (expect VR~1, robust |z| small)")
for q in (2, 6, 12):
    vr, z, p = variance_ratio(het, q)
    print(f"    q={q:3d}  VR={vr:.4f}  z={z:+7.3f}  p={p:.3f}")

# 6. Known fractional Brownian motion via cumulative sum of white noise
print("\n[6] DFA on a random walk's increments vs the walk itself")
print(f"    increments (white noise) H = {dfa_hurst(wn):.4f}   (expect 0.50)")
print(f"    the walk itself          H = {dfa_hurst(np.cumsum(wn)):.4f}   (expect ~1.50)")
print("\nIf [1] and [2] look right, the z-statistic is correctly scaled.")
