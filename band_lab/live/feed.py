"""
The 5-minute bar feed.

`PHASE2_PLAN.md` Stage 2 asks for "a 5-minute bar feed with a periodic
cross-check against a historical fetch". This implements the feed *as* the
historical fetch, polled, rather than as `reqRealTimeBars` plus a separate
reconciliation:

* §6.5 — whether `reqRealTimeBars` emits a bar when nothing trades — is an
  open question, and a feed that silently stops on a quiet bar would
  understate `session_high`, which is the anchor the strategy ratchets from.
* Polling `reqHistoricalData` for today's session returns whatever IBKR
  believes the completed bars are, which is the same source the cross-check
  would have used. One mechanism instead of two removes the class of bug
  where the feed and the check disagree.

The cost is latency: a bar is seen up to `poll_seconds` after it closes. The
strategy is defined on 5-minute closes and is not latency-sensitive (§1 of
the deployment notes), so this is the right trade.

`BarFeed` is deliberately pure-ish: it holds the set of bar indices already
emitted and yields only newly-completed ones, in order. That makes the "did we
miss a bar" question answerable by the engine (which reports gaps) rather than
hidden in the transport.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from broker import Broker          # noqa: E402
from strategy_core import Bar      # noqa: E402


@dataclass
class BarFeed:
    """Emits completed 5-minute bars for one symbol, once each, in order."""

    broker: Broker
    symbol: str
    duration: str = "1 D"
    bar_size: str = "5 mins"
    seen: set = field(default_factory=set)
    last_idx: int = -1

    def poll(self, now: Optional[datetime] = None) -> list[Bar]:
        """Return bars completed since the last call, oldest first.

        The final bar IBKR returns may still be forming, so it is held back
        until a later poll shows a bar beyond it. Acting on a partial bar would
        set the anchor from an incomplete high — §2.5.1 says the anchor updates
        only on completed bars, and this is where that is enforced in transport.
        """
        bars = self.broker.historical_bars(self.symbol, now, self.duration,
                                           self.bar_size)
        if not bars:
            return []
        bars = sorted(bars, key=lambda b: b.idx)
        completed = bars[:-1]                      # hold back the forming bar
        out = [b for b in completed if b.idx not in self.seen]
        for b in out:
            self.seen.add(b.idx)
            self.last_idx = max(self.last_idx, b.idx)
        return out

    def missing_before(self, idx: int) -> list[int]:
        """Bar indices that should have arrived by `idx` and did not.

        A missed bar understates `session_high`. The engine reports gaps when
        it sees a jump, but that only catches a gap *followed* by a bar; this
        answers the question directly at any point in the session.
        """
        if not self.seen:
            return []
        return [i for i in range(min(self.seen), idx) if i not in self.seen]

    def reset(self) -> None:
        """New session. Called by the pre-open job, never mid-session."""
        self.seen.clear()
        self.last_idx = -1
