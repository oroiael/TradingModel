---
name: ibkr-semantics
description: Verified IBKR/TWS and ib_async behaviour for the band_lab live trading engine — order states, cancels, modifies, OCA groups, error codes, and which of them this project has actually been burned by. Use this whenever touching band_lab/live/ (broker.py, orders.py, engine.py, run.py, watchdog.py), reasoning about an IBKR error code or order status, writing or changing FakeIB, or explaining why a live session behaved differently from the backtest. Also use it before asserting anything about what TWS "does" — IBKR's own documentation is unreachable from this environment, and every defect in this project's history came from assuming API behaviour instead of reading it.
---

# IBKR semantics, as far as they are actually known here

## The rule this exists to enforce

**Read the installed `ib_async` source before claiming what the API does.** It is on
disk, it is authoritative for the client half, and it takes a minute:

```bash
P=$(python3 -c "import ib_async, os; print(os.path.dirname(ib_async.__file__))")
sed -n '/    def placeOrder/,/^    def /p' $P/ib.py
grep -n "warningCodes" -A 4 $P/wrapper.py
```

This is not pedantry. **Every defect in `PROJECT_STATUS.md` §4 came from assuming
API behaviour rather than checking it**, starting with §4.1 — `readonly=True` was
believed to stop orders reaching the market, and it does not; it is a client-side
flag that skips two startup requests. Following the documentation as written would
have sent live orders during the session that existed to send none.

The failure mode is specific and worth naming: reasoning from a log plus general
market knowledge produces fluent, confident prose whether or not anything was
checked. The boundary between "derived from this log" and "recalled about an API"
is invisible in the output unless it is stated. **State it.** Mark claims as
verified-from-source or inferred, in code comments and in prose.

## What can and cannot be reached from here

| source | status |
|---|---|
| installed `ib_async` package | ✅ on disk, authoritative for client behaviour |
| `raw.githubusercontent.com` | ✅ reachable |
| `interactivebrokers.github.io/tws-api` | ❌ egress-blocked |
| `ibkrcampus.com` / `interactivebrokers.com` | ❌ egress-blocked |
| `InteractiveBrokers/tws-api-public` on GitHub | ⚠️ reachable but contains only a link page |

So **TWS-side behaviour cannot be verified here.** Anything about what the *server*
does — what an error code means, whether `reqGlobalCancel` frees a stuck OCA leg —
is inference until a live session shows it. `broker.py`'s header has said this
since the Stage 2 build; keep it true.

## Order status, and the two states that cause trouble

From `ib_async/order.py`, transcribed into `broker.py` as `DONE_STATES` /
`ACTIVE_STATES` and asserted equal to the package's own frozensets by
`test_fake_and_real_agree_on_what_counts_as_working`, so an upgrade that moves a
state fails the suite instead of drifting:

```
DoneStates    = {Filled, Cancelled, ApiCancelled, Inactive}
ActiveStates  = {PendingSubmit, ApiPending, PreSubmitted, Submitted,
                 ValidationError, ApiUpdate}
```

`IB.openTrades()` returns *every trade whose status is not a DoneState*. Two
consequences do most of the damage:

**`PendingCancel` is in neither set.** `IB.cancelOrder` sets it locally and it
stays until TWS confirms — only an untransmitted `PendingSubmit` order or an
`Inactive` one goes straight to `Cancelled`. So a cancel that TWS never
acknowledges keeps showing up as a working order forever. That is what
`LMT SELL 524 (PendingCancel)` was on 2026-08-10, holding the shares the flatten
needed while the engine spent its retry budget.

**`Cancelled` is a DoneState, and any non-warning error sets it.** `wrapper.error`
marks the trade `Cancelled` for every error code outside its warning set — and its
own comment admits what that costs:

> Errors can mean two things:
>  - new order is REJECTED
>  - existing order is server-canceled (DAY orders, margin problems)
>  - **modification to *existing* order just has an update error, but the order is STILL LIVE**

So a rejected modify makes the order vanish from the client's view while it is
still working upstream. On 2026-08-10 SOXS's `Error 103` did exactly that: the
engine believed `43.78 x1701`, the broker still had `43.71 x1703`, and the fill
settled 1,703 shares. **Never re-place an order because the client says it is
gone** — that is how you end up with two live entries. `orders.py:_modify_entry`
logs critical and refuses instead.

