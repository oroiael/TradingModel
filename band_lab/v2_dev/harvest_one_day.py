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

Two funded runs, on a real account rather than a sum of percentages
-------------------------------------------------------------------
Neither run opens a trade every minute. Both are sequential: one trade is
entered, and the next is not entered until that one has resolved. They differ
only in whether a loser is sold.

  RUN 1  PARK   A loser is not sold; it is held to the 15:55 close, so unsold
                losers accumulate. $100,000 account, $25,000 held back in cash
                (the pattern-day-trader minimum), leaving $75,000 across at most
                50 slots -> $1,500 a slot. An entry is skipped if no slot is
                free or if filling it would break the cash floor.

  RUN 2  CLOSE  A loser is sold on the -0.5% touch, so there is never more than
                one position open. The whole $75,000 above the cash floor goes
                into it, and the account compounds trade to trade.

    python3 band_lab/v2_dev/harvest_one_day.py
    python3 band_lab/v2_dev/harvest_one_day.py --date 2023-06-14
    python3 band_lab/v2_dev/harvest_one_day.py --seed 7 --pct 0.005
    python3 band_lab/v2_dev/harvest_one_day.py --equity 250000 --slots 20
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

        target, stop = entry * (1 + up_pct), entry * (1 - dn_pct)
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


def levels(pct):
    """(up, down) fractions from a scalar (symmetric) or an (up, down) pair.

    Kept permissive so every existing caller that passes one number keeps
    working and means the same thing it always did.
    """
    if isinstance(pct, (tuple, list)):
        return float(pct[0]), float(pct[1])
    return float(pct), float(pct)


def ibkr_tiered(shares, price):
    """IBKR Pro tiered US equity commission for ONE order.

    $0.0035 a share, a $1.00 order minimum, capped at 1% of trade value. The
    cap is what stops a 30-share order in a $3 stock costing more than the
    stock. Charged on the buy and again on the sell.
    """
    return min(max(1.00, 0.0035 * shares), 0.01 * shares * price)


