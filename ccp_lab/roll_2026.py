#!/usr/bin/env python3
"""SOXL covered call + 90-day protective put, ROLLING the call — 2026 only.

Same rule as run_2026.py except the weekly call is never allowed to assign: on
expiry day an in-the-money call is bought back and the far leg of the same combo
order sells the following week's call. Where the net debit cannot be funded from
cash the shares are still assigned, and that is reported.

    python3 ccp_lab/roll_2026.py

Writes ccp_lab/out/summary_2026_roll.md and the ledger/events/equity CSVs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ccp_lab.compat import safe_stdout, ensure_cache
from ccp_lab.engine import Data, run_year
from ccp_lab.report import write

YEAR = 2026
ROLL = "friday"        # classic combo roll: close the near leg, open the far leg
RESERVE = 0.0          # the rule says reinvest, so no cash is held back

if __name__ == "__main__":
    safe_stdout()
    if not ensure_cache():
        raise SystemExit(1)
    data = Data()
    res = run_year(YEAR, data, roll=ROLL, reserve_pct=RESERVE)
    s = write(res, data, tag="_roll", label="rolling, never assigned")
    print(s["text"])
