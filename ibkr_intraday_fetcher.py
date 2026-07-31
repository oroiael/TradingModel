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
        # Confirms connection is fully established and serverVersion is populated
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
        # Uses *args to catch all parameters safely regardless of ibapi version changes
        if 162 in args:
            print(f"[!] Historical Data Pacing Violation or Error: {args}")
            self.error_flag = True
            self.req_complete.set()
        elif 502 in args:
            print("[!] Couldn't connect to TWS on the specified port.")
            self.req_complete.set()
        # Suppress normal startup connection messages (codes 2104, 2106, 2158)
        elif not any(code in args for code in [2104, 2106, 2158]):
            if any(isinstance(x, int) and x < 1000 and x != -1 for x in args):
                print(f"[-] IBKR Message: {args}")

def run_loop():
    app.run()

# --- Configuration ---
TWS_PORT = 7497  # Change to 7497 if using a Paper Trading account
SYMBOL = "VXX"
YEARS_TO_FETCH = 6
# ---------------------

app = IBapi()
app.connect("127.0.0.1", TWS_PORT, clientId=999)

# Start socket in a separate thread
api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()

print("Attempting to connect to TWS...")
if not app.connected_event.wait(timeout=15):
    print("[!] Connection timed out. Ensure TWS is running, API is enabled, and port matches.")
    app.disconnect()
    exit(1)

print(f"Successfully connected! Server version: {app.serverVersion()}")

# Define Contract
contract = Contract()
contract.symbol = SYMBOL
contract.secType = "STK"
contract.exchange = "SMART"
contract.currency = "USD"

# Calculate total date range
end_date = datetime.now()
start_date = end_date - timedelta(days=YEARS_TO_FETCH * 365)
current_end = end_date

# --- RESUMABLE CHECKPOINT SETUP ---
file_name = f"{SYMBOL}_5min_{YEARS_TO_FETCH}Years.csv"

# Load existing file to pick up where we left off if interrupted
if os.path.exists(file_name):
    print(f"[*] Found existing {file_name}. Inspecting to resume download...")
    existing_df = pd.read_csv(file_name)
    if not existing_df.empty:
        oldest_date_str = str(existing_df['Date'].min())
        # Split out any trailing timezone strings (like America/New_York)
        parts = oldest_date_str.split()
        clean_oldest = f"{parts[0]} {parts[1]}"
        current_end = datetime.strptime(clean_oldest, "%Y%m%d %H:%M:%S")
        print(f"[*] Resuming download backward from: {current_end.strftime('%Y-%m-%d %H:%M:%S')}\n")

print(f"Starting fetch for {SYMBOL} back to {start_date.strftime('%Y-%m-%d')}")
print("This will take approximately 25-30 minutes due to IBKR API pacing limits...\n")

while current_end > start_date:
    end_date_str = current_end.strftime("%Y%m%d %H:%M:%S")
    print(f"Requesting 1 week of data up to: {end_date_str}")
    
    app.data = []
    app.req_complete.clear()
    app.error_flag = False
    
    app.reqHistoricalData(reqId=1, contract=contract, endDateTime=end_date_str, 
                          durationStr="1 W", barSizeSetting="5 mins", 
                          whatToShow="TRADES", useRTH=1, formatDate=1, 
                          keepUpToDate=False, chartOptions=[])
    
    # Circuit breaker: 30-second timeout prevents infinite hanging if socket stalls
    if not app.req_complete.wait(timeout=30):
        print("[!] Socket timed out waiting for TWS response. Retrying this chunk...")
        continue
    
    if app.error_flag:
        print("[!] Encountered a pacing error. Cooling down for 60 seconds...")
        time.sleep(60)
        continue
        
    if not app.data:
        print("[-] No data received for this week (holiday/no trading). Stepping back 1 week.")
        current_end -= timedelta(days=7)
        time.sleep(2)
        continue

    # --- CHECKPOINT SAVE ---
    chunk_df = pd.DataFrame(app.data)
    write_header = not os.path.exists(file_name)
    chunk_df.to_csv(file_name, mode='a', header=write_header, index=False)
    print(f"[*] Successfully checkpointed {len(chunk_df)} rows to disk.")

    # Get earliest date in current chunk to set the end_date for NEXT chunk
    try:
        first_date_str = str(app.data[0]['Date'])
        # Drop trailing timezone names by extracting only YYYYMMDD and HH:MM:SS
        parts = first_date_str.split()
        clean_date_str = f"{parts[0]} {parts[1]}"
        current_end = datetime.strptime(clean_date_str, "%Y%m%d %H:%M:%S")
    except Exception as e:
        print(f"[!] Date parse error ({e}), falling back to 7-day subtraction.")
        current_end -= timedelta(days=7)
    
    print("Waiting 11 seconds to respect IBKR pacing rules...")
    time.sleep(11)

# Disconnect API
app.disconnect()

# Final cleanup: sort chronologically and remove any overlapping edge rows
if os.path.exists(file_name):
    print("\n[*] Performing final sort and deduplication on saved dataset...")
    final_df = pd.read_csv(file_name)
    final_df.drop_duplicates(subset=['Date'], inplace=True)
    final_df.sort_values(by='Date', inplace=True)
    final_df.to_csv(file_name, index=False)
    print(f"[SUCCESS] Cleaned and finalized {len(final_df)} total rows in {file_name}")