def simulate(bars, pct, park_losers, equity, reserve, slots, commission=None,
             slippage=0.0, cutoff=NO_NEW_MIN):
    """Walk the session once with real money and real share counts.

    Sequential by construction: the next entry is only considered after the
    current trade has resolved. `park_losers` is the whole difference between
    the two runs -- when True a loser is kept, unsold, until the 15:55 close,
    which is what lets positions pile up.
    """
    fee = commission or (lambda shares, price: 0.0)
    up_pct, dn_pct = levels(pct)
    # Slippage is a per-share fill penalty: you pay above the print on the way
    # in and receive below it on the way out. The +/-pct levels are measured
    # from what was actually PAID, so the market has to travel slightly further
    # than the headline threshold to pay out.
    eod_close = bars[-1][4]
    cash, ledger, held, blocked = equity, [], [], []
    peak_open = peak_cost = 0
    paid = 0.0
    i = 0

    while i < len(bars):
        minute, entry = bars[i][0], bars[i][1] + slippage
        if minute >= cutoff:                   # no NEW entries from here
            break

        # Sizing. Parked losers tie capital up for the rest of the day, so each
        # slot gets a fixed share of the sleeve. With losers sold there is only
        # ever one position, so it takes everything above the cash floor and the
        # account compounds.
        budget = (equity - reserve) / slots if park_losers else cash - reserve
        shares = int(budget // entry)
        # The commission is cash out of the same pot, so it has to be sized for.
        # Without this the first order eats into the floor and every entry is
        # rejected -- silently producing a zero-trade backtest.
        if shares >= 1:
            shares = int(max(0.0, budget - fee(shares, entry)) // entry)
        while shares >= 1 and cash - shares * entry - fee(shares, entry) < reserve - 1e-9:
            shares -= 1
        cost = shares * entry
        buy_fee = fee(shares, entry) if shares >= 1 else 0.0

        if shares < 1 or len(held) >= slots:
            # No room. Try again next minute; a sold winner may free a slot.
            blocked.append(minute)
            i += 1
            continue

        cash -= cost + buy_fee
        paid += buy_fee
        held.append(dict(entry_min=minute, entry=entry, shares=shares, cost=cost))
        peak_open = max(peak_open, len(held))
        peak_cost = max(peak_cost, sum(h["cost"] for h in held))

        target, stop = entry * (1 + up_pct), entry * (1 - dn_pct)
        outcome, j, fill, ambiguous = resolve(bars, i, target, stop)

        if outcome == "up" or (outcome == "down" and not park_losers):
            fill -= slippage
            sell_fee = fee(shares, fill)
            cash += shares * fill - sell_fee
            paid += sell_fee
            held.pop()                         # sold; the slot and cash come back
            exit_min, exit_px, exit_why = bars[j][0], fill, "sold"
        else:
            # Still owned. It keeps its slot and its cash stays committed for the
            # rest of the session -- this is what makes positions pile up.
            sell_fee = fee(shares, eod_close - slippage)
            exit_min, exit_px = FLAT_MIN, eod_close - slippage
            exit_why = "parked" if outcome == "down" else "unresolved"

        ledger.append(dict(
            n=len(ledger) + 1, entry_min=minute, entry=entry, shares=shares,
            cost=cost, outcome=outcome, ambiguous=ambiguous,
            touch_min=bars[j][0] if j is not None else FLAT_MIN,
            exit_min=exit_min, exit=exit_px, exit_why=exit_why,
            proceeds=shares * exit_px, buy_fee=buy_fee, sell_fee=sell_fee,
            fees=buy_fee + sell_fee,
            pnl=shares * (exit_px - entry) - buy_fee - sell_fee))

        if outcome == "open":
            break
        i = j + 1                              # "wait until the next minute"

    for h in held:                             # 15:55: liquidate what is left
        px = eod_close - slippage
        liq_fee = fee(h["shares"], px)
        cash += h["shares"] * px - liq_fee
        paid += liq_fee

    return dict(ledger=ledger, ending=cash, peak_open=peak_open,
                peak_cost=peak_cost, blocked=blocked, eod_close=eod_close,
                fees=paid)


def report_run(title, rule, sim, equity, reserve, slots, show_ledger):
    led = sim["ledger"]
    wins = [t for t in led if t["outcome"] == "up"]
    losses = [t for t in led if t["outcome"] == "down"]
    unresolved = [t for t in led if t["outcome"] == "open"]
    pnl = sim["ending"] - equity

    print(f"\n{'-' * 78}")
    print(f"  {title}")
    print(f"  {rule}")
    print(f"{'-' * 78}")
    print(f"    start ${equity:,.0f}   cash floor ${reserve:,.0f}   "
          f"max {slots} position{'s' if slots > 1 else ''}")

    if show_ledger and led:
        print(f"\n    {'#':>3} {'in':>5} {'entry':>7} {'sh':>6} {'cost':>10}  "
              f"{'result':<11}{'out':>6} {'exit':>7} {'proceeds':>10} {'P&L $':>9}")
        for t in led:
            tag = {"up": "WIN", "down": "LOSS", "open": "UNRESOLVED"}[t["outcome"]]
            if t["exit_why"] != "sold":
                tag += " park" if t["outcome"] == "down" else ""
            print(f"    {t['n']:>3} {hhmm(t['entry_min']):>5} {t['entry']:>7.2f} "
                  f"{t['shares']:>6} {t['cost']:>10,.0f}  {tag:<11}"
                  f"{hhmm(t['exit_min']):>6} {t['exit']:>7.2f} "
                  f"{t['proceeds']:>10,.0f} {t['pnl']:>+9,.0f}")

    print(f"\n    trades {len(led)}    "
          f"won {len(wins)}    lost {len(losses)}    unresolved {len(unresolved)}"
          + (f"    win rate {len(wins) / (len(wins) + len(losses)) * 100:.1f}%"
             if wins or losses else ""))
    print(f"    peak positions open {sim['peak_open']}    "
          f"peak capital at risk ${sim['peak_cost']:,.0f}    "
          f"idle cash ${equity - sim['peak_cost']:,.0f}")
    if sim["blocked"]:
        print(f"    entries skipped for want of a slot or cash: "
              f"{len(sim['blocked'])} (first {hhmm(sim['blocked'][0])})")
    print(f"    ending equity ${sim['ending']:,.2f}    "
          f"P&L ${pnl:>+,.2f}    on the account {pnl / equity * 100:>+.2f}%"
          f"    on capital used {pnl / sim['peak_cost'] * 100:>+.2f}%"
          if sim["peak_cost"] else "")


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

    if amb:
        print(f"    * both levels touched inside one minute; stop assumed first")

    print(f"\n  BENCHMARK   buy the 09:30 open, hold to the 15:55 close   "
          f"{(eod_close / o - 1) * 100:>+.2f}%")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SOXL")
    p.add_argument("--date", default=None, help="YYYY-MM-DD; omit to draw at random")
    p.add_argument("--seed", type=int, default=0, help="seed for the random draw")
    p.add_argument("--pct", type=float, default=0.005)
    p.add_argument("--equity", type=float, default=100_000, help="starting account")
    p.add_argument("--reserve", type=float, default=25_000, help="cash never deployed")
    p.add_argument("--slots", type=int, default=50, help="max positions open at once")
    p.add_argument("--no-ledger", action="store_true", help="counts only")
    p.add_argument("--csv", default=None, help="write both run ledgers to this path")
    a = p.parse_args()

    day, bars = load_day(a.symbol, a.date, a.seed)

    trades, eod_close = run(bars, a.pct)
    report(a.symbol, day, bars, trades, eod_close, a.pct)

    runs = [
        ("RUN 1  PARK the losers",
         "enter, resolve, re-enter next minute; a loser is NOT sold, it is held "
         "to 15:55",
         simulate(bars, a.pct, True, a.equity, a.reserve, a.slots), a.slots),
        ("RUN 2  CLOSE the losers",
         "enter, resolve, re-enter next minute; a loser IS sold on the -0.5% "
         "touch, so only one position is ever open",
         simulate(bars, a.pct, False, a.equity, a.reserve, 1), 1),
    ]
    for title, rule, sim, slots in runs:
        report_run(title, rule, sim, a.equity, a.reserve, slots, not a.no_ledger)

    bh = int((a.equity - a.reserve) // bars[0][1])
    print(f"\n{'-' * 78}")
    print(f"  BENCHMARK  buy {bh:,} shares at the 09:30 open, sell at the 15:55 close")
    print(f"{'-' * 78}")
    print(f"    P&L ${bh * (eod_close - bars[0][1]):>+,.2f}    "
          f"on the account {bh * (eod_close - bars[0][1]) / a.equity * 100:>+.2f}%")
    print()

    if a.csv:
        frames = []
        for title, _rule, sim, _slots in runs:
            if sim["ledger"]:
                frames.append(pd.DataFrame(sim["ledger"]).assign(
                    run=title.split()[1], symbol=a.symbol, date=day.date()))
        if frames:
            pd.concat(frames).to_csv(a.csv, index=False)
            print(f"  ledgers -> {a.csv}\n")


if __name__ == "__main__":
    main()
