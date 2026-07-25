import pandas as pd

def analyze_grid_results(csv_file):
    print(f"Loading {csv_file} for Tradeability Analysis...")
    try:
        df = pd.read_csv(csv_file)
    except FileNotFoundError:
        print(f"Error: {csv_file} not found. Please ensure the ultimate grid has finished running.")
        return

    initial_rows = len(df)
    print(f"Loaded {initial_rows:,} total simulated strategies.\n")

    # =========================================================================
    # TRADEABILITY & HEDGE ASSUMPTIONS (Tweak these variables as needed)
    # =========================================================================
    MAX_TOTAL_MARGIN  = 0.85   # Max Account Allocation (Alloc * Max Trades)
    MIN_CREDIT        = 0.75   # Minimum upfront premium to afford the PRB Hedge
    MIN_STOP_LOSS     = 2.0    # Stop loss must be >= 2.0x to let the hedge activate
    MIN_TRADES        = 50     # Minimum sample size of trades over the 3 years
    MIN_WIN_RATE      = 75.0   # Must win 75% of the time to be a reliable engine
    MAX_DRAWDOWN      = 45.0   # Raw drawdown limit before the hedge is applied
    # =========================================================================

    # Clean the data types for mathematical filtering
    df['Min Credit Value'] = df['Min Credit'].replace('[\$,]', '', regex=True).astype(float)
    df['Stop Loss Value'] = df['Stop Loss'].replace('x', '', regex=True).astype(float)
    df['Alloc Value'] = df['Alloc'].replace('%', '', regex=True).astype(float) / 100
    df['Total Margin Used'] = df['Alloc Value'] * df['Max Trades']

    print("Applying Real-World Constraints...")
    
    # 1. Filter for Margin Safety
    tradeable_df = df[df['Total Margin Used'] <= MAX_TOTAL_MARGIN]
    print(f" -> {len(tradeable_df):,} survived Margin Constraints (<= {int(MAX_TOTAL_MARGIN*100)}%)")

    # 2. Filter for Hedge Financeability (Minimum Credit)
    tradeable_df = tradeable_df[tradeable_df['Min Credit Value'] >= MIN_CREDIT]
    print(f" -> {len(tradeable_df):,} survived Minimum Credit (>= ${MIN_CREDIT})")

    # 3. Filter for Hedge Compatibility (Wide Stop Loss)
    tradeable_df = tradeable_df[tradeable_df['Stop Loss Value'] >= MIN_STOP_LOSS]
    print(f" -> {len(tradeable_df):,} survived Stop-Loss Filter (>= {MIN_STOP_LOSS}x)")

    # 4. Filter for Statistical Reliability
    tradeable_df = tradeable_df[tradeable_df['Trades'] >= MIN_TRADES]
    tradeable_df = tradeable_df[tradeable_df['Win Rate %'] >= MIN_WIN_RATE]
    print(f" -> {len(tradeable_df):,} survived Statistical Reliability (>{MIN_TRADES} trades, >{MIN_WIN_RATE}% WR)")

    # 5. Filter for Survivability
    tradeable_df = tradeable_df[tradeable_df['Max DD %'] <= MAX_DRAWDOWN]
    print(f" -> {len(tradeable_df):,} survived Max Drawdown (<= {MAX_DRAWDOWN}%)\n")

    if tradeable_df.empty:
        print("Zero strategies survived the strict tradeability constraints. You may need to loosen them.")
        return

    # Sort the surviving strategies by Total ROI
    tradeable_df = tradeable_df.sort_values(by='Total ROI %', ascending=False)
    
    # Drop the temporary calculation columns for clean output
    display_cols = ['DTE', 'Width', 'Min Credit', 'Uptrend', 'Take Profit', 'Stop Loss', 'Alloc', 'Max Trades', 'Sweep', 'Trades', 'Win Rate %', 'Max DD %', 'Vault Cash $', 'Total ROI %']
    final_output = tradeable_df[display_cols]

    final_output.to_csv("SOXL_Tradeable_Hedgeable_Targets.csv", index=False)
    print("Exported final candidates to 'SOXL_Tradeable_Hedgeable_Targets.csv'\n")
    
    print("=== TOP 10 MOST TRADEABLE & HEDGEABLE STRATEGIES ===")
    print(final_output.head(10).to_string(index=False))

if __name__ == "__main__":
    analyze_grid_results("SOXL_ULTIMATE_GRID.csv")