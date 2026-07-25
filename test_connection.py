import asyncio
from ib_async import IB, Stock

async def main():
    ib = IB()
    
    print("Attempting to connect to IB Gateway (Paper Trading)...")
    try:
        # Port 4001 is the default for IB Gateway Paper Trading
        # clientId=1 is our unique identification tag for this script instance
        await ib.connectAsync('127.0.0.1', 4001, clientId=1)
        print("✅ Core TCP Socket Connected to IB Gateway!")
        
        # Give IB Gateway a quick 2-second breath to sync up data components
        print("Synchronizing data loops...")
        await asyncio.sleep(2)
        
        # Verify account identity
        print(f"Connected to Account: {ib.wrapper.account}")
        
        # Fetch account value fields explicitly
        print("\nFetching portfolio metrics...")
        account_values = ib.accountValues()
        
        if account_values:
            for value in account_values:
                if value.tag == 'NetLiquidation' and value.currency == 'USD':
                    print(f"💰 Balance (Net Liquidation Value): ${value.value}")
        else:
            print("⚠️ Connected, but account metrics are still loading. Try running again.")
                
        # Test a basic live market contract qualification for your core underlying
        print("\nQualifying SOXL Contract via SMART router...")
        contract = Stock('SOXL', 'SMART', 'USD')
        qualified = await ib.qualifyContractsAsync(contract)
        
        if qualified:
            print(f"🎯 Success! Qualified Contract ID: {qualified[0].conId} ({qualified[0].longName})")
        else:
            print("❌ Contract could not be qualified.")

    except Exception as e:
        print(f"❌ Connection error: {e}")
        print("\nQuick Troubleshooting Checklist:")
        print("1. Ensure IB Gateway is running and you are logged into Paper Trading.")
        print("2. Check Configure > API > Settings -> API Login Port matches 4001.")
        print("3. Ensure 'Trusted IPs' includes 127.0.0.1 to prevent dialogue blocking.")
        
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("\nCleanly disconnected from IB Gateway.")

if __name__ == '__main__':
    asyncio.run(main())