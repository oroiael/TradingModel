import pandas as pd
import requests
from datetime import date, timedelta

url = "http://127.0.0.1:25503/v3/option/history/eod"

# Let's pull just the last 30 days to guarantee active trading data
end_dt = date.today()
start_dt = end_dt - timedelta(days=30)

params = {
    "symbol": "SOXL",
    "expiration": "20260121",  
    "strike": 32.0,            
    "right": "call",           
    "start_date": start_dt.strftime('%Y%m%d'),
    "end_date": end_dt.strftime('%Y%m%d')
}

print(f"Requesting Expiration: {params['expiration']} | Strike: {params['strike']}...")

try:
    response = requests.get(url, params=params, headers={"Accept": "application/json"})
    
    print(f"\n--- SERVER RESPONSE ---")
    print(f"Status Code: {response.status_code}")
    print(f"Raw Text Received: '{response.text[:200]}'") # Prints the first 200 characters
    print(f"-----------------------\n")

    if response.status_code == 200:
        # Check if the response is completely empty before trying to parse it
        if not response.text.strip():
            print("The server returned a blank page. This means the contract had NO data in this window.")
        else:
            # Safely attempt to parse the JSON
            data = response.json()
            if "response" in data and len(data["response"]) > 0:
                pricing_data = data["response"][0].get("data", [])
                df = pd.DataFrame(pricing_data)
                print(">>> SUCCESS! Data retrieved:")
                print(df.head())
            else:
                print(">>> JSON parsed, but the dataset was empty.")
    else:
        print(f"Failed. The server rejected the request.")
        
except Exception as e:
    print(f"Crash prevented! Error details: {e}")