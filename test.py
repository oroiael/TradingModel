import requests

# Pointing directly to your local running Terminal
url = "http://127.0.0.1:25520/v2/hist/option/eod"

params = {
    "root": "SOXL",
    "exp": 0,          # The wildcard we are testing
    "strike": 0,       # The wildcard we are testing
    "right": "C",
    "start_date": "20250103", # A known valid trading day
    "end_date": "20250103"
}

print("Pinging local terminal...")
res = requests.get(url, params=params)

print(f"\nStatus Code: {res.status_code}")
print(f"Raw Response: {res.text}")