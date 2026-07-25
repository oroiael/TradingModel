import asyncio
from ib_async import IB, Stock

async def main():
    ib = IB()
    
    print("Connecting to IB Gateway on Port 4001...")
    try:
        await ib.connectAsync('127.0.0.1', 4001, clientId=1)
        print("✅ Connected!")
        
        # Pull and display your active paper trading account number safely
        managed_accounts = ib.wrapper.accounts
        print(f"Active Managed Account Profile: {managed_accounts}")
        
        # Step 1: Qualify the underlying stock
        print("\nQualifying SOXL Contract via SMART router...")
        underlying = Stock('SOXL', 'SMART', 'USD')
        await ib.qualifyContractsAsync(underlying)
        
        # Step 2: Request the full live option chains
        print("Requesting live option chains from exchange routing...")
        chains = await ib.reqSecDefOptParamsAsync(
            underlying.symbol, '', underlying.secType, underlying.conId
        )
        
        # Step 3: Parse and print out a summary of the chain data structures
        if chains:
            # Typically, US stocks return a list of chains representing different exchange listings.
            # We will look at the primary 'SMART' routed chain parameters.
            primary_chain = chains[0]
            
            print("\n" + "="*50)
            print(f"🎯 LIVE OPTION CHAIN SUMMARY FOR {underlying.symbol}")
            print("="*50)
            print(f"Trading Class:   {primary_chain.tradingClass}")
            print(f"Multiplier:      {primary_chain.multiplier}")
            
            # Sort and format active expirations
            expirations = sorted(list(primary_chain.expirations))
            print(f"\n📅 Available Expirations Count: {len(expirations)}")
            print(f"   Nearest Expiration:       {expirations[0]}")
            print(f"   Furthest Expiration:      {expirations[-1]}")
            
            # Sort and format active strikes
            strikes = sorted(list(primary_chain.strikes))
            print(f"\n💸 Available Strike Count:      {len(strikes)}")
            print(f"   Lowest Strike Price:      ${strikes[0]}")
            print(f"   Highest Strike Price:     ${strikes[-1]}")
            print("="*50)
            
            # Print a clean list of the next 4 upcoming expirations for strategic targeting
            print("\nNext 4 Upcoming Expiration Dates for your Collar / Spread selection:")
            for exp in expirations[:4]:
                print(f" -> {exp}")
                
        else:
            print("❌ No option chain parameters returned. Verify market data permissions.")

    except Exception as e:
        print(f"❌ Execution error: {e}")
        
    finally:
        ib.disconnect()
        print("\nCleanly disconnected from IB Gateway.")

if __name__ == '__main__':
    asyncio.run(main())