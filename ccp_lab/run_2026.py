#!/usr/bin/env python3
"""SOXL covered call + 90-day protective put — 2026 only.

    python3 ccp_lab/run_2026.py

Writes ccp_lab/out/summary_2026.md and the ledger/events/equity CSVs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ccp_lab.engine import Data, run_year
from ccp_lab.report import write

YEAR = 2026

if __name__ == "__main__":
    data = Data()
    res = run_year(YEAR, data)
    s = write(res, data)
    print(s["text"])
