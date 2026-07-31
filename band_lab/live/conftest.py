import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BAND_LAB = os.path.dirname(HERE)
ROOT = os.path.dirname(BAND_LAB)
for p in (HERE, os.path.join(BAND_LAB, "phase1")):
    if p not in sys.path:
        sys.path.insert(0, p)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: replays the full 6-year history (~60s)")
