"""
Phase 1 — reference constants, transcribed verbatim from
IMPLEMENTATION_SPEC.md §12, plus the config validation demanded by §6.8.

This module is deliberately dumb: it holds numbers and rejects bad ones.
Nothing here may be "improved" — §12 is the single source of truth and any
deviation is a strategy change, not a configuration change.
"""

from __future__ import annotations

# ----------------------------------------------------------- §12 constants
SLEEVES = ["SOXL", "SOXS"]
W_PER_SLEEVE = 0.50           # capital weight, valid [0.375, 0.75]
F_SIZE = 1.00                 # risk dial, valid (0, 1.00]; >1.0 rejected
GATE_ATR5_MIN = 6.0           # percent
ATR_LOOKBACK = 5              # sessions
OR_WINDOW = ("09:30", "10:00")
OR_PCTL = 0.80                # trailing threshold percentile
OR_PCTL_WINDOW = 504          # sessions
OR_PCTL_MINOBS = 120
POS10_TOP_THIRD = 2.0 / 3.0
START_TIME = "11:00"
DIP_PCT = 0.01                # entry = anchor * (1 - DIP_PCT)
TARGET_PCT = 0.01             # exit  = E * (1 + TARGET_PCT)
STOP_PCT = 0.04               # exit  = E * (1 - STOP_PCT), ABSOLUTE
MAX_FILLS = 5
MAX_STOPS = 2
FLATTEN_TIME = "15:55"
HARD_FLAT_BY = "16:00"
DAY_LOSS_KILL = -0.085        # fraction of sleeve capital
TIMEZONE = "America/New_York"

# ------------------------------------------------------------- other bounds
W_VALID_RANGE = (0.375, 0.75)
F_VALID_RANGE = (0.0, 1.00)   # exclusive lower, inclusive upper
SESSION_OPEN = "09:30"
SESSION_CLOSE = "16:00"
BAR_MINUTES = 5
TICK_SIZE = 0.01              # US equities above $1.00


class ConfigError(ValueError):
    """Raised by validate_config; §6.8 requires a hard startup failure."""


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def bar_index(hhmm: str) -> int:
    """§2.1: bar index 0 is the 09:30 bar; bar 18 is the 11:00 bar."""
    delta = _minutes(hhmm) - _minutes(SESSION_OPEN)
    if delta < 0 or delta % BAR_MINUTES:
        raise ValueError(f"{hhmm} is not a {BAR_MINUTES}-minute bar boundary")
    return delta // BAR_MINUTES


def bar_time(i: int) -> str:
    m = _minutes(SESSION_OPEN) + BAR_MINUTES * i
    return f"{m // 60:02d}:{m % 60:02d}"


def round_to_tick(price: float, tick: float = TICK_SIZE) -> float:
    """§2.5/§2.6 round_to_tick. Nearest tick; ties away from zero."""
    import math
    if tick <= 0:
        return float(price)
    n = price / tick
    return math.floor(n + 0.5) * tick if n >= 0 else math.ceil(n - 0.5) * tick


def validate_config(cfg) -> None:
    """§6.8 — reject anything that is a strategy change in disguise.

    `cfg` is an EngineConfig (duck-typed so this module stays import-light).
    """
    if not (F_VALID_RANGE[0] < cfg.f <= F_VALID_RANGE[1]):
        raise ConfigError(
            f"f={cfg.f} outside valid range (0, {F_VALID_RANGE[1]}]; "
            "leverage was tested and rejected (§2.9)")
    if not (W_VALID_RANGE[0] <= cfg.w <= W_VALID_RANGE[1]):
        raise ConfigError(
            f"w={cfg.w} outside validated plateau {W_VALID_RANGE} (§2.9)")
    for name, value, expected in [
        ("gate_atr5_min", cfg.gate_atr5_min, GATE_ATR5_MIN),
        ("dip_pct", cfg.dip_pct, DIP_PCT),
        ("target_pct", cfg.target_pct, TARGET_PCT),
        ("stop_pct", cfg.stop_pct, STOP_PCT),
        ("max_fills", cfg.max_fills, MAX_FILLS),
        ("max_stops", cfg.max_stops, MAX_STOPS),
        ("start_time", cfg.start_time, START_TIME),
    ]:
        if value != expected:
            raise ConfigError(
                f"{name}={value!r} differs from §12 ({expected!r}); this is a "
                "strategy change and requires re-validation, not a config edit")
    if getattr(cfg, "allow_short", False):
        raise ConfigError("shorting is an explicit non-goal (§11)")
    if getattr(cfg, "allow_overnight", False):
        raise ConfigError("overnight holding is forbidden (§1, §2.8)")
