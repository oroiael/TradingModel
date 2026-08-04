"""Option marks for the backtest, with a documented fallback ladder.

Priority for any (contract, date, minute) mark:
  1. real 5-min TRADE print at that exact bar          -> src 'print'
  2. nearest real print within +/-30 min the same day  -> src 'print_near'
  3. Black-Scholes repriced from that day's EOD implied vol to the 10:00 spot
                                                       -> src 'model'
Step 3 exists because far-dated puts trade thinly intraday; it is validated
against step 1/2 wherever both exist (see validate_pricing.py).
"""
import numpy as np
import pandas as pd
from math import log, sqrt, exp

SQ2 = sqrt(2.0)


def _ncdf(x):
    from scipy.special import ndtr
    return ndtr(x)


def bs_price(S, K, T, sigma, r=0.0, q=0.0, right="C"):
    S, K, T, sigma = map(np.asarray, (S, K, T, sigma))
    T = np.maximum(T, 1e-6)
    sigma = np.maximum(sigma, 1e-4)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    df, dq = np.exp(-r * T), np.exp(-q * T)
    call = S * dq * _ncdf(d1) - K * df * _ncdf(d2)
    put = K * df * _ncdf(-d2) - S * dq * _ncdf(-d1)
    return np.where(np.asarray(right) == "C", call, put)


class Pricer:
    """Marks options at a given minute-of-day using prints first, model second."""

    def __init__(self, eod, trades, carry=0.0, near_window=30):
        self.carry = carry            # effective r - q, calibrated from the chain
        self.near = near_window
        self.eod = eod.set_index(["date", "exp", "right", "strike"]).sort_index()
        t = trades.copy()
        self.tr = t.set_index(["date", "exp", "right", "strike"]).sort_index()
        self.stats = {"print": 0, "print_near": 0, "model": 0, "miss": 0}

    def _eod_row(self, date, exp, right, strike):
        try:
            return self.eod.loc[(date, exp, right, np.float32(strike))]
        except KeyError:
            return None

    def mark(self, date, exp, right, strike, spot, minute=600):
        """Return (price, source). Price is per share (x100 for a contract)."""
        try:
            g = self.tr.loc[(date, exp, right, np.float32(strike))]
            if isinstance(g, pd.Series):
                mins, pxs = np.array([g["minute"]]), np.array([g["px"]])
            else:
                mins, pxs = g["minute"].values, g["px"].values
            hit = np.where(mins == minute)[0]
            if len(hit):
                self.stats["print"] += 1
                return float(pxs[hit[0]]), "print"
            dd = np.abs(mins - minute)
            j = int(np.argmin(dd))
            if dd[j] <= self.near:
                self.stats["print_near"] += 1
                return float(pxs[j]), "print_near"
        except KeyError:
            pass

        row = self._eod_row(date, exp, right, strike)
        if row is None:
            self.stats["miss"] += 1
            return None, "miss"
        iv = float(row["iv"]) if np.isfinite(row["iv"]) else np.nan
        if not np.isfinite(iv) or iv <= 0:
            bid, ask = float(row["bid"]), float(row["ask"])
            if np.isfinite(bid) and np.isfinite(ask) and ask > 0:
                self.stats["model"] += 1
                return max((bid + ask) / 2, 0.0), "model_mid"
            self.stats["miss"] += 1
            return None, "miss"
        # time to expiry from `minute` on `date` to 16:00 on exp date
        days = (exp - date).days
        T = (days - (minute - 960) / 390.0 * 0 + (960 - minute) / 390.0) / 365.0
        p = float(bs_price(spot, strike, max(T, 1e-6), iv, self.carry, 0.0, right))
        self.stats["model"] += 1
        return max(p, 0.0), "model"

    def mark_eod(self, date, exp, right, strike, spot):
        """End-of-day mark for equity accounting: chain mid, else model at close."""
        row = self._eod_row(date, exp, right, strike)
        if row is not None:
            bid, ask = float(row["bid"]), float(row["ask"])
            if np.isfinite(bid) and np.isfinite(ask) and ask >= bid > 0:
                return (bid + ask) / 2.0
            iv = float(row["iv"])
            if np.isfinite(iv) and iv > 0:
                T = max((exp - date).days, 0) / 365.0
                return float(max(bs_price(spot, strike, max(T, 1e-6), iv,
                                          self.carry, 0.0, right), 0.0))
        return max(0.0, (spot - strike) if right == "C" else (strike - spot))
