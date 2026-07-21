#!/usr/bin/env python3
"""Black-Scholes (r=q=0) used ONLY to estimate a leg's value intraday, where the
data has no option quotes. verify.py showed BS priced with the data's own IV lands
inside the quoted bid/ask ~94% of the time, so it is a validated intraday proxy."""
import math


def bs_call(S, K, T, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    nd2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
    return S * nd1 - K * nd2


def bs_put(S, K, T, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    nnd1 = 0.5 * (1 + math.erf(-d1 / math.sqrt(2)))
    nnd2 = 0.5 * (1 + math.erf(-d2 / math.sqrt(2)))
    return K * nnd2 - S * nnd1
