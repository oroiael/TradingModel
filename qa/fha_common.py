"""Shared helpers for the final_hedged_audit.py QA tests.

Builds minimal synthetic CSVs in the exact shapes FinalAuditSimulator expects:

  options CSV : date, expiration, type, strike, close, delta, iv, underlying_price
  IBKR CSV    : date ("YYYYMMDD HH:MM:SS"), low

Standard entry chain (used by every test), entry date D0 = 2024-01-02,
spot = 100, expiration E chosen so DTE is inside the (30, 60) window:

  strike 90  close 3.00  delta -0.20   -> income SHORT leg AND hedge SELL leg
  strike 85  close 1.50  delta -0.05   -> income LONG leg ($5 wide, credit 1.50)
  strike 80  close 1.10  delta -0.03   -> hedge BUY leg x3 (net hedge cost 0.30)

With those quotes the engine computes:
  net_credit_realized = 1.50 - 0.30 - 6*0.05 = 0.90
  Base Risk           = (5.00 - 0.90) * 100  = $410 / contract
  contracts           = floor(150000 * 0.15 / 410) = 54
"""
import os
import sys
import tempfile

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

D0 = "2024-01-02"


def put_row(date, exp, strike, close, delta, iv=0.40, spot=100.0):
    return {
        "date": str(pd.Timestamp(date).date()),
        "expiration": str(pd.Timestamp(exp).date()),
        "type": "P",
        "strike": float(strike),
        "close": float(close),
        "delta": float(delta),
        "iv": float(iv),
        "underlying_price": float(spot),
    }


def entry_chain(exp, d0=D0, sign=-1.0):
    """The standard 3-strike entry chain. sign=-1 stores put deltas as
    negative (OPRA/ORATS style), sign=+1 as positive magnitudes."""
    return [
        put_row(d0, exp, 90, 3.00, sign * 0.20),
        put_row(d0, exp, 85, 1.50, sign * 0.05),
        put_row(d0, exp, 80, 1.10, sign * 0.03),
    ]


def run_engine(options_rows, day_lows, capital=150000):
    """Write the CSVs into a temp workdir, run FinalAuditSimulator there
    (so its output CSV stays out of the repo), return the closed-trades
    DataFrame it produced."""
    workdir = tempfile.mkdtemp(prefix="fha_qa_")
    opt_path = os.path.join(workdir, "options.csv")
    ibkr_path = os.path.join(workdir, "ibkr.csv")

    pd.DataFrame(options_rows).to_csv(opt_path, index=False)
    ib_rows = [
        {"date": f"{pd.Timestamp(d):%Y%m%d} 09:30:00", "low": float(lo)}
        for d, lo in day_lows.items()
    ]
    pd.DataFrame(ib_rows).to_csv(ibkr_path, index=False)

    from final_hedged_audit import FinalAuditSimulator

    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        FinalAuditSimulator(opt_path, ibkr_path, capital).run_audit()
        out = os.path.join(workdir, "SOXL_Final_Hedged_Audit.csv")
        return pd.read_csv(out) if os.path.exists(out) else pd.DataFrame()
    finally:
        os.chdir(cwd)
