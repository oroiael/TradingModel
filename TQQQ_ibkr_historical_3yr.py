import threading
import time
import pandas as pd
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

# 1. Create the combined EWrapper and EClient class
class IBapi(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.data = [] # List to store the historical bars

    # 2. Callback for receiving each historical bar
    def historicalData(self, reqId, bar):
        # time zone of returned bars is the time zone chosen in TWS on the login screen
        self.data.append({
            "Date": bar.date,
            "Open": bar.open,
            "High": bar.high,
            "Low": bar.low,
            "Close": bar.close,
            "Volume": bar.volume
        })

    # 3. Callback for the end of the historical data stream
    def historicalDataEnd(self, reqId, start, end):
        print(f"\nHistorical data download complete from {start} to {end}.")
        # Disconnect safely after the data is fully received
        self.disconnect()

# Function to run the API message loop in a separate thread
def run_loop():
    app.run()

# 4. Initialize and connect the app
app = IBapi()
# Ports: 7496 for TWS Live, 7497 for TWS Paper, 4001 for IBG Live, 4002 for IBG Paper
app.connect(host="127.0.0.1", port=7497, clientId=1)

# Start the socket in a background thread
api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()

# Give the API a moment to establish the connection
time.sleep(1)

# 5. Define the SOXL Contract
contract = Contract()
contract.symbol = "TQQQ"
contract.secType = "STK"         # ETF's use the STK security type
contract.exchange = "SMART"      # Smart-routing to find the best data
contract.currency = "USD"
contract.primaryExchange = "ARCA" 

print("Requesting 3 Years of EOD Historical Data for TQQQ...")

# 6. Request the Historical Data
# An empty string for endDateTime indicates up to the present moment
app.reqHistoricalData(
    reqId=1,
    contract=contract,
    endDateTime="",              
    durationStr="3 Y",           # Go back 3 Year 
    barSizeSetting="1 day",      # Daily EOD bars
    whatToShow="ADJUSTED_LAST",  # Adjusted for splits/dividends. (Change to "TRADES" for raw data)
    useRTH=1,                    # 1 = Regular Trading Hours only
    formatDate=1,                # 1 = YYYYMMDD formatting
    keepUpToDate=False,          # False = One-time snapshot
    chartOptions=[]
)

# Keep the main thread alive while the background thread fetches data
# The thread will automatically disconnect in historicalDataEnd when finished
while app.isConnected():
    time.sleep(0.5)

# 7. Convert the collected data to a Pandas DataFrame and save to CSV
if app.data:
    df = pd.DataFrame(app.data)
    # Convert 'Date' string to a datetime object for easier merging later
    df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d')
    output_filename = "TQQQ_IBKR_3YR_EOD.csv"
    df.to_csv(output_filename, index=False)
    print(f"Saved {len(df)} rows to {output_filename}")
    print(df.head())
else:
    print("No data was retrieved.")