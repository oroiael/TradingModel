# V2 Test Program — Entry Anchor for the Churn Harvester Core

Current value: **the session rolling high** (prior bars only, RTH from
09:30): the entry is a resting limit 1% below the highest print of the
day so far. This is the last open variable on the status board — after
V2 the register is fully audited.

What IS tested: the anchor's one structural rival so far — the static
band edge (buy the OR low) — lost catastrophically (−1.1%/day vs the
incumbent's +65.6 bp), establishing "buy pullbacks from an advancing
reference, never a fixed level." What is NOT tested: every other
advancing reference. VWAP, windowed highs, and reset anchors all define
"a dip" differently, and the incumbent has a known behavioral quirk that
has never been measured: **the session high never decays**, so on a day
that opens strong and fades, price can sit far below the anchor all
afternoon — after any exit the next "1% dip" trigger is instantly
satisfied and the sim re-enters at the market. Whether that
instant-re-entry behavior is a hidden bug or a hidden source of edge
(V11's deeper-dip escalation hints it may be the *feature*) is the
program's central question.

Everything else stays locked: dip/target 1%, stop −4% absolute, start
11:00, cap 5, 2-stop breaker, V9 direction filter, ATR5 ≥ 6 gate,
corrected engine. Only the anchor varies. Baseline: **65.6 bp/traded-day,
Sharpe 3.09.**

---

## T1 runs FIRST — entry anatomy under the incumbent (measurement)

**Mechanic.** Regenerate per-trade logs and record, for every entry, the
**depth below the anchor at fill**: (anchor − fill)/anchor. Bucket trades
by depth (≈1% "true dips" vs 2–4% vs >4% "deep re-entries on fade days")
and report count, mean return, stop rate, and outcome mix per bucket,
plus which trade-sequence numbers populate each bucket. This prices the
whole program before any rival anchor runs: if deep-below-anchor entries
carry the best edge, anchors that prevent them (windowed, reset) are
pre-doomed and the incumbent's quirk is confirmed as the feature; if
deep entries are the loss pocket, the rivals have a real target.

**Data now:** sufficient. **Depth:** hours. **Downside:** none.
**Expected (guess):** deep entries are where the V11 escalation lives —
mean return HIGHER than true-1% dips, at a higher stop rate; verdict
likely "feature, not bug."

## T2. Windowed rolling high

**Mechanic.** Anchor = max high over the last **N bars** (N ∈ {12, 24,
36} = 1h/2h/3h), prior bars only, vs the session anchor. A windowed
anchor decays: stale morning highs roll off, the trigger tracks recent
price structure, and a fresh local pullback is required before every
entry. Same plateau verdict standard.

**Data now:** sufficient. **Depth:** hours.
**Max upside:** avoids anchoring to a dead morning high on fade days —
if T1 shows deep entries lose, this is the fix; guessed +0–4 bp/day.
**Max downside:** kills the deep re-entries that T1 may show are the
best trades, and adds a parameter (N) to a variable that currently has
none — the incumbent wins ties by parsimony.

## T3. VWAP-referenced anchor (+ prior-close control cell)

**Mechanic.** Anchor = intraday cumulative VWAP (typical price ×
volume from the 5-min bars); entry = resting limit at VWAP × (1 − δ),
δ ∈ {0.5%, 1%, 1.5%}. VWAP is a *value* reference rather than an
*extreme* reference — it advances on strong days and sinks on weak
ones, so "1% below VWAP" is a fundamentally different dip definition
than "1% below the high," and it is the reference execution desks
actually peg to (IBKR supports VWAP-pegged orders natively). One extra
control cell: anchor = prior session close (entry 1% below it) — cheap,
closes the spec's last named alternative, expected to fail (on a ±3%
gapping 3x ETF it mostly measures the gap).

**Data now:** sufficient — 5-min bars carry Volume; note the 5-min
typical-price VWAP approximates tick VWAP (1-min data would sharpen it;
flagged, not blocking). **Depth:** half-day.
**Max upside:** a value-anchored dip may avoid buying the first
pullback of a blow-off (the high-anchor's blind spot); guessed
+0–3 bp/day. **Max downside:** below-VWAP entries on trend-up days may
simply never fill (VWAP rides under price all day) — trade count is the
thing to watch; a high-Sharpe-tiny-N result gets the V10-forms
treatment (calendar accounting kills it).

## T4. Reset-after-exit anchor

**Mechanic.** One prespecified structural variant: anchor = rolling
high **since the last exit** (or session start for the first trade).
This surgically removes the instant-re-entry behavior — after every
exit, price must set a local high and then pull back 1% from it before
the next entry. Directly tests T1's verdict: if deep re-entries are the
loss pocket, this variant harvests the fix; if they are the feature,
this variant measures exactly what the feature is worth (its P&L gap to
the incumbent = the value of instant re-entry).

**Data now:** sufficient. **Depth:** hours.
**Bounds:** symmetric — this is the cleanest mechanism probe in the
program; either way its number becomes documentation.

## T5. Validation protocol

**Mechanic.** (a) Yearly walk-forward across the anchor family
(incumbent, best windowed N, best VWAP δ, reset) — adoption bar OOS ≥4
of 5 years no worse than the incumbent; (b) plateau in N and δ; (c)
**mechanism tie-back** — any winner's day-overlap and entry-depth
distribution must match the T1 anatomy story (a rival that wins without
explaining WHICH entries it fixed is treated as fitted and rejected);
(d) trade-count and cost re-accounting; (e) desk restatement — the
anchor must remain executable as resting/pegged limit orders at IBKR
(session-high and VWAP-pegged both are; a windowed anchor needs API
order maintenance like the current ratchet).

**Data now:** sufficient. **Depth:** hours.

---

## Program summary

| test | depth | data now | decisive question | best case | worst case |
|---|---|---|---|---|---|
| **T1 entry anatomy** | hours | ✅ | are deep-below-anchor re-entries the feature or the bug? | prices the whole program | — (measurement) |
| T2 windowed high | hours | ✅ | should stale highs decay? | +0–4 bp on fade days | kills the deep-entry edge |
| T3 VWAP anchor | half-day | ✅ (1-min sharper) | extreme-reference vs value-reference? | value anchor dodges blow-off tops | never fills on trend days |
| T4 reset anchor | hours | ✅ | what is instant re-entry worth? | clean mechanism number either way | — |
| T5 validation | hours | ✅ | OOS + mechanism + executability | adoption evidence | incumbent confirmed, register closed |

**Recommended order: T1 → T2 → T3 → T4 → T5.**

**Aggregate bounds:** best case — a rival anchor adds ~2–4 bp/day with a
named mechanism (fade-day stale-anchor fix) and stays executable as
pegged orders. Realistic case — the incumbent wins or ties everywhere,
T1 documents that the deep re-entries are load-bearing (the quirk is
the feature), and T4's gap quantifies what instant re-entry is worth.
Worst case — same as realistic but with smaller numbers. In every
branch the register closes fully audited: twelve variables, every one
carrying a tested confirmation, a tested adoption, or a tested
rejection with a mechanism. Nothing here can damage the core: the
incumbent is nested in every comparison, all rivals face the same
walk-forward bar, and the whole program costs about a day.
