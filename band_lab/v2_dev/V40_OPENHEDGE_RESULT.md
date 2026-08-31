# V40 — Hedge at the open (V29 Tier 2 #6). Result: **not adopted.**

Tested against `V39_OPENHEDGE_BAR.md`, committed before the code existed.

    python3 band_lab/v2_dev/straddle_backtest.py --v39

## Verdict

**B1b fails 0 of 3. Open-hedging loses to close-hedging by 1.03 percentage
points per cycle**, exactly as V39 predicted from the variance measurement.

| entry DTE | close-hedged | open-hedged | difference | B1b | hedges/session |
|---|---|---|---|---|---|
| 30 | −11.20% | −11.92% | **−0.72%** | FAIL | 0.98 vs 1.07 |
| 37 | −10.11% | −11.88% | **−1.77%** | FAIL | 0.99 vs 1.05 |
| 45 | −11.32% | −11.93% | **−0.61%** | FAIL | 0.96 vs 1.01 |

Open-hedging is **more** hedged per session and still loses, so it is not losing
for want of hedge points. It loses because open-to-open captures 4.35% less
variance than close-to-close, which is what V39 said in advance.

**#6 is not a strategy, it is a scheduling change to #1, and it makes #1 worse.**
The V31/V32 schedule — hedge once daily at the close — is the best of the three
schedules measured.

## Three defects, and how they were found

The bar predicted open-hedging must lose. The run kept saying it won. **That
contradiction, not a test, is what found every one of these.**

| run | result | B1b | defect found |
|---|---|---|---|
| 1 | crashed | — | `ROOT` undefined; reported as "still running" for minutes because only the chain-load lines had appeared and that was read as buffering |
| 2 | **+2.18 pp** | 3/3 PASS | option sold at the close, hedge marked to the open — final intraday session unhedged every cycle |
| 3 | **+1.50 pp** | 3/3 PASS | exit skipped the 09:30 re-hedge — position unhedged ~1.5 sessions |
| 4 | **+1.44 pp** | 3/3 PASS | *(diagnostic added: open was hedging MORE per session, so it was never a clean schedule swap)* |
| **5** | **−1.03 pp** | **0/3 FAIL** | **lookahead: the 09:30 delta used that same session's CLOSING implied vol** |

**The lookahead alone was worth +2.47 percentage points per cycle** — it is the
difference between +1.44 and −1.03, and between adopting this and rejecting it.

A25, written and committed in the V39 bar before any code existed, said the
delta uses **the prior close's** implied vol. The code used the same session's.
**The assumption was right and the implementation did not match it**, which is
only findable by reading one against the other.

This is the same class of error that defined this project: the band strategy's
simulator priced a purchase at a moment that had already passed (V25), and
V31's grid bug manufactured the study's only positive cell by terminating early
(C7). Arithmetic catches a wrong number. Nothing catches information moving
backwards in time except checking.

## The correction to V27 that stands on its own

V27 reported *"overnight, market closed — 80.4% vol, **48% of variance**, not
hedgeable"* and V29, V31 and V38 repeated it. That figure was a **residual**:
total variance minus the 1-minute intraday *path*, which absorbs intraday
autocorrelation along with the gap.

Measured directly from `log(open_t / close_{t−1})` over 1,146 sessions:

| | V27 (residual) | **measured directly** |
|---|---|---|
| overnight vol | 80.4% | **71.7%** |
| share of close-to-close variance | **48%** | **36.7%** |

**"48% of SOXL's variance happens overnight" should be 36.7%.** V27's direction
survives — the gap is a large, unhedgeable share — but the number was inflated
and has been quoted four times.

## What a once-daily hedge actually captures

| schedule | ann. vol | vs close |
|---|---|---|
| once daily at the **close** | 118.2% | — |
| once daily at the **open** | 115.6% | −4.35% |
| **twice** daily (open + close) | 116.8% | −2.5% |

V29's premise — *"hedge to flat at 09:30 and you own the gap without paying to
chase the intraday chop"* — is wrong. A once-daily hedge captures a full
24-hour window whatever hour it is placed. The gap and the session are both
inside it either way. The only thing the hour changes is which covariance term
falls in the window: close-to-close carries Cov(overnight_t, intraday_t) at
+0.000069, open-to-open carries Cov(intraday_t, overnight_{t+1}) at −0.000051.

## Where the catalogue stands

| | verdict | on what |
|---|---|---|
| #1 straddle, hedged daily at the close | **rejected** | −10.11%/cycle, t = −3.76 |
| #2 straddle, unhedged | **not adopted** | −0.22%/cycle, one outlier cell |
| #3 call backspread | **not adopted** | −5.46% trimmed, three cycles carried it |
| #4 long-dated straddle | **inconclusive** | CI [−50%, +189%] on 9 cycles |
| **#6 hedge at the open** | **not adopted** | −1.03 pp/cycle vs #1, 0 of 3 |

Four resolved and rejected, one unresolvable on this data. **Every structure
that has been settled was settled against it.**

Remaining untested: **#5** (long both SOXL and SOXS, which needs pre-2022 data
for the same reason #4 does) and **#7** (asymmetric strangle avoiding the
expensive put wing). #7 is the only one left that this dataset can resolve.
