import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BAND_LAB = os.path.dirname(HERE)
ROOT = os.path.dirname(BAND_LAB)
for p in (HERE, BAND_LAB, os.path.join(ROOT, "cycle_lab")):
    if p not in sys.path:
        sys.path.insert(0, p)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: runs the full 6-year parity backtest (~40s)")
