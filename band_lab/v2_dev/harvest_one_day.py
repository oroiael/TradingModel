"""
One day, one rule, counted by hand: how often does +0.5% arrive before -0.5%?

The volatility-harvest work has accumulated a lot of machinery. This strips it
back to a single session and a single question, with nothing imported from the
rest of the project. The only inputs are SOXL_1min.csv and the 0.5% threshold.

The rule
--------
  * Buy at the OPEN of a minute. First entry is the 09:30 open.
  * Watch forward for the first touch of +0.5% (target) or -0.5% (stop).
  * When the trade resolves, wait for the next minute and buy again at its open.
    Only one trade is ever being *tracked* at a time.
  * No new entries once the clock reaches 14:00. Trades already open keep running.
  * 15:55: close whatever is still held at that minute's CLOSE, treated as the
    limit price actually achieved.

Where the touch is read, in the order the tape produces it
----------------------------------------------------------
  * Entry bar: its open IS the fill, so only that bar's high/low can resolve it.
  * Every later bar: the OPEN is the first print, so it is checked first; then
    the high (target) and low (stop).
  * Fill price: if a bar's open has already gapped through the level, the open
    is the fill. Otherwise the level itself fills, as a resting limit order.

Two honest unknowns, both surfaced rather than buried
-----------------------------------------------------
  1. When one bar's high reaches the target AND its low reaches the stop, OHLC
     cannot say which came first. Those bars are resolved adversely (stop first)
     and counted separately, so the reader can see how much of the result rests
     on that choice.
  2. The request says what to do after a WIN (re-enter next minute) but not
     after a loss, while also saying to close "all trades" at 15:55. Both
     readings produce the SAME chain of entries and the same win/loss count --
     they differ only in the price a loser is booked at:
        HOLD  losers are parked, unsold, and closed with everything else at the
              15:55 close. Several can be open at once.
        STOP  losers are sold at -0.5% on the touch. At most one trade is open.
     Both are reported.

    python3 band_lab/v2_dev/harvest_one_day.py
    python3 band_lab/v2_dev/harvest_one_day.py --date 2023-06-14
    python3 band_lab/v2_dev/harvest_one_day.py --seed 7 --pct 0.005
"""

from __future__ import annotations

import argparse
import os
import random

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OPEN_MIN = 9 * 60 + 30      # 09:30, first bar of the session
NO_NEW_MIN = 14 * 60        # 14:00, no entry may be opened at or after this
FLAT_MIN = 15 * 60 + 55     # 15:55, everything still held is closed here


def load_day(symbol, date=None, seed=0):
    """Return one full session as a list of bars, plus the date chosen.

    A full session must carry both the 09:30 and the 15:55 bar; half-days are
    not eligible because the 15:55 exit the rule depends on does not exist.
    """
    df = pd.read_csv(os.path.join(ROOT, f"{symbol}_1min.csv"))
    dt = pd.to_datetime(
        df["Date"].str.replace(f" America/New_York", "", regex=False),
        format="%Y%m%d %H:%M:%S")
    df = df.assign(day=dt.dt.normalize(), minute=dt.dt.hour * 60 + dt.dt.minute)

    by_min = df.groupby("day")["minute"]
    full = sorted(set(by_min.min()[by_min.min() == OPEN_MIN].index)
                  & set(df[df.minute == FLAT_MIN]["day"].unique()))
    if not full:
        raise SystemExit("no complete sessions in the file")

    if date is None:
        chosen = random.Random(seed).choice(full)
    else:
        chosen = pd.Timestamp(date).normalize()
        if chosen not in set(full):
            raise SystemExit(f"{date} is not a complete session in {symbol}_1min.csv")

    g = df[(df.day == chosen) & (df.minute >= OPEN_MIN) & (df.minute <= FLAT_MIN)]
    g = g.sort_values("minute")
    bars = list(zip(g.minute.astype(int), g.Open.astype(float), g.High.astype(float),
                    g.Low.astype(float), g.Close.astype(float), g.Volume.astype(float)))
    return chosen, bars


def resolve(bars, i, target, stop):
    """First touch of target or stop, starting from an entry at bars[i]'s open.

    Returns (outcome, bar_index, fill_price, ambiguous) with outcome one of
    'up', 'down', or 'open' (never resolved -- still held at 15:55).
    """
    for j in range(i, len(bars)):
        _, o, hi, lo, _, _ = bars[j]

        # The entry bar's open is the purchase itself and cannot also be the exit.
        if j > i:
            if o >= target:
                return "up", j, o, False
            if o <= stop:
                return "down", j, o, False

        hit_up, hit_dn = hi >= target, lo <= stop
        if hit_up and hit_dn:
            # Both levels live inside one minute. The tape order is unknowable
            # from OHLC, so the adverse side is assumed and the bar is flagged.
            return "down", j, stop, True
        if hit_up:
            return "up", j, target, False
        if hit_dn:
            return "down", j, stop, False

    return "open", None, None, False