The warning codes, which keep the order alive and set `ValidationError` (an
ActiveState): `{105, 110, 165, 321, 329, 399, 404, 434, 492, 10167}` and
`2100–2199`. Note **`103` is not among them** and **`202` is deliberately not** —
ib_async's comment: "202 is literally 'Order Canceled' error status, so now it is
an order-delete error".

## Modify, and the race it opens

`IB.placeOrder(contract, order)` with an `orderId` that already has a trade *is*
the modify. It asserts only that the status is not a DoneState, so it will happily
modify an order TWS has not acknowledged. `IBBroker.modify_limit` mutates the local
`Order` in place and then calls it — which means **on rejection the client's copy
already carries the new price and nothing rolls it back.**

The engine's defence is to treat its own limit as a belief: `_resync_entry` adopts
whatever the broker reports before every ratchet and warns when they disagree. The
optimistic write after a successful modify stays, because acceptance is
asynchronous and there is nothing to wait on — the next bar corrects it.

`orderStatus` overwrites the local status with whatever TWS reports, so a
`reqAllOpenOrders` *can* revive a trade the client wrongly marked `Cancelled`.
**This is not yet used and would be a real improvement** — it would let the engine
resolve the "I think I'm armed but see nothing" case instead of standing down.

## Executions are not fills

IBKR settles one order in as many executions as the book requires. On 2026-08-06 a
541-share entry arrived as 300 + 210 + 31; on 2026-08-10, 524 arrived as seven
executions and 1,703 as eleven. Two rules follow, and both have been violated in
this codebase at least once:

- **Size protective orders from `broker.position()`, not from an execution.**
  `position()` runs *ahead* of the execution stream — it already read 524 when the
  first execution reported 27. Sizing from the execution placed a 27-share bracket
  and replaced it a millisecond later, generating two OCA generations per entry.
- **Count round trips, not executions, wherever a count is compared to a §2.7
  counter.** `reconcile()` compared 7 executions to 1 fill and reported MISMATCH on
  every healthy session, which trains the operator to ignore it.

## OCA and global cancel

`ocaGroup` alone is not enough — `ocaType` defaults to `0`. `IBBroker._order` sets
`ocaType = 1` ("cancel remaining with block") and marks it `ASSUMPTION §6.3`.
A target fill was observed cancelling its sibling stop on 2026-08-10, which is
consistent, but that is one observation and not a verification.

`IB.reqGlobalCancel` is documented in ib_async as cancelling **"all active trades
including those placed by other clients or TWS/IB gateway."** It is the right
hammer when individual cancels stall, and it is genuinely global — it will take
this sleeve's own working flatten with it, which is why `ensure_flat` re-sends
unconditionally after escalating. Whether it frees a leg stuck in `PendingCancel`
is **not verified**; `FakeIB` models it optimistically and says so.

## Writing or changing FakeIB

The double exists so the order path can be tested without a broker, which only
works if it models the states the broker actually reports. It did not, for most of
this project's life: it filtered working orders to `Submitted`/`PreSubmitted`
while `IBBroker` returned everything from `openTrades()`. The state that carried
524 shares overnight could not be expressed in a test.

- Use `broker.is_working(status)`. **Never hand-write a status list** — that is
  the exact mistake, and it recurred inside a test double written to catch it.
- New states must be reachable: `stall_cancels` leaves cancels in `PendingCancel`,
  `confirm_cancels()` acknowledges them.
- If a new divergence appears, fix the double rather than working around it in the
  test. A test that reproduces a bug through a mechanism the broker does not have
  passes for the wrong reason.

## The standing open questions

These are inference, not verification, and each is marked at its use site:

| assumption | where | how it gets settled |
|---|---|---|
| a broker-side `STP` survives the client dying | `PHASE2_PLAN.md` §6.1 | kill the engine with a bracket on, look at TWS |
| `ocaType=1` gives cancel-with-block | `broker.py:_order` | observe a stop fill cancelling its target |
| `reqGlobalCancel` frees a stalled `PendingCancel` | `orders.py:ensure_flat` | a session where the escalation fires |
| modifying an unacknowledged order causes `103` | `orders.py:_modify_entry` | arm and ratchet in the same second, deliberately |
| `1 D` historical inside RTH may reach into the prior session | `PHASE2_PLAN.md` §6.4 | compare a request's span against the session |

When one of these is settled by a live session, move it out of this table and into
the verified sections above, with the date and what was observed.
