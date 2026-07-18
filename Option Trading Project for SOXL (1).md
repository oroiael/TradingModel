Option Trading Project for SOXL

Objective\#1: To analyze various option trading strategies involving SOXL (3x ETF)  
Objective\#2: Identify optimal outcomes generating weekly income  
Objective\#3: backtest and verify each strategy

This part of the project focuses on creating a backtest for a specific strategy per Objective \#3. 

NOTE: Create code that will evaluate the data files and provide details on the data in order to code the rest of this project. The code should evaluate specific parameters of the data sets relative to their nature and purpose. For example one file is 5 minute stock data on the SOXL etf, what do you need to know to evaluate that? What quality checks do you need to do no the data firs.t The second data file is for options data though daily. Make sure the dates match up. 

User: The User is a small investor compared to others. There should no limits as to trade size for the near future.   
User: Wants to be aggressive and alternative….though is open to standard programs as long as “alpha” is generated…and income is flowing on a weekly basis. 

Do not guess, verify assumptions (ask me if needed). DO NOT just go forward and make random changes. Verify that everything works and you are NOT making things up. DO NOT INVENT anything. BE HONEST and Critical \- which means if it works say so, if it doesn’t say that as well. This is real trading not creative writing. 

Parameters: 

1) Only use verifiable data when it excises. If data is missing information or appears to have “zeros” identify and explain. Do not make assumptions without specific direction and confirmation  
2) Find all outcomes, do not make assumptions about what is “good” trading practice or what an institutional investor may or may not do, the measure of success is that our strategy fits the data even if it is unorthodox or different.   
3) Use the option data provided, if more is needed to build stronger results please identify and request, lots of data is available.   
4) Assume the trades follow logical parameters such as a smaller investor is waiting until they can get execution quality, meaning they maybe trade moments after the open if that is part of the trade and not just at open. (use 5 min data)  
5) Option strikes are “whole numbers” for example 100, 101, 102, etc. No decimals. This is true for weeklies. Where strikes are provided in data sets, use those strikes, do not GUESS do not estimate. Use data from the data sets.   
6) For selling options (write) assume 20% above the low end of the spread and the reverse off of the long side when pricing options. USE the option pricing data provided.   
7) If you need to estimate pricing using Black Scholes methods, use the IV data from the data files. If you need to use the BS method then be very clear when, how, and why you did so as it may impact the project

Trade to Model

1. Trade Structure  
   1. Covered Call with a long-dated put (four to six months)  
   2. Calls are sold Monday by 10:00am at the start of the week  
   3. Short calls expire that Friday  
   4. The long-dated put is purchased at the nearest whole dollar strike to the underlying purchase price.   
   5. Long dated put is between 120-180. Look for optimal pricing relative to the trades  
2. Trade mechanics (Three Part Trade)  
   1. Part 1: Short Call  
      1. Every Monday: Sell Call (Write) on SOXL at the nearest out of the money strike (use the data file, do not estimate) to the underlying price at 10:00 am on Monday.   
      2. Call either expires worthless to the option holder on Friday if the Friday closing price is below the strike.   
      3. Call is exercised and the shares are assigned to the option holder if the closing price is above the strike.   
   2. Part 2: Underlying (Long Position)  
      1. If no shares held at Monday 9:30am, buy to open SOXL the number of share proportionate to the trade and the capital available \- see rules elsewhere. This condition occurs either at the beginning of the trade and/or backgest or when the shares are assigned the previous friday as the call is exercised by the option holder.   
      2. Underlying is not sold unless it part of either exercising the put or being assigned on the short call.   
   3. Part 3: Long Put  
      1. Long Put purchased at the nearest expiration to six months from the date of entering the underlying position.   
      2. Long Put is held unless specific conditions are met.   
      3. If Long Put expires, buy a new Long put another six months out.   
      4. If the underlying moves more than 10% between purchase on Monday at 10:00am and 3:30pm on Friday of the week or between when the underlying was originally purchased (carried over from week to week if the call is not exercised and the shares assigned) then roll the put (sell it and buy a new put at the nearest strike to the underlying price \- though the “rolled” put should be pushed out to the nearest expiration period to six months from the roll.   
      5. If the underlying falls more than 15% based on the same parameters as [c.iv](http://c.iv) \- AND the data in the option pricing file shows that the close amount of the option for that week would result in either a positive return equal to or greater than the loss in the underlying, sell the put, sell the underlying and restart the trade next week. If the put does not generate either the same or greater amount as the loss of the underlying. Hold the put.   
      6. Do not exercise the put, unless the gain covers the premium and the loss on the underlying. 

Capital

1. STart with $150,000  
2. Invest 75% (or nearest amount to maintain “whole number” shares \- 100, 101, 102, etc.  
3. For each week’s realized gains including income from writing calls \- reinvest 75% of that gain (cash)and sweep 25% of the cash generated to a separate account. Let that separate account cash cumulate and track the accumulation

Data Files: 

1. SOXL 5 Minute Data for 3 years (SOXL\_5min\_3Years.csv)  
2. SOXL Option Data (SOXL\_Master\_Cleaned.csv)

Quality control

1. Double check for errors every time. Especially in managing data. Do not invent code to cover gaps in understanding, flawed assumptions, or poor data.   
2. Your outputs should have evidence you performed double checks and verified your own code and outputs  
3. Double check you are using the data from the files. If you need other data please ask

OUTPUT

1. CSV file that shows weekly trades and values for each part / leg of the trade  
2. Show price per leg, cost per leg in $, units per leg.   
3. Show how each leg performed (gain / loss)   
4. Show what happened to each leg (assigned shares, exercised call, sold put, etc. or HELD).   
5. Show starting week investable capital, total balance at beginning of the week, cash generated / saved, and gains / losses that impact the final ending week balance.   
6. All numbers are based on actual math and/or pricing in the files. Do not estimate or make anything up. 

