"""QA harness scenario 2: entry week at $100, then every later week price is
$120 on Monday morning and $115 on Friday afternoon. Friday is always +15% vs
entry (>= 10% hurdle) but below the $120 call strike, so the position is never
called away.

Expected (buggy) result: the put is rolled EVERY Friday forever -- including
"rolls" from strike 115 to the identical strike 115 -- because the rally
baseline is measured from the original entry price and never resets (QA report
finding 1.4). Each roll pays a fresh 7-day extension in pure churn cost while
the reported Cycle_PnL never reflects it (finding 1.3).
"""
import sys, os, tempfile
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
                                 rally_threshold_pct=0.10)
    eng.run_simulation()

    df = pd.DataFrame(eng.trade_logs)
    print(df[['Date', 'SOXL_5min_Trigger_Price', 'Status', 'Put_Strike', 'Put_Exp',
              'Cycle_PnL', 'Trading_Balance', 'Roll_Action']].to_string(index=False))
