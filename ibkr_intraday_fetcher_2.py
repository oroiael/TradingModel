import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="google.protobuf")

import os
import threading
import time
from datetime import datetime, timedelta
import pandas as pd
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

class IBapi(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.data = []
        self.req_complete = threading.Event()
        self.connected_event = threading.Event()
        self.error_flag = False

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.connected_event.set()

    def historicalData(self, reqId, bar):
        self.data.append({
            "Date": bar.date,
            "Open": bar.open,
            "High": bar.high,
            "Low": bar.low,
            "Close": bar.close,
            "Volume": bar.volume
        })

    def historicalDataEnd(self, reqId, start, end):
        print(f"[*] Chunk successfully fetched ending at {end}")
        self.req_complete.set()

    def error(self, *args):
        if 162 in args:
            print(f"[!] Historical Data Error (Code 162): {args}")
            self.error_flag = True
            self.req_complete.set()
        elif 502 in args:
            print("[!] Couldn't connect to TWS on the specified port.")
            self.req_complete.set()
        elif 200 in args:
            print(f"[!] Contract Routing Error: {args}")
            self.error_flag = True
            self.req_complete.set()
        elif not any(code in args for code in [2104, 2106, 2158]):
            if any(isinstance(x, int) and x < 1000 and x != -1 for x in args):
                print(f"[-] IBKR Message: {args}")

def run_loop():
    app.run()

# --- Configuration ---
TWS_PORT = 7497          # 7496 for Live Pro, 7497 for Paper
SYMBOL = "SOX"       # Index Symbol
YEARS_TO_FETCH = 6
# ---------------------

app = IBapi()
app.connect("127.0.0.1", TWS_PORT, clientId=998) # Changed ClientID to prevent conflicts

api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()

print("Attempting to connect to TWS...")
if not app.connected_event.wait(timeout=15):
    print("[!] Connection timed out. Ensure TWS is running, API is enabled, and port matches.")
    app.disconnect()
    exit(1)

print(f"Successfully connected! Server version: {app.serverVersion()}")

# Define Contract as an Index
contract = Contract()
contract.conId = 416898
contract.symbol = SYMBOL
contract.secType = "IND"     # 'IND' specifically designates an Index
contract.exchange = "PHLX"  
contract.currency = "USD"

end_date = datetime.now()
start_date = end_date - timedelta(days=YEARS_TO_FETCH * 365)
current_end = end_date

file_name = f"{SYMBOL}_Daily_{YEARS_TO_FETCH}Years.csv"

# Setup Checkpoint Resumption
if os.path.exists(file_name):
    existing_df = pd.read_csv(file_name)
    if not existing_df.empty:
        oldest_date_str = str(existing_df['Date'].min())
        # For daily bars, IBKR returns "YYYYMMDD" (8 characters)
        if len(oldest_date_str) == 8:
            current_end = datetime.strptime(oldest_date_str, "%Y%m%d")
        else:
            parts = oldest_date_str.split()
            current_end = datetime.strptime(f"{parts[0]}", "%Y%m%d")
        print(f"[*] Found existing file. Resuming backward from: {current_end.strftime('%Y-%m-%d')}\n")

print(f"Starting fetch for {SYMBOL} back to {start_date.strftime('%Y-%m-%d')}")

while current_end > start_date:
    end_date_str = current_end.strftime("%Y%m%d %H:%M:%S US/Eastern")
    print(f"Requesting 1 YEAR of data up to: {end_date_str}")
    
    app.data = []
    app.req_complete.clear()
    app.error_flag = False
    
    # Request: 1 Year duration, 1 day bars
    app.reqHistoricalData(reqId=1, contract=contract, endDateTime=end_date_str, 
                          durationStr="1 Y", barSizeSetting="1 day", 
                          whatToShow="TRADES", useRTH=1, formatDate=1, 
                          keepUpToDate=False, chartOptions=[])
    
    if not app.req_complete.wait(timeout=30):
        print("[!] Socket timed out. Retrying...")
        continue
    
    if app.error_flag:
        print("[!] Encountered an error. Check symbol/routing. Cooling down for 10 seconds...")
        time.sleep(10)
        # If TRADES fails for an index, it might require MIDPOINT. 
        # You can manually change 'whatToShow="MIDPOINT"' above if code 162 persists.
        break
        
    if not app.data:
        print("[-] No data received. Stepping back 1 year.")
        current_end -= timedelta(days=365)
        time.sleep(2)
        continue

    # Save Chunk
    chunk_df = pd.DataFrame(app.data)
    write_header = not os.path.exists(file_name)
    chunk_df.to_csv(file_name, mode='a', header=write_header, index=False)
    print(f"[*] Successfully checkpointed {len(chunk_df)} daily bars to disk.")

    # Parse next date to step backwards
    try:
        first_date_str = str(app.data[0]['Date'])
        # Handle Daily format "YYYYMMDD"
        if len(first_date_str) == 8:
            current_end = datetime.strptime(first_date_str, "%Y%m%d")
        else:
            parts = first_date_str.split()
            current_end = datetime.strptime(f"{parts[0]}", "%Y%m%d")
    except Exception as e:
        print(f"[!] Date parse error ({e}), falling back to 365-day subtraction.")
        current_end -= timedelta(days=365)
    
    print("Waiting 11 seconds to respect IBKR pacing rules...")
    time.sleep(11)

app.disconnect()

if os.path.exists(file_name):
    print("\n[*] Performing final sort and deduplication...")
    final_df = pd.read_csv(file_name)
    final_df.drop_duplicates(subset=['Date'], inplace=True)
    final_df.sort_values(by='Date', inplace=True)
    final_df.to_csv(file_name, index=False)
    print(f"[SUCCESS] Cleaned and finalized {len(final_df)} trading days in {file_name}")