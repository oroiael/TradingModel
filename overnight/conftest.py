"""Put `overnight/` on the path so tests import the modules under test directly.

Mirrors `band_lab/live/conftest.py`. The live modules import each other by bare
name (`import core`), which keeps them runnable as scripts and keeps the
research/live boundary obvious in the imports.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: replays the full history against the research ledger")
