"""
Phase 1 — clean-room backtest engine.

Written from IMPLEMENTATION_SPEC.md §2 (and §12) alone. It does not import,
call, or copy any code from the research lab (`transfer_test`,
`spxl_scaling_test`, `v5_corrected_rerun`, `etf_scaling_test`). Parity
against those is measured in `parity.py`, not assumed here.

Where §2 is genuinely under-determined for a *bar-level* backtest, the
ambiguity is exposed as a named switch on `EngineConfig` rather than
resolved silently. Every switch is documented in PHASE1_PARITY.md §3 with
the spec text it comes from and its measured P&L impact. Two presets are
provided:

    SPEC_LITERAL    — the reading closest to the words of §2
    RESEARCH_COMPAT — the reading the research engine actually implements

Sign convention: a "return" is a fraction of *sleeve capital*, and a day's
P&L is the plain sum of its trade returns (each entry is sized from the
same pre-open sleeve capital per §2.4, so returns are additive, not
compounded, within a session).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from spec_constants import (
    DIP_PCT,
    FLATTEN_TIME,
    GATE_ATR5_MIN,
    MAX_FILLS,
    MAX_STOPS,
    OR_PCTL,
    OR_PCTL_MINOBS,
    OR_PCTL_WINDOW,
    OR_WINDOW,
    POS10_TOP_THIRD,
    SESSION_OPEN,
    START_TIME,
    STOP_PCT,
    TARGET_PCT,
    TICK_SIZE,
    W_PER_SLEEVE,
    F_SIZE,
    ATR_LOOKBACK,
    bar_index,
    round_to_tick,
    validate_config,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# §4: SOXL's 15:1 split (2021-03-02) is not applied in the raw repo file.
# §4 requires a consistently *adjusted* series for ATR5/OR30; this is data
# conditioning, not strategy logic. SOXS's file is already back-adjusted.
SPLIT_ADJUSTMENTS = {"SOXL": [(pd.Timestamp("2021-03-02"), 15.0)]}


# --------------------------------------------------------------- config
@dataclass(frozen=True)
class EngineConfig:
    # --- §12 constants (validate_config rejects any change) ---
    w: float = W_PER_SLEEVE
    f: float = F_SIZE
    gate_atr5_min: float = GATE_ATR5_MIN
    dip_pct: float = DIP_PCT
    target_pct: float = TARGET_PCT
    stop_pct: float = STOP_PCT
    max_fills: int = MAX_FILLS
    max_stops: int = MAX_STOPS
    start_time: str = START_TIME
    allow_short: bool = False
    allow_overnight: bool = False

    # --- interpretation switches (PHASE1_PARITY.md §3) ---
    # S1  §2.1 recomputes thr80 every session. RESOLVED 2026-07: the spec
    #     previously said "monthly"; it was amended to match the cadence the
    #     validated series was actually produced with. "monthly" is retained
    #     only so the alternative remains measurable.
    thr80_refresh: str = "daily"            # "daily" | "monthly"
    # S2  §2.2 "do not trade if ... the session is a scheduled half-day"
    half_day_policy: str = "off"            # "off" | "trade"
    # S3  §2.8 "At 15:55 ... close it"  vs. holding to the session close
    eod_mode: str = "flatten_1555"          # "flatten_1555" | "session_close"
    # S4  §2.6 OCA is live from the fill, so the target *could* fill on the
    #     entry bar; §2.6 now states the anti-lookahead rule explicitly.
    target_on_entry_bar: bool = False
    # S5  the LIVE engine always rounds to the tick grid (§2.5/§2.6) — it has
    #     no choice. The BACKTEST does not model it. RESOLVED 2026-07: the
    #     grid is worth +4.3 bp/ON-day on SOXL and is held as unbanked
    #     conservatism, to be settled against real fills in Phase 2.
    tick_rounding: bool = False
    tick_size: float = TICK_SIZE
    # S6  §2.1 bars are addressed by clock time, not by position in the file
    bar_indexing: str = "clock"             # "clock" | "positional"
    # S7  §2.4 whole shares only; off => idealised fractional sizing
    share_rounding: bool = False
    sleeve_capital: float = 150_000.0
    # §2.2 data-integrity refusal (§4 "sanity checks before trading each day")
    require_full_session_open: bool = True

    def __post_init__(self):
        validate_config(self)


SPEC_LITERAL = EngineConfig()

RESEARCH_COMPAT = EngineConfig(
    thr80_refresh="daily",
    half_day_policy="trade",
    eod_mode="session_close",
    target_on_entry_bar=False,
    tick_rounding=False,
    bar_indexing="positional",
    share_rounding=False,
    require_full_session_open=False,
)

# After the S1/S5 resolutions the two profiles differ only in S2 (half-days),
# S3 (the 15:55 flatten), S6 (clock bar addressing) and S8 (the incomplete-
# session refusal) — all four of which are cases where the spec is right and
# the research engine simply never implemented the rule. See PHASE1_PARITY.md.
RESIDUAL_SWITCHES = ("half_day_policy", "eod_mode", "bar_indexing",
                     "require_full_session_open")


# ----------------------------------------------------------------- data
def load_bars(symbol: str, root: str = ROOT) -> pd.DataFrame:
    """5-minute RTH bars for `symbol`, split-adjusted, sorted, one row/bar."""
    path = os.path.join(root, f"{symbol}_5min_6Years.csv")
    df = pd.read_csv(path)
    dt = pd.to_datetime(
        df["Date"].str.replace(" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    df = df.assign(dt=dt, date=dt.dt.normalize())
    for cut, ratio in SPLIT_ADJUSTMENTS.get(symbol, []):
        pre = df["date"] < cut
        for col in ("Open", "High", "Low", "Close"):
            df.loc[pre, col] = df.loc[pre, col] / ratio
    return df.sort_values("dt").reset_index(drop=True)


@dataclass
class Session:
    date: pd.Timestamp
    idx: np.ndarray      # §2.1 bar index: 0 == the 09:30 bar
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray

    @property
    def n_bars(self) -> int:
        return len(self.c)

    def upto(self, i: int) -> np.ndarray:
        """Positions of bars whose index is <= i (i.e. closed by bar_time(i+1))."""
        return np.nonzero(self.idx <= i)[0]


def build_sessions(bars: pd.DataFrame, cfg: EngineConfig) -> list[Session]:
    open_min = pd.Timedelta(SESSION_OPEN + ":00")
    out = []
    for date, gb in bars.groupby("date", sort=True):
        if cfg.bar_indexing == "clock":
            offs = (gb["dt"] - (date + open_min)).dt.total_seconds().to_numpy()
            idx = (offs / 300.0).round().astype(int)
        else:
            idx = np.arange(len(gb))
        out.append(Session(
            date=date, idx=idx,
            o=gb["Open"].to_numpy(float), h=gb["High"].to_numpy(float),
            l=gb["Low"].to_numpy(float), c=gb["Close"].to_numpy(float),
            v=gb["Volume"].to_numpy(float)))
    return out


# ------------------------------------------------------- daily features
def daily_features(sessions: list[Session], cfg: EngineConfig) -> pd.DataFrame:
    """§2.1 definitions. Every column uses only data available before it is
    consumed; ATR5 and thr80 use no data from day d at all."""
    or_lo_i, or_hi_i = bar_index(OR_WINDOW[0]), bar_index(OR_WINDOW[1])
    rows = []
    for s in sessions:
        win = np.nonzero((s.idx >= or_lo_i) & (s.idx < or_hi_i))[0]
        if len(win):
            or_high = float(s.h[win].max())
            or_low = float(s.l[win].min())
            # §2.1 pos10 uses the close at 10:00 = close of the last bar of
            # the opening-range window (the bar labelled 09:55).
            close10 = float(s.c[win[-1]])
        else:
            or_high = or_low = close10 = float("nan")
        span = or_high - or_low
        rows.append({
            "date": s.date,
            "n_bars": s.n_bars,
            "first_bar_idx": int(s.idx[0]),
            "last_bar_idx": int(s.idx[-1]),
            "open": float(s.o[0]),
            "high": float(s.h.max()),
            "low": float(s.l.min()),
            "close": float(s.c[-1]),
            "or_high": or_high,
            "or_low": or_low,
            "close10": close10,
            "or30": span / float(s.o[0]) * 100.0,
            # §2.1: "If OR_high == OR_low, use 0.5."
            "pos10": (close10 - or_low) / span if span > 0 else 0.5,
        })
    d = pd.DataFrame(rows).set_index("date").sort_index()

    # §2.1 daily_range_pct and ATR5 (mean over the 5 completed sessions before d)
    d["range_pct"] = (d["high"] - d["low"]) / d["open"] * 100.0
    d["atr5"] = d["range_pct"].rolling(ATR_LOOKBACK).mean().shift(1)

    # §2.1 thr80
    d["thr80"] = _trailing_pctl(d["or30"], cfg)

    # §2.2 half-day / data-integrity flags
    flatten_i = bar_index(FLATTEN_TIME)
    d["is_half_day"] = d["last_bar_idx"] < flatten_i
    d["late_open"] = d["first_bar_idx"] > 0
    return d


def _trailing_pctl(or30: pd.Series, cfg: EngineConfig) -> pd.Series:
    """80th percentile of OR30 over the prior `OR_PCTL_WINDOW` sessions,
    strictly before the reference session; >= OR_PCTL_MINOBS observations
    required, else NaN (and the sleeve does not trade)."""
    daily = (or30.shift(1)
             .rolling(OR_PCTL_WINDOW, min_periods=OR_PCTL_MINOBS)
             .quantile(OR_PCTL))
    if cfg.thr80_refresh == "daily":
        return daily
    if cfg.thr80_refresh != "monthly":
        raise ValueError(f"bad thr80_refresh={cfg.thr80_refresh!r}")
    # §2.1: recomputed on the first session of each calendar month and held
    # constant within the month.
    month = pd.Series(or30.index, index=or30.index).dt.to_period("M")
    first_of_month = ~month.duplicated()
    held = daily.where(first_of_month)
    return held.ffill()


# --------------------------------------------------------- daily gating
def gate_on(row: pd.Series, cfg: EngineConfig) -> tuple[bool, str]:
    """§2.2 daily gate, evaluated before the open. Returns (ok, reason)."""
    if not np.isfinite(row["atr5"]):
        return False, "atr5_unavailable"
    if row["atr5"] < cfg.gate_atr5_min:
        return False, "atr5_below_gate"
    if cfg.half_day_policy == "off" and row["is_half_day"]:
        return False, "scheduled_half_day"
    if cfg.require_full_session_open and row["late_open"]:
        return False, "incomplete_session_data"
    return True, "gate_on"


def filter_on(row: pd.Series, cfg: EngineConfig) -> tuple[bool, str]:
    """§2.3 morning filter, evaluated once at 10:00. Returns (ok, reason)."""
    if not np.isfinite(row["thr80"]):
        return False, "thr80_insufficient_history"
    if not np.isfinite(row["or30"]) or not np.isfinite(row["pos10"]):
        return False, "or30_unavailable"
    if row["or30"] >= row["thr80"] and row["pos10"] < POS10_TOP_THIRD:
        return False, "stand_down_wide_or_weak_pos10"
    return True, "filter_on"


# ------------------------------------------------------------ simulator
@dataclass
class Trade:
    entry_bar: int
    exit_bar: int
    entry_px: float
    exit_px: float
    qty: float
    ret: float
    outcome: str          # "target" | "stop" | "flatten"


@dataclass
class SessionResult:
    date: pd.Timestamp
    traded: bool
    pnl: float = 0.0
    fills: int = 0
    stop_outs: int = 0
    trades: list[Trade] = field(default_factory=list)
    anchor_updates: list[tuple[int, float, float]] = field(default_factory=list)
    reason: str = ""


def simulate_session(s: Session, cfg: EngineConfig) -> SessionResult:
    """§2.4–§2.8 on one session's bars.

    Timeline per bar i, in the order a live engine would observe it:
      1. bar i trades  -> resolve any open position against the OCA bracket
                          (stop first: worst-case intrabar ordering)
      2. still flat and counters permit -> the resting entry limit, priced
         off completed bars only, may fill
      3. bar i closes  -> anchor is updated with bar i's high, and the
         resting limit ratchets up for bar i+1
    """
    start_i = bar_index(cfg.start_time)
    flatten_i = bar_index(FLATTEN_TIME)
    last_bar_i = int(s.idx[-1])
    if cfg.eod_mode == "flatten_1555":
        # §2.8: flat at 15:55, i.e. the last bar that may hold a position is
        # the one that closes at 15:55 (the bar labelled 15:50).
        stop_i = min(flatten_i - 1, last_bar_i)
    elif cfg.eod_mode == "session_close":
        stop_i = last_bar_i
    else:
        raise ValueError(f"bad eod_mode={cfg.eod_mode!r}")

    res = SessionResult(date=s.date, traded=True)
    pos = np.nonzero((s.idx >= start_i) & (s.idx <= stop_i))[0]
    if len(pos) == 0:
        res.reason = "no_bars_in_trading_window"
        return res

    # §2.5 step 1: anchor = session high over completed bars only.
    prior = np.nonzero(s.idx < s.idx[pos[0]])[0]
    if len(prior) == 0:
        res.reason = "no_completed_bars_before_start"
        return res
    anchor = float(s.h[prior].max())

    def tick(x: float) -> float:
        return round_to_tick(x, cfg.tick_size) if cfg.tick_rounding else x

    def sized(limit_px: float) -> float:
        """§2.4 order_qty. Fractional sizing is the idealised limit of this."""
        if not cfg.share_rounding:
            return cfg.f * cfg.sleeve_capital / limit_px
        return float(math.floor(cfg.f * cfg.sleeve_capital / limit_px))

    in_pos = False
    entry_px = 0.0
    entry_bar = -1
    qty = 0.0
    limit_px = tick(anchor * (1 - cfg.dip_pct))
    res.anchor_updates.append((int(s.idx[pos[0]]), anchor, limit_px))

    def book(exit_bar: int, exit_px: float, outcome: str) -> None:
        nonlocal in_pos
        ret = qty * (exit_px - entry_px) / cfg.sleeve_capital
        res.trades.append(Trade(entry_bar, exit_bar, entry_px, exit_px,
                                qty, ret, outcome))
        res.pnl += ret
        if outcome == "stop":
            res.stop_outs += 1
        in_pos = False

    for p in pos:
        i = int(s.idx[p])
        o, h, l = s.o[p], s.h[p], s.l[p]

        # --- 1. resolve the open position against the live OCA bracket
        if in_pos:
            tgt = tick(entry_px * (1 + cfg.target_pct))
            stp = tick(entry_px * (1 - cfg.stop_pct))
            if l <= stp:
                # SELL STOP is stop-market: a gap through it fills at the open.
                book(i, min(o, stp), "stop")
            elif (cfg.target_on_entry_bar or i > entry_bar) and h >= tgt:
                # SELL LIMIT: a gap above it fills at the (better) open.
                book(i, max(o, tgt), "target")

        # --- 2. the resting BUY LIMIT (§2.5), if the counters permit (§2.7)
        if (not in_pos and res.fills < cfg.max_fills
                and res.stop_outs < cfg.max_stops and l <= limit_px):
            entry_px = min(limit_px, o)   # gap through the limit fills better
            entry_bar = i
            qty = sized(entry_px)
            if qty <= 0:                  # §2.4 whole shares only
                res.reason = "order_qty_below_one_share"
                break
            in_pos = True
            res.fills += 1
            # The bracket is live from the fill, so the stop may fire on the
            # entry bar itself. The target may not (see S4 / §2.6). The fill
            # is always at the stop price: entry_px <= o, so o > entry_px *
            # (1 - stop_pct) always holds and no gap-through is possible.
            stp = tick(entry_px * (1 - cfg.stop_pct))
            if l <= stp:
                book(i, stp, "stop")
            elif cfg.target_on_entry_bar:
                tgt = tick(entry_px * (1 + cfg.target_pct))
                if h >= tgt:
                    book(i, max(o, tgt), "target")

        # --- 3. bar i closes: ratchet the anchor, never downward (§2.5.3)
        if h > anchor:
            anchor = float(h)
            new_limit = tick(anchor * (1 - cfg.dip_pct))
            if new_limit > limit_px:
                limit_px = new_limit
                res.anchor_updates.append((i, anchor, limit_px))

    # --- §2.8 mandatory flatten
    if in_pos:
        last_p = int(pos[-1])
        book(int(s.idx[last_p]), float(s.c[last_p]), "flatten")
    return res


# ------------------------------------------------------------ sleeve run
def run_sleeve(symbol: str, cfg: EngineConfig = SPEC_LITERAL,
               root: str = ROOT, bars: pd.DataFrame | None = None):
    """Returns (daily_log DataFrame, ON-day return Series, trade log DataFrame)."""
    bars = load_bars(symbol, root) if bars is None else bars
    sessions = build_sessions(bars, cfg)
    d = daily_features(sessions, cfg)

    log_rows, trade_rows, returns = [], [], {}
    for s in sessions:
        row = d.loc[s.date]
        g_ok, g_why = gate_on(row, cfg)
        f_ok, f_why = (filter_on(row, cfg) if g_ok else (False, "gate_off"))
        rec = {
            "date": s.date, "symbol": symbol,
            "atr5": row["atr5"], "gate_on": g_ok, "gate_reason": g_why,
            "or30": row["or30"], "thr80": row["thr80"], "pos10": row["pos10"],
            "filter_on": f_ok, "filter_reason": f_why,
            "n_bars": row["n_bars"], "is_half_day": row["is_half_day"],
            "traded": False, "fills": 0, "stop_outs": 0,
            "anchor_updates": 0, "pnl": 0.0,
        }
        if g_ok and f_ok:
            r = simulate_session(s, cfg)
            rec.update(traded=True, fills=r.fills, stop_outs=r.stop_outs,
                       anchor_updates=len(r.anchor_updates), pnl=r.pnl)
            returns[s.date] = r.pnl
            for t in r.trades:
                trade_rows.append({
                    "date": s.date, "symbol": symbol,
                    "entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
                    "entry_px": t.entry_px, "exit_px": t.exit_px,
                    "qty": t.qty, "ret": t.ret, "outcome": t.outcome})
        log_rows.append(rec)

    daily_log = pd.DataFrame(log_rows).set_index("date")
    on = pd.Series(returns, dtype=float).sort_index()
    on.index.name = "date"
    trades = pd.DataFrame(trade_rows)
    return daily_log, on, trades
