"""QA regression test: put-roll trigger discipline.

Scenario: entry week at $100 (Friday dips to $99 so no assignment), then every
later week price is $120 on Monday morning and $115 on Friday afternoon.
Friday is always below the $120 weekly call strike, so the position is never
called away.

Correct behavior (rally measured from the CURRENT put strike, baseline resets
after each roll):
  * Friday of week 2: 115 >= 100 * 1.10 -> roll put 100 -> 115. Exactly once.
  * Every later Friday: 115 < 115 * 1.10 -> no roll. No same-strike churn.

The original engine measured the rally from the original entry price forever
and rolled the put from strike 115 to the identical strike 115 every single
Friday (~$800/week of churn) - see QA_REPORT_hybrid_collar_backtester.md, 1.4.
"""
import os
import sys
import tempfile

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from hybrid_collar_backtester import HybridCollarBacktester

WORKDIR = tempfile.mkdtemp(prefix="collar_qa_")

rows = []
d = pd.Timestamp("2024-01-08")
while d <= pd.Timestamp("2024-03-01"):
    if d.dayofweek < 5:
        first_week = d < pd.Timestamp("2024-01-15")
        t = d + pd.Timedelta(hours=9, minutes=30)
        end = d + pd.Timedelta(hours=16)
        while t <= end:
            if first_week:
                px = 100.0 if d.dayofweek < 4 else 99.0   # entry week, Friday below strike
            else:
                px = 120.0 if d.dayofweek < 4 else 115.0  # rallied, fades below Mon strike by Fri
            rows.append({"Datetime": t.strftime("%Y-%m-%d %H:%M:%S"), "close": px})
            t += pd.Timedelta(minutes=5)
    d += pd.Timedelta(days=1)
path = os.path.join(WORKDIR, "roll_5min.csv")
pd.DataFrame(rows).to_csv(path, index=False)

if __name__ == "__main__":
    os.chdir(WORKDIR)  # keep the engine's CSV log out of the repo
    eng = HybridCollarBacktester(options_path=os.path.join(WORKDIR, "nope.csv"),
                                 intraday_path=path, initial_capital=100000.0,
                                 rally_threshold_pct=0.10,
                                 require_options_data=False)
    eng.run_simulation()

    df = pd.DataFrame(eng.trade_logs)
    print(df[['Date', 'SOXL_5min_Trigger_Price', 'Status', 'Put_Strike', 'Put_Exp',
              'Cycle_PnL', 'Trading_Balance', 'Roll_Action']].to_string(index=False))

    rolls = int(df['Roll_Action'].str.contains("ROLLED PUT UP").sum())
    assert rolls == 1, f"expected exactly 1 rally roll, got {rolls} (baseline-reset regression)"
    assert not df['Status'].str.contains("CALLED AWAY").any(), "position should never be called away"
    assert df['Put_Strike'].iloc[0] == 100.0 and df['Put_Strike'].iloc[-1] == 115.0, \
        f"put strike path wrong: {df['Put_Strike'].tolist()}"
    strikes_after_roll = df['Put_Strike'].iloc[2:].unique().tolist()
    assert strikes_after_roll == [115.0], f"same-strike churn detected: {strikes_after_roll}"

    print("\nPASS: put rolled exactly once (100 -> 115), baseline reset, no same-strike churn.")