def run(bars, pct):
    """Walk the session once, producing the chain of trades."""
    eod_close = bars[-1][4]
    trades, i = [], 0

    while i < len(bars):
        minute, entry = bars[i][0], bars[i][1]
        if minute >= NO_NEW_MIN:            # 14:00 cutoff on NEW entries only
            break

        target, stop = entry * (1 + pct), entry * (1 - pct)
        outcome, j, fill, ambiguous = resolve(bars, i, target, stop)

        if outcome == "up":
            # Harvested. Same money out under either reading of the loss rule.
            hold, stop_px = fill, fill
            exit_min = bars[j][0]
        elif outcome == "down":
            # The two readings part company here, and only here.
            hold, stop_px = eod_close, fill
            exit_min = bars[j][0]
        else:
            hold = stop_px = eod_close
            exit_min = FLAT_MIN

        trades.append(dict(
            n=len(trades) + 1, entry_min=minute, entry=entry,
            outcome=outcome, exit_min=exit_min, ambiguous=ambiguous,
            hold_exit=hold, stop_exit=stop_px,
            hold_ret=hold / entry - 1, stop_ret=stop_px / entry - 1))

        if outcome == "open":
            break
        i = j + 1                            # "wait until the next minute segment"

    return trades, eod_close


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def concurrent_peak(trades):
    """Most positions open at the same moment under the HOLD reading.

    Winners close on their own touch; losers stay open to 15:55. Walk the
    minute-ordered opens and closes and take the running maximum.
    """
    events = []
    for t in trades:
        events.append((t["entry_min"], 0, +1))
        # ties at one minute: close before open, so a same-minute flip is not
        # double-counted as two positions.
        events.append((FLAT_MIN if t["outcome"] != "up" else t["exit_min"], -1, -1))
    live = peak = 0
    for _m, _pri, delta in sorted(events):
        live += delta
        peak = max(peak, live)
    return max(peak, 1)


def report(symbol, day, bars, trades, eod_close, pct):
    o, hi = bars[0][1], max(b[2] for b in bars)
    lo = min(b[3] for b in bars)

    wins = [t for t in trades if t["outcome"] == "up"]
    losses = [t for t in trades if t["outcome"] == "down"]
    unresolved = [t for t in trades if t["outcome"] == "open"]
    amb = [t for t in losses if t["ambiguous"]]
    resolved = len(wins) + len(losses)

    print(f"\n{'=' * 78}")
    print(f"  {symbol}  {day.date()}  ({day.day_name()})   threshold +/-{pct:.2%}")
    print(f"{'=' * 78}")
    print(f"  session   open {o:.2f}   high {hi:.2f}   low {lo:.2f}   "
          f"15:55 close {eod_close:.2f}")
    print(f"  day range {(hi / lo - 1) * 100:.2f}%   "
          f"open -> 15:55 {(eod_close / o - 1) * 100:+.2f}%")

    print(f"\n  THE COUNT  (identical under both readings of the loss rule)")
    print(f"    trades taken                         {len(trades):>6}")
    print(f"    rose +{pct:.1%} BEFORE falling -{pct:.1%}     {len(wins):>6}"
          + (f"   {len(wins) / resolved * 100:>5.1f}% of resolved" if resolved else ""))
    print(f"    fell  -{pct:.1%} first                  {len(losses):>6}"
          + (f"   {len(losses) / resolved * 100:>5.1f}% of resolved" if resolved else ""))
    print(f"    never resolved, ran to 15:55         {len(unresolved):>6}")
    print(f"    of the losses, same-minute ambiguous {len(amb):>6}"
          f"   (stop assumed first)")

    if trades:
        print(f"\n  LEDGER")
        print(f"    {'#':>3}  {'in':>5}  {'entry':>7}  {'result':<10} {'out':>5}  "
              f"{'HOLD exit':>9} {'HOLD ret':>9}   {'STOP exit':>9} {'STOP ret':>9}")
        for t in trades:
            tag = {"up": "WIN +0.5%", "down": "LOSS -0.5%",
                   "open": "UNRESOLVED"}[t["outcome"]]
            if t["ambiguous"]:
                tag += "*"
            print(f"    {t['n']:>3}  {hhmm(t['entry_min']):>5}  {t['entry']:>7.2f}  "
                  f"{tag:<10} {hhmm(t['exit_min']):>5}  "
                  f"{t['hold_exit']:>9.2f} {t['hold_ret'] * 100:>8.2f}%   "
                  f"{t['stop_exit']:>9.2f} {t['stop_ret'] * 100:>8.2f}%")
        if amb:
            print(f"    * both levels touched inside one minute; stop assumed first")

    # A parked loser stays open until 15:55, so under HOLD the positions stack
    # up and the capital behind them is what the return has to be measured on.
    # Summing trade returns without that divisor silently assumes free leverage.
    peak_hold = concurrent_peak(trades)

    print(f"\n  P&L, one unit of capital per trade, gross of commission and slippage")
    for label, key, peak in (
            ("HOLD  losers parked, closed at the 15:55 close", "hold_ret", peak_hold),
            ("STOP  losers sold on the -0.5% touch", "stop_ret", 1)):
        rets = [t[key] for t in trades]
        total = sum(rets)
        print(f"    {label}")
        print(f"      sum of trade returns  {total * 100:>+8.2f}%     "
              f"avg per trade {(total / len(rets) * 100 if rets else 0):>+6.3f}%")
        print(f"      peak positions open   {peak:>8}      "
              f"-> return on peak capital {total / peak * 100:>+6.2f}%")

    print(f"\n  BENCHMARK")
    print(f"    buy the 09:30 open, hold to the 15:55 close   "
          f"{(eod_close / o - 1) * 100:>+7.2f}%")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SOXL")
    p.add_argument("--date", default=None, help="YYYY-MM-DD; omit to draw at random")
    p.add_argument("--seed", type=int, default=0, help="seed for the random draw")
    p.add_argument("--pct", type=float, default=0.005)
    p.add_argument("--csv", default=None, help="write the ledger to this path")
    a = p.parse_args()

    day, bars = load_day(a.symbol, a.date, a.seed)
    trades, eod_close = run(bars, a.pct)
    report(a.symbol, day, bars, trades, eod_close, a.pct)

    if a.csv and trades:
        pd.DataFrame(trades).assign(symbol=a.symbol, date=day.date()).to_csv(a.csv, index=False)
        print(f"  ledger -> {a.csv}\n")


if __name__ == "__main__":
    main()
